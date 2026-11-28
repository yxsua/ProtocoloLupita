# Plan 3 — Doña Lupita y llamada simulada en móvil

**Responsable:** Integrante 3 · **Duración:** 18 horas · **Rol:** conversación de llamada

## Objetivo

Implementar una llamada enteramente simulada desde la sección pública Ciudadanía en un celular conectado a la misma red local que la laptop. La consola privada Gobierno, autenticada en la laptop, mostrará en tiempo real la transcripción saneada, los datos ficticios observados, la atribución de la trampa y el avance del análisis. La vista móvil solo participa en su llamada mediante un token acotado; no puede consultar los dashboards. No se llama ni se envían mensajes a números reales.

## Diseño acordado

- Flujo local opcional de audio: micrófono del celular → Whisper local, si está disponible → transcripción → selector de intención cerrada → fragmento pregrabado; usar Piper solo para dígitos u otro contenido dinámico.
- Modo de demostración garantizado sin modelos: guion de turnos prefijados y entrada de texto desde el celular, con opción de reproducir una grabación o usar síntesis de voz del navegador. La voz en vivo del micrófono es una mejora condicionada a permisos y soporte HTTPS del navegador en la red local.
- Ollama es opcional para selección de intención dentro de una lista fija; no debe producir texto o instrucciones libres. Si su latencia o instalación pone en riesgo el flujo, usar reglas locales para seleccionar la misma lista.
- Intenciones permitidas: asustarse, pedir repetición, preguntar cuenta de depósito, repetir dígitos, dar largas y despedirse.
- Audio pregrabado mientras corre la transcripción/modelo para hacer tolerable la espera.
- Límite de duración configurable y botón de finalizar. Ruta de respaldo textual disponible desde la interfaz.
- Cada llamada usa una sesión e identificadores, número de origen, número trampa receptor, hora, duración, ubicación de filtración y demás metadatos íntegramente ficticios. La atribución se determina por la trampa receptora, nunca por el origen.
- La sesión debe poder consultarse desde otro dispositivo durante la llamada y permanecer disponible al terminar para el reporte sintético. Publicar actualizaciones locales sin audio crudo; preferir polling sencillo cada 1–2 segundos salvo que la implementación existente justifique SSE/WebSocket.
- La pantalla móvil vive bajo `/ciudadania/demo/llamada/{session_id}`; la pantalla de escritorio vive bajo `/gobierno/llamadas/{session_id}` y requiere sesión de gobierno. Ambas se enlazan con un código/URL local, pero el token móvil solo autoriza operar esa llamada.
- El resultado final permite generar un expediente de demostración imprimible/descargable con cronología, datos sintéticos, indicadores enmascarados, atribución, nivel de confianza y hashes de evidencia. Rotularlo “SIMULADO — sin validez oficial”; no transmitirlo a autoridades.
- La persona nunca revela datos reales, amenaza, insulta ni afirma ser autoridad. Usar ficha y cuentas ficticias.

## Configuración de prueba

Usar `.env.example` como referencia, asignar los valores reales en el entorno del servidor y mantener secretos fuera del repositorio. Configurar la URL de voz del DID como `POST /api/telephony/voice`, y el callback de estado como `POST /api/telephony/status`. `PUBLIC_BASE_URL` debe ser HTTPS y coincidir con la URL pública que Twilio usa al firmar las solicitudes. La trampa sembrada de Doña Lupita es `+52 442 000 0102`.

## Archivos bajo responsabilidad

- `app/modules/telephony/` — webhooks, sesiones y adaptación Twilio.
- `app/modules/voice/` — política conversacional, extracción, fragmentos pregrabados y Piper.
- `app/modules/voice/assets/` — fragmentos de audio, inventario y voces locales.
- `app/templates/voice/`, `app/static/voice.js`.
- Vista pública del simulador y vista privada de monitoreo coordinada desde `app/modules/dashboard/` o una vista dedicada; coordinar con Integrante 1 los prefijos y controles backend.
- `app/modules/evidence/` y `app/modules/intel/` para persistir metadatos saneados, correlacionar indicadores y construir el expediente simulado.
- Casos de llamada en `data/scenarios/` para E01–E08 (Integrante 1 los consolida).

## Contrato de integración

Conservar `process_call(input) -> CallResult` con transcripción, intención seleccionada, indicadores candidatos, duración y estado. Agregar un identificador de sesión consultable y emitir actualizaciones resumidas para el monitor y el servicio de inteligencia. No persistir audio crudo ni transcripción sin sanear. Consumir el esquema común y entregar texto saneado y metadatos ficticios al servicio de Integrante 4. La atribución depende de `trap_id` receptor. Mantener texto/guion prefijado como ruta segura de demo cuando falle el audio o un modelo.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–1 h | Congelar contrato de sesión, separar pantalla móvil y monitor; definir metadatos ficticios y el payload consultable en vivo. |
| 1–3 h | Hacer fiable la llamada simulada en modo guion/texto, con sesión compartida, estado y finalización. |
| 3–5 h | Habilitar acceso móvil en la LAN (dirección/QR, diseño adaptable, reconexión y sesión visible); comprobar permisos de micrófono. |
| 5–8 h | Conectar captura/transcripción local opcional y audio de respuesta; incluir grabación/voz de navegador como alternativa. |
| 8–11 h | Enviar turnos al monitor en vivo y a inteligencia; mostrar extracción, origen/trampa ficticios, atribución y estados sin afirmar certeza. |
| 11–13 h | Crear expediente sintético imprimible/descargable con cronología y referencias/hash de evidencia. |
| 13–15 h | Mantener validación de CLABE y protección ante prompt injection; asegurar que ningún audio o dato personal crudo se guarda. |
| 15–16 h | Congelar contratos y verificar recuperación/conexión móvil y modo de respaldo. |
| 16–18 h | Ensayar recorrido de dos pantallas con caso determinista, generar expediente de muestra y preparar plan alterno sin micrófono. |

## Aceptación

- Se puede iniciar la sesión en la laptop y abrir el simulador en un celular por la red local; ambas pantallas muestran el mismo identificador.
- El guion o modo texto ejecuta una demo completa sin depender de servicios remotos ni modelos; cuando el navegador lo permita, se simula voz atacante desde el celular.
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

