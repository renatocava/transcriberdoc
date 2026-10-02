"""Voces de médicos registradas, para que la diarización los reconozca por nombre.

`gpt-4o-transcribe-diarize` acepta hasta 4 hablantes conocidos, cada uno con
una muestra de 2 a 10 segundos. Las muestras viven en `voces/` (fuera de git):
la voz es un dato biométrico y solo se registra con consentimiento.

En Streamlit Community Cloud el disco se borra al reiniciar la app, así que
allí las voces solo duran hasta el siguiente reinicio.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import re
import uuid
import wave
from pathlib import Path
from typing import Any

CARPETA = Path(__file__).resolve().parent.parent / "voces"
INDICE = CARPETA / "medicos.json"

MAX_CONOCIDOS = 4  # límite de la API
MIN_SEGUNDOS = 3.0  # la API pide 2; un poco más de margen mejora el reconocimiento
MAX_SEGUNDOS = 10.0


def listar() -> list[dict[str, Any]]:
    try:
        return json.loads(INDICE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _guardar_indice(medicos: list[dict[str, Any]]) -> None:
    CARPETA.mkdir(exist_ok=True)
    INDICE.write_text(json.dumps(medicos, ensure_ascii=False, indent=2), encoding="utf-8")


def preparar_wav(audio: bytes) -> tuple[bytes, float]:
    """Valida una muestra WAV y la recorta a 10 s si es más larga.

    Devuelve (wav listo, duración en segundos). Lanza ValueError si no es un
    WAV legible o dura menos de `MIN_SEGUNDOS`.
    """
    try:
        with wave.open(io.BytesIO(audio)) as w:
            params = w.getparams()
            cuadros = w.readframes(params.nframes)
    except (wave.Error, EOFError) as exc:
        raise ValueError("La muestra debe ser un archivo WAV válido.") from exc
    duracion = params.nframes / params.framerate
    if duracion < MIN_SEGUNDOS:
        raise ValueError(f"La muestra dura {duracion:.1f} s; se necesitan al menos {MIN_SEGUNDOS:.0f} s.")
    if duracion <= MAX_SEGUNDOS:
        return audio, duracion
    bytes_por_cuadro = params.sampwidth * params.nchannels
    salida = io.BytesIO()
    with wave.open(salida, "wb") as w:
        w.setparams(params)
        w.writeframes(cuadros[: int(MAX_SEGUNDOS * params.framerate) * bytes_por_cuadro])
    return salida.getvalue(), MAX_SEGUNDOS


def registrar(nombre: str, audio_wav: bytes) -> dict[str, Any]:
    nombre = re.sub(r"\s+", " ", nombre or "").strip()
    if not nombre:
        raise ValueError("Escribe el nombre del médico.")
    medicos = listar()
    if any(m["nombre"].lower() == nombre.lower() for m in medicos):
        raise ValueError(f"Ya hay una voz registrada para «{nombre}». Elimínala primero si quieres reemplazarla.")
    audio, duracion = preparar_wav(audio_wav)
    medico = {
        "id": uuid.uuid4().hex[:8],
        "nombre": nombre,
        "duracion": round(duracion, 1),
        "registrado": dt.datetime.now().isoformat(timespec="minutes"),
        "consentimiento": True,
    }
    CARPETA.mkdir(exist_ok=True)
    (CARPETA / f"{medico['id']}.wav").write_bytes(audio)
    _guardar_indice([*medicos, medico])
    return medico


def eliminar(medico_id: str) -> None:
    (CARPETA / f"{medico_id}.wav").unlink(missing_ok=True)
    _guardar_indice([m for m in listar() if m["id"] != medico_id])


def audio(medico_id: str) -> bytes | None:
    ruta = CARPETA / f"{medico_id}.wav"
    return ruta.read_bytes() if ruta.exists() else None


def referencias(ids: list[str]) -> tuple[list[str], list[str]]:
    """(nombres, muestras como data URL) de los médicos elegidos, para la API."""
    nombres, muestras = [], []
    por_id = {m["id"]: m for m in listar()}
    for medico_id in ids[:MAX_CONOCIDOS]:
        medico, datos = por_id.get(medico_id), audio(medico_id)
        if medico and datos:
            nombres.append(medico["nombre"])
            muestras.append("data:audio/wav;base64," + base64.b64encode(datos).decode())
    return nombres, muestras
