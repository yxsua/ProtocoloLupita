# Monitor de teléfono

Servidor FastAPI independiente para recibir y consultar eventos que envían teléfonos Android propios, con consentimiento de sus usuarios. El servidor y la app Android viven íntegramente en `monitor_telefono/`: no importan ni modifican el módulo de voz de Protocolo Lupita.

El Android de esta fase envía únicamente notificaciones de las aplicaciones que la persona activa. No lee la base de SMS, contactos ni registros de llamadas, y no graba audio. El servidor admite también eventos `sms` y `llamada` de otros clientes, limitados al esquema de la API. Registrar un número o etiqueta no verifica su titularidad.

## Estructura

- `server/`: FastAPI, interfaz web, autenticación, SQLite, WebSocket y pruebas.
- `android/`: aplicación Kotlin con consentimiento, allowlist local de apps, cola offline y envío autenticado.
- `scripts/simular_telefono.py`: emite eventos ficticios para probar la API; no contacta teléfonos.
- `docs/`: [guía de instalación](docs/GUIA_INSTALACION.md), [aviso de privacidad](docs/AVISO_PRIVACIDAD.md) y [nota de integración futura](docs/INTEGRACION_LUPITA.md).

## Requisitos

- Python 3.10 o posterior.
- Windows PowerShell, o Linux/macOS con `sh`.
- Para compilar Android: Android Studio, JDK 17 y Android SDK Platform 35.

## Inicio rápido: Windows

Desde PowerShell, en esta carpeta:

```powershell
Copy-Item .env.example .env
notepad .env
```

Configura `SECRET_KEY` (clave de sesión aleatoria) y `DATA_ENCRYPTION_KEY` (clave Fernet para cifrar textos) en `.env`. Genéralas localmente:

```powershell
py -c "import secrets; print(secrets.token_hex(32))"
py -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Guarda la primera salida en `SECRET_KEY` y la segunda en `DATA_ENCRYPTION_KEY`. No cambies la clave de cifrado mientras haya datos cifrados. No uses valores de ejemplo ni compartas o subas `.env`. Crea la primera cuenta admin desde consola y luego inicia el servidor:

```powershell
.\server\run.ps1 -CreateAdmin
.\server\run.ps1
```

El script crea `server\.venv` si hace falta, instala `server\requirements.txt` y ejecuta Uvicorn en `127.0.0.1:8100` por defecto. El comando de creación pide usuario y contraseña; Argon2 almacena únicamente el hash. Los admins pueden crear cuentas revisoras desde el panel. Abre `http://127.0.0.1:8100` e inicia sesión. Para probar localmente usa el simulador; para vincular teléfonos desde Internet despliega primero HTTPS y usa **Dispositivos > Agregar teléfono** para generar el QR o enlace de un solo uso.

Ejecuta las pruebas del servidor desde la raíz de este proyecto:

```powershell
.\server\.venv\Scripts\python.exe -m pytest .\server\tests -q
```

## Inicio rápido: Linux/macOS

Desde esta carpeta, crea `.env` a partir de `.env.example`, configura `SECRET_KEY` y `DATA_ENCRYPTION_KEY`, crea la cuenta admin y ejecuta:

```sh
sh server/run.sh --create-admin
sh server/run.sh
```

El script crea `server/.venv`, instala las dependencias y escucha en `127.0.0.1:8100` por defecto. La suite del servidor se ejecuta con:

```sh
server/.venv/bin/python -m pytest server/tests -q
```

## Probar la recepción sin teléfono

Después de registrar un dispositivo en **Dispositivos**, guarda temporalmente su token en la variable de proceso `DEVICE_KEY` y ejecuta el simulador:

```powershell
$env:DEVICE_KEY = "PEGA_AQUI_EL_TOKEN"
.\server\.venv\Scripts\python.exe .\scripts\simular_telefono.py --repeat-first
Remove-Item Env:DEVICE_KEY
```

El simulador envía notificaciones, SMS y una llamada ficticios, incluidos comillas, saltos de línea y emojis; no inicia llamadas ni envía SMS. También verifica la idempotencia del primer evento. Para probar otro servidor, configura `MONITOR_URL` o usa `--url`; nunca incluyas el token en la URL.

