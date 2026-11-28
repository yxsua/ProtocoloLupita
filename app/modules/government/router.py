"""Panel interno, escenarios cerrados y resultados en vivo."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.core.config import PROJECT_ROOT
from app.core.db import list_scenario_results
from app.core.scenario_runner import list_scenarios, run_scenario
from app.core.schemas import Channel
from app.modules.government.auth import require_government_user
from app.modules.government.events import events_after, latest_event_for_report, publish_event, snapshot

router = APIRouter(tags=["government"])
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))
_CALL_DESCRIPTIONS_PATH = PROJECT_ROOT / "data" / "scenarios" / "e01_e08_voice.json"


def _call_scenario_descriptions() -> dict[str, str]:
    if not _CALL_DESCRIPTIONS_PATH.exists():
        return {}
    try:
        data = json.loads(_CALL_DESCRIPTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(row.get("id")): str(row.get("description", "Escenario de llamada"))
        for row in data.get("scenarios", [])
        if row.get("id")
    }


@router.get("/gobierno", response_class=HTMLResponse)
def government_page(request: Request, _: str = Depends(require_government_user)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "government/index.html",
        {"title": "Actividad de llamadas · Panel gubernamental"},
    )


@router.get("/gobierno/escenarios", response_class=HTMLResponse)
def government_scenarios_page(
    request: Request,
    _: str = Depends(require_government_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "government/scenarios.html",
        {"title": "Simular escenarios · Panel gubernamental"},
    )


@router.get("/api/gobierno/snapshot")
def government_snapshot(_: str = Depends(require_government_user)) -> dict[str, Any]:
    scenarios = [scenario for scenario in list_scenarios() if scenario.channel == Channel.CALL]
    descriptions = _call_scenario_descriptions()
    return {
        **snapshot(),
        "scenarios": [
            {"id": scenario.id, "label": descriptions.get(scenario.id, f"Escenario {scenario.id}")}
            for scenario in scenarios
        ],
        "recent_scenarios": [
            {
                "scenario_id": result["scenario_id"],
                "passed": result["passed"],
                "ran_at": result["ran_at"],
                "duration_ms": result["duration_ms"],
            }
            for result in list_scenario_results(limit=10)
            if str(result.get("scenario_id", "")).startswith("E0")
        ],
    }


@router.get("/api/gobierno/eventos")
async def government_events(
    request: Request,
    after: int = 0,
    _: str = Depends(require_government_user),
) -> StreamingResponse:
    async def stream():
        cursor = max(0, after)
        while not await request.is_disconnected():
            pending = events_after(cursor)
            for event in pending:
                cursor = int(event["id"])
                yield f"id: {cursor}\nevent: update\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            if not pending:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.6)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/api/gobierno/escenarios/{scenario_id}/ejecutar")
def run_call_scenario(
    scenario_id: str,
    _: str = Depends(require_government_user),
) -> dict[str, Any]:
    scenario = next(
        (item for item in list_scenarios() if item.id == scenario_id and item.channel == Channel.CALL),
        None,
    )
    if scenario is None:
        raise HTTPException(status_code=404, detail="No se encontró ese escenario de llamada.")
    result = run_scenario(scenario)
    voice = result.actual.get("voice", {}) if isinstance(result.actual, dict) else {}
    intelligence = result.actual.get("intelligence", {}) if isinstance(result.actual, dict) else {}
    publish_event(
        "scenario.completed",
        {
            "source_mode": "scenario",
            "scenario_id": result.scenario_id,
            "passed": result.passed,
            "duration_ms": round(result.duration_ms, 1),
            "voice": {
                key: voice.get(key)
                for key in ("intenciones", "clabe_detectada", "digito_verificador_ok", "ultima_intencion")
            },
            "campaign": {
                key: intelligence.get(key)
                for key in ("status", "threat_category", "campaign_id", "confidence_level")
            },
            "synthetic_demo": True,
        },
    )
    return {
        "scenario_id": result.scenario_id,
        "passed": result.passed,
        "ran_at": result.ran_at.isoformat(),
        "duration_ms": round(result.duration_ms, 1),
        "voice": {
            key: voice.get(key)
            for key in (
                "intenciones", "clabe_detectada", "digito_verificador_ok",
                "ultima_intencion", "status", "confianza", "fuente_unica",
            )
        },
        "intelligence": {
            key: intelligence.get(key)
            for key in ("status", "threat_category", "campaign_id", "confidence_level")
        },
        "source_mode": "scenario",
    }


@router.get("/api/gobierno/reportes/{event_id}")
def government_report_draft(
    event_id: str,
    _: str = Depends(require_government_user),
) -> dict[str, Any]:
    event = latest_event_for_report(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="No hay un resultado reciente para preparar.")
    return {
        "report_version": "demo-1",
        "status": "borrador_no_enviado",
        "synthetic_demo": True,
        "notice": "Borrador de demostración. No se envió a una autoridad.",
        "generated_at": event.get("occurred_at"),
        "source_mode": event.get("source_mode"),
        "call_id": event.get("call_id"),
        "scenario_id": event.get("scenario_id"),
        "attribution": event.get("attribution"),
        "indicators": event.get("indicators", []),
        "campaign": event.get("campaign"),
        "evidence_hash": event.get("evidence_hash"),
    }
