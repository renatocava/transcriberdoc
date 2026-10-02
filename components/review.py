"""Vista de revisión: transcripción a la izquierda, historia clínica editable a la derecha."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from lib import cie10, state
from lib.extraction import extraer_historia_clinica
from lib.fuentes import SEP, de_texto, editado
from lib.hablantes import ROLES, aviso, etiqueta, hablantes

TIPOS_DX = ["presuntivo", "definitivo", "diferencial"]
SEXOS = ["", "M", "F", "Otro"]
COLOR_ROL = {"Doctor": "blue", "Paciente": "green", "Acompañante": "orange"}
ICONO_ROL = {"Doctor": "🩺", "Paciente": "🧑", "Acompañante": "👥"}
PREFIJO_ROL = "f_rol_"

#: Ruta de cada campo simple -> etiqueta visible (para las fuentes).
ETIQUETAS = {
    "paciente.nombre": "Nombre",
    "paciente.edad": "Edad",
    "paciente.sexo": "Sexo",
    "motivo_consulta": "Motivo de consulta",
    "enfermedad_actual": "Enfermedad actual",
    "examen_fisico.signos_vitales.presion_arterial": "Presión arterial",
    "examen_fisico.signos_vitales.frecuencia_cardiaca": "Frecuencia cardiaca",
    "examen_fisico.signos_vitales.temperatura": "Temperatura",
    "examen_fisico.signos_vitales.saturacion_oxigeno": "Saturación O₂",
    "examen_fisico.hallazgos": "Hallazgos",
    "plan.proxima_cita": "Próxima cita",
}
LISTAS_TEXTO = {
    "antecedentes.personales": "Antecedente",
    "antecedentes.alergias": "Alergia",
    "antecedentes.medicamentos_actuales": "Medicamento actual",
    "plan.examenes_solicitados": "Examen",
    "plan.indicaciones": "Indicación",
}
SIN_FUENTE = "⚠️ Sin fuente en la transcripción: agregado a mano o sin respaldo. Verifícalo."


# --------------------------------------------------------------------------
# Fuentes: de dónde sale cada dato
# --------------------------------------------------------------------------
def _utterances() -> list[dict[str, Any]]:
    return (st.session_state.get("transcription") or {}).get("utterances", [])


def _mmss(segundos: float) -> str:
    m, s = divmod(int(segundos or 0), 60)
    return f"{m:02d}:{s:02d}"


def _enfocar(ids: list[int]) -> None:
    st.session_state["foco"] = list(ids)


def _fuente(ruta: str) -> dict[str, Any] | None:
    return st.session_state.get("fuentes", {}).get(ruta)


def _ayuda(fuente: dict[str, Any] | None, valor: Any) -> str | None:
    """Tooltip con las citas textuales que respaldan un dato."""
    if not fuente:
        return SIN_FUENTE if valor not in ("", None) else None
    utterances = _utterances()
    mapping = st.session_state["speaker_mapping"]
    citas = []
    for i in fuente["ids"]:
        if i >= len(utterances):
            continue
        u = utterances[i]
        texto = (u.get("text") or "").strip()
        if len(texto) > 220:
            texto = texto[:220] + "…"
        citas.append(
            f"**#{i + 1}** · {etiqueta(u.get('speaker', ''), mapping)} · {_mmss(u.get('start'))}  \n«{texto}»"
        )
    if editado(fuente, valor):
        citas.append("✏️ *Editado a mano después de la extracción.*")
    citas.append("*Clic en 📎 para verlo en la transcripción y escuchar el audio.*")
    return "\n\n".join(citas)


def _numeros(fuente: dict[str, Any]) -> str:
    return ", ".join(f"#{i + 1}" for i in fuente["ids"])


def _boton_fuente(contenedor: Any, fuente: dict[str, Any] | None, valor: Any, key: str) -> None:
    """📎 que muestra la cita al pasar el mouse y al hacer clic la abre en la transcripción."""
    if fuente:
        contenedor.button(
            "📎", key=key, help=_ayuda(fuente, valor), type="tertiary",
            on_click=_enfocar, args=(fuente["ids"],),
        )
    elif valor not in ("", None):
        contenedor.markdown("⚠️", help=SIN_FUENTE)


def _fila_fuentes(campos: list[tuple[str, Any]], prefijo: str) -> None:
    """Botones «📎 Campo · #n» para los campos simples de una sección."""
    con_fuente = [(ruta, valor, _fuente(ruta)) for ruta, valor in campos]
    con_fuente = [c for c in con_fuente if c[2]]
    if not con_fuente:
        return
    with st.container(horizontal=True, gap="small"):
        for ruta, valor, fuente in con_fuente:
            marca = " ✏️" if editado(fuente, valor) else ""
            st.button(
                f"📎 {ETIQUETAS[ruta]} · {_numeros(fuente)}{marca}",
                key=f"{prefijo}_{ruta}",
                help=_ayuda(fuente, valor),
                type="tertiary",
                on_click=_enfocar,
                args=(fuente["ids"],),
            )


