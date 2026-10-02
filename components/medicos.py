"""Médicos con voz registrada: elegir quién atiende y registrar o eliminar voces."""

from __future__ import annotations

import streamlit as st

from lib import state, voces

FRASE_MUESTRA = (
    "«Buenos días, soy el doctor o la doctora ___. Cuénteme qué molestias tiene; "
    "vamos a revisarlo y luego le explico el tratamiento.»"
)
CONSENTIMIENTO = (
    "El médico autoriza el registro de su voz (dato biométrico, Ley 29733) solo para "
    "identificarlo en las transcripciones, y puede pedir que se elimine en cualquier momento."
)


def _guardar_seleccion() -> None:
    st.session_state[state.CLAVE_MEDICOS] = list(st.session_state["w_medicos"])


def selector_medicos() -> None:
    """Médicos presentes en la consulta; sus voces se reconocen por nombre."""
    registrados = {m["id"]: m["nombre"] for m in voces.listar()}
    if not registrados:
        st.caption("👤 Registra la voz de un médico en «Voces de médicos» para que aparezca con su nombre.")
        return
    # Igual que el modo: copia propia porque el widget solo existe en esta pantalla.
    st.session_state["w_medicos"] = [i for i in state.medicos_consulta() if i in registrados]
    st.multiselect(
        "Médico(s) en la consulta",
        options=list(registrados),
        format_func=registrados.get,
        max_selections=voces.MAX_CONOCIDOS,
        key="w_medicos",
        on_change=_guardar_seleccion,
        placeholder="Ninguno: se identificará al médico por orden de aparición",
        help="Su voz se reconocerá en la grabación y aparecerá con su nombre.",
    )


def _eliminar(medico_id: str) -> None:
    voces.eliminar(medico_id)
    st.session_state[state.CLAVE_MEDICOS] = [i for i in state.medicos_consulta() if i != medico_id]


def gestion_voces() -> None:
    with st.expander("Voces de médicos"):
        registrados = voces.listar()
        for m in registrados:
            c_nom, c_audio, c_del = st.columns([4, 5, 1], vertical_alignment="center")
            c_nom.markdown(f"**{m['nombre']}**  \n:gray[{m['duracion']} s · {m['registrado'][:10]}]")
            muestra = voces.audio(m["id"])
            if muestra:
                c_audio.audio(muestra, format="audio/wav")
            c_del.button(
                "×", key=f"voz_del_{m['id']}", help="Eliminar esta voz",
                on_click=_eliminar, args=(m["id"],),
            )
        if registrados:
            st.divider()

        st.markdown("**Registrar una voz**")
        st.caption(f"Graba entre 5 y 10 segundos hablando con naturalidad, por ejemplo: {FRASE_MUESTRA}")
        nombre = st.text_input("Nombre", key="voz_nombre", placeholder="Ej: Dr. Hurtado")

        try:
            from streamlit_mic_recorder import mic_recorder
        except ImportError:
            mic_recorder = None
        grabacion = mic_recorder and mic_recorder(
            start_prompt="🎙️  Grabar muestra",
            stop_prompt="⏹️  Detener",
            just_once=True,
            use_container_width=True,
            format="wav",
            key="mic_voz",
        )
        if grabacion and grabacion.get("bytes"):
            st.session_state["voz_pendiente"] = grabacion["bytes"]
        subida = st.file_uploader("O sube una muestra WAV", type=["wav"], key="voz_archivo")
        if subida is not None:
            st.session_state["voz_pendiente"] = subida.getvalue()

        pendiente = st.session_state.get("voz_pendiente")
        if pendiente:
            try:
                _, duracion = voces.preparar_wav(pendiente)
                st.audio(pendiente, format="audio/wav")
                nota = " (se usarán los primeros 10 s)" if duracion >= voces.MAX_SEGUNDOS else ""
                st.caption(f"Muestra lista{nota}.")
            except ValueError as exc:
                st.warning(str(exc))
                pendiente = None

        acepta = st.checkbox(CONSENTIMIENTO, key="voz_consentimiento")
        if st.button("Registrar voz", type="primary", disabled=not (pendiente and acepta and nombre.strip())):
            try:
                medico = voces.registrar(nombre, pendiente)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("voz_pendiente", None)
                for clave in ("voz_nombre", "voz_consentimiento", "voz_archivo"):
                    st.session_state.pop(clave, None)
                seleccion = state.medicos_consulta()
                if len(seleccion) < voces.MAX_CONOCIDOS:
                    st.session_state[state.CLAVE_MEDICOS] = [*seleccion, medico["id"]]
                st.toast(f"Voz de {medico['nombre']} registrada.")
                st.rerun()
