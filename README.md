# MedScribe AI — demo

Demo de transcripción y resumen automático de consultas médicas.
El doctor graba la consulta, el sistema la transcribe diferenciando hablantes,
extrae la información clínica en un formulario estructurado y permite revisarla,
editarla y "guardarla" en la historia clínica.

- **Transcripción + diarización:** OpenAI `gpt-4o-transcribe-diarize`
- **Extracción estructurada:** Anthropic `claude-sonnet-4-6` con tool use
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

1. **Grabar** — botón "Iniciar grabación" / "Detener grabación". Al detener,
   arranca el procesamiento automáticamente.
2. **Procesar** — 15-40 s para una consulta de 2-3 minutos.
3. **Revisar** — transcripción a la izquierda, historia clínica editable a la
   derecha. Arriba de la transcripción queda un reproductor con el audio de la
   consulta, para escuchar lo que se grabó mientras se revisa el formulario. Si el sistema confundió quién es quién, cambia "Speaker A es:" y
   confirma para re-extraer (ojo: se pierden las ediciones manuales).
4. **Guardar** — pantalla de confirmación y "Nueva consulta" para volver a empezar.

**Plan B si falla el micrófono de la clínica:** en la pantalla inicial, expander
"Opciones de demo" → "Usar audio pre-grabado" (lee `assets/demo-consulta.mp3`).
El mismo expander permite subir cualquier archivo de audio. El flujo posterior
es idéntico al de una grabación en vivo.

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
lib/mock_data.py        consulta de ejemplo para el modo simulado
components/recording.py pantalla idle (micrófono, audio pre-grabado, upload)
components/processing.py loader con st.status y manejo de errores
components/review.py    transcripción + formulario editable
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
