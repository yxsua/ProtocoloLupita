"""Esquemas Pydantic para el tablero de trazabilidad y boletín epidemiológico."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


ConfidenceLevel = Literal["baja", "media", "alta"]
IntelStatus = Literal["indicio", "corroborado", "sin_verificar"]


class DashboardFilters(BaseModel):
    """Filtros soportados por ``get_dashboard(filters)``."""

    channel: Optional[Literal["call", "sms", "portal"]] = None
    seed_period: Optional[str] = None
    campaign_id: Optional[str] = None
    status: Optional[str] = None
    confidence: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)


class AttributedEventView(BaseModel):
    """Fila explicada de evento atribuido en el tablero (sin reclasificar)."""

    event_id: str
    occurred_at: str
    channel: str
    trap_id: Optional[str] = None
    trap_display: str
    attribution_status: Literal["atribuido", "no_atribuido"]
    copy_id: Optional[str] = None
    provider: Optional[str] = None
    seed_period: Optional[str] = None
    persona_alias: Optional[str] = None
    campaign_id: Optional[str] = None
    status: str
    confidence: str
    indicator_ids: list[str] = Field(default_factory=list)
    masked_indicators: list[str] = Field(default_factory=list)
    evidence_hash: Optional[str] = None
    explanation: str
    synthetic: bool = True


class CampaignSummary(BaseModel):
    """Resumen de campaña recibido desde el motor de inteligencia."""

    campaign_id: str
    title: str
    brand: str
    channels: list[str] = Field(default_factory=list)
    event_count: int = 0
    traps_reached_count: int = 0
    script_variants: list[str] = Field(default_factory=list)
    first_trap_contact_at: Optional[str] = None
    first_citizen_report_at: Optional[str] = None
    lead_time_hours: Optional[float] = None
    confidence: str
    status: str
    indicator_ids: list[str] = Field(default_factory=list)
    simulated_third_party_notice: str = "Simulado (prototipo): sin envío real a bancos, telefónica, UIF o Fiscalía"


class DashboardSummaryMetrics(BaseModel):
    """Indicadores agregados superiores del tablero."""

    total_events: int = 0
    attributed_events: int = 0
    unattributed_events: int = 0
    active_campaigns: int = 0
    seeded_copies: int = 0
    seed_manifest_hash: str = ""
    best_lead_time_hours: Optional[float] = None
    synthetic_notice: str = "Datos 100% sintéticos (modo offline)"


class DashboardResponse(BaseModel):
    """Respuesta completa de ``get_dashboard(filters)``."""

    summary: DashboardSummaryMetrics
    attributions: list[AttributedEventView] = Field(default_factory=list)
    campaigns: list[CampaignSummary] = Field(default_factory=list)
    empty_state: Optional[str] = None
    filters_applied: DashboardFilters = Field(default_factory=DashboardFilters)
    synthetic: bool = True
