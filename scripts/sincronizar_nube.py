"""
scripts/sincronizar_nube.py
─────────────────────────────────────────────────────────────
Revisa la carpeta de OneDrive y carga los reportes de AdamoPay nuevos o
modificados (Monitoreo Transaccional). Lo ejecuta el servicio programado de
Railway (servicio sync-onedrive, C360_TAREA=sincronizar_nube); termina al acabar.

Uso:
    python scripts/sincronizar_nube.py                    # OneDrive (variables TX_ONEDRIVE_*)
    python scripts/sincronizar_nube.py --carpeta "D:\\AdamoPay_Datos"   # carpeta local, para pruebas
    python scripts/sincronizar_nube.py --listar           # solo muestra qué ve, sin cargar

Código de salida: 0 si todo bien, 1 si hubo errores (Railway lo marca como fallido).
"""

import argparse
import logging
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Carga automática de reportes AdamoPay desde la nube.")
    p.add_argument("--carpeta", help="Usar una carpeta local en lugar de OneDrive")
    p.add_argument("--db", help="URL PostgreSQL de destino (por defecto DATABASE_URL)")
    p.add_argument("--listar", action="store_true", help="Solo listar lo que se ve en la fuente")
    a = p.parse_args()
    if a.db:
        os.environ["DATABASE_URL"] = a.db

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    from app.monitoreo_tx.nube.fuentes import ConfigOneDrive, ErrorFuente, FuenteCarpeta, fuente_configurada

    fuente = FuenteCarpeta(a.carpeta) if a.carpeta else fuente_configurada()
    if fuente is None:
        cfg = ConfigOneDrive.desde_entorno()
        if cfg is None:
            print("La carga automática no está configurada: faltan variables TX_ONEDRIVE_*. Nada que hacer.")
            return 0
        # Modo delegado sin conexión: es un problema que alguien debe atender
        print("OneDrive no está conectado (o la conexión no se puede leer). "
              "Conéctelo en Monitoreo Transaccional → Cargas → «Conectar OneDrive».")
        return 1
    print(f"Fuente: {fuente.descripcion()}")

    if a.listar:
        try:
            listado = fuente.listar()
        except ErrorFuente as e:
            print(f"ERROR: {e}")
            return 1
        for arch in listado.archivos:
            print(f"  {arch.empresa} / {arch.nombre}  ({arch.tamano or 0:,} bytes, versión {arch.version[:24]})")
        for s in listado.sueltos:
            print(f"  (suelto en la raíz, se ignora) {s}")
        for s in listado.ignorados:
            print(f"  (formato no admitido, se ignora) {s}")
        return 0

    from db.database import engine
    from app.monitoreo_tx.nube.sincronizacion import revisar

    try:
        r = revisar(fuente, engine, usuario="programada")
    except ErrorFuente as e:
        print(f"ERROR: {e}")
        return 1
    print(f"\nResultado: {r.resultado} — {r.mensaje} ({r.duracion_s} s)")
    for x in r.archivos:
        print(f"  [{x.resultado}] {x.empresa} / {x.nombre}: {x.insertadas} nuevas, {x.actualizadas} actualizadas, "
              f"{x.rechazadas} rechazadas" + (f" · completitud: {x.completitud}" if x.completitud else "")
              + (f" · {x.mensaje}" if x.resultado == "ERROR" else ""))
    return 1 if r.resultado in ("ERROR", "CON_ERRORES") else 0


if __name__ == "__main__":
    sys.exit(main())
