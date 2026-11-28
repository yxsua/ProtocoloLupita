# Plan 1 — Plataforma, integración y escenarios

**Responsable:** Integrante 1 · **Duración:** 18 horas · **Rol:** plataforma e integración

## Objetivo

Entregar la aplicación local con dos secciones: **Ciudadanía pública** para orientación y reportes saneados, y **Gobierno privada** para los dashboards detallados de llamadas trampa, atribución y evidencia. La demo tendrá dos dispositivos coordinados: simulador desde la sección ciudadana en el celular y dashboard autenticado en la laptop. El expediente final será sintético. No habrá llamadas, mensajes ni reportes enviados a terceros reales.

## Arquitectura acordada

- Monolito modular en Python con FastAPI; interfaz HTML/CSS/JavaScript sencilla.
- SQLite para persistencia local. JSON para escenarios y datos de muestra. Sin dependencias de servicios remotos durante la demo.
- Para el uso desde celular, el servidor se podrá enlazar a la interfaz de red local y anunciar una URL/QR de sesión; el acceso queda limitado a la LAN de demostración. Evitar exponer información real.
- La pantalla móvil y el monitor compartirán un `session_id` local. El monitor consultará el estado/eventos de la sesión (polling como primera opción) y conservará el resultado tras colgar.
- La conexión de audio desde navegador móvil depende de permisos y contexto seguro. El guion/texto debe completar el recorrido sin micrófono ni modelos; audio grabado o voz del navegador puede servir como alternativa.
- El reporte institucional se genera como artefacto local imprimible/descargable, claramente sintético; no incluye función para enviarlo a autoridades.
- Separar rutas públicas (`/ciudadania`, `/api/public/*`) y privadas (`/gobierno`, `/api/gobierno/*`). Toda ruta privada requiere autenticación y autorización comprobadas en backend; la sección ciudadana solo recibe DTOs públicos con allowlist y agregación segura.
- Para la demo, implementar un rol de gobierno local y una sesión de servidor; no es un sistema de identidad real. El QR del celular contiene un token de corta duración que solo habilita la sesión telefónica asignada.
- Cada integrante es dueño de su módulo y de sus archivos; se integra mediante los contratos de este documento, no editando el módulo de otra persona.
- Todos los datos y números del prototipo son sintéticos y se muestran como tales.
- Los modelos locales y archivos del mapa deben estar disponibles antes de desconectar internet.

## Contratos comunes — congelar en la primera hora

Publicar `app/core/schemas.py` y compartirlos con el equipo antes de que cada quien avance:

- `Scenario`: `id`, `channel` (`call|sms|portal`), `trap_id`, `input`, `expected`.
- `Event`: `id`, `occurred_at`, `channel`, `trap_id`, `attribution_id`, `indicator_ids`, `campaign_id`, `confidence`, `status`, `evidence_hash`.
- `Indicator`: `id`, `type`, `value_masked`, `source_event_id`, `confidence`, `status`.
- `AttributionResult`: `trap_id`, `copy_id`, `provider`, `seed_period`, `synthetic`.
- `ScenarioResult`: `scenario_id`, `passed`, `expected`, `actual`, `duration_ms`.

Interfaces internas estables: `attribute(trap_id)`, `process_call(input)`, `analyze_sms(input)`, `process_event(event)`, `submit_report(input)` y `get_dashboard(filters)`. Se permiten nombres internos distintos si el adaptador conserva estas entradas/salidas. Registrar decisiones o cambios de contrato en un mensaje común antes de implementarlos.

## Archivos bajo responsabilidad

- `app/main.py`, `app/core/schemas.py`, `app/core/db.py`, `app/core/config.py`
- `app/core/scenario_runner.py`, `app/core/seed_data.py`
- `app/templates/base.html`, `app/static/app.css`, `app/static/app.js`
- `data/scenarios/*.json`, consolidando escenarios aportados por los demás
- Integración de routers y dependencias entre módulos; no reescribir su lógica interna.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–1 h | Resolver conflictos pendientes de `app/main.py`; acordar contratos, rutas, audiencia pública/privada y dueño de autenticación; confirmar cómo correr el proyecto. |
| 1–4 h | Crear FastAPI, SQLite, carga de configuración, layout de navegación y datos sintéticos iniciales. |
| 4–7 h | Integrar el límite público/privado y proteger endpoints internos; enlazar sesión de llamada con inteligencia/evidencia y dashboard privado en vivo. |
| 7–9 h | Preparar la URL/QR LAN de alcance limitado, adaptación móvil, estado de conexión y expediente sintético final. |
| 9–12 h | Implementar runner y validar los escenarios que sostienen el recorrido de demo; después completar el resto del catálogo si hay tiempo. |
| 12–15 h | Ejecutar recorrido integrado en dos dispositivos, corregir persistencia, red local, latencia y campos compartidos; habilitar demo sin internet. |
| 15–16 h | Congelar funciones y contratos; respaldar datos/artefactos sintéticos. |
| 16–18 h | Ensayar demo de tres minutos, registrar métricas observadas y grabar video de respaldo. |

## Aceptación

- Un comando inicia la app en laptop sin internet; el celular se conecta a la misma red local y abre el simulador sin números reales.
- El monitor de la laptop recibe los turnos de la llamada y muestra transcripción, atributos ficticios, atribución, indicadores, confianza y evidencia durante la sesión.
- La sección pública permite orientación y reporte ciudadano sin revelar atribución interna; el dashboard de llamadas trampa requiere iniciar sesión como gobierno.
- Consultar directamente APIs privadas sin sesión produce rechazo de autorización; APIs públicas devuelven solo datos aprobados para ciudadanía.
- Al cerrar la llamada se puede consultar y exportar/imprimir el expediente sintético, rotulado como demostración y sin envío a autoridades.
- Se puede navegar por todos los módulos y seguir un evento desde la trampa hasta tablero y ruta ciudadana.
- Los 14 JSON se cargan y el runner registra esperado y obtenido sin inventar porcentajes.
- Los registros de reporte almacenados no incluyen datos personales del formulario original.
- Existe una demo ensayada y un video local reproducible.

## Uso de herramientas de codificación con IA

Delegar cambios por archivo y contrato. Pedir primero un diff pequeño y revisión de imports; no permitir que un agente cambie esquemas congelados sin avisar. Integrar cada módulo cuando entregue una función importable y un ejemplo JSON, no esperar hasta la hora 12.

