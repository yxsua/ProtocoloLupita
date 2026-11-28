"""Servicio de lectura y agregación del tablero de Mosca Estéril.

Consume atribuciones desde ``planting`` y lee eventos, indicadores y campañas
desde el motor de inteligencia (Plan 4) sin recalcular ni promover niveles de
confianza.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from app.modules.dashboard.schemas import (
    AttributedEventView,
    CampaignSummary,
    DashboardFilters,
    DashboardResponse,
    DashboardSummaryMetrics,
)
from app.modules.planting.fixtures_local import (
    SAMPLE_CAMPAIGNS,
    SAMPLE_EVENTS,
    SAMPLE_INDICATORS,
)
from app.modules.planting.service import (
    attribute,
    ensure_seeded,
    get_seed_manifest_hash,
    get_seeded_copies,
)


def _load_intel_sources() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Obtiene eventos, indicadores y campañas desde Plan 4 si está integrado; si no, usa fixtures."""
    try:  # pragma: no cover - integración con Plan 4 cuando exista
        from app.modules.intel.router import list_campaigns, list_events, list_indicators

        events = [dict(item) for item in list_events()]
        indicators = {item["id"]: dict(item) for item in list_indicators()}
        campaigns = [dict(item) for item in list_campaigns()]
        return events, indicators, campaigns
    except ImportError:
        return (
            [dict(item) for item in SAMPLE_EVENTS],
            {k: dict(v) for k, v in SAMPLE_INDICATORS.items()},
            [dict(item) for item in SAMPLE_CAMPAIGNS],
        )


def _build_explanation(event: dict[str, Any], attr_dict: dict[str, Any]) -> str:
    channel_labels = {"call": "llamada", "sms": "SMS", "portal": "portal ciudadano"}
    ch_label = channel_labels.get(str(event.get("channel", "")), str(event.get("channel", "")))
    if attr_dict["status"] == "atribuido":
        return (
            f"Evento {event['id']} recibido por {ch_label} en trampa {attr_dict['trap_display']} "
            f"→ atribuido a {attr_dict['copy_id']} ({attr_dict['provider']}). "
            f"Estado recibido del motor: {event.get('status')} (confianza {event.get('confidence')})."
        )
    return (
        f"Evento {event['id']} recibido por {ch_label} sin número trampa sembrado "
        f"({attr_dict['trap_display']}). Estado recibido del motor: {event.get('status')} "
        f"(confianza {event.get('confidence')})."
    )


def get_dashboard(
    filters: Optional[DashboardFilters | dict[str, Any]] = None,
    *,
    db_path: Optional[str | Path] = None,
    data_provider: Optional[Callable[[], tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]]] = None,
) -> DashboardResponse:
    """Construye la vista del tablero aplicando filtros sin alterar las clasificaciones de inteligencia."""
    active_filters = (
        filters
        if isinstance(filters, DashboardFilters)
        else DashboardFilters(**(filters or {}))
    )

    ensure_seeded(db_path=db_path)
    seeded_copies = get_seeded_copies(db_path=db_path)
    manifest_hash = get_seed_manifest_hash(db_path=db_path)

    raw_events, indicators_map, raw_campaigns = (
        data_provider() if data_provider is not None else _load_intel_sources()
    )

    attributed_views: list[AttributedEventView] = []
    for event in sorted(raw_events, key=lambda item: str(item.get("occurred_at", "")), reverse=True):
        trap_id = event.get("trap_id")
        attr = attribute(trap_id, db_path=db_path)
        attr_data = attr.model_dump()

        if active_filters.channel and event.get("channel") != active_filters.channel:
            continue
        if active_filters.seed_period and attr.seed_period != active_filters.seed_period:
            continue
        if active_filters.campaign_id and event.get("campaign_id") != active_filters.campaign_id:
            continue
        if active_filters.status and event.get("status") != active_filters.status:
            continue
        if active_filters.confidence and event.get("confidence") != active_filters.confidence:
            continue

        ind_ids = list(event.get("indicator_ids") or [])
        masked_values = [
            str(indicators_map[ind_id].get("value_masked", ind_id))
            for ind_id in ind_ids
            if ind_id in indicators_map
        ]

        attributed_views.append(
            AttributedEventView(
                event_id=str(event["id"]),
                occurred_at=str(event.get("occurred_at", "")),
                channel=str(event.get("channel", "")),
                trap_id=trap_id,
                trap_display=attr.trap_display or "Sin número trampa",
                attribution_status=attr.status,
                copy_id=attr.copy_id,
                provider=attr.provider,
                seed_period=attr.seed_period,
                persona_alias=attr.persona_alias,
                campaign_id=event.get("campaign_id"),
                status=str(event.get("status", "sin_verificar")),
                confidence=str(event.get("confidence", "baja")),
                indicator_ids=ind_ids,
                masked_indicators=masked_values,
                evidence_hash=event.get("evidence_hash"),
                explanation=_build_explanation(event, attr_data),
                synthetic=True,
            )
        )

    attributed_views = attributed_views[: active_filters.limit]

    campaigns: list[CampaignSummary] = []
    for camp in raw_campaigns:
        if active_filters.campaign_id and camp.get("campaign_id") != active_filters.campaign_id:
            continue
        if active_filters.status and camp.get("status") != active_filters.status:
            continue
        if active_filters.confidence and camp.get("confidence") != active_filters.confidence:
            continue
        if active_filters.channel and active_filters.channel not in (camp.get("channels") or []):
            continue
        campaigns.append(CampaignSummary(**camp))

    lead_times = [c.lead_time_hours for c in campaigns if c.lead_time_hours is not None]
    best_lead_time = min(lead_times) if lead_times else None

    attributed_count = sum(1 for row in attributed_views if row.attribution_status == "atribuido")
    unattributed_count = sum(1 for row in attributed_views if row.attribution_status == "no_atribuido")

    empty_state = None
    if not attributed_views:
        has_filters = any(
            [
                active_filters.channel,
                active_filters.seed_period,
                active_filters.campaign_id,
                active_filters.status,
                active_filters.confidence,
            ]
        )
        empty_state = (
            "No hay eventos que coincidan con los filtros seleccionados."
            if has_filters
            else "Aún no hay eventos sintéticos registrados en el tablero."
        )

    return DashboardResponse(
        summary=DashboardSummaryMetrics(
            total_events=len(attributed_views),
            attributed_events=attributed_count,
            unattributed_events=unattributed_count,
            active_campaigns=sum(1 for c in campaigns if c.status != "sin_verificar"),
            seeded_copies=len(seeded_copies),
            seed_manifest_hash=manifest_hash,
            best_lead_time_hours=best_lead_time,
        ),
        attributions=attributed_views,
        campaigns=campaigns,
        empty_state=empty_state,
        filters_applied=active_filters,
        synthetic=True,
    )
