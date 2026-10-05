"""Datos simulados para desarrollar y ensayar la demo sin llamar a las APIs."""

from __future__ import annotations

from typing import Any

_DIALOGO = [
    ("A", "Buenos días, siéntese por favor. ¿Cómo se llama usted?"),
    ("B", "Buenos días doctor. María Rodríguez Quispe."),
    ("A", "¿Y qué edad tiene, señora María?"),
    ("B", "Treinta y cuatro años."),
    ("A", "Cuénteme, ¿qué la trae por acá?"),
    ("B", "Doctor, tengo un dolor de garganta fuerte desde hace tres días. Me duele "
          "mucho al tragar y anoche sentí fiebre."),
    ("A", "¿Se tomó la temperatura?"),
    ("B", "Sí, treinta y ocho y medio anoche. Tomé un paracetamol y me bajó un poco."),
    ("A", "¿Tos, flema, dolor de oído?"),
    ("B", "Tos no mucha, seca nomás. El oído derecho me molesta un poquito."),
    ("A", "¿Usted sufre de algo? ¿Diabetes, presión alta, asma?"),
    ("B", "No doctor, nada. Solo que soy alérgica a la penicilina, desde chica me sale "
          "roncha."),
    ("A", "Anotado, alergia a penicilina. ¿Está tomando alguna pastilla ahora?"),
    ("B", "Solo el paracetamol que le digo, y unas vitaminas."),
    ("A", "Ya, vamos a revisarla. Abra la boca y diga aaah... Tiene las amígdalas bien "
          "rojas e inflamadas, con placas blancas en la derecha. Los ganglios del cuello "
          "están un poco crecidos y dolorosos."),
    ("A", "La presión está bien. Frecuencia cardiaca ochenta y ocho, temperatura ahorita "
          "treinta y siete ocho, saturación noventa y ocho por ciento."),
    ("B", "¿Es algo grave, doctor?"),
    ("A", "No, señora. Es una faringoamigdalitis, muy probablemente bacteriana por las "
          "placas. Le voy a pedir un hemograma completo y un test rápido de estreptococo "
          "para confirmar."),
    ("A", "Como es alérgica a la penicilina, le voy a dar azitromicina de quinientos "
          "miligramos, una tableta al día por tres días. Y paracetamol de un gramo cada "
          "ocho horas si tiene fiebre o dolor."),
    ("B", "Ya doctor. ¿Algo más que deba hacer?"),
    ("A", "Tome bastante líquido, hagas gárgaras con agua tibia con sal, y repose. Nada "
          "de bebidas heladas. Si le sube la fiebre sobre treinta y nueve o le cuesta "
          "respirar, regresa de emergencia."),
    ("A", "La espero en una semana para control, y me trae los resultados."),
    ("B", "Gracias doctor, muy amable."),
]


#: Dictado de una ecografía de abdomen: el médico (A) y su asistente (B).
_DICTADO_ABDOMEN = [
    ("A", "Ya, empezamos. Paciente Carlos Mendoza Huamán, cincuenta y dos años, viene particular."),
    ("B", "Carlos Mendoza Huamán, cincuenta y dos. ¿Abdomen completo, doctor?"),
    ("A", "Sí, abdomen completo. Hígado normal, el lóbulo derecho mide ciento cuarenta y dos "
          "milímetros."),
    ("A", "Vesícula: setenta y ocho por treinta y dos milímetros, pared de dos milímetros, y "
          "adentro hay un cálculo de doce milímetros con sombra acústica posterior."),
    ("B", "¿Doce milímetros el cálculo?"),
    ("A", "Doce, sí. Colédoco cuatro milímetros, porta once."),
    ("A", "Bazo noventa y ocho milímetros, normal. Páncreas sin alteraciones, la cabeza mide "
          "veintidós."),
    ("A", "Riñón derecho ciento cuatro por cuarenta y ocho, riñón izquierdo ciento siete por "
          "cincuenta, los dos normales."),
    ("A", "Vejiga vacía. Lo demás normal, no hay líquido libre."),
    ("A", "Conclusión: litiasis vesicular única, el resto del abdomen dentro de límites normales."),
]


def _dictado_normal(formato: str) -> list[tuple[str, str]]:
    """Dictado mínimo de un estudio normal, para los formatos sin dictado propio."""
    from lib.ecografias import PLANTILLAS

    nombre = "Jorge Salas Ríos" if formato in ("vesicoprostatica", "vias_urinarias") else "Rosa Flores Vega"
    return [
        ("A", f"Paciente {nombre}, cuarenta y cinco años. {PLANTILLAS[formato].nombre}."),
        ("B", f"{nombre}, cuarenta y cinco años."),
        ("A", "Todo de aspecto normal, sin hallazgos patológicos. Conclusión: estudio normal."),
    ]


