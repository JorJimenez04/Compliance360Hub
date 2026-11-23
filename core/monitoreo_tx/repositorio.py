"""
Acceso a datos del módulo: la única capa que ejecuta SQL.

Este módulo NO verifica permisos: lo hace servicio.py.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import Connection, Engine, func, or_, select, update

from core.monitoreo_tx.domain.entidades import EmpresaVista, FiltrosTransacciones
from core.monitoreo_tx.tablas import (
    clientes, tx_empresas, tx_sincronizaciones, tx_transacciones, usuario_empresas,
)

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
_COLUMNAS_EMPRESA = [E.id, E.nombre_reporte, E.activa, E.cliente_id, E.notas, E.organizacion_id,
                     C.razon_social, C.nit, C.nivel_riesgo]


def _a_vista(fila) -> EmpresaVista:
    return EmpresaVista(
        id=fila.id, nombre_reporte=fila.nombre_reporte, activa=bool(fila.activa),
        cliente_id=fila.cliente_id, razon_social=fila.razon_social, nit=fila.nit,
        nivel_riesgo=fila.nivel_riesgo, notas=fila.notas, organizacion_id=fila.organizacion_id,
    )


class EmpresasRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _base(self):
        return select(*_COLUMNAS_EMPRESA).select_from(
            tx_empresas.outerjoin(clientes, E.cliente_id == C.id))

    def listar(self, solo_activas: bool = False, organizacion_id: int | None = None) -> list[EmpresaVista]:
        """organizacion_id=None: todas (solo para internos; el servicio decide quién puede)."""
        q = self._base()
        if solo_activas:
            q = q.where(E.activa.is_(True))
        if organizacion_id is not None:
            q = q.where(E.organizacion_id == organizacion_id)
        with self.engine.connect() as conn:
            filas = conn.execute(q).all()
        return sorted((_a_vista(f) for f in filas), key=lambda e: e.nombre_visible.casefold())

    def obtener(self, empresa_id: int) -> EmpresaVista | None:
        with self.engine.connect() as conn:
            fila = conn.execute(self._base().where(E.id == empresa_id)).first()
        return _a_vista(fila) if fila else None

    def ids_de_usuario(self, usuario_id: int) -> set[int]:
        """Empresas que un usuario con rol «cliente» tiene permitido consultar."""
        with self.engine.connect() as conn:
            filas = conn.scalars(
                select(usuario_empresas.c.empresa_id).where(usuario_empresas.c.usuario_id == usuario_id))
            return set(filas)

    def enlazar(self, empresa_id: int, cliente_id: int | None) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(tx_empresas).where(E.id == empresa_id).values(cliente_id=cliente_id))

    def mover_a_organizacion(self, empresa_id: int, organizacion_id: int) -> dict:
        """Pasa la empresa a otra organización en una sola transacción:
        quita el enlace con un cliente de la organización anterior y las asignaciones
        de usuarios que no son de la nueva (nadie conserva acceso por arrastre)."""
        from sqlalchemy import text as _text
        with self.engine.begin() as conn:
            existe = conn.scalar(_text("SELECT 1 FROM organizaciones WHERE id = :o AND activa"),
                                 {"o": organizacion_id})
            if not existe:
                return {"ok": False}
            conn.execute(update(tx_empresas).where(E.id == empresa_id)
                         .values(organizacion_id=organizacion_id, cliente_id=None))
            quitadas = conn.execute(_text(
                "DELETE FROM usuario_empresas ue USING usuarios u "
                "WHERE ue.usuario_id = u.id AND ue.empresa_id = :e "
                "AND u.organizacion_id IS DISTINCT FROM :o"), {"e": empresa_id, "o": organizacion_id}).rowcount
        return {"ok": True, "asignaciones_quitadas": quitadas}

    def cambiar_estado(self, empresa_id: int, activa: bool) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(tx_empresas).where(E.id == empresa_id).values(activa=activa))

    def clientes_disponibles(self, organizacion_id: int | None = None) -> list[dict]:
        """Fichas de Gestión de Clientes para enlazar (id, razón social, NIT, riesgo, organización)."""
        q = select(C.id, C.razon_social, C.nit, C.nivel_riesgo, C.organizacion_id).order_by(C.razon_social)
        if organizacion_id is not None:
            q = q.where(C.organizacion_id == organizacion_id)
        with self.engine.connect() as conn:
            filas = conn.execute(q).mappings().all()
        return [dict(f) for f in filas]

    def organizacion_de_cliente(self, cliente_id: int) -> int | None:
        with self.engine.connect() as conn:
            return conn.scalar(select(C.organizacion_id).where(C.id == cliente_id))


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
