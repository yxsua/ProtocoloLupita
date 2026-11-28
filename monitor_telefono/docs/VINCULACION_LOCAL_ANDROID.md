# Vincular Android en una demostración estrictamente local

## Resultado del análisis

El flujo de enrolamiento sí puede vincular un teléfono físico sin exponer el servidor a la LAN o a Internet. Para eso se necesita la app **debug** y un cable USB con `adb reverse`: el Android accede a `http://localhost:8100` y ADB reenvía ese puerto al servidor de la laptop, que sigue escuchando solo en `127.0.0.1`.

No hay una brecha en los endpoints de enrolamiento que impida ese modo: la app debug admite HTTP para loopback, el servidor acepta el origen local y el alta se realiza con código de un solo uso. La brecha es operativa y documental: las guías existentes describen el enrolamiento con release/HTTPS y la prueba API con simulador, pero no el puente USB para un teléfono físico. Un teléfono conectado solo por Wi-Fi no podrá usar `localhost` de la laptop; la política Android también rechaza HTTP hacia una IP de LAN.

En el entorno revisado no se encontró `adb` ni `java` disponibles en `PATH`, ni un APK debug ya generado. Por tanto, el procedimiento queda documentado, pero aún se requiere instalar/configurar Android Platform Tools y JDK 17 (o Android Studio con su JDK), compilar el APK e identificar el teléfono por USB para efectuar la vinculación física.

## Qué comunica el flujo

1. El administrador crea en **Dispositivos > Agregar teléfono** un código de enrolamiento. El servidor guarda su hash, limita intentos y el código caduca en 15 minutos o al primer uso.
2. La app valida el código con `POST /api/enrolar/preview` y presenta nombre, apps sugeridas y consentimiento.
3. Tras aceptar, Android envía `POST /api/enrolar`; el servidor registra el equipo y devuelve el token de dispositivo una sola vez.
4. La app cifra el token con Android Keystore, programa un latido y continúa con el permiso de acceso a notificaciones y la configuración de monitoreo.
5. El latido y los eventos usan `X-Device-Key`. Con `adb reverse` también cruzan únicamente el cable USB y el loopback local.

## Preparación antes de desconectar Internet

El día de la demo, la conexión entre Android y el servidor no requiere Internet. Para una demo completamente offline, prepara con anticipación las herramientas y sus dependencias: Python/paquetes del servidor, JDK 17, Android SDK Platform 35, Gradle y dependencias Android. Compila e instala el APK antes de desconectar Internet. El lector QR depende de Google Play Services; en un teléfono offline o sin ese servicio, introduce el código corto manualmente.

Usa un teléfono propio/de prueba y apps con notificaciones sintéticas. No uses mensajes personales.

## Pasos de vinculación local por USB

Desde PowerShell, abre una terminal en `monitor_telefono`.

1. Prepara `.env` a partir de `.env.example`. Define `SECRET_KEY` aleatoria de al menos 32 caracteres y una clave Fernet válida en `DATA_ENCRYPTION_KEY`; no dejes secretos vacíos. Deja `BASE_URL_PUBLICA` vacío. No configures `0.0.0.0`, Funnel ni un proxy público.

2. Crea la cuenta local una sola vez y arranca el servidor:

   ```powershell
   .\server\run.ps1 -CreateAdmin
   .\server\run.ps1
   ```

   El servidor queda en `127.0.0.1:8100`. En la laptop abre `http://127.0.0.1:8100`, inicia sesión y deja abierta la pantalla **Dispositivos**.

3. En Android activa **Opciones para desarrolladores > Depuración USB**, conecta el teléfono y acepta la huella RSA de esta laptop. Comprueba que ADB lo ve:

   ```powershell
   adb devices
   ```

4. Crea el puente USB sin cambiar la interfaz de escucha del servidor:

   ```powershell
   adb reverse tcp:8100 tcp:8100
   adb reverse --list
   ```

   Si hay más de un dispositivo, selecciona el serial con `adb -s <serial> reverse tcp:8100 tcp:8100` y usa el mismo `-s` en los comandos ADB siguientes. Conserva el cable conectado y el servidor activo durante la demo.

5. Desde la carpeta `monitor_telefono`, compila e instala la variante debug:

   ```powershell
   .\android\gradlew.bat assembleDebug
   adb install -r .\android\app\build\outputs\apk\debug\app-debug.apk
   ```

   Abre **Monitor de teléfono** en Android. En el campo **URL del servidor (solo debug)** escribe `http://localhost:8100`.

6. En el panel local pulsa **Agregar teléfono**, captura un nombre y selecciona apps sintéticas/de prueba. Pulsa **Generar QR y código**. En Android introduce el código de 8 caracteres y pulsa **Continuar con el código**. El QR puede usarse con el lector integrado si Google Play Services está disponible; la entrada manual evita esa dependencia y sigue siendo el camino recomendado para una demo offline.

7. Comprueba que la app muestra el nombre y las apps esperadas. Acepta el aviso y pulsa **Aceptar y vincular teléfono**. El código no se puede volver a utilizar. El token queda guardado de forma cifrada; no lo copies ni lo registres en capturas.

8. Completa los permisos locales que solicita Android para habilitar el monitoreo. El registro del teléfono y el primer latido deben aparecer en **Dispositivos**. Activa una notificación sintética de una app autorizada y confirma que llega al feed. Para validar solo el vínculo, basta con confirmar el dispositivo y el latido; el permiso especial de notificaciones corresponde a la captura de eventos, no al canje del código.

9. Al terminar, usa **Desvincular teléfono y borrar datos locales** y confirma que el dispositivo deja de enviar. Detén el servidor con `Ctrl+C` y elimina el puente:

   ```powershell
   adb reverse --remove tcp:8100
   ```

   El borrado local no elimina automáticamente eventos que ya llegaron a la base del servidor; limpia los registros de demo desde el panel o elimina la base local si ya no se necesita.

## Diagnóstico rápido

| Síntoma | Causa probable / acción |
|---|---|
| `adb devices` no muestra `device` | Falta Platform Tools, el cable no transporta datos o no se aceptó la autorización USB. |
| La app informa que HTTP solo se permite en loopback | Usa exactamente `http://localhost:8100`; la variante instalada debe ser debug. No uses la IP Wi-Fi de la laptop. |
| No se puede conectar o validar el código | Confirma que Uvicorn sigue activo en `127.0.0.1:8100`, que `adb reverse --list` muestra el puerto y que el teléfono permanece conectado por USB. |
| Código inválido, caducado o usado | Genera otro desde el panel; dura 15 minutos y solo se canjea una vez. |
| El QR no abre el lector | Escribe el código manualmente. El uso del QR no es requisito para vincular. |
| El dispositivo aparece, pero no llegan notificaciones | Completa el acceso especial a notificaciones de Android, permite notificaciones de la app y confirma que el paquete origen está autorizado. |

## Límites

- El flujo anterior es para desarrollo y demostración local con build debug. No distribuyas ese APK como release.
- El método USB mantiene el backend solo en loopback. No sustituye una ruta HTTPS para teléfonos remotos o conectados por Wi-Fi.
- Si se necesita una demostración inalámbrica, hace falta configurar una ruta privada con HTTPS; no basta con cambiar el servidor a `0.0.0.0`.
