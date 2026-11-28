"""Esquemas Pydantic para el mapa agregado de los 18 municipios de Querétaro."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class MunicipalityAggregate(BaseModel):
    """Estado de publicación de un municipio aplicando el umbral mínimo."""

    municipality_code: str
    municipality_name: str
    count: Optional[int] = None
    suppressed: bool = False
    display_label: str


class StateMapSummary(BaseModel):
    """Respuesta de ``get_map_summary()`` y ``GET /api/map``."""

    state_code: str = "22"
    state_name: str = "Querétaro"
    threshold: int = 5
    state_total: int = 0
    suppressed_municipalities_count: int = 0
    visible_municipalities_count: int = 0
    excluded_rate_limited_count: int = 0
    municipalities: list[MunicipalityAggregate] = Field(default_factory=list)
    geojson: dict[str, Any] = Field(default_factory=dict)
    synthetic: bool = True
