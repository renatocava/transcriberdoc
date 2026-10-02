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
    from lib.fuentes import vincular
    from lib.hablantes import AUTO, DOS, UNO, es_dictado, mapping_inicial
    from lib.mock_data import transcripcion_mock
    from lib.schema import historia_input_schema, normalizar_historia
    from lib.transcription import transcribir_audio

    esquema = historia_input_schema()
    assert "$defs" not in json.dumps(esquema), "quedaron $defs sin aplanar"
    assert "$ref" not in json.dumps(esquema), "quedaron $ref sin aplanar"
    print(f"[1/5] Schema aplanado OK — required: {esquema['required']}")

    voces = lambda *s: [{"speaker": x, "text": "t"} for x in s]  # noqa: E731
    assert es_dictado(mapping_inicial(voces("A"), AUTO))
    assert es_dictado(mapping_inicial(voces("A", "B"), UNO))
    assert mapping_inicial(voces("A", "B", "C"), AUTO)["C"] == "Acompañante"
    assert mapping_inicial(voces("A", "B", "C"), DOS)["C"] == "Otro"
    # Con un médico reconocido por su voz, él es el Doctor aunque no hable primero.
    m = mapping_inicial(voces("A", "Dr. Hurtado", "B"), AUTO, ["Dr. Hurtado"])
    assert m == {"Dr. Hurtado": "Doctor", "A": "Paciente", "B": "Acompañante"}
    from lib.hablantes import etiqueta
    assert etiqueta("Dr. Hurtado", m) == "Doctor (Dr. Hurtado)" and etiqueta("A", m) == "Paciente"

    import io, tempfile, wave
    from pathlib import Path
    from lib import voces as registro_voces

    def wav(segundos: float) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b"\0\0" * int(16000 * segundos))
        return buf.getvalue()

    assert registro_voces.preparar_wav(wav(14))[1] == registro_voces.MAX_SEGUNDOS  # recorta a 10 s
    try:
        registro_voces.preparar_wav(wav(1.5))
        raise AssertionError("debió rechazar una muestra de 1,5 s")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        registro_voces.CARPETA, registro_voces.INDICE = Path(tmp), Path(tmp) / "medicos.json"
        medico = registro_voces.registrar("Dr. Prueba", wav(5))
        nombres, muestras = registro_voces.referencias([medico["id"]])
        assert nombres == ["Dr. Prueba"] and muestras[0].startswith("data:audio/wav;base64,")
        registro_voces.eliminar(medico["id"])
        assert registro_voces.listar() == []
    print("[2/5] Asignación de roles y voces de médicos OK")

    h = {"paciente": {"nombre": "Ana"}, "diagnosticos": [{"descripcion": "X", "tipo": "presuntivo"}],
         "antecedentes": {"alergias": ["Penicilina"]}}
    mapa = vincular(h, [
        {"campo": "paciente.nombre", "fragmentos": [2]},
        {"campo": "diagnosticos[0]", "fragmentos": [3, 99]},  # 99 fuera de rango
        {"campo": "antecedentes.alergias[0]", "fragmentos": [1]},
        {"campo": "plan.inventado", "fragmentos": [1]},  # ruta inexistente
        {"campo": "paciente.edad", "fragmentos": [0]},  # número inválido
    ], n_utterances=5)
    assert mapa["paciente.nombre"]["ids"] == [1]
    assert h["diagnosticos"][0]["_fuentes"]["ids"] == [2]
    assert mapa["antecedentes.alergias::Penicilina"]["ids"] == [0]
    assert set(mapa) == {"paciente.nombre", "antecedentes.alergias::Penicilina"}
    print("[3/5] Validación de fuentes OK")

    from lib import cie10
    if cie10.disponible():
        assert cie10.obtener("j03.9")["descripcion"] == "AMIGDALITIS AGUDA, NO ESPECIFICADA"
        assert cie10.obtener("I10X")["codigo"] == "I10X"
        assert not cie10.es_valido("I84.9")  # cese de uso, RM 447-2024
        assert cie10.obtener("Z99.99") is None
        assert cie10.buscar("amígdalitis estreptocócica")[0]["codigo"] == "J03.0"
        from lib.extraction import _validar_cie10
        h = {"diagnosticos": [
            {"descripcion": "a", "cie10": "j03.9", "cie10_alternativas": ["J99.99", "J03.0"]},
            {"descripcion": "b", "cie10": "I84.9"},  # cesado
        ]}
        _validar_cie10(h)
        assert h["diagnosticos"][0]["cie10"] == "J03.9"
        assert h["diagnosticos"][0]["_cie10_sugeridos"] == ["J03.9", "J03.0"]
        assert h["diagnosticos"][1]["cie10"] == "" and "RM 447-2024" in h["diagnosticos"][1]["_cie10_aviso"]
        meta = cie10.procedencia()
        print(f"      Catálogo CIE-10 OK — {meta['codigos_vigentes']} códigos, sha256 {meta['sha256'][:12]}…")
    else:
        print("      Catálogo CIE-10 no generado (scripts/construir_cie10.py)")

    if audio:
        with open(audio, "rb") as fh:
            transcripcion = transcribir_audio(fh.read(), os.path.basename(audio))
    else:
        transcripcion = transcripcion_mock()
    print(f"[4/5] Transcripción OK — {len(transcripcion['utterances'])} intervenciones")
    print(formatear_dialogo(transcripcion["utterances"][:4], {"A": "Doctor", "B": "Paciente"}))

    mapping = mapping_inicial(transcripcion["utterances"], AUTO)
    historia, fuentes = extraer_historia_clinica(transcripcion["utterances"], mapping)
    historia = normalizar_historia(historia)
    print(f"[5/5] Extracción OK — {len(fuentes)} campos con fuente")
    print(json.dumps(historia, indent=2, ensure_ascii=False))
    for ruta, f in fuentes.items():
        print(f"  {ruta:<55} <- {', '.join(f'#{i + 1}' for i in f['ids'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
