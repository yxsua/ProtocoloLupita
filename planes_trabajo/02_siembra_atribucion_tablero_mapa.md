# Plan 2 — Siembra, atribución, tablero y mapa

**Proyecto:** Mosca Estéril (Doña Lupita) · **Responsable:** Integrante 2 · **Duración:** 18 horas · **Rol:** trazabilidad y visualización

## Objetivo

Construir la siembra de registros sintéticos del sistema **Mosca Estéril** y demostrar qué copia de base de datos corresponde a un número trampa que recibió una llamada o SMS. Mostrar la atribución de fugas para la Contraloría, el boletín epidemiológico de campañas, la ventaja de tiempo frente al primer reporte ciudadano y el mapa local de los 18 municipios de **Querétaro**.

La siembra, atribución individual y dashboards detallados pertenecen a la **sección privada de Gobierno** (`/gobierno`). La sección pública Ciudadanía solo podrá consultar un producto agregado con supresión de grupos pequeños y sin campos que permitan reconstruir la copia o el evento interno.

## Alcance asignado

- **Siembra determinista (`Faker('es_MX')`):** Generar al menos 15 personajes y copias ficticias usando semilla fija (p. ej. `seed=2026`) para que los fixtures sean reproducibles tras cualquier reinicio (ej. `Proveedor A - padrón predial - 2026-10`).
- **Mapeo 1 a 1 copia ↔ trampa y resguardo criptográfico:** Insertar un identificador trampa sintético por copia y periodo (`seed_period`, p. ej. `2026-10`); asignar una única copia a cada número trampa. Un mismo `trap_id` puede recibir llamadas y SMS (uso multicanal) para esa copia. El mapeo completo número↔copia es el secreto del sistema: se guarda protegido/separado para rol **Contraloría / tablero interno** (nunca expuesto en rutas ciudadanas públicas) y se publica su **hash SHA-256 de manifiesto (`seed_manifest_hash`)** para probar que no fue alterado.
- **Formato y normalización de números trampa:** Generar números exclusivamente ficticios con formato local de Querétaro **`+52 442`** (ej. `+52 442 XXX 0101 (ficticio)` / `+52 442 000 0101`), marcados visualmente como `[FICTICIO / SINTÉTICO]` en UI y fixtures, y nunca usados para marcar o enviar mensajes reales. Normalizar `trap_id` en una función pura (limpiando etiquetas como `(ficticio)`, espacios, guiones y prefijo `+52`/`52`) antes de consultar SQLite.
- **Atribución estricta por receptor:** Atribuir exclusivamente por el número trampa receptor; nunca deducir identidad por número de origen (el número de origen solo se conserva como dato secundario). Si un reporte (p. ej. portal ciudadano `E12–E14`) llega sin `trap_id` o con un número no sembrado, devolver un estado controlado `"no_atribuido"` sin lanzar error fatal.
- **Vista de siembra (`/gobierno/siembra`, migrar `/planting`):** Mostrar catálogo interno de personajes, copias y números trampa ficticios, el `seed_manifest_hash`, permitir resembrar/generar un periodo de prueba e incluir probador manual de `attribute(trap_id)`. Exigir rol de gobierno para vista y cada endpoint de lectura/escritura; no publicar el mapeo en la sección ciudadana.
- **Tablero privado (`/gobierno/dashboard`, migrar `/dashboard`):**
  - Mostrar atribuciones explicadas (`copy_id`, `provider`, `seed_period`, tipo de ataque), indicadores enmascarados y campañas recibidas desde el motor de inteligencia, sin volver a clasificarlas ni elevar su confianza.
  - Mostrar productos de inteligencia para tablero: **Atribución de fugas (Contraloría)**, **Boletín epidemiológico** (campañas activas, variantes de guion y **cuántos números trampa distintos alcanzó cada una**, sin audios ni datos personales) y **métrica clave de ventaja de tiempo** (horas entre el primer contacto a una trampa y el primer reporte ciudadano de la misma campaña, medible entre `E01` y `E12`).
  - Etiquetar explícitamente cualquier acción hacia terceros (bancos, telefónica, UIF, Fiscalía / autoridad competente) como **Simulado (prototipo)** y nunca afirmar bloqueos automáticos ni fraude confirmado por una sola fuente.
  - Soportar estados vacíos claros y ordenamiento cronológico inverso (`limit` configurable, por defecto 50).
