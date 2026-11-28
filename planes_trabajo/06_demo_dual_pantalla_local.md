# Plan 6 — Plataforma ciudadana y consola privada de Gobierno

**Estado:** alcance actualizado el 28 de noviembre de 2026
**Prioridad:** cierre de integración y preparación de demo
**Modalidad:** ejecución local, datos sintéticos, sin servicios externos

## Objetivo y alcance vigente

La plataforma tiene dos secciones con límites de acceso distintos:

- **Ciudadanía — pública:** orientación preventiva, análisis de SMS sospechosos, recepción de reportes saneados y resultados agregados aprobados.
- **Gobierno — privada:** simulación de llamadas por escenarios precargados, dashboard en vivo, historial de reportes, métricas, atribución, campañas y evidencia sintética.

La simulación de llamada vive exclusivamente en Gobierno. Un escenario recorre una llamada entrante, su contestación y la conversación completa. El sistema genera las voces de quien llama y de Doña Lupita; la transcripción aparece en el simulador y en el dashboard. No se permite enviar mensajes libres al personaje ni se depende del micrófono. El operador puede rechazar la llamada entrante o cancelar la sesión activa.

Todo número, cuenta, persona, ubicación, llamada, mensaje y atribución de la demostración es ficticio. No se originan llamadas/SMS reales ni se envían reportes a terceros. El reporte institucional es una salida de demostración y debe quedar rotulado como tal.

## Estado actual frente al alcance

| Área | Estado | Evidencia o brecha |
|---|---|---|
| Sección pública | Implementada | Portada, portal ciudadano, análisis SMS y avisos/mapa agregados. Los datos personales se saneen antes de guardar. |
| Sección privada | Implementada | Gobierno usa credenciales locales; simulator, escenarios, dashboard e historial de reportes están dentro del área protegida. |
| Simulación de llamada | Implementada | Escenarios de voz precargados ejecutan ambos parlamentos con voz del navegador. Hay controles para contestar, rechazar y cancelar. No se usa telefonía real, micrófono ni mensajes libres. |
| Transcripción en vivo | Implementada | Los turnos saneados se publican al simulador y al dashboard por eventos locales/SSE. La sesión y el bus de eventos dependen de memoria. |
| Inteligencia y atribución | Implementada | Siembra sintética, atribución por receptor, extracción/validación de indicadores, campañas, confianza y cadena de hashes. |
| Historial y métricas | Implementado | La sección de reportes gubernamentales consulta registros guardados y presenta métricas/gráficas. La persistencia no conserva el estado completo de la sesión de voz para reconstruirla después de reiniciar. |
| SMS y portal | Implementados | Análisis con fixtures, reglas de clasificación, dominios y reportes ciudadanos saneados. No hay recepción real de SMS. |
| Contenedorización | Implementada | Dockerfile y Compose con almacenamiento persistente local; imagen construida y configuración revisada en la iteración de contenedorización. |
| Ensayo y evidencia de demo | Pendiente de verificación | Falta registrar un recorrido integral de dos pantallas, latencia observada y resultados medidos de los escenarios; no se debe inventar una tasa de éxito. |
| Artefactos de presentación | Pendiente | Preparar diapositivas, guion de pitch y video de respaldo de la demo, si aún no existen fuera del repositorio. |

La revisión anterior de este plan proponía el simulador en Ciudadanía, micrófono/texto libre, un QR de sesión móvil y rutas de polling aún inexistentes. Esos puntos quedan **obsoletos** frente al alcance vigente. La arquitectura de dos secciones se conserva, pero tanto la simulación como sus resultados son privados de Gobierno.

## Límites de acceso y datos

| Sección | Permitido | Excluido |
|---|---|---|
| **Ciudadanía — pública** | Orientación, análisis de mensajes sospechosos, reporte saneado, avisos generales y agregados con umbral aplicado en backend. | Simulador, transcripción de llamadas trampa, `trap_id`, copia/proveedor atribuidos, datos de origen, campaña interna, hashes y expedientes gubernamentales. |
| **Gobierno — privada** | Ejecutar escenarios, ver transcripción saneada en vivo, atribución, indicadores enmascarados, campañas, dashboard, historial y reportes de demostración. | PII ciudadana en claro, audio crudo, llamadas reales, identificación real de personas y transmisión a autoridades. |

- Mantener autenticación del lado del servidor en las vistas y APIs de Gobierno; validar también las rutas antiguas que puedan exponer información interna.
- Las respuestas públicas usan campos permitidos explícitamente y agregación/supresión aplicada en backend.
- Las llamadas y conversaciones usan únicamente el guion sintético del escenario seleccionado. No introducir datos de jurados o usuarios reales.
- El reporte debe advertir: **“SIMULADO — sin validez oficial”**. No añadir controles para enviar el reporte a una autoridad, banco u operadora.
- En la demo de dos dispositivos, ambos abren la sección privada con las credenciales locales. No se requiere QR público ni token ciudadano para operar la llamada.

