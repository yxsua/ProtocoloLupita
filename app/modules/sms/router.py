"""Router FastAPI para la bandeja de SMS sinteticos y analizador sin navegacion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.modules.sms.dataset_classifier import get_default_dataset_classifier
from app.modules.sms.service import analyze_sms, get_default_circular_store, load_sms_inbox

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(prefix="/sms", tags=["sms"])


@router.get("", response_class=HTMLResponse)
def sms_inbox_page(request: Request) -> HTMLResponse:
    """Vista pública para revisar un mensaje en lenguaje sencillo."""
    return templates.TemplateResponse(
        request,
        "sms/inbox.html",
        {"active_page": "sms"},
    )


@router.get("/api/alerts")
def get_circular_alerts_api() -> dict[str, Any]:
    """Devuelve alertas circulares anonimas aprendidas de la ciudadania y estadisticas del dataset."""
    return {
        "alerts": get_default_circular_store().list_recent_alerts(),
        "dataset_stats": get_default_dataset_classifier().stats(),
        "links_disabled": True,
    }


@router.get("/api/inbox")
def get_sms_inbox_api() -> dict[str, Any]:
    """Devuelve fixtures de bandeja SMS con analisis y enlaces ya desactivados."""
    inbox = load_sms_inbox()
    return {
        "items": [analyze_sms(item).to_dict() for item in inbox],
        "links_disabled": True,
    }


@router.post("/api/analyze")
def analyze_sms_api(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Analiza un SMS pegado por la persona sin abrir enlaces."""
    result = analyze_sms(
        {
            "body": str(payload.get("body", "")),
            "sender": payload.get("sender"),
            "message_id": payload.get("message_id"),
            "municipality": payload.get("municipality"),
        }
    )
    return result.to_dict()
