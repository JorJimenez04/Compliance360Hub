"""
Verificación de completitud de las transacciones de una empresa.

El reporte de AdamoPay trae dos controles que permiten saber si falta algo:

1. Numeración consecutiva: la columna «No.» va de 1 al total de movimientos de
   la cuenta. Un número ausente es un movimiento que no llegó.
2. Saldo corrido: el saldo de cada movimiento es el saldo anterior más su
   monto total. Si no cuadra, falta un movimiento entre los dos o uno trae
   un valor errado.

Se aplica sobre todo lo guardado de la empresa (no solo el último archivo),
así detecta huecos entre un exporte y el siguiente. Una transacción que falta
no genera alerta: por eso esta verificación es parte de la confiabilidad del
monitoreo. Sin base de datos ni Streamlit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

TOLERANCIA_SALDO = 0.5   # pesos: el reporte trae valores enteros
MAX_EJEMPLOS = 10


@dataclass
class Continuidad:
    movimientos: int = 0
    no_inicial: int | None = None
    no_final: int | None = None
    faltantes: int = 0
    ejemplos_faltantes: list[str] = field(default_factory=list)   # rangos «120–125» o «340»
    descuadres_saldo: int = 0
    ejemplos_descuadre: list[int] = field(default_factory=list)   # No. donde no cuadra
    saldos_verificados: int = 0

    @property
    def completa(self) -> bool:
        return self.faltantes == 0 and self.descuadres_saldo == 0

    @property
    def parcial(self) -> bool:
        """La numeración no empieza en 1: el historial guardado no viene desde el inicio."""
        return self.no_inicial is not None and self.no_inicial > 1

    def resumen(self) -> str:
        if self.movimientos == 0:
            return "Sin movimientos"
        partes = []
        if self.faltantes:
            partes.append(f"{self.faltantes} número(s) faltante(s) ({', '.join(self.ejemplos_faltantes[:3])}…)"
                          if len(self.ejemplos_faltantes) > 3 else
                          f"{self.faltantes} número(s) faltante(s) ({', '.join(self.ejemplos_faltantes)})")
        if self.descuadres_saldo:
            ej = ", ".join(str(n) for n in self.ejemplos_descuadre[:3])
            partes.append(f"saldo no cuadra en {self.descuadres_saldo} movimiento(s) (No. {ej}…)")
        if not partes:
            texto = f"Completa: No. {self.no_inicial} a {self.no_final} sin huecos y saldos cuadrados"
        else:
            texto = "; ".join(partes)
        if self.parcial:
            texto += f" · el historial empieza en el No. {self.no_inicial}, no en 1"
        return texto

    def to_dict(self) -> dict:
        d = asdict(self)
        d["completa"] = self.completa
        d["parcial"] = self.parcial
        return d


def _rangos(numeros: list[int]) -> list[str]:
    """[3,4,5,9] -> ['3–5', '9']"""
    rangos, inicio, previo = [], None, None
    for n in numeros:
        if inicio is None:
            inicio = previo = n
        elif n == previo + 1:
            previo = n
        else:
            rangos.append(f"{inicio}–{previo}" if previo != inicio else str(inicio))
            inicio = previo = n
    if inicio is not None:
        rangos.append(f"{inicio}–{previo}" if previo != inicio else str(inicio))
    return rangos


def verificar_continuidad(df: pd.DataFrame) -> Continuidad:
    """
    df con columnas no_registro, saldo y monto_total (las demás se ignoran).
    Si un mismo No. aparece con varios ID (movimientos entre bolsillos), el
    saldo corrido no es verificable en ese punto y se omite.
    """
    r = Continuidad(movimientos=len(df))
    if df.empty:
        return r

    nos = pd.to_numeric(df["no_registro"], errors="coerce").dropna().astype(int)
    r.no_inicial, r.no_final = int(nos.min()), int(nos.max())
    presentes = set(nos)
    faltan = [n for n in range(r.no_inicial, r.no_final + 1) if n not in presentes]
    r.faltantes = len(faltan)
    r.ejemplos_faltantes = _rangos(faltan)[:MAX_EJEMPLOS]

    d = df[["no_registro", "saldo", "monto_total"]].copy()
    d["no_registro"] = pd.to_numeric(d["no_registro"], errors="coerce")
    d = d.dropna(subset=["no_registro"]).sort_values("no_registro", kind="stable")
    repetidos = d["no_registro"].duplicated(keep=False)
    previo = d["no_registro"].shift()
    # Solo se compara un movimiento con el inmediatamente anterior en numeración
    comparables = (
        ~repetidos & ~repetidos.shift(fill_value=False)
        & (d["no_registro"] - previo == 1)
        & d["saldo"].notna() & d["saldo"].shift().notna() & d["monto_total"].notna()
    )
    esperado = d["saldo"].shift() + d["monto_total"]
    descuadre = comparables & ((d["saldo"] - esperado).abs() > TOLERANCIA_SALDO)
    r.saldos_verificados = int(comparables.sum())
    r.descuadres_saldo = int(descuadre.sum())
    r.ejemplos_descuadre = [int(n) for n in d.loc[descuadre, "no_registro"].head(MAX_EJEMPLOS)]
    return r
