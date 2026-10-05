"""Revisión del informe ecográfico: la conversación a la izquierda y el informe a la derecha.

El informe se ve como quedará en el Word, con lo dictado en verde y lo que
falta en ámbar; «Editar» cambia la vista por el formulario de campos.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import streamlit as st

from components.review import (
    _ayuda,
    _boton_fuente,
    _enfocar,
    _fila_fuentes,
    _fuente,
    _numeros,
    _valor,
    render_transcript,
    selector_formato,
)
from lib import state
from lib.ecografias import PENDIENTE, PLANTILLAS, Plantilla, Seccion, calculos, es_normal, pendientes
from lib.fuentes import de_texto, editado
from lib.hablantes import es_dictado
from lib.informe_docx import generar_docx, nombre_archivo
from lib.informe_html import LEYENDA, html_informe

#: Vista (False) o formulario de edición (True) del informe en revisión.
CLAVE_EDITAR = "f_eco_editar"

ETIQUETAS_PACIENTE = {
    "paciente.nombre": "Nombre",
    "paciente.edad": "Edad",
    "medico": "Médico solicitante",
}


def _etiquetas(plantilla: Plantilla) -> dict[str, str]:
    return {**ETIQUETAS_PACIENTE, **{f"secciones.{s.clave}": s.etiqueta for s in plantilla.secciones}}


def _seccion_paciente(informe: dict) -> None:
    pac = informe.setdefault("paciente", {})
    with st.container(border=True):
        _fila_fuentes(
            [
                ("paciente.nombre", _valor("f_eco_nombre", pac.get("nombre"))),
                ("paciente.edad", _valor("f_eco_edad", pac.get("edad"))),
                ("medico", _valor("f_eco_medico", informe.get("medico"))),
            ],
            "f_eco_src_pac",
            ETIQUETAS_PACIENTE,
        )
        c1, c2 = st.columns([3, 1])
        pac["nombre"] = c1.text_input(
            "Nombres", value=pac.get("nombre") or "", key="f_eco_nombre",
            help=_ayuda(_fuente("paciente.nombre"), _valor("f_eco_nombre", pac.get("nombre"))),
        )
        pac["edad"] = c2.number_input(
            "Edad (años)", min_value=0, max_value=120, step=1, value=pac.get("edad"), key="f_eco_edad",
            help=_ayuda(_fuente("paciente.edad"), _valor("f_eco_edad", pac.get("edad"))),
        )
        c3, c4 = st.columns([3, 1])
        informe["medico"] = c3.text_input(
            "Médico solicitante", value=informe.get("medico") or "", key="f_eco_medico",
            placeholder="PARTICULAR",
            help=_ayuda(_fuente("medico"), _valor("f_eco_medico", informe.get("medico"))),
        )
        fecha = c4.date_input(
            "Fecha", value=dt.date.fromisoformat(informe["fecha"]), key="f_eco_fecha", format="DD/MM/YYYY",
        )
        informe["fecha"] = fecha.isoformat()


def _estado(fuente: dict[str, Any] | None, texto: str, seccion: Seccion) -> str:
    """Rótulo corto de cómo se llenó la sección."""
    normal = es_normal(seccion, texto)
    if not fuente:
        if texto.strip() == seccion.normal:
            return ":orange[no se mencionó · texto normal de la plantilla]"
        return ":orange[⚠️ sin respaldo en la transcripción]"
    marca = " ✏️" if editado(fuente, texto) else ""
    return f":gray[{'normal' if normal else 'con hallazgos'} · dictado {_numeros(fuente)}{marca}]"


def _secciones(informe: dict, plantilla: Plantilla) -> None:
    secciones = informe.setdefault("secciones", {})
    for s in plantilla.secciones:
        ruta = f"secciones.{s.clave}"
        key = f"f_eco_sec_{s.clave}"
        texto = _valor(key, secciones.get(s.clave, s.normal))
        fuente = _fuente(ruta)
        with st.container(border=True):
            c_tit, c_src = st.columns([12, 1], vertical_alignment="center")
            c_tit.markdown(f"**{s.titulo or s.etiqueta}** &nbsp; {_estado(fuente, texto, s)}")
            _boton_fuente(c_src, fuente, texto, f"f_eco_src_{s.clave}")
            # Sin `value=`: el botón de restaurar escribe en la key del widget.
            st.session_state.setdefault(key, secciones.get(s.clave, s.normal))
            secciones[s.clave] = st.text_area(
                s.etiqueta,
                height=max(68, 26 * (len(texto) // 70 + texto.count("\n") + 1)),
                key=key,
                label_visibility="collapsed",
                help=_ayuda(fuente, texto),
            )
            texto = secciones[s.clave]
            notas = []
            if texto.count(PENDIENTE):
                notas.append(f"✏️ {texto.count(PENDIENTE)} medida(s) sin dictar ({PENDIENTE})")
            notas += calculos(texto)
            if notas:
                st.caption(" · ".join(notas))
            if not es_normal(s, texto):
                st.button(
                    "↺ Restaurar texto normal", key=f"f_eco_rst_{s.clave}", type="tertiary",
                    on_click=st.session_state.update, kwargs={key: s.normal},
                )


def _conclusion(informe: dict) -> None:
    with st.container(border=True):
        st.markdown("**CONCLUSIÓN**")
        fuentes = st.session_state.get("fuentes", {})
        actuales = informe.get("conclusion") or []
        con_fuente = [(t, de_texto(fuentes, "conclusion", t)) for t in actuales]
        if any(f for _, f in con_fuente):
            with st.container(horizontal=True, gap="small"):
                for i, (t, f) in enumerate(con_fuente):
                    if f:
                        st.button(
                            f"📎 Ítem {i + 1} · {_numeros(f)}", key=f"f_eco_src_conc_{i}", type="tertiary",
                            help=_ayuda(f, t), on_click=_enfocar, args=(f["ids"],),
                        )
        sin_fuente = [i + 1 for i, (_, f) in enumerate(con_fuente) if not f]
        texto = st.text_area(
            "Conclusión", value="\n".join(actuales), key="f_eco_conc", label_visibility="collapsed",
            height=max(68, 30 * (len(actuales) + 1)),
            help="Un ítem por línea; cada uno sale con su viñeta en el informe.",
        )
        informe["conclusion"] = [l.strip() for l in texto.split("\n") if l.strip()]
        if sin_fuente:
            st.caption(
                f"⚠️ Ítem {', '.join(map(str, sin_fuente))}: propuesto sin que el médico lo dictara o "
                "editado a mano. Verifícalo."
            )


def boton_descarga(informe: dict, key: str, primario: bool = False, texto: str = "⬇️ Descargar informe (.docx)") -> None:
    try:
        datos = generar_docx(informe)
    except Exception as exc:  # una plantilla dañada no debe tumbar la revisión
        st.error(f"No se pudo generar el Word: {exc}")
        return
    st.download_button(
        texto,
        data=datos,
        file_name=nombre_archivo(informe),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=key,
        type="primary" if primario else "secondary",
        use_container_width=True,
    )


def _guardar(informe: dict) -> None:
    print("\n===== INFORME ECOGRÁFICO GUARDADO =====")
    print(json.dumps(state.strip_uids(informe), indent=2, ensure_ascii=False))
    print("=======================================\n", flush=True)
    state.set_stage(state.SAVED)


def dictadas(informe: dict, fuentes: dict[str, Any]) -> set[str]:
    """Secciones (y "conclusion") que no son el texto normal sin tocar: dictadas o editadas."""
    plantilla = PLANTILLAS[informe["plantilla"]]
    claves = {
        s.clave for s in plantilla.secciones
        if f"secciones.{s.clave}" in fuentes or informe["secciones"].get(s.clave, "").strip() != s.normal
    }
    conclusion = informe.get("conclusion") or []
    if conclusion != list(plantilla.conclusion) or any(de_texto(fuentes, "conclusion", t) for t in conclusion):
        claves.add("conclusion")
    return claves


def vista_informe(informe: dict, dictadas_: set[str], titulo: str) -> None:
    """El informe tal como saldrá en el Word, con lo variable resaltado."""
    completo = not pendientes(informe)
    fondo, color = ("#DCFCE7", "#166534") if completo else ("#FEF3C7", "#92400E")
    c_tit, c_est = st.columns([3, 1], vertical_alignment="center")
    c_tit.markdown(f"**📄 {titulo}**")
    c_est.markdown(
        f"<div style='text-align:right'><span style='background:{fondo};color:{color};border-radius:6px;"
        f"padding:0.1rem 0.5rem;font-size:0.78rem'>{'Completo' if completo else 'Faltan medidas'}</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(html_informe(informe, dictadas_), unsafe_allow_html=True)
    st.markdown(LEYENDA, unsafe_allow_html=True)


def _render_formulario(informe: dict, plantilla: Plantilla) -> None:
    st.caption(
        "Cada órgano parte del texto normal de la plantilla. 📎 muestra de dónde sale lo dictado; "
        f"{PENDIENTE} marca una medida que falta."
    )
    _seccion_paciente(informe)
    _secciones(informe, plantilla)
    _conclusion(informe)
    st.button("✓ Ver informe", key="f_eco_ver", type="primary", use_container_width=True,
              on_click=st.session_state.update, kwargs={CLAVE_EDITAR: False})


def _render_conversacion(informe: dict, plantilla: Plantilla) -> None:
    dictado = es_dictado(st.session_state["speaker_mapping"])
    st.markdown(f"**💬 {'Dictado del médico' if dictado else 'Conversación'}**")
    render_transcript(informe, _etiquetas(plantilla), {"conclusion": "Conclusión"})


def render_informe(informe: dict) -> None:
    plantilla = PLANTILLAS[informe["plantilla"]]
    izq, der = st.columns([5, 6], gap="large")
    with izq:
        _render_conversacion(informe, plantilla)
    with der:
        selector_formato()
        with st.container(border=True):
            if st.session_state.get(CLAVE_EDITAR):
                _render_formulario(informe, plantilla)
            else:
                vista_informe(informe, dictadas(informe, st.session_state.get("fuentes", {})), "Informe")
                c_ed, c_des = st.columns(2)
                c_ed.button("✏️ Editar", key="f_eco_editar_btn", use_container_width=True,
                            on_click=st.session_state.update, kwargs={CLAVE_EDITAR: True})
                with c_des:
                    boton_descarga(informe, "f_eco_descargar", texto="⬇️ Descargar")

        faltan = pendientes(informe)
        if faltan:
            st.warning(f"Quedan medidas sin dictar ({PENDIENTE}) en: {', '.join(faltan)}.")
        c_ok, c_no = st.columns(2)
        if c_ok.button("Guardar informe", type="primary", use_container_width=True):
            _guardar(informe)
            st.rerun()
        if c_no.button("Descartar", use_container_width=True):
            state.reset()
            st.rerun()