def _valor(key: str, defecto: Any) -> Any:
    """Valor vigente de un widget (el de session_state va un paso por delante de la historia)."""
    return st.session_state.get(key, defecto)


def _indice_inverso(historia: dict[str, Any]) -> dict[int, list[str]]:
    """Intervención -> datos del formulario que salen de ella."""
    inverso: dict[int, list[str]] = {}

    def anotar(ids: list[int], nombre: str) -> None:
        for i in ids:
            inverso.setdefault(i, []).append(nombre)

    for ruta, fuente in st.session_state.get("fuentes", {}).items():
        if SEP in ruta:
            base, texto = ruta.split(SEP, 1)
            anotar(fuente["ids"], f"{LISTAS_TEXTO.get(base, base)}: {texto}")
        else:
            anotar(fuente["ids"], ETIQUETAS.get(ruta, ruta))
    for dx in historia.get("diagnosticos", []):
        if dx.get("_fuentes"):
            codigo = f" ({dx['cie10']})" if dx.get("cie10") else ""
            anotar(dx["_fuentes"]["ids"], f"Diagnóstico: {dx.get('descripcion', '')}{codigo}")
    for med in historia.get("plan", {}).get("medicamentos", []):
        if med.get("_fuentes"):
            anotar(med["_fuentes"]["ids"], f"Medicamento: {med.get('nombre', '')}")
    return inverso


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


def _cancelar_cambio_roles() -> None:
    # Mutar la key de un widget solo es legal dentro de un callback.
    for voz, rol in st.session_state["speaker_mapping"].items():
        st.session_state[f"{PREFIJO_ROL}{voz}"] = rol


# --------------------------------------------------------------------------
# Editor de lista de textos simples
# --------------------------------------------------------------------------
def _editor_textos(titulo: str, lista: list[str], prefijo: str, placeholder: str, ruta: str) -> None:
    st.markdown(f"**{titulo}**")
    if not lista:
        st.caption("Sin registros")
    fuentes = st.session_state.get("fuentes", {})
    for i, item in enumerate(list(lista)):
        c_txt, c_src, c_del = st.columns([11, 1, 1], vertical_alignment="center")
        c_txt.markdown(f"• {item}")
        _boton_fuente(c_src, de_texto(fuentes, ruta, item), item, f"{prefijo}_src_{i}")
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
def _render_roles(utterances: list[dict[str, Any]]) -> None:
    mapping = st.session_state["speaker_mapping"]
    voces = hablantes(utterances)

    mensaje = aviso(len(voces), state.modo_hablantes())
    if mensaje:
        st.info(mensaje)

    st.caption(f"{len(voces)} {'voz detectada' if len(voces) == 1 else 'voces detectadas'} · rol de cada una:")
    nuevo: dict[str, str] = {}
    columnas = st.columns(min(len(voces), 4) or 1)
    for i, voz in enumerate(voces):
        st.session_state.setdefault(f"{PREFIJO_ROL}{voz}", mapping.get(voz, "Otro"))
        nuevo[voz] = columnas[i % len(columnas)].selectbox(
            f"Voz {voz}", ROLES, key=f"{PREFIJO_ROL}{voz}"
        )

    if nuevo != {v: mapping.get(v, "Otro") for v in voces}:
        st.warning("Los cambios manuales en el formulario se perderán.")
        c_ok, c_no = st.columns(2)
        if c_ok.button("Confirmar y re-extraer", type="primary", use_container_width=True):
            try:
                with st.spinner("Re-extrayendo información clínica..."):
                    historia, fuentes = extraer_historia_clinica(utterances, nuevo)
                st.session_state["speaker_mapping"] = nuevo
                st.session_state["historia"] = state.ensure_uids(historia)
                st.session_state["fuentes"] = fuentes
                st.session_state["foco"] = []
                for clave in [k for k in st.session_state if str(k).startswith("f_") and not str(k).startswith(PREFIJO_ROL)]:
                    del st.session_state[clave]
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo re-extraer la información: {exc}")
        c_no.button("Cancelar", use_container_width=True, on_click=_cancelar_cambio_roles)