- **Mapa agregado público de los 18 municipios de Querétaro (`/api/public/map`):**
  - Usar el GeoJSON oficial de los 18 municipios de **Querétaro** empaquetado localmente en `data/geo/municipios_18.geojson`, indexado por `municipality_code` (clave INEGI de 5 dígitos) y `municipality_name`.
  - Aplicar **umbral de publicación de `>= 5` reportes en el backend** antes de serializar la respuesta al frontend: los municipios con `1–4` reportes devuelven `count: null, suppressed: true`, pero **sí se suman al agregado estatal (`state_total`)**.
  - Contabilizar reportes ciudadanos saneados válidos (`E13`); excluir duplicados rechazados por límite de tasa (`E14`) y mostrar eventos sin municipio solo en el tablero general, sin inventar municipio.
- **Operación 100% offline:** Renderizar `data/geo/municipios_18.geojson` en `app/static/dashboard.js` usando **SVG en JavaScript puro** (o Leaflet local empaquetado en `app/static/` sin capa de teselas), sin teselas externas, geocodificación en internet ni CDNs.
- **Separación de acceso:** Toda ruta interna de tablero, siembra, evento, atribución, cadena de evidencia o paquete institucional requiere sesión autenticada de gobierno verificada en backend. La respuesta pública del mapa se construye con un esquema público explícito y aplica el umbral antes de serializar; ocultar controles del frontend no cuenta como autorización.
- **Prioridad y orden de recorte:** Prioridad 1 para Siembra y atribución, Prioridad 3 para Tablero y mapa. Si falta tiempo hacia el cierre, el mapa se recorta primero antes de afectar siembra, atribución o flujo principal de tablero.

## Archivos bajo responsabilidad

- `app/modules/planting/` — `generator.py`, `repository.py`, `service.py`, `schemas.py`, `router.py`, `fixtures_local.py`.
- `app/modules/dashboard/` — `service.py`, `schemas.py`, `router.py` (dashboard privado y endpoints de lectura, boletín, métrica de ventaja de tiempo y agregados públicos depurados).
- `app/modules/map/` — `aggregator.py`, `schemas.py`, `router.py` (agregación, umbral y GeoJSON estático).
- `app/templates/planting/index.html`, `app/templates/dashboard/index.html` (Jinja2 extendiendo `app/templates/base.html` mediante `{% block content %}` y `{% block scripts %}`), `app/static/dashboard.js`.
- `data/planting/seed_copies.json` y `data/geo/municipios_18.geojson` (coordinado con Integrante 1 para no duplicar fixtures).
- `tests/test_plan2_modules.py` — pruebas unitarias de determinismo, normalización, hash de manifiesto, atribución, tablero y umbral `>= 5`.

## Contratos de integración

- **Esquemas compartidos (`app/core/schemas.py`):**
  - `AttributionResult`: `trap_id`, `copy_id` (opcional si no existe trampa), `provider`, `seed_period`, `synthetic` (`True`), `attribution_id` (acordado con Plan 1 como `copy_id` o ID dedicado), `manifest_hash` y `status` (`"atribuido" | "no_atribuido"`).
  - `DashboardFilters`: `channel` (`call | sms | portal`), `seed_period`, `campaign_id`, `status`, `confidence`, `limit`.
  - `CampaignSummary`: `campaign_id`, `brand`, `channels`, `event_count`, `traps_reached_count`, `script_variants`, `lead_time_hours` (horas entre primer contacto en trampa y primer reporte ciudadano, opcional si no hay reporte aún), `confidence`, `status`, `indicator_ids`.
  - `DashboardResponse`: `summary` (incluyendo `seed_manifest_hash` y métrica de ventaja de tiempo), `attributions` (cruce de `Event` + `AttributionResult` + alias ficticio + `Indicator.value_masked` + explicación textual), `campaigns`, `empty_state`.
  - `StateMapSummary`: `state_name` (`"Querétaro"`), `state_total`, `threshold` (`5`), `municipalities` (siempre los 18 elementos con `municipality_code`, `municipality_name`, `count: int | None`, `suppressed: bool`) y `geojson`.
- **Funciones y endpoints expuestos:**
  - `attribute(trap_id) -> AttributionResult` (invocable desde `scenario_runner`, voz, SMS, portal o `intel.process_event`).
  - `get_dashboard(filters: DashboardFilters | None = None) -> DashboardResponse`.
  - `get_map_summary() -> StateMapSummary`.
  - `get_seed_manifest_hash() -> str`.
  - Rutas HTTP registradas vía `get_routers()` / `register_routes(app)`: `/planting`, `/api/planting/copies`, `/api/planting/seed`, `/api/planting/attribute/{trap_id}`, `/dashboard`, `/api/dashboard`, `/api/map`.
