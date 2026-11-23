"""
Clientes de una organización (p. ej. los clientes de Adamo: CM Grupo Tecno, Paxum…)
y su expediente 360 alimentado por el monitoreo transaccional.

Uso interno del equipo de cumplimiento: este módulo NO valida permisos; lo hace la API.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import Engine, text

from core.cumplimiento import catalogo as cat
from core.cumplimiento.alertas import ABIERTAS
from core.monitoreo_tx.domain import metricas
from core.monitoreo_tx.domain.entidades import FiltrosTransacciones
from core.monitoreo_tx.repositorio import CarteraRepo

NIVELES_CLIENTE = ("Sin calificar", *cat.NIVELES)
ESTADOS_CLIENTE = ("Prospecto", "Activo", "Suspendido", "Terminado")
CAMPOS_EDITABLES = ("razon_social", "nit", "tipo_persona", "modelos_negocio", "nivel_riesgo", "estado",
                    "sector_ciiu", "pais_constitucion", "sitio_web", "proxima_revision", "perfil_volumen_mensual",
                    "perfil_operaciones_mes", "perfil_ticket_promedio", "perfil_paises", "notas")


class ErrorCliente(ValueError):
    pass


def listar(engine: Engine, organizacion_id: int) -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(text(
            "SELECT c.id, c.razon_social, c.nit, c.nivel_riesgo, c.estado, c.modelos_negocio, c.proxima_revision, "
            "  COALESCE(json_agg(json_build_object('id', e.id, 'nombre', e.nombre_reporte) ORDER BY e.nombre_reporte) "
            "           FILTER (WHERE e.id IS NOT NULL), '[]') AS empresas, "
            "  (SELECT count(*) FROM cmp_alertas a JOIN tx_empresas x ON x.id = a.empresa_id "
            "    WHERE x.cliente_id = c.id AND a.estado = ANY(:ab)) AS alertas_abiertas, "
            "  (SELECT count(*) FROM cmp_alertas a JOIN tx_empresas x ON x.id = a.empresa_id "
            "    WHERE x.cliente_id = c.id AND a.estado = ANY(:ab) AND a.prioridad IN ('Crítica', 'Alta')) AS alertas_altas "
            "FROM clientes c LEFT JOIN tx_empresas e ON e.cliente_id = c.id "
            "WHERE c.organizacion_id = :o GROUP BY c.id ORDER BY lower(c.razon_social)"),
            {"o": organizacion_id, "ab": list(ABIERTAS)}).mappings().all()
    return [{**dict(f), "modelos_negocio": list(f["modelos_negocio"] or [])} for f in filas]


def empresas_sin_cliente(engine: Engine, organizacion_id: int) -> list[dict]:
    with engine.connect() as conn:
        return [dict(f) for f in conn.execute(text(
            "SELECT e.id, e.nombre_reporte AS nombre, "
            "  (SELECT count(*) FROM tx_transacciones t WHERE t.cliente = e.nombre_reporte) AS transacciones "
            "FROM tx_empresas e WHERE e.organizacion_id = :o AND e.cliente_id IS NULL "
            "ORDER BY lower(e.nombre_reporte)"), {"o": organizacion_id}).mappings()]


def crear_desde_empresas(engine: Engine, organizacion_id: int, empresa_ids: list[int], usuario: str) -> list[dict]:
    """Crea la ficha de cada empresa monitoreada (sin cliente) y las enlaza. Todo o nada."""
    if not empresa_ids:
        raise ErrorCliente("Seleccione al menos una empresa.")
    creados = []
    with engine.begin() as conn:
        empresas = conn.execute(text(
            "SELECT id, nombre_reporte, cliente_id FROM tx_empresas WHERE id = ANY(:ids) AND organizacion_id = :o "
            "FOR UPDATE"), {"ids": list(set(empresa_ids)), "o": organizacion_id}).mappings().all()
        if len(empresas) != len(set(empresa_ids)):
            raise ErrorCliente("Alguna empresa no existe o es de otra organización.")
        if any(e["cliente_id"] for e in empresas):
            raise ErrorCliente("Alguna empresa ya está enlazada con un cliente.")
        for e in empresas:
            cid = conn.execute(text(
                "INSERT INTO clientes (razon_social, organizacion_id, estado, creado_por) "
                "VALUES (:r, :o, 'Activo', :u) RETURNING id"),
                {"r": e["nombre_reporte"].strip(), "o": organizacion_id, "u": usuario}).scalar_one()
            conn.execute(text("UPDATE tx_empresas SET cliente_id = :c WHERE id = :e"), {"c": cid, "e": e["id"]})
            creados.append({"id": cid, "razon_social": e["nombre_reporte"], "empresa_id": e["id"]})
    return creados


def obtener(engine: Engine, cliente_id: int) -> dict | None:
    with engine.connect() as conn:
        f = conn.execute(text(
            "SELECT c.id, c.organizacion_id, o.nombre AS organizacion, c.razon_social, c.nit, c.tipo_persona, "
            "c.modelos_negocio, c.nivel_riesgo, c.estado, c.sector_ciiu, c.pais_constitucion, c.sitio_web, "
            "c.proxima_revision, c.fecha_ultima_calificacion, c.es_pep, c.en_listas_restriccion, "
            "c.perfil_volumen_mensual, c.perfil_operaciones_mes, c.perfil_ticket_promedio, c.perfil_paises, "
            "c.perfil_actualizado, c.notas, c.created_at "
            "FROM clientes c JOIN organizaciones o ON o.id = c.organizacion_id WHERE c.id = :id"),
            {"id": cliente_id}).mappings().first()
        if not f:
            return None
        empresas = conn.execute(text(
            "SELECT id, nombre_reporte AS nombre, activa FROM tx_empresas WHERE cliente_id = :c ORDER BY nombre_reporte"),
            {"c": cliente_id}).mappings().all()
    d = dict(f)
    for k in ("perfil_volumen_mensual", "perfil_ticket_promedio"):
        d[k] = float(d[k]) if d[k] is not None else None
    d["modelos_negocio"] = list(d["modelos_negocio"] or [])
    d["perfil_paises"] = list(d["perfil_paises"] or [])
    d["empresas"] = [dict(e) for e in empresas]
    return d


def actualizar(engine: Engine, cliente_id: int, cambios: dict) -> dict:
    valores: dict = {}
    for campo, v in cambios.items():
        if campo not in CAMPOS_EDITABLES:
            continue
        if isinstance(v, str):
            v = v.strip() or None
        if campo == "razon_social" and not v:
            raise ErrorCliente("La razón social es obligatoria.")
        if campo == "tipo_persona" and v not in (cat.PJ, cat.PN):
            raise ErrorCliente("Tipo de persona no válido.")
        if campo == "nivel_riesgo" and v not in NIVELES_CLIENTE:
            raise ErrorCliente("Nivel de riesgo no válido: use Alto, Medio o Bajo.")
        if campo == "estado" and v not in ESTADOS_CLIENTE:
            raise ErrorCliente("Estado no válido.")
        if campo == "modelos_negocio":
            v = list(dict.fromkeys(v or []))
            malos = [m for m in v if cat.modelo(m) is None]
            if malos:
                raise ErrorCliente(f"Modelos de negocio no válidos: {', '.join(malos)}")
        if campo == "perfil_paises":
            v = sorted({p.strip() for p in (v or []) if p and p.strip()})
        if campo.startswith("perfil_") and campo != "perfil_paises" and v is not None and float(v) < 0:
            raise ErrorCliente("El perfil declarado no admite valores negativos.")
        valores[campo] = v
    if not valores:
        return obtener(engine, cliente_id)
    if any(k.startswith("perfil_") for k in valores):
        valores["perfil_actualizado"] = date.today()
    if "nivel_riesgo" in valores:
        valores["fecha_ultima_calificacion"] = date.today()
    sets = ", ".join(f"{k} = :{k}" for k in valores)     # claves de una lista fija, no de la petición
    with engine.begin() as conn:
        hecho = conn.execute(text(f"UPDATE clientes SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                             {**valores, "id": cliente_id}).rowcount
    if not hecho:
        raise LookupError("El cliente no existe.")
    return obtener(engine, cliente_id)


# =========================
# Lo que dice el monitoreo
# =========================
def _nombres_empresas(engine: Engine, cliente_id: int) -> list[str]:
    with engine.connect() as conn:
        return list(conn.scalars(text("SELECT nombre_reporte FROM tx_empresas WHERE cliente_id = :c"), {"c": cliente_id}))


def resumen_operacion(engine: Engine, cliente_id: int, dias: int = 90) -> dict:
    """Indicadores de los últimos `dias` días con datos, sumando todas las empresas del cliente."""
    nombres = _nombres_empresas(engine, cliente_id)
    repo = CarteraRepo(engine)
    _, maximo, _ = repo.opciones(nombres)
    if not maximo:
        return {"desde": None, "hasta": None, "kpis": None, "ultima_operacion": None}
    desde = maximo - timedelta(days=dias - 1)
    diario = repo.diario(nombres, FiltrosTransacciones(desde=desde, hasta=maximo))
    ultima = max((v for v in repo.ultima_operacion(nombres).values() if v), default=None)
    return {"desde": desde, "hasta": maximo,
            "kpis": metricas.kpis_desde_totales(diario) if not diario.empty else None,
            "ultima_operacion": ultima}


def perfil_vs_real(engine: Engine, cliente_id: int, meses: int = 6) -> dict:
    """Mes a mes: lo que transó frente a lo que declaró (desviación = real / declarado)."""
    ficha = obtener(engine, cliente_id)
    if ficha is None:
        raise LookupError("El cliente no existe.")
    nombres = [e["nombre"] for e in ficha["empresas"]]
    repo = CarteraRepo(engine)
    _, maximo, _ = repo.opciones(nombres)
    declarado = {"volumen_mensual": ficha["perfil_volumen_mensual"], "operaciones_mes": ficha["perfil_operaciones_mes"],
                 "ticket_promedio": ficha["perfil_ticket_promedio"], "paises": ficha["perfil_paises"],
                 "actualizado": ficha["perfil_actualizado"]}
    if not maximo:
        return {"declarado": declarado, "meses": []}
    inicio = (maximo.replace(day=1) - pd.DateOffset(months=meses - 1)).date()
    diario = repo.diario(nombres, FiltrosTransacciones(desde=inicio, hasta=maximo))
    salida = []
    if not diario.empty:
        diario = diario.assign(mes=pd.to_datetime(diario["fecha"]).dt.to_period("M").dt.to_timestamp())
        for mes, g in diario.groupby("mes"):
            k = metricas.kpis_desde_totales(g)
            fila = {"periodo": mes.date(), "monto_pagado": k.monto_pagado, "operaciones": k.pagos_exitosos,
                    "ticket_promedio": k.ticket_promedio}
            fila["desv_volumen"] = (k.monto_pagado / declarado["volumen_mensual"]) if declarado["volumen_mensual"] else None
            fila["desv_operaciones"] = (k.pagos_exitosos / declarado["operaciones_mes"]) if declarado["operaciones_mes"] else None
            fila["desv_ticket"] = (k.ticket_promedio / declarado["ticket_promedio"]) if declarado["ticket_promedio"] else None
            salida.append(fila)
    return {"declarado": declarado, "meses": salida}
