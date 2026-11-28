"""Rutas HTTP del mapa agregado offline de los 18 municipios de Querétaro."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app.modules.map.aggregator import get_map_summary
from app.modules.map.schemas import StateMapSummary


router = APIRouter(tags=["map"])


@router.get("/api/map", response_model=StateMapSummary)
def api_map_summary() -> StateMapSummary:
    """Devuelve el GeoJSON de los 18 municipios con el umbral mínimo aplicado en backend."""
    return get_map_summary()


def get_routers() -> list[APIRouter]:
    """Devuelve los routers del módulo de mapa."""
    return [router]


def register_routes(app: FastAPI) -> None:
    """Registra las rutas del mapa en una instancia FastAPI."""
    app.include_router(router)
