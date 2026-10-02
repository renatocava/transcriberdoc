"""Convierte el Excel oficial CIE-10 del MINSA en `data/cie10.sqlite`.

Fuente: "CIE-10 (MINSA – Excel)", enlazado desde REUNIS
(https://www.minsa.gob.pe/reunis/?op=3&niv=1) como `CIE10_MINSA_OFICIAL.xlsx`,
hoja "VOLUMEN VIGENTE". Ya incorpora la RM 447-2024-MINSA: trae los 390 códigos
del Anexo 1 y ninguno de los 20 del Anexo 2. Esos 20 se agregan aquí con
`vigente = 0` para poder avisar si alguien los usa.

Solo usa la biblioteca estándar (el .xlsx se lee como zip + XML).

    python scripts/construir_cie10.py ~/Downloads/CIE10_MINSA_OFICIAL.xlsx
    python scripts/construir_cie10.py CIE10_MINSA_OFICIAL.xlsx --anexo1 "ANEXO 01.pdf"   # + verificación
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "data" / "cie10.sqlite"

URL_REUNIS = "https://www.minsa.gob.pe/reunis/?op=3&niv=1"
URL_ARCHIVO = "https://files.minsa.gob.pe/s/szimSEZTwFrQR25"
HOJA = "VOLUMEN VIGENTE"

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_CODIGO = re.compile(r"^([A-Z]\d{2}[0-9A-Z]{0,3})\s*-\s*(.+)$")
_CAPITULO = re.compile(r"^CAP[IÍ]TULO\s+([IVXL]+)\s*:?\s*(.*)$", re.I)
_GRUPO = re.compile(r"^\(\s*([A-Z]\d{2})\s*(?:-\s*([A-Z]\d{2}))?\s*\)\s*(.+)$")

#: Anexo 2 de la RM 447-2024-MINSA: cese de uso. Transcrito del PDF escaneado
#: (el OCR lee la «I» de I84x como «1»).
CESADOS = {
    "I840": "HEMORROIDES INTERNAS TROMBOSADAS",
    "I841": "HEMORROIDES INTERNAS CON OTRAS COMPLICACIONES",
    "I842": "HEMORROIDES INTERNAS SIN COMPLICACION",
    "I843": "HEMORROIDES EXTERNAS TROMBOSADAS",
    "I844": "HEMORROIDES EXTERNAS CON OTRAS COMPLICACIONES",
    "I845": "HEMORROIDES EXTERNAS SIN COMPLICACION",
    "I846": "PROMINENCIAS CUTANEAS, RESIDUO DE HEMORROIDES",
    "I847": "HEMORROIDES TROMBOSADAS NO ESPECIFICADAS",
    "I848": "HEMORROIDES NO ESPECIFICADAS, CON OTRAS COMPLICACIONES",
    "I849": "HEMORROIDES NO ESPECIFICADAS, SIN COMPLICACION",
    "F640": "TRANSEXUALISMO",
    "F641": "TRANSVESTISMO DE ROL DUAL",
    "F642": "TRASTORNO DE LA IDENTIDAD DE GENERO EN LA NIÑEZ",
    "F648": "OTROS TRASTORNOS DE LA IDENTIDAD DE GENERO",
    "F649": "TRASTORNO DE LA IDENTIDAD DE GENERO, NO ESPECIFICADO",
    "F651": "TRANSVESTISMO FETICHISTA",
    "F661": "ORIENTACION SEXUAL EGODISTONICA",
    "A90X": "DENGUE",
    "A91X": "DENGUE HEMORRAGICO",
    "U069": "ENFERMEDAD DEL VIRUS ZIKA, NO ESPECIFICADA",
}

#: Errores de codificación del Excel original. Ö, † y – son legítimos y se dejan.
CORRECCIONES = [("Â\xa0", " "), ("\xa0", " "), ("ˆ", "E")]


def _limpiar(texto: str) -> str:
    for malo, bueno in CORRECCIONES:
        texto = texto.replace(malo, bueno)
    return re.sub(r"\s+", " ", texto).strip()


def leer_columna_a(xlsx: Path) -> list[str]:
    """Textos de la columna A de la única hoja, en orden."""
    z = zipfile.ZipFile(xlsx)
    hojas = [s.get("name") for s in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{{{_NS['m']}}}sheet")]
    if hojas != [HOJA]:
        sys.exit(f"Se esperaba una sola hoja «{HOJA}» y hay: {hojas}")
    compartidos = [
        "".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS)
    ]
    textos = []
    for celda in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(f"{{{_NS['m']}}}c"):
        if not celda.get("r", "").startswith("A") or not celda.get("r")[1:].isdigit():
            continue
        v = celda.find("m:v", _NS)
        if v is not None:
            textos.append(compartidos[int(v.text)] if celda.get("t") == "s" else v.text)
    return textos


def parsear(textos: list[str]):
    capitulos, grupos, codigos, ignoradas = [], [], [], []
    for crudo in textos[2:]:  # título y encabezado
        linea = _limpiar(crudo or "")
        if not linea:
            continue
        if m := _CODIGO.match(linea):
            codigos.append((m[1], m[2].strip(), len(grupos)))
        elif m := _GRUPO.match(linea):
            grupos.append((m[1], m[2] or m[1], m[3].strip(), len(capitulos)))
        elif m := _CAPITULO.match(linea):
            capitulos.append((m[1].upper(), m[2].strip()))
        else:
            ignoradas.append(linea)
    return capitulos, grupos, codigos, ignoradas


def verificar_anexo1(pdf: Path, catalogo: set[str]) -> str:
    texto = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    encontrados = set()
    # El lookahead descarta los rangos de grupo: «(A90 - A99) FIEBRES VIRALES...».
    for c in re.findall(r"\b([A-Z1]\d{2}[0-9A-Z]{0,3})\s?-\.?\s?(?![A-Z]\d{2}\))[A-ZÑ]", texto):
        c = ("I" + c[1:]) if c[0] == "1" else c  # OCR: I -> 1
        encontrados.add(re.sub(r"XO$", "X0", c))  # OCR: 0 -> O
    faltan = sorted(encontrados - catalogo)
    if faltan:
        sys.exit(f"Anexo 1: {len(faltan)} códigos no están en el Excel: {faltan[:20]}")
    return f"{len(encontrados)}/{len(encontrados)} códigos del Anexo 1 presentes"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--anexo1", type=Path, help="PDF del Anexo 1 de la RM 447-2024 para verificar")
    args = ap.parse_args()

    capitulos, grupos, codigos, ignoradas = parsear(leer_columna_a(args.xlsx))
    catalogo = {c for c, _, _ in codigos}

    # Validaciones: si algo no cuadra, mejor no generar el archivo.
    errores = []
    if len(capitulos) != 22:
        errores.append(f"se esperaban 22 capítulos y hay {len(capitulos)}")
    if len(catalogo) != len(codigos):
        errores.append(f"{len(codigos) - len(catalogo)} códigos duplicados")
    if not 14000 <= len(codigos) <= 16000:
        errores.append(f"número de códigos fuera de rango: {len(codigos)}")
    if ignoradas:
        errores.append(f"{len(ignoradas)} líneas sin interpretar: {ignoradas[:5]}")
    if presentes := sorted(set(CESADOS) & catalogo):
        errores.append(f"códigos cesados por la RM 447-2024 aún presentes: {presentes}")
    if errores:
        sys.exit("No se generó el catálogo:\n  - " + "\n  - ".join(errores))
    anexo1 = verificar_anexo1(args.anexo1, catalogo) if args.anexo1 else "no verificado en esta ejecución"

    props = zipfile.ZipFile(args.xlsx).read("docProps/core.xml").decode()
    modificado = (re.search(r"<dcterms:modified[^>]*>([^<]+)<", props) or [None, ""])[1]

    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.unlink(missing_ok=True)
    con = sqlite3.connect(SALIDA)
    con.executescript(
        """
        CREATE TABLE capitulos (id INTEGER PRIMARY KEY, numero TEXT NOT NULL, titulo TEXT NOT NULL);
        CREATE TABLE grupos (
            id INTEGER PRIMARY KEY, desde TEXT NOT NULL, hasta TEXT NOT NULL,
            titulo TEXT NOT NULL, capitulo_id INTEGER REFERENCES capitulos(id));
        CREATE TABLE codigos (
            id INTEGER PRIMARY KEY,
            codigo TEXT NOT NULL UNIQUE,          -- sin punto, como en el HIS: J039
            descripcion TEXT NOT NULL,
            grupo_id INTEGER REFERENCES grupos(id),
            vigente INTEGER NOT NULL DEFAULT 1    -- 0 = cese de uso (RM 447-2024, Anexo 2)
        );
        CREATE VIRTUAL TABLE codigos_fts USING fts5(
            descripcion, content='codigos', content_rowid='id',
            tokenize='unicode61 remove_diacritics 2');
        CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
        """
    )
    con.executemany("INSERT INTO capitulos VALUES (?, ?, ?)", [(i + 1, n, t) for i, (n, t) in enumerate(capitulos)])
    con.executemany(
        "INSERT INTO grupos VALUES (?, ?, ?, ?, ?)",
        [(i + 1, d, h, t, cap) for i, (d, h, t, cap) in enumerate(grupos)],
    )
    con.executemany(
        "INSERT INTO codigos (codigo, descripcion, grupo_id, vigente) VALUES (?, ?, ?, 1)",
        [(c, d, g or None) for c, d, g in codigos],
    )
    con.executemany(
        "INSERT INTO codigos (codigo, descripcion, grupo_id, vigente) VALUES (?, ?, NULL, 0)",
        list(CESADOS.items()),
    )
    con.execute("INSERT INTO codigos_fts(codigos_fts) VALUES ('rebuild')")
    meta = {
        "fuente": "Ministerio de Salud del Perú (MINSA) — CIE-10 (MINSA – Excel), REUNIS",
        "url_reunis": URL_REUNIS,
        "url_archivo": URL_ARCHIVO,
        "archivo": args.xlsx.name,
        "sha256": hashlib.sha256(args.xlsx.read_bytes()).hexdigest(),
        "hoja": HOJA,
        "excel_modificado": modificado,
        "descargado": dt.datetime.fromtimestamp(args.xlsx.stat().st_mtime).isoformat(timespec="minutes"),
        "generado": dt.datetime.now().isoformat(timespec="minutes"),
        "base_legal": (
            "RM 553-2002-SA/DM (oficializa CIE-10); RM 447-2024-MINSA (Anexo 1: uso, "
            "Anexo 2: cese); DS 013-2006-SA art. 21"
        ),
        "codigos_vigentes": str(len(codigos)),
        "codigos_cesados": str(len(CESADOS)),
        "capitulos": str(len(capitulos)),
        "grupos": str(len(grupos)),
        "verificacion_anexo1": anexo1,
        "correcciones": "Â+espacio duro -> espacio (3 descripciones); ˆ -> E (2 títulos de capítulo)",
    }
    con.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
    con.commit()
    con.execute("VACUUM")
    con.close()

    print(f"{SALIDA.relative_to(RAIZ)} — {SALIDA.stat().st_size / 1024:.0f} KB")
    for k, v in meta.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
