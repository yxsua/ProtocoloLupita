"""Módulo de mapa municipal offline con umbral de privacidad (Plan 2)."""

from app.modules.map.aggregator import PUBLICATION_THRESHOLD, get_map_summary, load_queretaro_geojson
from app.modules.map.router import get_routers, register_routes, router
from app.modules.map.schemas import MunicipalityAggregate, StateMapSummary

__all__ = [
    "MunicipalityAggregate",
    "PUBLICATION_THRESHOLD",
    "StateMapSummary",
    "get_map_summary",
    "get_routers",
    "load_queretaro_geojson",
    "register_routes",
    "router",
]
