# Aviso de privacidad del Monitor de teléfono

> **Borrador sujeto a revisión legal.** No constituye asesoría legal ni acredita por sí mismo el cumplimiento de la LFPDPPP u otra normativa. Antes de usar el sistema con datos personales, el responsable debe completar la información pendiente, determinar la base legal aplicable y publicar este aviso actualizado.

**Responsable del tratamiento:** [indicar persona o entidad, domicilio y contacto].  
**Fecha y versión:** [completar antes de publicar].

## Datos tratados

Cuando la persona propietaria de un teléfono acepta y activa el monitoreo, el servidor puede tratar:

- UUID del evento, tipo, aplicación de origen, remitente, texto y fecha/hora.
- Para eventos recibidos de otras integraciones: dirección y duración de una llamada. La app Android de este proyecto no recopila SMS, registros de llamadas, contactos ni audio.
- Nombre/etiqueta, aplicaciones autorizadas, estado y último contacto del dispositivo.
- Nivel de riesgo, puntaje, reglas y razones del análisis, estado de revisión y fecha de revisión.
- Hash del token de dispositivo, hash/caducidad del código temporal de enrolamiento y metadatos de operación.

Los textos pueden contener datos personales que el remitente incluya en la notificación. La persona dueña decide qué aplicaciones autoriza. La app no realiza llamadas ni envía mensajes.

## Finalidades y análisis antifraude

Los datos se usan para recibir eventos consentidos, detectar señales de fraude o suplantación, presentar advertencias al teléfono, habilitar revisión humana de alertas, proteger la cuenta/dispositivo, y permitir solicitudes de acceso, exportación, rectificación o borrado.

El detector asigna un puntaje de 0 a 100 y razones explicables mediante reglas y heurísticas. Un resultado no determina que exista fraude ni se usa por sí solo para tomar decisiones con efectos legales sobre una persona. Las alertas medias y altas se envían a una cola de revisión humana.

## Quién puede ver los datos

- **Administradores:** gestionan dispositivos, cuentas, enrolamientos, reglas y configuración; pueden consultar el feed, exportar o borrar datos y acceder a la bitácora.
- **Revisores:** por defecto ven solo mensajes marcados como posibles alertas y hasta tres mensajes previos del mismo remitente, con contexto mínimo. No tienen acceso al feed general ni a la lista de teléfonos.
- **Configuración ampliada:** si `REVISORES_VEN_TODO=true`, los revisores pueden consultar los textos de todos los eventos únicamente de teléfonos que aceptaron la versión de consentimiento que informa esa opción. Los demás dispositivos conservan el acceso limitado a alertas. La app muestra esta condición antes del consentimiento y cada consulta se registra en la bitácora.
- **Persona propietaria del teléfono:** puede consultar y exportar exclusivamente los eventos vinculados a su token de dispositivo y solicitar su borrado desde la app.

Las acciones de consulta de alertas, marcado, exportación y borrado quedan registradas en una bitácora de solo anexado. La bitácora identifica la cuenta o dispositivo que realizó la acción, la acción, los identificadores afectados y la fecha; no almacena el texto del mensaje.

## Consentimiento, retiro y desinstalación

El monitoreo solo debe activarse en teléfonos propios o con autorización expresa de su propietario. Antes de vincular, la app informa quién revisa, qué puede consultar, la retención y cómo retirar el consentimiento. No se envían notificaciones hasta que la persona acepta y habilita el monitoreo.

La persona puede pausar el monitoreo, revocar el acceso a notificaciones de Android, desvincular el dispositivo o desinstalar la app desde los ajustes del sistema. Desvincular detiene nuevos envíos y borra la configuración/cola local si el servidor confirma la revocación; no elimina automáticamente los datos que ya están en el servidor. La opción **Solicitar borrado de mis datos del servidor** borra y desvincula los datos de ese teléfono.

## Conservación, cifrado y respaldos

- Los textos de eventos de riesgo bajo se eliminan después de `RETENCION_TEXTO_NORMAL_HORAS` (24 horas por defecto); sus metadatos se conservan hasta `RETENCION_DIAS` (30 días por defecto).
- Los textos y datos de eventos clasificados como riesgo medio o alto se conservan hasta `RETENCION_ALERTAS_DIAS` (90 días por defecto), salvo que se eliminen antes por solicitud.
- Los códigos de enrolamiento vencen en 15 minutos, solo se pueden canjear una vez y el servidor conserva su hash, no el código.
- La app mantiene eventos pendientes en una cola local hasta su envío o borrado local. Borrar la copia local no borra los eventos ya recibidos por el servidor.
- La limpieza automática se ejecuta al arrancar y cada 24 horas. Los respaldos pueden conservar copias cifradas hasta `BACKUP_RETENTION_DAYS` (30 días por defecto), y deben incluirse en el proceso de borrado y rotación definido por el responsable.

El servidor cifra los textos de eventos en SQLite mediante Fernet. `DATA_ENCRYPTION_KEY` se guarda fuera del repositorio y debe respaldarse bajo controles separados. Perderla impide descifrar los datos existentes. El cifrado en reposo no protege frente a una cuenta de servidor comprometida mientras la clave está disponible en el proceso.

## Proveedor, transmisión y seguridad

En despliegues en la nube, los datos se alojan en el VPS y proveedor elegidos por quien administra el servicio. El tráfico Android y web debe usar HTTPS; Caddy termina TLS y reenvía al servidor por una red privada de Docker. El responsable debe identificar al proveedor, ubicación, encargados y condiciones aplicables.

El panel utiliza cuentas individuales, contraseñas con hash Argon2, bloqueo temporal por intentos fallidos, sesiones `HttpOnly`/`SameSite=Strict`, protección CSRF, cookies `Secure` bajo HTTPS y cabeceras CSP/HSTS. La app almacena su token protegido con Android Keystore. Ningún proxy o sistema de observabilidad debe registrar cuerpos HTTP, tokens, cookies, cabeceras de autorización, códigos de enrolamiento ni textos de mensajes.

La seguridad no elimina todos los riesgos. Un teléfono desbloqueado, una cuenta comprometida, una clave de cifrado expuesta o un respaldo accesible podrían revelar datos.

## Derechos ARCO y solicitudes

Para solicitar acceso, exportación, rectificación, cancelación, oposición, revocación del consentimiento o eliminación, contacta a **[completar nombre, correo y procedimiento del responsable]**. La persona propietaria puede exportar y borrar los datos asociados a su teléfono desde la app. Admin puede exportar o borrar los datos de un dispositivo desde el panel. El responsable debe verificar la identidad del solicitante y atender la solicitud conforme a la legislación aplicable, incluyendo el tratamiento de respaldos y registros de auditoría.

## Cambios

Este borrador debe actualizarse cuando cambien los datos, finalidades, roles, retención, infraestructura o personas con acceso. Publica una versión fechada antes de recolectar mensajes reales.