- **Frontera con Inteligencia y Portal Ciudadano:**
  - Consumir `Event`, `Indicator`, campañas y conteos municipales por adaptador hacia servicios de Integrantes 4 y 5 (o lectura directa sobre tablas compartidas en `app/core/db.py`).
  - Respetar el catálogo de estados recibido (`"indicio"`, `"corroborado"`, `"sin_verificar"`) y niveles de confianza sin recalcular reglas de negocio en el tablero.
  - Exponer `init_planting_db(conn)` y `seed_if_empty(conn)` en `repository.py` para que `app/core/db.py` / `seed_data.py` puedan inicializar tablas SQLite de forma idempotente.

## Escenarios cubiertos (`E01–E14`)

- `E01–E11`: Atribución determinista de llamadas y SMS de fixture (p. ej. `E01` con `+52 442 XXX 0101 (ficticio)` → `"Proveedor A - padrón predial - 2026-10"`) vía `attribute(trap_id)`.
- `E12`: Visualización del cruce entre reporte ciudadano saneado (sin PII) y `E01` en el tablero, incluyendo el cálculo de horas de ventaja entre el primer contacto a la trampa y el reporte ciudadano.
- `E13`: Validación del umbral mínimo de `5` reportes en el mapa de Querétaro (municipio con `3` reportes suprimido individualmente e incluido en `state_total`).
- `E14`: Presentación de reportes marcados como `"sin verificar"` sin alterar conteos tras límite de tasa.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–1 h | Confirmar catálogo INEGI de los 18 municipios de Querétaro, formato canónico `+52 442` de `trap_id`, `attribution_id` y contratos de `DashboardResponse`/`StateMapSummary` con Integrantes 1, 4 y 5. |
| 1–5 h | Generador determinista con `Faker('es_MX')`, normalizador de `trap_id`, tablas SQLite (`init_planting_db`), cálculo de `seed_manifest_hash` y fixture compartido `data/planting/seed_copies.json`. |
| 5–8 h | Servicio `attribute(trap_id)` (incluyendo manejo de `no_atribuido`), API REST y vista `/planting` con probador interactivo y hash publicado. |
| 8–11 h | Servicio `get_dashboard(filters)` con adaptadores desacoplados, vista `/dashboard` (Contraloría, boletín epidemiológico, métrica de ventaja de tiempo, avisos de simulación) y estados vacíos claros. |
| 11–13 h | Empaquetado de `data/geo/municipios_18.geojson` (Querétaro), agregador con umbral `>= 5` en backend y renderizado offline en `app/static/dashboard.js`. |
| 13–16 h | Integración con routers en `main.py`, eventos reales de `intel`/`citizen`, pruebas `E01–E14` en modo sin internet y congelamiento. |
| 16–18 h | Verificar las vistas y métricas observadas durante el guion de demo de 3 minutos (pasos 1, 3 y 5); respaldar SQLite/fixtures y apoyar video. |

## Aceptación

- Una llamada o SMS de fixture a un número trampa `+52 442` (en cualquiera de sus variantes de formato) devuelve siempre la misma copia y periodo.
- El mapeo de siembra expone su hash de integridad (`seed_manifest_hash`) y nunca se filtra en rutas públicas ciudadanas.
- Un evento sin número trampa o con número desconocido se maneja de forma segura como `"no_atribuido"` sin romper tablero ni escenarios.
- El tablero explica qué copia se atribuyó, por qué evento, con qué estado/confianza e indicadores enmascarados recibidos del motor de inteligencia, muestra alcance en trampas y horas de ventaja de tiempo, y marca envíos a terceros como simulados.
- Se ven los 18 municipios de Querétaro en el mapa local; un municipio con 3 reportes aparece suprimido tanto en UI como en el JSON de `/api/map`, y sus 3 reportes se incluyen en `state_total`.
- El prototipo funciona 100% desconectado (sin peticiones externas en consola) y distingue visualmente toda información sintética.

## Trabajo independiente

Usar `app/modules/planting/fixtures_local.py` y adaptadores en memoria mientras llega la app base de Integrante 1. Mantener los módulos `planting`, `dashboard` y `map` importables sin editar `app/main.py`; entregar `get_routers()` / `register_routes(app)` a Integrante 1 cuando esté listo.

