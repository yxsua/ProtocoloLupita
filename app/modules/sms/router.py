"""Router FastAPI para la bandeja de SMS sinteticos y analizador sin navegacion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.modules.sms.dataset_classifier import get_default_dataset_classifier
from app.modules.sms.service import (
    analyze_sms,
    get_default_circular_store,
    get_default_live_inbox,
    ingest_device_sms,
    load_sms_inbox,
)

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(prefix="/sms", tags=["sms"])


def _combined_inbox_items() -> list[dict[str, Any]]:
    live_items = get_default_live_inbox().list_items()
    fixture_items = [
        {
            "source": "fixture",
            "raw": item,
            "analysis": analyze_sms(item).to_dict(),
        }
        for item in load_sms_inbox()
    ]
    return live_items + fixture_items


@router.get("", response_class=HTMLResponse)
def sms_inbox_page(request: Request) -> HTMLResponse:
    """Vista de bandeja de SMS sinteticos y recibidos (nunca abre enlaces ni responde SMS)."""
    precomputed = _combined_inbox_items()
    alerts = get_default_circular_store().list_recent_alerts()
    dataset_stats = get_default_dataset_classifier().stats()
    return templates.TemplateResponse(
        request,
        "sms/inbox.html",
        {
            "items": precomputed,
            "circular_alerts": alerts,
            "dataset_stats": dataset_stats,
        },
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
    """Devuelve SMS recibidos en vivo y fixtures con analisis y enlaces ya desactivados."""
    return {
        "items": _combined_inbox_items(),
        "links_disabled": True,
    }


@router.post("/api/device-webhook")
def receive_device_sms_api(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Endpoint para recibir SMS desde automatizacion del telefono (MacroDroid / iOS Atajos)."""
    entry = ingest_device_sms(payload)
    analysis = entry["analysis"]
    return {
        "status": "received",
        "message_id": entry["raw"]["message_id"],
        "is_suspicious": analysis["is_suspicious"],
        "impersonated_entity": analysis["impersonated_entity"],
        "scam_type": analysis["scam_type"],
        "verification_status": analysis["verification_status"],
        "preventive_warning": analysis["preventive_warning"],
        "defanged_urls": analysis["indicators"]["defanged_urls"],
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
