# Protocolo Lupita

## Aplicación local

La base ejecutable usa FastAPI, Jinja2 y SQLite. Requiere Python 3.11 o posterior y `uv`.

Antes del primer inicio, copia `.env.example` a `.env` y define `GOV_PANEL_USERNAME` y `GOV_PANEL_PASSWORD` para el panel privado.

```powershell
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

Abrir <http://127.0.0.1:8000>. La documentación de API queda en <http://127.0.0.1:8000/docs>.

## Con Docker Compose

Requiere Docker Desktop con Compose v2. Copia `.env.example` a `.env` y completa las credenciales del panel antes de arrancar:

```powershell
Copy-Item .env.example .env
# Edita .env y define GOV_PANEL_USERNAME y GOV_PANEL_PASSWORD
docker compose up --build -d
docker compose ps
docker compose logs -f app
```

Abre <http://127.0.0.1:8000>. Para mostrar la demo desde un celular conectado a la misma red, cambia `APP_BIND_ADDRESS=0.0.0.0` en `.env`, reinicia con `docker compose up -d` y abre `http://<IP-local-de-la-laptop>:8000` en el celular. Usa una red local de demostración.

Compose conserva las dos bases SQLite y el manifiesto de siembra en el volumen `protocolo-lupita-data`, separado del código y de los fixtures. `docker compose down` conserva el historial; eliminar el volumen también elimina esos datos. La aplicación corre como usuario no privilegiado y con un solo worker porque el flujo de eventos en vivo vive en memoria.

El servidor no requiere acceso al micrófono para la simulación de escenarios; las voces se generan en el navegador. Whisper y Piper son opciones locales separadas y no se instalan en la imagen base.

La portada y `/citizen` son la sección pública para orientación y reportes. El dashboard detallado está en `/gobierno` y pide credenciales HTTP Basic configuradas como `GOV_PANEL_USERNAME` y `GOV_PANEL_PASSWORD` en `.env`. La vista pública muestra avisos agregados; los resultados de llamadas trampa, escenarios y atribución solo aparecen en el panel autenticado.

Para mostrar la sección pública desde un celular conectado a la misma red local, inicia temporalmente con `--host 0.0.0.0` y abre `http://<IP-local-de-la-laptop>:8000`. El panel de gobierno continúa protegido por credenciales. Usa una red local de demostración y datos sintéticos.

Los contratos y decisiones compartidas están en [DECISIONES_ARQUITECTURA.md](DECISIONES_ARQUITECTURA.md). Los JSON de escenarios se guardan en `data/scenarios/`; SQLite queda en `data/prototipo.sqlite3` y está excluido de Git.

## Integración y pruebas

Los routers de siembra, voz, inteligencia, SMS, reportes ciudadanos, mapa y tablero se montan en la aplicación principal. El resumen de rutas, contratos entre módulos, catálogo de escenarios y cambios aplicados tras integrar ramas está en [INTEGRACION.md](INTEGRACION.md).

Para validar la integración local:

```powershell
uv sync --group dev
uv run pytest -q
```

La demo de esta iteración es enteramente local: el router de telefonía real no se monta en la aplicación. La llamada se simula desde `/gobierno/simulador` con escenarios de voz precargados; genera las voces de la persona que llama y Doña Lupita en el navegador, sin acceso al micrófono ni entrada manual de mensajes, y presenta la transcripción en el dashboard `/gobierno`. El bus SSE usa memoria, por lo que la aplicación se inicia con un solo worker. El simulador y los endpoints de escenarios, siembra, inteligencia y dashboard detallado requieren autenticación gubernamental.
