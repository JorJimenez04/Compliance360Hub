"""
Errores de negocio. La interfaz los muestra al usuario; cualquier otra
excepción es un fallo técnico y se registra en el log.
"""


class ErrorDominio(Exception):
    """Base de los errores que se pueden mostrar al usuario tal cual."""


class ErrorValidacion(ErrorDominio):
    def __init__(self, errores: list[str] | str):
        self.errores = [errores] if isinstance(errores, str) else list(errores)
        super().__init__("; ".join(self.errores))


class PermisoDenegado(ErrorDominio):
    def __init__(self, mensaje: str = "No tiene permiso para realizar esta acción."):
        super().__init__(mensaje)


class NoEncontrado(ErrorDominio):
    pass
