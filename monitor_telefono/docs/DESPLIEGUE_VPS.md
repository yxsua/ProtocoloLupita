# Despliegue en VPS Ubuntu con HTTPS automático

Guía para publicar el panel en un VPS Ubuntu 22.04/24.04 con dominio propio. El usuario del teléfono solo instala el APK firmado, escanea el QR, revisa las aplicaciones y acepta el consentimiento. No se necesita Tailscale, PC ni copiar tokens en el teléfono.

## 1. Dominio, DNS y firewall

1. Reserva un VPS con una dirección IPv4 pública y, si usas IPv6, una IPv6 estable.
2. Crea un registro DNS `A` para `monitor.tudominio.mx` que apunte a la IPv4. Crea un `AAAA` solo si el VPS tiene IPv6 funcional.
3. En el firewall del proveedor y del VPS permite SSH desde tus direcciones administrativas y TCP `80`, TCP `443` y UDP `443` desde Internet. No abras el puerto `8100`.

En Ubuntu, restringe SSH a tu red cuando sea posible:

```sh
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
sudo ufw status
```

Docker administra las reglas de publicación de puertos. No publiques ningún puerto del contenedor `monitor`; solo Caddy debe ser accesible desde Internet.

## 2. Instalar Docker Compose

Instala Docker Engine y el plugin oficial Docker Compose siguiendo la documentación de Docker para tu versión de Ubuntu. Verifica:

```sh
docker --version
docker compose version
```

Clona o copia únicamente este directorio al VPS y entra en él:

```sh
cd monitor_telefono
cp .env.example .env
mkdir -p downloads backups
chmod 700 backups
```

No guardes `.env`, claves de firma Android ni respaldos en un repositorio público.

## 3. Variables y secretos

Genera secretos nuevos en el VPS:

```sh
openssl rand -hex 32
openssl rand -hex 32
```

Edita `.env` y asigna:

```dotenv
MONITOR_PASSWORD=una-contraseña-larga-y-única
SECRET_KEY=pega-aquí-el-segundo-valor-aleatorio
DOMAIN=monitor.tudominio.mx
BASE_URL_PUBLICA=https://monitor.tudominio.mx
RETENCION_DIAS=30
ANDROID_DOWNLOAD_URL=https://monitor.tudominio.mx/downloads/monitor-app.apk
BACKUP_RETENTION_DAYS=30
```

`MONITOR_PASSWORD` protege el panel; cinco errores desde una IP activan un bloqueo temporal de 15 minutos. `SECRET_KEY` debe tener al menos 32 caracteres aleatorios. Caddy solicita y renueva TLS automáticamente cuando DNS y los puertos públicos están correctos. FastAPI marca la cookie `Secure` y HSTS se activa para solicitudes HTTPS.

Si todavía no publicaste el APK firmado, deja `ANDROID_DOWNLOAD_URL` vacío. El enlace de descarga aparecerá cuando configures la variable y publiques el archivo en `downloads/monitor-app.apk`.

## 4. Compilar y publicar la app

El APK release fija el dominio en `BuildConfig`. En el equipo de compilación, configura `MONITOR_SERVER_URL=https://monitor.tudominio.mx` o usa `-PmonitorServerUrl=https://monitor.tudominio.mx` y genera un APK release firmado desde Android Studio. No incluyas el keystore ni sus contraseñas en el repo.

Copia el APK firmado al VPS con el nombre configurado:

```sh
scp app-release.apk usuario@monitor.tudominio.mx:/ruta/monitor_telefono/downloads/monitor-app.apk
```

Comprueba que el APK es instalable y que la firma es la esperada antes de anunciar el enlace. Si la app usa otro nombre/ruta, actualiza `ANDROID_DOWNLOAD_URL` para que coincida.

## 5. Arrancar y comprobar

Desde `monitor_telefono/`:

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 monitor caddy backup
```

Comprueba desde una máquina externa:

```sh
curl -fsS https://monitor.tudominio.mx/api/salud
```

La respuesta esperada es `{"estado":"ok"}`. Abre `https://monitor.tudominio.mx`, inicia sesión, ve a **Dispositivos > Agregar teléfono** y crea el QR. El teléfono debe poder abrir el enlace desde datos móviles y desde Wi-Fi. El QR caduca a los 15 minutos y solo se puede canjear una vez.

El contenedor del servidor no publica `8100`. Caddy termina TLS en 80/443 y reenvía al servidor por la red privada de Docker. En el `docker-compose.yml`, Uvicorn acepta cabeceras proxy porque la API no tiene un puerto host publicado; no expongas directamente el contenedor a otra red no confiable.

## 6. Datos, respaldos y restauración

SQLite se guarda en el volumen persistente `monitor_data`. El servicio `backup` realiza una copia consistente diaria con la API `sqlite3.Connection.backup` y conserva `BACKUP_RETENTION_DAYS` días en `backups/`. Protege ese directorio como datos personales: contiene mensajes legibles.

Comprueba regularmente que hay archivos de respaldo y copia una versión cifrada a un almacenamiento externo separado. El contenedor no ofrece protección contra pérdida total del VPS. Para restaurar una copia concreta:

```sh
docker compose stop monitor
docker compose run --rm --no-deps --entrypoint sh backup -c \
  'cp /backups/monitor-AAAAMMDDTHHMMSSZ.sqlite3 /data/monitor.sqlite3 && chown 10001:10001 /data/monitor.sqlite3'
docker compose up -d monitor
```

Sustituye el nombre por un archivo existente. Antes de restaurar, guarda otra copia de la base actual.

## 7. Actualizaciones y operación

1. Haz una copia externa verificada de SQLite antes de actualizar.
2. Obtén la versión revisada del proyecto y revisa cambios de migración/configuración.
3. Ejecuta `docker compose up -d --build`.
4. Comprueba `docker compose ps`, `/api/salud`, el login y el feed.
5. Revisa logs sin habilitar volcados de cuerpos HTTP, cookies, tokens ni contenido de mensajes.

El despliegue usa un solo proceso Uvicorn por defecto para que el bloqueo de intentos en memoria sea compartido por todas las solicitudes del servidor. Si escalas réplicas o workers, reemplaza ese bloqueo por un almacén compartido y prueba las reglas del proxy antes de hacerlo.

## 8. Límites operativos

- La conectividad HTTPS y la renovación de certificados requieren DNS correcto y puertos públicos disponibles.
- La app usa Google Play Services Code Scanner; en equipos sin esos servicios, puede ingresarse el código corto manualmente.
- El panel marca un teléfono **En línea** si hubo contacto en los últimos 35 minutos; Android puede retrasar trabajos periódicos por ahorro de batería.
- Desvincular revoca el token y detiene nuevos envíos, pero no borra los eventos ya guardados. Bórralos desde la administración si la solicitud de la persona lo requiere.
- Completa y publica el aviso de privacidad con responsable, contacto y bases legales antes de recolectar mensajes reales.
