"""
Tablero transaccional de una empresa cliente de AdamoPay (pestaña «Tablero»
del módulo Monitoreo Transaccional). Uso interno: el usuario es de
Compliance360 Hub con un rol de ROLES_MONITOREO, por eso ve siempre la
evaluación de riesgo.

Organización pensada para un lector no técnico:
filtros a la vista -> resumen en palabras -> indicadores con variación ->
pestañas que responden una pregunta cada una.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core.monitoreo_tx.domain import metricas
from core.monitoreo_tx.domain.entidades import EmpresaVista, FiltrosTransacciones, OpcionesFiltro
from core.monitoreo_tx.domain.errores import ErrorDominio
from core.monitoreo_tx.servicio import registrar_auditoria, servicio
from app.monitoreo_tx.ui import graficos
from app.monitoreo_tx.ui.componentes import ficha, mostrar_error
from core.monitoreo_tx.formato import (
    enmascarar,
    fecha_corta,
    fecha_larga,
    formato_cop,
    formato_entero,
    formato_fecha_hora,
    formato_porcentaje,
    formato_variacion,
    slug,
)

logger = logging.getLogger(__name__)


def _md(texto: str) -> str:
    """Escapa los «$» de las cifras: con dos en un mismo párrafo, Streamlit los toma
    como fórmula matemática y el texto sale roto."""
    return texto.replace("$", "\\$")

MAX_FILAS_TABLA = 10_000  # la tabla viaja al navegador en cada interacción; el CSV trae todo
PERIODOS = {"Último mes": 30, "3 meses": 90, "12 meses": 365, "Todo": None, "Elegir fechas": None}
PERIODO_INICIAL = "3 meses"


def render(user: dict, empresa: EmpresaVista) -> None:
    srv = servicio()
    try:
        opciones = srv.opciones_filtro(user, empresa.id)
    except ErrorDominio as e:
        mostrar_error(e)
        return

    _encabezado(empresa, opciones)
    if opciones.tiene_datos:
        _estado_completitud(user, empresa)
    if not opciones.tiene_datos:
        st.info("Aún no hay transacciones cargadas para esta empresa. Use la pestaña «Cargas» para subir "
                "el reporte de AdamoPay.", icon=":material/hourglass_empty:")
        return

    filtros = _barra_filtros(empresa, opciones)
    if filtros is None:
        return

    with st.spinner("Consultando transacciones…"):
        df = srv.transacciones_filtradas(user, empresa.id, filtros)
        anterior = srv.kpis_periodo_anterior(user, empresa.id, filtros)
    if df.empty:
        st.info("No hay transacciones que cumplan los filtros seleccionados. Pruebe con un período "
                "más amplio o borre la búsqueda.", icon=":material/search_off:")
        return

    k = metricas.calcular_kpis(df)
    _resumen_en_palabras(k, anterior, df, filtros, "la empresa")
    _indicadores(k, anterior, df)

    nombres = [
        ":material/show_chart: Evolución",
        ":material/donut_small: Movimientos y montos",
        ":material/leaderboard: Ranking de clientes",
        ":material/account_balance: Destinos y horarios",
        ":material/undo: Devoluciones",
        ":material/table_rows: Transacciones",
        ":material/shield: Riesgo y cumplimiento",
    ]
    pestañas = st.tabs(nombres)
    with pestañas[0]:
        _pestaña_evolucion(df, filtros, empresa)
    with pestañas[1]:
        _pestaña_movimientos(df)
    with pestañas[2]:
        _pestaña_ranking(df, empresa)
    with pestañas[3]:
        _pestaña_destinos(df)
    with pestañas[4]:
        _pestaña_devoluciones(df, k)
    with pestañas[5]:
        _pestaña_transacciones(user, df, empresa, filtros)
    with pestañas[6]:
        _seccion_riesgo(user, empresa, filtros)


# =========================
# Encabezado y filtros
# =========================
def _encabezado(empresa: EmpresaVista, opciones: OpcionesFiltro) -> None:
    partes = []
    if empresa.nit:
        partes.append(f"NIT {empresa.nit}")
    if empresa.enlazada and empresa.nivel_riesgo:
        partes.append(f"Riesgo en ficha KYC: {empresa.nivel_riesgo}")
    elif not empresa.enlazada:
        partes.append("Sin enlazar con Gestión de Clientes")
    if opciones.tiene_datos:
        partes.append(f"Movimientos del {fecha_larga(opciones.fecha_min)} al {fecha_larga(opciones.fecha_max)}")
    st.caption(" · ".join(partes))


def _estado_completitud(user: dict, empresa: EmpresaVista) -> None:
    """Si faltan movimientos, los indicadores y alertas se calculan sobre datos incompletos: se dice."""
    try:
        cont = servicio().continuidad(user, empresa.id)
    except Exception:
        logger.exception("No se pudo verificar la completitud de %s", empresa.nombre_reporte)
        return
    if cont.completa and not cont.parcial:
        st.caption(f":material/verified: {cont.resumen()}.")
    elif cont.completa:
        st.info(cont.resumen() + ". Cargue un exporte desde el inicio para verificar el historial completo.",
                icon=":material/info:")
    else:
        st.warning(f"**Datos incompletos:** {cont.resumen()}. Los indicadores y alertas pueden no reflejar "
                   "toda la actividad. Descargue de nuevo el reporte completo de AdamoPay y cárguelo.",
                   icon=":material/report:")


def _barra_filtros(empresa: EmpresaVista, opciones: OpcionesFiltro) -> FiltrosTransacciones | None:
    clave = f"e{empresa.id}"  # filtros independientes por empresa
    with st.container(border=True):
        c_periodo, c_buscar, c_mas = st.columns([3.6, 2, 1], vertical_alignment="bottom")
        periodo = c_periodo.segmented_control(
            "Período", list(PERIODOS), default=PERIODO_INICIAL, key=f"periodo_{clave}",
        ) or PERIODO_INICIAL
        texto = c_buscar.text_input(
            "Buscar", placeholder="ID, referencia o beneficiario", key=f"texto_{clave}",
            help="Busca en el ID de la transacción, la referencia, la descripción, el beneficiario y su documento.",
        )
        with c_mas.popover("Más filtros", icon=":material/tune:", width="stretch"):
            estados = st.multiselect(
                "Estados", opciones.estados, default=list(opciones.estados), key=f"estados_{clave}",
            )
            if st.button("Restablecer filtros", key=f"reset_{clave}", width="stretch"):
                for k in (f"periodo_{clave}", f"texto_{clave}", f"estados_{clave}", f"fechas_{clave}"):
                    st.session_state.pop(k, None)
                st.rerun()

        desde, hasta = _rango_del_periodo(periodo, opciones)
        if periodo == "Elegir fechas":
            rango = st.date_input(
                "Fechas", value=(desde, hasta), min_value=opciones.fecha_min,
                max_value=opciones.fecha_max, format="DD/MM/YYYY", key=f"fechas_{clave}",
            )
            # Mientras el usuario elige, date_input devuelve una sola fecha (o ninguna si las borra)
            if isinstance(rango, date):
                rango = (rango,)
            if len(rango) == 2:
                desde, hasta = rango
            elif len(rango) == 1:
                desde, hasta = rango[0], opciones.fecha_max

        detalle = f"Del {fecha_larga(desde)} al {fecha_larga(hasta)}"
        if len(estados) < len(opciones.estados):
            detalle += f" · {len(estados)} de {len(opciones.estados)} estados"
        if texto.strip():
            detalle += f" · búsqueda «{texto.strip()}»"
        st.caption(detalle)

    if not estados:
        st.info("Seleccione al menos un estado en «Más filtros».", icon=":material/tune:")
        return None
    return FiltrosTransacciones(desde=desde, hasta=hasta, estados=tuple(estados), texto=texto.strip())


def _rango_del_periodo(periodo: str, opciones: OpcionesFiltro) -> tuple[date, date]:
    """Los períodos se cuentan hacia atrás desde la última fecha con datos, no desde hoy."""
    fin = opciones.fecha_max
    dias = PERIODOS.get(periodo)
    if dias is None:
        return opciones.fecha_min, fin
    return max(opciones.fecha_min, fin - timedelta(days=dias - 1)), fin


# =========================
# Resumen e indicadores
# =========================
def _resumen_en_palabras(k: metricas.KPIs, anterior: metricas.KPIs | None,
                         df: pd.DataFrame, filtros: FiltrosTransacciones, sujeto: str) -> None:
    frases = [
        f"Entre el **{fecha_corta(filtros.desde)}** y el **{fecha_corta(filtros.hasta)}** {sujeto} realizó "
        f"**{formato_entero(k.pagos_exitosos)} pagos exitosos** por **{formato_cop(k.monto_pagado)}**."
    ]
    if anterior and anterior.monto_pagado:
        cambio = metricas.variacion(k.monto_pagado, anterior.monto_pagado)
        sentido = "más" if cambio >= 0 else "menos"
        frases.append(f"Es un **{formato_porcentaje(abs(cambio))} {sentido}** que en el período anterior "
                      f"de igual duración ({formato_cop(anterior.monto_pagado, compacto=True)}).")
    if k.pagos_enviados:
        frases.append(f"El **{formato_porcentaje(k.tasa_exito)}** de los pagos enviados llegó a su destino")
        if k.devoluciones:
            frases[-1] += (f"; **{formato_entero(k.devoluciones)}** fueron devueltos por el banco "
                           "(vea la pestaña Devoluciones).")
        else:
            frases[-1] += " y no hubo devoluciones."
    pico = metricas.dia_pico(df)
    if pico:
        frases.append(f"El día de mayor movimiento fue el {fecha_larga(pico[0])}, "
                      f"con {formato_cop(pico[1], compacto=True)} pagados.")

    with st.container(border=True):
        st.markdown("**:material/insights: Resumen del período**")
        st.markdown(_md(" ".join(frases)))


def _indicadores(k: metricas.KPIs, anterior: metricas.KPIs | None, df: pd.DataFrame) -> None:
    def var(actual, campo, puntos=False):
        if anterior is None:
            return None
        base = getattr(anterior, campo)
        if puntos:
            return formato_variacion(actual - base, puntos=True) if anterior.pagos_enviados else None
        return formato_variacion(metricas.variacion(actual, base))

    ayuda_var = " La flecha compara con el período anterior de igual duración."
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Monto pagado (COP)", formato_cop(k.monto_pagado, compacto=True),
              delta=var(k.monto_pagado, "monto_pagado"), border=True,
              help=f"Suma de los pagos exitosos: {formato_cop(k.monto_pagado)} pesos colombianos. "
                   "M = millones." + ayuda_var)
    c2.metric("Pagos exitosos", formato_entero(k.pagos_exitosos),
              delta=var(k.pagos_exitosos, "pagos_exitosos"), border=True,
              help=f"Pagos confirmados (Pagado o Validado) de {formato_entero(k.pagos_enviados)} enviados." + ayuda_var)
    c3.metric("Tasa de éxito", formato_porcentaje(k.tasa_exito),
              delta=var(k.tasa_exito, "tasa_exito", puntos=True), border=True,
              help="Pagos que llegaron a su destino (exitosos menos devoluciones) sobre los pagos enviados. "
                   "La variación se expresa en puntos porcentuales (pp)." + ayuda_var)
    c4.metric("Pago promedio (COP)", formato_cop(k.ticket_promedio),
              delta=var(k.ticket_promedio, "ticket_promedio"), delta_color="off", border=True,
              help="Monto pagado dividido entre el número de pagos exitosos." + ayuda_var)

    c5, c6, c7 = st.columns(3)
    c5.metric("Fondeos recibidos (COP)", formato_cop(k.monto_fondeado, compacto=True),
              delta=f"{formato_entero(k.fondeos)} recargas", delta_color="off", delta_arrow="off", border=True,
              help="Recargas de saldo de la cuenta en AdamoPay.")
    c6.metric("Devoluciones", formato_entero(k.devoluciones),
              delta=var(k.devoluciones, "devoluciones"), delta_color="inverse", border=True,
              help=f"Pagos devueltos por el banco destino, por {formato_cop(k.monto_devuelto)}. "
                   "Que baje es positivo." + ayuda_var)
    beneficiarios = metricas.pagos_exitosos(df)["id_beneficiario"].nunique()
    por_beneficiario = f"{k.pagos_exitosos / beneficiarios:.1f}".replace(".", ",") if beneficiarios else "0"
    c7.metric("Beneficiarios distintos", formato_entero(beneficiarios),
              delta=f"{por_beneficiario} pagos por beneficiario", delta_color="off", delta_arrow="off", border=True,
              help="Personas o empresas que recibieron al menos un pago exitoso en el período.")
    st.caption(":material/payments: Todas las cifras están en pesos colombianos (COP). **M** = millones de pesos.")


# =========================
# Pestañas
# =========================
def _pestaña_evolucion(df: pd.DataFrame, filtros: FiltrosTransacciones, empresa: EmpresaVista) -> None:
    sugerida = metricas.granularidad_sugerida(filtros.desde, filtros.hasta)
    c1, c2 = st.columns([1, 1])
    medida = c1.segmented_control(
        "Mostrar", ["Monto pagado", "Número de pagos"], default="Monto pagado", key="evol_medida",
    ) or "Monto pagado"
    granularidad = c2.segmented_control(
        "Agrupar por", ["Diaria", "Semanal", "Mensual"], default=sugerida,
        # La clave incluye el período: al cambiarlo, se vuelve a la agrupación sugerida
        key=f"evol_gran_{empresa.id}_{filtros.desde}_{filtros.hasta}",
        format_func=lambda g: {"Diaria": "Día", "Semanal": "Semana", "Mensual": "Mes"}[g],
    ) or sugerida

    serie = metricas.serie_pagos(df, granularidad)
    if serie.empty:
        st.info("No hay pagos exitosos en el período seleccionado.")
        return
    st.plotly_chart(
        graficos.grafico_tendencia(serie, granularidad, "monto" if medida == "Monto pagado" else "pagos"),
        width="stretch", config=graficos.CONFIG,
    )
    st.caption("Pase el cursor sobre el gráfico para ver el monto y el número de pagos de cada período.")


def _pestaña_movimientos(df: pd.DataFrame) -> None:
    izq, der = st.columns(2, gap="large")
    with izq:
        st.markdown("##### ¿Qué movimientos tuvo la cuenta?")
        medida = st.segmented_control(
            "Medir por", ["Cantidad", "Monto"], default="Cantidad", key="mov_medida",
            label_visibility="collapsed",
        ) or "Cantidad"
        comp = metricas.composicion_movimientos(df)
        st.plotly_chart(
            graficos.grafico_composicion(comp, "movimientos" if medida == "Cantidad" else "monto"),
            width="stretch", config=graficos.CONFIG,
        )
        with st.expander("¿Qué significa cada tipo de movimiento?"):
            st.markdown(
                "- **Pagos exitosos**: pagos a los beneficiarios confirmados por el banco.\n"
                "- **Pagos sin estado confirmado**: el reporte no informó su resultado.\n"
                "- **Pagos rechazados**: no se pudieron enviar.\n"
                "- **Devoluciones**: pagos que el banco destino devolvió (por ejemplo, cuenta inexistente).\n"
                "- **Fondeos (recargas)**: dinero que ingresó a la cuenta en AdamoPay.\n"
                "- **Transferencias internas**: movimientos entre cuentas de la propia empresa."
            )
    with der:
        st.markdown("##### ¿De qué tamaño son los pagos?")
        st.caption("Pagos exitosos agrupados por rango de monto.")
        dist = metricas.distribucion_montos(df)
        if dist["pagos"].sum() == 0:
            st.info("No hay pagos exitosos en el período.")
        else:
            st.plotly_chart(graficos.grafico_rangos(dist), width="stretch", config=graficos.CONFIG)
            principal = dist.loc[dist["pagos"].idxmax()]
            st.caption(_md(f"La mayoría de los pagos ({formato_porcentaje(principal['pct'])}) está entre "
                           f"{principal['rango'].replace('–', 'y')}." if "–" in principal["rango"] else
                           f"La mayoría de los pagos ({formato_porcentaje(principal['pct'])}) son de "
                           f"{principal['rango'].lower()}."))


def _pestaña_ranking(df: pd.DataFrame, empresa: EmpresaVista) -> None:
    c1, c2 = st.columns([1, 1], vertical_alignment="bottom")
    orden = c1.segmented_control(
        "Ordenar por", ["Monto pagado", "Número de transacciones"], default="Monto pagado",
        key=f"rank_orden_{empresa.id}",
    ) or "Monto pagado"
    cuantos = c2.segmented_control(
        "Mostrar", [10, 20, 50], default=10, key=f"rank_n_{empresa.id}", format_func=lambda n: f"Top {n}",
    ) or 10
    por = "monto" if orden == "Monto pagado" else "pagos"

    top = metricas.top_beneficiarios(df, n=cuantos, por=por)
    if top.empty:
        st.info("No hay pagos exitosos en el período seleccionado.")
        return

    unidad = "del monto pagado" if por == "monto" else "de las transacciones"
    st.markdown(
        f"Los **{len(top)} clientes** con mayor {'monto' if por == 'monto' else 'número de transacciones'} "
        f"concentran el **{formato_porcentaje(top['pct'].sum())}** {unidad} en el período."
    )
    st.markdown(f"##### Top 10 por {'monto (COP)' if por == 'monto' else 'número de transacciones'}")
    st.plotly_chart(graficos.grafico_ranking(top.head(10), por), width="stretch", config=graficos.CONFIG)

    st.markdown(f"##### Detalle del top {len(top)}")
    tabla = pd.DataFrame({
        "#": top["posicion"],
        "Cliente": top["beneficiario"].fillna("Sin nombre"),
        "Documento": top["id_beneficiario"].map(enmascarar),
        "Transacciones": top["pagos"],
        "Monto (COP)": top["monto"],
        "Participación": top["pct"] * 100,
        "Último pago": top["ultimo_pago"],
    })
    st.dataframe(
        tabla, hide_index=True, width="stretch", height=min(430, 36 * len(tabla) + 40),
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "Cliente": st.column_config.TextColumn(width="large"),
            "Transacciones": st.column_config.NumberColumn(format="localized"),
            "Monto (COP)": st.column_config.NumberColumn(format="localized"),
            "Participación": st.column_config.NumberColumn(format="%.1f%%"),
            "Último pago": st.column_config.DatetimeColumn(format="DD/MM/YYYY"),
        },
    )
    st.caption("Clientes: personas o empresas que recibieron pagos exitosos. La participación se calcula "
               "sobre el total del período filtrado.")


def _pestaña_destinos(df: pd.DataFrame) -> None:
    izq, der = st.columns(2, gap="large")
    with izq:
        st.markdown("##### ¿A qué bancos llegan los pagos?")
        st.caption("Monto de pagos exitosos por banco de destino.")
        top = metricas.top_bancos(df)
        if top.empty:
            st.info("No hay pagos exitosos con banco informado en el período.")
        else:
            st.plotly_chart(graficos.grafico_bancos(top), width="stretch", config=graficos.CONFIG)
    with der:
        st.markdown("##### ¿Cuándo realiza los pagos?")
        st.caption("Pagos exitosos por día de la semana y hora. Un color más oscuro indica más pagos.")
        actividad = metricas.actividad_semana_hora(df)
        if actividad.values.sum() == 0:
            st.info("No hay pagos exitosos en el período.")
        else:
            st.plotly_chart(graficos.grafico_actividad(actividad), width="stretch", config=graficos.CONFIG)
            dia = actividad.sum(axis=1).idxmax()
            hora = int(actividad.sum(axis=0).idxmax())
            st.caption(f"El día con más pagos es el **{dia.lower()}** y la franja más activa, "
                       f"de **{hora:02d}:00 a {hora + 1:02d}:00**.")


_MOTIVOS_DE_DATOS = {
    "Cuenta y documento no coinciden",
    "La cuenta no existe o el número es inválido",
    "Tipo de cuenta incorrecto",
    "Datos del pago incorrectos",
}


def _pestaña_devoluciones(df: pd.DataFrame, k: metricas.KPIs) -> None:
    if not k.devoluciones:
        st.success("No hubo devoluciones en el período seleccionado.", icon=":material/check_circle:")
        return

    st.markdown(_md(
        f"En el período, **{formato_entero(k.devoluciones)} pagos** por **{formato_cop(k.monto_devuelto)}** "
        f"fueron devueltos por el banco destino "
        f"({formato_porcentaje(k.tasa_devolucion)} de los pagos exitosos)."
    ))
    motivos = metricas.motivos_devolucion(df)
    izq, der = st.columns([1.6, 1], gap="large")
    with izq:
        st.markdown("##### ¿Por qué se devolvieron?")
        st.plotly_chart(graficos.grafico_motivos(motivos), width="stretch", config=graficos.CONFIG)
    with der:
        st.write("")
        principal = motivos.iloc[0]
        st.markdown(f"El motivo más frecuente es **{principal['motivo'].lower()}** "
                    f"({formato_porcentaje(principal['pct'])} de los casos).")
        de_datos = motivos[motivos["motivo"].isin(_MOTIVOS_DE_DATOS)]
        pct_datos = de_datos["devoluciones"].sum() / motivos["devoluciones"].sum()
        if pct_datos >= 0.2:
            st.info(
                f"**{formato_porcentaje(pct_datos)} de las devoluciones** se deben a datos de la cuenta "
                "del beneficiario (número, tipo de cuenta o documento que no coinciden). Verificar esos "
                "datos antes de pagar evita la mayoría de estas devoluciones.",
                icon=":material/lightbulb:",
            )

    st.markdown("##### Devoluciones más recientes")
    dev = metricas.devoluciones(df)
    recientes = dev.head(20)
    recientes = recientes.assign(
        Motivo=recientes["descripcion"].map(metricas.motivo_devolucion),
        id_beneficiario=recientes["id_beneficiario"].map(enmascarar),
        numero_cuenta=recientes["numero_cuenta"].map(enmascarar),
    )
    st.dataframe(
        recientes[["fecha_hora", "beneficiario", "id_beneficiario", "banco", "numero_cuenta", "monto", "Motivo"]]
        .rename(columns={"fecha_hora": "Fecha", "beneficiario": "Beneficiario", "id_beneficiario": "Documento",
                         "banco": "Banco", "numero_cuenta": "Cuenta", "monto": "Monto (COP)"}),
        hide_index=True, width="stretch",
        column_config={
            "Fecha": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
            "Monto (COP)": st.column_config.NumberColumn(format="localized"),
            "Beneficiario": st.column_config.TextColumn(width="medium"),
            "Motivo": st.column_config.TextColumn(width="large"),
        },
    )


def _pestaña_transacciones(user: dict, df: pd.DataFrame, empresa: EmpresaVista,
                           filtros: FiltrosTransacciones) -> None:
    srv = servicio()
    total = len(df)
    # Solo se prepara lo que se muestra; el CSV completo se genera al descargar
    vista = metricas.tabla_para_exporte(df.head(MAX_FILAS_TABLA))
    # En pantalla, cuentas y documentos van enmascarados (toda la tabla viaja al
    # navegador, también las columnas ocultas). Completos solo en el CSV, que queda auditado.
    for columna in ("Documento beneficiario", "Número de cuenta"):
        if columna in vista.columns:
            vista[columna] = vista[columna].map(enmascarar)
    nombre = f"monitoreo_tx_{slug(empresa.nombre_visible)}_{filtros.desde:%Y%m%d}_{filtros.hasta:%Y%m%d}.csv"

    info, boton = st.columns([3, 1], vertical_alignment="center")
    info.markdown(f"**{formato_entero(total)}** movimientos · Seleccione una fila para ver su detalle.")
    info.caption(":material/visibility_off: Por seguridad, cuentas y documentos se muestran parcialmente; "
                 "el CSV los trae completos.")
    boton.download_button(
        "Descargar CSV",
        # Función: el archivo se arma solo cuando el usuario hace clic, no en cada interacción
        data=lambda: srv.csv_transacciones(user, empresa.id, filtros),
        on_click=lambda: registrar_auditoria(
            user, "EXPORT",
            f"Monitoreo TX: CSV de {empresa.nombre_reporte} · {filtros.desde:%Y-%m-%d} a {filtros.hasta:%Y-%m-%d} · "
            f"{formato_entero(total)} movimientos"),
        file_name=nombre, mime="text/csv",
        icon=":material/download:", type="primary", width="stretch",
        help="Descarga todos los movimientos del filtro actual, con números de cuenta y documentos completos. "
             "Se abre directamente en Excel. La descarga queda registrada.",
    )
    if total > MAX_FILAS_TABLA:
        st.caption(f"Se muestran los {formato_entero(MAX_FILAS_TABLA)} más recientes; el CSV incluye todos.")

    moneda = st.column_config.NumberColumn(format="localized")
    evento = st.dataframe(
        vista,
        hide_index=True,
        width="stretch",
        height=480,
        on_select="rerun",
        selection_mode="single-row",
        # La clave cambia con la empresa y los filtros: la fila elegida no se arrastra a otra consulta
        key=f"tabla_tx_{empresa.id}_{hash(filtros)}",
        column_order=["Fecha y hora", "Movimiento", "Beneficiario", "Banco", "Monto (COP)", "Estado",
                      "ID transacción", "Descripción"],
        column_config={
            "Fecha y hora": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
            "Monto (COP)": moneda,
            "Descripción": st.column_config.TextColumn(width="medium"),
        },
    )
    filas = evento.selection.rows if evento and evento.selection else []
    if filas:
        _detalle_transaccion(vista.iloc[filas[0]])


def _detalle_transaccion(fila: pd.Series) -> None:
    with st.container(border=True):
        st.markdown(f"**:material/receipt_long: Transacción {fila['ID transacción']}**")
        campos = [
            ("Fecha y hora", formato_fecha_hora(fila["Fecha y hora"]) if pd.notna(fila["Fecha y hora"]) else "—"),
            ("Movimiento", fila["Movimiento"]), ("Estado", fila["Estado"]),
            ("Beneficiario", fila["Beneficiario"]), ("Documento", fila.get("Documento beneficiario")),
            ("Banco", fila["Banco"]), ("Tipo de cuenta", fila.get("Tipo de cuenta")),
            ("Número de cuenta", fila.get("Número de cuenta")),
            ("Monto", formato_cop(fila["Monto (COP)"])),
            ("Comisión", formato_cop(fila["Comisión (COP)"]) if pd.notna(fila["Comisión (COP)"]) else "—"),
            ("Saldo después", formato_cop(fila["Saldo (COP)"]) if pd.notna(fila["Saldo (COP)"]) else "—"),
            ("Descripción", fila.get("Descripción")),
        ]
        if metricas.tipo_movimiento(fila["Tipo de transacción"]) == metricas.DEVOLUCION:
            campos.append(("Motivo de la devolución", metricas.motivo_devolucion(fila.get("Descripción"))))
        ficha(campos, columnas=3)


# =========================
# Riesgo (solo administradores)
# =========================
def _seccion_riesgo(user: dict, empresa: EmpresaVista, filtros: FiltrosTransacciones) -> None:
    st.caption(
        "Uso interno. Evaluación indicativa calculada sobre las transacciones del filtro actual "
        "(GAFI 40 % · UIAF 35 % · Operativo 25 %). Es una ayuda para priorizar la revisión; no reemplaza "
        "la segmentación ni el análisis del Oficial de Cumplimiento. El nivel oficial del cliente es el de su "
        "ficha KYC en Gestión de Clientes."
    )
    try:
        with st.spinner("Evaluando perfil de riesgo…"):
            analisis = servicio().evaluar_riesgo(user, empresa.id, filtros)
    except ErrorDominio as e:
        mostrar_error(e)
        return
    except Exception:
        logger.exception("Error en análisis de riesgo de %s", empresa.nombre_reporte)
        st.error("No se pudo calcular el análisis de riesgo. El detalle quedó en el registro del servidor.")
        return

    scoring = analisis.get("scoring", {})
    nivel = scoring.get("nivel_riesgo", "No evaluado")
    iconos = {"Bajo": ":material/check_circle:", "Medio": ":material/warning:",
              "Alto": ":material/error:", "Crítico": ":material/dangerous:"}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score total", f"{scoring.get('score_total', 'N/A')}/100", border=True)
    c2.metric("Score GAFI", f"{scoring.get('score_gafi', 'N/A')}/100", border=True)
    c3.metric("Score UIAF", f"{scoring.get('score_uiaf', 'N/A')}/100", border=True)
    c4.metric("Score operativo", f"{scoring.get('score_operativo', 'N/A')}/100", border=True)

    aviso = {"Bajo": st.success, "Medio": st.warning, "Alto": st.error, "Crítico": st.error}.get(nivel, st.info)
    aviso(f"Nivel de riesgo: **{nivel}**", icon=iconos.get(nivel, ":material/help:"))

    izq, der = st.columns(2, gap="large")
    with izq:
        alertas = analisis.get("alertas", [])
        st.markdown(f"#### Alertas ({len(alertas)})")
        if not alertas:
            st.caption("Sin alertas para el período.")
        for a in alertas:
            with st.expander(f"{a.get('prioridad', '')} · {a.get('titulo', 'Alerta')}"):
                st.write(a.get("descripcion", ""))
                if a.get("accion_requerida"):
                    st.markdown(f"**Acción requerida:** {a['accion_requerida']}")
                st.caption(
                    f"Tipo: {a.get('tipo', '')} · Días para acción: {a.get('dias_para_accion', 'N/A')}"
                    + (" · Requiere reporte UIAF" if a.get("requiere_reporte_uiaf") else "")
                )
    with der:
        st.markdown("#### Recomendaciones")
        for r in analisis.get("recomendaciones", []) or ["Sin recomendaciones adicionales."]:
            st.markdown(f"- {r}")
        if analisis.get("requiere_due_diligence_reforzada"):
            st.warning("Requiere debida diligencia reforzada.")
        if analisis.get("requiere_escalamiento"):
            st.error("Requiere escalamiento al Oficial de Cumplimiento.")
        if analisis.get("proximo_review"):
            st.caption(f"Próxima revisión: {analisis['proximo_review']}")
