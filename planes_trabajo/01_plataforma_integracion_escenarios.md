# Plan 1 — Plataforma, integración y escenarios

**Responsable:** Integrante 1 · **Duración:** 18 horas · **Rol:** plataforma e integración

## Objetivo

Entregar la aplicación que conecta los módulos y permite demostrar los 14 escenarios, además de una llamada desde un celular al número de prueba. La demo incluye dos superficies separadas: la experiencia ciudadana existente y un panel gubernamental protegido que muestra la llamada, su atribución y alertas en tiempo real. La consola gubernamental ejecuta escenarios cerrados y no permite interacción libre.

## Arquitectura acordada

- Monolito modular en Python con FastAPI; interfaz HTML/CSS/JavaScript sencilla.
- El prototipo y el runner pueden ejecutarse localmente; la llamada móvil requiere servidor públicamente accesible, TLS y conexión a un proveedor telefónico.
- Mantener vistas y APIs ciudadanas separadas de rutas gubernamentales protegidas. El panel gubernamental incluye una vista en vivo y un ejecutor de escenarios predefinidos.
- Limitar la demo telefónica a una llamada simultánea. El número llamado resuelve perfil, copia sembrada, fuente y periodo; el número de origen se etiqueta como no verificado.
- Emitir actualizaciones del panel en vivo mediante SSE. Guardar resultados de escenarios y mantener llamadas en el bus temporal con origen distinguible; no mezclar sus métricas.
- El envío de reportes a autoridades se presenta como borrador de demostración y no se automatiza.
- Cada integrante es dueño de su módulo y de sus archivos; se integra mediante los contratos de este documento, no editando el módulo de otra persona.
- Los fixtures, identidades, cuentas y atribuciones de demostración son sintéticos y se muestran como tales. El piloto usa un número de prueba real y recibe metadatos del proveedor; el identificador del llamante se rotula como no verificado y se enmascara.
- Los modelos locales y archivos del mapa deben estar disponibles antes de desconectar internet.

## Contratos comunes — congelar en la primera hora

Publicar `app/core/schemas.py` y compartirlos con el equipo antes de que cada quien avance:

- `Scenario`: `id`, `channel` (`call|sms|portal`), `trap_id`, `input`, `expected`.
- `CallInput`: origen (`telephony|scenario`), número receptor/trap, perfil de agente y sesión del proveedor o escenario; los adaptadores entregan turnos o audio al mismo servicio de voz.
- `Event`: `id`, `occurred_at`, `channel`, `trap_id`, `attribution_id`, `indicator_ids`, `campaign_id`, `confidence`, `status`, `evidence_hash`.
- `Indicator`: `id`, `type`, `value_masked`, `source_event_id`, `confidence`, `status`.
- `AttributionResult`: `trap_id`, `copy_id`, `provider`, `seed_period`, `synthetic`.
- `ScenarioResult`: `scenario_id`, `passed`, `expected`, `actual`, `duration_ms`.

Interfaces internas estables: `attribute(trap_id)`, `process_call(input)`, `analyze_sms(input)`, `process_event(event)`, `submit_report(input)` y `get_dashboard(filters)`. Se permiten nombres internos distintos si el adaptador conserva estas entradas/salidas. Registrar decisiones o cambios de contrato en un mensaje común antes de implementarlos.

## Archivos bajo responsabilidad

- `app/main.py`, `app/core/schemas.py`, `app/core/db.py`, `app/core/config.py`
- `app/core/scenario_runner.py`, `app/core/seed_data.py`
- `app/templates/base.html`, `app/static/app.css`, `app/static/app.js`
- Vistas y endpoints gubernamentales protegidos; SSE para enviar eventos de llamada a la pantalla de resultados.
- Adaptador de llamada del proveedor y control de una sesión telefónica activa.
- `data/scenarios/*.json`, consolidando escenarios aportados por los demás
- Integración de routers y dependencias entre módulos; no reescribir su lógica interna.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–2 h | Congelar contratos de evento, origen de llamada y acceso al panel; verificar que número, proveedor, credenciales y servidor público estén disponibles. |
| 2–5 h | Separar rutas ciudadanas/gubernamentales, proteger el panel y añadir la vista de consola de escenarios cerrados. |
| 3–9 h | En paralelo con Plan 3, conectar webhook HTTPS del proveedor con reconocimiento Gather, asociar número receptor con trampa y habilitar el límite de una llamada activa. |
| 8–12 h | Conectar eventos del agente, atribución, inteligencia y borrador de reporte; entregar actualizaciones del panel por SSE. |
| 12–15 h | Recorrer llamada móvil y escenarios JSON; verificar que el panel rotule y filtre ambos orígenes por separado. |
| 15–16 h | Congelar funciones y preparar respaldo de demostración si falla el proveedor o la red. |
| 16–18 h | Ensayar la llamada desde un celular, la lectura del panel en otra pantalla y el guion de presentación. |

## Aceptación

- Un celular llama al número de prueba y el agente responde desde el servidor público.
- El panel gubernamental protegido muestra en vivo el estado, intención, indicadores enmascarados y atribución a la copia/fuente sembrada.
- Una segunda llamada mientras la primera está activa recibe el mensaje de ocupado o cierre definido.
- La consola ejecuta escenarios cerrados por el mismo orquestador, sin entrada libre ni interacción conversacional.
- El panel diferencia la llamada móvil de las simulaciones y marca como simulados los datos y reportes de demo.
- La experiencia ciudadana no expone datos ni controles internos del panel gubernamental.
- Se puede navegar por todos los módulos y seguir un evento desde la trampa hasta tablero y ruta ciudadana.
- Los 14 JSON se cargan y el runner registra esperado y obtenido sin inventar porcentajes.
- Los registros de reporte almacenados no incluyen datos personales del formulario original.
- Existe una demo ensayada desde un celular y un video de respaldo reproducible.

## Fuera de esta integración inicial

Más números, llamadas simultáneas, alta disponibilidad, envío automático a instituciones y un sistema de telefonía de producción. Se documentan como paso posterior, no como recortes del flujo de demo.

## Uso de herramientas de codificación con IA

Delegar cambios por archivo y contrato. Pedir primero un diff pequeño y revisión de imports; no permitir que un agente cambie esquemas congelados sin avisar. Integrar cada módulo cuando entregue una función importable y un ejemplo JSON, no esperar hasta la hora 12.
