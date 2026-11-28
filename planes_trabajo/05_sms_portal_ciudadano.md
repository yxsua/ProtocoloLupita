# Plan 5 — SMS y portal ciudadano

**Responsable:** Integrante 5 · **Duración:** 18 horas · **Rol:** análisis de mensajes y experiencia ciudadana

## Objetivo

Construir la bandeja de SMS sintéticos y el portal donde una persona pega un mensaje sospechoso o envía un reporte. El mismo motor devuelve una explicación comprensible, cruza el indicador con campañas y ofrece una ruta de respuesta. La aplicación nunca abre enlaces ni responde SMS.

Este plan corresponde a la **sección pública Ciudadanía** (`/ciudadania`, conservando `/citizen` como alias durante la migración). No incorpora dashboards internos. La consulta ciudadana usa explicaciones redactadas y agregados públicos; la atribución de trampas, las llamadas en curso y los paquetes de evidencia quedan solo en la sección privada de Gobierno.

## Alcance asignado

- Bandeja alimentada por fixtures; extraer remitente, enlaces, teléfonos y cuentas del mensaje.
- Clasificar suplantación (SAT, IMSS, CFE, bancos, paquetería/telefónica) y tipo de engaño mediante reglas primero; etiqueta opcional de modelo local detrás de una interfaz intercambiable.
- Comparar dominios sin abrirlos: catálogo local de dominios oficiales, señales de similitud, acortadores y punycode.
- Guardar/mostrar enlaces desactivados (`hxxp`) y marcarlos claramente como no abiertos.
- Formulario ciudadano para llamada/SMS; limpiar nombre, CURP, teléfono y otros datos personales antes de persistir. Pasar solo campos sanitizados e indicadores al motor de inteligencia.
- Explicar el resultado en lenguaje claro, indicar si es indicio/campaña corroborada/sin verificar y mostrar ruta guiada local para reportar o protegerse.
- Límite de tasa para reportes repetidos y estado “sin verificar”; integrar agregados municipales con el mapa de Integrante 2.
- Mantener una allowlist pública de respuesta: recomendación, estado general de campaña y conteos agregados sobre el umbral. Nunca devolver `copy_id`, proveedor/dataset sembrado, `trap_id`, transcripción de llamada trampa, hash de evidencia ni paquetes institucionales.
- La vista y API pública de reporte no requieren cuenta, pero deben sanear PII antes de persistir. No reutilizar DTOs de dashboard o inteligencia interna directamente en respuestas públicas.
- El modo de llamada del jurado será un simulador ficticio dentro de la sección pública, autorizado por un token aleatorio limitado a esa sesión; no permite consultar resultados del dashboard.

## Archivos bajo responsabilidad

- `app/modules/sms/` — parser, reglas, comparación de dominios y router.
- `app/modules/citizen/` — formulario, saneamiento, límite de tasa y ruta guiada.
- `app/templates/sms/`, `app/templates/citizen/`, `app/static/citizen.js`.
- Layout y navegación pública compartidos con la sección privada, sin enlaces a rutas internas; coordinar aliases con Integrante 1.
- Casos E09–E14 en `data/scenarios/`; Integrante 1 los consolida.

## Contrato de integración

Exponer `analyze_sms(input) -> SmsAnalysis` y `submit_report(input) -> CitizenResponse`. Recibir campaña y confianza desde `process_event`; no definir independientemente que una cuenta sea fraude confirmado. Antes de llamar al motor, producir un `ReportInput` saneado. La API de mapa/tablero solo recibe municipio y conteo agregado que cumple el umbral. Acordar esquemas con Integrantes 1, 2 y 4 durante la primera hora.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–1 h | Acordar entrada/salida, catálogo local y campos personales que se descartan. |
| 1–5 h | Parser y reglas de SMS; dominios oficiales/impostores, acortadores y texto no confiable. |
| 5–7 h | Vista de bandeja y enlace desactivado; no incluir mecanismo que navegue al enlace. |
| 7–10 h | Formulario ciudadano y función de saneamiento antes de persistencia. |
| 10–12 h | Cruce con motor de inteligencia y respuesta/ruta guiada legible. |
| 12–14 h | Límite de tasa, estado “sin verificar” e integración con agregados de mapa. |
| 14–16 h | Integrar E09–E14, corregir contrato y congelar funciones. |
| 16–18 h | Ensayar flujo SMS y reporte en demo, revisar texto de pantallas y video. |

## Aceptación

- E09 detecta una imitación de dominio del SAT, crea/actualiza campaña y mantiene el enlace desactivado.
- E10 clasifica el mensaje de paquete retenido y señala el acortador.
- E11 clasifica el SMS como sospechoso y no obedece instrucciones incluidas en su texto.
- E12 descarta los datos personales del usuario antes de guardar el reporte; el indicador se cruza con E01.
- E13 respeta el umbral de 5 al mostrar el municipio y conserva el total agregado.
- E14 activa límite de tasa, conserva estado “sin verificar” y no publica el negocio.
- La respuesta nunca afirma certeza mayor que la confianza recibida del motor.
- Las páginas públicas no exponen atribuciones ni detalles de llamadas trampa; probar también acceso directo a endpoints, no solo navegación visual.

## Trabajo independiente

Implementar parser, reglas y saneamiento como funciones puras con fixtures locales antes de conectar vistas o persistencia. Usar adaptadores definidos por contrato para motor de inteligencia y mapa; no cambiar sus módulos directamente.

