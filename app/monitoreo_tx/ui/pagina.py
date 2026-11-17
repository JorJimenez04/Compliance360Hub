"""
Página «Monitoreo Transaccional» de Compliance360 Hub.

Pestañas:
- Tablero:  indicadores, gráficos, transacciones y riesgo de una empresa.
- Cargas:   subir el reporte de AdamoPay (Excel o CSV) y bitácora de cargas.
- Empresas: enlazar cada empresa del reporte con su ficha de Gestión de Clientes.
"""

from __future__ import annotations

import logging

import streamlit as st

from app.components import ui_kit as ui
from core.monitoreo_tx.domain.errores import ErrorDominio
from core.monitoreo_tx.servicio import puede_cargar, puede_ver, servicio
from app.monitoreo_tx.ui import cargas, empresas, tablero
from app.monitoreo_tx.ui.componentes import mostrar_error
from core.monitoreo_tx.formato import formato_fecha_hora

logger = logging.getLogger(__name__)


def render(user: dict) -> None:
    if not puede_ver(user):
        st.error("Su rol no tiene acceso al Monitoreo Transaccional.")
        return

    srv = servicio()
    try:
        ultima = srv.ultima_carga()
        lista = srv.empresas(user, solo_activas=True)
    except ErrorDominio as e:
        mostrar_error(e)
        return
    except Exception:
        logger.exception("Monitoreo TX: no se pudo leer la base")
        st.error("No se pudo consultar el módulo. Verifique que la migración 035 esté aplicada "
                 "(python db/sync_db.py).")
        return

    meta = f"Última carga: {formato_fecha_hora(ultima['finalizado_en'])}" if ultima else "Sin cargas"
    ui.render(ui.section_header(
        "Monitoreo Transaccional",
        "Transacciones de los clientes que operan con AdamoPay",
        icon_name="chart",
        meta=meta,
    ))

    nombres = ["Tablero", "Cargas"] + (["Empresas"] if puede_cargar(user) else [])
    pestañas = st.tabs(nombres)

    with pestañas[0]:
        if not lista:
            ui.render(ui.empty_state(
                "Aún no hay transacciones cargadas",
                "Suba el reporte de AdamoPay en la pestaña «Cargas».",
                icon_name="docs",
            ))
        else:
            empresa = _selector_empresa(lista)
            tablero.render(user, empresa)

    with pestañas[1]:
        cargas.render(user)

    if puede_cargar(user):
        with pestañas[2]:
            empresas.render(user)


def _selector_empresa(lista):
    por_id = {e.id: e for e in lista}
    ids = list(por_id)
    actual = st.session_state.get("tx_empresa_activa")
    empresa_id = st.selectbox(
        "Empresa", ids, index=ids.index(actual) if actual in por_id else 0,
        format_func=lambda i: por_id[i].nombre_visible + ("" if por_id[i].enlazada else "  · sin enlazar"),
        key="tx_selector_empresa",
    )
    st.session_state["tx_empresa_activa"] = empresa_id
    return por_id[empresa_id]
