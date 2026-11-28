# Integración del prototipo local

## Modo activo: ciudadanía pública y gobierno privado

La plataforma tiene dos secciones. La portada (`/`), el portal (`/citizen`), el analizador SMS (`/sms`) y los avisos agregados (`/dashboard`) son públicos. El panel de resultados detallados y escenarios está en `/gobierno` y requiere `GOV_PANEL_USERNAME` y `GOV_PANEL_PASSWORD`.

La simulación está dentro del área privada, en `/gobierno/simulador`, junto al dashboard `/gobierno`. Su GUI muestra una llamada entrante, permite contestarla o rechazarla y luego presenta la conversación como transcripción. El dashboard recibe el saludo inicial y cada turno mediante SSE, con el mismo texto saneado que ve el simulador. La llamada no usa la red telefónica: el navegador envía texto o audio al servicio local de voz, que selecciona respuestas de Doña Lupita. El número de origen, el número trampa y la copia atribuida son ficticios. Los endpoints de telefonía real no se montan en este modo.

El dictado del navegador se solicita en modo local para evitar servicios de voz remotos. Si el navegador no tiene instalado el paquete de español, el simulador ofrece prepararlo; si el navegador no admite reconocimiento local, se puede usar Whisper local o escribir los turnos.

Al entrar un turno, el módulo de voz sanea la transcripción para la consola, manda el texto saneado al motor local de inteligencia y transmite solo indicadores enmascarados, campaña y hash de evidencia. El audio crudo no se envía al panel ni se guarda. Los eventos quedan en memoria y se reinician cuando se cierra el servidor.

## Límites de acceso

- La ciudadanía puede enviar reportes sin cuenta; el portal descarta o enmascara PII antes de persistir.
- El dashboard, la atribución y la evidencia detallada requieren autenticación gubernamental en sus endpoints, además de las vistas.
- Los endpoints públicos de avisos y mapa solo devuelven campos agregados y aplican el umbral municipal en el backend.
- Los routers de siembra, inteligencia y ejecución de escenarios requieren autenticación. El reset de demo también es privado.
- El simulador y sus endpoints de voz requieren las mismas credenciales locales de Gobierno; ya no hay enlace público a la experiencia de llamada.
- Se permite una sola llamada activa. El botón de rechazar descarta la llamada antes de crear una sesión; «Cancelar llamada» termina una sesión contestada y notifica al dashboard.
- La integración telefónica permanece en el código fuente, pero su router no se monta en la aplicación local. No se reciben ni originan llamadas telefónicas reales en este modo.

## Iniciar en una laptop y abrir desde un celular

1. Copiar `.env.example` a `.env` y definir credenciales locales para Gobierno.
2. Iniciar en la laptop: `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env`.
3. Abrir `http://127.0.0.1:8000/gobierno` en la laptop e ingresar las credenciales configuradas.
4. Para que un celular en la misma red abra la sección pública, iniciar Uvicorn con `--host 0.0.0.0` y usar la IP local de la laptop. Mantener la demo en una red local controlada y usar solo datos sintéticos.

El bus de eventos y las sesiones de voz son locales y en memoria; usar un solo worker. Si el navegador del celular no permite micrófono sobre HTTP en la LAN, usar la entrada de texto. Los clips de audio servidos por la aplicación siguen disponibles como respuesta de voz.

## Artefactos

Los contratos entre módulos están en [DECISIONES_ARQUITECTURA.md](DECISIONES_ARQUITECTURA.md). Los escenarios JSON están en `data/scenarios/`; la base local se crea como `data/prototipo.sqlite3` y no se versiona.
