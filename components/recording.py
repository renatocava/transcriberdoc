"""Pantalla inicial: grabación de la consulta."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from components.medicos import gestion_voces, selector_medicos
from lib import state
from lib.ecografias import FORMATOS, PLANTILLAS, es_ecografia, normalizar_informe
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


def _guardar_formato() -> None:
    st.session_state[state.CLAVE_FORMATO] = st.session_state["w_formato"]


def _selector_formato() -> None:
    # Misma copia a clave propia que el modo (ver _selector_modo).
    st.session_state["w_formato"] = state.formato()
    st.selectbox(
        "Formato de salida",
        options=list(FORMATOS),
        format_func=FORMATOS.get,
        key="w_formato",
        on_change=_guardar_formato,
        help="Historia clínica de una consulta, o el informe de una ecografía con su plantilla.",
    )


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


def _vista_previa() -> None:
    """El formato elegido, vacío: cambia en cuanto se elige otro en el selector."""
    formato = state.formato()
    with st.container(border=True):
        if es_ecografia(formato):
            from components.informe_eco import vista_informe  # import local: evita el ciclo

            vista_informe(normalizar_informe(formato, {}), set(), f"{PLANTILLAS[formato].nombre} · vista previa")
            st.caption("Al detener la grabación, lo dictado reemplaza los espacios en ámbar.")
        else:
            st.markdown("**📄 Historia clínica · vista previa**")
            st.markdown(
                "- Datos del paciente\n- Motivo de consulta y enfermedad actual\n- Antecedentes\n"
                "- Examen físico y signos vitales\n- Diagnósticos con su código CIE-10\n"
                "- Plan: medicamentos, exámenes e indicaciones"
            )
            st.caption("Se llena con lo conversado al detener la grabación.")


def render_idle() -> None:
    izq, der = st.columns([5, 6], gap="large")
    with izq:
        st.markdown(
            "<p style='font-size:1.05rem; color:#334155; margin:0.5rem 0 1rem 0;'>"
            "🩺 Presiona el micrófono para grabar la consulta o el dictado de la ecografía.</p>",
            unsafe_allow_html=True,
        )
        selector_medicos()
        _selector_formato()
        _selector_modo()
        _grabador()
        st.markdown(
            "<p style='text-align:center; color:#64748B; font-size:0.85rem; margin-top:1rem;'>"
            + (
                "El informe se llena automáticamente al detener la grabación."
                if es_ecografia(state.formato())
                else "La transcripción y el resumen se generan automáticamente al detener la grabación."
            )
            + "</p>",
            unsafe_allow_html=True,
        )

        gestion_voces()

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
    with der:
        _vista_previa()
