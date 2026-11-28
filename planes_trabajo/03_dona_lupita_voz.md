# Plan 3 — Doña Lupita y llamada simulada local

**Responsable:** Integrante 3 · **Duración:** 18 horas · **Rol:** conversación de llamada

## Objetivo

El alcance vigente ubica el simulador enteramente dentro de la sección privada Gobierno. La ciudadanía pública no puede iniciar ni observar llamadas trampa. El operador ejecuta un escenario precargado como llamada entrante, contesta o rechaza y reproduce la conversación completa con voces locales del navegador; puede cancelar durante la llamada. La transcripción saneada se muestra en la simulación y en el dashboard gubernamental. No se llama ni se envían mensajes a números reales.

## Diseño acordado

- Modo de demostración garantizado sin modelos: escenario de turnos prefijados y síntesis de voz del navegador para quien llama y Doña Lupita. Asignar voces distintas cuando el navegador lo permita. El micrófono y el reconocimiento local no forman parte del recorrido base.
- El escenario controla el orden de los turnos y las respuestas; no se consulta un modelo conversacional ni se acepta entrada libre de atacante o de Doña Lupita.
- La interfaz muestra los controles de llamada entrante: contestar, rechazar y cancelar la sesión activa. La llamada simulada se termina al completar el guion o al cancelarla.
- Cada llamada usa una sesión e identificadores, número de origen, número trampa receptor, hora, duración, ubicación de filtración y demás metadatos íntegramente ficticios. La atribución se determina por la trampa receptora, nunca por el origen.
- La sesión debe poder consultarse desde otro dispositivo durante la llamada y permanecer disponible al terminar para el reporte sintético. Publicar actualizaciones locales sin audio crudo; preferir polling sencillo cada 1–2 segundos salvo que la implementación existente justifique SSE/WebSocket.
- El simulador está en `/gobierno/simulador` y el dashboard privado en `/gobierno`; las vistas y endpoints de llamada requieren autenticación de Gobierno. Si se muestran en dos dispositivos, ambos usan el acceso privado local.
- El resultado final permite generar un expediente de demostración imprimible/descargable con cronología, datos sintéticos, indicadores enmascarados, atribución, nivel de confianza y hashes de evidencia. Rotularlo “SIMULADO — sin validez oficial”; no transmitirlo a autoridades.
- La persona nunca revela datos reales, amenaza, insulta ni afirma ser autoridad. Usar ficha y cuentas ficticias.

## Configuración de prueba

Usar `.env.example` como referencia, asignar los valores reales en el entorno del servidor y mantener secretos fuera del repositorio. Configurar la URL de voz del DID como `POST /api/telephony/voice`, y el callback de estado como `POST /api/telephony/status`. `PUBLIC_BASE_URL` debe ser HTTPS y coincidir con la URL pública que Twilio usa al firmar las solicitudes. La trampa sembrada de Doña Lupita es `+52 442 000 0102`.

## Archivos bajo responsabilidad

- `app/modules/telephony/` — webhooks, sesiones y adaptación Twilio.
- `app/modules/voice/` — política conversacional, extracción, fragmentos pregrabados y Piper.
- `app/modules/voice/assets/` — fragmentos de audio, inventario y voces locales.
- `app/templates/voice/`, `app/static/voice.js`.
- Vista privada del simulador y monitor en vivo de Gobierno, coordinados desde `app/modules/government/` y `app/modules/voice/`.
- `app/modules/evidence/` y `app/modules/intel/` para persistir metadatos saneados, correlacionar indicadores y construir el expediente simulado.
- Casos de llamada en `data/scenarios/` para E01–E08 (Integrante 1 los consolida).

## Contrato de integración

Conservar `process_call(input) -> CallResult` con transcripción, intención seleccionada, indicadores candidatos, duración y estado. Agregar un identificador de sesión consultable y emitir actualizaciones resumidas para el monitor y el servicio de inteligencia. No persistir audio crudo ni transcripción sin sanear. Consumir el esquema común y entregar texto saneado y metadatos ficticios al servicio de Integrante 4. La atribución depende de `trap_id` receptor. Mantener texto/guion prefijado como ruta segura de demo cuando falle el audio o un modelo.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–1 h | Congelar contrato de sesión, separar pantalla móvil y monitor; definir metadatos ficticios y el payload consultable en vivo. |
| 1–3 h | Hacer fiable la llamada simulada en modo guion/texto, con sesión compartida, estado y finalización. |
| 3–5 h | Preparar acceso LAN autenticado de Gobierno desde el dispositivo secundario y comprobar diseño adaptable/reconexión. |
| 5–8 h | Asegurar reproducción ordenada de los parlamentos y voces diferenciadas del escenario en el navegador. |
| 8–11 h | Enviar turnos al monitor en vivo y a inteligencia; mostrar extracción, origen/trampa ficticios, atribución y estados sin afirmar certeza. |
| 11–13 h | Crear expediente sintético imprimible/descargable con cronología y referencias/hash de evidencia. |
| 13–15 h | Mantener validación de CLABE y protección ante prompt injection; asegurar que ningún audio o dato personal crudo se guarda. |
| 15–16 h | Congelar contratos y verificar recuperación/conexión móvil y modo de respaldo. |
| 16–18 h | Ensayar recorrido de dos pantallas con caso determinista, generar expediente de muestra y preparar plan alterno sin micrófono. |

## Aceptación

- Simulador y dashboard son exclusivos de Gobierno; cuando se muestran en dos dispositivos, ambos requieren autenticación local y muestran la misma sesión.
- Un escenario precargado ejecuta una demo completa con las voces generadas en el navegador, sin mensajes libres, micrófono, servicios remotos ni modelos.
- El monitor muestra cada turno en tiempo real o con retraso máximo objetivo de 2 segundos, además de atribución por receptor, indicadores enmascarados y estado de inteligencia.
- El expediente generado es coherente con los eventos, marcado como sintético y no se envía a autoridad alguna.
- E01 se puede demostrar con voz o modo de respaldo, y la cuenta sintética queda transcrita, validada y confirmada en voz.
- E04 convierte números dictados en palabras a dígitos y los repite para confirmar.
- E05 detecta dígito verificador incorrecto y solicita repetición.
- E06 permanece en personaje y no revela instrucciones internas.
- E07 marca cuenta de una sola fuente como indicio de confianza baja.
- La llamada termina sola al alcanzar el límite y el flujo de guion/texto está siempre disponible.

## Trabajo independiente

Desarrollar la política de conversación primero con turnos de guion. La captura y reproducción de audio son adaptadores opcionales sobre esa política. Integrar el monitor y la persistencia de evidencia antes de optimizar Whisper: así la demo en dos dispositivos funciona incluso sin modelos.

