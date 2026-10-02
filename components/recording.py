"""Pantalla inicial: grabación de la consulta."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from lib import state
from lib.hablantes import AYUDA_MODOS, MODOS

AUDIO_DEMO = Path(__file__).resolve().parent.parent / "assets" / "demo-consulta.mp3"


def _arrancar(audio_bytes: bytes, filename: str, audio_id: str | None = None) -> None:
    st.session_state["audio_bytes"] = audio_bytes
    st.session_state["audio_filename"] = filename
    st.session_state["last_audio_id"] = audio_id
    st.session_state["error"] = None
    state.set_stage(state.PROCESSING)
    st.rerun()


def _guardar_modo() -> None:
    st.session_state[state.CLAVE_MODO] = st.session_state["w_modo"]


def _selector_modo() -> None:
    # El widget se copia a una clave propia porque Streamlit olvida el valor de
    # los widgets que no se dibujan, y este solo existe en la pantalla inicial.
    st.session_state["w_modo"] = state.modo_hablantes()
    modo = st.segmented_control(
        "Participantes",
        options=list(MODOS),
        format_func=MODOS.get,
        key="w_modo",
        required=True,
        on_change=_guardar_modo,
        width="stretch",
    )
    st.caption(AYUDA_MODOS[modo])


def _grabador() -> None:
    try:
        from streamlit_mic_recorder import mic_recorder
    except ImportError:
        st.warning(
            "El componente de grabación no está instalado. "
            "Usa las opciones de demo para continuar."
        )
        return

    audio = mic_recorder(
        start_prompt="🎙️  Iniciar grabación",
        stop_prompt="⏹️  Detener grabación",
        just_once=False,
        use_container_width=True,
        format="webm",
        key="mic",
    )

    # `id` cambia con cada grabación nueva: evita reprocesar la misma al volver a idle.
    if audio and audio.get("bytes") and audio.get("id") != st.session_state.get("last_audio_id"):
        _arrancar(audio["bytes"], "consulta.webm", audio.get("id"))


def render_idle() -> None:
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.markdown(
            "<div style='text-align:center; padding: 2.5rem 0 1.5rem 0;'>"
            "<div style='font-size:3rem;'>🩺</div>"
            "<p style='font-size:1.15rem; color:#334155; margin-top:0.75rem;'>"
            "Presiona el micrófono para grabar la consulta médica.</p></div>",
            unsafe_allow_html=True,
        )
        _selector_modo()
        _grabador()
        st.markdown(
            "<p style='text-align:center; color:#64748B; font-size:0.85rem; margin-top:1rem;'>"
            "La transcripción y el resumen se generan automáticamente al detener la grabación."
            "</p>",
            unsafe_allow_html=True,
        )

        with st.expander("Opciones de demo"):
            if AUDIO_DEMO.exists():
                st.audio(str(AUDIO_DEMO), format="audio/mpeg")
            if st.button("Usar audio pre-grabado", use_container_width=True):
                if AUDIO_DEMO.exists():
                    _arrancar(AUDIO_DEMO.read_bytes(), AUDIO_DEMO.name, f"demo::{AUDIO_DEMO.name}")
                else:
                    st.error(f"No se encontró el archivo `assets/{AUDIO_DEMO.name}`.")

            subido = st.file_uploader(
                "O sube un archivo de audio",
                type=["mp3", "wav", "m4a", "webm", "mp4", "ogg"],
                label_visibility="collapsed",
            )
            if subido is not None:
                if st.button("Procesar archivo subido", type="primary", use_container_width=True):
                    _arrancar(subido.getvalue(), subido.name, f"upload::{subido.name}")
