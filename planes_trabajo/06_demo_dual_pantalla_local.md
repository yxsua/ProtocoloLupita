# Plan 6 — Plataforma ciudadana y consola privada de gobierno

**Prioridad:** siguiente implementación · **Base:** planes 1, 3 y 4 · **Modalidad:** solo local y datos sintéticos

## Objetivo

Separar la plataforma en dos secciones con permisos y propósitos distintos. La sección pública ofrece orientación y recepción segura de reportes ciudadanos. La sección privada de gobierno concentra los dashboards con resultados de llamadas trampa, atribución, seguimiento y evidencia. La demo muestra la llamada simulada en un celular desde la experiencia pública y los resultados detallados en la consola privada de la laptop. No hay telecomunicaciones reales, datos reales ni envío a autoridades.

## Estado actual frente al objetivo

| Área | Ya existe | Brecha para esta demo |
|---|---|---|
| Simulador de voz | `/voice/`, inicio/proceso/colgar; motor conversacional con intención, extracción de CLABE, respuestas de audio; captura de micrófono en el navegador y modo texto. | El acceso de audio en celular por IP local requiere validar permisos/contexto seguro. Hace falta guion totalmente determinista para que el recorrido no dependa de Whisper/Ollama ni del micrófono. |
| Sesión de llamada | Se crea `session_id` y mantiene un `VoiceService` en memoria. | No hay API de lectura de la sesión para un segundo cliente; al colgar se elimina la sesión. Aún faltan eventos de sesión durables y su vínculo con inteligencia/evidencia. |
| Tablero | `/dashboard` y `/api/dashboard` muestran atribuciones, campañas, mapa y datos de módulos/fixtures. | No es un monitor de turnos en vivo ni está ligado a la llamada abierta. |
| Atribución | Siembra local sintética; atribución estricta por `trap_id` receptor. | Conectar la trampa elegida para la sesión de voz a la consulta y mostrar origen solo como dato secundario no confiable. |
| Inteligencia/evidencia | Hay extracción, campañas, paquetes de autoridad simulados y una cadena de hashes local. | Integrar cada turno saneado de voz, el estado de la llamada y las referencias de evidencia en una vista coherente; el paquete existente no es todavía un expediente descargable de esa llamada. |
| Acceso | El portal ciudadano y las vistas internas están implementados como módulos. | No se encontró modelo de autenticación ni separación de permisos. Rutas como `/dashboard`, `/planting`, `/api/planting/*` y rutas de inteligencia deben protegerse o migrarse antes de mostrarlas por la LAN. |
| Operación | README inicia Uvicorn en `127.0.0.1`, válido para la laptop. | Para el celular hace falta exponer temporalmente el servidor a la LAN, mostrar URL/QR y revisar conectividad/firewall. No exponerlo a internet. |

Hay marcadores de conflicto Git sin resolver en `app/main.py`; resolver e integrar el arranque y los routers es la fase cero, antes de montar permisos o publicar la aplicación en la LAN. La interfaz de micrófono y el motor de conversación ya son una base útil. La prioridad es separación de acceso + sesión compartida + ingestión de eventos + monitor; pulir voz natural viene después.

## Dos secciones y límites de acceso

| Sección | Ruta de entrada propuesta | Contenido permitido | Contenido excluido |
|---|---|---|---|
| **Pública — Ciudadanía** | `/ciudadania` (puede conservar `/citizen` como alias) | Alertas preventivas redactadas, recomendaciones, consulta de mensajes/indicadores en lenguaje claro, reporte ciudadano saneado, mapa y conteos agregados que superen el umbral. Simulador telefónico de la demo en un modo de sesión acotado. | Mapeo trampa↔copia/proveedor, IDs internos de eventos, transcripción detallada de llamadas trampa, origen reportado, hashes de evidencia, expedientes institucionales, gestión de semillas. |
| **Privada — Gobierno** | `/gobierno` | Autenticación local de demo; dashboard de llamadas trampa en vivo e histórico; número trampa receptor, copia/proveedor atribuidos, transcripción saneada, indicadores enmascarados, campañas/confianza, cadena de evidencia y expediente sintético. Herramientas de siembra solo para rol autorizado. | Datos personales ciudadanos en claro, audio crudo, transmisión real a autoridades o llamadas reales. |

