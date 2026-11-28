"""Rutas HTTP y HTML del módulo de siembra y atribución."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.modules.planting.generator import DEFAULT_PERIOD, DEFAULT_SEED
from app.modules.planting.export import build_seed_archive
from app.modules.planting.schemas import AttributionResult, SeedBatchListItem, SeedBatchSummary, SeedCopyRecord
from app.modules.planting.service import (
    attribute,
    ensure_seeded,
    create_seed_batch,
    get_batch_copies,
    get_seed_batches,
    get_seed_manifest_hash,
    get_seeded_copies,
    reseed_period,
)
from app.modules.government.auth import require_government_user


APP_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = APP_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["planting"])


class ReseedRequest(BaseModel):
    """Parámetros opcionales para generar o resembrar un periodo sintético."""

    seed_period: str = DEFAULT_PERIOD
    total_copies: int = Field(default=15, ge=1, le=200)
    seed: int = DEFAULT_SEED


class CreateSeedBatchRequest(BaseModel):
    """Datos para crear un lote nuevo, sin sobrescribir lotes existentes."""

    seed_period: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
    total_copies: int = Field(default=3, ge=1, le=50)


def _resolve_base_template() -> str:
    """Usa ``base.html`` de Plan 1 si existe; de lo contrario usa la plantilla base local."""
    if (TEMPLATES_DIR / "base.html").exists():
        return "base.html"
    return "planting/_standalone_base.html"


@router.get("/planting", response_class=HTMLResponse)
def planting_page(request: Request, seed_period: Optional[str] = Query(default=None)) -> HTMLResponse:
    """Explica en lenguaje público cómo se producen los avisos del prototipo."""
    return templates.TemplateResponse(
        request,
        "planting/index.html",
        {
            "base_template": _resolve_base_template(),
            "page_title": "De dónde vienen los avisos · Protocolo Lupita",
            "active_page": "",
        },
    )


@router.get("/gobierno/siembras", response_class=HTMLResponse)
def government_seed_copies_page(
    request: Request,
    _: str = Depends(require_government_user),
) -> HTMLResponse:
    """Administra lotes y copias SQLite de demostración desde el panel privado."""
    return templates.TemplateResponse(
        request,
        "government/seed-copies.html",
        {"title": "Copias de prueba · Panel gubernamental", "active": "seed-copies"},
    )


@router.get("/api/planting/batches", response_model=list[SeedBatchListItem])
def api_list_seed_batches(_: str = Depends(require_government_user)) -> list[SeedBatchListItem]:
    return get_seed_batches()


@router.post("/api/planting/batches", response_model=SeedBatchListItem, status_code=201)
def api_create_seed_batch(
    payload: CreateSeedBatchRequest,
    _: str = Depends(require_government_user),
) -> SeedBatchListItem:
    try:
        return create_seed_batch(seed_period=payload.seed_period, total_copies=payload.total_copies)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/planting/batches/{seed_period}/download")
def api_download_seed_batch(
    seed_period: str,
    _: str = Depends(require_government_user),
) -> Response:
    copies = get_batch_copies(seed_period)
    if not copies:
        raise HTTPException(status_code=404, detail="No se encontró un lote con copias para descargar.")
    archive_bytes, filename = build_seed_archive(seed_period, copies)
    return Response(
        content=archive_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/planting/copies", response_model=list[SeedCopyRecord])
def api_list_copies(
    seed_period: Optional[str] = Query(default=None),
    _: str = Depends(require_government_user),
) -> list[SeedCopyRecord]:
    """Devuelve las copias sembradas (uso interno de Contraloría/tablero)."""
    return get_seeded_copies(seed_period=seed_period)


@router.get("/api/planting/manifest")
def api_manifest_hash(_: str = Depends(require_government_user)) -> dict[str, object]:
    """Publica el hash SHA-256 del manifiesto sin exponer el mapeo secreto."""
    return {
        "manifest_hash": get_seed_manifest_hash(),
        "synthetic": True,
    }


@router.post("/api/planting/seed", response_model=SeedBatchSummary)
def api_reseed(payload: ReseedRequest, _: str = Depends(require_government_user)) -> SeedBatchSummary:
    """Genera de forma determinista un lote sintético para un periodo."""
    return reseed_period(
        seed_period=payload.seed_period,
        total_copies=payload.total_copies,
        seed=payload.seed,
    )


@router.get("/api/planting/attribute", response_model=AttributionResult)
def api_attribute_query(
    trap_id: str = Query(default=""),
    _: str = Depends(require_government_user),
) -> AttributionResult:
    """Atribuye una copia vía parámetro de consulta (soporta vacío seguro)."""
    return attribute(trap_id)


@router.get("/api/planting/attribute/{trap_id:path}", response_model=AttributionResult)
def api_attribute(trap_id: str, _: str = Depends(require_government_user)) -> AttributionResult:
    """Atribuye una copia exclusivamente a partir del número trampa receptor."""
    return attribute(trap_id)


def get_routers() -> list[APIRouter]:
    """Devuelve los routers del módulo para integración en ``app/main.py``."""
    return [router]


def register_routes(app: FastAPI) -> None:
    """Registra las rutas de siembra y atribución en una instancia FastAPI."""
    app.include_router(router)
