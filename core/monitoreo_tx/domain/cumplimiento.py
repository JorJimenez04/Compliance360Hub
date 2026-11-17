"""
Requisitos documentales de los expedientes de cumplimiento.

Cada expediente reúne, para un cliente representativo, los soportes que piden
los aliados bancarios. Hay dos responsables:

- La empresa aporta lo que identifica a la persona (documento y foto).
- AdamoPay aporta el resultado de sus verificaciones (Infolaft, bases abiertas
  y screening). La empresa ve si están al día, pero no su contenido: el
  resultado de una verificación es información interna de cumplimiento.
"""

from __future__ import annotations

from dataclasses import dataclass

EMPRESA = "empresa"
ADAMOPAY = "adamopay"


@dataclass(frozen=True)
class Requisito:
    tipo: str
    titulo: str
    descripcion: str
    responsable: str   # EMPRESA o ADAMOPAY


REQUISITOS: tuple[Requisito, ...] = (
    Requisito("identificacion", "Documento de identidad",
              "Copia legible del documento por ambas caras.", EMPRESA),
    Requisito("foto", "Foto de la persona",
              "Fotografía reciente del titular.", EMPRESA),
    Requisito("infolaft", "Reporte Infolaft",
              "Consulta en Infolaft con fecha de generación.", ADAMOPAY),
    Requisito("bases_abiertas", "Consultas en bases abiertas",
              "Procuraduría, Contraloría, Policía, Rama Judicial y otras fuentes públicas.", ADAMOPAY),
    Requisito("screening", "Screening",
              "Cruce contra listas restrictivas y de control (OFAC, ONU, UE, PEP).", ADAMOPAY),
)
POR_TIPO = {r.tipo: r for r in REQUISITOS}

TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB por archivo

# Extensión -> (tipo MIME, firma con la que debe empezar el archivo)
FORMATOS = {
    "pdf": ("application/pdf", b"%PDF"),
    "jpg": ("image/jpeg", b"\xff\xd8\xff"),
    "jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    "png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}


def validar_archivo(nombre: str, contenido: bytes) -> tuple[str | None, str | None]:
    """Devuelve (mime, None) si el archivo es aceptable o (None, motivo) si no.
    Se revisa el contenido, no solo la extensión: un ejecutable renombrado a .pdf se rechaza."""
    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension not in FORMATOS:
        return None, "Formato no permitido. Use PDF, JPG o PNG."
    if not contenido:
        return None, "El archivo está vacío."
    if len(contenido) > TAMANO_MAXIMO:
        return None, f"El archivo supera el máximo de {TAMANO_MAXIMO // (1024 * 1024)} MB."
    mime, firma = FORMATOS[extension]
    if not contenido.startswith(firma):
        return None, "El contenido no corresponde a un archivo PDF, JPG o PNG válido."
    return mime, None
