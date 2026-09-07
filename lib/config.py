"""Acceso a secrets y flags de la demo."""

from __future__ import annotations

import os


def _leer(nombre: str) -> str:
    """Busca primero en st.secrets, luego en variables de entorno."""
    try:
        import streamlit as st

        valor = st.secrets.get(nombre)
        if valor:
            return str(valor).strip()
    except Exception:
        pass
    return (os.environ.get(nombre) or "").strip()


def usar_mock() -> bool:
    """True si la demo debe correr con datos simulados (sin llamar APIs)."""
    return _leer("USE_MOCK").lower() in {"1", "true", "yes", "si", "sí"}


def api_key(nombre: str) -> str:
    clave = _leer(nombre)
    if not clave:
        raise RuntimeError(
            f"Falta {nombre}. Agrégala en .streamlit/secrets.toml "
            "(o activa USE_MOCK = true para la demo sin APIs)."
        )
    return clave
