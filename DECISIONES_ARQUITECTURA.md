# Decisiones iniciales de arquitectura

Estado: decisiones de arranque para el prototipo y decisiones aplicadas a la integración inicial con llamada móvil y panel gubernamental.

## Decisiones cerradas para desbloquear trabajo

1. **Aplicación:** monolito modular en Python. FastAPI expone vistas y API en el mismo proceso; Jinja2 sirve una interfaz HTML ligera con JavaScript sin framework.
2. **Ejecución base:** la aplicación y los escenarios actuales corren localmente. **Demo con llamada móvil:** requiere un servidor público con HTTPS y un proveedor telefónico para el número de prueba; el procesamiento de voz puede seguir en el servidor y no requiere enviar audio a un modelo externo.
3. **Persistencia:** SQLite con `sqlite3` de la biblioteca estándar para los datos existentes de inteligencia, indicadores, campañas y corridas de escenarios. Los eventos de la llamada del piloto permanecen solo en memoria. Los escenarios fuente permanecen como JSON en `data/scenarios/`.
4. **Datos:** los fixtures y los datos de atribución de demo son sintéticos. La llamada al número de prueba y sus metadatos del proveedor sí son reales; el identificador del llamante se considera no verificado y no se conserva sin enmascarar. Twilio procesa audio de la llamada para reconocimiento; el servidor recibe texto y no almacena audio ni transcripción completa en disco. El texto se conserva enmascarado solo en el bus de eventos en memoria.
5. **Contrato común:** modelos Pydantic en `app/core/schemas.py`; fechas en ISO 8601 con zona horaria; identificadores legibles como `E01`; confianza `low|medium|high`; estado `new|indicative|corroborated|unverified|dismissed`. No existe estado de “fraude confirmado” automático.
6. **Escenarios:** un JSON por escenario, con `id`, `channel`, `trap_id`, `input` y `expected`. El runner ejecuta el manejador registrado por canal y compara recursivamente las claves de `expected` con `actual`; se permiten claves adicionales en `actual`.
7. **Atribución:** se resuelve por el identificador/número trampa receptor y devuelve la copia sembrada. El número de origen no determina la copia.
8. **Integración de módulos:** cada integrante entrega funciones de servicio importables y, cuando necesite endpoints, un router FastAPI propio. La app principal incluye routers; nadie más edita `app/main.py` ni `app/core/schemas.py` sin coordinar el cambio.
9. **Corridas:** `POST /api/scenarios/{id}/run` ejecuta la definición desde disco; `POST /api/scenarios/run-all` ejecuta el catálogo y `GET /api/scenarios/results` devuelve resultados guardados. La entrada y el resultado esperado no se aceptan del navegador.
10. **Inicio de demo base:** `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`. La demo telefónica requiere despliegue público con TLS y webhook HTTPS configurado con el proveedor.
11. **Integración de equipo:** el proyecto ya tiene Git, rama `yasua` y remoto `origin`. Para trabajar en paralelo, cada integrante conserva propiedad de sus archivos; Integrante 1 integra routers y contratos compartidos varias veces durante la jornada, no solo al final.

## Contratos de servicio

Cada módulo debe adaptar su implementación a estas entradas/salidas comunes:

- Siembra: `attribute(trap_id: str) -> AttributionResult`.
- Voz: `process_call(input: CallInput) -> CallResult`.
- SMS: `analyze_sms(input: SmsInput) -> SmsAnalysis`.
- Inteligencia: `process_event(event: Event) -> EventResult` (contiene el evento, indicadores y campaña actualizada).
- Portal: `submit_report(input: CitizenReportInput) -> CitizenResponse`.
- Tablero: `get_dashboard(filters: DashboardFilters) -> DashboardSnapshot`.
- Escenarios: cada módulo registra un manejador para su canal que recibe `Scenario` y devuelve un objeto JSON serializable con el resultado observable.

## Prefijos de API para evitar colisiones

Cada módulo es dueño de un `APIRouter` y de sus vistas parciales; Integrante 1 los agrega al crear cada integración. Los endpoints de producto deben quedar bajo estos prefijos:

| Módulo | Prefijo |
|---|---|
| Siembra | `/api/planting` |
| Voz | `/api/voice` |
| Inteligencia/evidencia | `/api/intel` |
| SMS | `/api/sms` |
| Portal ciudadano | `/api/citizen` |
| Tablero/mapa | `/api/dashboard` |

El núcleo conserva `/api/health`, `/api/scenarios`, `/api/scenarios/{id}/run`, `/api/scenarios/run-all`, `/api/scenarios/results` y `/api/demo/reset`.

Los manejadores se registran en `app/core/scenario_runner.py` antes de correr escenarios. Los errores se guardan como resultados fallidos con tipo de error; no se persiste el texto de la excepción, porque podría contener entrada sensible. `expected` y `actual` de los JSON/resultados no deben incluir CLABE, CURP, teléfono ni texto crudo.

`Event.attribution_id` contiene el `copy_id` devuelto por siembra. Los valores identificables de indicadores no se guardan: `value_masked` es lo que puede ver el tablero y `value_fingerprint` sirve para correlacionar la misma señal entre eventos. El módulo debe generar ese fingerprint antes de descartar el dato crudo.

Persistencia de una observación: guardar primero el `Event`, después sus `Indicator` (la tabla usa llave foránea) y al final la `Campaign` actualizada.

La ruta de voz acepta audio en el router del módulo; la función `process_call` trabaja sobre una transcripción, para separar navegador/micrófono de la conversación y permitir el modo texto.

