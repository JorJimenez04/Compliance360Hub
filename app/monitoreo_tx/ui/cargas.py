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
from app.monitoreo_tx.ui.formato import formato_entero, formato_fecha_hora

logger = logging.getLogger(__name__)

_NUEVA = "➕ Empresa nueva…"


def render(user: dict) -> None:
    srv = servicio()
    _seccion_nube(user)
    st.divider()
    if puede_cargar(user):
        with st.expander("Carga manual de un archivo", expanded=False):
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


def _seccion_nube(user: dict) -> None:
    srv = servicio()
    try:
        estado = srv.estado_nube(user)
    except Exception:
        logger.exception("Monitoreo TX: no se pudo leer el estado de la carga automática")
        st.warning("No se pudo leer el estado de la carga automática. Verifique que la migración 036 "
                   "esté aplicada (python db/sync_db.py).")
        return

    st.markdown("##### Carga automática desde OneDrive")
    if not estado["configurada"]:
        st.info("La carga automática no está configurada en el servidor. Mientras tanto, use la carga "
                "manual. Variables necesarias: TX_ONEDRIVE_TENANT_ID y TX_ONEDRIVE_CLIENT_ID.",
                icon=":material/cloud_off:")
    elif estado["delegado"] and not estado["lista"]:
        _conectar(user, reconectar=estado["conexion"] is not None)
    else:
        st.caption(f":material/cloud_sync: Carpeta: **{estado['descripcion']}**. Cada empresa en su "
                   "subcarpeta; los CSV nuevos o modificados se cargan solos cada hora.")
        if estado["delegado"] and estado["conexion"]:
            c = estado["conexion"]
            st.caption(f"Conectado por {c['conectado_por']} el {formato_fecha_hora(c['conectado_en'])} · "
                       f"acceso renovado el {formato_fecha_hora(c['renovado_en'])}.")

    revs = estado["revisiones"]
    if revs:
        u = revs[0]
        cuando = formato_fecha_hora(u["finalizado_en"] or u["iniciado_en"])
        texto = f"Última revisión: **{cuando}** ({u['usuario'] or 'programada'}) · {u['mensaje'] or u['resultado']}"
        {"OK": st.success, "CON_ERRORES": st.warning, "ERROR": st.error}.get(u["resultado"], st.info)(
            texto, icon=":material/schedule:")
    elif estado["lista"]:
        st.caption("Aún no se ha hecho ninguna revisión.")

    if estado["lista"] and puede_cargar(user):
        c1, c2 = st.columns([1, 1])
        if c1.button("Sincronizar ahora", icon=":material/sync:", key="tx_sync_nube"):
            _sincronizar_ahora(user)
        if estado["delegado"] and c2.button("Desconectar OneDrive", icon=":material/link_off:",
                                            key="tx_desconectar"):
            srv.desconectar_onedrive(user)
            st.rerun()

    if estado["archivos"]:
        with st.expander(f"Archivos procesados desde la nube ({len(estado['archivos'])} más recientes)"):
            st.dataframe(pd.DataFrame([{
                "Procesado": a["procesado_en"], "Empresa": a["empresa"], "Archivo": a["nombre"],
                "Resultado": a["resultado"], "Detalle": (a["mensaje"] or "").split("\n", 1)[0],
            } for a in estado["archivos"]]), hide_index=True, width="stretch",
                column_config={"Procesado": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})


def _sincronizar_ahora(user: dict) -> None:
    from app.monitoreo_tx.nube.fuentes import ErrorConexion
    try:
        with st.spinner("Revisando OneDrive y cargando archivos nuevos…"):
            r = servicio().sincronizar_nube_ahora(user)
    except ErrorDominio as e:
        mostrar_error(e)
        return
    except ErrorConexion as e:
        st.error(f"{e}", icon=":material/link_off:")
        return
    except Exception as e:
        logger.exception("Monitoreo TX: falló la sincronización manual")
        st.error(f"No se pudo sincronizar: {e}")
        return
    if r.resultado == "EN_CURSO":
        st.info(r.mensaje, icon=":material/hourglass_top:")
    else:
        st.rerun()


def _conectar(user: dict, reconectar: bool) -> None:
    """Inicio de sesión con código: la app nunca ve la contraseña del usuario."""
    if reconectar:
        st.warning("La conexión con OneDrive venció o no se puede leer. Vuelva a conectar para reanudar "
                   "la carga automática.", icon=":material/link_off:")
    else:
        st.info("Conecte su OneDrive una sola vez. Después, la carga es automática: la app solo podrá "
                "leer sus archivos (no los modifica ni ve los de otras personas).", icon=":material/cloud:")
    if not puede_cargar(user):
        return

    flujo = st.session_state.get("tx_flujo_onedrive")
    if flujo is None:
        if st.button("Reconectar OneDrive" if reconectar else "Conectar OneDrive", type="primary",
                     icon=":material/link:", key="tx_conectar"):
            try:
                st.session_state["tx_flujo_onedrive"] = servicio().iniciar_conexion_onedrive(user)
            except Exception as e:
                logger.exception("Monitoreo TX: no se pudo iniciar la conexión con OneDrive")
                st.error(f"No se pudo iniciar la conexión: {e}")
                return
            st.rerun()
        return

    with st.container(border=True):
        st.markdown(
            f"1. Abra **[{flujo['verification_uri']}]({flujo['verification_uri']})**\n"
            f"2. Escriba este código: **`{flujo['user_code']}`**\n"
            "3. Inicie sesión con su cuenta de la empresa y acepte los permisos.\n"
            "4. Vuelva aquí y pulse **Ya inicié sesión**."
        )
        st.caption(f"El código vence en {int(flujo.get('expires_in', 900)) // 60} minutos.")
        c1, c2 = st.columns([1, 1])
        if c1.button("Ya inicié sesión", type="primary", key="tx_completar"):
            try:
                hecho = servicio().completar_conexion_onedrive(user, flujo["device_code"])
            except ErrorDominio as e:
                mostrar_error(e)
                return
            except Exception as e:
                st.session_state.pop("tx_flujo_onedrive", None)
                st.error(f"{e}")
                return
            if hecho is None:
                st.info("Microsoft aún no confirma el inicio de sesión. Termine los pasos y vuelva a pulsar.",
                        icon=":material/hourglass_top:")
            else:
                st.session_state.pop("tx_flujo_onedrive", None)
                st.success(f"OneDrive conectado con la cuenta {hecho['cuenta']}.")
                st.rerun()
        if c2.button("Cancelar", key="tx_cancelar_conexion"):
            st.session_state.pop("tx_flujo_onedrive", None)
            st.rerun()


def _formulario(user: dict) -> None:
    srv = servicio()
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
