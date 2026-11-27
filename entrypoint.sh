#!/bin/bash
# entrypoint.sh — Compliance360 Hub
# Ejecuta migraciones y luego arranca Streamlit.
# Usado por Docker/Railway como punto de entrada del contenedor.
set -euo pipefail

# ── 0. Servicio programado: carga automática desde OneDrive ──────
# El servicio «sync-onedrive» de Railway usa esta misma imagen con
# C360_TAREA=sincronizar_nube: aplica migraciones, revisa la carpeta y termina.
# Su horario (Cron Schedule «0 0 * * *»: diario, 7 p. m. Colombia), sin healthcheck y con Restart
# Policy «Never» se configuran en Settings del servicio (Config as Code de
# Railway está obsoleto y los servicios nuevos no pueden usarlo).
if [ "${C360_TAREA:-}" = "sincronizar_nube" ]; then
    python db/sync_db.py > /dev/null
    exec python scripts/sincronizar_nube.py
fi

# ── 1. Verificación de variables críticas (solo en producción) ────
APP_ENV="${APP_ENV:-development}"
if [ "$APP_ENV" = "production" ]; then
    python -c "from app.utils.production_check import run_checks; run_checks()"
fi

# ── 2. Inicialización / migración de la base de datos ────────────
echo "[AdamoServices] Ejecutando migraciones de base de datos..."
python -m db.database
python db/sync_db.py
echo "[AdamoServices] Migraciones completadas."

# ── 3. (Retirado 2026-11-27) Seed de usuarios de prueba ───────────
# Creaba cuentas de prueba con perfiles de la app anterior (test_manager_ops,
# test_agente…) en cada despliegue. Desde la migración 044 la base solo acepta los
# perfiles actuales y los usuarios se crean únicamente desde la pantalla Usuarios.

# ── 4. Propagar SECRET_KEY como clave de firma de cookies de sesión ────────
# Streamlit usa STREAMLIT_SERVER_COOKIE_SECRET para firmar el token de sesión.
# La misma clave configura el firmado criptográfico del lado del servidor.
if [ -n "${SECRET_KEY:-}" ]; then
    export STREAMLIT_SERVER_COOKIE_SECRET="$SECRET_KEY"
    echo "[AdamoServices] STREAMLIT_SERVER_COOKIE_SECRET configurado desde SECRET_KEY."
else
    echo "[AdamoServices] ADVERTENCIA: SECRET_KEY no definida — las sesiones no serán seguras."
fi

# ── 5. Webhook de Power Automate (proceso en segundo plano) ────────
if [ -n "${WEBHOOK_SECRET:-}" ] || [ "$APP_ENV" != "production" ]; then
    echo "[AdamoServices] Iniciando webhook de correo en PORT_WEBHOOK=${PORT_WEBHOOK:-8502}..."
    python app/webhook.py &
fi

# ── 6. Puerto dinámico: Railway inyecta $PORT; defecto 8501 ──────
PORT="${PORT:-8501}"

# ── 7. Arrancar Streamlit ───────────────────────────────────────────
echo "[AdamoServices] Iniciando Streamlit en el puerto $PORT..."
exec python -m streamlit run app/main.py \
    --server.port "$PORT" \
    --server.address "0.0.0.0" \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection true \
    --browser.gatherUsageStats false
