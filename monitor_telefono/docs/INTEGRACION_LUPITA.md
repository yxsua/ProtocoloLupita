# Integración local con Protocolo Lupita

El servidor independiente `monitor_telefono` puede reenviar eventos aceptados al feed `/mensajes` de la aplicación principal. El reenvío es opcional y se ejecuta entre los dos procesos del equipo local; Android sigue enviando primero al monitor, que conserva el evento cifrado en su base local.

## Configuración para la demo local

1. Arranca la aplicación principal en la laptop, escuchando en el puerto local `8000`, y define en su `.env` una clave aleatoria de al menos 32 caracteres en `LUPITA_DEVICE_KEY`.
2. En `monitor_telefono/.env`, configura el endpoint y la misma clave de integración:

   ```dotenv
   LUPITA_EVENTS_URL=http://127.0.0.1:8000/api/eventos
   LUPITA_EVENTS_KEY=<misma clave aleatoria que LUPITA_DEVICE_KEY>
   ```

   El monitor requiere que ambas variables estén definidas juntas. HTTP se acepta solo para loopback; para integrar servidores en hosts distintos, usa HTTPS.
3. Reinicia ambos servidores. En teléfonos ya vinculados, desvincula y vuelve a enrolar para aceptar el nuevo aviso. Después activa las notificaciones de las apps de prueba autorizadas.
4. Abre `/mensajes` en la aplicación principal con las credenciales gubernamentales. Los eventos nuevos aparecen en vivo, y los que el monitor reintente conservan su `id_evento` para deduplicarlos.

Al habilitar el relay cambia el texto y la versión del consentimiento del enrolamiento. Los teléfonos vinculados antes del cambio no se reenvían al portal hasta que su dueño desvincule y vuelva a vincular aceptando el aviso actualizado. Los eventos anteriores tampoco se importan retrospectivamente.

La clave se comparte únicamente entre los dos procesos servidores y no se instala en el APK. El monitor entrega al endpoint principal solo el id, nombre visible del dispositivo, tipo, app, remitente, texto, datos de llamada y fecha. No reenvía el token Android, consentimiento ni la clave de integración en el cuerpo.

## Análisis y consulta

- El portal principal llama a `analyze_sms` para SMS y notificaciones con texto; el análisis usa las reglas, extractores, dominios, patrones circulares y adaptador del motor ya existentes.
- Las llamadas conservan su tipo y se muestran sin análisis de texto.
- En `/mensajes` se pueden buscar coincidencias de texto, remitente, aplicación, dispositivo y explicación, y filtrar por tipo, app, dispositivo y fechas.
- El feed principal transmite por WebSocket y retiene solo los 200 eventos recientes en memoria. El monitor mantiene su propia persistencia, historial cifrado, búsqueda y análisis de riesgo. Reiniciar el portal limpia su feed temporal; la integración no copia a SQLite principal.
- El relay publica eventos de teléfonos que aceptaron la versión de consentimiento con la integración; no importa retrospectivamente el historial que ya existía en el monitor.
- El análisis se presenta como una señal orientativa para revisión humana. No confirma fraude ni abre enlaces.

## Operación y recuperación

El monitor guarda el evento antes de reenviarlo. Si el portal no responde, el endpoint del monitor devuelve `503`; Android conserva el evento pendiente y WorkManager lo reintenta. El monitor acepta el reintento duplicado y vuelve a intentar el relay; la aplicación principal ignora un `id_evento` que ya esté en su ventana de 200 eventos.

Para una demo, arranca primero el portal principal y después el servidor del monitor. Verifica que el endpoint principal sea accesible desde el equipo que ejecuta el monitor; por ejemplo, si el portal está dentro de Docker, el puerto publicado del host debe ser alcanzable en `127.0.0.1:8000`.

Usa solo teléfonos propios y mensajes sintéticos. El consentimiento del usuario del teléfono sigue siendo obligatorio y se conserva la selección explícita de apps del enrolamiento.
