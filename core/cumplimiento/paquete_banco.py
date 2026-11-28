"""
Paquete para el banco (fase 2, cierre).

Reúne con un clic lo que un aliado bancario suele pedir de un subcliente:
  - un resumen KYC en PDF (datos, actividades, riesgo, perfil declarado, personas vinculadas,
    contratos, operación de los últimos 6 meses y qué documentos se incluyen o faltan);
  - los documentos propios reconocidos en su carpeta de OneDrive (solo lectura).
Se entrega como un ZIP. Los documentos de beneficiarios NO se incluyen.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta

from sqlalchemy import Engine, text

from core.cumplimiento import clientes as cl
from core.cumplimiento import documentos as doc
from core.cumplimiento import vinculados as vin

MAX_BYTES = 80 * 1024 * 1024
MESES = 6


def _latin(s) -> str:
    """fpdf con fuentes base solo admite latin-1: se reemplazan los caracteres que no caben."""
    s = "" if s is None else str(s)
    s = s.replace("–", "-").replace("—", "-").replace("“", '"').replace("”", '"').replace("’", "'").replace("•", "-")
    return s.encode("latin-1", "replace").decode("latin-1")


def _moneda(v) -> str:
    return "-" if v is None else "$ " + f"{float(v):,.0f}".replace(",", ".")


def _archivo_seguro(nombre: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', " ", nombre).strip() or "archivo"


def _operacion(engine: Engine, cliente_id: int, hoy: date) -> dict:
    desde = (hoy.replace(day=1) - timedelta(days=31 * (MESES - 1))).replace(day=1)
    with engine.connect() as conn:
        f = conn.execute(text("""
            SELECT count(*) FILTER (WHERE t.exitosa) AS pagos, COALESCE(sum(t.monto) FILTER (WHERE t.exitosa), 0) AS monto,
                   count(DISTINCT t.id_beneficiario) FILTER (WHERE t.exitosa) AS beneficiarios,
                   count(DISTINCT date_trunc('month', t.fecha)) FILTER (WHERE t.exitosa) AS meses, min(t.fecha), max(t.fecha)
              FROM tx_transacciones t JOIN tx_empresas e ON e.nombre_reporte = t.cliente
             WHERE e.cliente_id = :c AND t.tipo_transaccion ILIKE 'd_bito%' AND t.fecha BETWEEN :d AND :h"""),
            {"c": cliente_id, "d": desde, "h": hoy}).mappings().first()
    return {"desde": desde, "hasta": hoy, **dict(f)}


def _pdf(ficha: dict, personas: list[dict], contratos: list[dict], operacion: dict, estado_docs: dict,
         incluidos: list[str], hoy: date) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 9, _latin(f"Resumen KYC - {ficha['razon_social']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _latin(f"Preparado por el oficial de cumplimiento de {ficha['organizacion']} el {hoy.isoformat()}. "
                          "Documento confidencial."), new_x="LMARGIN", new_y="NEXT")

    def titulo(t):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _latin(t), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)

    def fila(k, v):
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(55, 5, _latin(k))
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _latin(v if v not in (None, "", []) else "-"), new_x="LMARGIN", new_y="NEXT")

    titulo("Identificación")
    fila("Razón social", ficha["razon_social"])
    fila("NIT / identificación", ficha.get("nit"))
    fila("Tipo de persona", "Jurídica" if ficha.get("tipo_persona") != "natural" else "Natural")
    fila("País de constitución", ficha.get("pais_constitucion"))
    fila("Sitio web", ficha.get("sitio_web"))
    fila("Actividades (CIIU)", "; ".join(f"{a['codigo']} {a.get('descripcion') or ''}".strip() for a in ficha.get("actividades") or []))

    titulo("Cumplimiento")
    fila("Nivel de riesgo", ficha.get("nivel_riesgo") or "Sin calificar")
    fila("Última calificación", ficha.get("fecha_ultima_calificacion"))
    fila("Próxima revisión", ficha.get("proxima_revision"))
    fila("PEP / listas", f"PEP: {'sí' if ficha.get('es_pep') else 'no'} · En listas restrictivas: "
                         f"{'sí' if ficha.get('en_listas_restriccion') else 'no'}")

    titulo("Perfil transaccional declarado")
    fila("Volumen mensual", _moneda(ficha.get("perfil_volumen_mensual")))
    fila("Operaciones al mes", ficha.get("perfil_operaciones_mes"))
    fila("Ticket promedio", _moneda(ficha.get("perfil_ticket_promedio")))
    fila("Países", ", ".join(ficha.get("perfil_paises") or []))

    titulo(f"Operación real ({operacion['desde'].isoformat()} a {operacion['hasta'].isoformat()})")
    meses = max(operacion["meses"] or 0, 1)
    fila("Pagos exitosos", f"{operacion['pagos']} por {_moneda(operacion['monto'])} (promedio mensual {_moneda(float(operacion['monto']) / meses)})")
    fila("Beneficiarios distintos", operacion["beneficiarios"])

    titulo("Personas vinculadas")
    if not personas:
        pdf.cell(0, 5, _latin("Sin personas registradas."), new_x="LMARGIN", new_y="NEXT")
    for p in personas:
        pct = f" · {p['pct_participacion']:.2f} %" if p.get("pct_participacion") is not None else ""
        marcas = (" · PEP" if p["es_pep"] else "") + (" · EN LISTAS" if p["en_listas_restriccion"] else "")
        pdf.multi_cell(0, 5, _latin(f"- {p['rol']}: {p['nombre_completo']} ({p.get('tipo_documento') or ''} "
                                    f"{p.get('numero_documento') or ''}){pct}{marcas}"), new_x="LMARGIN", new_y="NEXT")

    titulo("Contratos")
    if not contratos:
        pdf.cell(0, 5, _latin("Sin contratos registrados."), new_x="LMARGIN", new_y="NEXT")
    for c in contratos:
        servicios = ", ".join(f"{x['servicio']} ({x['estado']})" for x in c.get("servicios") or [])
        pdf.multi_cell(0, 5, _latin(f"- {c.get('empresa_grupo')}: {c.get('estado') or 'sin estado'}"
                                    f"{' · firmado' if c.get('contrato_firmado') else ' · sin firmar'}"
                                    f"{' · vence ' + str(c['fecha_vencimiento']) if c.get('fecha_vencimiento') else ''}"
                                    f"{' · ' + servicios if servicios else ''}"), new_x="LMARGIN", new_y="NEXT")

    titulo("Documentos")
    for f in estado_docs["requisitos"]:
        pdf.cell(0, 5, _latin(f"[{'X' if f['cargado'] else ' '}] {f['nombre']}"), new_x="LMARGIN", new_y="NEXT")
    if incluidos:
        pdf.ln(1)
        pdf.multi_cell(0, 5, _latin("Archivos incluidos en este paquete: " + "; ".join(incluidos)), new_x="LMARGIN", new_y="NEXT")
    if estado_docs["faltan"]:
        pdf.multi_cell(0, 5, _latin("Pendientes: " + ", ".join(estado_docs["faltan"])), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def generar(engine: Engine, cliente_id: int, lector=None, hoy: date | None = None) -> tuple[str, bytes, dict]:
    hoy = hoy or date.today()
    ficha = cl.obtener(engine, cliente_id)
    if ficha is None:
        raise LookupError("El subcliente no existe.")
    with engine.connect() as conn:
        drive = conn.scalar(text("SELECT carpeta_drive_id FROM clientes WHERE id = :c"), {"c": cliente_id})
        archivos = [a for a in doc._archivos_bd(conn, cliente_id) if a["id_beneficiario"] is None and a["codigo"]]
        items = {f[0]: f[1] for f in conn.execute(text(
            "SELECT id, item_id FROM cmp_documentos WHERE cliente_id = :c AND id_beneficiario IS NULL"), {"c": cliente_id})}
    estado_docs = doc.estado_propio(engine, cliente_id)
    if archivos and not drive:
        raise doc.ErrorCarpeta("Revise primero la carpeta del subcliente para poder descargar sus documentos.")

    buffer = io.BytesIO()
    total = 0
    incluidos: list[str] = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        if archivos:
            lector = lector or doc.lector_configurado(engine)
            for a in archivos:
                contenido = lector.descargar(drive, items[a["id"]])
                total += len(contenido)
                if total > MAX_BYTES:
                    raise doc.ErrorCarpeta("Los documentos superan 80 MB: el paquete sería demasiado grande.")
                nombre = f"Documentos/{_archivo_seguro(doc.DOCUMENTOS.get(a['codigo'], a['codigo']))} - {_archivo_seguro(a['nombre_archivo'])}"
                z.writestr(nombre, contenido)
                incluidos.append(a["nombre_archivo"])
        resumen = _pdf(ficha, vin.listar_personas(engine, cliente_id), vin.listar_contratos(engine, cliente_id),
                       _operacion(engine, cliente_id, hoy), estado_docs, incluidos, hoy)
        z.writestr(f"00 Resumen KYC - {_archivo_seguro(ficha['razon_social'])}.pdf", resumen)
    nombre_zip = f"Paquete banco - {_archivo_seguro(ficha['razon_social'])} - {hoy.isoformat()}.zip"
    return nombre_zip, buffer.getvalue(), {"documentos": len(incluidos), "faltan": estado_docs["faltan"]}
