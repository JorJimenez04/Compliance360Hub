"""
Reglas de negocio del módulo: permisos, caché y auditoría.

Los permisos se validan aquí (no solo en la pantalla): toda operación pública
recibe el usuario de Compliance360 Hub (dict de st.session_state["user"]).

Caché: las consultas se guardan en memoria por (versión de datos, empresa,
filtros). La versión es el id de la última carga exitosa, así una nueva carga
invalida todo. El tamaño es pequeño a propósito: una empresa grande ocupa
cientos de MB en memoria.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine

from app.monitoreo_tx.characterization.base_characterization import caracterizar_cliente_gafi
from app.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO
from app.monitoreo_tx.domain import metricas
from app.monitoreo_tx.domain.continuidad import Continuidad, verificar_continuidad
from app.monitoreo_tx.domain.entidades import EmpresaVista, FiltrosTransacciones, OpcionesFiltro
from app.monitoreo_tx.domain.errores import NoEncontrado, PermisoDenegado
from app.monitoreo_tx.etl.sync import ResumenSincronizacion, sincronizar
from app.monitoreo_tx.repositorio import EmpresasRepo, SincronizacionesRepo, TransaccionesRepo
from app.monitoreo_tx.risk_analysis import analizar_riesgo_cliente

logger = logging.getLogger(__name__)

ENTIDAD_AUDITORIA = "tx_transacciones"


def puede_ver(user: dict | None) -> bool:
    return bool(user) and user.get("rol") in ROLES_MONITOREO


def puede_cargar(user: dict | None) -> bool:
    return bool(user) and user.get("rol") in ROLES_CARGA


def _exigir(user: dict | None, roles: frozenset[str]) -> None:
    if not user or user.get("rol") not in roles:
        raise PermisoDenegado("Su rol no tiene acceso al Monitoreo Transaccional.")


def registrar_auditoria(user: dict, accion: str, descripcion: str, entidad_id: int | None = None,
                        valores_nuevos: dict | None = None, entidad: str = ENTIDAD_AUDITORIA) -> None:
    """Escribe en log_auditoria de Compliance360 Hub. Un fallo aquí no debe tumbar la pantalla."""
    try:
        from db.database import get_session
        from db.repositories.audit_repo import AuditRepository
        with next(get_session()) as session:
            AuditRepository(session).registrar(
                username=user.get("username", "desconocido"),
                usuario_id=user.get("id"),
                accion=accion,
                entidad=entidad,
                entidad_id=entidad_id,
                descripcion=descripcion,
                valores_nuevos=valores_nuevos,
                rol_usuario=user.get("rol"),
            )
    except Exception:
        logger.exception("No se pudo registrar en log_auditoria: %s", descripcion)


class MonitoreoService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.transacciones = TransaccionesRepo(engine)
        self.empresas_repo = EmpresasRepo(engine)
        self.sincronizaciones = SincronizacionesRepo(engine)
        self._consultar = lru_cache(maxsize=4)(self._consultar_sin_cache)
        self._riesgo = lru_cache(maxsize=8)(self._riesgo_sin_cache)
        self._totales = lru_cache(maxsize=32)(self._totales_sin_cache)
        self._continuidad = lru_cache(maxsize=32)(self._continuidad_sin_cache)

    # ---------- Estado de los datos ----------
    def ultima_carga(self) -> dict | None:
        return self.sincronizaciones.ultima_exitosa()

    def _version(self) -> int:
        ultima = self.sincronizaciones.ultima_exitosa()
        return ultima["id"] if ultima else 0

    # ---------- Empresas ----------
    def empresas(self, user: dict, solo_activas: bool = True) -> list[EmpresaVista]:
        _exigir(user, ROLES_MONITOREO)
        return self.empresas_repo.listar(solo_activas=solo_activas)

    def _empresa(self, user: dict, empresa_id: int) -> EmpresaVista:
        _exigir(user, ROLES_MONITOREO)
        empresa = self.empresas_repo.obtener(empresa_id)
        if empresa is None:
            raise NoEncontrado("La empresa no existe.")
        return empresa

    def conteo_por_empresa(self, user: dict) -> dict[str, int]:
        _exigir(user, ROLES_MONITOREO)
        return self.transacciones.conteo_por_cliente()

    def clientes_disponibles(self, user: dict) -> list[dict]:
        _exigir(user, ROLES_CARGA)
        return self.empresas_repo.clientes_disponibles()

    def enlazar_cliente(self, user: dict, empresa_id: int, cliente_id: int | None) -> None:
        _exigir(user, ROLES_CARGA)
        empresa = self._empresa(user, empresa_id)
        self.empresas_repo.enlazar(empresa_id, cliente_id)
        registrar_auditoria(
            user, "UPDATE",
            f"Monitoreo TX: empresa «{empresa.nombre_reporte}» enlazada con cliente {cliente_id or '(ninguno)'}",
            entidad_id=empresa_id,
            valores_nuevos={"cliente_id": cliente_id, "cliente_id_anterior": empresa.cliente_id},
            entidad="tx_empresas",
        )

    def cambiar_estado(self, user: dict, empresa_id: int, activa: bool) -> None:
        _exigir(user, ROLES_CARGA)
        empresa = self._empresa(user, empresa_id)
        self.empresas_repo.cambiar_estado(empresa_id, activa)
        registrar_auditoria(
            user, "UPDATE",
            f"Monitoreo TX: empresa «{empresa.nombre_reporte}» {'activada' if activa else 'desactivada'}",
            entidad_id=empresa_id,
            entidad="tx_empresas",
        )

    # ---------- Consultas ----------
    def opciones_filtro(self, user: dict, empresa_id: int) -> OpcionesFiltro:
        empresa = self._empresa(user, empresa_id)
        desde, hasta = self.transacciones.rango_fechas(empresa.nombre_reporte)
        return OpcionesFiltro(desde, hasta, tuple(self.transacciones.estados(empresa.nombre_reporte)))

    def transacciones_filtradas(self, user: dict, empresa_id: int,
                                filtros: FiltrosTransacciones) -> pd.DataFrame:
        """El DataFrame se comparte entre sesiones a través de la caché: tratarlo como solo lectura."""
        empresa = self._empresa(user, empresa_id)
        return self._consultar(self._version(), empresa.nombre_reporte, filtros)

    def csv_transacciones(self, user: dict, empresa_id: int, filtros: FiltrosTransacciones) -> bytes:
        """CSV completo (con cuentas y documentos sin enmascarar). Se llama solo al descargar."""
        df = self.transacciones_filtradas(user, empresa_id, filtros)
        return metricas.a_csv(metricas.tabla_para_exporte(df))

    def kpis_periodo_anterior(self, user: dict, empresa_id: int,
                              filtros: FiltrosTransacciones) -> metricas.KPIs | None:
        empresa = self._empresa(user, empresa_id)
        if not (filtros.desde and filtros.hasta):
            return None
        desde, hasta = metricas.periodo_anterior(filtros.desde, filtros.hasta)
        anterior = replace(filtros, desde=desde, hasta=hasta)
        totales = self._totales(self._version(), empresa.nombre_reporte, anterior)
        if totales.empty:
            return None
        return metricas.kpis_desde_totales(totales)

    def continuidad(self, user: dict, empresa_id: int) -> Continuidad:
        """Completitud de todo lo guardado de la empresa: numeración y saldo corrido."""
        empresa = self._empresa(user, empresa_id)
        return self._continuidad(self._version(), empresa.nombre_reporte)

    def evaluar_riesgo(self, user: dict, empresa_id: int, filtros: FiltrosTransacciones) -> dict:
        """Scoring GAFI/UIAF indicativo sobre las transacciones del filtro."""
        empresa = self._empresa(user, empresa_id)
        return self._riesgo(self._version(), empresa.nombre_reporte, filtros)

    # ---------- Carga ----------
    def cargar_archivo(self, user: dict, ruta: Path, nombre_archivo: str, cliente: str | None = None,
                       forzar: bool = False, eliminar_faltantes: bool = False) -> ResumenSincronizacion:
        _exigir(user, ROLES_CARGA)
        try:
            resumen = sincronizar(
                ruta, engine=self.engine, forzar=forzar, eliminar_faltantes=eliminar_faltantes,
                cliente=cliente, usuario=user.get("username"), nombre_archivo=nombre_archivo,
            )
        except Exception as e:
            registrar_auditoria(user, "CREATE", f"Monitoreo TX: carga fallida de «{nombre_archivo}»: {e}")
            raise
        registrar_auditoria(
            user, "CREATE",
            f"Monitoreo TX: carga «{nombre_archivo}» · {resumen.resultado} · "
            f"{resumen.insertadas} nuevas, {resumen.actualizadas} actualizadas, {resumen.rechazadas} rechazadas, "
            f"{resumen.faltantes} faltantes, {resumen.descuadres_saldo} saldos descuadrados",
            valores_nuevos={k: v for k, v in resumen.to_dict().items()
                            if k not in ("rechazos", "advertencias", "verificacion")},
        )
        return resumen

    def bitacora(self, user: dict, limite: int = 50) -> list[dict]:
        _exigir(user, ROLES_MONITOREO)
        return self.sincronizaciones.listar(limite)

    # ---------- Internos (sin control de acceso; no exponer) ----------
    def _consultar_sin_cache(self, version: int, cliente: str, filtros: FiltrosTransacciones) -> pd.DataFrame:
        return self.transacciones.consultar(cliente, filtros)

    def _totales_sin_cache(self, version: int, cliente: str, filtros: FiltrosTransacciones) -> pd.DataFrame:
        return self.transacciones.totales(cliente, filtros)

    def _continuidad_sin_cache(self, version: int, cliente: str) -> Continuidad:
        return verificar_continuidad(self.transacciones.datos_continuidad(cliente))

    def _riesgo_sin_cache(self, version: int, cliente: str, filtros: FiltrosTransacciones) -> dict:
        df = self._consultar(version, cliente, filtros)
        df_legacy = metricas.a_formato_legacy(df)
        perfil = caracterizar_cliente_gafi(df_legacy)
        return analizar_riesgo_cliente(df_legacy, perfil, cliente)


_servicio: MonitoreoService | None = None


def servicio() -> MonitoreoService:
    """Instancia única por proceso, sobre el motor de Compliance360 Hub."""
    global _servicio
    if _servicio is None:
        from db.database import engine
        _servicio = MonitoreoService(engine)
    return _servicio
