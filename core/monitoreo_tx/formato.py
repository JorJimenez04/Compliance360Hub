"""
Formato de números y textos para la interfaz (convención colombiana).
"""

from __future__ import annotations

import re
from datetime import date, datetime


# Espacio de no separación: «$ 42,3 M» nunca se parte entre dos líneas
_ESPACIO_FIJO = "\u00a0"


def formato_cop(valor: float, compacto: bool = False) -> str:
    """Pesos colombianos:  $ 1.234.567  ·  compacto: $ 42,3 M  /  $ 20.383 M  (M = millones).

    El compacto siempre se expresa en millones: «$ 20.383 M» se lee de inmediato,
    mientras que «$ 20,4 mil M» obliga a traducir. Solo desde el billón (un millón
    de millones) se cambia de unidad."""
    if compacto:
        magnitud = abs(valor)
        if magnitud >= 1e12:
            texto = f"$ {valor / 1e12:,.2f} billones"
        elif magnitud >= 1e9:
            texto = f"$ {valor / 1e6:,.0f} M"
        elif magnitud >= 1e6:
            texto = f"$ {valor / 1e6:,.1f} M"
        else:
            texto = None
        if texto:
            return texto.replace(",", "X").replace(".", ",").replace("X", ".").replace(" ", _ESPACIO_FIJO)
    return f"${_ESPACIO_FIJO}{valor:,.0f}".replace(",", ".")


def formato_entero(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def formato_porcentaje(valor: float) -> str:
    return f"{valor:.1%}".replace(".", ",")


def formato_fecha_hora(valor: datetime | None) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if valor else "—"


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_larga(valor: date) -> str:
    """12 de agosto de 2025"""
    return f"{valor.day} de {MESES[valor.month - 1]} de {valor.year}"


def fecha_corta(valor: date) -> str:
    """12 ago 2025"""
    return f"{valor.day} {MESES[valor.month - 1][:3]} {valor.year}"


def etiqueta_periodo(valor: date, granularidad: str) -> str:
    if granularidad == "Mensual":
        return f"{MESES[valor.month - 1].capitalize()} {valor.year}"
    if granularidad == "Semanal":
        return f"Semana del {fecha_corta(valor)}"
    return fecha_corta(valor)


def formato_variacion(valor: float | None, puntos: bool = False) -> str | None:
    """+12,3 % · -0,4 pp · None si no hay comparación.

    Usa el guion ASCII: st.metric decide la flecha y el color leyendo el signo,
    y no reconoce el signo menos tipográfico (−) como negativo."""
    if valor is None:
        return None
    if puntos:
        return f"{valor * 100:+.1f} pp".replace(".", ",")
    return f"{valor:+.1%}".replace(".", ",")


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")


def enmascarar(valor, visibles: int = 4) -> str | None:
    """Oculta un dato sensible dejando solo el final: '12345678901' -> '•••••••8901'.

    Para números de cuenta y documentos en pantalla. Un valor tan corto que
    mostrar el final lo revelaría casi entero se oculta por completo."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if len(texto) <= visibles + 2:
        return "•" * len(texto)
    return "•" * (len(texto) - visibles) + texto[-visibles:]
