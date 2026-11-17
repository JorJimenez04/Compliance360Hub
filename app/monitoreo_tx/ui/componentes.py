"""
Piezas de interfaz del módulo.

Todo valor que venga de los datos (beneficiarios, descripciones) pasa por
`html.escape` antes de pintarse: el reporte es una fuente externa y un texto
con etiquetas HTML no debe ejecutarse en el navegador.
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app.monitoreo_tx.domain.errores import ErrorDominio, ErrorValidacion

_CSS = """
<style>
.tx-campo{display:flex;flex-direction:column;gap:2px;margin-bottom:10px}
.tx-etiqueta{font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.04em}
.tx-valor{font-size:14px;color:#f9fafb;word-break:break-word}
</style>
"""


def _texto_seguro(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or str(valor).strip() == "":
        return "—"
    # &#36; evita que dos signos $ en una misma línea se interpreten como fórmula
    return html.escape(str(valor)).replace("$", "&#36;")


def ficha(campos: list[tuple[str, object]], columnas: int = 2) -> None:
    """Pares etiqueta/valor en una rejilla, fila por fila para que queden alineados."""
    st.markdown(_CSS, unsafe_allow_html=True)
    for i in range(0, len(campos), columnas):
        for columna, (etiqueta, valor) in zip(st.columns(columnas), campos[i:i + columnas]):
            columna.markdown(
                f"<div class='tx-campo'><span class='tx-etiqueta'>{html.escape(etiqueta)}</span>"
                f"<span class='tx-valor'>{_texto_seguro(valor)}</span></div>",
                unsafe_allow_html=True,
            )


def mostrar_error(error: ErrorDominio) -> None:
    if isinstance(error, ErrorValidacion) and len(error.errores) > 1:
        st.error("\n".join(f"- {e}" for e in error.errores))
    else:
        st.error(str(error))
