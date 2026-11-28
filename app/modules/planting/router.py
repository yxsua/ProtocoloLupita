"""Rutas HTTP y HTML del módulo de siembra y atribución."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.modules.planting.generator import DEFAULT_PERIOD, DEFAULT_SEED
from app.modules.planting.schemas import AttributionResult, SeedBatchSummary, SeedCopyRecord
from app.modules.planting.service import (
    attribute,
    ensure_seeded,
    get_seed_manifest_hash,
    get_seeded_copies,
    reseed_period,
)


APP_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = APP_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["planting"])


class ReseedRequest(BaseModel):
    """Parámetros opcionales para generar o resembrar un periodo sintético."""

    seed_period: str = DEFAULT_PERIOD
    total_copies: int = Field(default=15, ge=1, le=200)
    seed: int = DEFAULT_SEED


def _resolve_base_template() -> str:
    """Usa ``base.html`` de Plan 1 si existe; de lo contrario usa la plantilla base local."""
    if (TEMPLATES_DIR / "base.html").exists():
        return "base.html"
    return "planting/_standalone_base.html"


@router.get("/planting", response_class=HTMLResponse)
def planting_page(request: Request, seed_period: Optional[str] = Query(default=None)) -> HTMLResponse:
    """Renderiza la vista interna de siembra y probador de atribución."""
    ensure_seeded()
    copies = get_seeded_copies(seed_period=seed_period)
    manifest_hash = get_seed_manifest_hash()
    return templates.TemplateResponse(
        request,
        "planting/index.html",
        {
            "base_template": _resolve_base_template(),
            "page_title": "Siembra y Atribución — Mosca Estéril",
            "copies": copies,
            "manifest_hash": manifest_hash,
            "active_period": seed_period or "",
        },
    )


@router.get("/api/planting/copies", response_model=list[SeedCopyRecord])
def api_list_copies(seed_period: Optional[str] = Query(default=None)) -> list[SeedCopyRecord]:
    """Devuelve las copias sembradas (uso interno de Contraloría/tablero)."""
    return get_seeded_copies(seed_period=seed_period)


@router.get("/api/planting/manifest")
def api_manifest_hash() -> dict[str, object]:
    """Publica el hash SHA-256 del manifiesto sin exponer el mapeo secreto."""
    return {
        "manifest_hash": get_seed_manifest_hash(),
        "synthetic": True,
    }


@router.post("/api/planting/seed", response_model=SeedBatchSummary)
def api_reseed(payload: ReseedRequest) -> SeedBatchSummary:
    """Genera de forma determinista un lote sintético para un periodo."""
    return reseed_period(
        seed_period=payload.seed_period,
        total_copies=payload.total_copies,
        seed=payload.seed,
    )


@router.get("/api/planting/attribute", response_model=AttributionResult)
def api_attribute_query(trap_id: str = Query(default="")) -> AttributionResult:
    """Atribuye una copia vía parámetro de consulta (soporta vacío seguro)."""
    return attribute(trap_id)


@router.get("/api/planting/attribute/{trap_id:path}", response_model=AttributionResult)
def api_attribute(trap_id: str) -> AttributionResult:
    """Atribuye una copia exclusivamente a partir del número trampa receptor."""
    return attribute(trap_id)


def get_routers() -> list[APIRouter]:
    """Devuelve los routers del módulo para integración en ``app/main.py``."""
    return [router]


def register_routes(app: FastAPI) -> None:
    """Registra las rutas de siembra y atribución en una instancia FastAPI."""
    app.include_router(router)
