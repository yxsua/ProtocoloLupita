# Plan 2 — Siembra, atribución, tablero y mapa

**Responsable:** Integrante 2 · **Duración:** 18 horas · **Rol:** trazabilidad y visualización

## Objetivo

Construir la siembra de registros sintéticos y demostrar qué copia corresponde a un número trampa que recibió una llamada o SMS. Mostrar la atribución, campañas y agregados en el tablero y un mapa local de los 18 municipios.

## Alcance asignado

- Generar personajes y copias ficticias con Faker en español de México.
- Insertar un identificador trampa sintético por copia y periodo; asignar una copia a cada número.
- Guardar el mapeo en SQLite local y exponerlo al módulo de atribución. En la interfaz y fixtures, los números deben aparecer marcados como ficticios.
- Atribuir por el número trampa receptor; no deducir identidad por número de origen.
- Tablero con atribuciones, indicadores y campañas recibidos desde el motor de inteligencia.
- Mapa agregado de los 18 municipios con umbral de publicación de 5 reportes; los conteos inferiores no se muestran por municipio.
- Usar GeoJSON local empaquetado; no depender de teselas ni geocodificación en internet.

## Archivos bajo responsabilidad

- `app/modules/planting/` — generador, repositorio y servicio de atribución.
- `app/modules/dashboard/` — endpoints de lectura y agregados.
- `app/modules/map/` — agregación y datos geográficos estáticos.
- `app/templates/planting/`, `app/templates/dashboard/`, `app/static/dashboard.js`.
- Datos sintéticos/GeoJSON en `data/`; coordinar ubicación con Integrante 1 antes de duplicar fixtures.

## Contrato de integración

Consumir los esquemas comunes de `app/core/schemas.py`. Exponer `attribute(trap_id) -> AttributionResult` y `get_dashboard(filters)`. El resultado debe incluir `copy_id`, proveedor, periodo y bandera `synthetic`. Recibir campañas/indicadores como datos del motor de inteligencia; no volver a clasificarlos en el tablero. Avisar a Integrante 1 si una visualización necesita un campo nuevo.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–1 h | Acordar los campos compartidos y validar la estructura de carpetas. |
| 1–5 h | Generador de personajes/copias y asociación determinista de número trampa ficticio con copia. |
| 5–8 h | Servicio de atribución consultable por llamada, SMS y portal; persistencia local. |
| 8–11 h | Tablero con atribución y estado de campañas; estados vacíos claros. |
| 11–13 h | Mapa y agregados municipales offline, aplicando umbral mínimo de 5. |
| 13–16 h | Integración con los eventos reales del prototipo, ajuste de textos y congelamiento. |
| 16–18 h | Verificar la vista durante el guion de demo; apoyar video y ensayo. |

## Aceptación

- Una llamada o SMS de fixture a un número trampa devuelve siempre la copia correcta.
- El tablero explica qué copia se atribuyó, por qué evento y con qué estado/confianza recibido.
- Se ven los 18 municipios en el mapa local; un municipio con 3 reportes no aparece individualmente y sus datos se incluyen en el agregado estatal.
- El prototipo funciona desconectado y distingue visualmente toda información sintética.

## Trabajo independiente

Usar datos de ejemplo propios dentro de `app/modules/planting/` mientras llega la app base. Mantener el módulo importable sin editar `main.py`; entregar a Integrante 1 el router o función de registro cuando esté listo.

