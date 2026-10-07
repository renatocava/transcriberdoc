"""Formatos de informe ecográfico.

Cada formato replica una plantilla .docx de `plantillas/ecografia/`: los
mismos órganos, en el mismo orden y con el texto "normal" de la plantilla.
El médico dicta lo que ve en el monitor. Cada `___` de la plantilla es un
espacio con nombre (`bazo.longitud`): Claude devuelve solo los valores de las
medidas dictadas y, para una sección distinta de lo normal, su texto reescrito;
la app arma el informe con el texto fijo de la plantilla (`componer`). Así el
modelo no copia el texto normal y la respuesta es corta, lo que permite
actualizar el informe en vivo frase a frase (`aplicar_cambios`).

Un informe es un dict:

    {"plantilla": "abdomen",
     "paciente": {"nombre": str, "edad": int | None},
     "medico": str,               # médico que realiza el estudio (se elige, no se dicta)
     "fecha": "2026-10-04",
     "secciones": {"higado": "línea 1\\nlínea 2", ...},
     "conclusion": [str, ...]}

Las fuentes usan las rutas `paciente.nombre`, `secciones.higado`,
`conclusion[0]`, igual que en la historia clínica (ver lib/fuentes.py).
Sin dependencias de Streamlit: lo usan también las pruebas.
"""

from __future__ import annotations

