"""
Lectura, reparación, limpieza y validación del Excel maestro de AdamoPay.

Formato de entrada: un libro donde cada hoja es un cliente y cada fila un
movimiento. Problemas reales que se corrigen aquí:

1. Filas partidas: un salto de línea dentro de BENEFICIARIO o DESCRIPCION
   hace que el resto del registro quede en la fila siguiente, desplazado.
2. Filas de control al final de algunas hojas ("HASH: <sha256>").
3. Transacciones sin ESTADO.
4. Identificadores numéricos (cuentas, documentos) que no deben tratarse
   como números (se perderían ceros o se convertirían a float).

También lee el CSV «Historial de pagos» que AdamoPay exporta por cliente
(separado por punto y coma, mismas columnas): como el archivo no dice de qué
cliente es, el nombre se indica al cargarlo.

Este módulo no toca la base de datos: devuelve DataFrames limpios.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

from core.monitoreo_tx.config import (
    ESTADO_SIN_DATO,
    ESTADOS_EFECTIVOS,
    TIPOS_PERSONA_JURIDICA,
    TIPOS_PERSONA_NATURAL,
)

logger = logging.getLogger(__name__)

# Encabezado Excel -> columna en base de datos
COLUMNAS_EXCEL = {
    "No.": "no_registro",
    "FECHA": "fecha",
    "HORA": "hora",
    "ID DE TRANSACCION": "id_transaccion",
    "ID PAXUM": "referencia_externa",
    "TIPO DE TRANSACCION": "tipo_transaccion",
    "TIPO DE IDENTIFICACION": "tipo_identificacion",
    "BENEFICIARIO": "beneficiario",
    "ID DE CLIENTE": "id_beneficiario",
    "BANCO": "banco",
    "TIPO DE CUENTA": "tipo_cuenta",
    "NUMERO DE CUENTA": "numero_cuenta",
    "MONTO (COP)": "monto",
    "COMISION (COP)": "comision",
    "MONTO TOTAL (COP)": "monto_total",
    "ESTADO": "estado",
    "EXPORTADO POR": "exportado_por",
    "SALDO (COP)": "saldo",
    "DESCRIPCION": "descripcion",
}

COLUMNAS_OBLIGATORIAS = ["No.", "FECHA", "ID DE TRANSACCION", "MONTO (COP)", "ESTADO"]

COLUMNAS_TEXTO = [
    "tipo_transaccion", "beneficiario", "banco", "descripcion", "exportado_por",
]
COLUMNAS_ID = [
    "id_transaccion", "tipo_identificacion", "id_beneficiario", "tipo_cuenta",
    "numero_cuenta", "referencia_externa",
]

# Columnas que definen el contenido de una transacción (para detectar cambios)
COLUMNAS_NEGOCIO = [
    "fecha", "hora", "tipo_transaccion", "tipo_identificacion", "beneficiario",
    "id_beneficiario", "banco", "tipo_cuenta", "numero_cuenta", "monto", "comision",
    "monto_total", "estado", "saldo", "descripcion", "referencia_externa", "exportado_por",
]

_RE_HASH = re.compile(r"^(HASH:\s*)?[0-9A-F]{64}$", re.IGNORECASE)
_RE_ESPACIOS = re.compile(r"\s+")
_VALORES_NULOS = {"", "-", "nan", "none", "null", "nat"}


@dataclass
class ResultadoHoja:
    cliente: str
    df: pd.DataFrame
    filas_leidas: int
    reparadas: int = 0
    rechazos: list[dict] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


class ErrorEstructuraExcel(ValueError):
    """El archivo no tiene la estructura mínima esperada."""


# =========================
# Helpers de valores
# =========================
def _es_vacio(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    if v is pd.NaT:
        return True
    return isinstance(v, str) and v.strip().lower() in _VALORES_NULOS


def _a_fecha(v) -> date | None:
    """Solo acepta valores que sean fecha; un entero (p. ej. un documento) no lo es."""
    if isinstance(v, datetime):
        return None if pd.isna(v) else v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v.strip():
        f = pd.to_datetime(v.strip(), errors="coerce", dayfirst=True)
        return None if pd.isna(f) else f.date()
    return None


def _a_hora(v) -> str | None:
    if isinstance(v, datetime):
        return v.strftime("%H:%M:%S")
    if isinstance(v, time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, str) and v.strip():
        h = pd.to_datetime(v.strip(), format="mixed", errors="coerce")
        return None if pd.isna(h) else h.strftime("%H:%M:%S")
    return None


_RE_MOJIBAKE = re.compile("[ÃÂ]")
_RE_A_SUELTA = re.compile(r"Â(?=\s|$)")


def reparar_codificacion(texto: str) -> str:
    """
    Repara texto UTF-8 que fue leído como Windows-1252 antes de llegar al Excel:
    'PATIÃ‘O' -> 'PATIÑO', 'ALARCÃ“N' -> 'ALARCÓN', 'NICOLÃ\\x81S' -> 'NICOLÁS'.
    Si el resultado no es UTF-8 válido el texto se deja igual, así un nombre
    legítimo como 'SÃO PAULO' no se altera. Una 'Â' suelta es el resto de un
    espacio no separable (C2 A0) y se elimina.
    """
    if not _RE_MOJIBAKE.search(texto):
        return texto
    # Palabra por palabra: un carácter raro en una palabra no impide reparar las demás
    reparado = re.sub(r"\S+", lambda m: _reparar_palabra(m.group()), texto)
    return _RE_A_SUELTA.sub("", reparado)


def _reparar_palabra(palabra: str) -> str:
    # Algunos nombres se dañaron dos veces ('NIÃƒâ€˜O'): se repite mientras haya avance
    original = actual = palabra
    for _ in range(3):
        if not _RE_MOJIBAKE.search(actual):
            break
        siguiente = _decodificar_una_vez(actual)
        if siguiente == actual:
            break
        actual = siguiente
    # 'IBAñEZ' -> 'IBAÑEZ': si el resto de la palabra estaba en mayúsculas, se conserva
    letras = [c for c in original if c.isascii() and c.isalpha()]
    if actual != original and letras and all(c.isupper() for c in letras):
        actual = actual.upper()
    return actual


def _decodificar_una_vez(palabra: str) -> str:
    datos = bytearray()
    try:
        for ch in palabra:
            if ord(ch) < 0x80:
                datos.append(ord(ch))
                continue
            try:
                datos += ch.encode("cp1252")
            except UnicodeEncodeError:
                # cp1252 no define 0x81, 0x8D, 0x8F, 0x90 y 0x9D: llegan como el mismo código
                if ord(ch) > 0xFF:
                    raise
                datos.append(ord(ch))
        return datos.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return palabra


def _limpiar_texto(v) -> str | None:
    if _es_vacio(v):
        return None
    return _RE_ESPACIOS.sub(" ", reparar_codificacion(str(v))).strip() or None


def _limpiar_id(v) -> str | None:
    """Identificadores como texto: 1088007763 -> '1088007763' (nunca '1088007763.0')."""
    if _es_vacio(v):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return _limpiar_texto(v)


def _unir_texto(a, b) -> str | None:
    partes = [p for p in (_limpiar_texto(a), _limpiar_texto(b)) if p]
    return " ".join(partes) or None


def clasificar_tipo_persona(tipo_id: str | None) -> str:
    # pandas 3 representa los textos vacíos como NaN (float), no como None
    if not isinstance(tipo_id, str) or not tipo_id.strip():
        return "Desconocido"
    t = tipo_id.strip().upper()
    if t in TIPOS_PERSONA_NATURAL:
        return "Natural"
    if t in TIPOS_PERSONA_JURIDICA:
        return "Jurídica"
    return "Desconocido"


# =========================
# Reparación de filas
# =========================
def reparar_filas(df_raw: pd.DataFrame, cliente: str) -> tuple[pd.DataFrame, int, list[dict]]:
    """
    Recorre las filas en orden. Una fila con FECHA válida es una transacción.
    Una fila sin fecha puede ser:
      - vacía                         -> se ignora
      - control de integridad (HASH)  -> se descarta
      - continuación de BENEFICIARIO  -> el resto del registro está desplazado:
                                         celda 0 = final del nombre, celdas 1.. =
                                         columnas posteriores a BENEFICIARIO
      - continuación de un texto      -> una sola celda: se agrega a DESCRIPCION
      - cualquier otra cosa           -> rechazada
    Devuelve (df reparado con columna _fila_excel, nº de reparaciones, rechazos).
    """
    columnas = list(df_raw.columns)
    i_fecha = columnas.index("FECHA")
    i_benef = columnas.index("BENEFICIARIO") if "BENEFICIARIO" in columnas else None
    i_desc = columnas.index("DESCRIPCION") if "DESCRIPCION" in columnas else None

    filas: list[list] = []
    origen: list[int] = []
    rechazos: list[dict] = []
    reparadas = 0
    idx_ultima_valida = -10

    for idx, fila in enumerate(df_raw.itertuples(index=False, name=None)):
        fila_excel = idx + 2  # +1 encabezado, +1 base 1
        fila = list(fila)

        if _a_fecha(fila[i_fecha]) is not None:
            filas.append(fila)
            origen.append(fila_excel)
            idx_ultima_valida = idx
            continue

        no_vacios = [v for v in fila if not _es_vacio(v)]
        if not no_vacios:
            continue

        primera = fila[0]
        if isinstance(primera, str) and _RE_HASH.match(primera.strip()):
            rechazos.append(_rechazo(cliente, fila_excel, "Fila de control (hash de integridad)", primera))
            continue

        es_continuacion = idx_ultima_valida == idx - 1
        if es_continuacion:
            previa = filas[-1]

            if i_benef is not None and all(_es_vacio(v) for v in previa[i_benef + 1:]):
                n_resto = len(columnas) - i_benef - 1
                previa[i_benef] = _unir_texto(previa[i_benef], primera)
                previa[i_benef + 1:] = fila[1:1 + n_resto]
                reparadas += 1
                idx_ultima_valida = idx  # por si el nombre tenía más de un salto
                continue

            if i_desc is not None and len(no_vacios) == 1 and not _es_vacio(primera):
                previa[i_desc] = _unir_texto(previa[i_desc], primera)
                reparadas += 1
                idx_ultima_valida = idx
                continue

        rechazos.append(_rechazo(cliente, fila_excel, "Fila sin fecha válida", primera))

    df = pd.DataFrame(filas, columns=columnas)
    df["_fila_excel"] = origen
    return df, reparadas, rechazos


def _rechazo(cliente: str, fila_excel, motivo: str, valor=None) -> dict:
    valor = None if _es_vacio(valor) else str(valor)[:120]
    return {"cliente": cliente, "fila_excel": fila_excel, "motivo": motivo, "valor": valor}


# =========================
# Limpieza y validación
# =========================
def limpiar_hoja(df_raw: pd.DataFrame, cliente: str) -> ResultadoHoja:
    faltantes = [c for c in COLUMNAS_OBLIGATORIAS if c not in df_raw.columns]
    if faltantes:
        raise ErrorEstructuraExcel(f"Hoja '{cliente}': faltan columnas {faltantes}")

    resultado = ResultadoHoja(cliente=cliente, df=pd.DataFrame(), filas_leidas=len(df_raw))
    desconocidas = [c for c in df_raw.columns if c not in COLUMNAS_EXCEL]
    if desconocidas:
        resultado.advertencias.append(f"Columnas ignoradas: {desconocidas}")

    df, resultado.reparadas, resultado.rechazos = reparar_filas(df_raw, cliente)
    df = df.rename(columns=COLUMNAS_EXCEL)
    for col in COLUMNAS_EXCEL.values():
        if col not in df.columns:
            df[col] = None

    for col in COLUMNAS_TEXTO:
        df[col] = df[col].map(_limpiar_texto)
    for col in COLUMNAS_ID:
        df[col] = df[col].map(_limpiar_id)

    df["fecha"] = df["fecha"].map(_a_fecha)
    df["hora"] = df["hora"].map(_a_hora)
    df["no_registro"] = pd.to_numeric(df["no_registro"], errors="coerce")
    for col in ["monto", "comision", "monto_total", "saldo"]:
        df[col] = pd.to_numeric(df[col].map(lambda v: None if _es_vacio(v) else v), errors="coerce")
    df["comision"] = df["comision"].fillna(0.0)

    # --- Filas inválidas (se reportan, no se cargan)
    invalidas = {
        "Fecha inválida": df["fecha"].isna(),
        "No. inválido": df["no_registro"].isna() | (df["no_registro"] % 1 != 0),
        "Sin ID de transacción": df["id_transaccion"].isna(),
        "Monto no numérico": df["monto"].isna(),
    }
    descartar = pd.Series(False, index=df.index)
    for motivo, mascara in invalidas.items():
        nuevas = mascara & ~descartar
        for fila_excel in df.loc[nuevas, "_fila_excel"]:
            resultado.rechazos.append(_rechazo(cliente, fila_excel, motivo))
        descartar |= mascara
    df = df.loc[~descartar].copy()
    df["no_registro"] = df["no_registro"].astype("int64")

    # --- Estado
    estado = df["estado"].map(_limpiar_texto)
    sin_estado = int(estado.isna().sum())
    if sin_estado:
        resultado.advertencias.append(f"{sin_estado} transacciones sin estado -> '{ESTADO_SIN_DATO}'")
    df["estado"] = estado.str.capitalize().fillna(ESTADO_SIN_DATO)
    df["exitosa"] = df["estado"].str.upper().isin(ESTADOS_EFECTIVOS)

    # --- Derivadas
    df["cliente"] = cliente
    df["tipo_persona"] = df["tipo_identificacion"].map(clasificar_tipo_persona)
    df["fecha_hora"] = pd.to_datetime(
        df["fecha"].astype(str) + " " + df["hora"].fillna("00:00:00"), errors="coerce"
    )

    # --- Duplicados exactos de clave natural dentro del archivo: se conserva el último
    clave = ["no_registro", "id_transaccion"]
    duplicados = df.duplicated(clave, keep="last")
    for fila_excel in df.loc[duplicados, "_fila_excel"]:
        resultado.rechazos.append(_rechazo(cliente, fila_excel, "Duplicado (No. + ID) dentro del archivo"))
    df = df.loc[~duplicados]

    df["row_hash"] = (
        pd.util.hash_pandas_object(df[COLUMNAS_NEGOCIO].astype(str), index=False).astype(str)
    )

    resultado.df = df.drop(columns="_fila_excel").reset_index(drop=True)
    return resultado


def leer_excel_maestro(ruta: Path | str) -> list[ResultadoHoja]:
    """Lee todas las hojas del Excel maestro y devuelve una hoja limpia por cliente."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el Excel maestro: {ruta}")

    logger.info("Leyendo %s ...", ruta)
    # dtype=object conserva los valores tal cual vienen de openpyxl
    hojas = pd.read_excel(ruta, sheet_name=None, dtype=object, engine="openpyxl")

    resultados = []
    for nombre_hoja, df_raw in hojas.items():
        cliente = _limpiar_texto(nombre_hoja)
        if df_raw.empty or not cliente:
            logger.warning("Hoja '%s' vacía, se omite", nombre_hoja)
            continue
        df_raw.columns = [_limpiar_texto(c) or f"_col{i}" for i, c in enumerate(df_raw.columns)]
        resultado = limpiar_hoja(df_raw, cliente)
        logger.info(
            "  %-35s leídas=%d válidas=%d reparadas=%d rechazadas=%d",
            cliente, resultado.filas_leidas, len(resultado.df),
            resultado.reparadas, len(resultado.rechazos),
        )
        resultados.append(resultado)

    if not resultados:
        raise ErrorEstructuraExcel(f"El archivo {ruta.name} no contiene hojas con datos")
    return resultados


