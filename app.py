"""MedScribe AI — demo de documentación clínica asistida por IA."""

from __future__ import annotations

import streamlit as st

from components.informe_eco import boton_descarga
from components.processing import render_processing
from components.recording import render_idle
from components.review import render_review
from lib import state
from lib.config import usar_mock
from lib.ecografias import PLANTILLAS, es_ecografia

st.set_page_config(page_title="MedScribe AI", page_icon="🩺", layout="wide")

state.init_state()

col1, col2 = st.columns([6, 1])
with col1:
    st.title("MedScribe AI")
    st.caption("Asistente de documentación clínica")
with col2:
    st.markdown(f"`{'DEMO · SIMULADO' if usar_mock() else 'DEMO'}`")

st.divider()


def render_saved() -> None:
    nombre = ((st.session_state.get("historia") or {}).get("paciente") or {}).get("nombre")
    paciente = nombre.strip() if isinstance(nombre, str) and nombre.strip() else "el paciente"

    informe = st.session_state.get("historia") or {}
    eco = es_ecografia(informe.get("plantilla"))

    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.write("")
        if eco:
            st.success(f"✓ Informe de {PLANTILLAS[informe['plantilla']].nombre.lower()} guardado: {paciente}")
            boton_descarga(informe, "descargar_guardado", primario=True)
        else:
            st.success(f"✓ Consulta guardada en la historia clínica de {paciente}")
        st.caption("El registro quedó disponible para el equipo asistencial.")
        st.write("")
        if st.button("Nueva consulta", type="secondary" if eco else "primary", use_container_width=True):
            state.reset()
            st.rerun()


etapa = state.stage()
if etapa == state.PROCESSING:
    render_processing()
elif etapa == state.REVIEW:
    render_review()
elif etapa == state.SAVED:
    render_saved()
else:
    render_idle()
