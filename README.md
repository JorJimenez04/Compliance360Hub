# Compliance360 Hub

Plataforma de cumplimiento de AdamoServices: Banking Partners y Aliados Estratégicos, clientes, SARLAFT, Cripto Compliance y Monitoreo Transaccional (AdamoPay).  
Desarrollada por el área de Compliance de AdamoServices.

## Stack Tecnológico

- **Lenguaje:** Python 3.11
- **App actual:** Streamlit (todos los módulos)
- **Nueva interfaz (en migración):** API FastAPI (`api/`) + frontend Next.js 16 / TypeScript / Tailwind 4 (`web/`). Por ahora cubre Monitoreo Transaccional.
- **Base de Datos:** PostgreSQL (Docker local, Railway en producción)
- **Autenticación:** Basada en roles (RBAC)
- **Auditoría:** Log completo de cambios para cumplimiento regulatorio

## Estructura del Proyecto

```
Compliance360_Hub/
├── app/                        # Lógica de la aplicación Streamlit
│   ├── main.py                 # Entry point principal
│   ├── auth/                   # Autenticación y control de acceso
│   ├── pages/                  # Páginas de la app (Dashboard, Partners, Pipeline, Auditoría)
│   ├── monitoreo_tx/ui/        # Pantallas Streamlit de Monitoreo Transaccional
│   ├── components/             # Componentes UI reutilizables
│   └── utils/                  # Funciones utilitarias
├── db/                         # Capa de datos
│   ├── database.py             # Gestor de conexión (PostgreSQL)
│   ├── models.py               # Modelos de datos (Pydantic)
│   ├── repositories/           # Patrón Repository (CRUD desacoplado)
│   └── migrations/             # Scripts SQL de migración
├── api/                        # API FastAPI de la nueva interfaz
│   ├── main.py                 # Entry point (uvicorn api.main:app)
│   ├── seguridad.py            # Sesión (cookie HttpOnly firmada), CSRF, bloqueo por intentos, roles
│   └── rutas/                  # auth y monitoreo (tablero, transacciones, riesgo, cargas, OneDrive, empresas)
├── core/                       # Lógica de negocio compartida, sin Streamlit ni FastAPI
│   └── monitoreo_tx/           # Servicio, repositorio, dominio, ETL, nube, riesgo, formato
├── web/                        # Frontend Next.js (src/app, src/components, src/lib)
├── config/                     # Configuración centralizada
│   └── settings.py
├── tests/                      # Suite de pruebas
├── data/                       # Archivos locales de trabajo (gitignored)
├── Dockerfile / Dockerfile.api # Imágenes de la app Streamlit y de la API (web/Dockerfile para el frontend)
├── .env.example                # Variables de entorno de ejemplo
├── requirements.txt
└── README.md
```

## Monitoreo Transaccional (AdamoPay)

Ítem **Monitoreo Transaccional** del menú (roles `super_admin`, `admin`, `compliance`).
Lógica en `core/monitoreo_tx/` y pantallas Streamlit en `app/monitoreo_tx/ui/` (integrado desde AdamoPay_Analisis-ReporteTX); tablas `tx_*`
creadas por la migración `035_monitoreo_transaccional.sql`.

| Pestaña | Contenido |
|---|---|
| Tablero | Indicadores, evolución, movimientos, ranking de beneficiarios, bancos y horarios, devoluciones, detalle con exporte CSV y evaluación de riesgo GAFI/UIAF indicativa |
| Cargas | Subir el reporte de AdamoPay (Excel maestro o CSV «Historial de pagos» de una empresa) y bitácora de cargas |
| Empresas | Enlazar cada empresa del reporte con su ficha de Gestión de Clientes |

La carga es incremental e idempotente: solo escribe transacciones nuevas o modificadas, y un
archivo idéntico al último cargado se omite. Cada carga, enlace y descarga de CSV queda en
`log_auditoria`.

El Excel maestro completo supera el límite de subida de la app (10 MB) y procesarlo usa
cerca de 1 GB de memoria; se carga desde el equipo del responsable:

```bash
python scripts/cargar_adamopay.py --archivo "D:\AdamoPay\Data_Clients&TX.xlsx"            # base del .env
python scripts/cargar_adamopay.py --archivo reporte.xlsx --db "<DATABASE_PUBLIC_URL de Railway>"
python scripts/cargar_adamopay.py --archivo historial.csv --empresa "CM Group"
```

**Carga automática desde OneDrive**: el servicio programado `sync-onedrive` de Railway
(Cron Schedule `0 0 * * *` en Settings: diario, 7 p. m. Colombia; variable `C360_TAREA=sincronizar_nube`) revisa la carpeta
`AdamoPay_Datos` del OneDrive empresarial (una subcarpeta por empresa) y carga los CSV nuevos.
Se configura con `TX_ONEDRIVE_TENANT_ID` y `TX_ONEDRIVE_CLIENT_ID` (registro de aplicación en
Microsoft Entra ID con permisos delegados `Files.Read` y `offline_access`); el responsable conecta
su OneDrive una vez desde Cargas → «Conectar OneDrive» (inicio de sesión con código) y el acceso
queda cifrado con `SECRET_KEY`. El servicio programado necesita la misma `SECRET_KEY`.
Alternativa con administrador: `TX_ONEDRIVE_CLIENT_SECRET` + `TX_ONEDRIVE_USUARIO` y `Files.Read.All`.
Prueba sin cargar: `python scripts/sincronizar_nube.py --listar`.

Pruebas de sincronización contra PostgreSQL (la base indicada se vacía):
`$env:TX_TEST_PG_URL = "postgresql://adamo:adamo_dev_2026@localhost:5432/tx_test"`.

