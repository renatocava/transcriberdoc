"""Vista de revisión: transcripción a la izquierda, historia clínica editable a la derecha."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from lib import state
from lib.extraction import extraer_historia_clinica

TIPOS_DX = ["presuntivo", "definitivo", "diferencial"]
SEXOS = ["", "M", "F", "Otro"]
COLOR_ROL = {"Doctor": "blue", "Paciente": "green"}
ICONO_ROL = {"Doctor": "🩺", "Paciente": "🧑"}


# --------------------------------------------------------------------------
# Callbacks de los editores de lista (mutan las listas dentro de session_state)
# --------------------------------------------------------------------------
def _quitar_idx(lista: list, idx: int) -> None:
    if 0 <= idx < len(lista):
        lista.pop(idx)


def _quitar_uid(lista: list, uid: str) -> None:
    for i, item in enumerate(lista):
        if item.get("_uid") == uid:
            lista.pop(i)
            return


def _agregar_texto(lista: list, input_key: str) -> None:
    valor = (st.session_state.get(input_key) or "").strip()
    if valor:
        lista.append(valor)
        st.session_state[input_key] = ""


def _agregar_registro(lista: list, plantilla: dict[str, Any]) -> None:
    lista.append({**plantilla, "_uid": state.nuevo_uid()})


def _cancelar_cambio_speaker() -> None:
    # Mutar la key de un widget solo es legal dentro de un callback.
    st.session_state["f_speaker_a"] = st.session_state["speaker_mapping"]["A"]


# --------------------------------------------------------------------------
# Editor de lista de textos simples
# --------------------------------------------------------------------------
def _editor_textos(titulo: str, lista: list[str], prefijo: str, placeholder: str) -> None:
    st.markdown(f"**{titulo}**")
    if not lista:
        st.caption("Sin registros")
    for i, item in enumerate(list(lista)):
        c_txt, c_del = st.columns([12, 1], vertical_alignment="center")
        c_txt.markdown(f"• {item}")
        c_del.button(
            "×",
            key=f"{prefijo}_del_{i}",
            help="Eliminar",
            on_click=_quitar_idx,
            args=(lista, i),
        )
    c_in, c_add = st.columns([12, 1], vertical_alignment="center")
    c_in.text_input(
        titulo,
        key=f"{prefijo}_new",
        placeholder=placeholder,
        label_visibility="collapsed",
    )
    c_add.button(
        "＋",
        key=f"{prefijo}_add",
        help="Agregar",
        on_click=_agregar_texto,
        args=(lista, f"{prefijo}_new"),
    )


# --------------------------------------------------------------------------
# Columna izquierda: transcripción
# --------------------------------------------------------------------------
def _render_transcript() -> None:
    st.subheader("Transcripción")
    state.reproductor_audio()
    mapping = st.session_state["speaker_mapping"]
    utterances = (st.session_state.get("transcription") or {}).get("utterances", [])

    st.session_state.setdefault("f_speaker_a", mapping["A"])
    seleccion = st.radio("Speaker A es:", ["Doctor", "Paciente"], horizontal=True, key="f_speaker_a")

    if seleccion != mapping["A"]:
        st.warning("Los cambios manuales en el formulario se perderán.")
        c_ok, c_no = st.columns(2)
        if c_ok.button("Confirmar y re-extraer", type="primary", use_container_width=True):
            nuevo = state.mapping_desde(seleccion)
            try:
                with st.spinner("Re-extrayendo información clínica..."):
                    historia = extraer_historia_clinica(utterances, nuevo)
                st.session_state["speaker_mapping"] = nuevo
                st.session_state["historia"] = state.ensure_uids(historia)
                for clave in [k for k in st.session_state if str(k).startswith("f_") and k != "f_speaker_a"]:
                    del st.session_state[clave]
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo re-extraer la información: {exc}")
        c_no.button("Cancelar", use_container_width=True, on_click=_cancelar_cambio_speaker)

    with st.container(height=560, border=False):
        for u in utterances:
            rol = mapping.get(u.get("speaker", ""), u.get("speaker", "Hablante"))
            color = COLOR_ROL.get(rol, "gray")
            with st.container(border=True):
                st.markdown(f"{ICONO_ROL.get(rol, '💬')} :{color}[**{rol}**]")
                st.markdown(u.get("text", ""))


# --------------------------------------------------------------------------
# Columna derecha: formulario
# --------------------------------------------------------------------------
def _seccion_paciente(historia: dict) -> None:
    pac = historia.setdefault("paciente", {})
    with st.expander("Paciente", expanded=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        pac["nombre"] = c1.text_input("Nombre", value=pac.get("nombre") or "", key="f_pac_nombre")
        pac["edad"] = c2.number_input(
            "Edad", min_value=0, max_value=120, step=1, value=pac.get("edad"), key="f_pac_edad"
        )
        actual = pac.get("sexo") or ""
        sexo = c3.selectbox(
            "Sexo",
            SEXOS,
            index=SEXOS.index(actual) if actual in SEXOS else 0,
            format_func=lambda x: x or "—",
            key="f_pac_sexo",
        )
        pac["sexo"] = sexo or None


def _seccion_motivo(historia: dict) -> None:
    with st.expander("Motivo y enfermedad actual", expanded=True):
        historia["motivo_consulta"] = st.text_area(
            "Motivo de consulta",
            value=historia.get("motivo_consulta") or "",
            height=90,
            key="f_motivo",
        )
        historia["enfermedad_actual"] = st.text_area(
            "Enfermedad actual",
            value=historia.get("enfermedad_actual") or "",
            height=180,
            key="f_enfermedad",
        )


def _seccion_antecedentes(historia: dict) -> None:
    ant = historia.setdefault("antecedentes", {})
    with st.expander("Antecedentes", expanded=True):
        _editor_textos("Personales", ant.setdefault("personales", []), "f_ant_per", "Ej: Hipertensión arterial")
        st.divider()
        _editor_textos("Alergias", ant.setdefault("alergias", []), "f_ant_ale", "Ej: Penicilina")
        st.divider()
        _editor_textos(
            "Medicamentos actuales",
            ant.setdefault("medicamentos_actuales", []),
            "f_ant_med",
            "Ej: Metformina 850 mg",
        )


def _seccion_examen(historia: dict) -> None:
    exf = historia.setdefault("examen_fisico", {})
    sv = exf.setdefault("signos_vitales", {})
    with st.expander("Examen físico", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        sv["presion_arterial"] = c1.text_input("Presión arterial", value=sv.get("presion_arterial") or "", key="f_sv_pa")
        sv["frecuencia_cardiaca"] = c2.text_input("Frecuencia cardiaca", value=sv.get("frecuencia_cardiaca") or "", key="f_sv_fc")
        sv["temperatura"] = c3.text_input("Temperatura", value=sv.get("temperatura") or "", key="f_sv_t")
        sv["saturacion_oxigeno"] = c4.text_input("Saturación O₂", value=sv.get("saturacion_oxigeno") or "", key="f_sv_sat")
        exf["hallazgos"] = st.text_area(
            "Hallazgos", value=exf.get("hallazgos") or "", height=140, key="f_ex_hallazgos"
        )


def _seccion_diagnosticos(historia: dict) -> None:
    diags = historia.setdefault("diagnosticos", [])
    with st.expander("Diagnósticos", expanded=True):
        if not diags:
            st.caption("Sin diagnósticos registrados")
        for dx in list(diags):
            uid = dx.setdefault("_uid", state.nuevo_uid())
            c_desc, c_tipo, c_del = st.columns([7, 3, 1], vertical_alignment="center")
            dx["descripcion"] = c_desc.text_input(
                "Diagnóstico",
                value=dx.get("descripcion") or "",
                key=f"f_dx_desc_{uid}",
                label_visibility="collapsed",
            )
            tipo_actual = dx.get("tipo") if dx.get("tipo") in TIPOS_DX else TIPOS_DX[0]
            dx["tipo"] = c_tipo.selectbox(
                "Tipo",
                TIPOS_DX,
                index=TIPOS_DX.index(tipo_actual),
                key=f"f_dx_tipo_{uid}",
                label_visibility="collapsed",
            )
            c_del.button("×", key=f"f_dx_del_{uid}", help="Eliminar", on_click=_quitar_uid, args=(diags, uid))
        st.button(
            "＋ Agregar diagnóstico",
            key="f_dx_add",
            on_click=_agregar_registro,
            args=(diags, {"descripcion": "", "tipo": "presuntivo"}),
        )


def _seccion_plan(historia: dict) -> None:
    plan = historia.setdefault("plan", {})
    meds = plan.setdefault("medicamentos", [])
    with st.expander("Plan", expanded=True):
        st.markdown("**Medicamentos**")
        if not meds:
            st.caption("Sin medicamentos indicados")
        for med in list(meds):
            uid = med.setdefault("_uid", state.nuevo_uid())
            with st.container(border=True):
                c_nom, c_del = st.columns([12, 1], vertical_alignment="center")
                med["nombre"] = c_nom.text_input(
                    "Medicamento", value=med.get("nombre") or "", key=f"f_med_nom_{uid}", label_visibility="collapsed"
                )
                c_del.button("×", key=f"f_med_del_{uid}", help="Eliminar", on_click=_quitar_uid, args=(meds, uid))
                c1, c2, c3 = st.columns(3)
                med["dosis"] = c1.text_input("Dosis", value=med.get("dosis") or "", key=f"f_med_dos_{uid}")
                med["frecuencia"] = c2.text_input("Frecuencia", value=med.get("frecuencia") or "", key=f"f_med_fre_{uid}")
                med["duracion"] = c3.text_input("Duración", value=med.get("duracion") or "", key=f"f_med_dur_{uid}")
        st.button(
            "＋ Agregar medicamento",
            key="f_med_add",
            on_click=_agregar_registro,
            args=(meds, {"nombre": "", "dosis": "", "frecuencia": "", "duracion": ""}),
        )

        st.divider()
        _editor_textos(
            "Exámenes solicitados",
            plan.setdefault("examenes_solicitados", []),
            "f_plan_ex",
            "Ej: Hemograma completo",
        )
        st.divider()
        _editor_textos(
            "Indicaciones",
            plan.setdefault("indicaciones", []),
            "f_plan_ind",
            "Ej: Reposo por 48 horas",
        )
        st.divider()
        plan["proxima_cita"] = st.text_input(
            "Próxima cita", value=plan.get("proxima_cita") or "", key="f_plan_cita"
        )


def _guardar(historia: dict) -> None:
    final = state.strip_uids(historia)
    print("\n===== HISTORIA CLÍNICA GUARDADA =====")
    print(json.dumps(final, indent=2, ensure_ascii=False))
    print("=====================================\n", flush=True)
    state.set_stage(state.SAVED)


def _render_formulario(historia: dict) -> None:
    st.subheader("Historia Clínica")
    _seccion_paciente(historia)
    _seccion_motivo(historia)
    _seccion_antecedentes(historia)
    _seccion_examen(historia)
    _seccion_diagnosticos(historia)
    _seccion_plan(historia)

    st.write("")
    c_ok, c_no = st.columns(2)
    if c_ok.button("Guardar en Historia Clínica", type="primary", use_container_width=True):
        _guardar(historia)
        st.rerun()
    if c_no.button("Descartar", use_container_width=True):
        state.reset()
        st.rerun()


def render_review() -> None:
    historia = st.session_state.get("historia")
    if not historia:
        state.reset()
        st.rerun()
        return

    col_transcript, col_form = st.columns([2, 3], gap="large")
    with col_transcript:
        _render_transcript()
    with col_form:
        _render_formulario(historia)
