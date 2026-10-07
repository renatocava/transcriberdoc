# MedScribe AI — demo

Demo de transcripción y resumen automático de consultas médicas.
El doctor graba la consulta, el sistema la transcribe diferenciando hablantes,
extrae la información clínica en un formulario estructurado y permite revisarla,
editarla y "guardarla" en la historia clínica.

- **Transcripción + diarización:** OpenAI `gpt-4o-transcribe-diarize`
- **Extracción estructurada:** Anthropic `claude-sonnet-4-6` con tool use
- **Informes de ecografía:** cinco plantillas .docx; el informe se descarga en Word
  con el mismo formato (`python-docx`). Cada `___` de una plantilla es un espacio
  con nombre (`bazo.longitud`, `vesicula.pared`): Claude devuelve solo los valores
  dictados y, si un párrafo es distinto de lo normal, ese párrafo reescrito; la app
  arma el texto fijo (`lib/ecografias.py`, `componer`)
- **UI:** Streamlit
- **Persistencia:** ninguna. Todo vive en memoria; "Guardar" solo confirma en
  pantalla e imprime el JSON final en la consola.

## Instalación local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # y completa las API keys
streamlit run app.py
```

Requiere Python 3.11+ (3.10 también funciona en local).

## Secrets

`.streamlit/secrets.toml` (está en `.gitignore`, nunca se sube al repo):

```toml
OPENAI_API_KEY = "sk-..."
ANTHROPIC_API_KEY = "sk-ant-..."
USE_MOCK = false
```

Con `USE_MOCK = true` la app corre con una consulta simulada, sin llamar a
ninguna API: sirve para probar la interfaz, ensayar la demo o presentar sin
internet. El badge del encabezado muestra `DEMO · SIMULADO` cuando está activo.
También se puede activar con la variable de entorno `USE_MOCK=true`.

## Uso en la demo

1. **Grabar** — antes de empezar, elige el **Médico que realiza el estudio** (un
   médico con voz registrada u *Otro*, escribiendo su nombre; va en la línea MÉDICO
   del informe) y el **Formato de salida** (por defecto, ecografía de abdomen
   completo). Las elecciones se recuerdan entre consultas. Los participantes no se
   eligen: la ecografía se toma como dictado del médico y, en la consulta, las
   voces se detectan solas al procesar el audio. Luego
   "Iniciar grabación" / "Detener grabación".

   **En vivo:** mientras se graba, el navegador transcribe en tiempo real con
   `gpt-live-transcribe` (OpenAI) y las palabras aparecen bajo el botón mientras
   se dicen, con ~1 s de retraso. Se conecta directo a OpenAI con una clave
   temporal que genera el servidor (vale 10 min y solo abre sesiones de
   transcripción): la API key nunca llega al navegador. Cada formato le pasa sus
   términos técnicos como palabras clave. En cada pausa de la voz la frase se
   cierra y el informe se actualiza a la derecha con un modelo rápido
   (`claude-haiku-4-5`). En ecografía la actualización es incremental: Haiku recibe
   lo ya registrado y solo las frases nuevas, y devuelve solo lo que cambia (1–2 s
   por frase). Un dato ya registrado queda fijo: solo cambia si el médico dice
   *modificar* (o corregir, cambiar), por ejemplo «modificar colédoco cinco». Si una
   pausa corta una medida («cuatro punto» … «cinco»), el trozo se une a la frase
   anterior. La historia clínica se vuelve a llenar entera. Al detener una
   ecografía, el modelo principal revisa todo el dictado y solo completa lo que
   falte (la conclusión propuesta, alguna medida no registrada) sin cambiar lo ya
   registrado, y se pasa directo a revisar (unos 11 s). En la consulta, o si faltó
   alguna frase, se transcribe el audio completo con diarización para separar las voces.
   Con `USE_MOCK` el texto en vivo se simula.

   **Voces de médicos:** en el expander del mismo nombre se graba (o sube en WAV)
   una muestra de 5–10 s de cada médico, con su consentimiento. La diarización lo
   reconoce y sus intervenciones aparecen como "Doctor (Dr. Hurtado)", con el rol
   asignado solo. Las muestras se guardan en `voces/` (fuera de git; la voz es un
   dato biométrico). En Streamlit Cloud el disco se borra al reiniciar, así que
   allí las voces no persisten.
2. **Procesar** — 15-40 s para una consulta de 2-3 minutos (unos 11 s en dictado, porque ya se transcribió en vivo).
3. **Revisar** — se muestra solo el informe (o la historia clínica), ya lleno y
   editable. Bajo el título, la sección plegable **🎧 Transcripción y audio**
   tiene el audio completo, los roles de las voces y la transcripción, para
   consultarlos solo cuando hagan falta.
   - **Roles:** cada voz detectada tiene su rol (Doctor, Paciente, Acompañante,
     Otro). Si el sistema confundió quién es quién, corrígelo y confirma para
     re-extraer (ojo: se pierden las ediciones manuales). Si las voces no cuadran
     con el modo elegido, aparece un aviso.
   - **Fuentes:** cada dato lleva un 📎. Al pasar el mouse muestra la cita textual
     y el minuto; al hacer clic abre una ventana con la cita y solo ese trozo de
     audio, y la resalta en la transcripción. ✏️ marca datos editados a mano y ⚠️ los
     que no tienen respaldo en la transcripción. Cada intervención indica qué
     datos salieron de ella, y su ▶ abre la misma ventana para escucharla.
     En modo simulado los minutos son aproximados (no salen del audio real).
   - **CIE-10:** Claude propone un código por diagnóstico y hasta 3 alternativas;
     la app solo acepta los que existen y están vigentes en el catálogo oficial
     del MINSA (ver abajo). Si propuso uno inexistente o dado de baja, se
     descarta con un aviso. El médico confirma o cambia el código con el buscador
     (por código o por palabras) junto a cada diagnóstico.
4. **Guardar** — pantalla de confirmación y "Nueva consulta" para volver a empezar.

**Plan B si falla el micrófono de la clínica:** en la pantalla inicial, expander
"Opciones de demo" → "Usar audio pre-grabado" (lee `assets/demo-consulta.mp3`).
El mismo expander permite subir cualquier archivo de audio. El flujo posterior
es idéntico al de una grabación en vivo.

## Informes de ecografía

En la pantalla inicial, **Formato de salida** elige entre la historia clínica de
una consulta y cinco informes de ecografía, uno por plantilla de
`plantillas/ecografia/`:

| Formato | Plantilla | Secciones |
|---|---|---|
| Abdomen completo | `ECO ABDOMEN COMPLETO NORMAL.docx` | hígado, vesícula, colédoco, porta, bazo, páncreas, riñones, vejiga, genitales, Douglas, cavidad |
| Mamas | `ECO MAMA NORMAL.docx` | mama derecha e izquierda |
| Transvaginal | `ECO TV NORMAL.docx` | útero, cérvix, endometrio, ovarios, Douglas |
| Vésico-prostática | `ECO VESICO PROSTATICO NORMAL.docx` | próstata, vejiga, volúmenes pre/post miccional y RPM |
| Vías urinarias | `ECO VIAS URINARIAS NORMAL.docx` | riñones (con cortical), próstata, vejiga, volúmenes |

El médico dicta (o conversa con su asistente) lo que ve en el monitor. Cada
sección parte del **texto normal de la plantilla**: Claude pone las medidas
dictadas en los `___` y reescribe solo lo que difiere de lo normal. Lo que no se
dicta queda como `___`; Claude no calcula volúmenes ni porcentajes. En la revisión:

- cada órgano dice si quedó **normal**, **con hallazgos** o **no se mencionó**
  (texto normal sin respaldo en el dictado), con su 📎 como en la historia clínica;
- la app **sugiere** el volumen prostático (L×AP×T×0,52) y el RPM (post/pre), y
  avisa si no cuadran con lo escrito, pero nunca los escribe sola;
- antes de descargar avisa qué secciones aún tienen medidas `___`;
- "⬇️ Descargar informe (.docx)" genera el Word **sobre la plantilla original**:
  conserva membrete, pie, márgenes y viñetas; llena nombres, edad, médico
  (PARTICULAR si no se dicta), examen y fecha, y reescribe cuerpo y conclusión.

Con un formato de ecografía, la segunda voz se asigna como **Asistente** (el
transcriptor), no como paciente. Si se grabó con el formato equivocado, se puede
cambiar en la revisión y se vuelve a extraer.

Los textos normales viven en `lib/ecografias.py`. Si cambia una plantilla, hay
que actualizar ahí el texto de la sección correspondiente.

## Audio de respaldo

`assets/demo-consulta.mp3` (2:23) es una consulta sintetizada con dos voces
distintas de [piper](https://github.com/OHF-Voice/piper1-gpl): un médico y una
paciente con faringoamigdalitis. Se genera a partir del **mismo** diálogo que usa
el modo simulado, así que la demo muestra lo mismo con el audio pre-grabado que
con `USE_MOCK = true`.

Para regenerarlo (o para producir otra consulta editando `_DIALOGO` en
`lib/mock_data.py`):

```bash
python scripts/generar_audio_demo.py
```

Requiere `ffmpeg` y `piper` con dos voces en `~/.local/share/piper-voices`:
`es_MX-ald-medium` (doctor) y `es_MX-claude-high` (paciente), descargables de
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).

## Catálogo CIE-10

`data/cie10.sqlite` (1,9 MB) es el catálogo CIE-10 **oficial del MINSA**: el Excel
`CIE10_MINSA_OFICIAL.xlsx` (hoja "VOLUMEN VIGENTE") enlazado desde
[REUNIS](https://www.minsa.gob.pe/reunis/?op=3&niv=1). Trae 15 037 códigos
vigentes, incluidas las extensiones peruanas de 5–6 caracteres del HIS, y ya
incorpora la RM 447-2024-MINSA (los 361 códigos del Anexo 1 están; los 20 del
Anexo 2 se guardan con `vigente = 0`). La procedencia, con la huella sha256 del
Excel, queda guardada en la tabla `meta`.

```python
from lib import cie10
cie10.buscar("amigdalitis aguda")   # por palabras, sin importar tildes
cie10.buscar("J03")                 # por código o prefijo
cie10.obtener("J03.9")              # {'codigo': 'J03.9', 'descripcion': ..., 'vigente': True}
cie10.es_valido("I84.9")            # False: cese de uso por la RM 447-2024
```

```bash
sqlite3 data/cie10.sqlite "SELECT c.codigo, c.descripcion FROM codigos_fts f
  JOIN codigos c ON c.id = f.rowid WHERE codigos_fts MATCH 'neumonia* bacteriana*'"
