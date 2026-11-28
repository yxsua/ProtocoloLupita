"""Módulo ciudadano con exports perezosos para interoperar con SMS."""

from app.modules.citizen.schemas import (
    CitizenReportRaw,
    CitizenResponse,
    MapAggregateResponse,
    MunicipalAggregate,
    ReportInput,
)

__all__ = [
    "CitizenReportRaw",
    "CitizenResponse",
    "MapAggregateResponse",
    "MunicipalAggregate",
    "ReportInput",
    "get_map_aggregates",
    "submit_report",
]


def __getattr__(name: str):
    if name in {"get_map_aggregates", "submit_report"}:
        from app.modules.citizen import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
