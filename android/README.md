# Bridge Android de Protocolo Lupita

El bridge envía notificaciones visibles, SMS entrantes y nuevos registros de
llamada al backend. No graba audio, no mantiene una copia local de los eventos
y no lee SMS antiguos. Las llamadas se detectan al escribirse en el registro
del teléfono; por ello se informan al terminar, con sentido y duración.

La app muestra una explicación antes de solicitar permisos. Activa solo estas
fuentes en teléfonos propios y con autorización de sus usuarios.

## Dependencia

En el `build.gradle.kts` del módulo Android:

```kotlin
dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
```

## Configuración privada para BuildConfig

El archivo `local.properties` del proyecto Android (ignorado por Git) puede
contener:

```properties
LUPITA_BASE_URL=http://192.168.1.25:8000
LUPITA_DEVICE_KEY=pega_aqui_la_misma_clave_del_servidor
LUPITA_DEVICE_ID=tel-01
```

Añade al `build.gradle.kts` del módulo. Si tu Android `namespace` no es
`com.example.lupita`, cambia también el `package` de `NotificationBridge.kt`:

```kotlin
import java.util.Properties

val bridgeProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.isFile) file.inputStream().use { load(it) }
}
fun bridgeValue(name: String, fallback: String) =
    bridgeProperties.getProperty(name, fallback).replace("\\", "\\\\").replace("\"", "\\\"")

android {
    buildFeatures {
        buildConfig = true
    }
    defaultConfig {
        buildConfigField("String", "LUPITA_BASE_URL", "\"${bridgeValue("LUPITA_BASE_URL", "http://10.0.2.2:8000")}\"")
        buildConfigField("String", "LUPITA_DEVICE_KEY", "\"${bridgeValue("LUPITA_DEVICE_KEY", "")}\"")
        buildConfigField("String", "LUPITA_DEVICE_ID", "\"${bridgeValue("LUPITA_DEVICE_ID", "tel-01")}\"")
    }
}
```

`10.0.2.2` solo funciona desde el emulador Android hacia el equipo anfitrión.
En un teléfono físico configura la IP local del equipo que ejecuta Uvicorn y
asegúrate de que ambos estén en una red confiable. Usa HTTPS fuera de pruebas
locales. Una clave incluida en un APK puede extraerse; usa una clave única por
dispositivo y rótala si distribuyes el APK.

## Manifiesto

Dentro de `<manifest>`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.RECEIVE_SMS" />
<uses-permission android:name="android.permission.READ_CALL_LOG" />
```

Dentro de `<application>`:

```xml
<activity
    android:name=".MainActivity"
    android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
    </intent-filter>
</activity>

<service
    android:name=".NotificationBridge"
    android:exported="true"
    android:label="Protocolo Lupita"
    android:permission="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE">
    <intent-filter>
        <action android:name="android.service.notification.NotificationListenerService" />
    </intent-filter>
</service>

<receiver
    android:name=".SmsReceiver"
    android:exported="true"
    android:permission="android.permission.BROADCAST_SMS">
    <intent-filter>
        <action android:name="android.provider.Telephony.SMS_RECEIVED" />
    </intent-filter>
</receiver>
```

Para pruebas HTTP locales, Android puede requerir
`android:usesCleartextTraffic="true"` en `<application>`. No habilites tráfico
HTTP sin cifrar para despliegues reales.

## Activar en el teléfono

Instala y abre la app. Pulsa **Continuar y revisar permisos** y acepta o rechaza
individualmente el acceso a SMS entrantes y al registro de llamadas. Después
activa manualmente **Ajustes → Notificaciones → Acceso a notificaciones →
Protocolo Lupita** (la ruta depende del fabricante).

- `RECEIVE_SMS`: el bridge recibe y reenvía el remitente, el texto y la fecha
  de SMS entrantes; no consulta la bandeja histórica.
- `READ_CALL_LOG`: observa nuevas filas, limitado a las 100 más recientes por
  escaneo. Al conectar, marca las filas existentes como vistas y no las envía.
  Los nuevos registros incluyen número si está disponible, app de teléfono,
  dirección conocida, fecha y duración.
- Acceso a notificaciones: recibe texto visible de aplicaciones distintas a
  SMS y llamadas, que se envían como `notificacion`.

Si un permiso se deniega, esa fuente no se envía. Si falla la red, el evento se
descarta y queda un error en Logcat; no hay cola local ni reintento persistente.
La duración de llamadas requiere que Android escriba la fila del registro, así
que no es una transmisión mientras la llamada sigue activa.

## Límites de compilación

Este repositorio solo incluye los fuentes Android, no un proyecto Gradle ni
Android SDK. Copia estos Kotlin y los bloques anteriores a un proyecto Android
con `namespace = "com.example.lupita"` (o ajusta los `package`/`BuildConfig`).
La app necesita un `targetSdk` compatible con los permisos runtime de Android.
