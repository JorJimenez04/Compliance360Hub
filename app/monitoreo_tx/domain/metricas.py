"""
Cálculos puros (sin BD ni Streamlit) para indicadores, gráficos y exportes.

Tipos de movimiento en el reporte de AdamoPay:
- Débito                           -> PAGO a un beneficiario (Pagado/Validado = exitoso)
- Crédito (estado Retornado)       -> DEVOLUCIÓN de un pago que el banco destino rechazó
- Fondeo (estado Aprobado)         -> FONDEO: recarga de saldo de la empresa
- Transferencia entre bolsillos    -> INTERNO: movimiento entre cuentas de la empresa

Los indicadores de pagos (tasa de éxito, ticket) se calculan solo sobre los
débitos: un fondeo o una transferencia interna no es un pago fallido.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

PAGO, DEVOLUCION, FONDEO, INTERNO, OTRO = "pago", "devolucion", "fondeo", "interno", "otro"


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def tipo_movimiento(tipo_transaccion) -> str:
    t = _sin_tildes(tipo_transaccion) if isinstance(tipo_transaccion, str) else ""
    if t.startswith("debito"):
        return PAGO
    if t.startswith("credito"):
        return DEVOLUCION
    if t.startswith("fondeo"):
        return FONDEO
    if "bolsillo" in t:
        return INTERNO
    return OTRO


def movimientos(tipos: pd.Series) -> pd.Series:
    """tipo_movimiento vectorizado: se evalúa una vez por valor distinto."""
    return tipos.map({t: tipo_movimiento(t) for t in tipos.unique()})


# =========================
# Indicadores
# =========================
@dataclass(frozen=True)
class KPIs:
    pagos_enviados: int        # débitos, en cualquier estado
    pagos_exitosos: int        # débitos Pagado / Validado
    monto_pagado: float        # suma de los pagos exitosos
    ticket_promedio: float     # monto pagado / pagos exitosos
    # Un pago «Pagado» puede volver después como devolución: la tasa las descuenta.
    # (pagos exitosos − devoluciones) / pagos enviados, entre 0 y 1
    tasa_exito: float
    devoluciones: int
    monto_devuelto: float
    fondeos: int
    monto_fondeado: float
    total_movimientos: int

    @property
    def tasa_devolucion(self) -> float:
        return self.devoluciones / self.pagos_exitosos if self.pagos_exitosos else 0.0


def totalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Conteo y monto por (tipo de movimiento, exitosa). Misma forma que el agregado SQL."""
    if df.empty:
        return pd.DataFrame(columns=["tipo_transaccion", "exitosa", "transacciones", "monto"])
    return (
        df.groupby(["tipo_transaccion", "exitosa"], dropna=False)["monto"]
        .agg(transacciones="count", monto="sum")
        .reset_index()
    )


def kpis_desde_totales(totales: pd.DataFrame) -> KPIs:
    t = totales.assign(mov=totales["tipo_transaccion"].map(tipo_movimiento))
    exitosa = t["exitosa"].fillna(False).astype(bool)

    def suma(mask, col):
        return t.loc[mask, col].sum()

    pagos = t["mov"] == PAGO
    enviados = int(suma(pagos, "transacciones"))
    exitosos = int(suma(pagos & exitosa, "transacciones"))
    monto = float(suma(pagos & exitosa, "monto"))
    devoluciones = int(suma(t["mov"] == DEVOLUCION, "transacciones"))
    efectivos = max(exitosos - devoluciones, 0)
    return KPIs(
        pagos_enviados=enviados,
        pagos_exitosos=exitosos,
        monto_pagado=monto,
        ticket_promedio=monto / exitosos if exitosos else 0.0,
        tasa_exito=min(efectivos / enviados, 1.0) if enviados else 0.0,
        devoluciones=devoluciones,
        monto_devuelto=float(suma(t["mov"] == DEVOLUCION, "monto")),
        fondeos=int(suma(t["mov"] == FONDEO, "transacciones")),
        monto_fondeado=float(suma(t["mov"] == FONDEO, "monto")),
        total_movimientos=int(t["transacciones"].sum()),
    )


def calcular_kpis(df: pd.DataFrame) -> KPIs:
    return kpis_desde_totales(totalizar(df))


def variacion(actual: float, anterior: float | None) -> float | None:
    """Cambio relativo; None si no hay base de comparación."""
    if not anterior:
        return None
    return (actual - anterior) / anterior


