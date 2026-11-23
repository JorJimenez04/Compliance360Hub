"""
Punto de entrada de la API.

    uvicorn api.main:app --host 0.0.0.0 --port 8000

En Railway corre como servicio privado: el frontend (web/) la llama por la red
interna del proyecto, así que no necesita dominio público.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from config.settings import APP_ENV
from api.rutas import auth, clientes, monitoreo, organizaciones, usuarios

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

app = FastAPI(
    title="Compliance360 Hub API",
    version="1.0.0",
    # La documentación interactiva solo en desarrollo
    docs_url=None if APP_ENV == "production" else "/api/docs",
    redoc_url=None,
    openapi_url=None if APP_ENV == "production" else "/api/openapi.json",
)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("Cache-Control", "no-store")
    return respuesta


@app.exception_handler(RequestValidationError)
async def datos_invalidos(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Datos inválidos en la petición."})


@app.get("/api/salud")
def salud() -> dict:
    return {"ok": True}


app.include_router(auth.router)
app.include_router(monitoreo.router)
app.include_router(organizaciones.router)
app.include_router(organizaciones.router_catalogo)
app.include_router(usuarios.router)
app.include_router(clientes.router)
