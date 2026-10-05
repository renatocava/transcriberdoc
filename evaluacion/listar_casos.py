"""Escribe evaluacion/casos.md: los casos en un formato fácil de revisar.

    python evaluacion/listar_casos.py

Además de listarlos, revisa cada caso: toda medida esperada debe poder leerse
en el dictado (en cifras o en palabras, o en cm si la plantilla va en mm). Lo que no cuadre
queda marcado con ⚠️ para revisarlo a mano.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from lib.ecografias import PLANTILLAS  # noqa: E402

CASOS = Path(__file__).resolve().parent / "casos"
SALIDA = Path(__file__).resolve().parent / "casos.md"


_UNIDADES = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "veintiuno": 21, "veintiun": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
    "noventa": 90, "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
    "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600, "setecientos": 700,
    "ochocientos": 800, "novecientos": 900,
}


def _en_palabras(texto: str) -> set[float]:
    """Números dictados en palabras: «ciento ocho», «dos punto cuatro», «treinta y cinco»."""
    import unicodedata

    plano = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    numeros, actual, decimal, en_decimal = set(), None, None, False
    for palabra in re.findall(r"[a-z]+", plano) + ["fin"]:
        if palabra in _UNIDADES:
            v = _UNIDADES[palabra]
            if en_decimal:
                decimal = (decimal or 0) + v
            else:
                actual = (actual or 0) + v
        elif palabra == "y" and actual is not None and not en_decimal:
            continue
        elif palabra == "punto" and actual is not None:
            en_decimal = True
        else:
            if actual is not None:
                numeros.add(float(f"{actual}.{decimal}") if decimal is not None else float(actual))
            actual, decimal, en_decimal = None, None, False
    return numeros


def _cifras(texto: str) -> set[float]:
    en_cifras = {float(c.replace(",", ".")) for c in re.findall(r"\d+(?:[.,]\d+)?", texto)}
    return en_cifras | _en_palabras(texto)


def revisar(caso: dict) -> list[str]:
    """Medidas esperadas que no se encuentran en el dictado (en cifras o palabras, ni en cm)."""
    dictado = " ".join(u["texto"] for u in caso["dictado"])
    cifras = _cifras(dictado)
    avisos = []
    for s in caso["secciones"]:
        for m in s["medidas"]:
            v = float(m["valor"])
            if v in cifras or (m["unidad"] == "mm" and round(v / 10, 2) in cifras):
                continue
            avisos.append(f"{s['clave']}: {v:g} {m['unidad']} no aparece en el dictado")
    return avisos


def main() -> int:
    casos = [json.loads(p.read_text()) for p in sorted(CASOS.glob("*.json"))]
    estados = Counter(s["estado"] for c in casos for s in c["secciones"])
    con_avisos = {c["id"]: revisar(c) for c in casos}
    lineas = [
        "# Casos de evaluación: informes ecográficos",
        "",
        "Dictados sintéticos (Claude Opus 5.5) con la respuesta esperada. **Revisa sobre todo la "
        "columna «esperado»**: el puntaje solo vale si eso es lo que un ecografista escribiría.",
        "",
        f"{len(casos)} casos · secciones: {estados['normal']} normales, {estados['hallazgo']} con hallazgo, "
        f"{estados['no_mencionado']} no mencionadas · "
        f"{sum(1 for a in con_avisos.values() if a)} casos con avisos ⚠️",
        "",
        "| id | escenario | paciente | hallazgos esperados | ⚠️ |",
        "|---|---|---|---|---|",
    ]
    for c in casos:
        hallazgos = "; ".join(f"{s['clave']}: {s['hallazgo']}" for s in c["secciones"] if s["estado"] == "hallazgo")
        edad = c["paciente"]["edad"]
        lineas.append(
            f"| [{c['id']}](#{c['id']}) | {c['escenario']} | {c['paciente']['nombre']}"
            f"{f', {edad}' if edad is not None else ''} | {hallazgos or '—'} | {len(con_avisos[c['id']]) or ''} |"
        )
    for c in casos:
        plantilla = PLANTILLAS[c["formato"]]
        etiquetas = {s.clave: s.etiqueta for s in plantilla.secciones}
        lineas += ["", f"## {c['id']}", "", f"**{plantilla.nombre}** · escenario `{c['escenario']}`  ",
                   f"Dificultad: {c['dificultad']}", "", "Dictado:", "", "````text"]
        lineas += [f"{'Médico' if u['rol'] == 'medico' else 'Asistente'}: {u['texto']}" for u in c["dictado"]]
        lineas += ["````", "", "Esperado:", "",
                   f"- Paciente: {c['paciente']['nombre'] or '—'}, edad {c['paciente']['edad']}; "
                   f"solicitante: {c['medico_solicitante'] or 'PARTICULAR'}"]
        for s in c["secciones"]:
            medidas = ", ".join(f"{m['valor']:g} {m['unidad']}" for m in s["medidas"]) or "sin medidas"
            extra = f" — {s['hallazgo']}" if s["hallazgo"] else ""
            lineas.append(f"- {etiquetas[s['clave']]}: **{s['estado']}** · {medidas}{extra}")
        if c["conclusion_dictada"]:
            lineas.append("- Conclusión dictada: " + " / ".join(c["conclusion_dictada"]))
        for aviso in con_avisos[c["id"]]:
            lineas.append(f"- ⚠️ {aviso}")
    SALIDA.write_text("\n".join(lineas) + "\n")
    print(f"{SALIDA.relative_to(RAIZ)}: {len(casos)} casos, {sum(map(len, con_avisos.values()))} avisos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
