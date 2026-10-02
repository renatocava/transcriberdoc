"""Transcripción con diarización usando gpt-4o-transcribe-diarize (OpenAI)."""

from __future__ import annotations

import io
import re
import string
from typing import Any

from lib.config import api_key, usar_mock
from lib.mock_data import transcripcion_mock

MODELO = "gpt-4o-transcribe-diarize"
_LETRAS = string.ascii_uppercase


def _cliente():
    from openai import OpenAI

    return OpenAI(api_key=api_key("OPENAI_API_KEY"))


def _a_dict(obj: Any) -> Any:
    """Normaliza la respuesta del SDK a estructuras de Python simples."""
    if isinstance(obj, (dict, list, str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


def _letra_para(speaker_id: str, cache: dict[str, str], conocidos: set[str] = frozenset()) -> str:
    """Mapea `speaker_1` -> "A", `speaker_2` -> "B", etc.; los médicos conocidos conservan su nombre."""
    if speaker_id in conocidos:
        return speaker_id
    if speaker_id in cache:
        return cache[speaker_id]
    match = re.search(r"(\d+)\s*$", str(speaker_id))
    if match:
        idx = max(0, int(match.group(1)) - 1)
    else:
        idx = len(cache)
    cache[speaker_id] = _LETRAS[idx % len(_LETRAS)]
    return cache[speaker_id]


def _fusionar(utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une segmentos consecutivos del mismo hablante en una sola intervención."""
    fusionadas: list[dict[str, Any]] = []
    for u in utterances:
        if fusionadas and fusionadas[-1]["speaker"] == u["speaker"]:
            fusionadas[-1]["text"] = f"{fusionadas[-1]['text']} {u['text']}".strip()
            fusionadas[-1]["end"] = u["end"]
        else:
            fusionadas.append(dict(u))
    return fusionadas


def transcribir_audio(
    audio_bytes: bytes,
    filename: str = "consulta.webm",
    conocidos: tuple[list[str], list[str]] | None = None,
) -> dict[str, Any]:
    """Transcribe el audio y devuelve el transcript con sus intervenciones.

    Args:
        conocidos: (nombres, muestras como data URL) de médicos registrados
            (`lib.voces.referencias`). Sus intervenciones llegan con el nombre
            como hablante en lugar de una letra.

    Returns:
        {"transcript_completo": str,
         "utterances": [{"speaker": "A"|"B"|nombre, "text": str, "start": float, "end": float}]}
    """
    nombres, muestras = conocidos or ([], [])
    if usar_mock():
        return transcripcion_mock(medico=nombres[0] if nombres else None)

    if not audio_bytes:
        raise ValueError("No se recibió audio para transcribir.")

    archivo = io.BytesIO(audio_bytes)
    archivo.name = filename  # el SDK necesita un file-like con nombre

    respuesta = _cliente().audio.transcriptions.create(
        model=MODELO,
        file=archivo,
        language="es",
        response_format="diarized_json",
        chunking_strategy="auto",
        **({"known_speaker_names": nombres, "known_speaker_references": muestras} if nombres else {}),
    )

    datos = _a_dict(respuesta)
    if not isinstance(datos, dict):
        datos = {"segments": getattr(respuesta, "segments", []), "text": getattr(respuesta, "text", "")}

    segmentos = datos.get("segments") or datos.get("chunks") or []
    cache: dict[str, str] = {}
    utterances: list[dict[str, Any]] = []

    for seg in segmentos:
        seg = _a_dict(seg)
        if not isinstance(seg, dict):
            continue
        texto = (seg.get("text") or "").strip()
        if not texto:
            continue
        utterances.append(
            {
                "speaker": _letra_para(seg.get("speaker") or "speaker_1", cache, set(nombres)),
                "text": texto,
                "start": float(seg.get("start") or 0.0),
                "end": float(seg.get("end") or 0.0),
            }
        )

    utterances = _fusionar(utterances)

    if not utterances:
        texto_plano = (datos.get("text") or "").strip()
        if not texto_plano:
            raise RuntimeError("La transcripción llegó vacía. Verifica el audio e intenta de nuevo.")
        utterances = [{"speaker": "A", "text": texto_plano, "start": 0.0, "end": 0.0}]

    return {
        "transcript_completo": (datos.get("text") or " ".join(u["text"] for u in utterances)).strip(),
        "utterances": utterances,
    }
