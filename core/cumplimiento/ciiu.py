"""Actividades económicas CIIU Rev. 4 A.C. y su relación con los modelos de negocio del catálogo.

Fuente de la lista: DANE, CIIU Rev. 4 A.C. (actualización 2022), estructura detallada (502 clases),
más los códigos especiales que la DIAN usa en el RUT de personas naturales (Res. 000114 de 2020).

Relación CIIU → modelo de negocio (referencia del oficial de cumplimiento, ajustable aquí):
- `principal`: el modelo que se aplica automáticamente al elegir la actividad.
- `sugeridos`: otros modelos posibles para la misma actividad; se muestran para marcar con un clic.
Primero se busca la clase exacta (4 dígitos) y, si no hay regla, la división (2 dígitos).
Si una actividad no tiene regla, no se aplica nada y el modelo se elige a mano.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from core.cumplimiento import catalogo

_ARCHIVO = Path(__file__).parent / "datos" / "ciiu_rev4ac_2022.json"

CRIPTO = ("exchange_cripto", "otc_cripto", "custodia_cripto", "on_off_ramp")

# Reglas por clase: códigos → (principal, sugeridos). principal None = solo sugerir.
_POR_CLASE: list[tuple[tuple[str, ...], str | None, tuple[str, ...]]] = [
    # Pagos, fintech y activos virtuales
    (("6619",), "pasarela_pagos", ("dispersion_pagos", "monetizacion", "billetera_digital", "banking_as_a_service", *CRIPTO)),
    (("6499",), "banking_as_a_service", ("billetera_digital", "credito_digital", "crowdfunding", "emisor_tokens", *CRIPTO)),
    (("6494",), "dispersion_pagos", ("remesas", "pasarela_pagos")),
    (("6614",), "remesas", ("billetera_digital", "casa_cambio")),
    (("6615",), "casa_cambio", ("remesas",)),
    (("5310", "5320"), None, ("remesas",)),
    (("6493",), "factoring", ("credito_digital",)),
    (("6491",), "credito_digital", ("establecimiento_credito",)),
    (("8291",), None, ("credito_digital",)),
    # Sector financiero vigilado
    (("6411", "6412", "6421", "6422", "6423", "6495"), "establecimiento_credito", ()),
    (("6424", "6492"), "cooperativa", ()),
    (("6431", "6432", "6531", "6532", "6611", "6612", "6613", "6630"), "fiduciaria_valores", ()),
    (("6511", "6512", "6513", "6621", "6629"), "aseguradora", ()),
    (("6521", "6522"), "salud", ("aseguradora",)),
    # Tecnología, servicios y contenido
    (("5820", "6201", "6202", "6209", "6311", "6312"), "tecnologia_saas", ()),
    (("6399",), "tecnologia_saas", ("marketplace",)),
    (("5911", "5912", "5913", "5920", "6020"), None, ("contenido_adultos", "marketing_afiliados")),
    (("7310", "7320"), "marketing_afiliados", ()),
    (("8211", "8219", "8220", "8299"), "bpo_outsourcing", ()),
    (("7010", "7020", "7490"), "consultoria", ()),
    (("6910",), "servicios_juridicos", ()),
    (("6920",), "servicios_contables", ()),
    (("8010", "8020", "8030"), "seguridad_privada", ()),
    # Juego, deporte y entretenimiento
    (("9200",), "juegos_azar", ()),
    (("9312",), "clubes_deportivos", ()),
    (("9311", "9319"), None, ("clubes_deportivos", "eventos_espectaculos")),
    (("9006", "9007", "9008", "9321", "9329"), "eventos_espectaculos", ()),
    (("7911", "7912"), "turismo", ()),
    (("7990",), "turismo", ("eventos_espectaculos",)),
    # Comercio y sector real
    (("4791",), "ecommerce", ("marketplace",)),
    (("4792", "4799"), "ecommerce", ()),
    (("4511", "4512", "4541"), "vehiculos", ()),
    (("4645", "4664", "4773"), "farmaceutico_quimico", ()),
    (("4661", "4731", "4930"), "energia_hidrocarburos", ()),
    (("4662",), "metales_preciosos", ("comercio_general",)),
    (("0722", "0820", "2421", "3211"), "metales_preciosos", ()),
    (("5229",), "comercio_exterior", ("transporte_carga",)),
    (("4921", "4922", "5011", "5021", "5111", "5112"), "transporte_pasajeros", ()),
    (("4923", "5012", "5022", "5121", "5122"), "transporte_carga", ()),
    (("4111", "4112"), "construccion", ()),
    (("4210", "4220", "4290"), "construccion", ("contratista_estatal",)),
    (("6810", "6820"), "inmobiliario", ()),
    (("7810", "7820", "7830"), "bpo_outsourcing", ()),
]

# Reglas por división (2 dígitos), cuando la clase no tiene regla propia.
_POR_DIVISION: dict[str, tuple[str | None, tuple[str, ...]]] = {
    **{d: ("agroindustria", ()) for d in ("01", "02", "03", "10", "11", "12")},
    **{d: ("energia_hidrocarburos", ()) for d in ("05", "06", "07", "08", "09", "19", "35")},
    "20": ("farmaceutico_quimico", ()), "21": ("farmaceutico_quimico", ()),
    "41": ("construccion", ()), "42": ("construccion", ("contratista_estatal",)), "43": ("construccion", ()),
    "45": ("comercio_general", ("vehiculos",)),
    "46": ("comercio_general", ("comercio_exterior",)),
    "47": ("comercio_general", ()),
    "49": ("transporte_carga", ("transporte_pasajeros",)),
    "50": ("transporte_carga", ("transporte_pasajeros",)),
    "51": ("transporte_carga", ("transporte_pasajeros",)),
    "52": ("transporte_carga", ("comercio_exterior",)),
    "55": ("turismo", ()),
    "61": ("telecomunicaciones", ()),
    "62": ("tecnologia_saas", ()),
    "64": ("establecimiento_credito", ("credito_digital",)),
    "65": ("aseguradora", ()),
    "66": ("fiduciaria_valores", ()),
    "68": ("inmobiliario", ()),
    "71": ("consultoria", ()), "72": ("consultoria", ()), "74": ("consultoria", ()),
    "82": ("bpo_outsourcing", ()),
    "85": ("educacion", ()),
    "86": ("salud", ()), "87": ("salud", ("esal",)), "88": ("esal", ()),
    "90": ("eventos_espectaculos", ()),
    "94": ("esal", ()),
}


@dataclass(frozen=True)
class Actividad:
    codigo: str
    descripcion: str
    seccion: str
    division: str | None
    principal: str | None
    sugeridos: tuple[str, ...]

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "descripcion": self.descripcion, "seccion": self.seccion,
                "division": self.division, "principal": self.principal, "sugeridos": list(self.sugeridos)}


def _regla(codigo: str) -> tuple[str | None, tuple[str, ...]]:
    for codigos, principal, sugeridos in _POR_CLASE:
        if codigo in codigos:
            return principal, sugeridos
    return _POR_DIVISION.get(codigo[:2], (None, ())) if not codigo.startswith("00") else (None, ())


@lru_cache(maxsize=1)
def _datos() -> tuple[dict, dict[str, Actividad]]:
    crudo = json.loads(_ARCHIVO.read_text(encoding="utf-8"))
    actividades = {}
    for codigo, descripcion, seccion in crudo["clases"]:
        principal, sugeridos = _regla(codigo)
        actividades[codigo] = Actividad(codigo, descripcion, seccion, None if seccion == "DIAN" else codigo[:2],
                                        principal, tuple(s for s in sugeridos if s != principal))
    return crudo, actividades


def actividad(codigo: str | None) -> Actividad | None:
    return _datos()[1].get((codigo or "").strip())


def existe(codigo: str) -> bool:
    return actividad(codigo) is not None


def modelos_de(codigos: list[str] | tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Modelos automáticos y sugeridos para un conjunto de actividades (sin repetidos)."""
    principales, sugeridos = [], []
    for c in codigos:
        a = actividad(c)
        if not a:
            continue
        if a.principal and a.principal not in principales:
            principales.append(a.principal)
        sugeridos += [s for s in a.sugeridos if s not in sugeridos]
    return principales, [s for s in sugeridos if s not in principales]


def como_dict() -> dict:
    crudo, actividades = _datos()
    return {"fuente": crudo["fuente"], "secciones": crudo["secciones"], "divisiones": crudo["divisiones"],
            "actividades": [a.como_dict() for a in actividades.values()]}


def validar_reglas() -> list[str]:
    """Errores de configuración: códigos CIIU o modelos que no existen (lo usan las pruebas)."""
    errores = []
    _, actividades = _datos()
    for codigos, principal, sugeridos in _POR_CLASE:
        errores += [f"CIIU inexistente: {c}" for c in codigos if c not in actividades]
        errores += [f"Modelo inexistente: {m}" for m in (principal, *sugeridos) if m and not catalogo.modelo(m)]
    for div, (principal, sugeridos) in _POR_DIVISION.items():
        errores += [f"Modelo inexistente: {m}" for m in (principal, *sugeridos) if m and not catalogo.modelo(m)]
        if not any(a.division == div for a in actividades.values()):
            errores.append(f"División inexistente: {div}")
    return errores
