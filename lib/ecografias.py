"""Formatos de informe ecográfico.

Cada formato replica una plantilla .docx de `plantillas/ecografia/`: los
mismos órganos, en el mismo orden y con el texto "normal" de la plantilla.
El médico dicta lo que ve en el monitor; Claude parte de ese texto normal,
pone las medidas dictadas en los `___` y reescribe solo lo que difiere.

Un informe es un dict:

    {"plantilla": "abdomen",
     "paciente": {"nombre": str, "edad": int | None},
     "medico": str,               # médico solicitante; vacío = PARTICULAR
     "fecha": "2026-10-04",
     "secciones": {"higado": "línea 1\\nlínea 2", ...},
     "conclusion": [str, ...]}

Las fuentes usan las rutas `paciente.nombre`, `medico`, `secciones.higado`,
`conclusion[0]`, igual que en la historia clínica (ver lib/fuentes.py).
Sin dependencias de Streamlit: lo usan también las pruebas.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Marca de una medida que el médico todavía no dictó.
PENDIENTE = "___"

CARPETA = Path(__file__).resolve().parent.parent / "plantillas" / "ecografia"

#: Formato de la historia clínica de consulta (el original de la app).
CONSULTA = "consulta"


@dataclass(frozen=True)
class Seccion:
    clave: str
    #: Rótulo en negrita del informe ("HÍGADO"). Vacío: líneas sin rótulo.
    titulo: str
    #: Texto normal; la primera línea va tras el rótulo, las demás en párrafos aparte.
    lineas: tuple[str, ...]
    etiqueta_ui: str = ""

    @property
    def etiqueta(self) -> str:
        return self.etiqueta_ui or self.titulo.capitalize()

    @property
    def normal(self) -> str:
        return "\n".join(self.lineas)


@dataclass(frozen=True)
class Plantilla:
    clave: str
    nombre: str
    archivo: str
    #: Texto de la línea EXAMEN del encabezado.
    examen: str
    secciones: tuple[Seccion, ...]
    conclusion: tuple[str, ...]

    @property
    def ruta(self) -> Path:
        return CARPETA / self.archivo


_RINON = (
    "DE MORFOLOGÍA, TAMAÑO Y LOCALIZACIÓN NORMAL; PARENQUIMA HOMOGÉNEO CON ADECUADA "
    "DIFERENCIACIÓN CORTICO MEDULAR. SENO RENAL SIN ECTASIA NI LITIASIS, NO LESIONES "
    "EXPANSIVAS, NI HIDRONEFROSIS."
)
_MAMA = (
    "PARÉNQUIMA HOMOGÉNEO DE ECOESTRUCTURA CONSERVADA; NO SE APRECIA LESIÓN FOCAL SOLIDA NI "
    "QUÍSTICA, ASÍ COMO TAMPOCO ÁREA DE DISTORSIÓN ARQUITECTURAL.",
    "CONDUCTOS GALACTÓFOROS DE DIÁMETROS NORMALES. MIDE: ___ mm",
    "REGIÓN AXILAR LIBRE DE ADENOPATIAS.",
)
_OVARIO = (
    "DE ___ mm; DE MORFOLOGÍA Y DIMENSIONES CONSERVADAS. REGIÓN ANEXIAL CORRESPONDIENTE SIN "
    "LESIÓN SÓLIDA, NI QUISTICAS."
)
_PROSTATA = (
    "DE ECOGENICIDAD PARENQUIMAL HOMOGENEA SIN CALCIFICACIONES INTRAPRENQUIMALES MIDE: "
    "L: ___ mm AP: ___ mm T: ___ mm VOL APROX. ___ cc"
)
_VOLUMENES = Seccion(
    "volumenes", "",
    ("PRE MICCIONAL: ___ cc", "POST MICCIONAL: ___ cc", "RPM: ___ %"),
    "Volúmenes vesicales",
)

PLANTILLAS: dict[str, Plantilla] = {
    p.clave: p
    for p in (
        Plantilla(
            "abdomen", "Ecografía de abdomen completo", "ECO ABDOMEN COMPLETO NORMAL.docx",
            "ECOGRAFIA DE ABDOMEN COMPLETO",
            (
                Seccion("higado", "HÍGADO", (
                    "PARÉNQUIMA HOMOGENEA DE ECOGENICIDAD CONSERVADA Y EN FORMA DIFUSA, DE BORDES "
                    "LOBULADOS. NO SE APRECIA DILATACIÓN DE LAS VÍAS BILIARES INTRAHEPÁTICAS.",
                    "MIDE: LHD: ___ mm",
                )),
                Seccion("vesicula", "VESÍCULA BILIAR", (
                    "MIDE: ___ mm, DE PAREDES DELGADAS DE ___ mm, SIN EVIDENCIA DE CALCULOS EN SU INTERIOR.",
                )),
                Seccion("coledoco", "COLÉDOCO", ("PERMEABLE DE ___ mm.",)),
                Seccion("porta", "VENA PORTA", ("NO DILATADA DE ___ mm",)),
                Seccion("bazo", "BAZO", ("___ mm DE ECOESTRUCTURA NORMAL.",)),
                Seccion("pancreas", "PÁNCREAS", (
                    "DE MORFOLOGÍA Y ECOGENICIDAD CONSERVADA, SIN LESIÓN FOCAL CIRCUNSCRITA NI "
                    "PROCESOS INFLAMATORIOS, MIDE: ___ mm EN SU PORCION CEFALICA.",
                )),
                Seccion("rinon_der", "RIÑÓN DERECHO", (_RINON, "SUS DIMENSIONES SON: ___ mm.")),
                Seccion("rinon_izq", "RIÑÓN IZQUIERDO", (_RINON, "SUS DIMENSIONES SON: ___ mm.")),
                Seccion("vejiga", "VEJIGA", (
                    "VACUA, PAREDES DELGADAS, SIN IMÁGENES SOLIDAS NI QUISTICAS EN SU INTERIOR.",
                )),
                Seccion("genitales", "GENITALES INTERNOS", (
                    "DE CARACTERES MORFOLOGICOS NORMALES PARA LA EDAD.",
                )),
                Seccion("douglas", "FONDO DE SACO DOUGLAS", ("LIBRE",)),
                Seccion("cavidad", "", ("NO LIQUIDO LIBRE NO MASAS",), "Cavidad abdominal"),
            ),
            ("ECOGRAFIA ABDOMEN COMPLETO DENTRO DE LIMITES NORMALES.",),
        ),
        Plantilla(
            "mama", "Ecografía de mamas", "ECO MAMA NORMAL.docx",
            "ECOGRAFIA DE MAMAS BILATERAL",
            (
                Seccion("mama_der", "MAMA DERECHA", _MAMA),
                Seccion("mama_izq", "MAMA IZQUIERDA", _MAMA),
            ),
            ("ECOGRAFIA DE AMBAS MAMAS DE CARACTERES MORFOLOGICOS NORMALES.",),
        ),
        Plantilla(
            "transvaginal", "Ecografía transvaginal", "ECO TV NORMAL.docx",
            "ECOGRAFIA TRANSVAGINAL",
            (
                Seccion("utero", "ÚTERO", (
                    "EN AVF LATERALIZADO A LA IZQUIERDA DE L: ___ mm AP: ___ mm T: ___ mm, MIOMETRIO "
                    "DE ECOGENICIDAD PARENQUIMAL HOMOGENO, SIN LESIONES SOLIDAS O QUISTICAS EN SU INTERIOR.",
                )),
                Seccion("cervix", "CÉRVIX", ("CON CANAL NO DILATADO ___ mm.",)),
                Seccion("endometrio", "ENDOMETRIO", ("HOMOGENEO DE ___ mm",)),
                Seccion("ovario_der", "OVARIO DERECHO", (_OVARIO,)),
                Seccion("ovario_izq", "OVARIO IZQUIERDO", (_OVARIO,)),
                Seccion("douglas", "FONDO DE SACO DE DOUGLAS", ("LIBRE.",)),
            ),
            ("ESTUDIO ECOGRAFICO TV DE CARACTERES MORFOLOGICOS NORMALES.",),
        ),
        Plantilla(
            "vesicoprostatica", "Ecografía vésico-prostática", "ECO VESICO PROSTATICO NORMAL.docx",
            "ECOGRAFIA VESICO-PROSTATICO",
            (
                Seccion("prostata", "PROSTATA", (_PROSTATA,), "Próstata"),
                Seccion("vejiga", "VEJIGA", (
                    "A MEDIANA REPLESION, PAREDES DELGADAS, CONTENIDO LÍQUIDO HOMOGÉNEO SIN CÁLCULOS "
                    "NI PROCESOS EXPANSIVOS EN SU INTERIOR.",
                )),
                _VOLUMENES,
            ),
            ("PROSTATA NORMAL DE ACUERDO A LA EDAD.", "VEJIGA CON RPM DE ___ %"),
        ),
        Plantilla(
            "vias_urinarias", "Ecografía de vías urinarias", "ECO VIAS URINARIAS NORMAL.docx",
            "ECOGRAFIA VIAS URINARIAS COMPLETA",
            (
                Seccion("rinon_der", "RIÑÓN DERECHO", (_RINON, "SUS DIMENSIONES SON: ___ mm\t\tCORTICAL: ___ mm")),
                Seccion("rinon_izq", "RIÑÓN IZQUIERDO", (_RINON, "SUS DIMENSIONES SON: ___ mm\t\tCORTICAL: ___ mm")),
                Seccion("prostata", "PROSTATA", (_PROSTATA,), "Próstata"),
                Seccion("vejiga", "VEJIGA", (
                    "ADECUADAMENTE DISTENDIDA, PAREDES DELGADAS, CONTENIDO LÍQUIDO HOMOGÉNEO SIN "
                    "CÁLCULOS NI PROCESOS EXPANSIVOS EN SU INTERIOR.",
                )),
                _VOLUMENES,
            ),
            ("RIÑONES DE CARACTERES MORFOLOGICOS NORMALES PARA LA EDAD.", "VEJIGA NORMAL CON RPM DE ___ %"),
        ),
    )
}

#: Formato -> etiqueta del selector de la pantalla inicial.
FORMATOS = {CONSULTA: "Historia clínica (consulta)", **{c: p.nombre for c, p in PLANTILLAS.items()}}

#: Formato preseleccionado al abrir la app.
FORMATO_INICIAL = "abdomen"


def es_ecografia(formato: str | None) -> bool:
    return formato in PLANTILLAS


# --------------------------------------------------------------------------
# Datos del informe
# --------------------------------------------------------------------------
_MESES = (
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SETIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
)


def fecha_larga(fecha: dt.date) -> str:
    """Fecha como la escriben las plantillas: «04 DE OCTUBRE DEL 2026»."""
    return f"{fecha.day:02d} DE {_MESES[fecha.month - 1]} DEL {fecha.year}"


def _texto_seccion(valor: Any, seccion: Seccion) -> str:
    texto = str(valor or "").strip()
    # A veces el modelo repite el rótulo («HÍGADO: ...»); el informe ya lo pone.
    if seccion.titulo and texto.upper().startswith(seccion.titulo + ":"):
        texto = texto[len(seccion.titulo) + 1:].strip()
    return texto


def normalizar_informe(formato: str, datos: dict[str, Any] | None, fecha: dt.date | None = None) -> dict[str, Any]:
    """Informe completo a partir de lo que devolvió el modelo.

    Toda sección ausente o vacía queda con el texto normal de la plantilla (y,
    al no tener fuente, la revisión la marca como no dictada). Nunca levanta
    excepción.
    """
    plantilla = PLANTILLAS[formato]
    datos = datos if isinstance(datos, dict) else {}
    pac = datos.get("paciente") if isinstance(datos.get("paciente"), dict) else {}
    try:
        edad = int(pac["edad"]) if pac.get("edad") not in (None, "") else None
    except (TypeError, ValueError):
        edad = None
    recibidas = datos.get("secciones") if isinstance(datos.get("secciones"), dict) else {}
    conclusion = [str(c).strip() for c in datos.get("conclusion") or [] if str(c).strip()]
    return {
        "plantilla": formato,
        "paciente": {"nombre": str(pac.get("nombre") or "").strip(), "edad": edad},
        "medico": str(datos.get("medico") or "").strip(),
        "fecha": (fecha or dt.date.today()).isoformat(),
        "secciones": {
            s.clave: _texto_seccion(recibidas.get(s.clave), s) or s.normal for s in plantilla.secciones
        },
        "conclusion": conclusion or list(plantilla.conclusion),
    }


def input_schema(formato: str) -> dict[str, Any]:
    """JSON Schema del tool para un formato; cada sección describe su texto normal."""
    plantilla = PLANTILLAS[formato]
    return {
        "type": "object",
        "properties": {
            "paciente": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre completo del paciente, si se dicta."},
                    "edad": {"anyOf": [{"type": "integer"}, {"type": "null"}], "description": "Edad en años."},
                },
            },
            "medico": {
                "type": "string",
                "description": "Médico que solicita el examen, solo si se menciona. Vacío si no.",
            },
            "secciones": {
                "type": "object",
                "properties": {
                    s.clave: {
                        "type": "string",
                        "description": (
                            f"{s.etiqueta}. Sin el rótulo; una línea por párrafo. Texto normal:\n{s.normal}"
                        ),
                    }
                    for s in plantilla.secciones
                },
                "required": [s.clave for s in plantilla.secciones],
            },
            "conclusion": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Ítems de la conclusión, uno por línea. Conclusión normal de la plantilla: "
                    + " / ".join(plantilla.conclusion)
                ),
            },
        },
        "required": ["paciente", "secciones", "conclusion"],
    }


def es_normal(seccion: Seccion, texto: str) -> bool:
    """True si el texto es el normal de la plantilla, con o sin las medidas puestas."""
    patron = re.escape(seccion.normal.strip()).replace(re.escape(PENDIENTE), r"\s*[^\n]+?\s*")
    return re.fullmatch(patron, texto.strip()) is not None


def pendientes(informe: dict[str, Any]) -> list[str]:
    """Etiquetas de las partes del informe que aún tienen medidas `___`."""
    plantilla = PLANTILLAS[informe["plantilla"]]
    faltan = [s.etiqueta for s in plantilla.secciones if PENDIENTE in informe["secciones"].get(s.clave, "")]
    if any(PENDIENTE in c for c in informe.get("conclusion", [])):
        faltan.append("Conclusión")
    return faltan


# --------------------------------------------------------------------------
# Cálculos de apoyo: la app los sugiere, nunca los escribe en el informe
# --------------------------------------------------------------------------
_NUM = r"(\d+(?:[.,]\d+)?)"


def _num(texto: str) -> float:
    return float(texto.replace(",", "."))


def _fmt(valor: float) -> str:
    return f"{valor:.1f}".rstrip("0").rstrip(".")


def calculos(texto: str) -> list[str]:
    """Volumen prostático y RPM calculados a partir de las medidas de una sección.

    Devuelve avisos para el médico; si el valor escrito no cuadra con el
    calculado, lo dice.
    """
    avisos = []
    m = re.search(rf"L:\s*{_NUM}\s*mm\s*AP:\s*{_NUM}\s*mm\s*T:\s*{_NUM}\s*mm", texto, re.I)
    if m and "VOL" in texto.upper():
        vol = 0.52 * _num(m[1]) * _num(m[2]) * _num(m[3]) / 1000
        escrito = re.search(rf"VOL[^0-9_]*{_NUM}\s*cc", texto, re.I)
        aviso = f"Volumen calculado (elipsoide, L×AP×T×0,52): {_fmt(vol)} cc"
        if escrito and abs(_num(escrito[1]) - vol) > max(1.0, vol * 0.1):
            aviso += f" — ⚠️ el informe dice {escrito[1]} cc"
        avisos.append(aviso)

    pre = re.search(rf"PRE\s*MICCIONAL:\s*{_NUM}\s*cc", texto, re.I)
    post = re.search(rf"POST\s*MICCIONAL:\s*{_NUM}\s*cc", texto, re.I)
    if pre and post and _num(pre[1]) > 0:
        rpm = _num(post[1]) / _num(pre[1]) * 100
        escrito = re.search(rf"RPM:\s*{_NUM}\s*%", texto, re.I)
        aviso = f"RPM calculado (post / pre): {_fmt(rpm)} %"
        if escrito and abs(_num(escrito[1]) - rpm) > 1:
            aviso += f" — ⚠️ el informe dice {escrito[1]} %"
        avisos.append(aviso)
    return avisos
