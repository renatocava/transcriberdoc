"""Extracción del formulario clínico con Claude (tool use forzado)."""

from __future__ import annotations

from typing import Any

from lib import cie10, ecografias
from lib.config import api_key, usar_mock
from lib.fuentes import esquema_fuentes, vincular
from lib.hablantes import es_dictado, etiqueta
from lib.mock_data import fuentes_mock, historia_mock, informe_mock
from lib.schema import historia_input_schema, normalizar_historia

MODELO = "claude-sonnet-4-6"
TOOL_NAME = "llenar_historia_clinica"
TOOL_ECO = "llenar_informe_ecografico"
MAX_TOKENS = 8192  # el formulario más las fuentes de cada dato

SYSTEM_PROMPT = (
    "Eres un asistente médico experto. Analiza la siguiente transcripción de una consulta "
    "y extrae la información en el formulario estructurado usando la herramienta "
    "`llenar_historia_clinica`. Reglas estrictas: (1) Si un campo no se menciona en la "
    "conversación, déjalo vacío, null, o array vacío según corresponda. (2) NUNCA inventes "
    "datos clínicos, medicamentos, dosis, ni diagnósticos. (3) Usa exactamente los términos "
    "que menciona el doctor o el paciente. (4) Para signos vitales, si el doctor dice "
    "'presión bien' sin dar cifra, escribe eso literal. (5) Si participa un acompañante, "
    "lo que cuenta sobre el paciente es válido para la historia, pero los datos de "
    "identificación (nombre, edad, sexo) son siempre los del paciente. (6) Cada intervención "
    "lleva un número [n]. En `fuentes` registra, para CADA dato que llenes, los números de "
    "las intervenciones de donde sale; si un dato no tiene respaldo en ninguna, no lo llenes. "
    "(7) Para cada diagnóstico propone el código CIE-10 más específico que permita lo que se "
    "dijo y hasta 3 alternativas; si no estás seguro, deja `cie10` vacío: el médico lo elegirá."
)

SYSTEM_ECO = (
    "Eres un asistente de ecografía. El médico dicta, o conversa con su asistente o "
    "transcriptor, lo que va viendo en el monitor del ecógrafo. Llena el informe de "
    "{examen} con la herramienta `llenar_informe_ecografico`. Reglas estrictas: "
    "(1) Cada sección parte de su texto normal de plantilla, que está en la descripción del "
    "campo. Reemplaza cada ___ por la medida dictada, en la unidad de la plantilla (si dicta "
    "en centímetros, pásalo a milímetros; ml equivale a cc). Si da dos o tres diámetros para "
    "un mismo ___, escríbelos como «78 x 32». (2) Si el médico describe algo distinto de lo "
    "normal, reescribe solo esa parte del texto, en el mismo estilo (MAYÚSCULAS, frases "
    "cortas) y conserva el resto tal cual. (3) Si una medida no se dicta, deja ___. NUNCA "
    "inventes medidas ni hallazgos, y no calcules volúmenes ni porcentajes que el médico no "
    "dijo. (4) Si una sección no se menciona, devuelve su texto normal sin cambios y no le "
    "pongas fuente. Si el médico dice algo general («el resto normal»), esa intervención es "
    "la fuente de las secciones que abarca. (5) Conclusión: la que dicte el médico, un ítem "
    "por línea. Si no dicta ninguna, propón una breve y coherente con los hallazgos (o la "
    "conclusión normal de la plantilla si todo es normal) y no le pongas fuente. "
    "(6) Los hallazgos los da el Doctor; lo que pregunta o repite el asistente solo vale si "
    "el Doctor lo confirma. (7) Paciente: nombre y edad en años si se dictan. Médico "
    "solicitante: solo si se menciona. (8) Cada intervención lleva un número [n]. En "
    "`fuentes` registra, para cada dato que llenes, los números de las intervenciones de "
    "donde sale. Rutas: 'paciente.nombre', 'paciente.edad', 'medico', "
    "'secciones.<clave>' (por ejemplo 'secciones.{ejemplo}') y 'conclusion[0]'."
)

CONTEXTO_DICTADO = (
    "Modalidad: dictado. Solo habla el médico, que describe la consulta y al paciente "
    "en tercera persona."
)


def _cliente():
    import anthropic

    return anthropic.Anthropic(api_key=api_key("ANTHROPIC_API_KEY"))


def formatear_dialogo(
    utterances: list[dict[str, Any]], mapping: dict[str, str], numerar: bool = False
) -> str:
    """Convierte las intervenciones en un diálogo etiquetado por rol.

    Con `numerar`, cada línea lleva `[n]` (índice + 1) para que el modelo pueda
    citar de dónde sale cada dato.
    """
    lineas = []
    for i, u in enumerate(utterances, start=1):
        rol = etiqueta(u.get("speaker", ""), mapping)
        texto = (u.get("text") or "").strip()
        if texto:
            lineas.append(f"[{i}] {rol}: {texto}" if numerar else f"{rol}: {texto}")
    return "\n".join(lineas)


