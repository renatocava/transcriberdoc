"""Cuántas personas hablan en la consulta y qué rol tiene cada voz.

La API de diarización no deja fijar el número de hablantes, así que el modo
se aplica después, al asignar roles a las voces que detectó el modelo. La app
ya no lo pregunta: la ecografía es un dictado (UNO) y en la consulta se
detectan las voces (AUTO); ver `state.modo_hablantes`.
Sin dependencias de Streamlit: lo usan también las pruebas.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

AUTO = "auto"
UNO = "1"
DOS = "2"
VARIOS = "3+"

ROLES = ["Doctor", "Paciente", "Asistente", "Acompañante", "Otro"]


def hablantes(utterances: list[dict[str, Any]]) -> list[str]:
    """Etiquetas de hablante distintas, en orden de aparición."""
    vistos: list[str] = []
    for u in utterances:
        s = u.get("speaker", "")
        if s and s not in vistos:
            vistos.append(s)
    return vistos


def es_nombre(speaker: str) -> bool:
    """True si la voz llegó con el nombre de un médico registrado (no una letra)."""
    return not re.fullmatch(r"[A-Z]?", speaker or "")


def mapping_inicial(
    utterances: list[dict[str, Any]],
    modo: str,
    medicos: Iterable[str] = (),
    interlocutor: str = "Paciente",
) -> dict[str, str]:
    """Rol por defecto de cada voz según el modo elegido.

    Los médicos reconocidos por su voz son «Doctor». Si no hay ninguno, el
    primero en hablar se toma como el médico, que es quien suele abrir la
    consulta. La siguiente voz es el `interlocutor`: el paciente en una
    consulta, el asistente que transcribe en una ecografía. El resto se
    corrige en la pantalla de revisión.
    """
    voces = hablantes(utterances) or ["A"]
    if modo == UNO or len(voces) == 1:
        return {v: "Doctor" for v in voces}

    reconocidos = [v for v in voces if v in set(medicos)]
    otros = [v for v in voces if v not in reconocidos]
    if not reconocidos:
        reconocidos, otros = otros[:1], otros[1:]
    mapping = {v: "Doctor" for v in reconocidos}
    # Con "médico y paciente" una voz de más suele ser un error de diarización:
    # se marca como "Otro" para que salte a la vista en la revisión.
    resto = "Otro" if modo == DOS else "Acompañante"
    for i, v in enumerate(otros):
        mapping[v] = interlocutor if i == 0 else resto
    return mapping


def es_dictado(mapping: dict[str, str]) -> bool:
    return bool(mapping) and set(mapping.values()) == {"Doctor"}


def etiqueta(speaker: str, mapping: dict[str, str]) -> str:
    """Rol visible de una voz: «Doctor (Dr. Hurtado)» si se reconoció por su voz;
    si dos voces sin nombre comparten rol, se distinguen por letra."""
    rol = mapping.get(speaker, speaker or "Hablante")
    if es_nombre(speaker):
        return f"{rol} ({speaker})"
    if es_dictado(mapping):
        return rol
    if sum(1 for r in mapping.values() if r == rol) > 1:
        return f"{rol} {speaker}"
    return rol


def aviso(n_voces: int, modo: str) -> str | None:
    """Mensaje si las voces detectadas no cuadran con el modo elegido."""
    if modo == UNO and n_voces > 1:
        return (
            f"Se detectaron {n_voces} voces, pero elegiste «Solo el médico»: "
            "todo se atribuyó al médico."
        )
    if modo == DOS and n_voces > 2:
        return (
            f"Se detectaron {n_voces} voces, pero elegiste «Médico y paciente». "
            "Revisa las voces marcadas como «Otro»."
        )
    if modo in (DOS, VARIOS) and n_voces == 1:
        return "Solo se detectó una voz: se trató como dictado del médico."
    if modo == VARIOS and n_voces == 2:
        return "Solo se detectaron dos voces: no se identificó ningún acompañante."
    return None
