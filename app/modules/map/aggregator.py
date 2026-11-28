"""Agregador offline del mapa de los 18 municipios de Querétaro.

Aplica el umbral mínimo de 5 reportes por municipio en el backend antes de
serializar la respuesta al frontend, conservando los municipios suprimidos
dentro del agregado estatal (``state_total``).
"""

from __future__ import annotations

import copy
import json
import unicodedata
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.db import list_citizen_report_municipality_counts
from app.modules.map.schemas import MunicipalityAggregate, StateMapSummary
from app.modules.planting.fixtures_local import QUERETARO_MUNICIPALITIES


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GEOJSON_PATH = REPO_ROOT / "data" / "geo" / "municipios_18.geojson"
PUBLICATION_THRESHOLD = 5


def _municipality_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char)).split()
    )


def load_queretaro_geojson(geojson_path: Optional[Path] = None) -> dict[str, Any]:
    """Carga el GeoJSON local empaquetado de los 18 municipios de Querétaro."""
    target = geojson_path or DEFAULT_GEOJSON_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def _load_citizen_counts() -> list[dict[str, Any]]:
    """Lee conteos de reportes ciudadanos saneados guardados en SQLite."""
    return list_citizen_report_municipality_counts()


def get_map_summary(
    *,
    threshold: int = PUBLICATION_THRESHOLD,
    geojson_path: Optional[Path] = None,
    counts_provider: Optional[Callable[[], list[dict[str, Any]]]] = None,
) -> StateMapSummary:
    """Calcula el agregado estatal y aplica supresión municipal para conteos ``< threshold``."""
    raw_counts = counts_provider() if counts_provider is not None else _load_citizen_counts()
    name_to_code = {
        _municipality_key(m["municipality_name"]): m["municipality_code"]
        for m in QUERETARO_MUNICIPALITIES
    }
    counts_by_code: dict[str, int] = {}
    excluded_rate_limited = 0

    for entry in raw_counts:
        code = str(entry.get("municipality_code") or "").strip()
        if not code and entry.get("municipality_name"):
            code = name_to_code.get(_municipality_key(str(entry["municipality_name"])), "")
        val = max(0, int(entry.get("count", 0) or 0))
        excluded_rate_limited += max(0, int(entry.get("rate_limited_excluded", 0) or 0))
        if code:
            counts_by_code[code] = counts_by_code.get(code, 0) + val

    municipalities: list[MunicipalityAggregate] = []
    by_code_view: dict[str, MunicipalityAggregate] = {}
    state_total = 0
    suppressed_count = 0
    visible_count = 0

    for muni in QUERETARO_MUNICIPALITIES:
        code = muni["municipality_code"]
        name = muni["municipality_name"]
        raw_total = counts_by_code.get(code, 0)
        state_total += raw_total

        if 0 < raw_total < threshold:
            agg = MunicipalityAggregate(
                municipality_code=code,
                municipality_name=name,
                count=None,
                suppressed=True,
                display_label=f"Suprimido (<{threshold} reportes)",
            )
            suppressed_count += 1
        else:
            agg = MunicipalityAggregate(
                municipality_code=code,
                municipality_name=name,
                count=raw_total,
                suppressed=False,
                display_label=f"{raw_total} reportes",
            )
            if raw_total >= threshold:
                visible_count += 1

        municipalities.append(agg)
        by_code_view[code] = agg

    geojson = copy.deepcopy(load_queretaro_geojson(geojson_path=geojson_path))
    for feature in geojson.get("features", []):
        props = feature.setdefault("properties", {})
        code = str(props.get("municipality_code", ""))
        agg = by_code_view.get(code)
        if agg is not None:
            props["count"] = agg.count
            props["suppressed"] = agg.suppressed
            props["display_label"] = agg.display_label

    return StateMapSummary(
        state_code="22",
        state_name="Querétaro",
        threshold=threshold,
        state_total=state_total,
        suppressed_municipalities_count=suppressed_count,
        visible_municipalities_count=visible_count,
        excluded_rate_limited_count=excluded_rate_limited,
        municipalities=municipalities,
        geojson=geojson,
        synthetic=False,
    )