def _render_foco(utterances: list[dict[str, Any]]) -> None:
    """Fragmentos seleccionados, cada uno con su trozo de audio."""
    foco = [i for i in st.session_state.get("foco", []) if i < len(utterances)]
    if not foco:
        return
    mapping = st.session_state["speaker_mapping"]
    audio = st.session_state.get("audio_bytes")
    formato = state.mime_audio(st.session_state.get("audio_filename", ""))
    with st.container(border=True):
        c_tit, c_x = st.columns([12, 1], vertical_alignment="center")
        c_tit.markdown("**📍 Fuente seleccionada**")
        c_x.button("✕", key="f_foco_cerrar", help="Cerrar", type="tertiary", on_click=_enfocar, args=([],))
        for i in foco:
            u = utterances[i]
            inicio, fin = float(u.get("start") or 0), float(u.get("end") or 0)
            st.caption(f"#{i + 1} · {etiqueta(u.get('speaker', ''), mapping)} · {_mmss(inicio)}–{_mmss(fin)}")
            st.markdown(f"«{(u.get('text') or '').strip()}»")
            if audio and fin > inicio:
                st.audio(audio, format=formato, start_time=max(0.0, inicio - 0.3), end_time=fin + 0.5)


def _render_transcript(historia: dict[str, Any]) -> None:
    st.subheader("Transcripción")
    state.reproductor_audio()
    utterances = _utterances()
    _render_roles(utterances)
    _render_foco(utterances)

    mapping = st.session_state["speaker_mapping"]
    foco = set(st.session_state.get("foco", []))
    usos = _indice_inverso(historia)
    with st.container(height=560, border=False):
        for i, u in enumerate(utterances):
            voz = u.get("speaker", "")
            rol = mapping.get(voz, "Otro")
            color = COLOR_ROL.get(rol, "gray")
            texto = u.get("text", "")
            with st.container(border=True):
                c_head, c_play = st.columns([12, 1], vertical_alignment="center")
                c_head.markdown(
                    f"{'📍 ' if i in foco else ''}{ICONO_ROL.get(rol, '💬')} :{color}[**{etiqueta(voz, mapping)}**]"
                    f" &nbsp; :gray[#{i + 1} · {_mmss(u.get('start'))}]"
                )
                c_play.button(
                    "▶", key=f"f_play_{i}", help="Escuchar este fragmento", type="tertiary",
                    on_click=_enfocar, args=([i],),
                )
                if i in foco:
                    st.info(texto)
                else:
                    st.markdown(texto)
                if usos.get(i):
                    st.caption("📎 " + " · ".join(usos[i]))


# --------------------------------------------------------------------------
# Columna derecha: formulario
# --------------------------------------------------------------------------
def _seccion_paciente(historia: dict) -> None:
    pac = historia.setdefault("paciente", {})
    with st.expander("Paciente", expanded=True):
        _fila_fuentes(
            [
                ("paciente.nombre", _valor("f_pac_nombre", pac.get("nombre"))),
                ("paciente.edad", _valor("f_pac_edad", pac.get("edad"))),
                ("paciente.sexo", _valor("f_pac_sexo", pac.get("sexo")) or None),
            ],
            "f_src_pac",
        )
        c1, c2, c3 = st.columns([3, 1, 1])
        pac["nombre"] = c1.text_input(
            "Nombre", value=pac.get("nombre") or "", key="f_pac_nombre",
            help=_ayuda(_fuente("paciente.nombre"), _valor("f_pac_nombre", pac.get("nombre"))),
        )
        pac["edad"] = c2.number_input(
            "Edad", min_value=0, max_value=120, step=1, value=pac.get("edad"), key="f_pac_edad",
            help=_ayuda(_fuente("paciente.edad"), _valor("f_pac_edad", pac.get("edad"))),
        )
        actual = pac.get("sexo") or ""
        sexo = c3.selectbox(
            "Sexo",
            SEXOS,
            index=SEXOS.index(actual) if actual in SEXOS else 0,
            format_func=lambda x: x or "—",
            key="f_pac_sexo",
            help=_ayuda(_fuente("paciente.sexo"), _valor("f_pac_sexo", actual) or None),
        )
        pac["sexo"] = sexo or None


