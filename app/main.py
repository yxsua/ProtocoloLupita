"""Punto de entrada FastAPI para Plan 5 (SMS y portal ciudadano)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.modules.citizen.router import router as citizen_router
from app.modules.intel.router import create_fastapi_router as create_intel_router
from app.modules.sms.router import router as sms_router

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    """Construye la aplicacion FastAPI montando rutas de SMS, portal ciudadano, inteligencia y estaticos."""
    application = FastAPI(
        title="Protocolo Lupita — SMS, Portal Ciudadano e Inteligencia",
        version="0.1.0",
    )
    application.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    application.include_router(sms_router)
    application.include_router(citizen_router)
    application.include_router(create_intel_router())

    @application.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/citizen")

    return application


app = create_app()
