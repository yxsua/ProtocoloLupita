# Despliegue en EC2 Ubuntu

Guía para desplegar Protocolo Lupita y el monitor Android en una instancia EC2. El dominio principal será `protocololupita.blockcode.site`; el monitor Android usará `monitor.protocololupita.blockcode.site` para disponer de su propio origen HTTPS.

## Arquitectura de esta guía

- **Protocolo Lupita:** Docker Compose, publicado solo en `127.0.0.1:8000`.
- **Monitor de teléfono:** servicio `systemd`, publicado solo en `127.0.0.1:8100`.
- **Caddy:** proxy inverso del host en puertos 80/443; termina TLS y dirige cada hostname al servicio local correspondiente.
- **Relay:** el monitor reenvía eventos al portal por `http://127.0.0.1:8000/api/eventos`, protegido por una clave compartida de servidor a servidor.

El monitor no debe exponer HTTP directamente. El APK release se compila con el hostname HTTPS del monitor. Si no puedes crear el registro DNS `monitor.protocololupita.blockcode.site`, puedes desplegar el portal principal, pero no el flujo Android integrado descrito aquí: la app requiere un origen HTTPS propio y no admite una ruta bajo el dominio principal.

Este despliegue es para una demostración controlada. Usa teléfonos propios y datos sintéticos. No habilita llamadas reales, envío de SMS ni reportes a autoridades.

## 1. Crear la instancia y la red en AWS

1. En EC2, lanza **Ubuntu Server 24.04 LTS** en una subred pública con salida a Internet. Para construir y ejecutar los dos servicios en la misma máquina, como punto de partida usa 2 vCPU, 4 GiB de RAM y un volumen EBS de 30 GiB o mayor. Ajusta el tamaño según la concurrencia y los artefactos que guardes.
2. Selecciona o crea un par de claves SSH y guarda la clave privada fuera del repositorio.
3. Asocia un **Elastic IP** a la instancia para que el DNS no dependa de la IP pública temporal.
4. En el grupo de seguridad configura estas reglas de entrada:

   | Protocolo | Puerto | Origen |
   |---|---:|---|
   | SSH | 22 | Tu IP pública, por ejemplo `203.0.113.25/32` |
   | HTTP | 80 | `0.0.0.0/0` |
   | HTTPS | 443 | `0.0.0.0/0` |

   No abras 8000 ni 8100. Si configuras IPv6 en la VPC y en Ubuntu, agrega también las reglas HTTP/HTTPS para `::/0` y registros DNS `AAAA` válidos. Limita SSH a la IP desde donde administrarás la instancia.

5. En la zona DNS de `blockcode.site`, crea estos registros `A`, ambos apuntando al Elastic IP:

   | Nombre | Tipo | Valor |
   |---|---|---|
   | `protocololupita` | A | Elastic IP de EC2 |
   | `monitor.protocololupita` | A | El mismo Elastic IP |

   Espera a que ambos nombres resuelvan antes de configurar Caddy. No crees registros `AAAA` si la instancia no tiene IPv6 público operativo.

AWS usa grupos de seguridad como firewall de la instancia; un Elastic IP ofrece una IPv4 persistente que puede asociarse a EC2. [Crear reglas de grupo de seguridad](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-security-group.html) · [Asociar un Elastic IP](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html)

## 2. Entrar a Ubuntu e instalar Docker y Caddy

Desde PowerShell, conecta usando la clave privada descargada de AWS:

```powershell
ssh -i .\mi-clave-ec2.pem ubuntu@<ELASTIC_IP>
```

