"""
scripts/crear_usuario_cliente.py
Crea (o actualiza) un usuario externo con rol «cliente»: entra a la nueva interfaz,
ve solo Monitoreo Transaccional (Tablero y Transacciones) y solo de SUS empresas.

Uso:
    python scripts/crear_usuario_cliente.py ^
        --username jcmantilla --nombre "Juan Camilo Mantilla" ^
        --email correo@ejemplo.com --empresa "CM Grupo Tecno" ^
        [--database-url postgresql://...]

    --empresa puede repetirse (una persona con varias empresas).
    --reset-clave  genera una clave nueva para un cliente que ya existe.

La clave temporal se genera al azar, se muestra UNA sola vez y en la base solo
queda su hash. Entréguela por un canal distinto del que usa para el usuario.

Seguridad: el script nunca modifica a un usuario que no sea «cliente».
Crea clientes con alcance 'empresas' (solo las indicadas), en la organización de esas
empresas. Para alcance de toda la organización o perfiles Junta, use la pantalla
Usuarios de la nueva interfaz (solo super_admin).
La base destino se resuelve como en los demás scripts (scripts/_db_target.py):
--database-url, luego DATABASE_PUBLIC_URL, luego DATABASE_URL del .env.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# La consola de Windows (cp1252) no admite los emojis de los mensajes: evita que el script se caiga
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from api.claves import clave_temporal, hash_clave as _hash

from scripts._db_target import crear_engine

ROL = "cliente"


def _buscar_empresa(conn, texto: str) -> tuple[int, str, int]:
    """Solo nombre exacto (sin distinguir mayúsculas). Esto da acceso a datos de una empresa a una
    persona externa: un error de tipeo no debe poder asignarle otra empresa; las sugerencias solo se muestran."""
    exacta = conn.execute(text("SELECT id, nombre_reporte, organizacion_id FROM tx_empresas "
                               "WHERE lower(nombre_reporte) = lower(:t)"), {"t": texto.strip()}).all()
    if len(exacta) == 1:
        return exacta[0][0], exacta[0][1], exacta[0][2]
    todas = [r[0] for r in conn.execute(text("SELECT nombre_reporte FROM tx_empresas ORDER BY 1"))]
    parecidas = [n for n in todas if texto.strip().lower() in n.lower()]
    sys.exit(f"❌ No hay una empresa llamada exactamente «{texto}».\n"
             f"   Parecidas: {', '.join(parecidas) or '(ninguna)'}\n"
             f"   Todas: {', '.join(todas) or '(ninguna)'}\n"
             "   Use el nombre tal cual aparece en el reporte.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Crea o actualiza un usuario con rol «cliente».")
    ap.add_argument("--username", required=True)
    ap.add_argument("--nombre", required=True, help="Nombre completo")
    ap.add_argument("--email", required=True)
    ap.add_argument("--empresa", action="append", required=True, help="Nombre de la empresa en el reporte (repetible)")
    ap.add_argument("--reset-clave", action="store_true", help="Genera una clave nueva si el usuario ya existe")
    ap.add_argument("--database-url", default=None, help="Base destino (por defecto, la del .env)")
    args = ap.parse_args()

    username, email = args.username.strip(), args.email.strip().lower()
    if not username or "@" not in email:
        sys.exit("❌ Usuario o correo no válidos.")

    engine, destino = crear_engine()
    print(f"\n🎯 Base destino: {destino}\n")

    clave_nueva: str | None = None
    with engine.begin() as conn:
        empresas = [_buscar_empresa(conn, e) for e in args.empresa]
        # Migración 038: un cliente pertenece a UNA organización; sus empresas deben ser de ella
        organizaciones = {org for _, _, org in empresas}
        if len(organizaciones) != 1:
            sys.exit("❌ Las empresas indicadas pertenecen a organizaciones distintas. No se hizo ningún cambio.")
        organizacion_id = organizaciones.pop()

        filas = conn.execute(
            text("SELECT id, username, email, rol FROM usuarios WHERE username = :u OR lower(email) = :e"),
            {"u": username, "e": email},
        ).mappings().all()
        if len(filas) > 1 or (filas and (filas[0]["username"] != username or filas[0]["email"].lower() != email)):
            sys.exit("❌ El usuario o el correo ya pertenecen a cuentas distintas. No se hizo ningún cambio.")

        if filas:
            u = filas[0]
            if u["rol"] != ROL:
                sys.exit(f"❌ «{username}» ya existe con el rol «{u['rol']}»: este script solo gestiona clientes. "
                         "No se hizo ningún cambio.")
            usuario_id = u["id"]
            org_actual = conn.scalar(text("SELECT organizacion_id FROM usuarios WHERE id = :id"), {"id": usuario_id})
            if org_actual != organizacion_id:
                sys.exit("❌ Las empresas son de otra organización distinta a la del usuario. "
                         "No se hizo ningún cambio.")
            accion = "ya existía"
            if args.reset_clave:
                clave_nueva = clave_temporal()
                conn.execute(text("UPDATE usuarios SET password_hash = :h, activo = 1, updated_at = CURRENT_TIMESTAMP "
                                  "WHERE id = :id"), {"h": _hash(clave_nueva), "id": usuario_id})
                accion = "clave renovada"
        else:
            clave_nueva = clave_temporal()
            usuario_id = conn.execute(
                text("INSERT INTO usuarios (username, nombre_completo, email, password_hash, rol, activo, "
                     "organizacion_id, alcance) VALUES (:u, :n, :e, :h, :r, 1, :o, 'empresas') RETURNING id"),
                {"u": username, "n": args.nombre.strip(), "e": email, "h": _hash(clave_nueva), "r": ROL,
                 "o": organizacion_id},
            ).scalar_one()
            accion = "creado"

        for empresa_id, _, _ in empresas:
            conn.execute(text("INSERT INTO usuario_empresas (usuario_id, empresa_id) VALUES (:u, :e) "
                              "ON CONFLICT DO NOTHING"), {"u": usuario_id, "e": empresa_id})

        conn.execute(
            text("INSERT INTO log_auditoria (username, accion, entidad, entidad_id, descripcion, resultado, rol_usuario) "
                 "VALUES (:u, :a, 'usuarios', :id, :d, 'exitoso', :r)"),
            {"u": "script:crear_usuario_cliente", "a": "CREATE" if accion == "creado" else "UPDATE",
             "id": usuario_id, "r": ROL,
             "d": f"Usuario cliente «{username}» {accion}; empresas: {', '.join(n for _, n, _ in empresas)}"},
        )

    print(f"✅ Usuario «{username}» {accion}.")
    print(f"   Nombre  : {args.nombre.strip()}")
    print(f"   Correo  : {email}")
    print(f"   Rol     : {ROL}")
    print(f"   Empresas: {', '.join(n for _, n, _ in empresas)}")
    if clave_nueva:
        print(f"\n   Clave temporal (se muestra UNA vez, cópiela ahora): {clave_nueva}")
        print("   Entréguela por un canal distinto del usuario (p. ej. llamada o mensajería).")
    else:
        print("\n   (No se cambió la clave. Use --reset-clave para generar una nueva.)")


if __name__ == "__main__":
    main()
