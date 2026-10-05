"""Transcripción e informe en vivo: el informe se llena mientras el médico habla.

El navegador (components/grabador_vivo/) transcribe en tiempo real directo con
OpenAI (`gpt-live-transcribe`), con una clave temporal que da el servidor: las
palabras aparecen en pantalla mientras se dicen y, en cada pausa, la frase
terminada llega aquí como una intervención. Con lo transcrito hasta ese momento
el informe se actualiza en segundo plano con un modelo rápido. En ecografía la
actualización es incremental: el modelo recibe lo ya registrado y solo las
frases nuevas, y devuelve solo lo que cambia (ver
`extraction.extraer_cambios_ecografia`), así que tarda alrededor de un segundo.
Esa vista es provisional: al detener se hace una última extracción completa
con el modelo principal.

Sin dependencias de Streamlit: el hilo no toca session_state, solo esta clase.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from lib import extraction
from lib.config import usar_mock
from lib.ecografias import PLANTILLAS, aplicar_cambios, componer, es_ecografia, estado_vacio
from lib.fuentes import vincular
from lib.hablantes import mapping_inicial

#: Frases ya registradas que acompañan a las nuevas, para entender referencias
#: («la otra mide lo mismo») y correcciones.
CONTEXTO_FRASES = 3

#: Modelo de las extracciones intermedias: llega antes, aunque el final lo da MODELO.
MODELO_EN_VIVO = "claude-haiku-4-5-20251001"

#: Términos que se dictan en cada formato: orientan a la transcripción en tiempo
#: real, que sin ellos confunde palabras técnicas («Ecco verafía»).
_GENERALES = ["paciente", "años", "milímetros", "centímetros", "conclusión", "normal", "doctor"]
_TERMINOS = {
    "abdomen": ["ecografía", "hígado", "vesícula biliar", "colédoco", "vena porta", "bazo", "páncreas",
                "riñón derecho", "riñón izquierdo", "vejiga", "parénquima", "ecogenicidad", "litiasis",
                "sombra acústica", "hidronefrosis", "líquido libre", "esteatosis", "hepatomegalia"],
    "mama": ["ecografía", "mama derecha", "mama izquierda", "parénquima", "ecoestructura", "galactóforos",
             "BI-RADS", "axila", "adenopatías", "nódulo", "hipoecoico", "cuadrante superoexterno",
             "cuadrante inferointerno", "Doppler", "fibroadenoma", "quiste"],
    "transvaginal": ["ecografía transvaginal", "útero", "anteversoflexión", "retroversoflexión", "miometrio",
                     "endometrio", "ovario derecho", "ovario izquierdo", "folículos", "fondo de saco de Douglas",
                     "mioma", "quiste", "anexos"],
    "vesicoprostatica": ["ecografía vésico-prostática", "vejiga", "próstata", "pre miccional", "post miccional",
                         "residuo post miccional", "volumen prostático", "riñón", "calcificaciones", "litiasis"],
    "vias_urinarias": ["ecografía de vías urinarias", "riñón derecho", "riñón izquierdo", "vejiga", "uréter",
                       "parénquima", "diferenciación córtico medular", "hidronefrosis", "litiasis", "pielocalicial"],
}
_CONSULTA = ["presión arterial", "frecuencia cardiaca", "saturación", "temperatura", "alergia", "antecedentes",
             "diagnóstico", "miligramos", "cada ocho horas", "tableta", "hemograma", "control"]


def palabras_clave(formato: str) -> list[str]:
    """Términos para orientar la transcripción en tiempo real del formato dado."""
    if not es_ecografia(formato):
        return _GENERALES + _CONSULTA
    titulos = [s.titulo.lower() for s in PLANTILLAS[formato].secciones if s.titulo]
    return list(dict.fromkeys(_TERMINOS.get(formato, []) + titulos + _GENERALES))


def _log(texto: str) -> None:
    """Registro en la consola del servidor, para seguir una grabación en vivo."""
    print(f"[en vivo {time.strftime('%H:%M:%S')}] {texto}", flush=True)


class SesionEnVivo:
    """Una grabación en curso: las frases transcritas y el último informe.

    Un hilo re-extrae el informe cada vez que llega una frase. Si llegan más
    mientras extrae, al terminar hace una sola extracción con todo lo acumulado.
    """

    def __init__(self, id: str, formato: str, modo: str, conocidos: tuple[list[str], list[str]]) -> None:
        self.id = id
        self.formato, self.modo, self.conocidos = formato, modo, conocidos
        self._lock = threading.Lock()
        self._turnos: dict[int, dict[str, Any]] = {}  # seq -> intervención
        self._hay_nuevo = threading.Event()
        self._extrayendo_lock = threading.Lock()
        self._cerrada = False
        self._terminando = False  # tras detener ya no se hacen extracciones en vivo

        # Lo que muestra la vista en vivo.
        self.historia: dict[str, Any] | None = None
        self.fuentes: dict[str, dict[str, Any]] = {}
        self.mapping: dict[str, str] = {}
        self.formato_extraido: str | None = None
        self.n_extraidas = 0
        self.actualizado: float | None = None  # time.time() de la última extracción
        self.extrayendo = False
        self.error: str | None = None
        # Actualización incremental (ecografía): lo registrado y de qué frases sale.
        self._estado = estado_vacio()
        self._fuentes: dict[str, set[int]] = {}  # ruta -> números [n] (desde 1)

        threading.Thread(target=self._bucle, daemon=True, name="en-vivo-extrae").start()

    # ---------------------------------------------------------------- entrada
    def configurar(self, formato: str, modo: str, conocidos: tuple[list[str], list[str]]) -> None:
        """Toma lo elegido en pantalla; si cambia el formato, el informe se rehace."""
        with self._lock:
            cambio = formato != self.formato
            self.formato, self.modo, self.conocidos = formato, modo, conocidos
        if cambio:
            self._hay_nuevo.set()

    def agregar_turnos(self, turnos: list[dict[str, Any]], extraer: bool = True) -> None:
        """Frases terminadas `{seq, texto, inicio, fin}`; las repetidas se ignoran.

        El navegador manda cada vez todas las que lleva, por si Streamlit se
        saltó algún mensaje. Con `extraer=False` (al detener) no se lanza una
        extracción en vivo: viene enseguida la final.
        """
        nuevos = 0
        with self._lock:
            if self._cerrada:
                return
            voz = self.conocidos[0][0] if self.conocidos[0] else "A"
            for t in turnos:
                seq = int(t["seq"])
                if seq in self._turnos:
                    continue
                self._turnos[seq] = {
                    "speaker": voz,
                    "text": str(t.get("texto") or "").strip(),
                    "start": float(t.get("inicio") or 0.0),
                    "end": float(t.get("fin") or 0.0),
                }
                nuevos += 1
            total = len(self._turnos)
        if nuevos:
            _log(f"{self.id[:8]} {nuevos} frase(s) nueva(s) · {total} en total")
            if extraer:
                self._hay_nuevo.set()

    # ----------------------------------------------------------------- estado
    def utterances(self) -> list[dict[str, Any]]:
        """Las frases consecutivas desde la primera, sin las vacías.

        Si una frase llega antes que la anterior, se espera a esa: así los
        números [n] de las intervenciones no cambian entre extracciones.
        """
        with self._lock:
            salida: list[dict[str, Any]] = []
            seq = 0
            while seq in self._turnos:
                if self._turnos[seq]["text"]:
                    salida.append(dict(self._turnos[seq]))
                seq += 1
            return salida

    def _al_dia(self) -> bool:
        return len(self.utterances()) == self.n_extraidas and self.formato == self.formato_extraido

    # ------------------------------------------------------------- extracción
    def _extraer(self, modelo: str | None) -> None:
        utterances = self.utterances()
        with self._lock:
            formato, modo, nombres = self.formato, self.modo, self.conocidos[0]
        if not utterances:
            return
        mapping = mapping_inicial(
            utterances, modo, nombres, interlocutor="Asistente" if es_ecografia(formato) else "Paciente"
        )
        t0 = time.monotonic()
        historia, fuentes = extraction.extraer(utterances, mapping, formato, modelo=modelo)
        _log(f"{self.id[:8]} informe con {len(utterances)} intervenciones en {time.monotonic() - t0:.1f} s"
             f" ({modelo or extraction.MODELO})")
        with self._lock:
            self.historia, self.fuentes, self.mapping = historia, fuentes, mapping
            self.formato_extraido, self.n_extraidas = formato, len(utterances)
            self.actualizado = time.time()

    def _actualizar(self) -> None:
        """Pone el informe en vivo al día con las frases nuevas."""
        if es_ecografia(self.formato) and not usar_mock():
            self._actualizar_incremental()
        else:
            self._extraer(MODELO_EN_VIVO)

    def _actualizar_incremental(self) -> None:
        utterances = self.utterances()
        with self._lock:
            formato, modo, nombres = self.formato, self.modo, self.conocidos[0]
        if formato != self.formato_extraido:  # formato nuevo: se registra todo de cero
            self._estado, self._fuentes, self.n_extraidas = estado_vacio(), {}, 0
        desde = self.n_extraidas
        nuevas = utterances[desde:]
        if not nuevas:
            return
        mapping = mapping_inicial(utterances, modo, nombres, interlocutor="Asistente")
        # Con una sola frase nueva, ella es la fuente de todo lo que cambie: no hace
        # falta pedirle al modelo que la cite (menos texto que generar).
        con_fuentes = len(nuevas) > 1
        t0 = time.monotonic()
        cambios, citadas = extraction.extraer_cambios_ecografia(
            formato, self._estado, utterances[max(0, desde - CONTEXTO_FRASES):desde], nuevas, mapping, desde,
            modelo=MODELO_EN_VIVO, con_fuentes=con_fuentes, conclusion_propuesta=False,
        )
        estado, tocadas = aplicar_cambios(formato, self._estado, cambios)
        numeros_nuevas = set(range(desde + 1, len(utterances) + 1))
        for f in citadas:
            ids = {n for n in f.get("fragmentos") or [] if isinstance(n, int) and 1 <= n <= len(utterances)}
            if ids:
                self._fuentes.setdefault(str(f.get("campo", "")), set()).update(ids)
        for ruta in tocadas:
            if not con_fuentes or not any(f.get("campo") == ruta for f in citadas):
                self._fuentes.setdefault(ruta, set()).update(numeros_nuevas)
        informe = componer(formato, estado)
        fuentes = vincular(
            informe, [{"campo": c, "fragmentos": sorted(ids)} for c, ids in self._fuentes.items()], len(utterances)
        )
        _log(f"{self.id[:8]} informe +{len(nuevas)} frase(s) en {time.monotonic() - t0:.1f} s (incremental) · "
             f"{len(tocadas)} dato(s)")
        with self._lock:
            self._estado = estado
            self.historia, self.fuentes, self.mapping = informe, fuentes, mapping
            self.formato_extraido, self.n_extraidas = formato, len(utterances)
            self.actualizado = time.time()

    def _bucle(self) -> None:
        while True:
            self._hay_nuevo.wait()
            self._hay_nuevo.clear()
            if self._cerrada:
                return
            if self._terminando or self._al_dia():
                continue
            with self._extrayendo_lock:
                if self._cerrada:
                    return
                if self._terminando:
                    continue
                self.extrayendo = True
                try:
                    self._actualizar()
                except Exception as exc:  # la vista en vivo sigue con el informe anterior
                    _log(f"{self.id[:8]} extracción FALLÓ: {type(exc).__name__}: {exc}")
                    self.error = f"No se pudo actualizar el informe: {type(exc).__name__}: {exc}"
                finally:
                    self.extrayendo = False

    # ------------------------------------------------------------------ cierre
    def terminar(self, total: int, extraer_final: bool = True) -> dict[str, Any] | None:
        """Deja el resultado definitivo.

        Args:
            total: frases que cerró el navegador; si falta alguna (no se
                transcribió o se perdió), devuelve None y hay que procesar el
                audio completo.
            extraer_final: hace la última extracción con el modelo principal.

        Returns:
            {"transcription", "mapping", "historia", "fuentes"} o None.
        """
        with self._lock:
            self._terminando = True
            completas = all(s in self._turnos for s in range(total))
        _log(f"{self.id[:8]} fin · {total} frases cerradas · completas: {completas}")
        if not completas:
            self.cerrar()
            return None
        utterances = self.utterances()
        if extraer_final and utterances:
            with self._extrayendo_lock:  # espera a la extracción en vivo que esté en curso
                self._extraer(None)
        self.cerrar()
        return {
            "transcription": {
                "transcript_completo": " ".join(u["text"] for u in utterances),
                "utterances": utterances,
            },
            "mapping": self.mapping,
            "historia": self.historia,
            "fuentes": self.fuentes,
        }

    def cerrar(self) -> None:
        """Detiene el hilo de extracción."""
        with self._lock:
            self._cerrada = True
        self._hay_nuevo.set()