Actualiza Ubuntu e instala Docker Engine y el plugin Compose desde el repositorio oficial de Docker:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git python3 python3-venv build-essential
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker version
sudo docker compose version
```

Instala Caddy desde su repositorio oficial; el paquete crea y activa el servicio `systemd`:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Docker mantiene instrucciones específicas para Ubuntu y Compose; Caddy se encarga de solicitar y renovar HTTPS cuando el dominio resuelve a la instancia y los puertos 80/443 son accesibles. [Docker Engine en Ubuntu](https://docs.docker.com/engine/install/ubuntu/) · [Docker Compose en Linux](https://docs.docker.com/compose/install/linux/) · [Instalar Caddy en Debian/Ubuntu](https://caddyserver.com/docs/install) · [HTTPS automático en Caddy](https://caddyserver.com/docs/automatic-https)

Si activas UFW además del grupo de seguridad, permite SSH antes de habilitarlo para no perder acceso:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

## 3. Copiar el repositorio

Clona la rama que contiene la integración. Sustituye los marcadores por la URL y rama reales:

```bash
sudo install -d -o ubuntu -g ubuntu /opt/protocololupita
git clone --branch <RAMA> <URL_REPOSITORIO> /opt/protocololupita
cd /opt/protocololupita
```

Para un repositorio privado, configura acceso de lectura desde esta instancia mediante un mecanismo de despliegue controlado; no guardes una clave privada dentro del checkout. Protege los archivos `.env` con permisos restrictivos y no los subas al repositorio.

## 4. Configurar el portal principal

Crea el archivo de entorno que Compose cargará:

```bash
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Edita `.env` y define al menos:

```dotenv
GOV_PANEL_USERNAME=operador-demo
GOV_PANEL_PASSWORD=<contraseña-larga-y-exclusiva>
APP_PORT=8000
APP_BIND_ADDRESS=127.0.0.1
PIPER_MODEL_PATH=
LUPITA_DEVICE_KEY=<salida-aleatoria-de-64-caracteres-hex>
```

`LUPITA_DEVICE_KEY` debe ser aleatoria y de al menos 32 caracteres; más adelante se copia en `LUPITA_EVENTS_KEY` del monitor. No reutilices una contraseña personal. No cambies `APP_BIND_ADDRESS` a `0.0.0.0`: Caddy es el único servicio público y Docker publicará el portal en loopback.

Construye y arranca el portal:

```bash
sudo docker compose up -d --build app
sudo docker compose ps
curl -fsS http://127.0.0.1:8000/api/health
```

La comprobación local debe responder con estado `ok`. Para consultar los logs:

```bash
sudo docker compose logs --tail=100 app
```

## 5. Configurar el monitor Android y el relay

Prepara sus secretos y archivo `.env`:

```bash
cd /opt/protocololupita/monitor_telefono
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

En `monitor_telefono/.env`, define:

```dotenv
SECRET_KEY=<secreto-aleatorio-hex-de-al-menos-32-caracteres>
DATA_ENCRYPTION_KEY=<salida-base64-url-safe-generada-arriba>
PUERTO=8100
DATABASE_PATH=/opt/protocololupita/monitor_telefono/server/data/monitor.sqlite3
BASE_URL_PUBLICA=https://monitor.protocololupita.blockcode.site
COOKIE_SECURE=true
LUPITA_EVENTS_URL=http://127.0.0.1:8000/api/eventos
LUPITA_EVENTS_KEY=<el-mismo-valor-de-LUPITA_DEVICE_KEY>
```

La clave Fernet debe conservarse para poder descifrar los textos guardados por el monitor. El relay usa HTTP solo por loopback dentro de EC2. Las cuentas de administración del monitor son independientes de las credenciales HTTP Basic del portal.

Crea la cuenta administradora del monitor y su entorno Python:

```bash
sh server/run.sh --create-admin
```

El comando puede tardar mientras instala `server/requirements.txt`; solicita usuario y contraseña de administrador. Después crea `/etc/systemd/system/monitor-telefono.service`:

```ini
[Unit]
Description=Monitor de teléfono FastAPI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/protocololupita/monitor_telefono/server
EnvironmentFile=/opt/protocololupita/monitor_telefono/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/protocololupita/monitor_telefono/server/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Activa el servicio y comprueba su endpoint local:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now monitor-telefono
sudo systemctl status monitor-telefono --no-pager
curl -fsS http://127.0.0.1:8100/api/salud
```

Debe responder `{"estado":"ok"}`. Logs:

```bash
sudo journalctl -u monitor-telefono -n 100 --no-pager
sudo journalctl -u monitor-telefono -f
```

## 6. Configurar HTTPS y los dos hostnames

Confirma primero que los registros `A` de ambos nombres resuelven al Elastic IP. Edita `/etc/caddy/Caddyfile`:

```caddyfile
protocololupita.blockcode.site {
    reverse_proxy 127.0.0.1:8000
}

monitor.protocololupita.blockcode.site {
    reverse_proxy 127.0.0.1:8100
}
```

Valida y recarga Caddy:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
sudo journalctl -u caddy -n 100 --no-pager
```

