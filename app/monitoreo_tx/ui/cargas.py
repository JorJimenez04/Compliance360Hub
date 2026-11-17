"""
Carga del reporte de AdamoPay y bitácora de cargas.

El tamaño máximo por archivo lo fija .streamlit/config.toml (maxUploadSize).
El Excel maestro completo pesa más y procesarlo usa cerca de 1 GB de memoria:
se carga con scripts/cargar_adamopay.py desde el equipo del responsable.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from app.monitoreo_tx.domain.errores import ErrorDominio
from app.monitoreo_tx.servicio import puede_cargar, servicio
from app.monitoreo_tx.ui.componentes import mostrar_error
from app.monitoreo_tx.ui.formato import formato_entero

logger = logging.getLogger(__name__)

_NUEVA = "➕ Empresa nueva…"


def render(user: dict) -> None:
    srv = servicio()
    if puede_cargar(user):
        _formulario(user)
        st.divider()

    st.markdown("##### Bitácora de cargas")
    filas = srv.bitacora(user, limite=50)
    if not filas:
        st.caption("Aún no se ha cargado ningún archivo.")
        return
    tabla = pd.DataFrame([{
        "#": f["id"],
        "Fecha": f["finalizado_en"] or f["iniciado_en"],
        "Archivo": f["archivo"],
        "Resultado": f["resultado"],
        "Usuario": f.get("usuario") or "—",
        "Empresas": f["clientes"],
        "Leídas": f["filas_leidas"],
        "Nuevas": f["insertadas"],
        "Actualizadas": f["actualizadas"],
        "Rechazadas": f["rechazadas"],
        "Faltantes": f.get("faltantes") or 0,
        "Saldos descuadrados": f.get("descuadres_saldo") or 0,
        "Mensaje": (f["mensaje"] or "").split("\n", 1)[0],
    } for f in filas])
    st.dataframe(
        tabla, hide_index=True, width="stretch",
        column_config={"Fecha": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")},
    )


def _formulario(user: dict) -> None:
    srv = servicio()
    st.markdown("##### Cargar reporte de AdamoPay")
    st.caption(
        "**Excel maestro**: una hoja por empresa cliente. **CSV «Historial de pagos»**: el que AdamoPay "
        "exporta por cliente (separado por punto y coma); indique a qué empresa corresponde. "
        "Solo se escriben las transacciones nuevas o modificadas: cargar dos veces el mismo archivo no duplica."
    )
    archivo = st.file_uploader("Archivo", type=["xlsx", "csv"], key="tx_archivo")

    cliente = None
    if archivo is not None and archivo.name.lower().endswith(".csv"):
        nombres = [e.nombre_reporte for e in srv.empresas(user, solo_activas=False)]
        eleccion = st.selectbox("Empresa del CSV", nombres + [_NUEVA], key="tx_csv_empresa")
        if eleccion == _NUEVA:
            cliente = st.text_input("Nombre de la empresa (tal como aparece en AdamoPay)", key="tx_csv_nueva").strip()
        else:
            cliente = eleccion

    c1, c2 = st.columns(2)
    forzar = c1.checkbox("Reprocesar aunque el archivo no haya cambiado", key="tx_forzar")
    eliminar = c2.checkbox(
        "Eliminar transacciones que ya no vienen en el archivo", key="tx_eliminar",
        help="Con un CSV, solo afecta a esa empresa. Con el Excel maestro, borra también las empresas "
             "cuya hoja no viene en el archivo. Úselo solo si el archivo es la versión completa.",
    )
    if eliminar:
        st.warning("Se borrarán de la base las transacciones que no estén en este archivo. "
                   "La acción queda registrada en el log de auditoría.", icon=":material/warning:")

    listo = archivo is not None and (not archivo.name.lower().endswith(".csv") or bool(cliente))
    if st.button("Cargar archivo", type="primary", disabled=not listo, key="tx_cargar"):
        _cargar(user, archivo, cliente, forzar, eliminar)


def _cargar(user: dict, archivo, cliente: str | None, forzar: bool, eliminar: bool) -> None:
    sufijo = Path(archivo.name).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / f"carga{sufijo}"
        ruta.write_bytes(archivo.getvalue())
        try:
            with st.spinner("Procesando el archivo…"):
                r = servicio().cargar_archivo(
                    user, ruta, archivo.name, cliente=cliente, forzar=forzar, eliminar_faltantes=eliminar)
        except ErrorDominio as e:
            mostrar_error(e)
            return
        except Exception as e:
            logger.exception("Monitoreo TX: error cargando %s", archivo.name)
            st.error(f"No se pudo cargar el archivo: {e}")
            return

    if r.resultado == "OMITIDA":
        st.info(r.mensaje, icon=":material/info:")
        return
    st.success(f"Carga completada en {r.duracion_s:.1f} s.", icon=":material/check_circle:")
    c = st.columns(5)
    c[0].metric("Empresas", formato_entero(r.clientes))
    c[1].metric("Filas leídas", formato_entero(r.filas_leidas))
    c[2].metric("Nuevas", formato_entero(r.insertadas))
    c[3].metric("Actualizadas", formato_entero(r.actualizadas))
    c[4].metric("Rechazadas", formato_entero(r.rechazadas))
    st.markdown("**Verificación de completitud** (todo lo guardado de cada empresa)")
    for empresa, v in r.verificacion.items():
        if v["completa"] and not v["parcial"]:
            st.success(f"**{empresa}**: No. {v['no_inicial']} a {v['no_final']} sin huecos; "
                       f"{formato_entero(v['saldos_verificados'])} saldos verificados.", icon=":material/verified:")
        elif v["completa"]:
            st.info(f"**{empresa}**: sin huecos ni descuadres, pero el historial empieza en el No. "
                    f"{v['no_inicial']}, no en 1.", icon=":material/info:")
        else:
            detalle = []
            if v["faltantes"]:
                detalle.append(f"{v['faltantes']} número(s) faltante(s): {', '.join(v['ejemplos_faltantes'])}")
            if v["descuadres_saldo"]:
                detalle.append(f"saldo no cuadra en {v['descuadres_saldo']} movimiento(s), "
                               f"p. ej. No. {', '.join(str(n) for n in v['ejemplos_descuadre'][:5])}")
            st.warning(f"**{empresa}**: " + "; ".join(detalle)
                       + ". Revise el reporte con AdamoPay.", icon=":material/report:")
    if r.empresas_nuevas:
        st.info("Empresas nuevas: " + ", ".join(r.empresas_nuevas)
                + ". Enlácelas con su ficha en la pestaña «Empresas».", icon=":material/domain_add:")
    if r.advertencias:
        with st.expander(f"Advertencias ({len(r.advertencias)})"):
            for a in r.advertencias:
                st.markdown(f"- {a}")
    if r.rechazos:
        with st.expander(f"Filas rechazadas ({len(r.rechazos)})"):
            df = pd.DataFrame(r.rechazos)
            st.dataframe(df, hide_index=True, width="stretch")
            st.download_button("Descargar rechazos (CSV)", df.to_csv(index=False).encode("utf-8-sig"),
                               file_name="rechazos_carga.csv", mime="text/csv")
