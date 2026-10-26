"""MedScribe AI — demo de documentación clínica asistida por IA."""

from __future__ import annotations

import streamlit as st

from components.processing import render_processing
from components.recording import render_idle
from components.review import render_review
from lib import state
from lib.config import usar_mock

st.set_page_config(page_title="MedScribe AI", page_icon="🩺", layout="wide")

state.init_state()

col1, col2 = st.columns([6, 1])
with col1:
    st.title("MedScribe AI")
    st.caption("Asistente de documentación clínica")
with col2:
    st.markdown(f"`{'DEMO · SIMULADO' if usar_mock() else 'DEMO'}`")

st.divider()


etapa = state.stage()
if etapa == state.PROCESSING:
    render_processing()
elif etapa == state.REVIEW:
    render_review()
else:
    render_idle()
