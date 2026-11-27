"""Generación y hash de claves temporales (usado por la API)."""

from __future__ import annotations

import secrets

import bcrypt

# Sin caracteres que se confunden al leerlos (0/O, 1/l/I)
ALFABETO = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def clave_temporal(largo: int = 16) -> str:
    while True:
        c = "".join(secrets.choice(ALFABETO) for _ in range(largo))
        # Garantiza mayúscula, minúscula y dígito
        if any(x.islower() for x in c) and any(x.isupper() for x in c) and any(x.isdigit() for x in c):
            return c


MINIMO = 12


def validar_clave(clave: str) -> str | None:
    """Motivo por el que una clave escrita por el super_admin no sirve; None si cumple."""
    if clave != clave.strip():
        return "La clave no puede empezar ni terminar con espacios."
    if len(clave) < MINIMO:
        return f"La clave debe tener al menos {MINIMO} caracteres."
    if not (any(c.islower() for c in clave) and any(c.isupper() for c in clave) and any(c.isdigit() for c in clave)):
        return "La clave debe tener al menos una mayúscula, una minúscula y un número."
    return None


def hash_clave(clave: str) -> str:
    return bcrypt.hashpw(clave.encode(), bcrypt.gensalt(12)).decode()
