"""Módulo de tablero de trazabilidad y campañas (Plan 2)."""

from app.modules.dashboard.router import get_routers, register_routes, router
from app.modules.dashboard.schemas import (
    AttributedEventView,
    CampaignSummary,
    DashboardFilters,
    DashboardResponse,
    DashboardSummaryMetrics,
)
from app.modules.dashboard.service import get_dashboard

__all__ = [
    "AttributedEventView",
    "CampaignSummary",
    "DashboardFilters",
    "DashboardResponse",
    "DashboardSummaryMetrics",
    "get_dashboard",
    "get_routers",
    "register_routes",
    "router",
]
