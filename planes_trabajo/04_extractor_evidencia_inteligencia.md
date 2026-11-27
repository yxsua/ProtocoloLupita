# Plan 4 — Extractor, evidencia y motor de inteligencia

**Responsable:** Integrante 4 · **Duración:** 18 horas · **Rol:** indicadores y correlación

## Objetivo

Extraer indicadores de llamadas, SMS y reportes sintéticos; validar CLABE y Luhn; conservar evidencia de forma reproducible; agrupar señales en campañas y actualizar su nivel de confianza sin convertir una sola coincidencia en fraude confirmado.

## Alcance asignado

- Extracción de CLABE, tarjeta, teléfono de origen, cuenta, enlace, marca suplantada, guion/plantilla y datos solicitados (NIP/código), cuando existan.
- Validador de CLABE de 18 dígitos y su dígito verificador; validador Luhn para tarjetas. Mantener las cuentas generadas exclusivamente sintéticas.
- Cadena ordenada de hashes de eventos/artefactos para detectar cambios en la demo; registrar algoritmo, orden y hash previo. No usarla como afirmación de custodia legal.
- Normalización y agrupación de llamadas/SMS/reportes por indicadores y similitud de guion/mensaje.
- Confianza por corroboración: una sola fuente queda como indicio; elevar nivel solo ante coincidencia independiente. Conservar estado “sin verificar” cuando aplique.
- Paquete de indicadores sintético para tablero y reporte institucional simulado.

## Archivos bajo responsabilidad

- `app/modules/intel/extractors.py`, `validators.py`, `campaigns.py`, `confidence.py`.
- `app/modules/evidence/` — hash, metadatos y consulta de eventos.
- `app/modules/intel/router.py` — funciones/endpoints de integración.
- Casos E01–E08 (llamadas), E09–E11 (SMS) y eventos de correlación sintéticos en `data/scenarios/`.

## Contrato de integración

Exponer `process_event(event) -> EventResult`, `extract_indicators(text, channel)` y `verify_account(value, kind)`. Consumir `Event`/`Indicator` comunes. Aceptar transcripción o texto ya sanitizado, nunca depender de audios. Enviar `campaign_id`, confianza, estado y referencias de indicadores al tablero/portal; notificar a Integrante 1 si requiere una migración de esquema.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–1 h | Fijar estructura de `EventResult`, estados y significado de niveles de confianza con el equipo. |
| 1–4 h | Extractores deterministas de CLABE, tarjeta, teléfono, enlaces, marca y patrones de guion. |
| 4–6 h | Validadores CLABE/Luhn y datos de prueba sintéticos generados con banco ficticio. |
| 6–9 h | Registro de evento con hash encadenado y consulta de integridad; pruebas con alteración deliberada del fixture. |
| 9–12 h | Agrupación de campaña y correlación por indicadores entre canales. |
| 12–14 h | Niveles de confianza y paquete de reporte simulado para instituciones/autoridad. |
| 14–16 h | Integrar con voz, SMS, portal y tablero; congelar interfaces. |
| 16–18 h | Revisar E01/E05/E07/E09/E12 y apoyar la demo y sus métricas observadas. |

## Aceptación

- Extracción produce valores normalizados y enmascarados en la interfaz; se valida el dígito de control.
- Los eventos sintéticos enlazan hashes y un cambio de contenido se puede detectar.
- Una coincidencia única queda como indicio; la corroboración por otra trampa o reporte actualiza la campaña sin etiquetarla automáticamente como fraude confirmado.
- SMS de contenido similar con enlaces distintos se agrupan en una campaña.
- Tablero y ruta ciudadana consumen la misma campaña e indicadores, sin duplicar reglas.

## Trabajo independiente

Crear fixtures propios con entradas de texto y salidas JSON siguiendo los contratos. El extractor no debe importar Whisper, FastAPI ni código de UI; mantenerlo como funciones Python puras para facilitar integración paralela.