- Proteger en el servidor cada vista y endpoint, no solo ocultar enlaces del menú. En prototipo local, usar una cuenta/rol de demo con cookie de sesión y middleware/dependencia de autorización; rotular el acceso como simulado. No dejar dashboards privados accesibles por conocer la URL.
- El reporte ciudadano sigue siendo público y anónimo; sanear antes de persistir. La sesión del simulador en el celular recibe una credencial aleatoria de alcance limitado a esa llamada, sin acceso a endpoints privados ni a otras sesiones.
- Separar la API en `/api/public/*` y `/api/gobierno/*`. Durante la migración, mapear cada endpoint actual y retirar o proteger rutas antiguas abiertas que entreguen atribuciones o paquetes internos.
- Las vistas públicas y sus respuestas API deben usar allowlist de campos. Aplicar el umbral de publicación en backend y comprobar que ningún campo interno pueda filtrarse accidentalmente.

## Experiencia de demostración

1. El funcionario abre la sección privada `/gobierno`, inicia sesión con la cuenta local de demo e inicia una corrida ficticia (proveedor/copia sembrada, número trampa receptor, origen simulado, municipio y guion del atacante). La consola crea un código/URL/QR de participación de un solo uso.
2. El jurado abre en el celular la sección pública, entra al simulador de llamada y ve nombre/identificador ficticio, temporizador, controles de llamada y modo de entrada (guion, texto o audio disponible). La credencial del QR habilita solo esa llamada.
3. El jurado u operador reproduce/dice el guion de atacante. Cada turno se procesa por el servicio existente; Doña Lupita responde con el audio preparado o voz local y el texto de respaldo.
4. En el dashboard privado de la laptop el monitor se actualiza automáticamente: estado y duración, transcripción saneada por turno, datos ficticios observados y enmascarados, número trampa receptor, copia/proveedor atribuidos, confianza, campaña y referencias/hash de evidencia. Debe distinguir “pendiente”, “indicio”, “corroborado” y “sin verificar”. La pantalla pública no recibe esos datos internos.
5. Al terminar se conserva la sesión y se genera un expediente sintético imprimible y descargable (HTML/JSON; PDF vía imprimir del navegador si no requiere dependencia adicional), con cronología, indicadores enmascarados, atribución, hashes y limitaciones. Mostrar siempre “SIMULADO — sin validez oficial”.

## Contrato y diseño técnico propuestos

- Conservar las rutas actuales de voz y agregar lectura de sesión activa/finalizada y expediente, por ejemplo `/voice/sessions/{session_id}` y `/voice/sessions/{session_id}/report`.
- Mantener el payload de sesión tipado y versionable: `session_id`, estado, inicio/fin, duración, canal, `trap_id` receptor, origen ficticio, `scenario_id`, turnos visibles, indicadores enmascarados, atribución, `campaign_id`, confianza y `evidence_refs`.
- Agregar eventos incrementales por turno con `event_id`, `occurred_at`, `speaker`, texto saneado, intención, indicadores y estado de análisis. No guardar audio. Conservar localmente hasta el reinicio de demo solo la transcripción saneada (marcadores para teléfonos/cuentas y datos personales), necesaria para reconstruir el expediente; el botón de reinicio elimina sesiones y eventos de la corrida.
- Para el primer corte, el monitor consulta el endpoint cada 1–2 segundos. El endpoint devuelve el snapshot más reciente y `last_event_id` para actualizar sin duplicados. SSE/WebSocket queda como alternativa si el polling no logra la latencia objetivo.
- Aplicar autorización de gobierno a todas las vistas y APIs privadas mediante una dependencia centralizada. Las APIs ciudadanas exponen solo esquemas públicos dedicados; no serializar directamente `DashboardResponse`, `SeedCopyRecord` o `EventResult`.
- El QR de participación usa un token aleatorio, revocable y de vida limitada; solo autoriza iniciar/continuar la sesión concreta, sin acceso a datos de atribución ni a la API del dashboard.
- No guardar el estado en un diccionario del router como fuente única: persistir eventos y resumen en SQLite/local store existente, conservando recuperación tras recarga y fin de llamada. El motor de voz puede permanecer en memoria mientras está activa.
- Usar `attribute(trap_id)` para resolver copia. No inferir atribución a partir del Caller ID; el número origen va marcado como sintético y no verificado.
- Enviar a `IntelEngine.process_event` únicamente entrada saneada y metadatos sintéticos. Reutilizar cadena de evidencia y `build_authority_package`; adaptar la salida a un artefacto local imprimible/descargable sin añadir transmisión a servicios externos.
- Seguridad de demo: modo LAN se habilita explícitamente; la UI y todo expediente marcan los datos como ficticios. No exponer formularios de texto libre para PII real. Aplicar límite de tamaño/tasa a audio y texto.
- Audio: priorizar micrófono móvil solo después de confirmar soporte de `getUserMedia` desde la IP LAN. Si el navegador lo bloquea, usar guion/texto con reproducción de voz pregrabada/TTS local. Esta alternativa debe mantener intacto el recorrido del monitor.