import copy
import datetime as dt
import difflib
import re
import unicodedata
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
    #: Nombre de cada `___` del texto normal, en orden («lhd», «pared»...).
    espacios: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.normal.count(PENDIENTE) != len(self.espacios):
            raise ValueError(f"{self.clave}: {self.normal.count(PENDIENTE)} espacios ___ y {len(self.espacios)} nombres")

    @property
    def etiqueta(self) -> str:
        return self.etiqueta_ui or self.titulo.capitalize()

    @property
    def normal(self) -> str:
        return "\n".join(self.lineas)

    @property
    def marcada(self) -> str:
        """Texto normal con cada `___` como su marcador: «MIDE: LHD: {lhd} mm»."""
        nombres = iter(self.espacios)
        return re.sub(re.escape(PENDIENTE), lambda _: "{" + next(nombres) + "}", self.normal)


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
    ("pre", "post", "rpm"),
)
_ESPACIOS_PROSTATA = ("l", "ap", "t", "volumen")

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
                ), espacios=("lhd",)),
                Seccion("vesicula", "VESÍCULA BILIAR", (
                    "MIDE: ___ mm, DE PAREDES DELGADAS DE ___ mm, SIN EVIDENCIA DE CALCULOS EN SU INTERIOR.",
                ), espacios=("dimensiones", "pared")),
                Seccion("coledoco", "COLÉDOCO", ("PERMEABLE DE ___ mm.",), espacios=("calibre",)),
                Seccion("porta", "VENA PORTA", ("NO DILATADA DE ___ mm",), espacios=("calibre",)),
                Seccion("bazo", "BAZO", ("___ mm DE ECOESTRUCTURA NORMAL.",), espacios=("longitud",)),
                Seccion("pancreas", "PÁNCREAS", (
                    "DE MORFOLOGÍA Y ECOGENICIDAD CONSERVADA, SIN LESIÓN FOCAL CIRCUNSCRITA NI "
                    "PROCESOS INFLAMATORIOS, MIDE: ___ mm EN SU PORCION CEFALICA.",
                ), espacios=("cabeza",)),
                Seccion("rinon_der", "RIÑÓN DERECHO", (_RINON, "SUS DIMENSIONES SON: ___ mm."),
                        espacios=("dimensiones",)),
                Seccion("rinon_izq", "RIÑÓN IZQUIERDO", (_RINON, "SUS DIMENSIONES SON: ___ mm."),
                        espacios=("dimensiones",)),
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
                Seccion("mama_der", "MAMA DERECHA", _MAMA, espacios=("conductos",)),
                Seccion("mama_izq", "MAMA IZQUIERDA", _MAMA, espacios=("conductos",)),
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
                ), espacios=("l", "ap", "t")),
                Seccion("cervix", "CÉRVIX", ("CON CANAL NO DILATADO ___ mm.",), espacios=("canal",)),
                Seccion("endometrio", "ENDOMETRIO", ("HOMOGENEO DE ___ mm",), espacios=("grosor",)),
                Seccion("ovario_der", "OVARIO DERECHO", (_OVARIO,), espacios=("medida",)),
                Seccion("ovario_izq", "OVARIO IZQUIERDO", (_OVARIO,), espacios=("medida",)),
                Seccion("douglas", "FONDO DE SACO DE DOUGLAS", ("LIBRE.",)),
            ),
            ("ESTUDIO ECOGRAFICO TV DE CARACTERES MORFOLOGICOS NORMALES.",),
        ),
        Plantilla(
            "vesicoprostatica", "Ecografía vésico-prostática", "ECO VESICO PROSTATICO NORMAL.docx",
            "ECOGRAFIA VESICO-PROSTATICO",
            (
                Seccion("prostata", "PROSTATA", (_PROSTATA,), "Próstata", _ESPACIOS_PROSTATA),
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
                Seccion("rinon_der", "RIÑÓN DERECHO", (_RINON, "SUS DIMENSIONES SON: ___ mm\t\tCORTICAL: ___ mm"),
                        espacios=("dimensiones", "cortical")),
                Seccion("rinon_izq", "RIÑÓN IZQUIERDO", (_RINON, "SUS DIMENSIONES SON: ___ mm\t\tCORTICAL: ___ mm"),
                        espacios=("dimensiones", "cortical")),
                Seccion("prostata", "PROSTATA", (_PROSTATA,), "Próstata", _ESPACIOS_PROSTATA),
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


# --------------------------------------------------------------------------
# Espacios con nombre: el modelo da los valores, la app arma el texto
# --------------------------------------------------------------------------
_MARCADOR = re.compile(r"\{(\w+)\}")
#: Unidad repetida al final de una medida («98 mm»): la plantilla ya la pone.
_UNIDAD_FINAL = re.compile(r"\s*(mm|cm|cc|ml|%)\.?$", re.I)


def espacios(formato: str) -> dict[str, tuple[Seccion, str]]:
    """Ruta de cada espacio del formato («bazo.longitud») -> (sección, nombre)."""
    return {f"{s.clave}.{n}": (s, n) for s in PLANTILLAS[formato].secciones for n in s.espacios}


def parrafos(seccion: Seccion) -> dict[str, str]:
    """Clave de cada párrafo del texto normal (con marcadores) -> su texto.

    Un hallazgo reemplaza solo su párrafo: el resto de la sección (por ejemplo,
    la línea con la medida de los conductos) sigue siendo el de la plantilla.
    """
    lineas = seccion.marcada.split("\n")
    if len(lineas) == 1:
        return {seccion.clave: lineas[0]}
    return {f"{seccion.clave}.{i}": linea for i, linea in enumerate(lineas, start=1)}


def estado_vacio() -> dict[str, Any]:
    """Lo registrado de un informe antes de armarlo: aún nada dictado."""
    return {"paciente": {"nombre": "", "edad": None}, "medico": "", "medidas": {}, "hallazgos": {}, "conclusion": []}


def _rellenar(texto: str, valores: dict[str, str]) -> str:
    return _MARCADOR.sub(lambda m: valores.get(m[1]) or PENDIENTE, texto)


def registrados(estado: dict[str, Any]) -> dict[str, Any]:
    """Cada dato ya registrado por su clave: 'paciente.nombre', 'medidas.bazo.longitud',
    'hallazgos.higado', 'conclusion'. Son las claves que acepta `aplicar_cambios(fijos=...)`."""
    pac = estado.get("paciente") or {}
    datos = {
        "paciente.nombre": pac.get("nombre"),
        "paciente.edad": pac.get("edad"),
        **{f"medidas.{k}": v for k, v in (estado.get("medidas") or {}).items()},
        **{f"hallazgos.{k}": v for k, v in (estado.get("hallazgos") or {}).items()},
        "conclusion": tuple(estado.get("conclusion") or ()),
    }
    return {k: v for k, v in datos.items() if v not in (None, "", ())}


def aplicar_cambios(
    formato: str,
    estado: dict[str, Any],
    cambios: dict[str, Any],
    fijos: set[str] | frozenset[str] = frozenset(),
    ignorados: list[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Aplica lo que devolvió el modelo al estado del informe.

    Args:
        fijos: claves de `registrados` que no se pueden cambiar ni borrar (en
            vivo, un dato ya registrado solo cambia si el médico dice
            «modificar»). Lo que se intentó cambiar se anota en `ignorados`.

    Returns:
        (estado nuevo, rutas que tocó), con las rutas de las fuentes:
        'paciente.nombre', 'secciones.bazo', 'conclusion[0]'...
    """
    plantilla = PLANTILLAS[formato]
    por_clave = {s.clave: s for s in plantilla.secciones}
    por_parrafo = {k: (s, texto) for s in plantilla.secciones for k, texto in parrafos(s).items()}
    rutas_espacio = espacios(formato)
    cambios = cambios if isinstance(cambios, dict) else {}
    nuevo = copy.deepcopy(estado)
    tocadas: list[str] = []
    antes = registrados(estado)
    ignorados = [] if ignorados is None else ignorados

    def bloqueado(clave: str, valor: Any) -> bool:
        if clave in fijos and valor != antes.get(clave):
            ignorados.append(clave)
            return True
        return False

    pac = cambios.get("paciente") if isinstance(cambios.get("paciente"), dict) else {}
    nombre = str(pac.get("nombre") or "").strip()
    if nombre and not bloqueado("paciente.nombre", nombre):
        nuevo["paciente"]["nombre"] = nombre
        tocadas.append("paciente.nombre")
    try:
        edad = int(pac["edad"]) if pac.get("edad") not in (None, "") else None
    except (TypeError, ValueError):
        edad = None
    if edad is not None and not bloqueado("paciente.edad", edad):
        nuevo["paciente"]["edad"] = edad
        tocadas.append("paciente.edad")

    medidas = cambios.get("medidas") if isinstance(cambios.get("medidas"), dict) else {}
    for ruta, valor in medidas.items():
        if ruta not in rutas_espacio:
            continue
        valor = _UNIDAD_FINAL.sub("", str(valor or "").strip()).strip()
        if valor == PENDIENTE:
            valor = ""
        if bloqueado(f"medidas.{ruta}", valor or None):
            continue
        if valor:
            nuevo["medidas"][ruta] = valor
        else:  # "" borra una medida (el médico se corrigió)
            nuevo["medidas"].pop(ruta, None)
        tocadas.append(f"secciones.{rutas_espacio[ruta][0].clave}")

    hallazgos = cambios.get("hallazgos") if isinstance(cambios.get("hallazgos"), dict) else {}
    for clave, texto in hallazgos.items():
        if clave not in por_parrafo:
            continue
        seccion, normal = por_parrafo[clave]
        texto = _texto_seccion(texto, seccion)
        if texto == normal:
            texto = ""
        if bloqueado(f"hallazgos.{clave}", texto or None):
            continue
        if texto:
            nuevo["hallazgos"][clave] = texto
        else:  # "" o el texto normal: el párrafo vuelve a lo normal
            nuevo["hallazgos"].pop(clave, None)
        tocadas.append(f"secciones.{seccion.clave}")

    for clave in cambios.get("normales") or []:
        if clave in por_clave:
            tocadas.append(f"secciones.{clave}")

    conclusion = [str(c).strip() for c in cambios.get("conclusion") or [] if str(c).strip()]
    if conclusion and not bloqueado("conclusion", tuple(conclusion)):
        nuevo["conclusion"] = conclusion
        tocadas += [f"conclusion[{i}]" for i in range(len(conclusion))]
    return nuevo, list(dict.fromkeys(tocadas))


def componer(formato: str, estado: dict[str, Any], fecha: dt.date | None = None) -> dict[str, Any]:
    """El informe completo: el texto de la plantilla con los valores registrados."""
    plantilla = PLANTILLAS[formato]
    medidas = estado.get("medidas") or {}
    hallazgos = estado.get("hallazgos") or {}
    secciones = {
        s.clave: _rellenar(
            "\n".join(hallazgos.get(k) or texto for k, texto in parrafos(s).items()),
            {n: medidas.get(f"{s.clave}.{n}", "") for n in s.espacios},
        )
        for s in plantilla.secciones
    }
    # La conclusión normal de vejiga lleva el RPM: se completa con el dictado.
    rpm = medidas.get("volumenes.rpm")
    conclusion = estado.get("conclusion") or [c.replace(PENDIENTE, rpm) if rpm else c for c in plantilla.conclusion]
    datos = {"paciente": estado.get("paciente"), "medico": estado.get("medico"), "secciones": secciones,
             "conclusion": conclusion}
    return normalizar_informe(formato, datos, fecha)


def esquema_cambios(formato: str, conclusion_propuesta: bool) -> dict[str, Any]:
    """JSON Schema del tool: solo lo que dice el dictado, nunca el texto normal.

    Args:
        conclusion_propuesta: si el médico no dicta conclusión, el modelo
            propone una (extracción completa) o la deja vacía (en vivo).
    """
    plantilla = PLANTILLAS[formato]
    lineas_con = {
        ruta: next(l for l in seccion.marcada.split("\n") if "{" + nombre + "}" in l)
        for ruta, (seccion, nombre) in espacios(formato).items()
    }
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
            "medidas": {
                "type": "object",
                "description": (
                    "Solo las medidas dictadas, por su nombre: el número sin la unidad, en la unidad de la "
                    "plantilla (si dicta en centímetros, pásalo a milímetros; ml equivale a cc). Dos o tres "
                    "diámetros: «78 x 32». Para borrar una medida que el médico corrigió: \"\"."
                ),
                "properties": {
                    ruta: {"type": "string", "description": f"{seccion.etiqueta}: «{lineas_con[ruta]}»"}
                    for ruta, (seccion, _) in espacios(formato).items()
                },
                "additionalProperties": False,
            },
            "hallazgos": {
                "type": "object",
                "description": (
                    "Solo los párrafos que el médico describe distintos de lo normal: el párrafo reescrito "
                    "en el mismo estilo (MAYÚSCULAS, frases cortas), sin el rótulo. Conserva los marcadores "
                    "{nombre} de las medidas de la plantilla (sus valores van en `medidas`). Cada frase "
                    "normal que deja de ser cierta con lo dictado se quita o se cambia por lo dictado "
                    "(con una lesión dentro, el órgano ya no es «de morfología y dimensiones conservadas»). "
                    "Las medidas propias del hallazgo (tamaño de un nódulo, de un cálculo) van escritas en el "
                    "texto, en milímetros (1.2 cm son 12 mm). Los demás párrafos de la sección no se tocan. "
                    "\"\" devuelve el párrafo a lo normal."
                ),
                "properties": {
                    clave: {
                        "type": "string",
                        "description": f"{s.etiqueta}{'' if clave == s.clave else ', párrafo ' + clave.split('.')[1]}. "
                        f"Normal: {texto}",
                    }
                    for s in plantilla.secciones
                    for clave, texto in parrafos(s).items()
                },
                "additionalProperties": False,
            },
            "normales": {
                "type": "array",
                "items": {"type": "string", "enum": [s.clave for s in plantilla.secciones]},
                "description": (
                    "Secciones que el médico menciona como normales, sin medidas ni hallazgos, incluidas "
                    "las que abarca algo general como «el resto normal»."
                ),
            },
            "conclusion": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Ítems de la conclusión, uno por línea. "
                    + (
                        "La que dicte el médico; si no dicta ninguna, propón una breve que resuma los "
                        "hallazgos dictados sin agregar diagnósticos que el médico no dijo (o la normal si "
                        "todo es normal): "
                        if conclusion_propuesta
                        else "Solo si el médico la dicta; si no, omítela. Conclusión normal: "
                    )
                    + " / ".join(plantilla.conclusion)
                ),
            },
        },
        # En la extracción completa la conclusión es obligatoria: si faltara, el
        # informe quedaría con la normal de la plantilla aunque haya hallazgos.
        "required": ["conclusion"] if conclusion_propuesta else [],
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


# --------------------------------------------------------------------------
# Resaltado para la vista del informe: qué es plantilla y qué se dictó
# --------------------------------------------------------------------------
#: Tipos de trozo que devuelve `resaltar`.
FIJO, DICTADO, FALTA = "fijo", "dictado", "pendiente"

_TOKEN = re.compile(rf"{PENDIENTE}|\w+|[^\w\s]|\s+")


def _clave_token(token: str) -> str:
    """Comparación sin mayúsculas ni tildes: «HOMOGÉNEA» y «homogenea» son el mismo texto."""
    sin_tildes = unicodedata.normalize("NFD", token.upper())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


def resaltar(base: str, texto: str) -> list[tuple[str, str]]:
    """Trozos `(tipo, texto)` de `texto` comparado con el texto normal `base`.

    FIJO: igual que la plantilla. DICTADO: medidas puestas en los `___` y todo
    lo que el médico cambió o agregó. FALTA: medidas que siguen en `___`.
    Los trozos, unidos, reproducen `texto` tal cual.
    """
    tokens = _TOKEN.findall(texto)
    palabras = [i for i, t in enumerate(tokens) if not t.isspace()]
    base_palabras = [_clave_token(t) for t in _TOKEN.findall(base) if not t.isspace()]
    tipos = [FIJO] * len(tokens)
    comparador = difflib.SequenceMatcher(
        None, base_palabras, [_clave_token(tokens[i]) for i in palabras], autojunk=False
    )
    for op, _, _, j1, j2 in comparador.get_opcodes():
        if op != "equal":
            for j in range(j1, j2):
                tipos[palabras[j]] = DICTADO
    for i, t in enumerate(tokens):
        if t == PENDIENTE:
            tipos[i] = FALTA
        # Un espacio entre dos palabras dictadas es parte del mismo dato («78 x 32»).
        elif t.isspace() and 0 < i < len(tokens) - 1 and tipos[i - 1] == tipos[i + 1] == DICTADO:
            tipos[i] = DICTADO

    trozos: list[tuple[str, str]] = []
    for tipo, t in zip(tipos, tokens):
        if trozos and trozos[-1][0] == tipo:
            trozos[-1] = (tipo, trozos[-1][1] + t)
        else:
            trozos.append((tipo, t))
    return trozos
