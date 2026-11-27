# Plan 3 — Doña Lupita y voz híbrida

**Responsable:** Integrante 3 · **Duración:** 18 horas · **Rol:** conversación de llamada

## Objetivo

Implementar una llamada demostrable desde el micrófono de la laptop: transcribir al atacante, elegir una intención permitida y responder con audio controlado. Debe capturar y confirmar la CLABE dictada, mantener una duración máxima y conservar modo texto como respaldo.

## Diseño acordado

- Flujo local: audio → Whisper → transcripción → selector de intención cerrada → fragmento pregrabado; usar Piper solo para dígitos u otro contenido dinámico.
- Ollama es opcional para selección de intención dentro de una lista fija; no debe producir texto o instrucciones libres. Si su latencia o instalación pone en riesgo el flujo, usar reglas locales para seleccionar la misma lista.
- Intenciones permitidas: asustarse, pedir repetición, preguntar cuenta de depósito, repetir dígitos, dar largas y despedirse.
- Audio pregrabado mientras corre la transcripción/modelo para hacer tolerable la espera.
- Límite de duración configurable y botón de finalizar. Ruta de respaldo textual disponible desde la interfaz.
- La persona nunca revela datos reales, amenaza, insulta ni afirma ser autoridad. Usar ficha y cuentas ficticias.

## Archivos bajo responsabilidad

- `app/modules/voice/` — captura, transcripción, política de intención, reproducción y estado de llamada.
- `app/modules/voice/assets/` — fragmentos de audio, inventario y configuración de voces locales.
- `app/templates/voice/`, `app/static/voice.js`.
- Casos de llamada en `data/scenarios/` para E01–E08 (Integrante 1 los consolida).

## Contrato de integración

Exponer `process_call(input) -> CallResult` con transcripción, intención seleccionada, indicadores candidatos, duración, estado de finalización y referencia al evento; no incluir audio crudo en el evento persistido. Consumir el esquema común y entregar extracción de cuenta al servicio de Integrante 4, o devolver el texto transcrito para que ese servicio lo procese. Coordinar el formato al inicio y conservar modo texto si falla un modelo.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–1 h | Acordar `CallResult`, formato de audio y ejecución offline; confirmar que los modelos necesarios están descargados antes del hackathon. |
| 1–3 h | Flujo de texto determinista con lista cerrada, estado de conversación y finalización por duración. |
| 3–7 h | Captura de micrófono y transcripción local con Whisper; manejo de silencio y errores. |
| 7–10 h | Selector de intenciones cerrado, protección frente a “ignora instrucciones” y respuestas de fallback. |
| 10–13 h | Fragmentos pregrabados y reproducción; Piper local solo para contenido dinámico. |
| 13–15 h | Conectar extractor, confirmar dígitos dictados y mantener control de duración. |
| 15–16 h | Congelar voz y verificar modo texto ante fallo de audio/modelo. |
| 16–18 h | Ensayar E01 en el flujo de demo, revisar latencia y apoyar grabación del video. |

## Aceptación

- E01 se puede demostrar desde micrófono y la cuenta de prueba queda transcrita, validada y confirmada en voz.
- E04 convierte números dictados en palabras a dígitos y los repite para confirmar.
- E05 detecta dígito verificador incorrecto y solicita repetición.
- E06 permanece en personaje y no revela instrucciones internas.
- E07 marca cuenta de una sola fuente como indicio de confianza baja.
- La llamada termina sola al alcanzar el límite y el flujo textual está siempre disponible.

## Trabajo independiente

Desarrollar la política de conversación primero con transcripciones escritas de ejemplo. La captura y audio son adaptadores sobre esa política; así otros módulos pueden integrar y probar el flujo aunque Whisper no esté listo.

