"""
Clientes de una organización y su compliance (expediente 360, alertas y casos).

SOLO equipo interno de cumplimiento. Separación de responsabilidades (2026-11-23):
  - Las alertas, los casos, la calificación de riesgo y los posibles ROS son de uso interno.
  - El equipo del cliente (Adamo) solo ve su operación (Monitoreo); nunca esta sección.
  - Los clientes de los clientes (CM Grupo Tecno…) no tienen acceso a la plataforma.
"""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from api import seguridad as seg
from core.cumplimiento import alertas as al
from core.cumplimiento import beneficiarios as bf
from core.cumplimiento import documentos as dc
from core.cumplimiento import catalogo as cat
from core.cumplimiento import clientes as cl
from core.cumplimiento import vinculados as vc
from core.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO

router = APIRouter(tags=["clientes y alertas"])
interno = seg.requiere_roles(ROLES_MONITOREO)
gestion = seg.requiere_roles(ROLES_CARGA)


def _engine():
    from db.database import engine
    return engine


def _json(v):
    return json.loads(json.dumps(v, default=lambda x: x.isoformat() if hasattr(x, "isoformat") else float(x)))


def _kpis(k):
    return None if k is None else {**k.__dict__, "tasa_devolucion": k.tasa_devolucion}


def _existe_organizacion(organizacion_id: int) -> None:
    with _engine().connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM organizaciones WHERE id = :id"), {"id": organizacion_id}):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "La organización no existe.")


def _cliente(cliente_id: int) -> dict:
    f = cl.obtener(_engine(), cliente_id)
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El cliente no existe.")
    return f


