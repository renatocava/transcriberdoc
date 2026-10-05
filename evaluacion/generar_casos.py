"""Genera dictados sintéticos de ecografía con su respuesta esperada.

    python evaluacion/generar_casos.py                # los 50 casos (10 por formato)
    python evaluacion/generar_casos.py --formato mama # solo un formato
    python evaluacion/generar_casos.py --rehacer abdomen-03

Cada caso es un dictado (médico solo o con su asistente) y lo que el informe
debería decir: estado de cada sección, medidas en la unidad de la plantilla,
hallazgos y datos del paciente. Los escenarios están fijos en ESCENARIOS para
que la cobertura no dependa del azar; Claude Opus 5.5 escribe el dictado y la
respuesta esperada de cada uno.

Las respuestas esperadas salen de un modelo: hay que revisarlas a mano
(evaluacion/casos.md) antes de confiar en el puntaje. Un caso se escribe en
cuanto termina, y los que ya existen no se regeneran.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from lib.config import api_key  # noqa: E402
from lib.ecografias import PLANTILLAS, Plantilla  # noqa: E402

CARPETA = Path(__file__).resolve().parent / "casos"
MODELO = "claude-opus-5-5"

#: (id, instrucción). Los mismos diez escenarios para cada formato.
ESCENARIOS = [
    ("normal_completo",
     "Dictado del médico solo. Estudio completamente normal y el médico dicta TODAS las medidas "
     "que pide la plantilla. NO dicta conclusión."),
    ("hallazgo_simple",
     "Dictado del médico solo. Un hallazgo patológico frecuente en este estudio, con su medida; "
     "el resto normal y con sus medidas. Paciente particular: NO se menciona médico solicitante."),
    ("asistente",
     "Conversación entre el médico y su asistente, que pregunta los datos del paciente y repite "
     "algunas medidas en voz alta para confirmarlas. Un hallazgo."),
    ("medidas_cm",
     "El médico dicta varias medidas en centímetros (o ml) aunque la plantilla use mm (o cc); "
     "en la respuesta esperada van convertidas a la unidad de la plantilla."),
    ("resto_normal",
     "El médico describe con detalle 2 o 3 secciones y luego dice algo inequívoco como «el resto "
     "de órganos, normales». Las secciones cubiertas por esa frase son «normal» y sin medidas. "
     "NO dicta conclusión."),
    ("correccion",
     "El médico se corrige al menos una medida («no, perdón, ...») y quizá un hallazgo. Lo "
     "esperado es siempre el valor corregido."),
    ("omisiones",
     "El médico no menciona en absoluto una o dos secciones (quedan «no_mencionado») y omite "
     "varias medidas de las que sí describe. No dice la edad del paciente ni dicta conclusión."),
    ("multiples_hallazgos",
     "Dos o tres hallazgos en secciones distintas, y el médico dicta su conclusión al final."),
    ("asistente_trampa",
     "El asistente sugiere una medida o un hallazgo y el médico lo corrige o no lo confirma. Lo "
     "que el médico no confirmó NO va en la respuesta esperada."),
    ("coloquial",
     "Dictado coloquial, con muletillas y en un orden distinto al de la plantilla. Menciona al "
     "médico que solicitó el examen por su nombre."),
]

SISTEMA = """\
Eres radiólogo con experiencia en ecografía en Perú y preparas casos de prueba para un \
sistema que llena informes ecográficos a partir de lo que el médico dicta mientras mira el \
monitor del ecógrafo.

Escribe un caso realista: el dictado, tal como lo entregaría un transcriptor automático \
(números casi siempre en cifras, alguna vez en palabras; frases cortas, telegráficas; sin \
etiquetas de hablante dentro del texto), y la respuesta esperada que debe salir de ese \
dictado.

Reglas para la respuesta esperada:
- Una entrada por cada sección de la plantilla, con su clave exacta.
- estado «normal»: el médico la describió como normal o la cubrió con una frase general \
inequívoca. «hallazgo»: describió algo distinto del texto normal de la plantilla. \
«no_mencionado»: no la mencionó de ninguna forma.
- medidas: TODAS las cifras que deben quedar escritas en esa sección del informe, cada una \
por separado (78 x 32 mm son dos medidas: 78 mm y 32 mm), en la unidad de la plantilla \
(mm, cc o %). Si el médico dicta en cm, conviértelo a mm. Incluye las medidas de los \
hallazgos. Nada que el médico no haya dicho: no calcules volúmenes ni porcentajes.
- hallazgo: en una frase, qué debe decir el informe de distinto a lo normal; vacío si el \
estado no es «hallazgo».
- conclusion_dictada: los ítems de conclusión que dictó el médico; vacía si no dictó ninguna.
- Paciente: nombre y edad solo si se dicen; médico solicitante solo si se nombra.

