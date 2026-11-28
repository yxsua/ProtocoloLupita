# Protocolo Lupita

## Aplicación local

La base ejecutable usa FastAPI, Jinja2 y SQLite. Requiere Python 3.11 o posterior y `uv`.

```powershell
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abrir <http://127.0.0.1:8000>. La documentación de API queda en <http://127.0.0.1:8000/docs>.

Los contratos y decisiones compartidas están en [DECISIONES_ARQUITECTURA.md](DECISIONES_ARQUITECTURA.md). Los JSON de escenarios se guardan en `data/scenarios/`; SQLite queda en `data/prototipo.sqlite3` y está excluido de Git.

## Integración y pruebas

Los routers de siembra, voz, inteligencia, SMS, reportes ciudadanos, mapa y tablero se montan en la aplicación principal. El resumen de rutas, contratos entre módulos, catálogo de escenarios y cambios aplicados tras integrar ramas está en [INTEGRACION.md](INTEGRACION.md).

Para validar la integración local:

```powershell
uv sync --group dev
uv run pytest -q
```

La demo telefónica usa un DID Twilio, webhook HTTPS y las variables de `.env.example`; consulta [INTEGRACION.md](INTEGRACION.md) para la configuración. La guía de despliegue público está en [DESPLIEGUE_EC2_UBUNTU.md](DESPLIEGUE_EC2_UBUNTU.md). Inicia un solo worker para respetar el límite de una llamada y mantener el SSE en memoria. La app expone `/api/health`, `/api/scenarios`, `/api/scenarios/{id}/run`, `/api/scenarios/run-all` y `/api/scenarios/results`, además de la interfaz web y las rutas de cada módulo.
