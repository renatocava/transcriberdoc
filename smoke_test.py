"""Pruebas de humo de las capas sin UI.

    python smoke_test.py                 # todo en modo mock (sin APIs)
    python smoke_test.py --real          # extracción real con Claude (consulta y ecografía)
    python smoke_test.py --real audio.mp3  # transcripción + extracción reales
"""

from __future__ import annotations

import json
import os
import re
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
    print(f"[1/6] Schema aplanado OK — required: {esquema['required']}")

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
    print("[2/6] Asignación de roles y voces de médicos OK")

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
    print("[3/6] Validación de fuentes OK")

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
    print(f"[4/6] Transcripción OK — {len(transcripcion['utterances'])} intervenciones")
    print(formatear_dialogo(transcripcion["utterances"][:4], {"A": "Doctor", "B": "Paciente"}))

    mapping = mapping_inicial(transcripcion["utterances"], AUTO)
    historia, fuentes = extraer_historia_clinica(transcripcion["utterances"], mapping)
    historia = normalizar_historia(historia)
    print(f"[5/6] Extracción OK — {len(fuentes)} campos con fuente")
    print(json.dumps(historia, indent=2, ensure_ascii=False))
    for ruta, f in fuentes.items():
        print(f"  {ruta:<55} <- {', '.join(f'#{i + 1}' for i in f['ids'])}")

    probar_ecografias()
    if not real:
        probar_en_vivo()
    return 0


def probar_en_vivo() -> None:
    """Grabación en vivo (mock): frases desordenadas, repetidas y perdidas."""
    import time

    from lib.en_vivo import SesionEnVivo, palabras_clave
    from lib.hablantes import UNO

    assert "BI-RADS" in palabras_clave("mama") and "mama derecha" in palabras_clave("mama")
    assert "presión arterial" in palabras_clave("consulta")

    turno = lambda seq, texto: {"seq": seq, "texto": texto, "inicio": seq * 4.0, "fin": seq * 4.0 + 3}  # noqa: E731
    s = SesionEnVivo("prueba", "abdomen", UNO, ([], []))
    s.agregar_turnos([turno(1, "Hígado normal.")])  # la 1 llega antes que la 0: se espera
    assert s.utterances() == []
    s.agregar_turnos([turno(0, "Paciente Carlos, 52 años."), turno(1, "repetida"), turno(2, "")])
    assert [u["text"] for u in s.utterances()] == ["Paciente Carlos, 52 años.", "Hígado normal."]  # sin vacías
    limite = time.monotonic() + 10
    while (s.n_extraidas < 2 or s.extrayendo) and time.monotonic() < limite:
        time.sleep(0.05)
    assert s.n_extraidas == 2 and s.historia["plantilla"] == "abdomen", s.n_extraidas
    s.configurar("mama", UNO, ([], []))  # cambiar el formato rehace el informe
    limite = time.monotonic() + 10
    while s.formato_extraido != "mama" and time.monotonic() < limite:
        time.sleep(0.05)
    assert s.historia["plantilla"] == "mama"
    final = s.terminar(3)
    assert final and len(final["transcription"]["utterances"]) == 2 and final["historia"]["plantilla"] == "mama"
    assert all(v == "Doctor" for v in final["mapping"].values())

    s = SesionEnVivo("perdida", "abdomen", UNO, (["Dr. Cava"], ["x"]))
    s.agregar_turnos([turno(0, "Uno."), turno(2, "Tres.")])  # la 1 nunca llegó: hay que procesar el audio
    assert s.utterances()[0]["speaker"] == "Dr. Cava"
    assert s.terminar(3) is None
    print("[7/7] Grabación en vivo OK")


