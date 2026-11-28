# Monitor de teléfono para Android

Aplicación Kotlin del monitor. Requiere Android Studio, JDK 17 y Android SDK Platform 35. Usa Android Gradle Plugin 8.7.3, Gradle 8.9, Kotlin 2.0.21, `compileSdk`/`targetSdk` 35, `minSdk` 26 y JVM target 17.

## Abrir y compilar

1. Abre Android Studio y selecciona **Open** en esta carpeta `monitor_telefono/android`.
2. Sincroniza Gradle e instala SDK Platform 35 y Build Tools desde SDK Manager.
3. Para compilar debug en Windows:

   ```powershell
   .\gradlew.bat assembleDebug
   .\gradlew.bat testDebugUnitTest
   ```

   En Linux/macOS:

   ```sh
   ./gradlew assembleDebug
   ./gradlew testDebugUnitTest
   ```

4. El APK debug se crea en `app/build/outputs/apk/debug/app-debug.apk`. HTTP se permite solo en debug para loopback y el emulador Android.

## URL del servidor y build release

La URL se incluye en `BuildConfig.DEFAULT_SERVER_URL`. El valor de reserva (`https://monitor.example.com`) es ilustrativo; release debe compilarse apuntando al dominio real. Desde PowerShell:

```powershell
$env:MONITOR_SERVER_URL = "https://monitor.tudominio.mx"
.\gradlew.bat assembleRelease
```

También se puede usar `-PmonitorServerUrl=https://monitor.tudominio.mx`. En debug el campo de URL es editable; en release queda fijado al valor del build y se rechazan códigos de un dominio diferente. Release requiere HTTPS.

Genera un APK **firmado** desde Android Studio > **Build > Generate Signed Bundle / APK**. Guarda el keystore y contraseñas en un gestor seguro fuera del repositorio. Copia el APK firmado al directorio `monitor_telefono/downloads/` del servidor, y configura `ANDROID_DOWNLOAD_URL` con la URL HTTPS publicada por Caddy antes de compartirla.

## Vincular un teléfono

1. El administrador crea un enrolamiento desde el panel web **Dispositivos > Agregar teléfono**. Comparte el QR o enlace; el código corto vence en 15 minutos y solo se usa una vez.
2. En la app, escanea el QR con Google Play Services Code Scanner, abre el deep link `monitortelefono://enroll`, o introduce el código a mano. El lector integrado no solicita permiso de cámara.
3. Revisa el nombre y la selección de aplicaciones sugeridas. Puedes cambiar el nombre, marcar/desmarcar apps y aceptar el consentimiento explícito; la app no envía notificaciones antes de aceptar y activar el monitoreo.
4. El servidor entrega el token una sola vez. La app lo guarda cifrado con Android Keystore y no lo muestra ni requiere copiarlo.
5. El asistente abre Ajustes para acceso a notificaciones y optimización de batería, detecta el regreso y continúa. Si Android 13+ bloquea el permiso por instalación fuera de Play, abre Información de la app > ⋮ > **Permitir ajustes restringidos** y vuelve a activar el acceso.
6. La app envía un latido cada 15 minutos. WorkManager conserva tareas al reiniciar, reintenta eventos con la red y el servicio vuelve a solicitar `requestRebind` si Android desconecta el listener.
7. **Desvincular teléfono y borrar datos locales** avisa al servidor para revocar el token y después borra la configuración cifrada, cola e historial local. Los eventos recibidos por el servidor no se eliminan automáticamente.

## Datos y permisos

- Solo se procesan notificaciones de las aplicaciones que la persona elige. Las apps sugeridas por el administrador aparecen seleccionadas y son editables.
- El permiso de notificaciones especial se activa manualmente en Android; `POST_NOTIFICATIONS` se solicita para mostrar el indicador permanente.
- No pide permiso de cámara, contactos, micrófono, lectura de SMS ni registros de llamadas. No graba audio.
- Configuración y token se cifran mediante Android Keystore. Eventos pendientes y cursores de deduplicación se guardan localmente en Room.
- Solo una aceptación expresa habilita el alta en el servidor; el monitoreo empieza después de conceder los permisos y activar la captura.

La operación de VPS, descarga y respaldo se describe en [../docs/DESPLIEGUE_VPS.md](../docs/DESPLIEGUE_VPS.md).
