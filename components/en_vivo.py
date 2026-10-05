"""Grabación con el informe en vivo: se llena mientras el médico habla o dicta.

El grabador del navegador (grabador_vivo/index.html) transcribe en tiempo real
directo con OpenAI, con una clave temporal que da este módulo, y muestra las
palabras mientras se dicen. Cada frase terminada llega a
`lib.en_vivo.SesionEnVivo`, que re-extrae el informe en segundo plano; un
fragmento se refresca solo para mostrarlo. Al detener, el resultado pasa directo
a la revisión; si hubo varias voces o faltó alguna frase, se procesa el audio
completo como antes.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from lib import state, voces
from lib.config import usar_mock
from lib.ecografias import PLANTILLAS, es_ecografia, normalizar_informe
from lib.en_vivo import SesionEnVivo, palabras_clave
from lib.hablantes import UNO
from lib.mock_data import transcripcion_mock
from lib.transcription import secreto_tiempo_real

_componente = components.declare_component("grabador_vivo", path=str(Path(__file__).parent / "grabador_vivo"))

#: La sesión en curso (SesionEnVivo), los mensajes del grabador ya atendidos y
#: la clave temporal de transcripción ({"formato", "valor", "expira"}).
CLAVE_SESION = "en_vivo"
CLAVE_VISTOS = "en_vivo_vistos"
CLAVE_SECRETO = "en_vivo_secreto"

REFRESCO_S = 1.5
#: Duración de la clave temporal y margen para renovarla antes de que venza:
#: la clave solo debe servir para abrir la sesión al pulsar grabar.
SECRETO_S, SECRETO_MARGEN_S = 600, 120

_EXTENSIONES = {"audio/ogg": "ogg", "audio/mp4": "m4a"}


def sesion() -> SesionEnVivo | None:
    return st.session_state.get(CLAVE_SESION)


def cerrar_sesion() -> None:
    s = st.session_state.pop(CLAVE_SESION, None)
    if s is not None:
        s.cerrar()


def _configuracion() -> tuple[str, str, tuple[list[str], list[str]]]:
    return state.formato(), state.modo_hablantes(), voces.referencias(state.medicos_consulta())


def _sesion_para(id_sesion: str) -> SesionEnVivo:
    s = sesion()
    if s is None or s.id != id_sesion:
        cerrar_sesion()
        s = SesionEnVivo(id_sesion, *_configuracion())
        st.session_state[CLAVE_SESION] = s
    return s


def _secreto() -> tuple[str | None, str | None]:
    """(clave temporal, aviso). La clave se reutiliza mientras le quede margen."""
    formato = state.formato()
    guardado = st.session_state.get(CLAVE_SECRETO)
    if guardado and guardado["formato"] == formato and guardado["expira"] - time.time() > SECRETO_MARGEN_S:
        return guardado["valor"], None
    try:
        valor, expira = secreto_tiempo_real(palabras_clave(formato), SECRETO_S)
    except Exception as exc:  # sin transcripción en vivo, se graba igual
        return None, f"Sin transcripción en vivo ({type(exc).__name__}): el informe se llenará al detener."
    st.session_state[CLAVE_SECRETO] = {"formato": formato, "valor": valor, "expira": expira}
    return valor, None


def grabador() -> None:
    """El botón de grabar con la transcripción en vivo; atiende sus mensajes."""
    if usar_mock():
        clave, aviso = None, None
        simulado = [u["text"] for u in transcripcion_mock(formato=state.formato())["utterances"]]
    else:
        (clave, aviso), simulado = _secreto(), None
    evento = _componente(clave=clave, simulado=simulado, aviso=aviso, key="w_grabador_vivo", default=None)
    s = sesion()
    if s is not None:
        s.configurar(*_configuracion())  # el formato se puede cambiar mientras se graba
    if not evento or not evento.get("sesion"):
        return
    # "turnos" trae siempre todas las frases: repetirlo no hace daño. "inicio" y
    # "fin" se atienden una sola vez (el valor del componente persiste entre reruns).
    if evento["evento"] != "turnos":
        vistos = st.session_state.setdefault(CLAVE_VISTOS, set())
        if (evento["sesion"], evento["evento"]) in vistos:
            return
        vistos.add((evento["sesion"], evento["evento"]))
        print(f"[en vivo] {evento['sesion'][:8]} evento {evento['evento']} · total {evento.get('total')}", flush=True)

    s = _sesion_para(evento["sesion"])
    s.agregar_turnos(evento.get("turnos") or [], extraer=evento["evento"] != "fin")
    if evento["evento"] == "fin":
        _terminar(s, evento)


def _terminar(s: SesionEnVivo, evento: dict[str, Any]) -> None:
    audio = base64.b64decode(evento.get("audio") or "")
    mime = (evento.get("mime") or "audio/webm").split(";")[0]
    st.session_state["audio_bytes"] = audio
    st.session_state["audio_filename"] = f"consulta.{_EXTENSIONES.get(mime, 'webm')}"
    st.session_state["last_audio_id"] = f"vivo::{s.id}"
    st.session_state["error"] = None

    # La transcripción en tiempo real no separa voces: con varias, se transcribe
    # el audio completo con diarización para que cada voz quede con su rol.
    dictado = state.modo_hablantes() == UNO
    resultado = None
    with st.spinner("Terminando el informe con todo lo dictado..." if dictado else "Terminando la grabación..."):
        try:
            resultado = s.terminar(int(evento.get("total") or 0), extraer_final=dictado)
        except Exception:  # el procesamiento normal reintenta y muestra el error
            resultado = None
    cerrar_sesion()

    if dictado and resultado and resultado["transcription"]["utterances"]:
        st.session_state["transcription"] = resultado["transcription"]
        st.session_state["speaker_mapping"] = resultado["mapping"]
        state.recien_extraida(resultado["historia"])
        st.session_state["fuentes"] = resultado["fuentes"]
        state.set_stage(state.REVIEW)
    else:
        state.set_stage(state.PROCESSING)
    st.rerun()


# --------------------------------------------------------------------------
# Vista en vivo
# --------------------------------------------------------------------------
def _estado(s: SesionEnVivo) -> str:
    if s.error:
        return f"⚠️ {s.error}"
    if s.extrayendo:
        return "⏳ Actualizando el informe…"
    if s.actualizado:
        return f"🟢 Actualizado hace {int(time.time() - s.actualizado)} s"
    return "🎙️ Escuchando… el informe se llena al terminar cada frase."


def _vista_historia(historia: dict[str, Any] | None) -> None:
    """La historia clínica en curso, solo lo que ya tiene datos."""
    st.markdown("**📄 Historia clínica · en vivo**")
    h = historia or {}
    p = h.get("paciente") or {}
    lineas = []
    if p.get("nombre") or p.get("edad"):
        lineas.append(f"**Paciente:** {p.get('nombre') or '—'}" + (f", {p['edad']} años" if p.get("edad") else ""))
    for clave, titulo in (("motivo_consulta", "Motivo de consulta"), ("enfermedad_actual", "Enfermedad actual")):
        if h.get(clave):
            lineas.append(f"**{titulo}:** {h[clave]}")
    ant = h.get("antecedentes") or {}
    for clave, titulo in (("personales", "Antecedentes"), ("alergias", "Alergias"),
                          ("medicamentos_actuales", "Medicación actual")):
        if ant.get(clave):
            lineas.append(f"**{titulo}:** {', '.join(ant[clave])}")
    ex = h.get("examen_fisico") or {}
    signos = {k: v for k, v in (ex.get("signos_vitales") or {}).items() if v}
    if signos:
        lineas.append("**Signos vitales:** " + " · ".join(f"{k.replace('_', ' ')} {v}" for k, v in signos.items()))
    if ex.get("hallazgos"):
        lineas.append(f"**Examen físico:** {ex['hallazgos']}")
    for dx in h.get("diagnosticos") or []:
        lineas.append(f"**Dx:** {dx.get('descripcion', '')} ({dx.get('tipo', '')}) {dx.get('cie10') or ''}".rstrip())
    plan = h.get("plan") or {}
    for m in plan.get("medicamentos") or []:
        lineas.append("**Rx:** " + " ".join(str(m.get(k) or "") for k in ("nombre", "dosis", "frecuencia", "duracion")).strip())
    for clave, titulo in (("examenes_solicitados", "Exámenes"), ("indicaciones", "Indicaciones")):
        if plan.get(clave):
            lineas.append(f"**{titulo}:** {'; '.join(plan[clave])}")
    if plan.get("proxima_cita"):
        lineas.append(f"**Próxima cita:** {plan['proxima_cita']}")
    st.markdown("\n\n".join(lineas) if lineas else ":gray[Aún no hay datos.]")


@st.fragment(run_every=REFRESCO_S)
def _informe_en_vivo() -> None:
    s = sesion()
    if s is None:
        return
    formato = state.formato()
    # Si se cambió el formato, se muestra el nuevo vacío hasta la siguiente extracción.
    historia = s.historia if s.formato_extraido == formato else None
    with st.container(border=True):
        if es_ecografia(formato):
            from components.informe_eco import dictadas, vista_informe  # import local: evita el ciclo

            informe = historia or normalizar_informe(formato, {})
            marcadas = dictadas(informe, s.fuentes) if historia else set()
            vista_informe(informe, marcadas, f"{PLANTILLAS[formato].nombre} · en vivo")
        else:
            _vista_historia(historia)
        st.caption(_estado(s) + " · Al detener, se revisa todo con el modelo principal.")


def informe() -> bool:
    """Informe en vivo. False si no se está grabando (se muestra la vista previa)."""
    if sesion() is None:
        return False
    _informe_en_vivo()
    return True