def probar_ecografias() -> None:
    """Informes ecográficos: normalización, cálculos, extracción y Word de los cinco formatos."""
    import io
    import zipfile

    from lib import ecografias as eco
    from lib.extraction import extraer
    from lib.hablantes import AUTO, mapping_inicial
    from lib.informe_docx import generar_docx
    from lib.mock_data import transcripcion_mock

    inf = eco.normalizar_informe("abdomen", {"secciones": {"bazo": "BAZO: 98 mm DE ECOESTRUCTURA NORMAL."}})
    assert inf["secciones"]["bazo"] == "98 mm DE ECOESTRUCTURA NORMAL."  # sin el rótulo repetido
    assert inf["secciones"]["higado"] == eco.PLANTILLAS["abdomen"].secciones[0].normal  # ausente -> normal
    assert inf["medico"] == "" and inf["conclusion"] == list(eco.PLANTILLAS["abdomen"].conclusion)
    bazo = eco.PLANTILLAS["abdomen"].secciones[4]
    assert eco.es_normal(bazo, "98 mm DE ECOESTRUCTURA NORMAL.")
    assert not eco.es_normal(bazo, "98 mm CON IMAGEN NODULAR.")
    avisos = eco.calculos("L: 40 mm AP: 30 mm T: 50 mm VOL APROX. 60 cc")
    assert avisos[0].startswith("Volumen calculado") and "31.2 cc" in avisos[0] and "60 cc" in avisos[0]
    avisos = eco.calculos("PRE MICCIONAL: 300 cc\nPOST MICCIONAL: 36 cc\nRPM: 12 %")
    assert avisos == ["RPM calculado (post / pre): 12 %"], avisos

    # Espacios con nombre: cada ___ tiene nombre y el informe se arma con los valores.
    assert set(eco.espacios("abdomen")) >= {"bazo.longitud", "vesicula.pared", "higado.lhd"}
    assert eco.PLANTILLAS["abdomen"].secciones[4].marcada == "{longitud} mm DE ECOESTRUCTURA NORMAL."
    estado, tocadas = eco.aplicar_cambios("mama", eco.estado_vacio(), {
        "paciente": {"nombre": "Roxana Quispe", "edad": 29},
        "medidas": {"mama_izq.conductos": "2 mm", "mama_der.inventada": "9"},  # la unidad sobra; la ruta no existe
        "hallazgos": {"mama_izq.1": "NÓDULO SÓLIDO DE 14 x 9 mm."},
        "normales": ["mama_der"],
    })
    assert tocadas == ["paciente.nombre", "paciente.edad", "secciones.mama_izq", "secciones.mama_der"], tocadas
    izq = eco.componer("mama", estado)["secciones"]["mama_izq"].split("\n")
    # El hallazgo reemplaza solo su párrafo: los conductos y la axila siguen siendo los de la plantilla.
    assert izq == ["NÓDULO SÓLIDO DE 14 x 9 mm.", "CONDUCTOS GALACTÓFOROS DE DIÁMETROS NORMALES. MIDE: 2 mm",
                   "REGIÓN AXILAR LIBRE DE ADENOPATIAS."], izq
    # Correcciones: "" borra la medida y devuelve el párrafo a lo normal.
    estado, _ = eco.aplicar_cambios("mama", estado, {"medidas": {"mama_izq.conductos": ""}, "hallazgos": {"mama_izq.1": ""}})
    assert eco.componer("mama", estado)["secciones"]["mama_izq"] == eco.PLANTILLAS["mama"].secciones[1].normal
    vp = eco.componer("vesicoprostatica", {**eco.estado_vacio(), "medidas": {"volumenes.rpm": "12"}})
    assert vp["conclusion"][1] == "VEJIGA CON RPM DE 12 %"  # el RPM dictado completa la conclusión normal
    claves = eco.esquema_cambios("mama", False)["properties"]["hallazgos"]["properties"]
    assert list(claves) == ["mama_der.1", "mama_der.2", "mama_der.3", "mama_izq.1", "mama_izq.2", "mama_izq.3"]

    # Vista del informe: lo dictado en verde, lo que falta en ámbar, el resto fijo.
    trozos = eco.resaltar("MIDE: ___ mm, DE PAREDES DELGADAS DE ___ mm.", "MIDE: 78 x 32 mm, DE PAREDES DELGADAS DE ___ mm.")
    assert [t for t in trozos if t[0] != eco.FIJO] == [(eco.DICTADO, "78 x 32"), (eco.FALTA, "___")], trozos
    assert "".join(t for _, t in trozos) == "MIDE: 78 x 32 mm, DE PAREDES DELGADAS DE ___ mm."
    assert eco.resaltar("HOMOGENEA DE ___", "homogénea de ___")[0] == (eco.FIJO, "homogénea de ")
    from lib.informe_html import html_informe
    html = html_informe(inf, {"bazo"})
    assert '<mark class="ok">98</mark>' in html and '<mark class="falta">___</mark>' in html
    assert '<p class=""><b>BAZO:</b>' in html and '<p class="gris"><b>HÍGADO:</b>' in html  # no dictado: gris
    assert "<script" not in html_informe({**inf, "paciente": {"nombre": "<script>x</script>"}})

    # Con --real, Claude llena el informe a partir de los dictados de ejemplo.
    for formato in eco.PLANTILLAS:
        utterances = transcripcion_mock(formato=formato)["utterances"]
        mapping = mapping_inicial(utterances, AUTO, interlocutor="Asistente")
        assert mapping.get("B") == "Asistente"
        informe, fuentes = extraer(utterances, mapping, formato)
        assert informe["plantilla"] == formato and set(informe["secciones"]) == {
            s.clave for s in eco.PLANTILLAS[formato].secciones
        }
        doc = generar_docx(informe)
        xml = zipfile.ZipFile(io.BytesIO(doc)).read("word/document.xml").decode()
        texto = re.sub(r"<[^>]+>", "", xml)
        assert informe["paciente"]["nombre"].upper() in texto
        assert all(c in texto for c in informe["conclusion"])
        print(f"      {formato:<18} {len(fuentes):>2} datos con fuente · Word {len(doc) // 1024} KB")
        if formato == "abdomen":
            print(json.dumps(informe, indent=2, ensure_ascii=False))
    print("[6/6] Informes ecográficos OK")


if __name__ == "__main__":
    raise SystemExit(main())