def leer_csv_cliente(ruta: Path | str, cliente: str) -> list[ResultadoHoja]:
    """Lee el CSV «Historial de pagos» de un solo cliente (exportado desde AdamoPay)."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    cliente = _limpiar_texto(cliente)
    if not cliente:
        raise ErrorEstructuraExcel("Un CSV trae un solo cliente: indique su nombre con --cliente.")

    logger.info("Leyendo %s ...", ruta)
    # Se lee con el módulo csv (no con pandas) para conservar las filas partidas por
    # un salto de línea dentro del nombre: reparar_filas las recompone igual que en el Excel.
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = [fila for fila in csv.reader(f, delimiter=";") if fila]
    if len(filas) < 2:
        raise ErrorEstructuraExcel(f"El archivo {ruta.name} no contiene transacciones")

    columnas = [_limpiar_texto(c) or f"_col{i}" for i, c in enumerate(filas[0])]
    if "FECHA" not in columnas:
        raise ErrorEstructuraExcel(
            f"El archivo {ruta.name} no parece un historial de pagos de AdamoPay "
            "(se esperaba separador punto y coma y la columna FECHA)."
        )
    ancho = len(columnas)
    cuerpo = [(fila + [None] * ancho)[:ancho] for fila in filas[1:]]
    df_raw = pd.DataFrame(cuerpo, columns=columnas, dtype=object)

    resultado = limpiar_hoja(df_raw, cliente)
    logger.info(
        "  %-35s leídas=%d válidas=%d reparadas=%d rechazadas=%d",
        cliente, resultado.filas_leidas, len(resultado.df), resultado.reparadas, len(resultado.rechazos),
    )
    return [resultado]


def leer_archivo(ruta: Path | str, cliente: str | None = None) -> list[ResultadoHoja]:
    """Excel maestro (una hoja por cliente) o CSV de un cliente, según la extensión."""
    if Path(ruta).suffix.lower() == ".csv":
        return leer_csv_cliente(ruta, cliente or "")
    if cliente:
        raise ErrorEstructuraExcel("--cliente solo aplica a archivos CSV; en el Excel cada hoja es un cliente.")
    return leer_excel_maestro(ruta)
