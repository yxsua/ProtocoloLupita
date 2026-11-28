# Publicar en AWS EC2 con Ubuntu y HTTPS

Guía para desplegar el prototipo en una sola instancia EC2, con Caddy como proxy HTTPS y Uvicorn en `127.0.0.1`. El piloto debe permanecer con **un worker**: el límite de llamadas y el flujo SSE usan memoria del proceso.

## 1. Preparar recursos en AWS

1. En EC2, lanza una instancia con Ubuntu Server 24.04 LTS en una subred pública. Para este piloto, usa una instancia de al menos 2 vCPU y 4 GiB de RAM si vas a habilitar Piper; sin Piper puede bastar una instancia más pequeña.
2. Crea o selecciona un par de llaves SSH y guárdalo fuera del repositorio.
3. Asocia un Elastic IP a la instancia para tener una dirección estable y poder apuntar el DNS a ella.
4. En el grupo de seguridad, agrega estas reglas de entrada:

   | Protocolo | Puerto | Origen |
   | --- | ---: | --- |
   | SSH | 22 | Solo tu IP pública, como `203.0.113.25/32` |
   | HTTP | 80 | `0.0.0.0/0` y `::/0` si usas IPv6 |
   | HTTPS | 443 | `0.0.0.0/0` y `::/0` si usas IPv6 |

   No abras el puerto 8000: Caddy y Uvicorn se comunican dentro de la instancia. AWS documenta que el grupo de seguridad actúa como firewall de la instancia y que SSH debe limitarse al origen que administra el servidor. [Reglas de grupos de seguridad](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html)

5. En el proveedor de DNS, crea un registro `A` (por ejemplo, `demo.midominio.org`) apuntando al Elastic IP. Si agregas un registro `AAAA`, verifica que la instancia también tenga IPv6 público operativo.

Un Elastic IP se puede asociar a la instancia para darle una dirección pública persistente. [Elastic IP en EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html)

## 2. Conectarse e instalar herramientas

Desde PowerShell, sustituye la ruta de la llave y la IP:

```powershell
ssh -i .\mi-llave.pem ubuntu@<ELASTIC_IP>
```

En la instancia Ubuntu:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git python3 python3-venv build-essential
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

Instala Caddy desde su repositorio oficial de paquetes para Ubuntu:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

