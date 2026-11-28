"""
main.py — Punto de entrada FastAPI de ProtocoloLupita.

Monta los archivos estáticos y registra los routers de los módulos activos.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.modules.voice.router import router as voice_router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Protocolo Lupita",
    description="Prototipo modular anti-fraude con cuatro avatares ciudadanos y voz híbrida",
    version="0.1.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

app.include_router(voice_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    """Menú principal con acceso al simulador educativo de voz."""
    return """
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Protocolo Lupita</title>
      <style>
        body { font: 16px system-ui, sans-serif; margin: 0; min-height: 100vh;
               display: grid; place-items: center; background: #101820; color: #f3f5f7; }
        main { max-width: 620px; padding: 32px; text-align: center; }
        a { display: inline-block; margin-top: 16px; padding: 12px 20px; border-radius: 8px;
            background: #d84c68; color: white; text-decoration: none; font-weight: 700; }
      </style>
    </head>
    <body>
      <main>
        <h1>Protocolo Lupita</h1>
        <p>Demo educativa para practicar la detección de señales de fraude telefónico.</p>
        <a href="/voice/">Abrir módulo de voz</a>
      </main>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    """Verificación básica de estado de la aplicación."""
    return {"status": "ok", "module": "voice"}
