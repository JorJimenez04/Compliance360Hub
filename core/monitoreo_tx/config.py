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

# Director de cumplimiento del grupo: interno, ve todas las organizaciones en SOLO LECTURA
# (está en ROLES_MONITOREO, nunca en ROLES_CARGA).
ROL_DIRECTOR = "director_cumplimiento"
# Roles que entran al módulo. Es información transaccional de terceros con
# datos personales de beneficiarios: solo cumplimiento y administración.
ROLES_MONITOREO = frozenset({"super_admin", "admin", "compliance", ROL_DIRECTOR})
# Roles que pueden cargar archivos y enlazar empresas con clientes
ROLES_CARGA = frozenset({"super_admin", "admin", "compliance"})

# Rol externo: el cliente de AdamoPay. Solo consulta el tablero y las transacciones
# de SUS empresas (tabla usuario_empresas). No ve riesgo, cargas, enlaces ni exportes.
ROL_CLIENTE = "cliente"
# Quienes pueden consultar tablero y transacciones (internos: todas las empresas; cliente: las de
# su organización, o solo las asignadas si su alcance es 'empresas')
ROLES_CONSULTA = ROLES_MONITOREO | {ROL_CLIENTE}

# Rol externo de la junta directiva de una organización: tablero ejecutivo sin datos personales.
# No entra al detalle de transacciones (tienen nombres y documentos de beneficiarios).
ROL_JUNTA = "junta"

# Alcance de un usuario «cliente» (columna usuarios.alcance)
ALCANCE_ORGANIZACION = "organizacion"   # ve todas las empresas de su organización
ALCANCE_EMPRESAS = "empresas"           # ve solo las de usuario_empresas
