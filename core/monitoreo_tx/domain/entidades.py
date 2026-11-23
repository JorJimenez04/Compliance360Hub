"""
Entidades del dominio: estructuras inmutables que circulan entre capas.
No dependen de la base de datos ni de Streamlit.

La autenticación y los roles son los de Compliance360 Hub (st.session_state["user"]);
este módulo no tiene usuarios propios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class FiltrosTransacciones:
    """Inmutable y hashable: sirve como clave de caché."""
    desde: date | None = None
    hasta: date | None = None
    estados: tuple[str, ...] | None = None  # None = todos; () = ninguno
    texto: str = ""


@dataclass(frozen=True)
class EmpresaVista:
    """
    Empresa cliente tal como aparece en el reporte de AdamoPay (una hoja), con
    los datos de su ficha KYC en `clientes` cuando ya está enlazada.
    """
    id: int
    nombre_reporte: str
    activa: bool
    cliente_id: int | None = None
    # Organización dueña de la empresa (migración 038). None solo en dobles de prueba antiguos.
    organizacion_id: int | None = None
    razon_social: str | None = None
    nit: str | None = None
    nivel_riesgo: str | None = None
    notas: str | None = None

    @property
    def nombre_visible(self) -> str:
        return self.razon_social or self.nombre_reporte

    @property
    def enlazada(self) -> bool:
        return self.cliente_id is not None


@dataclass(frozen=True)
class OpcionesFiltro:
    fecha_min: date | None
    fecha_max: date | None
    estados: tuple[str, ...] = field(default_factory=tuple)

    @property
    def tiene_datos(self) -> bool:
        return self.fecha_min is not None
