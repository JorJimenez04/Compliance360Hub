"""
Beneficiarios de un cliente: las personas y empresas a las que les paga, tomadas de sus transacciones.

Un beneficiario se identifica por su número de identificación (id_beneficiario). Para cada uno
se calculan sus pagos, montos, fechas, bancos y cuentas, y unas señales de revisión:

  - varios_nombres      el mismo documento aparece con nombres distintos
  - varias_cuentas      recibe en más de MAX_CUENTAS cuentas
  - cuenta_compartida   alguna de sus cuentas también la usa otro beneficiario del cliente
  - concentracion       recibe más del UMBRAL_CONCENTRACION del monto pagado por el cliente
  - rechazos            MIN_RECHAZOS o más pagos rechazados

Uso interno del equipo de cumplimiento (la API restringe el acceso).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import Engine, text

from core.monitoreo_tx.domain import metricas
from core.monitoreo_tx.domain.entidades import FiltrosTransacciones
from core.monitoreo_tx.repositorio import TransaccionesRepo

MAX_CUENTAS = 2
UMBRAL_CONCENTRACION = 0.20
MIN_RECHAZOS = 3

SENALES = {
    "varios_nombres": "El mismo documento aparece con nombres distintos",
    "varias_cuentas": f"Recibe en más de {MAX_CUENTAS} cuentas",
    "cuenta_compartida": "Una de sus cuentas la usa otro beneficiario",
    "concentracion": f"Recibe más del {UMBRAL_CONCENTRACION:.0%} de lo pagado por el cliente",
    "rechazos": f"{MIN_RECHAZOS} o más pagos rechazados",
}


def _empresas(engine: Engine, cliente_id: int) -> list[str]:
    with engine.connect() as conn:
        return list(conn.scalars(text("SELECT nombre_reporte FROM tx_empresas WHERE cliente_id = :c ORDER BY 1"),
                                 {"c": cliente_id}))


def _movimientos(engine: Engine, cliente_id: int, desde: date | None, hasta: date | None, texto: str = "") -> pd.DataFrame:
    repo = TransaccionesRepo(engine)
    filtros = FiltrosTransacciones(desde=desde, hasta=hasta, texto=texto)
    partes = [repo.consultar(n, filtros).assign(empresa=n) for n in _empresas(engine, cliente_id)]
    partes = [p for p in partes if not p.empty]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def enmascarar(cuenta) -> str | None:
    s = str(cuenta or "").strip()
    return None if not s else ("•••• " + s[-4:]) if len(s) > 4 else s


def _moda(s: pd.Series):
    s = s.dropna()
    return s.mode().iat[0] if not s.empty else None


def listar(engine: Engine, cliente_id: int, desde: date | None = None, hasta: date | None = None) -> dict:
    df = _movimientos(engine, cliente_id, desde, hasta)
    vacio = {"total_beneficiarios": 0, "monto_total": 0.0, "pagos_total": 0, "desde": desde, "hasta": hasta,
             "senales": SENALES, "beneficiarios": []}
    if df.empty:
        return vacio
    df = df[df["id_beneficiario"].notna() & (df["id_beneficiario"].astype(str).str.strip() != "")].copy()
    df["id_beneficiario"] = df["id_beneficiario"].astype(str).str.strip()
    mov = metricas.movimientos(df["tipo_transaccion"])
    pagos = df[(mov == metricas.PAGO)]
    if pagos.empty:
        return vacio
    ok = pagos[pagos["exitosa"]]
    monto_total = float(ok["monto"].sum())

    cuentas = pagos.dropna(subset=["numero_cuenta"]).assign(numero_cuenta=lambda x: x["numero_cuenta"].astype(str).str.strip())
    cuentas = cuentas[cuentas["numero_cuenta"] != ""]
    compartidas = set(cuentas.groupby("numero_cuenta")["id_beneficiario"].nunique().loc[lambda s: s > 1].index)

    filas = []
    for idb, g in pagos.groupby("id_beneficiario"):
        gok = g[g["exitosa"]]
        sus_cuentas = sorted(set(cuentas.loc[cuentas["id_beneficiario"] == idb, "numero_cuenta"]))
        monto = float(gok["monto"].sum())
        nombres = sorted({str(n).strip() for n in g["beneficiario"].dropna() if str(n).strip()})
        rechazos = int((~g["exitosa"]).sum())
        senales = [k for k, cumple in (
            ("varios_nombres", len({n.upper() for n in nombres}) > 1),
            ("varias_cuentas", len(sus_cuentas) > MAX_CUENTAS),
            ("cuenta_compartida", bool(compartidas.intersection(sus_cuentas))),
            ("concentracion", monto_total > 0 and monto / monto_total > UMBRAL_CONCENTRACION),
            ("rechazos", rechazos >= MIN_RECHAZOS),
        ) if cumple]
        filas.append({
            "id_beneficiario": idb,
            "nombre": _moda(g["beneficiario"]),
            "otros_nombres": [n for n in nombres if n != _moda(g["beneficiario"])],
            "tipo_identificacion": _moda(g["tipo_identificacion"]),
            "tipo_persona": _moda(g["tipo_persona"]),
            "pagos": int(len(gok)), "rechazos": rechazos, "monto": monto,
            "participacion": monto / monto_total if monto_total else 0.0,
            "ticket_promedio": monto / len(gok) if len(gok) else 0.0,
            "primer_pago": gok["fecha"].min().date() if not gok.empty else None,
            "ultimo_pago": gok["fecha"].max().date() if not gok.empty else None,
            "bancos": sorted({str(b) for b in g["banco"].dropna()}),
            "cuentas": [enmascarar(c) for c in sus_cuentas],
            "empresas": sorted(set(g["empresa"])),
            "senales": senales,
        })
    filas.sort(key=lambda f: (-f["monto"], -f["pagos"]))
    return {"total_beneficiarios": len(filas), "monto_total": monto_total, "pagos_total": int(len(ok)),
            "desde": df["fecha"].min().date(), "hasta": df["fecha"].max().date(), "senales": SENALES,
            "beneficiarios": filas}


def movimientos_de(engine: Engine, cliente_id: int, id_beneficiario: str, limite: int = 200) -> list[dict]:
    """Movimientos de un beneficiario con el cliente (los más recientes primero)."""
    df = _movimientos(engine, cliente_id, None, None, texto=id_beneficiario)
    if df.empty:
        return []
    df = df[df["id_beneficiario"].astype(str).str.strip() == id_beneficiario.strip()]
    df = df.sort_values("fecha_hora", ascending=False).head(limite)
    return [{"fecha_hora": r.fecha_hora, "empresa": r.empresa, "id_transaccion": r.id_transaccion,
             "tipo_transaccion": r.tipo_transaccion, "estado": r.estado, "exitosa": bool(r.exitosa),
             "monto": float(r.monto), "banco": r.banco, "cuenta": enmascarar(r.numero_cuenta),
             "nombre": r.beneficiario} for r in df.itertuples()]
