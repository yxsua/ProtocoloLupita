"""Router FastAPI para el portal ciudadano y agregados municipales seguros."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.modules.citizen.service import get_map_aggregates, submit_report

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(prefix="/citizen", tags=["citizen"])


@router.get("", response_class=HTMLResponse)
def citizen_portal_page(request: Request) -> HTMLResponse:
    """Formulario público para contar una llamada o mensaje sospechoso."""
    return templates.TemplateResponse(
        request,
        "citizen/portal.html",
        {"active_page": "citizen"},
    )


@router.post("/api/report")
def submit_citizen_report_api(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Recibe reporte ciudadano, descarta PII antes de persistir y devuelve ruta guiada."""
    channel = payload.get("channel", "sms")
    if channel not in ("sms", "llamada"):
        channel = "sms"

    clean_payload = dict(payload)
    clean_payload["channel"] = channel
    response = submit_report(clean_payload)
    return response.to_dict()


@router.get("/api/map-aggregates")
def get_municipal_aggregates_api() -> dict[str, Any]:
    """API para el mapa de Integrante 2: solo municipios >= umbral y total agregado."""
    return get_map_aggregates().to_dict()
