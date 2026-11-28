"""Carpeta Compliance de la organización (migración 048).

Lo que no puede fallar:
  - los nombres se reconocen sin importar mayúsculas, tildes, números de orden ni sufijos;
  - un subcliente sin carpeta se enlaza solo; uno con carpeta pegada a mano la conserva;
  - los documentos de cada aliado se reconocen y los exigidos dependen de si es regulado/colombiano;
  - los vencimientos generan avisos; las evidencias de cada requerimiento se cuentan;
  - «Enviado» sin respuesta en la carpeta queda señalado;
  - la carpeta «Requerimientos» del subcliente no se toma como documentación propia;
  - una organización no toca los datos de otra.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from core.cumplimiento import aliados as ali  # noqa: E402
from core.cumplimiento import carpeta_compliance as cc  # noqa: E402
from core.cumplimiento import clientes as cl  # noqa: E402
from core.cumplimiento import documentos as dc  # noqa: E402
from core.cumplimiento import requerimientos as rq  # noqa: E402

HOY = date.today()


def test_nombres():
    assert cc.clave("02 - Aliados Bancarios") == "aliados bancarios"
    assert cc.coincide("CM GRUPO TECNO S.A.S.", "CM Grupo Tecno")
    assert cc.coincide("Cobre", "PEXTO COLOMBIA S.A.S. - Cobre")
    assert not cc.coincide("CM Group", "CM Grupo Tecno")
    assert not cc.coincide("Pa", "Paxum")
    assert cc.es_carpeta_aliados("Aliados bancarios") and cc.es_carpeta_aliados("1. Banking partners")
    assert cc.es_carpeta_requerimientos("03. Requerimientos")
    assert cc.consecutivo_de("REQ-2026-7 - KYC Paxum") == "REQ-2026-007"
    assert cc.consecutivo_de("req_2026_012") == "REQ-2026-012" and cc.consecutivo_de("Otra cosa") is None
    assert [cc.parte_evidencia(n) for n in ("1. Solicitud", "2. Soportes", "3. Respuesta", "Notas")] == ["solicitud", "soportes", "respuesta", None]


def test_reconocer_documentos_de_aliado():
    casos = {"Contrato marco Cobre 2025.pdf": "contrato", "Poliza de cumplimiento.pdf": "poliza",
             "Licencia SFC.pdf": "licencia", "Cuestionario AML Wolfsberg.pdf": "aml", "Certificacion SARLAFT.pdf": "aml",
             "Estados financieros 2024.pdf": "estados_financieros", "Camara de comercio.pdf": "certificado_existencia",
             "RUT Cobre.pdf": "rut", "foto.png": None}
    for nombre, codigo in casos.items():
        assert cc.reconocer_aliado(nombre) == codigo, nombre
    exigidos = lambda r: {f["codigo"] for f in cc.requisitos_aliado(r) if f["exigido"]}  # noqa: E731
    assert exigidos({"pais": "Colombia", "regulado": True}) == {"contrato", "aml", "certificado_existencia", "rut", "licencia"}
    assert exigidos({"pais": "Estados Unidos", "regulado": False}) == {"contrato", "aml", "certificado_existencia"}


class Lector:
    def __init__(self, arbol):
        self.arbol = arbol

    def resolver(self, enlace):
        return {"drive_id": "d1", "item_id": "raiz", "nombre": "Compliance"}

    def hijos(self, drive, item_id):
        return self.arbol.get(item_id, [])


def _c(i, n):
    return {"id": i, "name": n, "folder": {}, "webUrl": f"https://x.sharepoint.com/{i}"}


def _a(i, n):
    return {"id": i, "name": n, "file": {}, "size": 10, "webUrl": f"https://x.sharepoint.com/{i}",
            "lastModifiedDateTime": "2026-11-20T10:00:00Z"}


@pytest.fixture
def pg():
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    from sqlalchemy import create_engine, text
    from tests._esquema import crear_esquema_minimo, id_adamo
    engine = create_engine(url)
    crear_esquema_minimo(engine)
    adamo = id_adamo(engine)
    with engine.begin() as c:
        paycop = c.execute(text("INSERT INTO organizaciones (nombre) VALUES ('Paycop') RETURNING id")).scalar_one()
    x = {"adamo": adamo, "paycop": paycop,
         "tecno": cl.crear(engine, adamo, {"razon_social": "CM Grupo Tecno S.A.S.", "nivel_riesgo": "Medio"}, "j"),
         "paxum": cl.crear(engine, adamo, {"razon_social": "Paxum", "nit": "900111", "nivel_riesgo": "Medio"}, "j"),
         "cobre": ali.crear(engine, adamo, {"nombre": "PEXTO COLOMBIA S.A.S. - Cobre", "estado": "activo", "pais": "Colombia"}, "j"),
         "iris": ali.crear(engine, adamo, {"nombre": "Iris", "estado": "activo"}, "j"),
         "ajeno": ali.crear(engine, paycop, {"nombre": "Finity", "estado": "activo"}, "j")}
    # Paxum ya tenía su carpeta pegada a mano
    cl.actualizar(engine, x["paxum"], {"carpeta_onedrive": "https://x.sharepoint.com/manual-paxum"}, "j")
    x["req_org"] = rq.crear(engine, adamo, {"dirigido_a": "organizacion", "origen": "aliado", "relacion_aliado_id": x["cobre"],
                                           "tipo": "recertificacion_aml", "asunto": "Recertificación AML anual",
                                           "fecha_recibido": HOY}, "j")
    x["req_cli"] = rq.crear(engine, adamo, {"dirigido_a": "cliente", "cliente_id": x["tecno"], "origen": "oficial",
                                           "tipo": "kyc_kyb", "asunto": "KYC actualizado de CM", "fecha_recibido": HOY}, "j")
    yield engine, x
    engine.dispose()


def _arbol():
    return {
        "raiz": [_c("f-tecno", "CM GRUPO TECNO"), _c("f-paxum", "Paxum"), _c("f-ali", "02. Aliados bancarios"),
                 _c("f-req", "Requerimientos"), _c("f-otra", "Plantillas"), _a("suelto", "nota.txt")],
        "f-tecno": [_c("t-doc", "Documentación corporativa"), _c("t-req", "Requerimientos")],
        "t-doc": [_a("t1", "Certificado de existencia.pdf"), _a("t2", "RUT.pdf")],
        "t-req": [_c("t-req1", "REQ-2026-002 - KYC actualizado")],
        "t-req1": [_c("t-s", "1. Solicitud"), _c("t-r", "3. Respuesta")],
        "t-s": [_a("ts1", "correo banco.pdf")], "t-r": [],
        "f-ali": [_c("a-cobre", "Cobre"), _c("a-nadie", "Banco Fantasma")],
        "a-cobre": [_a("c1", "Contrato Cobre.pdf"), _a("c2", "Cuestionario AML.pdf"), _a("c3", "Camara de comercio.pdf"),
                    _a("c4", "Anexo sin nombre.pdf")],
        "f-req": [_c("r1", "REQ-2026-001 - Recertificación AML"), _c("r9", "REQ-2026-099 - Huérfano")],
        "r1": [_c("r1s", "Solicitud"), _c("r1p", "Soportes"), _c("r1r", "Respuesta"), _a("r1x", "suelto.pdf")],
        "r1s": [_a("r1s1", "a.pdf")], "r1p": [_a("r1p1", "b.pdf"), _a("r1p2", "c.pdf")], "r1r": [_a("r1r1", "d.pdf")],
    }


def test_revision_completa(pg):
    engine, x = pg
    cc.guardar_enlace(engine, x["adamo"], "https://x.sharepoint.com/compliance")
    res = cc.revisar_organizacion(engine, x["adamo"], Lector(_arbol()))
    subs = {s["subcliente"]: s for s in res["subclientes"]}
    assert subs["CM Grupo Tecno S.A.S."]["enlace"] == "compliance" and subs["Paxum"]["enlace"] == "manual"
    assert res["carpetas_sin_subcliente"] == ["Plantillas"] and res["carpetas_sin_aliado"] == ["Banco Fantasma"]
    assert res["aliados_sin_carpeta"] == ["Iris"] and res["requerimientos"] == 2
    assert res["carpetas_req_sin_coincidir"] == ["REQ-2026-099 - Huérfano"]
    # CM Grupo Tecno quedó enlazado y sus documentos se leyeron, sin tomar la carpeta Requerimientos
    with engine.connect() as conn:
        from sqlalchemy import text
        origen, url = conn.execute(text("SELECT carpeta_origen, carpeta_onedrive FROM clientes WHERE id = :c"), {"c": x["tecno"]}).one()
        paxum_url = conn.execute(text("SELECT carpeta_onedrive FROM clientes WHERE id = :c"), {"c": x["paxum"]}).scalar()
        rutas = list(conn.scalars(text("SELECT ruta FROM cmp_documentos WHERE cliente_id = :c"), {"c": x["tecno"]}))
    assert origen == "compliance" and url.endswith("f-tecno") and paxum_url.endswith("manual-paxum")
    assert sorted(rutas) == ["Documentación corporativa/Certificado de existencia.pdf", "Documentación corporativa/RUT.pdf"]
    # Documentos del aliado
    a = ali.obtener(engine, x["adamo"], x["cobre"])
    cargados = {f["codigo"] for f in a["documentos"]["filas"] if f["cargado"]}
    assert cargados == {"contrato", "aml", "certificado_existencia"}
    assert [d["nombre_archivo"] for d in a["documentos"]["sin_reconocer"]] == ["Anexo sin nombre.pdf"]
    assert any("Faltan documentos: RUT" in v["texto"] for v in a["avisos"])
    # Evidencias
    q1 = rq.obtener(engine, x["adamo"], x["req_org"]["id"])
    assert (q1["ev_solicitud"], q1["ev_soportes"], q1["ev_respuesta"]) == (1, 3, 1)
    q2 = rq.obtener(engine, x["adamo"], x["req_cli"]["id"])
    assert (q2["ev_solicitud"], q2["ev_respuesta"]) == (1, 0)
    rq.cambiar_estado(engine, x["adamo"], x["req_cli"]["id"], "enviado", "j", resumen_respuesta="Se envió el KYC completo")
    assert rq.obtener(engine, x["adamo"], x["req_cli"]["id"])["sin_evidencia_respuesta"]
    assert rq.listar(engine, x["adamo"])["resumen"]["sin_evidencia_respuesta"] == 1
    # Asignar a mano un archivo no reconocido, y que la siguiente revisión lo respete
    cc.asignar_documento_aliado(engine, x["adamo"], a["documentos"]["sin_reconocer"][0]["id"], "rut", "j")
    cc.revisar_organizacion(engine, x["adamo"], Lector(_arbol()))
    assert ali.obtener(engine, x["adamo"], x["cobre"])["documentos"]["completo"]
    with pytest.raises(LookupError):
        cc.asignar_documento_aliado(engine, x["paycop"], a["documentos"]["filas"][0]["archivos"][0]["id"], "rut", "j")
    # La carpeta desaparece: se sueltan el enlace automático y los documentos del aliado
    arbol = _arbol()
    arbol["raiz"] = [h for h in arbol["raiz"] if h["id"] not in ("f-tecno", "f-ali")]
    cc.revisar_organizacion(engine, x["adamo"], Lector(arbol))
    assert ali.obtener(engine, x["adamo"], x["cobre"])["documentos"]["carpeta"] is False
    with engine.connect() as conn:
        assert conn.execute(text("SELECT carpeta_onedrive FROM clientes WHERE id = :c"), {"c": x["tecno"]}).scalar() is None
    # El aliado de otra organización no se tocó
    assert ali.obtener(engine, x["paycop"], x["ajeno"])["documentos"]["carpeta"] is False


def test_vencimientos_y_errores(pg):
    engine, x = pg
    ali.actualizar(engine, x["adamo"], x["cobre"], {}, {"vence_contrato": HOY - timedelta(days=1),
                                                       "vence_poliza": HOY + timedelta(days=10)})
    a = ali.obtener(engine, x["adamo"], x["cobre"])
    textos = [v["texto"] for v in a["avisos"]]
    assert "Contrato: venció el " + str(HOY - timedelta(days=1)) in textos and any(t.startswith("Póliza: vence el") for t in textos)
    r = ali.listar(engine, x["adamo"])["resumen"]
    assert r["documentos_vencidos"] == 1 and r["documentos_por_vencer"] == 1
    with pytest.raises(dc.ErrorCarpeta):
        cc.guardar_enlace(engine, x["adamo"], "https://google.com/carpeta")
    with pytest.raises(dc.ErrorCarpeta):
        cc.revisar_organizacion(engine, x["adamo"], Lector({}))                       # sin enlace

    class Roto(Lector):
        def resolver(self, enlace):
            raise dc.ErrorCarpeta("La cuenta conectada a OneDrive no tiene acceso a esa carpeta.")
    cc.guardar_enlace(engine, x["adamo"], "https://x.sharepoint.com/compliance")
    with pytest.raises(dc.ErrorCarpeta):
        cc.revisar_organizacion(engine, x["adamo"], Roto({}))
    assert "no tiene acceso" in cc.estado(engine, x["adamo"])["carpeta_error"]


# ---------- Requerimientos sugeridos ----------
def test_sugerencias(pg):
    from core.cumplimiento import sugerencias as sg
    engine, x = pg
    cc.guardar_enlace(engine, x["adamo"], "https://x.sharepoint.com/compliance")
    cc.revisar_organizacion(engine, x["adamo"], Lector(_arbol()))
    ali.actualizar(engine, x["adamo"], x["cobre"], {}, {"vence_contrato": HOY - timedelta(days=3)})
    ali.cambiar(engine, x["adamo"], x["iris"], {"proxima_revision": HOY - timedelta(days=1), "motivo": "Revisión anual programada"}, "j")
    claves = {s["clave"]: s for s in sg.sugerir(engine, x["adamo"])}
    assert f"docs:{x['tecno']}" in claves and "Composición accionaria" in claves[f"docs:{x['tecno']}"]["motivo"]
    assert f"vence:{x['cobre']}:contrato:{HOY - timedelta(days=3)}" in claves
    assert f"revision:{x['iris']}:{HOY - timedelta(days=1)}" in claves
    assert f"docsaliado:{x['cobre']}" in claves
    assert sg.sugerir(engine, x["paycop"]) == []                                   # nada de otra organización
    clave = f"docs:{x['tecno']}"
    r = sg.crear_desde_sugerencia(engine, x["adamo"], clave, "jorge")
    q = rq.obtener(engine, x["adamo"], r["id"])
    assert q["clave_origen"] == clave and q["cliente_id"] == x["tecno"] and q["origen"] == "oficial"
    assert q["fecha_limite"] == HOY + timedelta(days=sg.PLAZO_DIAS)
    assert clave not in {s["clave"] for s in sg.sugerir(engine, x["adamo"])}         # no se repite
    with pytest.raises(LookupError):
        sg.crear_desde_sugerencia(engine, x["adamo"], clave, "jorge")


# ---------- Paquete para el banco ----------
def test_paquete_banco(pg):
    import io
    import zipfile
    from core.cumplimiento import paquete_banco as pb
    from core.cumplimiento import vinculados as vin
    engine, x = pg

    class LectorConContenido(Lector):
        def descargar(self, drive, item_id):
            return f"contenido de {item_id}".encode()

    cc.guardar_enlace(engine, x["adamo"], "https://x.sharepoint.com/compliance")
    cc.revisar_organizacion(engine, x["adamo"], Lector(_arbol()))
    vin.crear_persona(engine, x["tecno"], {"nombre_completo": "María Pérez Ñuñez", "rol": "Representante Legal",
                                           "tipo_documento": "CC", "numero_documento": "52111222"}, "j")
    nombre, contenido, info = pb.generar(engine, x["tecno"], LectorConContenido(_arbol()))
    z = zipfile.ZipFile(io.BytesIO(contenido))
    nombres = sorted(z.namelist())
    assert nombres[0].startswith("00 Resumen KYC - CM Grupo Tecno") and nombres[0].endswith(".pdf")
    assert z.read(nombres[0]).startswith(b"%PDF")
    assert any(n.startswith("Documentos/RUT - RUT.pdf") for n in nombres) and len(nombres) == 3
    assert info["documentos"] == 2 and "Composición accionaria" in info["faltan"]
    assert nombre.startswith("Paquete banco - CM Grupo Tecno")
    # Sin carpeta: igual sale el resumen
    sin = cl.crear(engine, x["adamo"], {"razon_social": "Sin Carpeta", "nit": "900444", "nivel_riesgo": "Bajo"}, "j")
    nombre2, contenido2, info2 = pb.generar(engine, sin, LectorConContenido({}))
    assert info2["documentos"] == 0 and len(zipfile.ZipFile(io.BytesIO(contenido2)).namelist()) == 1
