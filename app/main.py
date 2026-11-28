"""
main.py — Punto de entrada FastAPI de ProtocoloLupita.

Monta los archivos estáticos y registra los routers de los módulos activos.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.modules.voice.router import router as voice_router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="ProtocoloLupita",
    description="Prototipo modular anti-fraude con Doña Lupita y voz híbrida",
    version="0.1.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

app.include_router(voice_router)


@app.get("/", include_in_schema=False)
async def root():
    """Redirige a la interfaz del módulo de voz."""
    return RedirectResponse(url="/voice/")


@app.get("/health")
async def health():
    """Verificación básica de estado de la aplicación."""
    return {"status": "ok", "module": "voice"}
