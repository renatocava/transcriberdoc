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
