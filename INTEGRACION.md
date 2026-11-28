# Integración del prototipo

## Qué quedó integrado

La aplicación funciona como un monolito FastAPI local. `app/main.py` monta los routers de siembra y atribución, voz, inteligencia, SMS, reportes ciudadanos, mapa y tablero; además publica la página inicial, salud, ejecución de escenarios y resultados.

## Integración inicial: llamada móvil y panel gubernamental

La llamada móvil y el panel gubernamental están implementados como una primera integración con Twilio. Un celular llama al DID de prueba conectado a Twilio; el servidor público atiende mediante webhooks HTTPS y limita el piloto a una llamada activa. La vista ciudadana sigue separada del panel gubernamental protegido.

El piloto usa `<Gather input="speech">`: Twilio recibe la voz telefónica, realiza reconocimiento de voz en su servicio y envía al servidor el texto reconocido junto con la confianza disponible. No se transmite el audio a Whisper ni se guarda audio de la llamada. Esta decisión evita introducir streaming WSS en el piloto; cambiar a transcripción propia en servidor requiere una integración de Media Streams y WSS como siguiente etapa. El proveedor procesa el audio y el texto reconocido fuera del servidor del prototipo, por lo que la demo debe usar únicamente entradas sintéticas y datos de prueba.

El panel gubernamental, en `/gobierno`, muestra el estado de llamada, turnos reconocidos, intención, indicadores enmascarados y atribución determinada por el DID receptor. El identificador del número llamante se presenta como no verificado. Los escenarios E01–E08 se ejecutan en una consola protegida separada (`/gobierno/escenarios`), y sus eventos se marcan como simulación. Los eventos se mantienen en memoria; no se mezclan con la llamada móvil ni sobreviven al reinicio.

El motor de respuestas sigue siendo el servicio de voz existente. Los saludos y frases disponibles se reproducen desde clips; el contenido dinámico usa Piper si se configura un modelo, y usa la voz de Twilio como respaldo. Para una voz mexicana más natural, configurar un modelo de voz en español mexicano en `PIPER_MODEL_PATH` y escucharlo antes de la demo. Los eventos del servidor actualizan la interfaz con SSE. El reporte se descarga como borrador de demostración; no se envía a una autoridad.

### Configuración de la demo telefónica

Para publicar el prototipo en Ubuntu sobre EC2 con Caddy y HTTPS, sigue [DESPLIEGUE_EC2_UBUNTU.md](DESPLIEGUE_EC2_UBUNTU.md).

1. Crear una cuenta/número Twilio de prueba, copiar `.env.example` a `.env` y completar sus valores. Cargarlo al arrancar con `--env-file .env`; no guardar secretos en el repositorio.
2. Publicar la aplicación bajo una URL HTTPS estable en `PUBLIC_BASE_URL`; los webhooks validan `X-Twilio-Signature` usando esa URL pública.
3. En la configuración de voz del DID, usar `POST https://<host>/api/telephony/voice`. Configurar el webhook de estado en `POST https://<host>/api/telephony/status` para liberar sesiones si la llamada termina inesperadamente.
4. Definir `TWILIO_TEST_TRAP_ID` como una trampa sembrada; la semilla del piloto Doña Lupita es `+52 442 000 0102`. El número que recibe la llamada debe coincidir con `TWILIO_TEST_NUMBER`.
5. Configurar `GOV_PANEL_USERNAME` y `GOV_PANEL_PASSWORD`, iniciar un solo proceso de Uvicorn con `--env-file .env` y abrir `/gobierno` con esas credenciales.

Este piloto requiere un único proceso/worker: el límite de llamadas y el bus SSE son en memoria. Al reiniciar, desaparecen los eventos; para alta disponibilidad o varias réplicas, mover estado y eventos a almacenamiento/pubsub compartido. WSS, más números y llamadas simultáneas quedan para una etapa posterior.

Los escenarios se normalizan desde los distintos formatos de fixtures aportados por los planes. El runner adapta los casos a los servicios reales y evalúa un subconjunto recursivo de la respuesta, por lo que un módulo puede añadir campos sin romper el contrato de prueba.

