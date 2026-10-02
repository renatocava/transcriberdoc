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


def transcripcion_mock(medico: str | None = None) -> dict[str, Any]:
    """Consulta simulada; con `medico`, la voz del doctor llega con ese nombre (como con voces registradas)."""
    utterances = []
    t = 0.0
    for speaker, texto in _DIALOGO:
        if medico and speaker == "A":
            speaker = medico
        dur = max(2.0, len(texto) / 14)
        utterances.append(
            {"speaker": speaker, "text": texto, "start": round(t, 2), "end": round(t + dur, 2)}
        )
        t += dur + 0.4
    return {
        "transcript_completo": " ".join(t for _, t in _DIALOGO),
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