## Variables de entorno

| Variable | Descripción | Valor predeterminado |
|---|---|---|
| `SECRET_KEY` | Clave de firma de sesiones, aleatoria y de al menos 32 caracteres. Obligatoria. | Sin valor; el servidor no arranca. |
| `DATA_ENCRYPTION_KEY` | Clave Fernet para cifrar textos de eventos en SQLite. Obligatoria; respáldala de forma segura. | Sin valor; el servidor no arranca. |
| `RETENCION_TEXTO_NORMAL_HORAS` | Horas hasta borrar el texto de eventos de riesgo bajo. | `24` |
| `RETENCION_ALERTAS_DIAS` | Días hasta borrar eventos de riesgo medio/alto. | `90` |
| `RETENCION_DIAS` | Días que se conservan los metadatos de eventos de riesgo bajo. | `30` |
| `PUERTO` | Puerto de escucha de Uvicorn. | `8100` |
| `DATABASE_PATH` | Ruta del archivo SQLite. | `server/data/monitor.sqlite3` |
| `EVENTOS_POR_MINUTO` | Límite de ingesta por dispositivo. | `120` |
| `BASE_URL_PUBLICA` | Origen HTTPS público admitido para WebSocket, sin ruta. | Vacío |
| `COOKIE_SECURE` | Fuerza `Secure` en la cookie; también se marca automáticamente bajo HTTPS. | `false` |
| `ANDROID_DOWNLOAD_URL` | URL HTTPS del APK release firmado ofrecido en la página de enrolamiento. | Vacío |
| `REVISORES_VEN_TODO` | Si es `true`, revisores pueden ver texto de todos los eventos; cada consulta se audita. | `false` |
| `RIESGO_UMBRAL_MEDIO` / `RIESGO_UMBRAL_ALTO` | Umbrales de riesgo para cola de revisión y alerta alta. | `40` / `70` |
| `REGLAS_FRAUDE_CSV` | Ruta del archivo CSV de reglas antifraude. | `server/data/reglas_fraude.csv` |
| `DOMAIN` | Dominio DNS publicado por Caddy en Docker. | Sin valor |
| `BACKUP_RETENTION_DAYS` | Días que se conservan respaldos diarios SQLite. | `30` |

El archivo `.env.example` contiene valores vacíos para los secretos. Define los valores reales solamente en el `.env` local, que está excluido por `.gitignore`. Protege y respalda `DATA_ENCRYPTION_KEY`: si se pierde o cambia, no será posible descifrar mensajes existentes. Detrás de un proxy HTTPS, define también `BASE_URL_PUBLICA` y `COOKIE_SECURE=true`; restringe Uvicorn para que solo confíe en el proxy que controlas.

## Android

Abre `android/` en Android Studio, instala JDK 17 y SDK Platform 35, sincroniza Gradle y compila la variante `debug`:

```powershell
cd android
.\gradlew.bat assembleDebug
```

Versiones: Android Gradle Plugin 8.7.3, Gradle 8.9, Kotlin 2.0.21 y JVM target 17; usa `compileSdk 35`, `targetSdk 35` y `minSdk 26`. En Linux/macOS, usa `./gradlew assembleDebug`. Consulta [android/README.md](android/README.md) para el lector QR, enrolamiento, permisos, firma y publicación.

El servidor release se fija en `BuildConfig` desde `MONITOR_SERVER_URL` o `-PmonitorServerUrl=...`; su reserva es `https://monitor.example.com`. En release la persona no puede cambiar la URL; en debug sí. Un teléfono real debe usar HTTPS. No abras ni reenvíes el puerto HTTP directamente a la LAN o a Internet.

## Enrolamiento automático Android