```

Para regenerarlo cuando el MINSA publique una versión nueva (descárgalo a mano
desde REUNIS; el servidor bloquea descargas automáticas):

```bash
python scripts/construir_cie10.py CIE10_MINSA_OFICIAL.xlsx --anexo1 "ANEXO 01.pdf"
```

El script no genera nada si algo no cuadra (capítulos, duplicados, líneas sin
interpretar, códigos cesados presentes).

## Pruebas sin interfaz

```bash
python smoke_test.py                    # todo simulado, sin APIs
python smoke_test.py --real             # extracción real con Claude
python smoke_test.py --real audio.mp3   # transcripción + extracción reales
```

## Despliegue en Streamlit Community Cloud

1. Sube el repo a GitHub. Verifica que `.streamlit/secrets.toml` **no** esté
   incluido (ya está en `.gitignore`); sí deben ir `config.toml` y
   `secrets.toml.example`.
2. Entra a [share.streamlit.io](https://share.streamlit.io) y conecta el repo.
3. Main file path: `app.py`. En **Advanced settings** elige Python 3.11 y pega
   en **Secrets** el contenido de tu `secrets.toml` local.
4. Deploy. Queda una URL pública tipo `https://medscribe-demo.streamlit.app`.

> El navegador solo entrega el micrófono en contextos seguros: la URL de
> Streamlit Cloud es HTTPS y funciona. En local usa `localhost` (también cuenta
> como contexto seguro), no la IP de red.

