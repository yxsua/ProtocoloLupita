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


@router.get("/api/public/map")
def api_public_map() -> dict[str, object]:
    """Entrega al panel público solo las zonas que cumplen el mínimo de publicación."""
    summary = get_map_summary()
    visible = [
        {"name": item.municipality_name, "count": item.count}
        for item in summary.municipalities
        if not item.suppressed and item.count is not None and item.count >= summary.threshold
    ]
    visible_names = {item["name"] for item in visible}
    features = []
    for feature in summary.geojson.get("features", []):
        name = feature.get("properties", {}).get("municipality_name")
        features.append({
            "type": feature.get("type", "Feature"),
            "geometry": feature.get("geometry"),
            "properties": {"published": name in visible_names},
        })
    return {
        "threshold": summary.threshold,
        "visible_areas": visible,
        "geojson": {"type": "FeatureCollection", "features": features},
    }


def get_routers() -> list[APIRouter]:
    """Devuelve los routers del módulo de mapa."""
    return [router]


def register_routes(app: FastAPI) -> None:
    """Registra las rutas del mapa en una instancia FastAPI."""
    app.include_router(router)
