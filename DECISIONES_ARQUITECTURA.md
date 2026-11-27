# Decisiones iniciales de arquitectura

Estado: decisiones de arranque para el prototipo del hackathon. Se pueden revisar antes de congelar las interfaces, pero los cinco módulos deben compartirlas mientras tanto.

## Decisiones cerradas para desbloquear trabajo

1. **Aplicación:** monolito modular en Python. FastAPI expone vistas y API en el mismo proceso; Jinja2 sirve una interfaz HTML ligera con JavaScript sin framework.
2. **Ejecución:** local en una laptop, sin llamadas a servicios remotos durante la demo. Whisper/Ollama/Piper y los recursos geográficos se preparan antes de desconectar internet.
3. **Persistencia:** SQLite con `sqlite3` de la biblioteca estándar. Eventos, indicadores, campañas y corridas de escenarios se guardan localmente. Los escenarios fuente permanecen como JSON en `data/scenarios/`.
4. **Datos:** todo dato de producto es sintético. Los textos entrantes de llamada/SMS/reporte son entradas transitorias; la base común no guarda texto crudo ni datos personales.
5. **Contrato común:** modelos Pydantic en `app/core/schemas.py`; fechas en ISO 8601 con zona horaria; identificadores legibles como `E01`; confianza `low|medium|high`; estado `new|indicative|corroborated|unverified|dismissed`. No existe estado de “fraude confirmado” automático.
6. **Escenarios:** un JSON por escenario, con `id`, `channel`, `trap_id`, `input` y `expected`. El runner ejecuta el manejador registrado por canal y compara recursivamente las claves de `expected` con `actual`; se permiten claves adicionales en `actual`.
7. **Atribución:** se resuelve por el identificador/número trampa receptor y devuelve la copia sembrada. El número de origen no determina la copia.
8. **Integración de módulos:** cada integrante entrega funciones de servicio importables y, cuando necesite endpoints, un router FastAPI propio. La app principal incluye routers; nadie más edita `app/main.py` ni `app/core/schemas.py` sin coordinar el cambio.
9. **Corridas:** `POST /api/scenarios/{id}/run` ejecuta la definición desde disco; `POST /api/scenarios/run-all` ejecuta el catálogo y `GET /api/scenarios/results` devuelve resultados guardados. La entrada y el resultado esperado no se aceptan del navegador.
10. **Inicio de demo:** `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`. `GET /api/health` confirma que la app y SQLite iniciaron.
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

## Brechas que bloqueaban empezar y resolución

- El directorio `Proyecto` solo tenía el README y planes: no había proyecto Python, dependencias, punto de entrada, almacenamiento ni contratos ejecutables. Se crea ahora el esqueleto mínimo.
- `input` y `expected` de escenario estaban descritos como campos sin tipo ni regla de comparación. Se fijan como JSON y comparación recursiva por subconjunto.
- No estaba decidido qué podía persistirse. La base común almacena metadatos e indicadores enmascarados; no texto entrante original.
- No había dueño del punto de entrada ni límite de edición. Integrante 1 es responsable de plataforma; los módulos se registran mediante routers y manejadores.

## Pendientes que requieren confirmación del equipo

1. ¿Todos pueden ejecutar `uv` y Python 3.11 o posterior en la laptop asignada?
2. ¿La laptop de demo tiene micrófono y los modelos locales ya descargados? Si no, dejar lista la ruta textual hasta confirmar.
3. ¿Quién compartirá el GeoJSON local de los 18 municipios y los 14 JSON de escenario esperados?
4. Acordar si cada módulo se integrará mediante ramas o un checkout compartido. No editar en paralelo `app/main.py`, `app/core/schemas.py` ni `app/core/db.py`; Integrante 1 mantiene esos archivos.

