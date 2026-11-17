"""
Parámetros del módulo de Monitoreo Transaccional.

La conexión a la base es la de Compliance360 Hub (db.database.engine); aquí
solo viven las reglas propias de los datos de AdamoPay.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

# Estados con los que un débito se considera pagado
ESTADOS_EFECTIVOS = ["PAGADO", "VALIDADO"]
# C/CC cédula, CE extranjería, PA pasaporte, TI tarjeta de identidad,
# PPT permiso por protección temporal, PEP permiso especial de permanencia
TIPOS_PERSONA_NATURAL = ["C", "CC", "PA", "CE", "CEDULA", "TI", "PPT", "PEP"]
TIPOS_PERSONA_JURIDICA = ["N", "NIT"]

# Estado asignado a transacciones que llegan sin estado en el reporte
ESTADO_SIN_DATO = "Sin estado"

# Carpeta donde la sincronización deja el CSV de filas rechazadas (ignorada por git)
SYNC_LOG_DIR = Path(os.getenv("TX_SYNC_LOG_DIR", BASE_DIR / "data" / "logs"))

# Roles que entran al módulo. Es información transaccional de terceros con
# datos personales de beneficiarios: solo cumplimiento y administración.
ROLES_MONITOREO = frozenset({"super_admin", "admin", "compliance"})
# Roles que pueden cargar archivos y enlazar empresas con clientes
ROLES_CARGA = frozenset({"super_admin", "admin", "compliance"})