## Estructura

```
app.py                  router por estado + encabezado
lib/schema.py           modelos Pydantic y JSON Schema para el tool de Claude
lib/transcription.py    wrapper de OpenAI (diarización -> utterances A/B)
lib/extraction.py       wrapper de Anthropic (tool use forzado)
lib/state.py            máquina de estados y helpers de session_state
lib/config.py           secrets y flag de modo simulado
lib/mock_data.py        consulta y dictados de ecografía para el modo simulado
lib/ecografias.py       formatos de ecografía: secciones y texto normal de cada plantilla
lib/informe_docx.py     informe ecográfico en Word sobre la plantilla original
plantillas/ecografia/   las cinco plantillas .docx
components/recording.py pantalla idle (micrófono, audio pre-grabado, upload)
components/processing.py loader con st.status y manejo de errores
components/review.py    transcripción + formulario editable
components/informe_eco.py revisión del informe ecográfico y descarga en Word
```

### Notas de implementación

- **Estados:** `idle → processing → review → saved`, en
  `st.session_state["stage"]`. Solo hay `st.rerun()` al cambiar de estado, al
  re-extraer y al guardar/descartar; editar el formulario nunca fuerza un rerun
  ni vuelve a llamar a las APIs.
- **Ids estables en las listas:** cada diagnóstico y medicamento lleva un `_uid`
  interno, y las keys de los widgets se derivan de él, no del índice. Sin eso,
  borrar un ítem del medio haría que el siguiente heredara sus valores. El
  `_uid` se elimina del JSON al guardar.
- **JSON Schema:** los `$ref`/`$defs` que genera Pydantic se aplanan antes de
  mandarlos como `input_schema` del tool.
