"""Médico que realiza el estudio y las voces registradas de los médicos."""

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


#: Opción del selector para escribir el nombre de un médico sin voz registrada,
#: y la clave que recuerda que se eligió (aunque aún no se haya escrito el nombre).
OTRO = "__otro__"
CLAVE_OTRO = "medico_es_otro"


def _elegir(medico_id: str | None, nombre: str, otro: bool = False) -> None:
    st.session_state[state.CLAVE_MEDICOS] = [medico_id] if medico_id else []
    st.session_state[state.CLAVE_MEDICO] = nombre.strip()
    st.session_state[CLAVE_OTRO] = otro


def _guardar_seleccion(registrados: dict[str, str]) -> None:
    elegido = st.session_state["w_medico"]
    if elegido == OTRO:
        _elegir(None, st.session_state.get("w_medico_otro", ""), otro=True)
    else:
        _elegir(elegido, registrados.get(elegido, ""))


def _guardar_otro() -> None:
    _elegir(None, st.session_state["w_medico_otro"], otro=True)


def selector_medico() -> None:
    """Médico que realiza el estudio: va en la línea MÉDICO del informe y, si
    registró su voz, sus intervenciones aparecen con su nombre."""
    registrados = {m["id"]: m["nombre"] for m in voces.listar()}
    seleccion = [i for i in state.medicos_consulta() if i in registrados]
    # Igual que el formato: copia propia porque el widget solo existe en esta pantalla.
    otro = st.session_state.get(CLAVE_OTRO) or (not seleccion and bool(state.medico()))
    st.session_state["w_medico"] = seleccion[0] if seleccion else (OTRO if otro else None)
    st.session_state["w_medico_otro"] = "" if seleccion else state.medico()
    elegido = st.selectbox(
        "Médico que realiza el estudio",
        options=[*registrados, OTRO],
        format_func=lambda i: registrados.get(i, "Otro (escribir el nombre)"),
        key="w_medico",
        on_change=_guardar_seleccion,
        args=(registrados,),
        placeholder="Elige al médico",
        help="Aparece en la línea MÉDICO del informe. Si registró su voz, se reconoce en la grabación.",
    )
    if elegido == OTRO:
        st.text_input(
            "Nombre del médico", key="w_medico_otro", on_change=_guardar_otro,
            placeholder="Ej: Dr. Hurtado", label_visibility="collapsed",
        )


def _eliminar(medico_id: str) -> None:
    voces.eliminar(medico_id)
    if medico_id in state.medicos_consulta():
        _elegir(None, "")


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
                _elegir(medico["id"], medico["nombre"])
                st.toast(f"Voz de {medico['nombre']} registrada.")
                st.rerun()
