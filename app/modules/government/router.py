"""Panel interno, escenarios cerrados y resultados en vivo."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.core.config import PROJECT_ROOT
from app.core.db import get_government_report, get_government_report_analytics, list_government_reports, list_scenario_results, record_government_report
from app.core.scenario_runner import list_scenarios, run_scenario
from app.core.schemas import Channel
from app.modules.government.auth import require_government_user
from app.modules.government.events import events_after, publish_event, snapshot

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


@router.get("/gobierno/simulador", response_class=HTMLResponse)
def government_simulator_page(
    request: Request,
    _: str = Depends(require_government_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "government/simulator.html",
        {"title": "Simular llamada · Panel gubernamental"},
    )


@router.get("/gobierno/escenarios", response_class=HTMLResponse)
def government_scenarios_page(
    request: Request,
    _: str = Depends(require_government_user),
) -> RedirectResponse:
    return RedirectResponse(url="/gobierno/simulador", status_code=307)


@router.get("/gobierno/reportes", response_class=HTMLResponse)
def government_reports_page(
    request: Request,
    _: str = Depends(require_government_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "government/reports.html",
        {"title": "Reportes y métricas · Panel gubernamental"},
    )


@router.get("/api/gobierno/reportes-resumen")
def government_reports_summary(
    days: int = 30,
    _: str = Depends(require_government_user),
) -> dict[str, Any]:
    return get_government_report_analytics(days=days)


@router.get("/api/gobierno/reportes-guardados")
def government_saved_reports(
    limit: int = 100,
    offset: int = 0,
    _: str = Depends(require_government_user),
) -> dict[str, Any]:
    return {"items": list_government_reports(limit=limit, offset=offset)}


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
def government_saved_report_detail(
    event_id: str,
    _: str = Depends(require_government_user),
) -> dict[str, Any]:
    report = get_government_report(event_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No se encontró un reporte guardado con ese identificador.")
    return {
        "report_version": "demo-1",
        "status": "borrador_no_enviado",
        "synthetic_demo": True,
        "notice": "SIMULADO — sin validez oficial. No se envió a terceros.",
        "report": report,
    }


@router.post("/api/gobierno/reportes/{event_id}/borrador")
def government_prepare_report_draft(
    event_id: str,
    _: str = Depends(require_government_user),
) -> dict[str, Any]:
    report = get_government_report(event_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No se encontró un reporte guardado con ese identificador.")
    if report["report_type"] != "call":
        raise HTTPException(status_code=409, detail="Solo se puede preparar el borrador de una llamada guardada.")
    details = dict(report.get("details") or {})
    if details.get("call_status") == "active":
        raise HTTPException(status_code=409, detail="La llamada debe terminar antes de preparar el borrador.")
    details["draft_status"] = "borrador_exportado"
    record_government_report(
        report_id=report["report_id"],
        report_type=report["report_type"],
        created_at=report["created_at"],
        channel=report["channel"],
        status=report["status"],
        confidence=report["confidence"],
        threat_category=report["threat_category"],
        campaign_id=report["campaign_id"],
        municipality=report["municipality"],
        details=details,
        synthetic=report["synthetic"],
    )
    return {
        "report_version": "demo-1",
        "status": "borrador_no_enviado",
        "synthetic_demo": True,
        "notice": "Borrador de demostración. No se envió a una autoridad.",
        "report": {**report, "details": details},
    }
