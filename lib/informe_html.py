"""Informe ecográfico en HTML, con el aspecto de la plantilla Word.

El texto de la plantilla queda fijo; lo variable va resaltado: en verde lo que
ya tiene valor (lo dictado, el paciente, la fecha) y en ámbar lo que falta
dictar. Las secciones que el médico no mencionó van en gris: llevan el texto
normal de la plantilla tal cual.

Sin dependencias de Streamlit: lo usan también las pruebas.
"""

from __future__ import annotations

import datetime as dt
from html import escape
from typing import Any

from lib.ecografias import DICTADO, FALTA, PENDIENTE, PLANTILLAS, resaltar

ESTILOS = """
<style>
.inf { font-family: Cambria, Georgia, "Times New Roman", serif; font-size: 0.86rem;
       line-height: 1.45; color: #0F172A; text-align: justify; }
.inf .tit { font-family: Arial, Helvetica, sans-serif; font-weight: 700; font-size: 1.05rem;
            text-align: center; text-decoration: underline; margin: 0.2rem 0 1rem; }
.inf .cab { font-family: Arial, Helvetica, sans-serif; font-weight: 700; font-size: 0.8rem;
            margin: 0.1rem 0; }
.inf .cab span.r { display: inline-block; min-width: 4.6rem; }
.inf p { margin: 0 0 0.55rem; white-space: pre-wrap; }
.inf p.sig { margin-top: -0.45rem; }
.inf .sec-cab { margin-top: 0.9rem; }
.inf .gris { color: #94A3B8; }
.inf ul { margin: 0.2rem 0 0 1.2rem; padding: 0; }
.inf mark { border-radius: 4px; padding: 0 0.2rem; color: inherit; }
.inf mark.ok { background: #BBF7D0; color: #14532D; }
.inf mark.falta { background: #FDE68A; color: #78350F; }
.inf-ley { font-size: 0.78rem; color: #64748B; margin-top: 0.6rem; }
.inf-ley mark { border-radius: 4px; padding: 0 0.3rem; }
.inf-ley mark.ok { background: #BBF7D0; color: #14532D; }
.inf-ley mark.falta { background: #FDE68A; color: #78350F; }
</style>
"""

_CLASE = {DICTADO: "ok", FALTA: "falta"}


def _marca(texto: str, clase: str) -> str:
    return f'<mark class="{clase}">{escape(texto)}</mark>'


def _trozos(base: str, texto: str) -> str:
    return "".join(
        _marca(t, _CLASE[tipo]) if tipo in _CLASE else escape(t) for tipo, t in resaltar(base, texto)
    )


def _parrafos(base: str, texto: str, rotulo: str, gris: bool) -> list[str]:
    """Una línea por párrafo; el rótulo en negrita antes de la primera."""
    salida = []
    for linea in _trozos(base, texto).split("\n"):
        if not linea.strip():
            continue
        prefijo = f"<b>{escape(rotulo)}:</b> " if rotulo and not salida else ""
        clases = " ".join(c for c in ("gris" if gris else "", "sig" if salida else "") if c)
        salida.append(f'<p class="{clases}">{prefijo}{linea}</p>')
    return salida


def _cabecera(rotulo: str, valor: Any, sufijo: str = "") -> str:
    valor = str(valor).strip() if valor not in (None, "") else ""
    dato = _marca(valor.upper(), "ok") if valor else _marca(PENDIENTE, "falta")
    return f'<div class="cab"><span class="r">{rotulo}</span>:  {dato}{sufijo}</div>'


def html_informe(informe: dict[str, Any], dictadas: set[str] | frozenset[str] = frozenset()) -> str:
    """HTML del informe. `dictadas`: claves de sección (y "conclusion") que el médico mencionó."""
    plantilla = PLANTILLAS[informe["plantilla"]]
    pac = informe.get("paciente") or {}
    edad = pac.get("edad")
    fecha = dt.date.fromisoformat(informe["fecha"]) if informe.get("fecha") else dt.date.today()

    partes = [
        '<div class="inf">',
        f'<div class="tit">{escape(plantilla.examen)}</div>',
        _cabecera("NOMBRES", pac.get("nombre")),
        _cabecera("EDAD", edad, " AÑOS"),
        _cabecera("MÉDICO", informe.get("medico")),
        f'<div class="cab"><span class="r">EXAMEN</span>:  {escape(plantilla.examen)}</div>',
        _cabecera("FECHA", fecha.strftime("%d/%m/%Y")),
        '<div class="sec-cab"></div>',
    ]
    for s in plantilla.secciones:
        texto = informe.get("secciones", {}).get(s.clave, s.normal)
        partes += _parrafos(s.normal, texto, s.titulo, gris=s.clave not in dictadas)

    conclusion = informe.get("conclusion") or []
    base = "\n".join(plantilla.conclusion)
    gris = "" if "conclusion" in dictadas else ' class="gris"'
    items = _trozos(base, "\n".join(conclusion)).split("\n")
    partes.append(f"<p{gris}><b>CONCLUSIÓN:</b></p>")
    partes.append(f"<ul{gris}>" + "".join(f"<li>{i}</li>" for i in items if i.strip()) + "</ul>")
    partes.append("</div>")
    return ESTILOS + "".join(partes)


LEYENDA = (
    '<div class="inf-ley"><mark class="ok">Verde</mark> dictado · '
    f'<mark class="falta">{PENDIENTE}</mark> falta dictar · '
    '<span style="color:#94A3B8">gris</span>: no se mencionó, queda el texto normal</div>'
)