1. El administrador abre **Dispositivos > Agregar teléfono**, elige un nombre y apps sugeridas y genera el QR. El código vence en 15 minutos, solo se puede canjear una vez y queda protegido por un límite de cinco intentos fallidos por IP durante 15 minutos.
2. La persona instala la app desde el enlace oficial publicado por el administrador, escanea el QR con el lector integrado (sin permiso de cámara), abre el enlace profundo o escribe el código.
3. La app muestra el servidor, nombre y apps sugeridas. La persona puede editar nombre y selección, leer el aviso y debe aceptar expresamente antes de que el servidor entregue el token.
4. El token queda cifrado con Android Keystore y no se muestra en builds release. La app ofrece un asistente de acceso a notificaciones y batería, y envía un latido cada 15 minutos.
5. **Desvincular este teléfono** revoca el token en el servidor y, al confirmarlo, borra la clave y la cola local. Los eventos ya enviados permanecen en la nube hasta el borrado administrativo o la retención.

El panel marca **En línea** cuando el contacto ocurrió en los últimos 35 minutos y actualiza cada 30 segundos. Configura `ANDROID_DOWNLOAD_URL` con una URL HTTPS a un APK release firmado para mostrar descarga en la página pública.

## Despliegue en la nube

Se incluye Docker, Caddy para HTTPS automático, SQLite persistente y una tarea de respaldo diario. Sigue [docs/DESPLIEGUE_VPS.md](docs/DESPLIEGUE_VPS.md); la alternativa de piloto con Tailscale Funnel y sus riesgos está en [docs/PRUEBA_RAPIDA_FUNNEL.md](docs/PRUEBA_RAPIDA_FUNNEL.md).

En Ubuntu, prepara `.env` con el dominio, `BASE_URL_PUBLICA=https://tu-dominio`, `SECRET_KEY` y `DATA_ENCRYPTION_KEY` aleatorias. Crea la primera cuenta con `docker compose exec -it monitor python -m app.cli create-admin --username admin`; el comando solicita la contraseña. Después:

```sh
docker compose up -d --build
docker compose logs -f monitor caddy
```

La app no publica su puerto directamente; Caddy atiende 80/443 y reenvía al servidor. El volumen `monitor_data` conserva SQLite y los respaldos diarios van a `backups/`. El usuario final no necesita PC, VPN ni copiar tokens; necesita el APK firmado y el QR/enlace del panel.

Para compilar release con el dominio ya fijado, configura `MONITOR_SERVER_URL=https://tu-dominio` y ejecuta `assembleRelease`. Firma el APK antes de distribuirlo; un release sin firma no se debe ofrecer como instalador.

## Acceso de red y datos

Los scripts limitan Uvicorn a loopback. Para otros equipos, usa una VPN privada con salida HTTPS (por ejemplo, Tailscale Serve) o un proxy inverso TLS que reenvíe a `127.0.0.1:8100`; activa `COOKIE_SECURE=true`. No expongas el puerto HTTP directamente a la red. El Android release requiere HTTPS; HTTP debug se limita a loopback y al puente del emulador.

El detector analiza cada evento, devuelve riesgo de 0 a 100 y razones breves, y envía los niveles medio/alto a la cola revisora. Las reglas editables usan CSV con columnas `rule_id,kind,value,entity,score,reason,enabled`; `kind` admite `sender`, `domain`, `phrase`, `regex` y `entity`. Las cuentas revisoras solo ven alertas y hasta tres mensajes previos del mismo remitente, salvo que `REVISORES_VEN_TODO=true` se haya informado en el consentimiento; el acceso ampliado solo aplica a teléfonos que aceptaron esa versión del consentimiento. Los demás conservan la revisión limitada. El servidor cifra los textos en SQLite; limpia el texto normal después de 24 horas y elimina alertas después de 90 días por defecto. La búsqueda de texto de la interfaz envía el filtro en un cuerpo POST; configura también el proxy para no registrar cuerpos, credenciales, parámetros sensibles ni textos de mensajes. Protege el equipo servidor, las copias de seguridad y la clave de cifrado. Revisa el [aviso de privacidad](docs/AVISO_PRIVACIDAD.md) antes de usar datos reales.

## Aislamiento e integración

Este proyecto no importa ni modifica `/app`, ni el sistema de voz, Whisper o Piper. La posible integración futura está descrita, sin implementarla, en [INTEGRACION_LUPITA.md](docs/INTEGRACION_LUPITA.md).