def _seccion_motivo(historia: dict) -> None:
    with st.expander("Motivo y enfermedad actual", expanded=True):
        motivo = _valor("f_motivo", historia.get("motivo_consulta"))
        enfermedad = _valor("f_enfermedad", historia.get("enfermedad_actual"))
        _fila_fuentes([("motivo_consulta", motivo), ("enfermedad_actual", enfermedad)], "f_src_mot")
        historia["motivo_consulta"] = st.text_area(
            "Motivo de consulta",
            value=historia.get("motivo_consulta") or "",
            height=90,
            key="f_motivo",
            help=_ayuda(_fuente("motivo_consulta"), motivo),
        )
        historia["enfermedad_actual"] = st.text_area(
            "Enfermedad actual",
            value=historia.get("enfermedad_actual") or "",
            height=180,
            key="f_enfermedad",
            help=_ayuda(_fuente("enfermedad_actual"), enfermedad),
        )


def _seccion_antecedentes(historia: dict) -> None:
    ant = historia.setdefault("antecedentes", {})
    with st.expander("Antecedentes", expanded=True):
        _editor_textos(
            "Personales", ant.setdefault("personales", []), "f_ant_per",
            "Ej: Hipertensión arterial", "antecedentes.personales",
        )
        st.divider()
        _editor_textos(
            "Alergias", ant.setdefault("alergias", []), "f_ant_ale",
            "Ej: Penicilina", "antecedentes.alergias",
        )
        st.divider()
        _editor_textos(
            "Medicamentos actuales",
            ant.setdefault("medicamentos_actuales", []),
            "f_ant_med",
            "Ej: Metformina 850 mg",
            "antecedentes.medicamentos_actuales",
        )


def _seccion_examen(historia: dict) -> None:
    exf = historia.setdefault("examen_fisico", {})
    sv = exf.setdefault("signos_vitales", {})
    signos = [
        ("presion_arterial", "Presión arterial", "f_sv_pa"),
        ("frecuencia_cardiaca", "Frecuencia cardiaca", "f_sv_fc"),
        ("temperatura", "Temperatura", "f_sv_t"),
        ("saturacion_oxigeno", "Saturación O₂", "f_sv_sat"),
    ]
    ruta_sv = "examen_fisico.signos_vitales."
    with st.expander("Examen físico", expanded=True):
        hallazgos = _valor("f_ex_hallazgos", exf.get("hallazgos"))
        _fila_fuentes(
            [(ruta_sv + campo, _valor(key, sv.get(campo))) for campo, _, key in signos]
            + [("examen_fisico.hallazgos", hallazgos)],
            "f_src_ex",
        )
        for col, (campo, etiqueta_sv, key) in zip(st.columns(4), signos):
            sv[campo] = col.text_input(
                etiqueta_sv, value=sv.get(campo) or "", key=key,
                help=_ayuda(_fuente(ruta_sv + campo), _valor(key, sv.get(campo))),
            )
        exf["hallazgos"] = st.text_area(
            "Hallazgos", value=exf.get("hallazgos") or "", height=140, key="f_ex_hallazgos",
            help=_ayuda(_fuente("examen_fisico.hallazgos"), hallazgos),
        )


def _seccion_diagnosticos(historia: dict) -> None:
    diags = historia.setdefault("diagnosticos", [])
    with st.expander("Diagnósticos", expanded=True):
        if not diags:
            st.caption("Sin diagnósticos registrados")
        for dx in list(diags):
            uid = dx.setdefault("_uid", state.nuevo_uid())
            c_desc, c_tipo, c_src, c_del = st.columns([7, 3, 1, 1], vertical_alignment="center")
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
            _boton_fuente(c_src, dx.get("_fuentes"), dx if dx.get("descripcion") else None, f"f_dx_src_{uid}")
            c_del.button("×", key=f"f_dx_del_{uid}", help="Eliminar", on_click=_quitar_uid, args=(diags, uid))
            _selector_cie10(dx, uid)
        st.button(
            "＋ Agregar diagnóstico",
            key="f_dx_add",
            on_click=_agregar_registro,
            args=(diags, {"descripcion": "", "tipo": "presuntivo", "cie10": ""}),
        )


