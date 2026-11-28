# Decisiones iniciales de arquitectura

Estado: decisiones de arranque para el prototipo del hackathon. Se pueden revisar antes de congelar las interfaces, pero los cinco módulos deben compartirlas mientras tanto.

## Decisiones cerradas para desbloquear trabajo

1. **Aplicación:** monolito modular en Python. FastAPI expone vistas y API en el mismo proceso; Jinja2 sirve una interfaz HTML ligera con JavaScript sin framework.
2. **Ejecución:** local en una laptop, sin llamadas a servicios remotos durante la demo. La llamada de demostración se simula; no se marca ni envía mensaje a ningún número real. Whisper/Ollama/Piper son opcionales y cualquier recurso necesario se prepara antes de desconectar internet.
3. **Persistencia:** SQLite con `sqlite3` de la biblioteca estándar. Eventos, indicadores, campañas y corridas de escenarios se guardan localmente. Los escenarios fuente permanecen como JSON en `data/scenarios/`.
4. **Datos:** todo dato de producto es sintético. Los textos entrantes de llamada/SMS/reporte son entradas transitorias; la base común no guarda texto crudo ni datos personales.
5. **Contrato común:** modelos Pydantic en `app/core/schemas.py`; fechas en ISO 8601 con zona horaria; identificadores legibles como `E01`; confianza `low|medium|high`; estado `new|indicative|corroborated|unverified|dismissed`. No existe estado de “fraude confirmado” automático.
6. **Escenarios:** un JSON por escenario, con `id`, `channel`, `trap_id`, `input` y `expected`. El runner ejecuta el manejador registrado por canal y compara recursivamente las claves de `expected` con `actual`; se permiten claves adicionales en `actual`.
7. **Atribución:** se resuelve por el identificador/número trampa receptor y devuelve la copia sembrada. El número de origen no determina la copia.
8. **Integración de módulos:** cada integrante entrega funciones de servicio importables y, cuando necesite endpoints, un router FastAPI propio. La app principal incluye routers; nadie más edita `app/main.py` ni `app/core/schemas.py` sin coordinar el cambio.
9. **Corridas:** `POST /api/scenarios/{id}/run` ejecuta la definición desde disco; `POST /api/scenarios/run-all` ejecuta el catálogo y `GET /api/scenarios/results` devuelve resultados guardados. La entrada y el resultado esperado no se aceptan del navegador.
10. **Inicio de demo:** en modo local de un solo dispositivo: `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`. Para el demo de dos dispositivos, enlazar temporalmente a la interfaz LAN (`--host 0.0.0.0`) y mostrar una URL/QR con la IP local; no publicar el servidor en internet. `GET /api/health` confirma que la app y SQLite iniciaron.
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

## Alcance acordado para la siguiente demo

- La plataforma se separa en **Ciudadanía pública** (`/ciudadania`, APIs `/api/public/*`) y **Gobierno privada** (`/gobierno`, APIs `/api/gobierno/*`). Ciudadanía recibe orientación, reporte saneado y agregados que cumplan el umbral; Gobierno ve dashboards detallados de llamadas trampa, atribución, eventos y evidencia.
- Proteger rutas y APIs privadas en el servidor con sesión autenticada y rol autorizado. La ocultación de enlaces en HTML no es control de acceso. La demo usa una cuenta local simulada, claramente marcada como tal, sin representar identidad gubernamental real.
- Las APIs públicas usan esquemas de respuesta separados con allowlist: nunca devuelven mapeo copia↔trampa, `copy_id`, proveedor/dataset, transcripciones de trampas, IDs internos o evidencia privada. Aplicar supresión de grupos pequeños del lado servidor.
- El simulador móvil es una ruta pública de demostración con token aleatorio, revocable y limitado a una llamada; no entrega permisos de gobierno. Cada llamada sigue siendo ficticia.
- Al migrar, proteger o retirar endpoints internos antiguos (`/dashboard`, `/planting`, `/api/planting/*`, `/api/intel/*` y similares) antes de enlazar la app a la LAN.
- La pantalla `/voice/` representa una llamada ficticia operada desde el celular; un monitor separado muestra el análisis en vivo en la laptop. Los dos clientes comparten un `session_id`.
- Priorizar polling local de una lectura de sesión cada 1–2 segundos. Solo cambiar a SSE/WebSocket si el volumen o la latencia medida lo exige.
- La sesión conserva metadatos sintéticos (origen, trampa receptora, fechas/duración, escenario de filtración y datos observados) y eventos saneados después de colgar, para alimentar el expediente de demostración.
- Transcripciones y audio crudos no se incorporan a la cadena de evidencia. El contenido guardado debe limitarse a texto saneado, indicadores enmascarados/hash y metadatos de la llamada. Todos los teléfonos, cuentas, entidades y ubicaciones son sintéticos.
- El expediente se genera localmente para imprimir/descargar, lleva la leyenda “SIMULADO — sin validez oficial” y no ofrece envío a autoridades.
- La entrada de micrófono desde IP local puede no estar disponible en el navegador por la política de contexto seguro. El flujo de guion/texto debe poder demostrar el sistema completo; audio pregrabado o TTS del navegador son alternativas locales.

La app actual no tiene autenticación ni autorización registradas y `app/main.py` contiene marcadores de conflicto Git. Resolver el arranque y establecer el límite de acceso son prerrequisitos para exponer la demo en la LAN.

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

