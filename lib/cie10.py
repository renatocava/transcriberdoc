"""Consulta del catálogo CIE-10 oficial del MINSA (data/cie10.sqlite).

El archivo lo genera `scripts/construir_cie10.py` a partir del Excel que
publica el MINSA en REUNIS. Los códigos se guardan sin punto, como en el HIS
(`J039`), y se muestran con punto (`J03.9`).
"""

from __future__ import annotations

import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

DB = Path(__file__).resolve().parent.parent / "data" / "cie10.sqlite"

_PATRON_CODIGO = re.compile(r"^[A-Za-z]\d{2}(\.?\w)?$|^[A-Za-z]\d{0,2}$")


def normalizar(codigo: str) -> str:
    """`j03.9`, `J03-9`, ` J039 ` -> `J039`."""
    return re.sub(r"[^A-Z0-9]", "", str(codigo or "").upper())


def formatear(codigo: str) -> str:
    """`J039` -> `J03.9`. Los de 3 caracteres y los rellenos con X del HIS (`I10X`) quedan igual."""
    c = normalizar(codigo)
    if len(c) <= 3 or c[3] == "X":
        return c
    return f"{c[:3]}.{c[3:]}"


@lru_cache(maxsize=1)
def _conexion() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(
            f"No existe {DB.name}. Genéralo con: python scripts/construir_cie10.py <CIE10_MINSA_OFICIAL.xlsx>"
        )
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def disponible() -> bool:
    return DB.exists()


def _fila(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {"codigo": formatear(row["codigo"]), "descripcion": row["descripcion"], "vigente": bool(row["vigente"])}


def obtener(codigo: str) -> dict[str, Any] | None:
    """Código y descripción oficial, o None si no existe en el catálogo."""
    row = _conexion().execute(
        "SELECT codigo, descripcion, vigente FROM codigos WHERE codigo = ?", (normalizar(codigo),)
    ).fetchone()
    return _fila(row)


def es_valido(codigo: str) -> bool:
    """True si el código existe y está vigente (no dado de baja por la RM 447-2024)."""
    fila = obtener(codigo)
    return bool(fila and fila["vigente"])


def validar(codigo: str) -> tuple[str, str | None]:
    """Código propuesto -> (código oficial formateado o "", aviso para el médico)."""
    if not str(codigo or "").strip():
        return "", None
    fila = obtener(codigo)
    if fila is None:
        return "", f"Se propuso «{codigo}», que no existe en el catálogo CIE-10 del MINSA."
    if not fila["vigente"]:
        return "", (
            f"Se propuso {fila['codigo']} ({fila['descripcion'].lower()}), "
            "dado de baja por la RM 447-2024-MINSA."
        )
    return fila["codigo"], None


def buscar(texto: str, limite: int = 20, solo_vigentes: bool = True) -> list[dict[str, Any]]:
    """Busca por código (`J03`, `J03.9`) o por palabras (`amigdalitis aguda`).

    Las palabras se buscan por prefijo y sin distinguir tildes ni mayúsculas.
    """
    texto = (texto or "").strip()
    if not texto:
        return []
    filtro = "AND c.vigente = 1" if solo_vigentes else ""
    con = _conexion()

    if _PATRON_CODIGO.match(texto):
        rows = con.execute(
            f"SELECT codigo, descripcion, vigente FROM codigos c WHERE codigo LIKE ? {filtro} "
            "ORDER BY length(codigo), codigo LIMIT ?",
            (normalizar(texto) + "%", limite),
        ).fetchall()
        if rows:
            return [_fila(r) for r in rows]

    palabras = re.findall(r"\w+", texto)
    if not palabras:
        return []
    consulta = " ".join(f'"{p}"*' for p in palabras)
    rows = con.execute(
        f"SELECT c.codigo, c.descripcion, c.vigente FROM codigos_fts f "
        f"JOIN codigos c ON c.id = f.rowid WHERE codigos_fts MATCH ? {filtro} "
        "ORDER BY bm25(codigos_fts), length(c.codigo) LIMIT ?",
        (consulta, limite),
    ).fetchall()
    return [_fila(r) for r in rows]


def procedencia() -> dict[str, str]:
    """Metadatos de origen del catálogo (fuente, URL, sha256, fecha de descarga...)."""
    return {r["clave"]: r["valor"] for r in _conexion().execute("SELECT clave, valor FROM meta")}