def _selector_cie10(dx: dict, uid: str) -> None:
    """Código CIE-10 del diagnóstico: propuesta validada, alternativas o búsqueda en el catálogo."""
    if not cie10.disponible():
        st.caption("Catálogo CIE-10 no disponible (scripts/construir_cie10.py).")
        return
    c_cod, c_bus = st.columns([7, 4], vertical_alignment="center")
    consulta = c_bus.text_input(
        "Buscar CIE-10",
        key=f"f_dx_bus_{uid}",
        placeholder="🔍 Buscar CIE-10: código o palabras",
        label_visibility="collapsed",
    )
    actual = dx.get("cie10") or ""
    if consulta.strip():
        candidatos = [c["codigo"] for c in cie10.buscar(consulta, limite=25)]
    else:
        candidatos = list(dx.get("_cie10_sugeridos") or [])
    opciones = list(dict.fromkeys(["", actual, *candidatos])) if actual else ["", *candidatos]
    descripciones = {c: (cie10.obtener(c) or {}).get("descripcion", "") for c in opciones if c}
    dx["cie10"] = c_cod.selectbox(
        "CIE-10",
        opciones,
        index=opciones.index(actual),
        format_func=lambda c: f"{c} · {descripciones[c]}" if c else "— sin código CIE-10 —",
        key=f"f_dx_cie_{uid}",
        label_visibility="collapsed",
        help="Catálogo CIE-10 oficial del MINSA (incluye la RM 447-2024).",
    )
    if consulta.strip() and not candidatos:
        st.caption("Sin resultados en el catálogo para esa búsqueda.")
    if not dx["cie10"] and dx.get("_cie10_aviso"):
        st.caption(f"⚠️ {dx['_cie10_aviso']}")


def _seccion_plan(historia: dict) -> None:
    plan = historia.setdefault("plan", {})
    meds = plan.setdefault("medicamentos", [])
    with st.expander("Plan", expanded=True):
        cita = _valor("f_plan_cita", plan.get("proxima_cita"))
        _fila_fuentes([("plan.proxima_cita", cita)], "f_src_plan")
        st.markdown("**Medicamentos**")
        if not meds:
            st.caption("Sin medicamentos indicados")
        for med in list(meds):
            uid = med.setdefault("_uid", state.nuevo_uid())
            with st.container(border=True):
                c_nom, c_src, c_del = st.columns([11, 1, 1], vertical_alignment="center")
                med["nombre"] = c_nom.text_input(
                    "Medicamento", value=med.get("nombre") or "", key=f"f_med_nom_{uid}", label_visibility="collapsed"
                )
                _boton_fuente(c_src, med.get("_fuentes"), med if med.get("nombre") else None, f"f_med_src_{uid}")
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
            "plan.examenes_solicitados",
        )
        st.divider()
        _editor_textos(
            "Indicaciones",
            plan.setdefault("indicaciones", []),
            "f_plan_ind",
            "Ej: Reposo por 48 horas",
            "plan.indicaciones",
        )
        st.divider()
        plan["proxima_cita"] = st.text_input(
            "Próxima cita", value=plan.get("proxima_cita") or "", key="f_plan_cita",
            help=_ayuda(_fuente("plan.proxima_cita"), cita),
        )


def _guardar(historia: dict) -> None:
    final = state.strip_uids(historia)
    print("\n===== HISTORIA CLÍNICA GUARDADA =====")
    print(json.dumps(final, indent=2, ensure_ascii=False))
    print("=====================================\n", flush=True)
    state.set_stage(state.SAVED)


def _render_formulario(historia: dict) -> None:
    st.subheader("Historia Clínica")
    st.caption("📎 muestra de qué parte de la consulta sale cada dato · ⚠️ dato sin respaldo en la transcripción")
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
    # El formulario se dibuja primero en su columna para que la transcripción
    # muestre los vínculos ya actualizados con lo que el médico editó.
    with col_form:
        _render_formulario(historia)
    with col_transcript:
        _render_transcript(historia)
