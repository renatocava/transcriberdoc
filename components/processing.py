"""Pantalla de procesamiento: transcripción + extracción."""

from __future__ import annotations

import streamlit as st

from lib import state, voces
from lib.ecografias import es_ecografia
from lib.hablantes import hablantes, mapping_inicial
from lib.extraction import extraer
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
            formato = state.formato()
            eco = es_ecografia(formato)
            conocidos = voces.referencias(state.medicos_consulta())
            transcripcion = transcribir_audio(
                st.session_state.get("audio_bytes"),
                st.session_state.get("audio_filename", "consulta.webm"),
                conocidos=conocidos,
                formato=formato,
            )

            status.update(label="Identificando participantes...")
            mapping = mapping_inicial(
                transcripcion["utterances"], state.modo_hablantes(), conocidos[0],
                interlocutor="Asistente" if eco else "Paciente",
            )
            n = len(hablantes(transcripcion["utterances"]))
            st.write(f"Identificando participantes... {n} {'voz' if n == 1 else 'voces'}")

            paso = "Llenando el informe ecográfico..." if eco else "Estructurando información clínica..."
            status.update(label=paso)
            st.write(paso)
            historia, fuentes = extraer(transcripcion["utterances"], mapping, formato)

            resultado = (transcripcion, mapping, historia, fuentes)
            listo = "Informe listo" if eco else "Historia clínica lista"
            status.update(label=listo, state="complete", expanded=False)
        except Exception as exc:  # la demo nunca debe crashear en vivo
            st.session_state["error"] = f"{type(exc).__name__}: {exc}"
            status.update(label="No se pudo procesar la consulta", state="error")

    if resultado is not None:
        transcripcion, mapping, historia, fuentes = resultado
        st.session_state["transcription"] = transcripcion
        st.session_state["speaker_mapping"] = mapping
        state.recien_extraida(historia)
        st.session_state["fuentes"] = fuentes
        state.set_stage(state.REVIEW)

    st.rerun()
