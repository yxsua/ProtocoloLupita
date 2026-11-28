# Plan 3 — Doña Lupita y voz híbrida

**Responsable:** Integrante 3 · **Duración:** 18 horas · **Rol:** conversación de llamada

## Objetivo

Atender una llamada desde un celular al número de prueba. El proveedor telefónico reconoce la voz y entrega texto al servidor; el agente elige una intención permitida y responde con audio controlado. El panel gubernamental muestra los resultados de la llamada en vivo. Una persona del equipo puede interpretar al atacante con un guion; el panel de escenarios no ofrece interacción libre.

## Diseño acordado

- Flujo piloto: celular → Twilio → webhook HTTPS → Gather con `deepgram_nova-3`/`es-MX` → texto reconocido → selector de intención cerrada → audio pregrabado o respuesta dinámica.
- Twilio procesa el audio de voz; este piloto no manda audio a Whisper ni almacena grabaciones. Migrar a Media Streams/WSS y reconocimiento propio queda como siguiente etapa.
- El perfil del agente se resuelve por el número receptor asociado a la trampa; el identificador del número llamante es secundario y no verificado.
- Limitar el piloto a una llamada activa. El estado de la sesión y SSE viven en memoria; ejecutar un solo worker.
- Enviar eventos de inicio, turnos, intenciones, indicadores y finalización al panel gubernamental; la transcripción en el bus es temporal y se enmascaran secuencias numéricas largas.
- Los saludos y respuestas disponibles se reproducen desde clips; usar Piper local para texto dinámico con una voz en español mexicano si está configurada. Escuchar y revisar la pronunciación antes de la demo. Twilio `<Say>` es el fallback.
- Conservar la pantalla de voz actual como herramienta de desarrollo/respaldo. Las simulaciones corren por separado y no se registran como llamadas móviles.
- Ollama es opcional para seleccionar una intención de una lista cerrada; reglas locales son el fallback. No generar conversación libre.
- La persona nunca revela datos reales, amenaza, insulta ni afirma ser autoridad. Usar ficha y cuentas ficticias.

## Configuración de prueba

Usar `.env.example` como referencia, asignar los valores reales en el entorno del servidor y mantener secretos fuera del repositorio. Configurar la URL de voz del DID como `POST /api/telephony/voice`, y el callback de estado como `POST /api/telephony/status`. `PUBLIC_BASE_URL` debe ser HTTPS y coincidir con la URL pública que Twilio usa al firmar las solicitudes. La trampa sembrada de Doña Lupita es `+52 442 000 0102`.

## Archivos bajo responsabilidad

- `app/modules/telephony/` — webhooks, sesiones y adaptación Twilio.
- `app/modules/voice/` — política conversacional, extracción, fragmentos pregrabados y Piper.
- `app/modules/voice/assets/` — fragmentos de audio, inventario y voces locales.
- `app/templates/voice/`, `app/static/voice.js`.
- Casos de llamada E01–E08 en `data/scenarios/`; se ejecutan por el mismo servicio de voz, pero fuera de la telefónica.

## Contrato de integración

La integración acepta texto transcrito del proveedor como turno de entrada y llama `VoiceService.process_call()`. Emite eventos de inicio, turno, intención, indicadores y fin al bus gubernamental. No escribe audio ni texto íntegro a disco. Ante silencio usa los mensajes de repetición y termina tras tres intentos sin entrada; una llamada termina a los cinco minutos.

## Secuencia de trabajo

| Tiempo | Entrega |
|---|---|
| 0–1 h | Acordar proveedor, DID de prueba, variables de entorno, webhook HTTPS y acceso al panel. |
| 1–3 h | Preparar perfil, guion y política de intenciones cerradas; mantener ejecución determinista desde escenarios. |
| 3–7 h | Recibir llamadas por webhook, verificar firma del proveedor y comprobar Gather español con el número de prueba. |
| 7–10 h | Conectar selector de intención y extracción; limitar a una llamada activa y controlar silencios. |
| 10–13 h | Reproducir clips por teléfono; medir naturalidad y latencia de Piper dinámico si aplica. |
| 13–15 h | Emitir eventos al panel y ejecutar E01–E08 por el servicio compartido. |
| 15–16 h | Verificar fallback de voz, ocupado y limpieza de sesión al colgar o perder conexión. |
| 16–18 h | Ensayar E01 desde celular, revisar atribución/resultados en vivo y preparar respaldo de demo. |

## Aceptación

- E01 se demuestra con una llamada al DID de prueba y el panel gubernamental recibe los eventos en vivo.
- E04 repite cifras para confirmar y E05 solicita corregir cuentas con validación inválida.
- E06 permanece en personaje y no revela instrucciones internas; E07 trata la cuenta como indicio de confianza baja.
- La llamada termina por límite de tiempo o falta de entrada; una segunda llamada recibe el mensaje de ocupado.
- El panel etiqueta el DID asociado a la copia sembrada y muestra el número de origen como no verificado.
- La voz de salida se prueba en el teléfono y se entiende bien en español mexicano.
