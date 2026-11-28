# Guía de instalación y operación

Esta guía cubre el servidor FastAPI y la app Android de `monitor_telefono/`. Usa el sistema solo con teléfonos propios y con consentimiento expreso de sus usuarios. El flujo no verifica números telefónicos.

## 1. Preparar secretos

Desde la carpeta `monitor_telefono`, copia la plantilla:

### Windows PowerShell

```powershell
Copy-Item .env.example .env
notepad .env
```

### Linux/macOS

```sh
cp .env.example .env
${EDITOR:-nano} .env
```

Define una clave aleatoria de sesión en `SECRET_KEY` y una clave Fernet en `DATA_ENCRYPTION_KEY`. Genera ambas localmente:

```powershell
py -c "import secrets; print(secrets.token_hex(32))"
py -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

Guarda las salidas en `SECRET_KEY` y `DATA_ENCRYPTION_KEY`, respectivamente. Respalda la clave Fernet: perderla impide descifrar los textos existentes. No pongas secretos en código, argumentos que queden en el historial, capturas o repositorios. `.env` está excluido por `.gitignore`; limita el acceso al equipo donde se almacena.

## 2. Instalar y arrancar el servidor

Python 3.10 o posterior es necesario. Los scripts crean el entorno virtual local, instalan `server/requirements.txt` y arrancan Uvicorn.

En PowerShell, desde `monitor_telefono`:

```powershell
.\server\run.ps1 -CreateAdmin
.\server\run.ps1
```

En Linux/macOS, desde `monitor_telefono`:

```sh
sh server/run.sh --create-admin
sh server/run.sh
```

El puerto predeterminado es `8100`; se puede cambiar con `PUERTO` en `.env`. Los scripts escuchan únicamente en `127.0.0.1`, habilitan `--proxy-headers` y solo confían en cabeceras reenviadas desde ese loopback. No es necesario abrir el puerto 8100 en el firewall. No cambies el host a `0.0.0.0` ni expongas HTTP directamente a otros equipos.

El primer comando solicita el nombre y la contraseña del admin y guarda el hash Argon2; ejecútalo una sola vez. Luego abre `http://127.0.0.1:8100` e inicia sesión con esa cuenta. Admin puede crear cuentas revisoras desde el panel. `/api/salud` es un endpoint sin datos de eventos. Para que otros equipos accedan, configura Tailscale Serve o un proxy TLS que reenvíe a `http://127.0.0.1:8100`; define `BASE_URL_PUBLICA` con el origen HTTPS externo y `COOKIE_SECURE=true` en `.env`. La cookie se marca `Secure` cuando Uvicorn reconoce `X-Forwarded-Proto: https`.

## 3. Generar un enrolamiento y probar el servidor

1. En la interfaz web, abre **Dispositivos > Agregar teléfono**, elige un nombre sugerido y las aplicaciones que se mostrarán en el teléfono y pulsa **Generar QR y código**.
2. El QR contiene el origen HTTPS y un código aleatorio de ocho caracteres. El código vence en 15 minutos, solo se puede canjear una vez y el servidor almacena únicamente su hash. Después de cinco intentos fallidos desde una misma IP, esa IP queda bloqueada temporalmente.
3. La persona abre el enlace desde Android, escanea el QR con la app (no requiere permiso de cámara) o introduce el código a mano. La app muestra el nombre y las apps sugeridas, permite editarlos y no envía notificaciones hasta que se acepta el consentimiento y se activa el monitoreo.
4. El token permanente se entrega solo a la app, queda cifrado con Android Keystore y no se muestra para copiar. Si el código caduca o se usa, genera uno nuevo desde el panel.
5. Para comprobar la API con el simulador, el alta manual heredada todavía está disponible en **Dispositivos**; úsala solo para pruebas y no para los teléfonos finales. Pasa el token de esa integración temporal por variable de entorno y no por URL:

   ```powershell
   $env:DEVICE_KEY = "PEGA_AQUI_EL_TOKEN"
   .\server\.venv\Scripts\python.exe .\scripts\simular_telefono.py --repeat-first
   Remove-Item Env:DEVICE_KEY
   ```

   En Linux/macOS:

   ```sh
   DEVICE_KEY='PEGA_AQUI_EL_TOKEN' server/.venv/bin/python scripts/simular_telefono.py --repeat-first
   ```

   Los datos del simulador son ficticios; no contacta teléfonos. Confirma los eventos en el feed y la respuesta idempotente del duplicado.
6. Ejecuta las pruebas del servidor:

   ```powershell
   .\server\.venv\Scripts\python.exe -m pytest .\server\tests -q
   ```

   En Linux/macOS:

   ```sh
   server/.venv/bin/python -m pytest server/tests -q
   ```

## 4. Compilar e instalar Android

### Instalar JDK 17

