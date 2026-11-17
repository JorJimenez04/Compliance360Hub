"""
Empresas del reporte de AdamoPay y su enlace con Gestión de Clientes.

Cada hoja del Excel (o CSV) crea una empresa con el nombre que usa AdamoPay.
Enlazarla con su ficha KYC permite ver en el tablero la razón social, el NIT
y el nivel de riesgo oficial del cliente.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.monitoreo_tx.domain.errores import ErrorDominio
from core.monitoreo_tx.servicio import servicio
from app.monitoreo_tx.ui.componentes import mostrar_error


def render(user: dict) -> None:
    srv = servicio()
    lista = srv.empresas(user, solo_activas=False)
    if not lista:
        st.caption("Las empresas aparecen aquí después de la primera carga.")
        return
    conteo = srv.conteo_por_empresa(user)

    st.dataframe(pd.DataFrame([{
        "Nombre en AdamoPay": e.nombre_reporte,
        "Cliente enlazado": e.razon_social or "—",
        "NIT": e.nit or "—",
        "Riesgo KYC": e.nivel_riesgo or "—",
        "Transacciones": conteo.get(e.nombre_reporte, 0),
        "Activa": e.activa,
    } for e in lista]), hide_index=True, width="stretch",
        column_config={"Transacciones": st.column_config.NumberColumn(format="localized")})

    pendientes = [e for e in lista if not e.enlazada]
    if pendientes:
        st.caption(f"{len(pendientes)} empresa(s) sin enlazar con su ficha de Gestión de Clientes.")

    st.markdown("##### Editar empresa")
    por_id = {e.id: e for e in lista}
    empresa_id = st.selectbox("Empresa", list(por_id), format_func=lambda i: por_id[i].nombre_reporte,
                              key="tx_emp_editar")
    empresa = por_id[empresa_id]

    clientes = srv.clientes_disponibles(user)
    opciones = [None] + [c["id"] for c in clientes]
    etiquetas = {c["id"]: f"{c['razon_social']}  ·  NIT {c['nit'] or 's/n'}  ·  {c['nivel_riesgo']}" for c in clientes}
    with st.form(f"tx_form_empresa_{empresa_id}"):
        cliente_id = st.selectbox(
            "Ficha en Gestión de Clientes", opciones,
            index=opciones.index(empresa.cliente_id) if empresa.cliente_id in opciones else 0,
            format_func=lambda i: "— Sin enlazar —" if i is None else etiquetas[i],
        )
        activa = st.toggle("Activa (aparece en el tablero)", value=empresa.activa)
        guardar = st.form_submit_button("Guardar", type="primary")
    if not clientes:
        st.caption("No hay fichas en Gestión de Clientes. Créela allí primero para poder enlazarla.")

    if guardar:
        try:
            if cliente_id != empresa.cliente_id:
                srv.enlazar_cliente(user, empresa_id, cliente_id)
            if activa != empresa.activa:
                srv.cambiar_estado(user, empresa_id, activa)
        except ErrorDominio as e:
            mostrar_error(e)
            return
        st.success("Cambios guardados.")
        st.rerun()
