"""Pantalla de procesamiento: transcripción + extracción."""

from __future__ import annotations

import streamlit as st

from lib import state
from lib.extraction import extraer_historia_clinica
from lib.transcription import transcribir_audio


def _render_error() -> None:
    st.error(st.session_state.get("error") or "Ocurrió un error inesperado.")
    _, centro, _ = st.columns([1, 1, 1])
    with centro:
        if st.button("Reintentar", type="primary", use_container_width=True):
            state.reset()
            st.rerun()


def render_processing() -> None:
    if st.session_state.get("error"):
        _render_error()
        return

    state.reproductor_audio()

    resultado = None
    with st.status("Procesando la consulta...", expanded=True) as status:
        try:
            status.update(label="Transcribiendo audio con IA...")
            st.write("Transcribiendo audio con IA...")
            transcripcion = transcribir_audio(
                st.session_state.get("audio_bytes"),
                st.session_state.get("audio_filename", "consulta.webm"),
            )

            status.update(label="Identificando participantes...")
            st.write("Identificando participantes...")
            mapping = state.mapping_desde("Doctor")

            status.update(label="Estructurando información clínica...")
            st.write("Estructurando información clínica...")
            historia = extraer_historia_clinica(transcripcion["utterances"], mapping)

            resultado = (transcripcion, mapping, historia)
            status.update(label="Historia clínica lista", state="complete", expanded=False)
        except Exception as exc:  # la demo nunca debe crashear en vivo
            st.session_state["error"] = f"{type(exc).__name__}: {exc}"
            status.update(label="No se pudo procesar la consulta", state="error")

    if resultado is not None:
        transcripcion, mapping, historia = resultado
        st.session_state["transcription"] = transcripcion
        st.session_state["speaker_mapping"] = mapping
        st.session_state["historia"] = state.ensure_uids(historia)
        state.set_stage(state.REVIEW)

    st.rerun()
