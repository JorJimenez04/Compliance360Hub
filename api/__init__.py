"""
API de Compliance360 Hub (FastAPI).

Sirve al nuevo frontend (web/, Next.js) y reutiliza la lógica existente:
config/, db/ (motor, repositorios, auditoría) y los servicios de cada módulo
(p. ej. core/monitoreo_tx/servicio.py). No duplica reglas de negocio.

Migración gradual: Streamlit (app/main.py) sigue funcionando; cada módulo pasa
a la nueva interfaz cuando su API y sus pantallas están completas.
"""