Usa nombres peruanos variados y verosímiles (ficticios). Hallazgos clínicamente coherentes \
con la edad y el sexo del paciente."""


def _esquema(plantilla: Plantilla) -> dict:
    claves = [s.clave for s in plantilla.secciones]
    medida = {
        "type": "object",
        "properties": {"valor": {"type": "number"}, "unidad": {"type": "string", "enum": ["mm", "cc", "%"]}},
        "required": ["valor", "unidad"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "dictado": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rol": {"type": "string", "enum": ["medico", "asistente"]},
                        "texto": {"type": "string"},
                    },
                    "required": ["rol", "texto"],
                    "additionalProperties": False,
                },
            },
            "paciente": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "edad": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                },
                "required": ["nombre", "edad"],
                "additionalProperties": False,
            },
            "medico_solicitante": {"type": "string"},
            "secciones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "clave": {"type": "string", "enum": claves},
                        "estado": {"type": "string", "enum": ["normal", "hallazgo", "no_mencionado"]},
                        "medidas": {"type": "array", "items": medida},
                        "hallazgo": {"type": "string"},
                    },
                    "required": ["clave", "estado", "medidas", "hallazgo"],
                    "additionalProperties": False,
                },
            },
            "conclusion_dictada": {"type": "array", "items": {"type": "string"}},
            "dificultad": {"type": "string"},
        },
        "required": ["dictado", "paciente", "medico_solicitante", "secciones", "conclusion_dictada", "dificultad"],
        "additionalProperties": False,
    }


def _plantilla_texto(plantilla: Plantilla) -> str:
    lineas = [f"Estudio: {plantilla.nombre}. Las medidas pendientes de la plantilla aparecen como ___."]
    for s in plantilla.secciones:
        lineas.append(f"\n[{s.clave}] {s.titulo or s.etiqueta}:\n{s.normal}")
    lineas.append("\nConclusión normal: " + " / ".join(plantilla.conclusion))
    return "\n".join(lineas)


def validar(caso: dict, plantilla: Plantilla) -> list[str]:
    """Problemas de forma del caso; vacío si está bien."""
    problemas = []
    claves = [s["clave"] for s in caso["secciones"]]
    esperadas = [s.clave for s in plantilla.secciones]
    if sorted(claves) != sorted(esperadas):
        problemas.append(f"secciones {claves} != {esperadas}")
    for s in caso["secciones"]:
        if (s["estado"] == "hallazgo") != bool(s["hallazgo"].strip()):
            problemas.append(f"{s['clave']}: estado {s['estado']} con hallazgo {s['hallazgo']!r}")
        if s["estado"] == "no_mencionado" and s["medidas"]:
            problemas.append(f"{s['clave']}: no mencionada pero con medidas")
    if not any(u["rol"] == "medico" for u in caso["dictado"]):
        problemas.append("sin intervenciones del médico")
    return problemas


def generar(cliente, plantilla: Plantilla, escenario: tuple[str, str], previos: list[str]) -> dict:
    nombre, instruccion = escenario
    contenido = (
        f"{_plantilla_texto(plantilla)}\n\nEscenario «{nombre}»: {instruccion}\n\n"
        + ("Pacientes ya usados en otros casos (no los repitas): " + ", ".join(previos) if previos else "")
    )
    respuesta = cliente.beta.messages.create(
        model=MODELO,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _esquema(plantilla)}},
        system=SISTEMA,
        messages=[{"role": "user", "content": contenido}],
    )
    if respuesta.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason={respuesta.stop_reason}")
    texto = next(b.text for b in respuesta.content if b.type == "text")
    datos = json.loads(texto)
    datos["_generacion"] = {
        "modelo": respuesta.model,
        "input_tokens": respuesta.usage.input_tokens,
        "output_tokens": respuesta.usage.output_tokens,
    }
    return datos


def main() -> int:
    import anthropic

    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--formato", choices=list(PLANTILLAS))
    args.add_argument("--rehacer", nargs="*", default=[], help="ids de casos a regenerar")
    opciones = args.parse_args()

    CARPETA.mkdir(exist_ok=True)
    cliente = anthropic.Anthropic(api_key=api_key("ANTHROPIC_API_KEY"))
    gasto_in = gasto_out = 0
    for formato, plantilla in PLANTILLAS.items():
        if opciones.formato and formato != opciones.formato:
            continue
        for i, escenario in enumerate(ESCENARIOS, start=1):
            caso_id = f"{formato}-{i:02d}"
            ruta = CARPETA / f"{caso_id}.json"
            if ruta.exists() and caso_id not in opciones.rehacer:
                continue
            previos = [
                json.loads(p.read_text())["paciente"]["nombre"]
                for p in sorted(CARPETA.glob("*.json")) if p.stem != caso_id
            ]
            for intento in range(3):
                try:
                    datos = generar(cliente, plantilla, escenario, previos)
                except (anthropic.APIStatusError, anthropic.APIConnectionError, RuntimeError, json.JSONDecodeError) as exc:
                    print(f"  {caso_id}: error {type(exc).__name__}: {exc}", file=sys.stderr)
                    continue
                gasto_in += datos["_generacion"]["input_tokens"]
                gasto_out += datos["_generacion"]["output_tokens"]
                problemas = validar(datos, plantilla)
                if problemas:
                    print(f"  {caso_id}: inválido ({'; '.join(problemas)}), reintento", file=sys.stderr)
                    continue
                caso = {"id": caso_id, "formato": formato, "escenario": escenario[0], **datos}
                ruta.write_text(json.dumps(caso, ensure_ascii=False, indent=2) + "\n")
                print(f"{caso_id} ({escenario[0]}): {datos['paciente']['nombre']}, {len(datos['dictado'])} intervenciones")
                break
            else:
                print(f"  {caso_id}: no se pudo generar", file=sys.stderr)
    # Opus 5.5: US$4 / 20 por millón de tokens de entrada / salida.
    print(f"Tokens: {gasto_in} entrada, {gasto_out} salida ≈ US$ {gasto_in * 4e-6 + gasto_out * 2e-5:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
