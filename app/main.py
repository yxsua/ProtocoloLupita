<<<<<<< HEAD
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.core.config import APP_TITLE, PROJECT_ROOT
from app.core.db import initialize_database, list_scenario_results, reset_demo_data
from app.core.scenario_runner import list_scenarios, run_all_scenarios, run_scenario


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title=APP_TITLE, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static")
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": APP_TITLE},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "protocolo-lupita", "storage": "sqlite"}


@app.get("/api/scenarios")
async def scenarios():
    return list_scenarios()


@app.post("/api/scenarios/{scenario_id}/run")
async def run_one_scenario(scenario_id: str):
    scenario = next((item for item in list_scenarios() if item.id == scenario_id), None)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario is not in data/scenarios")
    return run_scenario(scenario)


@app.post("/api/scenarios/run-all")
async def run_all():
    return run_all_scenarios()


@app.get("/api/scenarios/results")
async def scenario_results():
    return list_scenario_results()


@app.post("/api/demo/reset")
async def reset_demo():
    reset_demo_data()
    return {"status": "reset"}

=======
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
>>>>>>> origin/Josue
