"""
Figuras Plotly del portal, pensadas para lectores no técnicos:
- Una idea por gráfico y un solo eje Y (nunca doble eje).
- Cada barra lleva su valor escrito; el color nunca es la única pista.
- Colores de estado reservados (verde = exitoso, naranja = devuelto, rojo = rechazado)
  y siempre acompañados de su nombre en el eje.
- Escala secuencial de un solo azul para intensidades (mapa de actividad).
- Formato colombiano (1.234.567,8) y tooltips en español.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from app.monitoreo_tx.ui.formato import MESES, etiqueta_periodo, formato_cop, formato_entero, formato_porcentaje

# Paleta para el tema oscuro de Compliance360 Hub (.streamlit/config.toml)
AZUL = "#5fe9d0"
AZUL_SUAVE = "#2a8f80"
AZUL_RELLENO = "rgba(95, 233, 208, 0.14)"
NEUTRO = "#6b7280"
TINTA = "#f9fafb"
TINTA_SUAVE = "#9ca3af"
GRILLA = "rgba(255, 255, 255, 0.08)"

# Estados (paleta de estado, distinta de la de series) y neutros para lo que no es un pago
COLORES_CATEGORIA = {
    "pago_ok": "#22c55e",
    "pago_sin_estado": "#fab219",
    "pago_rechazado": "#ef4444",
    "devolucion": "#ec835a",
    "fondeo": "#8B9BB0",
    "interno": "#6b7280",
    "otro": "#4b5563",
}
ESCALA_AZUL = [
    [0.0, "#1e2433"], [0.12, "#164e4a"], [0.3, "#1f6f66"], [0.5, "#2a8f80"],
    [0.68, "#3bb3a0"], [0.84, "#4fd1bb"], [1.0, "#5fe9d0"],
]

CONFIG = {"displayModeBar": False}


def _base(fig: go.Figure, alto: int = 340) -> go.Figure:
    fig.update_layout(
        height=alto,
        margin=dict(l=4, r=12, t=8, b=4),
        separators=",.",
        showlegend=False,
        hoverlabel=dict(font_size=14, bgcolor="#1e2433", bordercolor="#293056", font_color=TINTA),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TINTA_SUAVE, size=13),
        bargap=0.28,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRILLA)
    fig.update_yaxes(gridcolor=GRILLA, zeroline=False)
    return fig


def _ticks_cop(maximo: float, n: int = 4) -> tuple[list[float], list[str]]:
    """Marcas «redondas» del eje en pesos con texto legible ($ 2 mil M, $ 500 M…), no «2G»."""
    if maximo <= 0:
        return [0], ["$ 0"]
    bruto = maximo / n
    magnitud = 10 ** math.floor(math.log10(bruto))
    paso = next(m * magnitud for m in (1, 2, 2.5, 5, 10) if m * magnitud >= bruto)
    valores = [i * paso for i in range(int(maximo // paso) + 2)]
    return valores, [formato_cop(v, compacto=True) if v else "$ 0" for v in valores]


def _barras_horizontales(etiquetas, valores, textos, colores, hover, alto_fila: int = 46,
                         holgura: float = 1.55) -> go.Figure:
    """holgura: cuánto se extiende el eje más allá de la barra mayor para que quepa su texto."""
    fig = go.Figure(go.Bar(
        x=valores, y=etiquetas, orientation="h",
        marker=dict(color=colores, cornerradius=4),
        text=textos, textposition="outside", cliponaxis=False,
        textfont=dict(color=TINTA, size=13),
        hovertext=hover, hoverinfo="text",
    ))
    # Espacio a la derecha de la barra más larga para que su texto no se corte
    maximo = max(valores) if len(valores) else 0
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, maximo * holgura if maximo else 1])
    fig.update_yaxes(showgrid=False, autorange="reversed", ticks="", tickfont=dict(color=TINTA, size=13))
    return _base(fig, alto=max(180, alto_fila * len(etiquetas) + 30))


# =========================
# Tendencia
# =========================
def grafico_tendencia(serie: pd.DataFrame, granularidad: str, medida: str) -> go.Figure:
    """medida: 'monto' o 'pagos'. Columnas para semanas/meses; línea para días."""
    es_monto = medida == "monto"
    hover = [
        f"<b>{etiqueta_periodo(p, granularidad)}</b><br>"
        f"Monto pagado: {formato_cop(m)}<br>Pagos exitosos: {formato_entero(int(n))}"
        for p, m, n in zip(serie["periodo"], serie["monto"], serie["pagos"])
    ]
    y = serie["monto"] if es_monto else serie["pagos"]

    if granularidad == "Diaria" and len(serie) > 45:
        traza = go.Scatter(x=serie["periodo"], y=y, mode="lines", line=dict(color=AZUL, width=2),
                           fill="tozeroy", fillcolor=AZUL_RELLENO, hovertext=hover, hoverinfo="text")
    else:
        traza = go.Bar(x=serie["periodo"], y=y, marker=dict(color=AZUL, cornerradius=4),
                       hovertext=hover, hoverinfo="text")
    fig = go.Figure(traza)
    if es_monto:
        valores, textos = _ticks_cop(float(y.max()))
        fig.update_yaxes(tickvals=valores, ticktext=textos)
    else:
        fig.update_yaxes(tickformat=",d")
    # Plotly no trae los nombres de meses en español: las marcas se escriben a mano
    periodos = list(serie["periodo"])
    paso = max(1, math.ceil(len(periodos) / 12))
    marcas = periodos[::paso]
    if granularidad == "Mensual":
        textos_x = [f"{MESES[p.month - 1][:3]} {p.year}" for p in marcas]
    else:
        textos_x = [f"{p.day} {MESES[p.month - 1][:3]}" for p in marcas]
    fig.update_xaxes(tickvals=marcas, ticktext=textos_x, tickangle=0)
    fig = _base(fig, alto=360)
    fig.update_layout(hovermode="x")
    return fig


# =========================
# Composición y montos
# =========================
def grafico_composicion(comp: pd.DataFrame, medida: str) -> go.Figure:
    """medida: 'movimientos' (cantidad) o 'monto'."""
    valores = comp[medida]
    total = valores.sum() or 1
    if medida == "monto":
        textos = [f"{formato_cop(v, compacto=True)}  ({formato_porcentaje(v / total)})" for v in valores]
    else:
        textos = [f"{formato_entero(int(v))}  ({formato_porcentaje(v / total)})" for v in valores]
    hover = [
        f"<b>{c}</b><br>Movimientos: {formato_entero(int(n))}<br>Monto: {formato_cop(m)}"
        for c, n, m in zip(comp["categoria"], comp["movimientos"], comp["monto"])
    ]
    colores = [COLORES_CATEGORIA[c] for c in comp["clave"]]
    return _barras_horizontales(comp["categoria"], valores, textos, colores, hover)


def grafico_rangos(dist: pd.DataFrame) -> go.Figure:
    hover = [
        f"<b>{r}</b><br>Pagos: {formato_entero(int(n))} ({formato_porcentaje(p)})<br>Monto: {formato_cop(m)}"
        for r, n, p, m in zip(dist["rango"], dist["pagos"], dist["pct"], dist["monto"])
    ]
    # Etiquetas en dos líneas: horizontales y legibles, sin inclinarlas
    etiquetas = [r.replace(" – ", " –<br>").replace("Hasta ", "Hasta<br>").replace("Más de ", "Más de<br>")
                 for r in dist["rango"]]
    fig = go.Figure(go.Bar(
        x=etiquetas, y=dist["pagos"],
        marker=dict(color=AZUL, cornerradius=4),
        text=[formato_porcentaje(p) for p in dist["pct"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=TINTA, size=13),
        hovertext=hover, hoverinfo="text",
    ))
    fig.update_yaxes(tickformat=",d", title=dict(text="Número de pagos", font=dict(size=12)))
    fig.update_xaxes(tickfont=dict(color=TINTA, size=12), tickangle=0)
    fig.update_yaxes(range=[0, dist["pagos"].max() * 1.15])
    return _base(fig, alto=360)


# =========================
# Destinos y horarios
# =========================
def grafico_bancos(top: pd.DataFrame) -> go.Figure:
    textos = [f"{formato_cop(m, compacto=True)}  ({formato_porcentaje(p)})" for m, p in zip(top["monto"], top["pct"])]
    hover = [
        f"<b>{b}</b><br>Monto: {formato_cop(m)}<br>Pagos: {formato_entero(int(n))}"
        for b, m, n in zip(top["banco"], top["monto"], top["pagos"])
    ]
    colores = [(NEUTRO if b == "Otros bancos" else AZUL) for b in top["banco"]]
    return _barras_horizontales(top["banco"], top["monto"], textos, colores, hover, alto_fila=40, holgura=2.0)


def grafico_ranking(top: pd.DataFrame, medida: str) -> go.Figure:
    """Ranking de clientes. medida: 'monto' o 'pagos'."""
    es_monto = medida == "monto"
    # El número de posición hace única cada etiqueta (dos clientes pueden llamarse igual)
    etiquetas = [f"{pos}. {_recortar(nombre)}" for pos, nombre in zip(top["posicion"], top["beneficiario"])]
    if es_monto:
        textos = [f"{formato_cop(m, compacto=True)}  ({formato_porcentaje(p)})" for m, p in zip(top["monto"], top["pct"])]
    else:
        textos = [f"{formato_entero(int(n))} pagos  ({formato_porcentaje(p)})" for n, p in zip(top["pagos"], top["pct"])]
    hover = [
        f"<b>{b}</b><br>Pagos: {formato_entero(int(n))}<br>Monto: {formato_cop(m)} COP"
        for b, m, n in zip(top["beneficiario"], top["monto"], top["pagos"])
    ]
    # Los tres primeros resaltados; el resto en un azul más claro
    colores = [AZUL if pos <= 3 else AZUL_SUAVE for pos in top["posicion"]]
    return _barras_horizontales(etiquetas, top["monto" if es_monto else "pagos"], textos, colores, hover,
                                alto_fila=38, holgura=1.7)


def _recortar(texto, largo: int = 30) -> str:
    texto = str(texto) if isinstance(texto, str) and texto.strip() else "Sin nombre"
    return texto if len(texto) <= largo else texto[:largo - 1].rstrip() + "…"


def grafico_actividad(tabla: pd.DataFrame) -> go.Figure:
    horas = [f"{h:02d}:00" for h in tabla.columns]
    hover = [
        [f"<b>{dia}, {h}</b><br>Pagos: {formato_entero(int(v))}" for h, v in zip(horas, fila)]
        for dia, fila in zip(tabla.index, tabla.values)
    ]
    fig = go.Figure(go.Heatmap(
        z=tabla.values, x=horas, y=list(tabla.index),
        colorscale=ESCALA_AZUL, xgap=2, ygap=2, showscale=False,
        hovertext=hover, hoverinfo="text",
    ))
    fig.update_xaxes(tickvals=horas[::3], tickfont=dict(size=12), side="bottom")
    fig.update_yaxes(autorange="reversed", tickfont=dict(color=TINTA, size=13), showgrid=False)
    return _base(fig, alto=300)


def grafico_motivos(motivos: pd.DataFrame) -> go.Figure:
    textos = [f"{formato_entero(int(n))}  ({formato_porcentaje(p)})" for n, p in zip(motivos["devoluciones"], motivos["pct"])]
    hover = [
        f"<b>{m}</b><br>Devoluciones: {formato_entero(int(n))}<br>Monto: {formato_cop(v)}"
        for m, n, v in zip(motivos["motivo"], motivos["devoluciones"], motivos["monto"])
    ]
    colores = [(NEUTRO if m in ("Motivo no informado", "Otros motivos") else COLORES_CATEGORIA["devolucion"])
               for m in motivos["motivo"]]
    return _barras_horizontales(motivos["motivo"], motivos["devoluciones"], textos, colores, hover, alto_fila=40)