La instalación oficial registra Caddy como servicio `systemd`. [Instalar Caddy en Debian/Ubuntu](https://caddyserver.com/docs/install)

## 3. Copiar el proyecto y preparar la cuenta de servicio

Usa la URL y rama reales de tu repositorio. Para un repositorio privado, configura acceso de lectura con una llave de despliegue; no copies una llave privada a la instancia dentro del código.

```bash
sudo useradd --system --create-home --home-dir /var/lib/protocolo \
  --shell /usr/sbin/nologin --user-group protocolo
sudo install -d -o ubuntu -g protocolo -m 2750 /opt/protocolo-lupita
git clone --branch <RAMA> <URL_REPOSITORIO> /opt/protocolo-lupita
cd /opt/protocolo-lupita
sudo chown -R ubuntu:protocolo /opt/protocolo-lupita
sudo chmod -R g+rX /opt/protocolo-lupita
sudo chmod g+s /opt/protocolo-lupita
sudo chmod -R g+rX /opt/protocolo-lupita/data
sudo chmod g+rwx,g+s /opt/protocolo-lupita/data
sudo install -d -o ubuntu -g protocolo -m 2770 /opt/protocolo-lupita/data/planting
uv sync --locked
sudo chmod -R g+rX /opt/protocolo-lupita/.venv
```

La cuenta `protocolo` ejecutará la aplicación sin acceso SSH ni permisos de escritura sobre el código. El grupo compartido permite que esa cuenta lea la aplicación y que Git/`uv` ejecutados por `ubuntu` puedan actualizarla.

## 4. Configurar secretos y variables de entorno

Crea un archivo que no forme parte del repositorio:

```bash
sudo install -o root -g protocolo -m 640 /dev/null /etc/protocolo-lupita.env
sudoedit /etc/protocolo-lupita.env
```

Añade las variables necesarias y sustituye todos los ejemplos:

```dotenv
TWILIO_AUTH_TOKEN=TOKEN_REAL_DE_TWILIO
TWILIO_TEST_NUMBER=+52XXXXXXXXXX
TWILIO_TEST_TRAP_ID="+52 442 000 0102"
PUBLIC_BASE_URL=https://demo.midominio.org
GOV_PANEL_USERNAME=operador
GOV_PANEL_PASSWORD=CONTRASENA_LARGA_ALEATORIA
TWILIO_GATHER_LANGUAGE=es-MX
TWILIO_SPEECH_MODEL=deepgram_nova-3
PIPER_MODEL_PATH=
```

`TWILIO_TEST_NUMBER` debe ser el DID asignado por Twilio; `TWILIO_TEST_TRAP_ID` es la trampa sembrada que se atribuirá. `PUBLIC_BASE_URL` debe coincidir con el dominio público, sin barra final ni prefijo de ruta. No pongas secretos en Git, en la unidad de systemd ni en comandos que queden en el historial.

Si usarás Piper, instala el modelo de voz en una ruta legible por el grupo `protocolo` y pon aquí la ruta del modelo `.onnx`. Sin modelo, el motor usa sus clips y la voz de respaldo de Twilio.

## 5. Crear el servicio systemd

```bash
sudoedit /etc/systemd/system/protocolo-lupita.service
```

Contenido:

```ini
[Unit]
Description=Protocolo Lupita FastAPI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=protocolo
Group=protocolo
WorkingDirectory=/opt/protocolo-lupita
EnvironmentFile=/etc/protocolo-lupita.env
ExecStart=/opt/protocolo-lupita/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=3
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/protocolo-lupita/data

[Install]
WantedBy=multi-user.target
```

La aplicación necesita escribir en `data/` para SQLite y en `data/planting/` para el manifiesto de siembra. Los fixtures de `data/scenarios/` se mantienen de solo lectura. El resto del árbol queda de solo lectura para el proceso. Arranca el servicio y confirma que responde localmente:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now protocolo-lupita
sudo systemctl status protocolo-lupita --no-pager
curl http://127.0.0.1:8000/api/health
```

La respuesta esperada incluye `"status":"ok"`. Consulta los logs con:

```bash
sudo journalctl -u protocolo-lupita -n 100 --no-pager
sudo journalctl -u protocolo-lupita -f
```

## 6. Publicar con HTTPS mediante Caddy

Confirma primero que el registro DNS ya resuelve al Elastic IP y que el grupo de seguridad deja entrar por los puertos 80 y 443. Caddy usa esos puertos para validar y servir el certificado, redirige HTTP a HTTPS y renueva el certificado automáticamente. [HTTPS automático de Caddy](https://caddyserver.com/docs/automatic-https)

Edita el archivo:

```bash
sudoedit /etc/caddy/Caddyfile
```

Configura el dominio real:

```caddyfile
demo.midominio.org {
    reverse_proxy 127.0.0.1:8000
}
```

Valida y recarga Caddy:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
sudo journalctl -u caddy -n 100 --no-pager
```

Prueba desde tu computadora:

```bash
curl -i https://demo.midominio.org/api/health
curl -I http://demo.midominio.org
```

La primera ruta debe devolver JSON con estado `ok`; la segunda debe redirigir a HTTPS. Si el certificado no se emite, revisa que el DNS apunte al Elastic IP, los puertos 80/443 estén abiertos en el grupo de seguridad y no haya un registro AAAA roto.

## 7. Conectar el número de Twilio y validar el panel

En la consola de Twilio, configura el webhook de voz del DID:

- Método: `POST`
- URL: `https://demo.midominio.org/api/telephony/voice`
- Callback de estado: `https://demo.midominio.org/api/telephony/status`

Después:

1. Abre `https://demo.midominio.org/gobierno` e inicia sesión con `GOV_PANEL_USERNAME` y `GOV_PANEL_PASSWORD`.
2. Abre `https://demo.midominio.org/api/gobierno/snapshot` con las mismas credenciales; debe requerir autenticación.
3. Haz una llamada desde el celular al DID. Verifica el saludo, una respuesta de voz, la atribución al número receptor y los eventos en el panel.
4. Llama de nuevo mientras la primera siga activa: debe recibirse el mensaje de línea ocupada.
5. Desde `/gobierno/escenarios`, ejecuta una prueba y confirma que aparezca etiquetada como simulación separada de la llamada.

## 8. Operación y actualización

Reiniciar o actualizar la instancia no conserva los eventos de llamadas en memoria. SQLite y el manifiesto están en el volumen de la instancia; configura copias de seguridad de ese volumen o respalda `data/` antes de actualizar. No escales a varios workers ni varias instancias hasta mover el límite de llamadas y el bus SSE a un servicio compartido.

Para desplegar una nueva versión:

```bash
cd /opt/protocolo-lupita
git pull --ff-only
uv sync --locked
sudo chmod -R g+rX .venv
sudo systemctl restart protocolo-lupita
sudo systemctl status protocolo-lupita --no-pager
```

Los archivos `.env`, llaves SSH y tokens nunca deben guardarse en el repositorio. La transcripción de voz la procesa Twilio Gather; usa solo datos sintéticos y un guion de demostración para la prueba.

## Diagnóstico rápido

- **`status=203/EXEC` en systemd:** `ExecStart` apunta a un ejecutable que no existe o no se puede ejecutar. Comprueba `ls -l /opt/protocolo-lupita/.venv/bin/uvicorn` y que `WorkingDirectory`, `ExecStart` y `ReadWritePaths` apunten a la misma raíz del repositorio. Si el `git clone` creó una subcarpeta, corrige esas rutas para incluirla o vuelve a clonar con la ruta destino explícita como arriba.
- **`uv sync` no instala `twilio`:** el checkout no incluye la integración telefónica. Confirma que estás desplegando la rama/commit que contiene `app/modules/telephony/`, `app/modules/government/` y la dependencia `twilio` en `pyproject.toml` antes de continuar con Twilio.
- **El servicio arranca pero no puede crear SQLite:** confirma que la ruta de `ReadWritePaths` cubra el directorio `data/` correcto y que el grupo `protocolo` pueda escribir en él.
