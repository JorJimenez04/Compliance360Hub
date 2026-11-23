"""
scripts/cargar_adamopay.py
─────────────────────────────────────────────────────────────
Carga el reporte de AdamoPay en el módulo Monitoreo Transaccional.

Para el Excel maestro completo (varias decenas de MB, ~1 GB de RAM al
procesarlo), que supera el límite de subida de la app. Se ejecuta desde el
equipo del responsable apuntando a la base que corresponda.

Uso:
    python scripts/cargar_adamopay.py --carpeta "D:\\AdamoPay_Datos"        # una subcarpeta por empresa
    python scripts/cargar_adamopay.py --archivo "D:\\AdamoPay\\Data_Clients&TX.xlsx"
    python scripts/cargar_adamopay.py --archivo historial.csv --empresa "CM Group"
    python scripts/cargar_adamopay.py --archivo reporte.xlsx --db "postgresql://..."   # p. ej. Railway

Opciones:
    --forzar               reprocesar aunque el archivo no haya cambiado
    --eliminar-faltantes   borrar transacciones que ya no vienen en el archivo
    --usuario NOMBRE       quién ejecuta la carga (queda en la bitácora)

Con --carpeta, cada subcarpeta es una empresa y su nombre es el nombre de la
empresa en el sistema; se cargan todos sus CSV «Historial de pagos», del más
antiguo al más reciente por nombre de archivo:

    AdamoPay_Datos/
        CM Grupo Tecno/
            2026-11-12_historial-de-pagos.csv
        Otra Empresa/
            ...

Sin --db se usa DATABASE_URL del entorno o del archivo .env.
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
    p = argparse.ArgumentParser(description="Carga el reporte de AdamoPay (Excel o CSV).")
    origen = p.add_mutually_exclusive_group(required=True)
    origen.add_argument("--archivo", help="Excel maestro (.xlsx) o CSV «Historial de pagos»")
    origen.add_argument("--carpeta", help="Carpeta con una subcarpeta por empresa (CSV)")
    p.add_argument("--empresa", help="Obligatorio con CSV: nombre de la empresa en AdamoPay")
    p.add_argument("--db", help="URL PostgreSQL de destino (por defecto DATABASE_URL)")
    p.add_argument("--forzar", action="store_true")
    p.add_argument("--eliminar-faltantes", action="store_true")
    p.add_argument("--usuario", default=os.getenv("USERNAME") or os.getenv("USER") or "script")
    a = p.parse_args()

    if a.db:
        # Antes de importar db.database, que lee DATABASE_URL al cargarse
        os.environ["DATABASE_URL"] = a.db

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    from db.database import engine
    from core.monitoreo_tx.etl.sync import sincronizar

    destino = engine.url.render_as_string(hide_password=True)
    print(f"Destino: {destino}")
    if a.eliminar_faltantes:
        print("ATENCIÓN: se eliminarán las transacciones que no vengan en el archivo.")

    if a.carpeta:
        trabajos = _trabajos_de_carpeta(pathlib.Path(a.carpeta))
        if not trabajos:
            print("No se encontraron CSV en subcarpetas de", a.carpeta)
            return 1
    else:
        trabajos = [(pathlib.Path(a.archivo), a.empresa)]

    codigo = 0
    for ruta, empresa in trabajos:
        print(f"\n▶ {ruta.name}" + (f"  →  {empresa}" if empresa else ""))
        try:
            r = sincronizar(ruta, engine=engine, forzar=a.forzar, eliminar_faltantes=a.eliminar_faltantes,
                            cliente=empresa, usuario=f"{a.usuario} (script)")
        except Exception as e:
            print(f"  ERROR: {e}")
            codigo = 1
            continue
        _imprimir(r)
        if r.resultado not in ("OK", "OMITIDA"):
            codigo = 1
    return codigo


def _trabajos_de_carpeta(carpeta: pathlib.Path) -> list[tuple[pathlib.Path, str]]:
    """(archivo, empresa) por cada CSV de cada subcarpeta, ordenados por nombre."""
    trabajos = []
    for sub in sorted(p for p in carpeta.iterdir() if p.is_dir()):
        for archivo in sorted(sub.glob("*.csv")):
            trabajos.append((archivo, sub.name.strip()))
    sueltos = sorted(carpeta.glob("*.csv"))
    if sueltos:
        print("ATENCIÓN: estos CSV están sueltos en la raíz y no se cargan (no se sabe de qué empresa son):")
        for s in sueltos:
            print("   -", s.name)
    return trabajos


def _imprimir(r) -> None:
    print(f"  Resultado: {r.resultado} — {r.mensaje}")
    if r.resultado == "OK":
        from core.cumplimiento.alertas import evaluar_por_nombres
        ev = evaluar_por_nombres(engine, list(r.verificacion) or None, usuario="script")
        if ev:
            print(f"  Alertas de cumplimiento: {ev.nuevas} nuevas, {ev.actualizadas} actualizadas")
    if r.resultado == "OK":
        print(f"  Empresas: {r.clientes} · leídas: {r.filas_leidas} · nuevas: {r.insertadas} · "
              f"actualizadas: {r.actualizadas} · sin cambios: {r.sin_cambios} · "
              f"rechazadas: {r.rechazadas} · eliminadas: {r.eliminadas} · {r.duracion_s} s")
        for empresa, v in r.verificacion.items():
            marca = "OK " if v["completa"] else "!! "
            texto = ("sin huecos ni descuadres" if v["completa"] else
                     f"{v['faltantes']} faltante(s) {v['ejemplos_faltantes'][:5]}, "
                     f"{v['descuadres_saldo']} saldo(s) descuadrado(s) {v['ejemplos_descuadre'][:5]}")
            print(f"  {marca}Completitud {empresa}: No. {v['no_inicial']}–{v['no_final']}, {texto}"
                  + (" · historial no empieza en 1" if v["parcial"] else ""))
        if r.empresas_nuevas:
            print(f"  Empresas nuevas (enlácelas en la app): {', '.join(r.empresas_nuevas)}")
        if r.archivo_rechazos:
            print(f"  Rechazos: {r.archivo_rechazos}")


if __name__ == "__main__":
    sys.exit(main())