Caddy administra los certificados y las redirecciones HTTP a HTTPS. Desde tu equipo, verifica ambas rutas:

```bash
curl -I https://protocololupita.blockcode.site
curl -I https://monitor.protocololupita.blockcode.site
curl -i https://protocololupita.blockcode.site/api/health
curl -i https://monitor.protocololupita.blockcode.site/api/salud
```

Si no se emite el certificado, confirma la propagación DNS, que no exista un registro `AAAA` apuntando a una IPv6 no configurada y que el grupo de seguridad permita 80/443. Caddy también debe ser el único proceso que use esos puertos.

## 7. Vincular el teléfono y probar el relay

1. Compila un APK release firmado con el servidor del monitor fijado al hostname HTTPS. En el entorno de compilación Android, desde `monitor_telefono/android`:

   ```powershell
   $env:MONITOR_SERVER_URL = "https://monitor.protocololupita.blockcode.site"
   .\gradlew.bat assembleRelease
   ```

   Firma el APK antes de distribuirlo. La URL de release no se puede cambiar desde el teléfono.
2. En `https://monitor.protocololupita.blockcode.site`, inicia sesión con la cuenta de administrador del monitor y crea un código desde **Dispositivos > Agregar teléfono**.
3. Instala el APK en un teléfono de prueba, escanea el QR o escribe el código, revisa las apps permitidas y acepta el aviso de privacidad.
4. Completa los permisos de notificaciones en Android y genera una notificación sintética de una app autorizada.
5. En `https://protocololupita.blockcode.site/gobierno`, inicia sesión con las credenciales de `.env` y abre **Eventos del teléfono** (`/mensajes`). El evento debe aparecer y el texto debe mostrar su análisis local.

Si el teléfono ya estaba vinculado antes de activar el relay, desvincúlalo y vuelve a enrolarlo para aceptar el aviso actualizado. El servidor no reenvía eventos de teléfonos que no hayan aceptado esa versión. Los eventos anteriores del monitor no se importan retrospectivamente.

En `/mensajes`, la búsqueda y filtros aplican a los últimos 200 eventos que mantiene el portal en memoria. La base cifrada y la búsqueda del monitor permanecen en su propio servicio. Al reiniciar el portal, su feed temporal vuelve a quedar vacío; los eventos nuevos se seguirán reenviando.

## 8. Actualizar, respaldar y operar

Para actualizar el portal:

```bash
cd /opt/protocololupita
git pull --ff-only
sudo docker compose up -d --build app
sudo docker compose ps
```

Para actualizar el monitor, revisa los cambios de esquema/dependencias, conserva sus archivos `.env` y vuelve a preparar el entorno si cambian requirements:

```bash
cd /opt/protocololupita
git pull --ff-only
cd monitor_telefono
sh server/run.sh --create-admin
sudo systemctl restart monitor-telefono
sudo systemctl status monitor-telefono --no-pager
```

Respalda por separado el volumen Docker `protocolo-lupita-data`, que contiene los datos del portal, y `monitor_telefono/server/data`, que contiene la base y datos cifrados del monitor. Programa snapshots EBS y conserva `DATA_ENCRYPTION_KEY` fuera de la instancia; perder esa clave impide descifrar eventos del monitor. Prueba la restauración antes de depender de los respaldos.

El monitor devuelve `503` y Android reintenta si no logra reenviar un evento al portal. Consulta `journalctl -u monitor-telefono` y `sudo docker compose logs app` para diagnosticarlo. Revisa que `LUPITA_EVENTS_URL`, `LUPITA_EVENTS_KEY` y `LUPITA_DEVICE_KEY` coincidan y que el portal esté sano en `127.0.0.1:8000`.

## Referencias oficiales

- [Ubuntu 24.04 LTS](https://documentation.ubuntu.com/release-notes/24.04/)
- [Reglas de grupos de seguridad EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-security-group.html)
- [Pares de claves EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html)
- [Elastic IP y direcciones persistentes](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html)
- [Instalar Docker Engine en Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Instalar Docker Compose](https://docs.docker.com/compose/install/linux/)
- [Instalar Caddy en Ubuntu](https://caddyserver.com/docs/install)
- [HTTPS automático de Caddy](https://caddyserver.com/docs/automatic-https)