## Secuencia de implementación

| Fase | Trabajo | Resultado revisable |
|---|---|---|
| 0. Arranque (0.5–1 h) | Resolver conflicto de `app/main.py`; integrar routers y acordar prefijos y dueño de autenticación. | Aplicación inicia con rutas registradas sin conflicto. |
| 1. Secciones y permisos (1–3 h) | Crear entradas `/ciudadania` y `/gobierno`, sesión/rol de demo y dependencias backend; clasificar y proteger rutas existentes. | Ciudadanía ve solo contenido permitido; acceso privado redirige o responde 401/403 sin sesión de gobierno. |
| 2. Contratos y estado (1–3 h) | Definir `CallSession`, `CallTurnEvent`, campos sintéticos, reglas de saneamiento y un fixture de demo único; guardar eventos y conservar sesión al colgar. | Sesión persistida y trazable a E01. |
| 3. Simulador público y LAN (2–4 h) | Adaptar vista móvil, entrada de guion/texto, voz grabada opcional y QR/token de un solo uso ligado a la sesión. | Celular completa llamada ficticia sin poder abrir endpoints privados. |
| 4. Dashboard privado en vivo (2–4 h) | Crear `/gobierno/llamadas/{session_id}`, polling incremental, atribución y análisis con protección de autenticación. | Cada turno aparece en ≤2 s solo en consola autenticada. |
| 5. Inteligencia y expediente (2–4 h) | Conectar evento saneado a intel/evidencia y habilitar descarga/impresión de expediente privado simulado. | Expediente coincide con sesión y muestra referencias verificables. |
| 6. Ensayo y robustez (1–2 h) | Probar permisos, red LAN, reconexión, latencia, fallback sin micrófono/modelos y reinicio de demo. | Guion de jurado repetible y plan B comprobado. |

Las fases 2–5 son el núcleo. El micrófono en vivo, Piper/Whisper y PDF generado por biblioteca son mejoras sujetas al tiempo; el guion, texto, reproducción existente, monitor y expediente local forman la ruta obligatoria.

## Criterios de aceptación

- Una laptop y un celular en la misma LAN completan la demo sin números reales ni acceso a servicios externos.
- La ciudadanía puede abrir orientación y enviar un reporte sin cuenta; las respuestas públicas no incluyen copia/proveedor atribuidos ni datos de las llamadas trampa.
- Un visitante sin sesión no puede abrir vistas privadas ni consultar sus APIs; el rol de gobierno autenticado sí accede al dashboard.
- El operador inicia la llamada en la sección privada y el celular entra por QR/código de alcance limitado; ambas pantallas muestran el mismo ID de demo.
- Una llamada guionizada produce al menos tres turnos de ida y vuelta; el detalle aparece en ≤2 segundos en el dashboard privado y no aparece en la sección pública.
- Se ve con claridad qué número sintético recibió la llamada, qué copia/proveedor se atribuye por ese receptor, qué señales se extrajeron y qué evidencia se generó.
- Al colgar, la sesión continúa consultable y el expediente imprimible/descargable coincide con sus eventos. El documento advierte que es una simulación sin validez oficial.
- El recorrido completo funciona con micrófono/modelos desactivados; no se persiste audio ni PII del jurado/operador.
- Un ciudadano no autenticado no puede obtener detalle de siembra, eventos, transcripciones internas, hashes o paquetes de autoridad consultando directamente las rutas API.
- La atribución y la confianza respetan los contratos existentes y ninguna pantalla etiqueta fraude como confirmado por un indicio aislado.

## Fuera de alcance de esta iteración

Llamadas telefónicas/SMS reales, integración con operadoras, envío a fiscalías/autoridades, identificación real de personas, almacenamiento de audios de terceros, publicación de datos personales y despliegue público. El artefacto es una demostración local de trazabilidad, no un reporte oficial ni una prueba de cadena de custodia legal.