def periodo_anterior(desde: date, hasta: date) -> tuple[date, date]:
    """Período de igual duración inmediatamente anterior."""
    dias = (hasta - desde).days + 1
    fin = desde - timedelta(days=1)
    return fin - timedelta(days=dias - 1), fin


# =========================
# Series y distribuciones
# =========================
FRECUENCIAS = {"Diaria": "D", "Semanal": "W-MON", "Mensual": "MS"}


def granularidad_sugerida(desde: date, hasta: date) -> str:
    dias = (hasta - desde).days + 1
    if dias <= 62:
        return "Diaria"
    return "Semanal" if dias <= 370 else "Mensual"


def _pagos_exitosos(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["exitosa"] & (movimientos(df["tipo_transaccion"]) == PAGO)]


def pagos_exitosos(df: pd.DataFrame) -> pd.DataFrame:
    return _pagos_exitosos(df)


def devoluciones(df: pd.DataFrame) -> pd.DataFrame:
    return df[movimientos(df["tipo_transaccion"]) == DEVOLUCION]


def serie_pagos(df: pd.DataFrame, granularidad: str = "Diaria") -> pd.DataFrame:
    """Monto y número de pagos exitosos por período (incluye períodos sin pagos)."""
    ok = _pagos_exitosos(df)[["fecha", "monto"]]
    if ok.empty:
        return pd.DataFrame(columns=["periodo", "monto", "pagos"])
    return (
        ok.set_index("fecha")["monto"]
        .resample(FRECUENCIAS[granularidad], label="left", closed="left")
        .agg(["sum", "count"])
        .rename(columns={"sum": "monto", "count": "pagos"})
        .reset_index(names="periodo")
    )


CATEGORIAS_MOVIMIENTO = [
    # (clave, etiqueta para el cliente)
    ("pago_ok", "Pagos exitosos"),
    ("pago_sin_estado", "Pagos sin estado confirmado"),
    ("pago_rechazado", "Pagos rechazados"),
    ("devolucion", "Devoluciones"),
    ("fondeo", "Fondeos (recargas)"),
    ("interno", "Transferencias internas"),
    ("otro", "Otros movimientos"),
]


def composicion_movimientos(df: pd.DataFrame) -> pd.DataFrame:
    """Movimientos agrupados en categorías comprensibles, con conteo, monto y participación."""
    if df.empty:
        return pd.DataFrame(columns=["clave", "categoria", "movimientos", "monto", "pct"])
    mov = movimientos(df["tipo_transaccion"])
    sin_estado = df["estado"].fillna("").str.lower().str.strip() == "sin estado"
    clave = mov.map({DEVOLUCION: "devolucion", FONDEO: "fondeo", INTERNO: "interno"}).fillna("otro")
    clave = clave.mask(mov == PAGO, "pago_rechazado")
    clave = clave.mask((mov == PAGO) & sin_estado, "pago_sin_estado")
    clave = clave.mask((mov == PAGO) & df["exitosa"], "pago_ok")
    g = df.assign(clave=clave).groupby("clave")["monto"].agg(movimientos="count", monto="sum")
    etiquetas = dict(CATEGORIAS_MOVIMIENTO)
    orden = [c for c, _ in CATEGORIAS_MOVIMIENTO if c in g.index]
    g = g.loc[orden].reset_index()
    g["categoria"] = g["clave"].map(etiquetas)
    g["pct"] = g["movimientos"] / g["movimientos"].sum()
    return g[["clave", "categoria", "movimientos", "monto", "pct"]]


RANGOS_MONTO = [
    (0, 100_000, "Hasta $100 mil"),
    (100_000, 500_000, "$100 mil – $500 mil"),
    (500_000, 1_000_000, "$500 mil – $1 M"),
    (1_000_000, 5_000_000, "$1 M – $5 M"),
    (5_000_000, 20_000_000, "$5 M – $20 M"),
    (20_000_000, float("inf"), "Más de $20 M"),
]


def distribucion_montos(df: pd.DataFrame) -> pd.DataFrame:
    """Pagos exitosos por rango de monto, en orden de menor a mayor."""
    ok = _pagos_exitosos(df)
    bordes = [r[0] for r in RANGOS_MONTO] + [float("inf")]
    etiquetas = [r[2] for r in RANGOS_MONTO]
    rango = pd.cut(ok["monto"], bins=bordes, labels=etiquetas, right=False, include_lowest=True)
    d = ok.assign(rango=rango).groupby("rango", observed=False)["monto"].agg(pagos="count", monto="sum")
    d = d.reset_index()
    total = d["pagos"].sum()
    d["pct"] = d["pagos"] / total if total else 0.0
    d["rango"] = d["rango"].astype(str)
    return d


