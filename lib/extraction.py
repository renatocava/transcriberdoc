"""Extracción del formulario clínico con Claude (tool use forzado)."""

from __future__ import annotations

from typing import Any

from lib import cie10
from lib.config import api_key, usar_mock
from lib.fuentes import esquema_fuentes, vincular
from lib.hablantes import es_dictado, etiqueta
from lib.mock_data import fuentes_mock, historia_mock
from lib.schema import historia_input_schema, normalizar_historia

MODELO = "claude-sonnet-4-6"
TOOL_NAME = "llenar_historia_clinica"
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


def extraer_historia_clinica(
    utterances: list[dict[str, Any]], mapping: dict[str, str]
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

    respuesta = _cliente().messages.create(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": contenido,
            }
        ],
    )

    for bloque in respuesta.content:
        if getattr(bloque, "type", None) == "tool_use" and bloque.name == TOOL_NAME:
            return _con_fuentes(bloque.input, len(utterances))

    raise RuntimeError("El modelo no devolvió el formulario estructurado. Intenta de nuevo.")
