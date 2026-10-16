"""De dónde sale cada dato: vínculo entre campos del formulario e intervenciones.

Claude recibe el diálogo numerado ([1], [2], ...) y devuelve, junto al
formulario, una lista `fuentes` con la ruta de cada campo y los números de las
intervenciones que lo respaldan. Aquí esa lista se valida y se convierte en:

- `_fuentes` dentro de cada diagnóstico y medicamento (viajan con el ítem
  aunque se borren o reordenen otros);
- un mapa `ruta -> fuente` para campos simples, y `ruta::texto -> fuente` para
  los ítems de listas de texto (alergias, indicaciones...).

Cada fuente es `{"ids": [índices 0-based de utterances], "valor": original}`;
`valor` permite avisar cuando el médico editó el dato después.
"""

from __future__ import annotations

import copy
import re
from typing import Any

SEP = "::"

#: Listas cuyos ítems son registros (dict) y llevan su propia fuente.
LISTAS_REGISTRO = {"diagnosticos", "plan.medicamentos"}

DESCRIPCION_CAMPO = (
    "Ruta del dato en el formulario. Campos simples: 'paciente.nombre', "
    "'motivo_consulta', 'examen_fisico.signos_vitales.temperatura', 'plan.proxima_cita'. "
    "Ítems de listas, con su índice desde 0: 'antecedentes.alergias[0]', "
    "'diagnosticos[1]', 'plan.medicamentos[0]', 'plan.indicaciones[2]'."
)


def esquema_fuentes() -> dict[str, Any]:
    """Propiedad `fuentes` que se agrega al input_schema del tool."""
    return {
        "type": "array",
        "description": (
            "Un elemento por cada dato registrado en el formulario, con los números [n] "
            "de las intervenciones de donde sale."
        ),
        "items": {
            "type": "object",
            "properties": {
                "campo": {"type": "string", "description": DESCRIPCION_CAMPO},
                "fragmentos": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Números [n] de las intervenciones que respaldan el dato.",
                },
            },
            "required": ["campo", "fragmentos"],
        },
    }


_RUTA = re.compile(r"^(?P<base>[a-z_.]+?)(?:\[(?P<idx>\d+)\])?$")


def _resolver(historia: dict[str, Any], base: str) -> Any:
    nodo: Any = historia
    for parte in base.split("."):
        if not isinstance(nodo, dict) or parte not in nodo:
            return None
        nodo = nodo[parte]
    return nodo


def vincular(
    historia: dict[str, Any], fuentes: list[dict[str, Any]], n_utterances: int
) -> dict[str, dict[str, Any]]:
    """Valida las fuentes del modelo y las ancla a la historia.

    Muta `historia` (agrega `_fuentes` a diagnósticos y medicamentos) y
    devuelve el mapa del resto de campos. Descarta rutas inexistentes y
    números de intervención fuera de rango: mejor sin fuente que con una falsa.
    """
    mapa: dict[str, dict[str, Any]] = {}
    for f in fuentes or []:
        if not isinstance(f, dict):
            continue
        ids = sorted(
            {n - 1 for n in f.get("fragmentos") or [] if isinstance(n, int) and 1 <= n <= n_utterances}
        )
        match = _RUTA.match(str(f.get("campo", "")).strip())
        if not ids or not match:
            continue
        base, idx = match["base"], match["idx"]
        destino = _resolver(historia, base)

        if idx is None:
            if destino is None or isinstance(destino, (dict, list)):
                continue
            mapa[base] = {"ids": ids, "valor": destino}
            continue

        if not isinstance(destino, list) or int(idx) >= len(destino):
            continue
        item = destino[int(idx)]
        if base in LISTAS_REGISTRO and isinstance(item, dict):
            valor = {k: v for k, v in item.items() if not k.startswith("_")}
            item["_fuentes"] = {"ids": ids, "valor": copy.deepcopy(valor)}
        elif isinstance(item, str):
            mapa[f"{base}{SEP}{item}"] = {"ids": ids, "valor": item}
    return mapa


#: Clave del mapa con las intervenciones que no se usaron en el informe:
#: `{"ids": [índices 0-based], "motivos": [motivo de cada una]}`.
DESCARTADAS = "_descartadas"

#: Por qué una intervención no va al informe -> cómo se muestra en la revisión.
MOTIVOS = {
    "indicacion_paciente": "indicación al paciente",
    "conversacion": "conversación ajena al estudio",
    "otra_persona": "habla de otra persona",
    "duda_descartada": "duda que el médico descartó",
    "otro": "ajeno al informe",
}


def esquema_descartadas() -> dict[str, Any]:
    """Propiedad `descartadas` que se agrega al input_schema del tool."""
    return {
        "type": "array",
        "description": (
            "Intervenciones que NO aportan nada al informe porque no describen el estudio de este "
            "paciente (vacío si todas aportan). No incluyas las que solo ordenan el dictado "
            "(«ahora el riñón»)."
        ),
        "items": {
            "type": "object",
            "properties": {
                "intervencion": {"type": "integer", "description": "Número [n] de la intervención."},
                "motivo": {"type": "string", "enum": list(MOTIVOS)},
            },
            "required": ["intervencion", "motivo"],
        },
    }


def anotar_descartadas(
    mapa: dict[str, dict[str, Any]], descartadas: list[dict[str, Any]], n_utterances: int
) -> None:
    """Agrega al mapa de fuentes las intervenciones descartadas por el modelo.

    Una intervención que respalda algún dato no se marca como descartada:
    si el modelo la usó, cuenta lo que quedó en el informe.
    """
    usadas = {i for ruta, f in mapa.items() if ruta != DESCARTADAS for i in f.get("ids", [])}
    motivos: dict[int, str] = {}
    for d in descartadas or []:
        n = d.get("intervencion") if isinstance(d, dict) else None
        if isinstance(n, int) and 1 <= n <= n_utterances and n - 1 not in usadas:
            motivo = d.get("motivo")
            motivos[n - 1] = motivo if motivo in MOTIVOS else "otro"
    mapa.pop(DESCARTADAS, None)
    if motivos:
        ids = sorted(motivos)
        mapa[DESCARTADAS] = {"ids": ids, "motivos": [motivos[i] for i in ids]}


def descartadas_de(mapa: dict[str, dict[str, Any]]) -> dict[int, str]:
    """Intervención (0-based) -> motivo, de las que no se usaron en el informe."""
    d = mapa.get(DESCARTADAS) or {}
    return dict(zip(d.get("ids", []), d.get("motivos", [])))


def de_texto(mapa: dict[str, dict[str, Any]], base: str, texto: str) -> dict[str, Any] | None:
    """Fuente de un ítem de lista de texto (se busca por su contenido)."""
    return mapa.get(f"{base}{SEP}{texto}")


def editado(fuente: dict[str, Any] | None, valor_actual: Any) -> bool:
    """True si el médico cambió el dato respecto de lo que se extrajo."""
    if not fuente:
        return False
    original = fuente.get("valor")
    if isinstance(original, dict) and isinstance(valor_actual, dict):
        actual = {k: v for k, v in valor_actual.items() if not k.startswith("_")}
        return actual != original
    return valor_actual != original
