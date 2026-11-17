"""
Acceso a datos del módulo: la única capa que ejecuta SQL.

Este módulo NO verifica permisos: lo hace servicio.py.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import Connection, Engine, func, or_, select, update

from core.monitoreo_tx.domain.entidades import EmpresaVista, FiltrosTransacciones
from core.monitoreo_tx.tablas import clientes, tx_empresas, tx_sincronizaciones, tx_transacciones

T = tx_transacciones.c
E = tx_empresas.c
C = clientes.c
S = tx_sincronizaciones.c

COLUMNAS_CONSULTA = [
    T.fecha_hora, T.fecha, T.id_transaccion, T.referencia_externa, T.tipo_transaccion,
    T.beneficiario, T.tipo_identificacion, T.tipo_persona, T.id_beneficiario, T.banco,
    T.tipo_cuenta, T.numero_cuenta, T.monto, T.comision, T.monto_total, T.estado,
    T.exitosa, T.saldo, T.descripcion,
]


# =========================
# Transacciones
# =========================
class TransaccionesRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def conteo_por_cliente(self) -> dict[str, int]:
        with self.engine.connect() as conn:
            filas = conn.execute(select(T.cliente, func.count()).group_by(T.cliente))
            return {cliente: n for cliente, n in filas}

    def contar(self) -> int:
        with self.engine.connect() as conn:
            return conn.scalar(select(func.count()).select_from(tx_transacciones)) or 0

    def rango_fechas(self, cliente: str) -> tuple[date | None, date | None]:
        with self.engine.connect() as conn:
            minimo, maximo = conn.execute(
                select(func.min(T.fecha), func.max(T.fecha)).where(T.cliente == cliente)
            ).one()
        return minimo, maximo

    def estados(self, cliente: str) -> list[str]:
        with self.engine.connect() as conn:
            return list(conn.scalars(
                select(T.estado).where(T.cliente == cliente).distinct().order_by(T.estado)
            ))

    def datos_continuidad(self, cliente: str, conn: Connection | None = None) -> pd.DataFrame:
        """No., saldo y monto total de todas las transacciones de la empresa (para verificar completitud)."""
        q = select(T.no_registro, T.saldo, T.monto_total).where(T.cliente == cliente)
        if conn is not None:
            return pd.DataFrame(conn.execute(q).all(), columns=["no_registro", "saldo", "monto_total"])
        with self.engine.connect() as c:
            return pd.DataFrame(c.execute(q).all(), columns=["no_registro", "saldo", "monto_total"])

    def consultar(self, cliente: str, filtros: FiltrosTransacciones) -> pd.DataFrame:
        """
        Transacciones de una empresa. `filtros.estados=None` no filtra por estado;
        una tupla vacía devuelve vacío. `filtros.texto` busca sin distinguir
        mayúsculas en ID, referencia externa, descripción, beneficiario y documento.
        """
        q = _filtrar(select(*COLUMNAS_CONSULTA), cliente, filtros)
        q = q.order_by(T.fecha_hora.desc(), T.no_registro.desc())
        with self.engine.connect() as conn:
            df = pd.read_sql(q, conn)
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
        df["exitosa"] = df["exitosa"].astype(bool)
        return df

    def totales(self, cliente: str, filtros: FiltrosTransacciones) -> pd.DataFrame:
        """Conteo y monto por (tipo de transacción, exitosa): pocas filas, sin traer el detalle."""
        q = _filtrar(
            select(T.tipo_transaccion, T.exitosa,
                   func.count().label("transacciones"), func.sum(T.monto).label("monto")),
            cliente, filtros,
        ).group_by(T.tipo_transaccion, T.exitosa)
        with self.engine.connect() as conn:
            df = pd.read_sql(q, conn)
        df["exitosa"] = df["exitosa"].astype(bool)
        df["monto"] = df["monto"].fillna(0.0)
        return df


def _filtrar(q, cliente: str, filtros: FiltrosTransacciones):
    q = q.where(T.cliente == cliente)
    if filtros.desde:
        q = q.where(T.fecha >= filtros.desde)
    if filtros.hasta:
        q = q.where(T.fecha <= filtros.hasta)
    if filtros.estados is not None:
        q = q.where(T.estado.in_(filtros.estados))
    texto = filtros.texto.strip()
    if texto:
        q = q.where(or_(*(
            col.icontains(texto, autoescape=True)
            for col in (T.id_transaccion, T.referencia_externa, T.descripcion,
                        T.beneficiario, T.id_beneficiario)
        )))
    return q


# =========================
# Empresas (hojas del reporte) y su enlace con clientes
# =========================
_COLUMNAS_EMPRESA = [E.id, E.nombre_reporte, E.activa, E.cliente_id, E.notas,
                     C.razon_social, C.nit, C.nivel_riesgo]


def _a_vista(fila) -> EmpresaVista:
    return EmpresaVista(
        id=fila.id, nombre_reporte=fila.nombre_reporte, activa=bool(fila.activa),
        cliente_id=fila.cliente_id, razon_social=fila.razon_social, nit=fila.nit,
        nivel_riesgo=fila.nivel_riesgo, notas=fila.notas,
    )


class EmpresasRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _base(self):
        return select(*_COLUMNAS_EMPRESA).select_from(
            tx_empresas.outerjoin(clientes, E.cliente_id == C.id))

    def listar(self, solo_activas: bool = False) -> list[EmpresaVista]:
        q = self._base()
        if solo_activas:
            q = q.where(E.activa.is_(True))
        with self.engine.connect() as conn:
            filas = conn.execute(q).all()
        return sorted((_a_vista(f) for f in filas), key=lambda e: e.nombre_visible.casefold())

    def obtener(self, empresa_id: int) -> EmpresaVista | None:
        with self.engine.connect() as conn:
            fila = conn.execute(self._base().where(E.id == empresa_id)).first()
        return _a_vista(fila) if fila else None

    def enlazar(self, empresa_id: int, cliente_id: int | None) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(tx_empresas).where(E.id == empresa_id).values(cliente_id=cliente_id))

    def cambiar_estado(self, empresa_id: int, activa: bool) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(tx_empresas).where(E.id == empresa_id).values(activa=activa))

    def clientes_disponibles(self) -> list[dict]:
        """Fichas de Gestión de Clientes para enlazar (id, razón social, NIT, riesgo)."""
        with self.engine.connect() as conn:
            filas = conn.execute(
                select(C.id, C.razon_social, C.nit, C.nivel_riesgo).order_by(C.razon_social)
            ).mappings().all()
        return [dict(f) for f in filas]


def registrar_empresas_faltantes(conn: Connection, nombres_reporte: list[str]) -> list[str]:
    """Crea la ficha de las hojas que aún no tienen empresa. Devuelve las nuevas."""
    existentes = set(conn.scalars(select(E.nombre_reporte)))
    nuevas = sorted({n for n in nombres_reporte if n and n not in existentes}, key=str.casefold)
    if nuevas:
        conn.execute(tx_empresas.insert(), [{"nombre_reporte": n, "activa": True} for n in nuevas])
    return nuevas


# =========================
# Bitácora de sincronizaciones
# =========================
class SincronizacionesRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def ultima_exitosa(self) -> dict | None:
        with self.engine.connect() as conn:
            fila = conn.execute(
                select(tx_sincronizaciones).where(S.resultado == "OK").order_by(S.id.desc()).limit(1)
            ).mappings().first()
        return dict(fila) if fila else None

    def listar(self, limite: int = 50) -> list[dict]:
        with self.engine.connect() as conn:
            filas = conn.execute(
                select(tx_sincronizaciones).order_by(S.id.desc()).limit(limite)
            ).mappings().all()
        return [dict(f) for f in filas]
