"""Punto de entrada de la aplicación monolítica local."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.core.config import APP_TITLE, PROJECT_ROOT
from app.core.db import initialize_database, list_scenario_results, reset_demo_data
from app.core.scenario_runner import list_scenarios, run_all_scenarios, run_scenario
from app.core.scenario_handlers import register_default_handlers
from app.modules.citizen.router import router as citizen_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.intel.router import create_fastapi_router as create_intel_router
from app.modules.map.router import router as map_router
from app.modules.planting.router import router as planting_router
from app.modules.planting.service import ensure_seeded
from app.modules.sms.router import router as sms_router
from app.modules.voice.router import router as voice_router
from app.modules.government.router import router as government_router
from app.modules.telephony.router import router as telephony_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    ensure_seeded()
    yield


app = FastAPI(
    title=APP_TITLE,
    description="Prototipo local de atribución de filtraciones e inteligencia de amenazas.",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static")
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")
register_default_handlers()

for module_router in (
    planting_router,
    voice_router,
    create_intel_router(),
    sms_router,
    citizen_router,
    dashboard_router,
    map_router,
    government_router,
    telephony_router,
):
    app.include_router(module_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": APP_TITLE},
    )


@app.get("/api/health")
@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "app": "protocolo-lupita", "storage": "sqlite"}


@app.get("/api/scenarios")
async def scenarios():
    return list_scenarios()


@app.post("/api/scenarios/{scenario_id}/run")
def run_one_scenario(scenario_id: str):
    scenario = next((item for item in list_scenarios() if item.id == scenario_id), None)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario is not in data/scenarios")
    return run_scenario(scenario)


@app.post("/api/scenarios/run-all")
def run_all():
    return run_all_scenarios()


@app.get("/api/scenarios/results")
async def scenario_results():
    return list_scenario_results()


@app.post("/api/demo/reset")
async def reset_demo():
    reset_demo_data()
    return {"status": "reset"}
