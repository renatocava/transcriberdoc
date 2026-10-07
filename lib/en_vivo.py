"""Transcripción e informe en vivo: el informe se llena mientras el médico habla.

El navegador (components/grabador_vivo/) transcribe en tiempo real directo con
OpenAI (`gpt-live-transcribe`), con una clave temporal que da el servidor: las
palabras aparecen en pantalla mientras se dicen y, en cada pausa, la frase
terminada llega aquí como una intervención. Con lo transcrito hasta ese momento
el informe se actualiza en segundo plano con un modelo rápido. En ecografía la
actualización es incremental: el modelo recibe lo ya registrado y solo las
frases nuevas, y devuelve solo lo que cambia (ver
`extraction.extraer_cambios_ecografia`), así que tarda alrededor de un segundo.
Un dato ya registrado queda fijo: solo cambia si el médico dice «modificar»
(o corregir, cambiar). Al detener, el modelo principal revisa todo el dictado
y completa lo que falte, sin cambiar lo que el médico ya vio registrado.

La transcripción corta una frase en cada pausa, y a veces la pausa cae en medio
de una medida («mide cuatro punto» … «cinco»): esos trozos se unen a la frase
anterior antes de extraer (`unir_cortes`).

Sin dependencias de Streamlit: el hilo no toca session_state, solo esta clase.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any

from lib import extraction
from lib.config import usar_mock
from lib.ecografias import PLANTILLAS, aplicar_cambios, componer, es_ecografia, estado_vacio, registrados
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


#: Palabras con que el médico pide cambiar un dato ya registrado.
_MODIFICAR = re.compile(r"\b(modific|corrig|correg|cambi|rectific)\w*", re.I)

_PALABRAS_NUMERO = (
    r"cero|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|"
    r"dieci\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento"
)
#: Una frase que termina a medias («… mide», «… cuatro punto», «… 78 por»).
_CONECTOR_FINAL = re.compile(r"\b(punto|coma|por|x|de|mide|miden|y)[\s.,:;]*$", re.I)
_NUMERO_FINAL = re.compile(rf"(\d|\b({_PALABRAS_NUMERO}))[\s.,:;]*$", re.I)
#: Una frase que sigue el número de la anterior («5 milímetros», «cinco», «por 32»).
_SIGUE_NUMERO = re.compile(
    rf"^\s*(\d|(?:{_PALABRAS_NUMERO}|punto|coma|por|x|mm|milímetros?|centímetros?|cc)\b)", re.I
)
#: Pausa máxima entre dos trozos de una misma frase.
PAUSA_CORTE_S = 3.0


def continua(anterior: dict[str, Any], siguiente: dict[str, Any]) -> bool:
    """True si `siguiente` es el resto de `anterior`, cortada por una pausa."""
    if float(siguiente.get("start") or 0) - float(anterior.get("end") or 0) > PAUSA_CORTE_S:
        return False
    a, b = anterior["text"], siguiente["text"]
    return bool(_CONECTOR_FINAL.search(a) or (_NUMERO_FINAL.search(a) and _SIGUE_NUMERO.match(b)))


def unir_cortes(utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Las frases con los trozos cortados por una pausa unidos a la anterior."""
    salida: list[dict[str, Any]] = []
    for u in utterances:
        if salida and continua(salida[-1], u):
            salida[-1] = {**salida[-1], "text": f"{salida[-1]['text'].rstrip()} {u['text'].lstrip()}", "end": u["end"]}
        else:
            salida.append(dict(u))
    return salida


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
        self._textos: list[str] = []  # las frases tal como se extrajeron
        self.actualizado: float | None = None  # time.time() de la última extracción
        self.extrayendo = False
        self.error: str | None = None
        # Actualización incremental (ecografía): lo registrado y de qué frases sale.
        self._estado = estado_vacio()
        self._fuentes: dict[str, set[int]] = {}  # ruta -> números [n] (desde 1)
        self._origen: dict[str, int] = {}  # clave de `registrados` -> frase (desde 0) que lo dio

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
        """Las frases consecutivas desde la primera, sin las vacías y con los
        trozos cortados por una pausa unidos (`unir_cortes`).

        Si una frase llega antes que la anterior, se espera a esa: así los
        números [n] de las intervenciones no cambian entre extracciones (solo
        la última puede crecer con un trozo).
        """
        with self._lock:
            salida: list[dict[str, Any]] = []
            seq = 0
            while seq in self._turnos:
                if self._turnos[seq]["text"]:
                    salida.append(dict(self._turnos[seq]))
                seq += 1
        return unir_cortes(salida)

    def _al_dia(self) -> bool:
        return [u["text"] for u in self.utterances()] == self._textos and self.formato == self.formato_extraido

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
            self._textos = [u["text"] for u in utterances]
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
            self._estado, self._fuentes, self._origen, self._textos = estado_vacio(), {}, {}, []
        textos = [u["text"] for u in utterances]
        # Desde la primera frase distinta de lo ya registrado: una nueva, o la
        # última si se le unió un trozo («mide 4.» + «5 milímetros»).
        desde = next(
            (i for i, (a, b) in enumerate(zip(textos, self._textos)) if a != b), min(len(textos), len(self._textos))
        )
        nuevas = utterances[desde:]
        if not nuevas:
            return
        mapping = mapping_inicial(utterances, modo, nombres, interlocutor="Asistente")
        # Lo registrado por frases anteriores queda fijo, salvo que se pida modificarlo.
        modificar = any(_MODIFICAR.search(u["text"]) for u in nuevas)
        fijos = set() if modificar else {k for k, i in self._origen.items() if i < desde}
        # Con una sola frase nueva, ella es la fuente de todo lo que cambie: no hace
        # falta pedirle al modelo que la cite (menos texto que generar).
        con_fuentes = len(nuevas) > 1
        t0 = time.monotonic()
        cambios, citadas = extraction.extraer_cambios_ecografia(
            formato, self._estado, utterances[max(0, desde - CONTEXTO_FRASES):desde], nuevas, mapping, desde,
            modelo=MODELO_EN_VIVO, con_fuentes=con_fuentes, conclusion_propuesta=False,
        )
        tocadas, ignorados = self._registrar(
            formato, utterances, mapping, cambios, citadas, fijos, set(range(desde + 1, len(utterances) + 1))
        )
        _log(f"{self.id[:8]} informe +{len(nuevas)} frase(s) en {time.monotonic() - t0:.1f} s (incremental) · "
             f"{len(tocadas)} dato(s)" + (" · modificar" if modificar else "")
             + (f" · sin cambiar (no se dijo «modificar»): {', '.join(ignorados)}" if ignorados else ""))

    def _registrar(
        self,
        formato: str,
        utterances: list[dict[str, Any]],
        mapping: dict[str, str],
        cambios: dict[str, Any],
        citadas: list[dict[str, Any]],
        fijos: set[str],
        sin_cita: set[int],
    ) -> tuple[list[str], list[str]]:
        """Aplica los cambios al informe en vivo. `sin_cita`: números [n] que
        son la fuente de lo que el modelo cambió sin citar de dónde.

        Returns:
            (rutas que tocó, datos fijos que el modelo intentó cambiar).
        """
        ignorados: list[str] = []
        antes = registrados(self._estado)
        estado, tocadas = aplicar_cambios(formato, self._estado, cambios, fijos, ignorados)
        ultima = len(utterances) - 1
        self._origen = {
            k: self._origen.get(k, ultima) if v == antes.get(k) else ultima for k, v in registrados(estado).items()
        }
        for f in citadas:
            ids = {n for n in f.get("fragmentos") or [] if isinstance(n, int) and 1 <= n <= len(utterances)}
            if ids:
                self._fuentes.setdefault(str(f.get("campo", "")), set()).update(ids)
        for ruta in tocadas:
            if sin_cita and not any(f.get("campo") == ruta for f in citadas):
                self._fuentes.setdefault(ruta, set()).update(sin_cita)
        informe = componer(formato, estado)
        fuentes = vincular(
            informe, [{"campo": c, "fragmentos": sorted(ids)} for c, ids in self._fuentes.items()], len(utterances)
        )
        with self._lock:
            self._estado = estado
            self.historia, self.fuentes, self.mapping = informe, fuentes, mapping
            self.formato_extraido, self.n_extraidas = formato, len(utterances)
            self._textos = [u["text"] for u in utterances]
            self.actualizado = time.time()
        return tocadas, ignorados

    def _completar_ecografia(self) -> None:
        """Al detener: pone al día lo registrado en vivo y el modelo principal
        revisa todo el dictado. Lo registrado no cambia (el médico ya lo vio y lo
        habría modificado); la revisión solo llena lo que falta, como una medida
        que no se registró o la conclusión propuesta."""
        if not self._al_dia():
            self._actualizar_incremental()
        utterances = self.utterances()
        with self._lock:
            formato, modo, nombres = self.formato, self.modo, self.conocidos[0]
        mapping = mapping_inicial(utterances, modo, nombres, interlocutor="Asistente")
        t0 = time.monotonic()
        cambios, citadas = extraction.extraer_cambios_ecografia(formato, estado_vacio(), [], utterances, mapping, 0)
        tocadas, ignorados = self._registrar(
            formato, utterances, mapping, cambios, citadas, set(registrados(self._estado)), set()
        )
        _log(f"{self.id[:8]} revisión final en {time.monotonic() - t0:.1f} s ({extraction.MODELO}) · "
             f"{len(tocadas)} parte(s) revisadas" + (f" · se mantuvo lo registrado: {', '.join(ignorados)}" if ignorados else ""))

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
                if es_ecografia(self.formato) and not usar_mock():
                    self._completar_ecografia()
                    utterances = self.utterances()
                else:
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