def _dialogo(formato: str | None) -> list[tuple[str, str]]:
    if formato == "abdomen":
        return _DICTADO_ABDOMEN
    from lib.ecografias import es_ecografia

    return _dictado_normal(formato) if es_ecografia(formato) else _DIALOGO


def transcripcion_mock(medico: str | None = None, formato: str | None = None) -> dict[str, Any]:
    """Consulta (o dictado del formato de ecografía) simulada; con `medico`, la voz
    del doctor llega con ese nombre (como con voces registradas)."""
    dialogo = _dialogo(formato)
    utterances = []
    t = 0.0
    for speaker, texto in dialogo:
        if medico and speaker == "A":
            speaker = medico
        dur = max(2.0, len(texto) / 14)
        utterances.append(
            {"speaker": speaker, "text": texto, "start": round(t, 2), "end": round(t + dur, 2)}
        )
        t += dur + 0.4
    return {
        "transcript_completo": " ".join(t for _, t in dialogo),
        "utterances": utterances,
    }


def historia_mock() -> dict[str, Any]:
    return {
        "paciente": {"nombre": "María Rodríguez Quispe", "edad": 34, "sexo": "F"},
        "motivo_consulta": "Dolor de garganta intenso de tres días de evolución, asociado a fiebre.",
        "enfermedad_actual": (
            "Paciente refiere odinofagia intensa de tres días de evolución. Anoche presentó "
            "alza térmica de 38.5 °C que cedió parcialmente con paracetamol. Refiere tos seca "
            "escasa y otalgia leve derecha."
        ),
        "antecedentes": {
            "personales": ["Niega diabetes, hipertensión y asma"],
            "alergias": ["Penicilina (erupción cutánea desde la infancia)"],
            "medicamentos_actuales": ["Paracetamol", "Vitaminas"],
        },
        "examen_fisico": {
            "signos_vitales": {
                "presion_arterial": "La presión está bien",
                "frecuencia_cardiaca": "88 lpm",
                "temperatura": "37.8 °C",
                "saturacion_oxigeno": "98%",
            },
            "hallazgos": (
                "Amígdalas eritematosas e inflamadas, con placas blancas en amígdala derecha. "
                "Adenopatías cervicales pequeñas y dolorosas."
            ),
        },
        "diagnosticos": [
            {
                "descripcion": "Faringoamigdalitis aguda, probablemente bacteriana",
                "tipo": "presuntivo",
                "cie10": "J03.9",
                "cie10_alternativas": ["J03.0", "J02.9", "J06.81"],
            },
        ],
        "plan": {
            "medicamentos": [
                {
                    "nombre": "Azitromicina",
                    "dosis": "500 mg",
                    "frecuencia": "1 tableta al día",
                    "duracion": "3 días",
                },
                {
                    "nombre": "Paracetamol",
                    "dosis": "1 g",
                    "frecuencia": "cada 8 horas",
                    "duracion": "condicional a fiebre o dolor",
                },
            ],
            "examenes_solicitados": ["Hemograma completo", "Test rápido de estreptococo"],
            "indicaciones": [
                "Ingesta abundante de líquidos",
                "Gárgaras con agua tibia con sal",
                "Reposo",
                "Evitar bebidas heladas",
                "Acudir a emergencia si fiebre mayor a 39 °C o dificultad respiratoria",
            ],
            "proxima_cita": "Control en una semana con resultados de exámenes",
        },
    }


def fuentes_mock() -> list[dict[str, Any]]:
    """Fuentes de `historia_mock`, numeradas como `_DIALOGO` ([1] = primera línea)."""
    pares = [
        ("paciente.nombre", [2]),
        ("paciente.edad", [3, 4]),
        ("paciente.sexo", [3]),
        ("motivo_consulta", [6]),
        ("enfermedad_actual", [6, 8, 10]),
        ("antecedentes.personales[0]", [11, 12]),
        ("antecedentes.alergias[0]", [12, 13]),
        ("antecedentes.medicamentos_actuales[0]", [14]),
        ("antecedentes.medicamentos_actuales[1]", [14]),
        ("examen_fisico.signos_vitales.presion_arterial", [16]),
        ("examen_fisico.signos_vitales.frecuencia_cardiaca", [16]),
        ("examen_fisico.signos_vitales.temperatura", [16]),
        ("examen_fisico.signos_vitales.saturacion_oxigeno", [16]),
        ("examen_fisico.hallazgos", [15]),
        ("diagnosticos[0]", [18]),
        ("plan.medicamentos[0]", [19, 12]),
        ("plan.medicamentos[1]", [19]),
        ("plan.examenes_solicitados[0]", [18]),
        ("plan.examenes_solicitados[1]", [18]),
        ("plan.indicaciones[0]", [21]),
        ("plan.indicaciones[1]", [21]),
        ("plan.indicaciones[2]", [21]),
        ("plan.indicaciones[3]", [21]),
        ("plan.indicaciones[4]", [21]),
        ("plan.proxima_cita", [22]),
    ]
    return [{"campo": c, "fragmentos": f} for c, f in pares]