Instala un JDK 17 de 64 bits (por ejemplo, Eclipse Temurin 17). En Windows, desde PowerShell, configura `JAVA_HOME` para esta terminal y verifica la versión:

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.x-hotspot"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
```

La salida debe indicar Java 17. En Android Studio también puedes elegir JDK 17 en **Settings > Build, Execution, Deployment > Build Tools > Gradle > Gradle JDK**. No uses Java 8 ni el JBR 25 de Android Studio para este build.

### Instalar Android SDK Platform 35

En Android Studio abre **Tools > SDK Manager > SDK Platforms**, activa **Android 15 / API 35** y aplica los cambios. En **SDK Tools**, instala Android SDK Build-Tools y Platform-Tools. Configura la ruta SDK que muestra SDK Manager, por ejemplo:

```powershell
$env:ANDROID_SDK_ROOT = "$env:LOCALAPPDATA\Android\Sdk"
```

Abre la carpeta `monitor_telefono/android` en Android Studio, permite la sincronización de Gradle y selecciona la variante `debug`. El proyecto usa compile/target SDK 35, min SDK 26, Android Gradle Plugin 8.7.3, Gradle 8.9, Kotlin 2.0.21 y JVM target 17.

### Compilar e instalar

Compila desde PowerShell:

```powershell
cd android
.\gradlew.bat assembleDebug
```

O desde Linux/macOS:

```sh
cd android
./gradlew assembleDebug
```

El APK debug, si el build finaliza correctamente, queda en `app/build/outputs/apk/debug/app-debug.apk`. Se puede instalar desde Android Studio o con un dispositivo conectado y depuración USB activada:

```powershell
adb install -r .\app\build\outputs\apk\debug\app-debug.apk
```

Para distribuirlo fuera de Play, genera un **APK release firmado** desde Android Studio. Define `MONITOR_SERVER_URL=https://tu-dominio` (o `-PmonitorServerUrl=https://tu-dominio`) al compilar: la URL queda integrada en `BuildConfig` y no se puede cambiar en release. Protege la clave de firma fuera del repositorio. El escáner usa Google Play Services Code Scanner y no declara permiso de cámara; si el servicio no está disponible, se puede escribir el código corto.

## 5. Configurar permisos y terminar la vinculación

1. Instala el APK release firmado en un teléfono propio. El administrador debe haberlo compilado con el mismo origen HTTPS que usa el servidor.
2. Escanea el QR, abre el enlace recibido o escribe el código. Revisa el nombre, las aplicaciones sugeridas y el servidor que muestra la app.
3. Edita las aplicaciones que compartirás y acepta expresamente el aviso de privacidad. Antes de aceptar, la app no envía datos de notificaciones ni registra el teléfono en el servidor.
4. El asistente abre la pantalla de acceso a notificaciones. Activa el permiso y vuelve a la app: detecta el cambio y continúa con el paso de batería. También valida las notificaciones necesarias para mostrar el indicador permanente.
5. Si Android 13+ muestra **Permitir ajustes restringidos** para una instalación fuera de Play, abre la información de la app, toca ⋮ > **Permitir ajustes restringidos**, vuelve a activar el acceso a notificaciones y regresa al asistente.
6. Al terminar el flujo, la app activa el monitoreo. Comprueba el indicador persistente, el evento en el feed, el estado del teléfono y el último contacto. Se envía un latido cada 15 minutos; el panel actualiza En línea/Sin conexión cada 30 segundos y considera en línea un contacto de los últimos 35 minutos.
7. El botón **Desvincular teléfono y borrar datos locales** avisa al servidor para revocar el token y después borra token cifrado, cola e historial local. No elimina eventos ya enviados; el administrador debe borrarlos desde el panel o esperar su retención.

La integración no verifica la titularidad de un número por SMS o llamada. El cliente Android no lee la base de SMS, contactos ni registros de llamadas, y no graba audio.

## 6. Publicar el servicio

**Producción recomendada:** VPS Ubuntu, DNS propio, Docker Compose y Caddy con HTTPS automático. Sigue [DESPLIEGUE_VPS.md](DESPLIEGUE_VPS.md). No publiques el puerto 8100.

**Piloto:** Tailscale Funnel puede exponer el servicio temporalmente; no es una VPN privada. Sigue [PRUEBA_RAPIDA_FUNNEL.md](PRUEBA_RAPIDA_FUNNEL.md) y no uses mensajes reales ni cuentas de producción durante el piloto.

Para un proxy HTTPS local, el origen debe usar HTTPS y `BASE_URL_PUBLICA` debe coincidir. Ejemplo:

   ```dotenv
   BASE_URL_PUBLICA=https://monitor.tudominio.mx
   COOKIE_SECURE=true
   ```

Reinicia el servidor para aplicar el entorno. Configura el proxy para no registrar cuerpos, tokens, códigos ni textos; nunca reenvíes HTTP directamente a la LAN o Internet.

## 7. Retención y mantenimiento

Los textos de riesgo bajo se eliminan después de `RETENCION_TEXTO_NORMAL_HORAS` (24 horas por defecto); sus metadatos se conservan hasta `RETENCION_DIAS` (30 días). Alertas medias/altas se conservan hasta `RETENCION_ALERTAS_DIAS` (90 días). En Docker, SQLite persiste en `monitor_data`; se crean respaldos consistentes diarios en `backups/` y se rotan con `BACKUP_RETENTION_DAYS` (30 días por defecto). Los respaldos contienen mensajes cifrados con `DATA_ENCRYPTION_KEY`; limita su acceso y cifra copias externas.

Para retirar consentimiento, pausa o desvincula el teléfono desde Android. La app incluye **Solicitar borrado de mis datos del servidor**, además de exportación propia autenticada. Admin también puede exportar o borrar datos por dispositivo; estas acciones quedan en auditoría. La eliminación es definitiva. La limpieza del servidor no borra automáticamente la cola offline, ni viceversa.