def top_bancos(df: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    """Bancos de destino de los pagos exitosos por monto; el resto se agrupa en «Otros bancos»."""
    ok = _pagos_exitosos(df).dropna(subset=["banco"])
    if ok.empty:
        return pd.DataFrame(columns=["banco", "pagos", "monto", "pct"])
    # «BANCOLOMBIA» y «Bancolombia», o «Bre-B» y «BreB», son el mismo banco:
    # se agrupa sin distinguir mayúsculas, tildes, espacios ni guiones
    clave = ok["banco"].map(lambda b: re.sub(r"[^a-z0-9]", "", _sin_tildes(str(b))))
    nombres = ok.groupby(clave)["banco"].agg(lambda s: s.mode().iat[0])
    g = ok.groupby(clave)["monto"].agg(pagos="count", monto="sum").sort_values("monto", ascending=False)
    g.index = nombres.loc[g.index].values
    if len(g) > n:
        resto = g.iloc[n:].sum()
        g = pd.concat([g.iloc[:n], pd.DataFrame([resto], index=["Otros bancos"])])
    g = g.reset_index(names="banco")
    g["pct"] = g["monto"] / g["monto"].sum()
    return g


def top_beneficiarios(df: pd.DataFrame, n: int = 10, por: str = "monto") -> pd.DataFrame:
    """Ranking de los clientes (beneficiarios) con más pagos exitosos.

    `por`: "monto" o "pagos". Se agrupa por documento; el nombre es el más frecuente
    para ese documento. `pct` es la participación sobre el total de la medida elegida."""
    columnas = ["posicion", "beneficiario", "id_beneficiario", "pagos", "monto", "pct", "ultimo_pago"]
    ok = _pagos_exitosos(df).dropna(subset=["id_beneficiario"])
    if ok.empty:
        return pd.DataFrame(columns=columnas)
    g = ok.groupby("id_beneficiario").agg(
        beneficiario=("beneficiario", lambda s: s.mode().iat[0] if s.notna().any() else None),
        pagos=("monto", "count"), monto=("monto", "sum"), ultimo_pago=("fecha_hora", "max"),
    )
    medida = "pagos" if por == "pagos" else "monto"
    otra = "monto" if medida == "pagos" else "pagos"
    g["pct"] = g[medida] / g[medida].sum()
    g = g.sort_values([medida, otra], ascending=False).head(n).reset_index()
    g["posicion"] = range(1, len(g) + 1)
    return g[columnas]


DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def actividad_semana_hora(df: pd.DataFrame) -> pd.DataFrame:
    """Pagos exitosos por día de la semana (filas) y hora del día (columnas 0-23)."""
    ok = _pagos_exitosos(df).dropna(subset=["fecha_hora"])
    tabla = pd.crosstab(ok["fecha_hora"].dt.dayofweek, ok["fecha_hora"].dt.hour)
    tabla = tabla.reindex(index=range(7), columns=range(24), fill_value=0)
    tabla.index = DIAS_SEMANA
    return tabla


# Motivos de devolución agrupados en causas que el cliente puede corregir
_MOTIVOS = [
    ("Cuenta y documento no coinciden",
     r"IDENTIFICATION|NO CORRESPONDEN|ID NOT VALID|INVALID ID|NIT ERRADO|DOCUMENTO|"
     r"DO NOT MATCH|NO COINCIDE"),
    ("La cuenta no existe o el número es inválido",
     r"DOES ?N.?T EXIST|DOESNT EXIST|NO EXISTE|INVALID ACCOUNT NUMBER|WRONG.BANK.ACCOUNT"),
    ("Cuenta inactiva, bloqueada o no autorizada",
     r"INACTIVE|BLOCKED|NOT.AUTHORIZED|NO AUTORIZADA|BLOQUEAD|INACTIV"),
    ("Supera el límite permitido por el banco", r"EXCEED|LIMIT|MAXIM"),
    ("Tipo de cuenta incorrecto", r"ACCOUNT TYPE|TIPO DE CUENTA"),
    ("Datos del pago incorrectos", r"WRONG.DATA|DATOS"),
    ("Fondos insuficientes", r"\bNSF\b|INSUFFICIENT|FONDOS"),
    ("Falla técnica o demora del banco",
     r"TIMEOUT|TECNICO|TÉCNICO|DEMORA|PROCESSING FAILED|COULD NOT PROCESS|TRY AGAIN"),
    ("Rechazada por el banco", r"REJECTED|RECHAZ"),
]

# Textos que no explican la causa: «PAGADO - <origen>», «TRUE», «TRANSACTION RETURNED»…
_SIN_MOTIVO = re.compile(r"^\s*-?\s*(PAGADO|TRUE|TRANSACTION RETURNED|COMUNICATE)\b|^\s*-\s*\S+\s*$")


def motivo_devolucion(descripcion) -> str:
    if not isinstance(descripcion, str) or not descripcion.strip():
        return "Motivo no informado"
    texto = descripcion.upper()
    for etiqueta, patron in _MOTIVOS:
        if re.search(patron, texto):
            return etiqueta
    return "Motivo no informado" if _SIN_MOTIVO.match(texto) else "Otros motivos"


def motivos_devolucion(df: pd.DataFrame) -> pd.DataFrame:
    dev = devoluciones(df)
    if dev.empty:
        return pd.DataFrame(columns=["motivo", "devoluciones", "monto", "pct"])
    g = (
        dev.assign(motivo=dev["descripcion"].map(motivo_devolucion))
        .groupby("motivo")["monto"].agg(devoluciones="count", monto="sum")
        .sort_values("devoluciones", ascending=False).reset_index()
    )
    g["pct"] = g["devoluciones"] / g["devoluciones"].sum()
    return g


def dia_pico(df: pd.DataFrame) -> tuple[date, float] | None:
    ok = _pagos_exitosos(df)
    if ok.empty:
        return None
    por_dia = ok.groupby(ok["fecha"].dt.date)["monto"].sum()
    return por_dia.idxmax(), float(por_dia.max())


# =========================
# Tabla y exportes
# =========================
ETIQUETAS_EXPORTE = {
    "fecha_hora": "Fecha y hora",
    "id_transaccion": "ID transacción",
    "referencia_externa": "Referencia externa",
    "tipo_transaccion": "Tipo de transacción",
    "beneficiario": "Beneficiario",
    "tipo_identificacion": "Tipo identificación",
    "id_beneficiario": "Documento beneficiario",
    "banco": "Banco",
    "tipo_cuenta": "Tipo de cuenta",
    "numero_cuenta": "Número de cuenta",
    "monto": "Monto (COP)",
    "comision": "Comisión (COP)",
    "monto_total": "Monto total (COP)",
    "estado": "Estado",
    "saldo": "Saldo (COP)",
    "descripcion": "Descripción",
}


NOMBRES_MOVIMIENTO = {PAGO: "Pago", DEVOLUCION: "Devolución", FONDEO: "Fondeo",
                      INTERNO: "Transferencia interna", OTRO: "Otro"}


def tabla_para_exporte(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas legibles para la tabla y el CSV (sin columnas internas)."""
    cols = [c for c in ETIQUETAS_EXPORTE if c in df.columns]
    salida = df[cols].rename(columns=ETIQUETAS_EXPORTE)
    # «Débito/Crédito» es jerga contable: se agrega el tipo de movimiento en lenguaje simple
    salida.insert(1, "Movimiento", movimientos(df["tipo_transaccion"]).map(NOMBRES_MOVIMIENTO).values)
    if not salida["Referencia externa"].notna().any():
        salida = salida.drop(columns="Referencia externa")
    return salida


def a_csv(df: pd.DataFrame) -> bytes:
    # utf-8-sig: Excel abre bien las tildes y la ñ
    return df.to_csv(index=False, date_format="%Y-%m-%d %H:%M:%S").encode("utf-8-sig")


def a_formato_legacy(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas con los nombres que esperan src/characterization y src/risk_analysis."""
    return pd.DataFrame({
        "FECHA": df["fecha_hora"].fillna(df["fecha"]),
        "MONTO (COP)": df["monto"],
        "ESTADO": df["estado"],
        "TIPO DE TRA": df["tipo_transaccion"],
        "TIPO_PERSONA": df["tipo_persona"],
        "BENEFICIARIO": df["beneficiario"],
        "BANCO": df["banco"],
    })