## Experiencia pública

La propuesta inicial contempla siete capacidades internas y cuatro recorridos para demostrar valor. La navegación pública ahora prioriza lo que una persona necesita hacer: **revisar un mensaje, reportar una llamada o mensaje, consultar avisos** y, como demostración opcional, conocer la conversación de Doña Lupita. La siembra, la atribución y las comprobaciones técnicas siguen en los servicios del prototipo, fuera del camino principal.

Las pantallas públicas comparten navegación, palabras cotidianas y el mismo sistema visual. La información se presenta como señales y consejos, sin exponer elementos internos del sistema. Las pantallas de SMS y reporte recogen solo lo necesario para orientar; los resultados dicen qué señal se encontró y qué puede hacer la persona. Los avisos aclaran que son parte de una demostración y no son cifras oficiales.

La interfaz usa texto grande, botones amplios, foco visible, etiquetas asociadas a los campos, mensajes anunciados por lectores de pantalla, navegación por teclado y un diseño que se adapta a teléfono. Los estados se expresan con palabras y no dependen solo del color.

## Contratos y decisiones de integración

- **Voz:** el escenario envía cada texto como un turno de la llamada; el saludo inicial no se cuenta como respuesta a un turno del fixture. La duración cero simula el timeout de E08.
- **SMS:** la respuesta del módulo se proyecta al contrato del escenario con enlaces desactivados, detección de suplantación/acortadores, señales de reglas y existencia de campaña.
- **Inteligencia:** cada ejecución usa un motor nuevo para aislar escenarios. E12 precarga E01 para probar corroboración independiente; E14 valida el estado de no verificación.
- **Portal ciudadano:** cada escenario usa almacenamiento y limitador aislados. El reporte se sanitiza antes de guardar y enviar al motor.
- **Mapa:** los municipios por debajo del umbral se suprimen por nombre y solo se publica su cantidad. Por eso E13 comprueba `hidden_municipalities_count`, acorde al contrato del adaptador y a la privacidad del agregado.
- **Importación:** los paquetes SMS y ciudadano exportan dependencias de manera diferida para evitar el ciclo de imports que aparecía al cargar servicios directamente.
- **Dependencias:** `faker`, `python-multipart`, `twilio` y `python-dotenv` son dependencias de ejecución; `pytest` y `httpx` están en el grupo de desarrollo. `uv.lock` conserva la resolución del entorno.

## Catálogo de escenario

| Casos | Área | Cobertura principal |
| --- | --- | --- |
| E01–E08 | Llamada / voz | CLABE válida e inválida, urgencia, despedida, prompt injection, timeout y permanencia en personaje |
| E09–E11 | SMS | Suplantación de dominio, acortadores, enlaces desactivados y texto hostil incrustado |
| E12 | Reporte ciudadano / inteligencia | Saneamiento de PII y corroboración con E01 |
| E13 | Mapa | Umbral municipal de cinco reportes y supresión de agregados pequeños |
| E14 | Reporte ciudadano / tablero | Limitador de tasa y estado sin verificar |

## Ejecutar y verificar

```powershell
uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run pytest -q
```

También se puede revisar el catálogo en `GET /api/scenarios`, ejecutar uno con `POST /api/scenarios/{id}/run` o ejecutar los catorce con `POST /api/scenarios/run-all`. Los resultados se consultan con `GET /api/scenarios/results` y se guardan en SQLite local.

La verificación ejecutó los catorce escenarios: **14/14 aprobados**. La suite completa pasó con **102 pruebas aprobadas**. Quedaron advertencias de deprecación de Starlette/Pydantic y `datetime.utcnow()`; no afectan el resultado actual.

## Datos locales

Los fixtures de `data/scenarios/` son sintéticos. La base SQLite y el manifiesto de siembra generado localmente están excluidos de Git. Las URLs de ejemplo se analizan como texto y los enlaces se desactivan; no se visitan.