def informe_mock(formato: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Informe que devolvería Claude para el dictado simulado del formato, con sus fuentes."""
    from lib.ecografias import PLANTILLAS

    if formato != "abdomen":
        plantilla = PLANTILLAS[formato]
        nombre = _dictado_normal(formato)[1][1].split(",")[0]
        datos = {
            "paciente": {"nombre": nombre, "edad": 45},
            "secciones": {s.clave: s.normal for s in plantilla.secciones},
            "conclusion": list(plantilla.conclusion),
        }
        fuentes = [("paciente.nombre", [1, 2]), ("paciente.edad", [1, 2])]
        fuentes += [(f"secciones.{s.clave}", [3]) for s in plantilla.secciones]
        fuentes += [(f"conclusion[{i}]", [3]) for i in range(len(plantilla.conclusion))]
        return datos, [{"campo": c, "fragmentos": f} for c, f in fuentes]

    datos = {
        "paciente": {"nombre": "Carlos Mendoza Huamán", "edad": 52},
        "medico": "",
        "secciones": {
            "higado": (
                "PARÉNQUIMA HOMOGENEA DE ECOGENICIDAD CONSERVADA Y EN FORMA DIFUSA, DE BORDES "
                "LOBULADOS. NO SE APRECIA DILATACIÓN DE LAS VÍAS BILIARES INTRAHEPÁTICAS.\n"
                "MIDE: LHD: 142 mm"
            ),
            "vesicula": (
                "MIDE: 78 x 32 mm, DE PAREDES DELGADAS DE 2 mm, CON IMAGEN LITIÁSICA DE 12 mm CON "
                "SOMBRA ACÚSTICA POSTERIOR EN SU INTERIOR."
            ),
            "coledoco": "PERMEABLE DE 4 mm.",
            "porta": "NO DILATADA DE 11 mm",
            "bazo": "98 mm DE ECOESTRUCTURA NORMAL.",
            "pancreas": (
                "DE MORFOLOGÍA Y ECOGENICIDAD CONSERVADA, SIN LESIÓN FOCAL CIRCUNSCRITA NI "
                "PROCESOS INFLAMATORIOS, MIDE: 22 mm EN SU PORCION CEFALICA."
            ),
            "rinon_der": PLANTILLAS["abdomen"].secciones[6].lineas[0] + "\nSUS DIMENSIONES SON: 104 x 48 mm.",
            "rinon_izq": PLANTILLAS["abdomen"].secciones[7].lineas[0] + "\nSUS DIMENSIONES SON: 107 x 50 mm.",
            "vejiga": "VACUA, PAREDES DELGADAS, SIN IMÁGENES SOLIDAS NI QUISTICAS EN SU INTERIOR.",
            "genitales": "DE CARACTERES MORFOLOGICOS NORMALES PARA LA EDAD.",
            "douglas": "LIBRE",
            "cavidad": "NO LIQUIDO LIBRE NO MASAS",
        },
        "conclusion": ["LITIASIS VESICULAR ÚNICA.", "RESTO DE ECOGRAFÍA ABDOMINAL DENTRO DE LÍMITES NORMALES."],
    }
    pares = [
        ("paciente.nombre", [1, 2]),
        ("paciente.edad", [1, 2]),
        ("secciones.higado", [3]),
        ("secciones.vesicula", [4, 5, 6]),
        ("secciones.coledoco", [6]),
        ("secciones.porta", [6]),
        ("secciones.bazo", [7]),
        ("secciones.pancreas", [7]),
        ("secciones.rinon_der", [8]),
        ("secciones.rinon_izq", [8]),
        ("secciones.vejiga", [9]),
        # «Lo demás normal» respalda genitales y Douglas; el líquido libre se dijo explícito.
        ("secciones.genitales", [9]),
        ("secciones.douglas", [9]),
        ("secciones.cavidad", [9]),
        ("conclusion[0]", [10]),
        ("conclusion[1]", [10]),
    ]
    return datos, [{"campo": c, "fragmentos": f} for c, f in pares]
