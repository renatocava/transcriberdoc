"""Genera `assets/demo-consulta.mp3` con dos voces sintéticas distintas.

Usa el mismo diálogo que el modo simulado (`lib/mock_data.py`), de modo que la
demo se vea igual con el audio pre-grabado o con USE_MOCK activado.

Requiere `piper` y `ffmpeg` en el PATH, y dos voces en ~/.local/share/piper-voices.

    python scripts/generar_audio_demo.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from lib.mock_data import _DIALOGO  # noqa: E402

VOCES = Path.home() / ".local/share/piper-voices"
SALIDA = RAIZ / "assets" / "demo-consulta.mp3"
TMP = RAIZ / ".audio_tmp"

# speaker -> (modelo, velocidad). Dos timbres claramente distintos para que la
# diarización tenga algo real que separar.
PERFILES = {
    "A": (VOCES / "es_MX-ald-medium.onnx", 1.02),      # Doctor
    "B": (VOCES / "es_MX-claude-high.onnx", 1.08),     # Paciente
}

SILENCIO = 0.45  # segundos entre intervenciones
SAMPLE_RATE = 22050


def _piper(texto: str, modelo: Path, velocidad: float, destino: Path) -> None:
    subprocess.run(
        ["piper", "-m", str(modelo), "-f", str(destino),
         "--length-scale", str(velocidad), "--sentence-silence", "0.35"],
        input=texto, text=True, check=True, capture_output=True,
    )


def _normalizar(origen: Path, destino: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(origen),
         "-ar", str(SAMPLE_RATE), "-ac", "1", str(destino)],
        check=True,
    )


def main() -> int:
    faltantes = [str(m) for m, _ in PERFILES.values() if not m.exists()]
    if faltantes:
        print("Faltan voces de piper:\n  " + "\n  ".join(faltantes))
        print("\nDescárgalas de https://huggingface.co/rhasspy/piper-voices")
        return 1

    TMP.mkdir(exist_ok=True)
    for viejo in TMP.glob("*.wav"):
        viejo.unlink()

    silencio = TMP / "sil.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", str(SILENCIO), str(silencio)],
        check=True,
    )

    piezas: list[Path] = []
    for i, (speaker, texto) in enumerate(_DIALOGO):
        modelo, velocidad = PERFILES[speaker]
        crudo = TMP / f"{i:03d}_raw.wav"
        limpio = TMP / f"{i:03d}.wav"
        _piper(texto, modelo, velocidad, crudo)
        _normalizar(crudo, limpio)
        crudo.unlink()
        piezas.append(limpio)
        print(f"  [{i + 1:>2}/{len(_DIALOGO)}] {speaker} · {texto[:56]}...")

    lista = TMP / "lista.txt"
    lineas = []
    for pieza in piezas:
        lineas.append(f"file '{pieza}'")
        lineas.append(f"file '{silencio}'")
    lista.write_text("\n".join(lineas), encoding="utf-8")

    SALIDA.parent.mkdir(exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(lista), "-b:a", "96k", str(SALIDA)],
        check=True,
    )

    for archivo in TMP.iterdir():
        archivo.unlink()
    TMP.rmdir()

    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(SALIDA)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    print(f"\n{SALIDA.relative_to(RAIZ)} — {float(dur):.0f} s, "
          f"{SALIDA.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
