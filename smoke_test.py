"""Pruebas de humo de las capas sin UI.

    python smoke_test.py                 # todo en modo mock (sin APIs)
    python smoke_test.py --real          # extracción real con Claude
    python smoke_test.py --real audio.mp3  # transcripción + extracción reales
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    args = sys.argv[1:]
    real = "--real" in args
    audio = next((a for a in args if not a.startswith("--")), None)
    os.environ["USE_MOCK"] = "false" if real else "true"

    from lib.extraction import extraer_historia_clinica, formatear_dialogo
    from lib.mock_data import transcripcion_mock
    from lib.schema import historia_input_schema, normalizar_historia
    from lib.transcription import transcribir_audio

    esquema = historia_input_schema()
    assert "$defs" not in json.dumps(esquema), "quedaron $defs sin aplanar"
    assert "$ref" not in json.dumps(esquema), "quedaron $ref sin aplanar"
    print(f"[1/3] Schema aplanado OK — required: {esquema['required']}")

    if audio:
        with open(audio, "rb") as fh:
            transcripcion = transcribir_audio(fh.read(), os.path.basename(audio))
    else:
        transcripcion = transcripcion_mock()
    print(f"[2/3] Transcripción OK — {len(transcripcion['utterances'])} intervenciones")
    print(formatear_dialogo(transcripcion["utterances"][:4], {"A": "Doctor", "B": "Paciente"}))

    historia = extraer_historia_clinica(transcripcion["utterances"], {"A": "Doctor", "B": "Paciente"})
    historia = normalizar_historia(historia)
    print("[3/3] Extracción OK")
    print(json.dumps(historia, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
