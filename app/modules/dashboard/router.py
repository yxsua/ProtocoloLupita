"""Rutas HTTP y HTML del tablero de Mosca Estéril."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.modules.dashboard.schemas import DashboardFilters, DashboardResponse
from app.modules.dashboard.service import get_dashboard


APP_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = APP_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["dashboard"])


def _resolve_base_template() -> str:
    if (TEMPLATES_DIR / "base.html").exists():
        return "base.html"
    return "planting/_standalone_base.html"


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request) -> HTMLResponse:
    """Renderiza el tablero principal (atribución, campañas y mapa offline)."""
    initial_data = get_dashboard()
    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "base_template": _resolve_base_template(),
            "page_title": "Tablero y Mapa — Mosca Estéril",
            "initial_data": initial_data,
        },
    )


@router.get("/api/dashboard", response_model=DashboardResponse)
def api_dashboard(
    channel: Optional[Literal["call", "sms", "portal"]] = Query(default=None),
    seed_period: Optional[str] = Query(default=None),
    campaign_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    confidence: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> DashboardResponse:
    """Devuelve datos filtrados de atribuciones y campañas para el tablero."""
    filters = DashboardFilters(
        channel=channel,
        seed_period=seed_period,
        campaign_id=campaign_id,
        status=status,
        confidence=confidence,
        limit=limit,
    )
    return get_dashboard(filters)


def get_routers() -> list[APIRouter]:
    """Devuelve los routers del módulo de tablero."""
    return [router]


def register_routes(app: FastAPI) -> None:
    """Registra las rutas del tablero en una instancia FastAPI."""
    app.include_router(router)