## Nueva interfaz (API + Web)

Reemplaza gradualmente la app Streamlit. Su primera pantalla es Monitoreo Transaccional
(Tablero, Transacciones, Riesgo, Cargas y Empresas) y reutiliza la misma base de datos, roles y auditoría.

- **API** (`api/`): sesión con cookie HttpOnly firmada con `SECRET_KEY`, protección CSRF por cabecera,
  bloqueo por intentos fallidos y auditoría. Salud: `GET /api/salud`. Documentación interactiva
  (`/api/docs`) solo fuera de producción.
- **Web** (`web/`): el navegador solo habla con Next.js, que reenvía `/api/*` a FastAPI (variable `API_URL`).
  `NEXT_PUBLIC_APP_CLASICA_URL` apunta a la app Streamlit.

```bash
# Terminal 1 — API (con el venv activo y el .env configurado)
pip install -r api/requirements.txt      # autocontenido: no instala Streamlit
uvicorn api.main:app --reload --port 8000

# Terminal 2 — Web
cd web
npm install
npm run dev          # http://localhost:3000   (npm run typecheck para validar tipos)
```

## Despliegue en Railway

Un solo proyecto de Railway (`faithful-magic`, entorno `production`) con cinco servicios.
No hay `railway.toml`: Config as Code está obsoleto en Railway, y un `railway.toml` en la raíz
se aplicaba a todos los servicios del repo (forzaba el Dockerfile de Streamlit en la API).
Cada servicio se configura en su panel.

| Servicio | Origen | Configuración clave |
|---|---|---|
| App Streamlit | Raíz del repo, `Dockerfile` | Start command `/entrypoint.sh`; healthcheck `/_stcore/health` (180 s); reinicio On Failure |
| `API` (FastAPI) | Raíz del repo, `Dockerfile.api` | `RAILWAY_DOCKERFILE_PATH=Dockerfile.api`, `PORT=8000`; sin dominio público; healthcheck `/api/salud` |
| `web` (Next.js) | Root Directory `web` | `API_URL=http://api.railway.internal:8000` y `NEXT_PUBLIC_APP_CLASICA_URL` (ambas se leen al construir); healthcheck `/login`; único con dominio nuevo |
| `sync-onedrive` | Misma imagen de Streamlit | `C360_TAREA=sincronizar_nube`, Cron Schedule diario |
| `Postgres` | Plantilla de Railway (PostgreSQL 18) | Sin acceso público; los servicios usan `DATABASE_URL=${{Postgres.DATABASE_URL}}` por la red privada |

Variables comunes a Streamlit, API y `sync-onedrive`: `DATABASE_URL`, `SECRET_KEY` (la misma en todos),
`ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL`, `APP_ENV=production`.

Para operar la base desde un equipo local (respaldo o restauración) hay que abrir el acceso público
de `Postgres` solo durante la operación y cerrarlo al terminar. Respaldo con el cliente de la misma versión:
`pg_dump "<URL pública>" --format=custom --no-owner --no-acl -f adamo.dump` (imagen `postgres:18`).

`api/requirements.txt` es independiente de `requirements.txt` (el de Streamlit), y `Dockerfile.api`
solo copia `api/`, `core/`, `db/`, `config/` y `scripts/`. Regla: `api/` y `core/` no importan `app/`. (Pendiente: `db/repositories/crypto_repo.py` aún importa `app.utils.crypto_logic`; no lo usa la API.)
Pruebas de la API: `pytest tests/test_api.py`.

## Módulos de Pipeline (Estados)

```
Prospecto → En Calificación → Onboarding → Activo → Suspendido → Terminado
```

## Roles de Acceso

| Rol              | Permisos                                                  |
|------------------|-----------------------------------------------------------|
| `admin`          | Acceso total. Gestión de usuarios.                        |
| `compliance`     | CRUD completo. Aprobación SARLAFT. Log de auditoría.      |
| `comercial`      | Crear prospectos. Editar campos comerciales.              |
| `consulta`       | Solo lectura.                                             |

## Ejecución en Local

**Requisito previo:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y en ejecución (solo para la BD).

**1. Levantar PostgreSQL**

```bash
docker compose up -d postgres
```

**2. Preparar entorno Python**

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

**3. Crear `.env` en la raíz del proyecto**

```env
APP_ENV=development
SECRET_KEY=cualquier_string_de_desarrollo_local
ADMIN_USERNAME=jorge_jimenez
ADMIN_PASSWORD=<elige_una_contraseña_local_fuerte>
ADMIN_EMAIL=compliance@adamoservices.co
DATABASE_URL=postgresql://adamo:adamo_dev_2026@localhost:5432/adamoservices
```

**4. Inicializar BD y ejecutar**

```bash
python -m db.database
streamlit run app/main.py
```

Acceder en `http://localhost:8501`.

Para detener la BD: `docker compose down`

## Instalación (resumen mínimo)

```bash
git clone https://github.com/JorJimenez04/Proyecto_BP-AliadosEstrategicos_Reporte.git
cd Proyecto_BP-AliadosEstrategicos_Reporte
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
```

## Variables de Entorno

Ver `.env.example` para la lista completa y descripción de cada variable.

## Cumplimiento Regulatorio

Este sistema fue diseñado para soportar los requerimientos de:
- **SARLAFT** (Superintendencia Financiera de Colombia)
- **UIAF** — Reportes de operaciones sospechosas
- **Listas Restrictivas** — OFAC, ONU, UE

---
*AdamoServices — Compliance & Technology | [adamoservices.co](https://adamoservices.co)*