def _con_fuentes(
    datos: dict[str, Any], n_utterances: int
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    datos = dict(datos or {})
    fuentes = datos.pop("fuentes", None) or []
    historia = normalizar_historia(datos)
    _validar_cie10(historia)
    return historia, vincular(historia, fuentes, n_utterances)


def _validar_cie10(historia: dict[str, Any]) -> None:
    """Deja solo códigos del catálogo oficial; lo descartado queda como aviso.

    La propuesta y las alternativas válidas quedan en `_cie10_sugeridos`
    (interno, no se exporta) para ofrecerlas siempre en el selector.
    """
    for dx in historia.get("diagnosticos", []):
        alternativas = dx.pop("cie10_alternativas", None) or []
        if not cie10.disponible():
            continue
        codigo, aviso = cie10.validar(dx.get("cie10", ""))
        dx["cie10"] = codigo
        if aviso:
            dx["_cie10_aviso"] = aviso
        validas = [cie10.validar(a)[0] for a in alternativas]
        dx["_cie10_sugeridos"] = list(dict.fromkeys(c for c in [codigo, *validas[:3]] if c))


def _llamar(system: str, contenido: str, tool: dict[str, Any], modelo: str | None = None) -> dict[str, Any]:
    """Llama a Claude forzando el tool y devuelve su input."""
    respuesta = _cliente().messages.create(
        model=modelo or MODELO,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": contenido}],
    )
    for bloque in respuesta.content:
        if getattr(bloque, "type", None) == "tool_use" and bloque.name == tool["name"]:
            return bloque.input
    raise RuntimeError("El modelo no devolvió el formulario estructurado. Intenta de nuevo.")


def extraer(
    utterances: list[dict[str, Any]],
    mapping: dict[str, str],
    formato: str = ecografias.CONSULTA,
    modelo: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Historia clínica o informe ecográfico, según el formato elegido.

    `modelo` cambia el modelo de Claude (la vista en vivo usa uno más rápido).
    """
    if ecografias.es_ecografia(formato):
        return extraer_informe_ecografico(utterances, mapping, formato, modelo)
    return extraer_historia_clinica(utterances, mapping, modelo)


def extraer_informe_ecografico(
    utterances: list[dict[str, Any]], mapping: dict[str, str], formato: str, modelo: str | None = None
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Informe ecográfico del formato dado y el mapa de fuentes de cada dato."""
    if usar_mock():
        datos, fuentes = informe_mock(formato)
    else:
        dialogo = formatear_dialogo(utterances, mapping, numerar=True)
        if not dialogo.strip():
            raise ValueError("La transcripción está vacía, no hay nada que extraer.")
        plantilla = ecografias.PLANTILLAS[formato]
        esquema = ecografias.input_schema(formato)
        esquema["properties"]["fuentes"] = esquema_fuentes()
        esquema["required"].append("fuentes")
        tool = {
            "name": TOOL_ECO,
            "description": f"Registra el informe de {plantilla.nombre.lower()} con lo que dictó el médico.",
            "input_schema": esquema,
        }
        system = SYSTEM_ECO.format(examen=plantilla.nombre.lower(), ejemplo=plantilla.secciones[0].clave)
        datos = _llamar(system, f"Transcripción del estudio:\n\n{dialogo}", tool, modelo)
        datos = dict(datos or {})
        fuentes = datos.pop("fuentes", None) or []
    informe = ecografias.normalizar_informe(formato, datos)
    return informe, vincular(informe, fuentes, len(utterances))


def extraer_historia_clinica(
    utterances: list[dict[str, Any]], mapping: dict[str, str], modelo: str | None = None
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Devuelve la historia clínica estructurada y el mapa de fuentes de cada dato."""
    if usar_mock():
        return _con_fuentes({**historia_mock(), "fuentes": fuentes_mock()}, len(utterances))

    dialogo = formatear_dialogo(utterances, mapping, numerar=True)
    if not dialogo.strip():
        raise ValueError("La transcripción está vacía, no hay nada que extraer.")

    contenido = f"Transcripción de la consulta:\n\n{dialogo}"
    if es_dictado(mapping):
        contenido = f"{CONTEXTO_DICTADO}\n\n{contenido}"

    esquema = historia_input_schema()
    esquema["properties"]["fuentes"] = esquema_fuentes()
    esquema["required"] = [*esquema.get("required", []), "fuentes"]

    tool = {
        "name": TOOL_NAME,
        "description": "Registra la información clínica de la consulta en la historia clínica estructurada.",
        "input_schema": esquema,
    }

    return _con_fuentes(_llamar(SYSTEM_PROMPT, contenido, tool, modelo), len(utterances))
