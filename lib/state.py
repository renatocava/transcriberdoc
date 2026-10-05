"""Máquina de estados y helpers de session_state."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from typing import Any

import streamlit as st

from lib.ecografias import FORMATO_INICIAL
from lib.hablantes import UNO

IDLE = "idle"
PROCESSING = "processing"
REVIEW = "review"
SAVED = "saved"

#: Claves propias de la app en session_state (todo lo demás es de los widgets).
CLAVES_CORE = (
    "stage",
    "audio_bytes",
    "audio_filename",
    "transcription",
    "speaker_mapping",
    "historia",
    "fuentes",
    "foco",
    "error",
    "last_audio_id",
)

#: Todos los widgets del formulario y del transcript usan este prefijo,
#: para poder limpiarlos de una sola pasada en `reset()`.
PREFIJO_FORM = "f_"

#: Extensión -> MIME, para que `st.audio` reproduzca en el navegador.
MIMES_AUDIO = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
}

_DEFECTOS: dict[str, Any] = {
    "stage": IDLE,
    "audio_bytes": None,
    "audio_filename": "consulta.webm",
    "transcription": None,
    "speaker_mapping": {"A": "Doctor", "B": "Paciente"},
    # Historia clínica o, si lleva la clave "plantilla", informe ecográfico.
    "historia": None,
    "fuentes": {},  # ruta -> {"ids", "valor"}; ver lib/fuentes.py
    "foco": [],  # intervenciones resaltadas en la transcripción
    "error": None,
    "last_audio_id": None,
}


#: Modo de hablantes elegido antes de grabar. Vive fuera de `_DEFECTOS` para
#: que se mantenga entre una consulta y la siguiente.
CLAVE_MODO = "modo_hablantes"


def init_state() -> None:
    for clave, valor in _DEFECTOS.items():
        st.session_state.setdefault(clave, copy.deepcopy(valor))
    st.session_state.setdefault(CLAVE_MODO, UNO)
    st.session_state.setdefault(CLAVE_MEDICOS, [])
    st.session_state.setdefault(CLAVE_FORMATO, FORMATO_INICIAL)


def modo_hablantes() -> str:
    return st.session_state.get(CLAVE_MODO, UNO)


#: Ids de los médicos (voces registradas) presentes en la consulta. Como el
#: modo, se mantiene entre consultas.
CLAVE_MEDICOS = "medicos_consulta"


def medicos_consulta() -> list[str]:
    return list(st.session_state.get(CLAVE_MEDICOS, []))


#: Formato de salida elegido antes de grabar: historia clínica o una de las
#: plantillas de ecografía (lib/ecografias.py). Se mantiene entre consultas.
CLAVE_FORMATO = "formato_salida"


def formato() -> str:
    return st.session_state.get(CLAVE_FORMATO, FORMATO_INICIAL)


def stage() -> str:
    return st.session_state.get("stage", IDLE)


def set_stage(nuevo: str) -> None:
    st.session_state["stage"] = nuevo


def reset() -> None:
    """Limpia la consulta actual y vuelve a `idle`.

    Borra también los widgets del formulario, pero deja intacto el estado
    interno de `mic_recorder` para no romper el componente.
    """
    for clave in list(st.session_state.keys()):
        if str(clave).startswith(PREFIJO_FORM):
            del st.session_state[clave]
    for clave, valor in _DEFECTOS.items():
        st.session_state[clave] = copy.deepcopy(valor)


def nuevo_uid() -> str:
    return uuid.uuid4().hex[:8]


def ensure_uids(historia: dict[str, Any]) -> dict[str, Any]:
    """Asigna un id estable a cada ítem de las listas editables.

    Las keys de los widgets se derivan de este id y no del índice; así, borrar
    un ítem del medio no hace que el siguiente herede sus valores.
    """
    historia = copy.deepcopy(historia or {})
    listas = [
        historia.setdefault("diagnosticos", []),
        historia.setdefault("plan", {}).setdefault("medicamentos", []),
    ]
    for lista in listas:
        for item in lista:
            if isinstance(item, dict) and not item.get("_uid"):
                item["_uid"] = nuevo_uid()
    return historia


def strip_uids(obj: Any) -> Any:
    """Copia la estructura sin las claves internas (`_uid`, `_fuentes`), lista para exportar."""
    if isinstance(obj, dict):
        return {k: strip_uids(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [strip_uids(item) for item in obj]
    return obj


def mime_audio(filename: str) -> str:
    """MIME del audio en curso; por defecto webm, que es lo que graba el micrófono."""
    return MIMES_AUDIO.get(Path(filename or "").suffix.lower(), "audio/webm")


def reproductor_audio() -> None:
    """Muestra el reproductor del audio de la consulta actual, si lo hay."""
    import streamlit as st  # import local: evita ciclos al importar el módulo

    audio = st.session_state.get("audio_bytes")
    if audio:
        st.audio(audio, format=mime_audio(st.session_state.get("audio_filename", "")))