## Decisiones abiertas, sin bloquear el esqueleto

- Modelo local y versión de Whisper; modelo y reglas para Ollama; voz Piper y carpeta de assets. Confirmar que los pesos estén descargados y que la laptop tenga recursos suficientes.
- API exacta de grabación de voz en navegador (MediaRecorder y formato que acepte Whisper). Mantener transcripción escrita como fallback.
- Fuente del GeoJSON de municipios; empaquetar un archivo local y evitar mapas de teselas en línea.
- Lista final de entidades/campos particulares de cada módulo. Se añaden en el módulo dueño; el núcleo solo guarda datos normalizados y no contenido crudo.
- Si el equipo requiere un instalador portable además del comando `uv`; decidirlo tras iniciar la app en la laptop de demo.
- Proveedor telefónico, disponibilidad y configuración del número de prueba, URL pública, certificado TLS y validación de firmas de webhook.
- Método de acceso al panel gubernamental y cuenta de demostración; no debe compartir permisos con la vista ciudadana.
- Voz del actor que interpretará al atacante, límites de retención y campos que aparecerán en vivo en el panel.

## Integración inicial: llamada móvil y panel gubernamental

Este alcance complementa el prototipo actual. La demo se realizará desde un celular que llama al número de prueba. Una persona del equipo interpreta al atacante; el sistema contesta con el perfil de agente asociado al número receptor. El servidor admite una llamada simultánea.

- Mantener la experiencia ciudadana existente. Añadir un panel gubernamental en rutas y APIs protegidas, con una vista de resultados en vivo y una consola de escenarios cerrados.
- El proveedor envía la llamada a un adaptador telefónico por webhook HTTPS. Para el piloto, Twilio hace el reconocimiento de voz con Gather y entrega el texto transcrito al servicio de voz; el servidor responde con clips pregrabados o voz dinámica acotada. Usar Media Streams/WSS y reconocimiento propio queda para la siguiente etapa.
- Resolver la atribución por el número receptor: `número de prueba → trampa/copia sembrada → fuente y periodo → perfil de agente`. El identificador de origen se muestra como no verificado y no determina la atribución.
- El panel gubernamental recibe eventos de inicio, turnos reconocidos, intenciones, indicadores, atribución y borrador de reporte. Usar Server-Sent Events (SSE) para actualizar la pantalla; no necesita un canal de control bidireccional.
- La consola ejecuta únicamente escenarios JSON aprobados, sin chat libre. Usa el mismo orquestador y flujo de eventos que la llamada; cada resultado conserva `source_mode` (`telephony` o `scenario`) y `scenario_id` cuando aplique.
- Separar los resultados de escenario de las llamadas del número de prueba. Toda alerta derivada de fixtures y todo reporte de la demo lleva una marca visible de “simulación” o “borrador”; no se envía automáticamente a una autoridad.
- El flujo de llamada transforma audio a texto para procesarlo. No guardar audio completo ni transcripción íntegra por defecto; conservar metadatos mínimos, indicadores enmascarados y evidencia aprobada para la demostración.
- Al alcanzar el límite de una llamada activa, rechazar una segunda llamada con un mensaje breve de ocupado. No agregar cola, balanceador ni escalamiento horizontal en esta etapa.

### Secuencia de demo propuesta

1. Desde el celular, una persona llama al número de prueba e interpreta el guion de atacante.
2. El perfil asignado al número responde con una voz natural y controlada.
3. En el panel gubernamental se observan el estado de llamada, el texto reconocido de forma transitoria, la intención, indicadores enmascarados y la atribución a la copia sembrada.
4. El operador revisa el borrador de reporte, etiquetado como simulación; la autoridad receptora y cualquier envío real quedan fuera de esta demo.
5. Desde la consola se ejecuta un escenario fijo para mostrar un resultado repetible, claramente separado de la llamada móvil.

### Escalamiento posterior

El piloto documenta como siguiente paso habilitar más números y perfiles, varias llamadas concurrentes, almacenamiento compartido de sesiones, workers de voz separados y alta disponibilidad. Ninguno de esos elementos es requisito de la demo de una llamada.

## Brechas que bloqueaban empezar y resolución

- El directorio `Proyecto` solo tenía el README y planes: no había proyecto Python, dependencias, punto de entrada, almacenamiento ni contratos ejecutables. Se crea ahora el esqueleto mínimo.
- `input` y `expected` de escenario estaban descritos como campos sin tipo ni regla de comparación. Se fijan como JSON y comparación recursiva por subconjunto.
- No estaba decidido qué podía persistirse. La base común almacena metadatos e indicadores enmascarados; no texto entrante original.
- No había dueño del punto de entrada ni límite de edición. Integrante 1 es responsable de plataforma; los módulos se registran mediante routers y manejadores.

## Pendientes que requieren confirmación del equipo

1. Confirmar proveedor, número de prueba, webhook, webhook HTTPS público y acceso a credenciales antes de iniciar la integración.
2. Confirmar que el servidor puede cargar los modelos de voz una vez y sostener una llamada; si no, definir un fallback de audio pregrabado.
3. Definir autenticación mínima para el panel gubernamental y el acceso a la consola de escenarios.
4. Acordar qué indicadores y metadatos se muestran en vivo, y el formato del borrador de reporte.
5. Acordar si cada módulo se integrará mediante ramas o un checkout compartido. No editar en paralelo `app/main.py`, `app/core/schemas.py` ni `app/core/db.py`; Integrante 1 mantiene esos archivos.