# =========================
# Clientes de la organización
# =========================
@router.get("/api/organizaciones/{organizacion_id}/clientes")
def listar_clientes(organizacion_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _existe_organizacion(organizacion_id)
    return _json({"clientes": cl.listar(_engine(), organizacion_id),
                  "empresas_sin_cliente": cl.empresas_sin_cliente(_engine(), organizacion_id)})


class DesdeEmpresas(BaseModel):
    empresa_ids: list[int] = Field(min_length=1, max_length=500)


@router.post("/api/organizaciones/{organizacion_id}/clientes/desde-empresas", status_code=201)
def crear_desde_empresas(organizacion_id: int, datos: DesdeEmpresas, request: Request,
                         u: seg.Usuario = Depends(gestion)) -> dict:
    _existe_organizacion(organizacion_id)
    try:
        creados = cl.crear_desde_empresas(_engine(), organizacion_id, datos.empresa_ids, u.username)
    except cl.ErrorCliente as e:
        raise HTTPException(400, str(e))
    seg.auditar(u, "CREATE", "clientes",
                f"{len(creados)} clientes creados desde empresas monitoreadas (organización {organizacion_id})",
                ip=seg.ip_cliente(request), valores_nuevos={"creados": creados})
    return {"creados": creados}


@router.get("/api/clientes/{cliente_id}")
def ficha_cliente(cliente_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    f = _cliente(cliente_id)
    r = cl.resumen_operacion(_engine(), cliente_id)
    nivel = f["nivel_riesgo"] if f["nivel_riesgo"] in cat.NIVELES else (cat.riesgo_sugerido(f["modelos_negocio"]) or "Alto")
    try:
        paquete = [{"codigo": x.documento.codigo, "nombre": x.documento.nombre, "carpeta": x.documento.carpeta,
                    "aporta": x.documento.aporta, "vigencia_meses": x.vigencia_meses, "nota": x.documento.nota,
                    "origen": list(x.origen)}
                   for x in cat.requisitos(f["modelos_negocio"], nivel, f["tipo_persona"])]
    except ValueError:
        paquete = []
    alertas = al.listar(_engine(), f["organizacion_id"], cliente_id=cliente_id)
    abiertas = [a for a in alertas if a["estado"] in al.ABIERTAS]
    return _json({
        **f, "riesgo_sugerido": cat.riesgo_sugerido(f["modelos_negocio"]),
        "operacion": {"desde": r["desde"], "hasta": r["hasta"], "kpis": _kpis(r["kpis"]),
                      "ultima_operacion": r["ultima_operacion"]},
        "alertas_resumen": {"abiertas": len(abiertas), "total": len(alertas),
                            "por_prioridad": {p: sum(1 for a in abiertas if a["prioridad"] == p)
                                              for p in ("Crítica", "Alta", "Media", "Baja")},
                            "posible_ros": sum(1 for a in alertas if a["estado"] == "posible_ros")},
        "paquete": {"nivel": nivel, "nivel_es_provisional": f["nivel_riesgo"] not in cat.NIVELES, "documentos": paquete},
    })


class CambioCliente(BaseModel):
    razon_social: str | None = Field(None, max_length=200)
    nit: str | None = Field(None, max_length=30)
    tipo_persona: str | None = None
    modelos_negocio: list[str] | None = Field(None, max_length=30)
    actividades_ciiu: list[str] | None = Field(None, max_length=4)
    nivel_riesgo: str | None = None
    estado: str | None = None
    sector_ciiu: str | None = Field(None, max_length=120)
    pais_constitucion: str | None = Field(None, max_length=80)
    sitio_web: str | None = Field(None, max_length=200)
    proxima_revision: date | None = None
    perfil_volumen_mensual: float | None = Field(None, ge=0)
    perfil_operaciones_mes: int | None = Field(None, ge=0)
    perfil_ticket_promedio: float | None = Field(None, ge=0)
    perfil_paises: list[str] | None = Field(None, max_length=50)
    notas: str | None = Field(None, max_length=2000)
    carpeta_onedrive: str | None = Field(None, max_length=1000)


class NuevoCliente(CambioCliente):
    razon_social: str = Field(min_length=2, max_length=200)


def _conflicto_nit(e: Exception) -> None:
    if "uq_clientes_organizacion_nit" in str(e):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un cliente con ese NIT en la organización.")


def _resumen_ciiu(cambios: dict) -> str:
    partes = []
    if "actividades_ciiu" in cambios:
        partes.append("CIIU: " + (", ".join(cambios["actividades_ciiu"] or []) or "ninguna"))
    if "modelos_negocio" in cambios:
        partes.append("modelos: " + (", ".join(cambios["modelos_negocio"] or []) or "ninguno"))
    return f" ({'; '.join(partes)})" if partes else ""


@router.post("/api/organizaciones/{organizacion_id}/clientes", status_code=201)
def crear_cliente(organizacion_id: int, datos: NuevoCliente, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    """Alta manual: el equipo diligencia la ficha (RUT, actividades, modelos, riesgo) al crear el cliente."""
    _existe_organizacion(organizacion_id)
    cambios = datos.model_dump(exclude_unset=True)
    try:
        cid = cl.crear(_engine(), organizacion_id, cambios, u.username)
    except cl.ErrorCliente as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        _conflicto_nit(e)
        raise
    seg.auditar(u, "CREATE", "clientes", f"Cliente «{cambios['razon_social'].strip()}» creado a mano por {u.username}"
                f"{_resumen_ciiu(cambios)}", entidad_id=cid, ip=seg.ip_cliente(request), valores_nuevos=_json(cambios))
    return {"id": cid}


@router.patch("/api/clientes/{cliente_id}")
def cambiar_cliente(cliente_id: int, datos: CambioCliente, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    antes = _cliente(cliente_id)
    cambios = datos.model_dump(exclude_unset=True)
    try:
        cl.actualizar(_engine(), cliente_id, cambios, u.username)
    except cl.ErrorCliente as e:
        raise HTTPException(400, str(e))
    except Exception as e:                      # NIT repetido dentro de la organización
        _conflicto_nit(e)
        raise
    seg.auditar(u, "UPDATE", "clientes", f"Cliente «{antes['razon_social']}» actualizado por {u.username}"
                f"{_resumen_ciiu(cambios)}",
                entidad_id=cliente_id, ip=seg.ip_cliente(request), valores_nuevos=_json(cambios))
    return {"ok": True}


@router.get("/api/clientes/{cliente_id}/perfil")
def perfil(cliente_id: int, meses: int = Query(6, ge=1, le=24), u: seg.Usuario = Depends(interno)) -> dict:
    _cliente(cliente_id)
    return _json(cl.perfil_vs_real(_engine(), cliente_id, meses))


# =========================
# Beneficiarios (a quién le paga el cliente)
# =========================
@router.get("/api/clientes/{cliente_id}/beneficiarios")
def beneficiarios(cliente_id: int, desde: date | None = None, hasta: date | None = None,
                  u: seg.Usuario = Depends(interno)) -> dict:
    _cliente(cliente_id)
    return _json(bf.listar(_engine(), cliente_id, desde, hasta))


@router.get("/api/clientes/{cliente_id}/beneficiarios/{id_beneficiario}/movimientos")
def movimientos_beneficiario(cliente_id: int, id_beneficiario: str, u: seg.Usuario = Depends(interno)) -> dict:
    _cliente(cliente_id)
    if not id_beneficiario.strip() or len(id_beneficiario) > 40:
        raise HTTPException(400, "Identificación no válida.")
    return _json({"movimientos": bf.movimientos_de(_engine(), cliente_id, id_beneficiario)})


# =========================
# Documentación en OneDrive (propia y de beneficiarios)
# =========================
@router.get("/api/clientes/{cliente_id}/documentacion")
def documentacion(cliente_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _cliente(cliente_id)
    return _json(dc.estado_propio(_engine(), cliente_id))


@router.post("/api/clientes/{cliente_id}/documentacion/revisar")
def revisar_carpeta(cliente_id: int, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    """Lee ahora la carpeta del cliente en OneDrive (también ocurre tras cada sincronización)."""
    f = _cliente(cliente_id)
    try:
        r = dc.revisar(_engine(), cliente_id, usuario=u.username)
    except dc.ErrorCarpeta as e:
        raise HTTPException(400, str(e))
    seg.auditar(u, "READ", "clientes", f"Carpeta de OneDrive de «{f['razon_social']}» revisada: "
                f"{r['archivos_propios']} archivos propios, {r['carpetas_beneficiarios']} carpetas de beneficiarios",
                entidad_id=cliente_id, ip=seg.ip_cliente(request))
    return r


class Asignacion(BaseModel):
    codigo: str | None = Field(None, max_length=40)


@router.patch("/api/documentos/{documento_id}")
def asignar_documento(documento_id: int, datos: Asignacion, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    try:
        f = dc.asignar(_engine(), documento_id, datos.codigo, u.username)
    except dc.ErrorCarpeta as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    nombre = dc.DOCUMENTOS.get(datos.codigo or "", "sin tipo")
    seg.auditar(u, "UPDATE", "clientes", f"Archivo «{f['nombre_archivo']}» asignado como {nombre}",
                entidad_id=f["cliente_id"], ip=seg.ip_cliente(request))
    return {"ok": True}


@router.get("/api/clientes/{cliente_id}/expedientes-beneficiarios")
def expedientes_beneficiarios(cliente_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _cliente(cliente_id)
    return _json(dc.expedientes_beneficiarios(_engine(), cliente_id))


class NuevoExpediente(BaseModel):
    id_beneficiario: str = Field(min_length=1, max_length=40)


@router.post("/api/clientes/{cliente_id}/expedientes-beneficiarios", status_code=201)
def abrir_expediente(cliente_id: int, datos: NuevoExpediente, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    f = _cliente(cliente_id)
    try:
        dc.abrir_expediente(_engine(), cliente_id, datos.id_beneficiario.strip(), u.username)
    except dc.ErrorCarpeta as e:
        raise HTTPException(400, str(e))
    seg.auditar(u, "CREATE", "clientes", f"Expediente del beneficiario {datos.id_beneficiario} abierto "
                f"(cliente «{f['razon_social']}»)", entidad_id=cliente_id, ip=seg.ip_cliente(request))
    return {"ok": True}


@router.delete("/api/clientes/{cliente_id}/expedientes-beneficiarios/{id_beneficiario}")
def cerrar_expediente(cliente_id: int, id_beneficiario: str, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    f = _cliente(cliente_id)
    if not dc.cerrar_expediente(_engine(), cliente_id, id_beneficiario):
        raise HTTPException(404, "Ese beneficiario no tiene expediente.")
    seg.auditar(u, "UPDATE", "clientes", f"Expediente del beneficiario {id_beneficiario} cerrado "
                f"(cliente «{f['razon_social']}»)", entidad_id=cliente_id, ip=seg.ip_cliente(request))
    return {"ok": True}


# =========================
# Personas vinculadas, contratos y calificación de riesgo (migrados de la app anterior)
# =========================
class Persona(BaseModel):
    nombre_completo: str | None = Field(None, max_length=200)
    tipo_documento: str | None = Field(None, max_length=20)
    numero_documento: str | None = Field(None, max_length=40)
    nacionalidad: str | None = Field(None, max_length=80)
    rol: str | None = Field(None, max_length=40)
    pct_participacion: float | None = None
    es_pep: bool | None = None
    en_listas_restriccion: bool | None = None
    fecha_verificacion: date | None = None
    notas: str | None = Field(None, max_length=2000)
    activo: bool | None = None


def _vinculado(fn):
    try:
        return fn()
    except vc.ErrorVinculado as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/api/clientes/{cliente_id}/personas")
def personas(cliente_id: int, todas: bool = False, u: seg.Usuario = Depends(interno)) -> dict:
    _cliente(cliente_id)
    lista = vc.listar_personas(_engine(), cliente_id, todas)
    return _json({"personas": lista, "resumen": vc.resumen_personas(lista), "roles": vc.ROLES_PERSONA,
                  "tipos_documento": vc.TIPOS_DOCUMENTO})


@router.post("/api/clientes/{cliente_id}/personas", status_code=201)
def crear_persona(cliente_id: int, datos: Persona, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    f = _cliente(cliente_id)
    d = datos.model_dump(exclude_unset=True)
    pid = _vinculado(lambda: vc.crear_persona(_engine(), cliente_id, d, u.username))
    seg.auditar(u, "CREATE", "clientes", f"Persona vinculada «{d.get('nombre_completo')}» ({d.get('rol')}) agregada a "
                f"«{f['razon_social']}»", entidad_id=cliente_id, ip=seg.ip_cliente(request), valores_nuevos=_json(d))
    return {"id": pid}


@router.patch("/api/clientes/{cliente_id}/personas/{persona_id}")
def cambiar_persona(cliente_id: int, persona_id: int, datos: Persona, request: Request,
                    u: seg.Usuario = Depends(gestion)) -> dict:
    _cliente(cliente_id)
    d = datos.model_dump(exclude_unset=True)
    r = _vinculado(lambda: vc.actualizar_persona(_engine(), cliente_id, persona_id, d))
    accion = "retirada" if d.get("activo") is False else "reactivada" if d.get("activo") else "actualizada"
    seg.auditar(u, "UPDATE", "clientes", f"Persona vinculada «{r['nombre']}» {accion}", entidad_id=cliente_id,
                ip=seg.ip_cliente(request), valores_nuevos=_json(d))
    return {"ok": True}


class Contrato(BaseModel):
    empresa_grupo: str = Field(max_length=40)
    estado: str | None = None
    fecha_inicio: date | None = None
    fecha_vencimiento: date | None = None
    contrato_firmado: bool | None = None
    fecha_firma: date | None = None
    numero_contrato: str | None = Field(None, max_length=60)
    contacto_operativo: str | None = Field(None, max_length=120)
    email_operativo: str | None = Field(None, max_length=120)
    telefono_operativo: str | None = Field(None, max_length=40)
    contacto_compliance: str | None = Field(None, max_length=120)
    email_compliance: str | None = Field(None, max_length=120)
    sla_contratado: str | None = Field(None, max_length=200)
    volumen_mensual_cop: int | None = None
    num_transacciones_mes: int | None = None
    notas: str | None = Field(None, max_length=2000)
    servicios: list[str] | None = Field(None, max_length=10)


@router.get("/api/clientes/{cliente_id}/contratos")
def contratos(cliente_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _cliente(cliente_id)
    return _json({"contratos": vc.listar_contratos(_engine(), cliente_id), "empresas": vc.EMPRESAS_GRUPO,
                  "estados": vc.ESTADOS_CONTRATO, "servicios": vc.SERVICIOS})


@router.post("/api/clientes/{cliente_id}/contratos")
def guardar_contrato(cliente_id: int, datos: Contrato, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    f = _cliente(cliente_id)
    d = datos.model_dump(exclude_unset=True)
    empresa = d.pop("empresa_grupo")
    cid = _vinculado(lambda: vc.guardar_contrato(_engine(), cliente_id, empresa, d, u.username))
    seg.auditar(u, "UPDATE", "clientes", f"Contrato con {empresa} de «{f['razon_social']}» actualizado"
                + (f" (servicios: {', '.join(d['servicios']) or 'ninguno'})" if "servicios" in d else ""),
                entidad_id=cliente_id, ip=seg.ip_cliente(request), valores_nuevos=_json(d))
    return {"id": cid}


class Calificacion(BaseModel):
    nivel: str
    puntaje: int | None = Field(None, ge=0, le=100)
    motivo: str = Field(max_length=1000)
    observaciones: str | None = Field(None, max_length=2000)
    proxima_revision: date | None = None


@router.get("/api/clientes/{cliente_id}/riesgo")
def riesgo(cliente_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    f = _cliente(cliente_id)
    return _json({"nivel_actual": f["nivel_riesgo"], "puntaje_actual": f.get("puntaje_riesgo"),
                  "fecha_ultima_calificacion": f.get("fecha_ultima_calificacion"), "proxima_revision": f.get("proxima_revision"),
                  "riesgo_sugerido": f.get("riesgo_sugerido"), "niveles": vc.NIVELES,
                  "historial": vc.historial_riesgo(_engine(), cliente_id)})


@router.post("/api/clientes/{cliente_id}/riesgo", status_code=201)
def calificar(cliente_id: int, datos: Calificacion, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    f = _cliente(cliente_id)
    _vinculado(lambda: vc.calificar(_engine(), cliente_id, datos.nivel, datos.puntaje, datos.motivo,
                                    datos.observaciones, u.username, datos.proxima_revision))
    seg.auditar(u, "UPDATE", "clientes", f"Riesgo de «{f['razon_social']}» calificado: {f['nivel_riesgo']} → {datos.nivel}"
                f"{f' (puntaje {datos.puntaje})' if datos.puntaje is not None else ''}. Motivo: {datos.motivo.strip()}",
                entidad_id=cliente_id, ip=seg.ip_cliente(request))
    return {"ok": True}


@router.get("/api/clientes/{cliente_id}/documentos-anteriores")
def documentos_anteriores(cliente_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _cliente(cliente_id)
    return _json({"documentos": vc.documentos_anteriores(_engine(), cliente_id)})


# =========================
# Alertas y casos
# =========================
@router.get("/api/organizaciones/{organizacion_id}/alertas")
def alertas_organizacion(organizacion_id: int, estado: list[str] | None = Query(None),
                         u: seg.Usuario = Depends(interno)) -> dict:
    _existe_organizacion(organizacion_id)
    return _json({"alertas": al.listar(_engine(), organizacion_id, estados=estado)})


@router.get("/api/clientes/{cliente_id}/alertas")
def alertas_cliente(cliente_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    f = _cliente(cliente_id)
    return _json({"alertas": al.listar(_engine(), f["organizacion_id"], cliente_id=cliente_id)})


class Evaluar(BaseModel):
    meses: int = Field(3, ge=1, le=12)


@router.post("/api/organizaciones/{organizacion_id}/alertas/evaluar")
def evaluar(organizacion_id: int, datos: Evaluar, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    """Reevalúa ahora las empresas de la organización (lo mismo que ocurre tras cada carga)."""
    _existe_organizacion(organizacion_id)
    with _engine().connect() as conn:
        ids = list(conn.scalars(text("SELECT id FROM tx_empresas WHERE organizacion_id = :o AND activa"),
                                {"o": organizacion_id}))
    r = al.evaluar(_engine(), ids, meses=datos.meses, usuario=u.username)
    seg.auditar(u, "CREATE", "cmp_alertas", f"Evaluación de alertas (organización {organizacion_id}): "
                f"{r.nuevas} nuevas, {r.actualizadas} actualizadas", ip=seg.ip_cliente(request))
    return r.to_dict()


@router.get("/api/alertas/analistas")
def analistas(u: seg.Usuario = Depends(interno)) -> dict:
    with _engine().connect() as conn:
        filas = conn.execute(text("SELECT id, nombre_completo FROM usuarios WHERE activo = 1 AND organizacion_id IS NULL "
                                  "AND rol IN ('super_admin', 'admin', 'compliance') ORDER BY nombre_completo")).mappings()
        return {"analistas": [{"id": f["id"], "nombre": f["nombre_completo"]} for f in filas]}


@router.get("/api/alertas/{alerta_id}")
def alerta(alerta_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    a = al.obtener(_engine(), alerta_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La alerta no existe.")
    return _json({**a, "eventos": al.eventos(_engine(), alerta_id),
                  "transiciones": sorted(al.TRANSICIONES[a["estado"]])})


class Gestion(BaseModel):
    estado: str | None = None
    justificacion: str | None = Field(None, max_length=4000)
    analista_id: int | None = None
    quitar_analista: bool = False
    nota: str | None = Field(None, max_length=4000)


@router.patch("/api/alertas/{alerta_id}")
def gestionar(alerta_id: int, datos: Gestion, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    try:
        a = al.gestionar(_engine(), alerta_id, u.username, estado=datos.estado, justificacion=datos.justificacion,
                         analista_id=datos.analista_id, quitar_analista=datos.quitar_analista, nota=datos.nota)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except al.ErrorAlerta as e:
        raise HTTPException(400, str(e))
    seg.auditar(u, "UPDATE", "cmp_alertas", f"Alerta {alerta_id} gestionada por {u.username}",
                entidad_id=alerta_id, ip=seg.ip_cliente(request), valores_nuevos=_json(datos.model_dump(exclude_unset=True)))
    return _json(a)


@router.get("/api/clientes/{cliente_id}/bitacora")
def bitacora(cliente_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    """Línea de tiempo del cliente: decisiones sobre sus alertas y cambios en su ficha."""
    _cliente(cliente_id)
    items = []
    with _engine().connect() as conn:
        for f in conn.execute(text(
                "SELECT ev.creado_en AS fecha, ev.usuario, ev.accion, ev.estado_anterior, ev.estado_nuevo, ev.nota, "
                "a.id AS alerta_id, a.titulo, a.periodo FROM cmp_alerta_eventos ev "
                "JOIN cmp_alertas a ON a.id = ev.alerta_id JOIN tx_empresas e ON e.id = a.empresa_id "
                "WHERE e.cliente_id = :c ORDER BY ev.creado_en DESC LIMIT 300"), {"c": cliente_id}).mappings():
            items.append({"origen": "alerta", **dict(f)})
        if conn.scalar(text("SELECT to_regclass('log_auditoria') IS NOT NULL")):
            for f in conn.execute(text(
                    "SELECT created_at AS fecha, username AS usuario, accion, descripcion AS nota FROM log_auditoria "
                    "WHERE entidad = 'clientes' AND entidad_id = :c ORDER BY created_at DESC LIMIT 100"),
                    {"c": cliente_id}).mappings():
                items.append({"origen": "ficha", **dict(f)})
    items.sort(key=lambda x: x["fecha"], reverse=True)
    return _json({"eventos": items[:300]})
