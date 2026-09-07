"""Extracción del formulario clínico con Claude (tool use forzado)."""

from __future__ import annotations

from typing import Any

from lib.config import api_key, usar_mock
from lib.mock_data import historia_mock
from lib.schema import historia_input_schema, normalizar_historia

MODELO = "claude-sonnet-4-6"
TOOL_NAME = "llenar_historia_clinica"
MAX_TOKENS = 4096

SYSTEM_PROMPT = (
    "Eres un asistente médico experto. Analiza la siguiente transcripción de una consulta "
    "y extrae la información en el formulario estructurado usando la herramienta "
    "`llenar_historia_clinica`. Reglas estrictas: (1) Si un campo no se menciona en la "
    "conversación, déjalo vacío, null, o array vacío según corresponda. (2) NUNCA inventes "
    "datos clínicos, medicamentos, dosis, ni diagnósticos. (3) Usa exactamente los términos "
    "que menciona el doctor o el paciente. (4) Para signos vitales, si el doctor dice "
    "'presión bien' sin dar cifra, escribe eso literal."
)


def _cliente():
    import anthropic

    return anthropic.Anthropic(api_key=api_key("ANTHROPIC_API_KEY"))


def formatear_dialogo(utterances: list[dict[str, Any]], mapping: dict[str, str]) -> str:
    """Convierte las intervenciones en un diálogo etiquetado por rol."""
    lineas = []
    for u in utterances:
        rol = mapping.get(u.get("speaker", ""), u.get("speaker", "Hablante"))
        texto = (u.get("text") or "").strip()
        if texto:
            lineas.append(f"{rol}: {texto}")
    return "\n".join(lineas)


def extraer_historia_clinica(
    utterances: list[dict[str, Any]], mapping: dict[str, str]
) -> dict[str, Any]:
    """Devuelve la historia clínica estructurada a partir del transcript."""
    if usar_mock():
        return normalizar_historia(historia_mock())

    dialogo = formatear_dialogo(utterances, mapping)
    if not dialogo.strip():
        raise ValueError("La transcripción está vacía, no hay nada que extraer.")

    tool = {
        "name": TOOL_NAME,
        "description": "Registra la información clínica de la consulta en la historia clínica estructurada.",
        "input_schema": historia_input_schema(),
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
                "content": f"Transcripción de la consulta:\n\n{dialogo}",
            }
        ],
    )

    for bloque in respuesta.content:
        if getattr(bloque, "type", None) == "tool_use" and bloque.name == TOOL_NAME:
            return normalizar_historia(bloque.input)

    raise RuntimeError("El modelo no devolvió el formulario estructurado. Intenta de nuevo.")