## Recorrido de demostración

1. En la laptop, el operador inicia la aplicación local y abre `/gobierno`.
2. En el simulador privado `/gobierno/simulador`, selecciona un escenario sintético y pulsa iniciar.
3. La interfaz muestra llamada entrante, identidad ficticia y controles de contestar/rechazar. Al contestar, reproduce por turnos las voces del atacante y de Doña Lupita.
4. El simulador y el dashboard gubernamental muestran la misma transcripción saneada, junto con indicadores enmascarados, estado/confianza, atribución por número receptor y referencias de evidencia disponibles.
5. El operador puede cancelar la llamada durante la conversación. El sistema la marca como terminada y libera la sesión para iniciar otro escenario.
6. El operador consulta el evento en reportes guardados y métricas. El reporte es sintético y no se envía a terceros.
7. Desde la sección pública se demuestra por separado el análisis de un SMS de ejemplo y/o el reporte ciudadano saneado, sin exponer información de las llamadas trampa.

## Siguiente implementación

### Prioridad 0 — Cerrar la demo repetible

| Trabajo | Resultado revisable |
|---|---|
| Verificar permisos de Gobierno en vistas y APIs, incluida la lectura de atribución, voz, inteligencia, dashboard y reportes. Corregir cualquier endpoint interno que siga abierto. | Matriz de rutas privadas comprobada sin sesión y con credenciales. |
| Recorrer contestar, rechazar, cancelar durante la conversación, terminar y volver a iniciar. Revisar también el error al fallar un turno del escenario. | La sesión siempre queda cerrada y no aparece un conflicto 409 al repetir la demo. |
| Ejecutar el catálogo de escenarios y conservar resultados esperados/obtenidos. Confirmar que todos los IDs E01–E14 están cargados, aunque compartan archivos JSON. | Resumen reproducible de cobertura y resultados, sin cifras inventadas. |
| Ensayar la vista en laptop y celular dentro de la LAN, con síntesis de voz disponible y sin micrófono/modelos externos. | Guion cronometrado, controles legibles y plan de respaldo probado. |

### Prioridad 1 — Hacer el historial de llamadas completo

| Trabajo | Resultado revisable |
|---|---|
| Persistir metadatos y turnos ya saneados de la llamada, vinculados a un `session_id`/`event_id`; no guardar audio ni texto crudo. | Una llamada terminada sigue consultable después de recargar o reiniciar el servidor. |
| Hacer que el reporte guardado incluya la cronología, escenario, duración, número trampa ficticio, atribución, indicadores enmascarados, estado/confianza y hashes disponibles. | El detalle del reporte coincide con los eventos mostrados en vivo y está rotulado como simulado. |
| Asegurar estados de finalización coherentes para rechazada, cancelada y completada; liberar cualquier candado de llamada aunque ocurra una excepción. | No quedan sesiones activas huérfanas ni se bloquean ejecuciones siguientes. |

### Prioridad 2 — Métricas, experiencia y entrega

| Trabajo | Resultado revisable |
|---|---|
| Afinar el dashboard histórico para separar llamadas, análisis SMS y reportes ciudadanos; asegurar que los filtros y gráficas indiquen periodo y fuente. | Métricas entendibles y trazables a registros almacenados. |
| Medir la cobertura de atribución, extracción de CLABE y clasificación SMS con los escenarios sintéticos. | Indicadores calculados desde las ejecuciones; no estimaciones. |
| Preparar pitch de tres minutos y grabar video local de respaldo. | Demo ensayada y reproducible si el equipo falla el día del evento. |

## Criterios de aceptación

- Ciudadanía puede usar orientación, análisis SMS y reporte saneado sin acceder a dashboards ni a resultados de llamadas trampa.
- Gobierno exige autenticación tanto para las páginas privadas como para sus APIs.
- Un escenario seleccionado recorre llamada entrante, contestación y conversación completa con dos voces generadas localmente.
- La misma transcripción saneada se ve en el simulador y en el dashboard privado mientras avanza el escenario.
- Rechazar una llamada evita iniciar la conversación; cancelar una llamada activa termina la sesión y permite comenzar otra.
- Los escenarios funcionan sin micrófono, Whisper, Ollama, telefonía ni servicios remotos.
- Al terminar, queda un reporte privado persistido, consistente con los eventos de la sesión y rotulado **“SIMULADO — sin validez oficial”**.
- Los valores usados son sintéticos; no se guardan audio ni PII en claro y no hay envío a autoridades o terceros.
- Las métricas de demo provienen de escenarios ejecutados y se acompañan de sus resultados esperados/obtenidos.
- La demo local puede iniciarse mediante Docker Compose y conserva las bases de datos en el volumen configurado.

## Fuera de alcance

Telefonía real, números reales, recepción real de SMS, integración con operadoras, grabación de audio de terceros, uso de datos personales reales, identificación real de responsables, envío de reportes a autoridades/empresas, despliegue público y afirmaciones de cadena de custodia legal.
