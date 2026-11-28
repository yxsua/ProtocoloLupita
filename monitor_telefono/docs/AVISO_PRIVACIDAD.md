# Aviso de privacidad del Monitor de teléfono

> **Borrador para revisión.** Este documento es informativo, no constituye asesoría legal ni acredita por sí mismo el cumplimiento de la LFPDPPP u otra normativa. Antes de usar el sistema con datos personales, el responsable debe completar los datos de contacto, definir las condiciones del tratamiento y obtener asesoría legal aplicable.

**Responsable del tratamiento:** [indicar persona o entidad responsable y domicilio/contacto].  
**Fecha y versión:** [completar antes de publicar].

## Datos que pueden tratarse

Cuando un dispositivo autorizado envía un evento, el servidor puede recibir y almacenar los campos de su API:

- UUID del evento, identificador y nombre/etiqueta del dispositivo.
- Tipo de evento, nombre de paquete de la aplicación de origen y fecha/hora.
- Remitente y texto de una notificación o mensaje.
- Si otro cliente envía un evento de llamada: dirección y duración. La app Android incluida en este proyecto no recopila registros ni metadatos de llamadas.
- Fecha de recepción, último contacto, estado del dispositivo y hash del token de dispositivo.
- Durante la vinculación: hash del código temporal, nombre sugerido, aplicaciones sugeridas, estado y vencimiento del enrolamiento. El código temporal vence en 15 minutos; el token del dispositivo se entrega una sola vez y el servidor conserva solo su hash.

La etiqueta del dispositivo puede contener un número telefónico, pero no se verifica su titularidad. El token original se muestra al registrarlo; el servidor conserva su hash. La app Android almacena localmente la configuración cifrada y una cola de los eventos autorizados pendientes de envío. Su sistema operativo entrega notificaciones a un servicio con acceso especial; la app aplica la selección explícita de aplicaciones antes de guardar y enviar eventos.

Los mensajes podrían contener datos personales o información sensible que sus remitentes incluyan en la notificación. El usuario del teléfono debe considerar esto al decidir qué aplicaciones compartir. No se graban llamadas, no se captura audio y la app no solicita acceso a contactos, base de SMS o registros de llamadas.

## Finalidades

Los datos se tratan para:

1. Recibir y mostrar en tiempo real notificaciones compartidas voluntariamente por teléfonos autorizados.
2. Mantener una cola local cuando no hay conexión y reintentar su entrega.
3. Autenticar dispositivos, identificar su origen, evitar duplicados, limitar abuso y mantener el servicio.
4. Permitir al administrador buscar, filtrar, revocar dispositivos y borrar eventos.

No se deben utilizar los eventos para contactar a remitentes, tomar decisiones automatizadas sobre personas ni integrarlos con otros sistemas sin definir una finalidad, consentimiento y controles separados.

## Consentimiento, acceso y revocación

El uso se limita a teléfonos propios o a aquellos cuyos usuarios hayan recibido información clara y dado consentimiento expreso antes de activar la captura. La persona puede desactivar el monitoreo o revocar el consentimiento desde la app, retirar el acceso a notificaciones en Android y pedir al administrador que revoque el dispositivo y borre los eventos correspondientes.

El acceso web requiere la contraseña local del monitor. Quien administra el servidor puede consultar los mensajes almacenados; debe restringir el acceso a personas autorizadas y proteger las credenciales.

## Conservación, respaldo y eliminación

El servidor conserva los mensajes y demás eventos hasta que el administrador los borre manualmente o venza `RETENCION_DIAS` (30 días por defecto). La limpieza automática se ejecuta al arrancar y cada 24 horas. El administrador puede eliminar eventos de un dispositivo al eliminar su registro o borrar todos los eventos desde el panel.

El botón **Desvincular este teléfono** revoca el token para impedir nuevos envíos y elimina el token cifrado, la cola y el historial local del teléfono. **No borra los mensajes que ya llegaron al servidor**: se mantienen hasta el borrado administrativo o la retención automática. Para ejercer una solicitud de borrado, contacta al responsable y solicita que elimine los eventos del dispositivo o todos los eventos que correspondan.

El despliegue Docker crea respaldos diarios consistentes de SQLite en `backups/` y conserva `BACKUP_RETENTION_DAYS` días (30 por defecto); después, los archivos locales vencidos se eliminan automáticamente. El responsable debe proteger ese directorio como datos personales, definir si existe una copia externa, cuánto tiempo se conserva y cómo se elimina de forma segura. Un respaldo externo no se borra al eliminar la base activa, salvo que el operador aplique también su política de rotación.

La cola del Android conserva los eventos pendientes mientras no se entreguen o se borren desde la app. Eliminar datos del servidor no borra automáticamente la cola del teléfono; borrar la cola del teléfono no elimina eventos ya recibidos por el servidor. Los códigos de enrolamiento expiran a los 15 minutos y solo se canjean una vez; sus hashes y metadatos se eliminan al vencer `RETENCION_DIAS`.

## Encargados, transmisión y seguridad

En el despliegue de nube descrito en este proyecto, los mensajes se transmiten por HTTPS y quedan almacenados en una base SQLite persistente en el VPS que elija quien administra. El proveedor de VPS puede procesar datos técnicos de conexión y almacenamiento según su contrato, ubicación y configuración. Caddy termina TLS y reenvía tráfico al servidor por una red privada de Docker. El administrador debe identificar al proveedor y la ubicación del servicio antes de publicar este aviso.

En el despliegue Docker, solo Caddy publica puertos; agrega TLS automático, HSTS y cookies `Secure`. El panel limita los intentos de contraseña y el enrolamiento limita intentos fallidos por IP. La interfaz envía búsquedas de texto en un cuerpo POST y el middleware redacta `texto`, `key` y `code` de las URL antes del log de acceso de Uvicorn. Cualquier proxy debe configurarse para omitir cuerpos de solicitudes, tokens, cabeceras de autorización y parámetros sensibles. No se deben incluir tokens, códigos de enrolamiento ni textos de mensajes en logs, capturas, tickets o repositorios.

Ninguna medida elimina todos los riesgos: la pérdida de un teléfono, una contraseña comprometida, permisos concedidos por error o respaldos expuestos podrían revelar mensajes.

## Derechos y contacto

Para solicitudes de acceso, rectificación, cancelación u oposición (ARCO), revocación del consentimiento o dudas sobre los datos, contacta a **[completar nombre, correo y procedimiento del responsable]**. El responsable debe verificar la identidad del solicitante y responder conforme a la legislación aplicable. No se debe publicar el contenido de mensajes al presentar una solicitud.

## Cambios

Este borrador debe actualizarse cuando cambien los campos, las finalidades, la infraestructura, la retención o las personas con acceso. Publica una versión fechada antes de habilitar el tratamiento real.
