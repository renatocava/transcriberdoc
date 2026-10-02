"""Cuántas personas hablan en la consulta y qué rol tiene cada voz.

La API de diarización no deja fijar el número de hablantes, así que el modo
elegido antes de grabar se aplica después, al asignar roles a las voces que
detectó el modelo. Sin dependencias de Streamlit: lo usan también las pruebas.
"""

from __future__ import annotations

from typing import Any

AUTO = "auto"
UNO = "1"
DOS = "2"
VARIOS = "3+"

#: Modo -> etiqueta del selector previo a la grabación.
MODOS = {
    AUTO: "Automático",
    UNO: "Solo el médico",
    DOS: "Médico y paciente",
    VARIOS: "Con acompañante",
}

AYUDA_MODOS = {
    AUTO: "Detecta cuántas voces hay y asigna los roles por orden de aparición.",
    UNO: "Dictado: el médico describe la consulta; todo se atribuye al médico.",
    DOS: "Consulta entre médico y paciente.",
    VARIOS: "Médico, paciente y uno o más acompañantes (familiar, intérprete).",
}

ROLES = ["Doctor", "Paciente", "Acompañante", "Otro"]


def hablantes(utterances: list[dict[str, Any]]) -> list[str]:
    """Etiquetas de hablante distintas, en orden de aparición."""
    vistos: list[str] = []
    for u in utterances:
        s = u.get("speaker", "")
        if s and s not in vistos:
            vistos.append(s)
    return vistos


def mapping_inicial(utterances: list[dict[str, Any]], modo: str) -> dict[str, str]:
    """Rol por defecto de cada voz según el modo elegido.

    El primero en hablar se toma como el médico, que es quien suele abrir la
    consulta; el resto se corrige en la pantalla de revisión.
    """
    voces = hablantes(utterances) or ["A"]
    if modo == UNO or len(voces) == 1:
        return {v: "Doctor" for v in voces}

    mapping = {voces[0]: "Doctor", voces[1]: "Paciente"}
    # Con "médico y paciente" una tercera voz suele ser un error de diarización:
    # se marca como "Otro" para que salte a la vista en la revisión.
    resto = "Otro" if modo == DOS else "Acompañante"
    for v in voces[2:]:
        mapping[v] = resto
    return mapping


def es_dictado(mapping: dict[str, str]) -> bool:
    return bool(mapping) and set(mapping.values()) == {"Doctor"}


def etiqueta(speaker: str, mapping: dict[str, str]) -> str:
    """Rol visible de una voz; si dos voces comparten rol se distinguen por letra."""
    rol = mapping.get(speaker, speaker or "Hablante")
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
