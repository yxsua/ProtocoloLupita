# Plan 1 — Plataforma, integración y escenarios

**Responsable:** Integrante 1 · **Duración:** 18 horas · **Rol:** plataforma e integración

## Objetivo

Entregar la aplicación local que conecta los módulos, conserva resultados sintéticos y permite ejecutar y demostrar los 14 escenarios de principio a fin. Este plan no reduce el alcance: da soporte a siembra y atribución, voz, extracción y evidencia, inteligencia, SMS, portal ciudadano y tablero/mapa.

## Arquitectura acordada

- Monolito modular en Python con FastAPI; interfaz HTML/CSS/JavaScript sencilla.
- SQLite para persistencia local. JSON para escenarios y datos de muestra. Sin dependencias de servicios remotos durante la demo.
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
| 0–1 h | Acordar contratos, rutas internas, estructura de carpetas y cómo correr el proyecto. Crear repo ejecutable mínimo. |
| 1–4 h | Crear FastAPI, SQLite, carga de configuración, layout de navegación y datos sintéticos iniciales. |
| 4–8 h | Integrar un adaptador por módulo y asegurar que cada pantalla pueda abrirse aunque use datos provisionales. |
| 8–12 h | Implementar cargador de escenarios JSON, runner y registro de esperado/obtenido; consolidar los 14 casos. |
| 12–15 h | Ejecutar recorrido integrado, corregir errores de rutas, persistencia y campos compartidos; habilitar modo demo sin internet. |
| 15–16 h | Congelar funciones y código; etiquetar versión de demo y respaldar datos. |
| 16–18 h | Ensayar demo de tres minutos, registrar métricas reales del prototipo y grabar video de respaldo. |

## Aceptación

- Un comando inicia la app en laptop sin internet y muestra datos sintéticos.
- Se puede navegar por todos los módulos y seguir un evento desde la trampa hasta tablero y ruta ciudadana.
- Los 14 JSON se cargan y el runner registra esperado y obtenido sin inventar porcentajes.
- Los registros de reporte almacenados no incluyen datos personales del formulario original.
- Existe una demo ensayada y un video local reproducible.

## Uso de herramientas de codificación con IA

Delegar cambios por archivo y contrato. Pedir primero un diff pequeño y revisión de imports; no permitir que un agente cambie esquemas congelados sin avisar. Integrar cada módulo cuando entregue una función importable y un ejemplo JSON, no esperar hasta la hora 12.

