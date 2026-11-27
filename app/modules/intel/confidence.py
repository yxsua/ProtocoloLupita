"""Reglas de confianza por corroboración y generadores de productos institucionales."""

from __future__ import annotations

from typing import Any

from app.modules.intel.contracts import (
    CampaignSummary,
    Channel,
    ConfidenceLevel,
    IntelStatus,
)

MAX_CONFIDENCE = 0.90

NON_COERCION_NOTICE = (
    "Paquete sintético de demostración; el sistema reporta indicios y no bloquea "
    "líneas ni congela cuentas por sí mismo. Las medidas coercitivas corresponden "
    "exclusivamente a la autoridad competente y a las instituciones financieras."
)


def evaluate_confidence(
    independent_sources_count: int,
    channels_observed: list[Channel],
    has_valid_financial: bool,
    has_sensitive_request: bool,
    rate_limited: bool = False,
    force_unverified: bool = False,
) -> tuple[IntelStatus, float, ConfidenceLevel, list[str]]:
    """Calcula estado y confianza sin convertir una sola coincidencia en fraude confirmado."""
    if rate_limited or force_unverified:
        return (
            "sin_verificar",
            0.0,
            "baja",
            ["Evento retenido en estado sin_verificar por límite de tasa o revisión pendiente."],
        )

    if independent_sources_count <= 0:
        return (
            "sin_verificar",
            0.0,
            "baja",
            ["Sin fuentes independientes válidas; permanece como sin_verificar."],
        )

    if independent_sources_count == 1:
        score = 0.30
        if has_valid_financial and has_sensitive_request:
            score = 0.35
        return (
            "indicio",
            score,
            "baja",
            [
                "Indicio único pendiente de corroboración independiente; "
                "no se etiqueta como fraude confirmado."
            ],
        )

    # 2 o más fuentes independientes: sube nivel a corroborada (tope 0.90)
    score = 0.65
    if len(set(channels_observed)) >= 2:
        score += 0.10
    if independent_sources_count >= 3:
        score += 0.05
    if has_valid_financial:
        score += 0.05
    score = round(min(score, MAX_CONFIDENCE), 2)

    level: ConfidenceLevel = "alta" if score >= 0.75 else "media"
    return (
        "corroborada",
        score,
        level,
        [
            f"Campaña corroborada por {independent_sources_count} fuentes independientes "
            f"(confianza {score:.2f}, sin afirmación de fraude confirmado)."
        ],
    )


def build_institutional_package(
    campaign: CampaignSummary,
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Genera paquete sintético general de indicadores para demostración y reporte."""
    return {
        "package_version": "1.0-demo",
        "synthetic": True,
        "simulated_report": True,
        "notice": NON_COERCION_NOTICE,
        "campaign_id": campaign.campaign_id,
        "status": campaign.status,
        "confidence": campaign.confidence,
        "confidence_level": campaign.confidence_level,
        "threat_category": campaign.threat_category,
        "legal_tag": campaign.legal_tag,
        "independent_sources_count": campaign.independent_sources_count,
        "traps_reached_count": campaign.traps_reached_count,
        "channels_observed": list(campaign.channels_observed),
        "claimed_brands": list(campaign.claimed_brands),
        "indicators": [ind.to_dict() for ind in campaign.indicators],
        "template_variants": list(campaign.template_variants),
        "first_trap_seen_at": campaign.first_trap_seen_at,
        "first_citizen_report_at": campaign.first_citizen_report_at,
        "detection_lead_hours": campaign.detection_lead_hours,
        "evidence_refs": list(evidence_refs),
    }


def build_authority_package(
    campaign: CampaignSummary,
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Genera paquete orientado a Fiscalía / Policía Cibernética / UIF."""
    pkg = build_institutional_package(campaign, evidence_refs)
    pkg["target_audience"] = "autoridad_competente_uif_fiscalia"
    pkg["action_scope"] = "Solo entrega de indicios y hashes verificables; sin bloqueo ni congelamiento automático."
    return pkg


def build_impersonated_brand_notice(campaign: CampaignSummary) -> dict[str, Any]:
    """Genera aviso enfocado a institución suplantada (dominio desactivado y plantilla)."""
    defanged_urls = [
        ind.value_masked
        for ind in campaign.indicators
        if ind.type == "url"
    ]
    return {
        "package_version": "1.0-demo",
        "synthetic": True,
        "simulated_report": True,
        "target_audience": "institucion_suplantada",
        "campaign_id": campaign.campaign_id,
        "status": campaign.status,
        "confidence_level": campaign.confidence_level,
        "claimed_brands": list(campaign.claimed_brands),
        "defanged_urls": defanged_urls,
        "template_variants": list(campaign.template_variants),
        "notice": "Enlaces entregados en formato desactivado hxxp; no abrir fuera de entorno aislado.",
    }


def build_epidemiological_bulletin(campaigns: list[CampaignSummary]) -> dict[str, Any]:
    """Genera boletín semanal de campañas activas excluyendo eventos sin verificar."""
    published = [
        {
            "campaign_id": camp.campaign_id,
            "status": camp.status,
            "confidence_level": camp.confidence_level,
            "threat_category": camp.threat_category,
            "claimed_brands": list(camp.claimed_brands),
            "channels_observed": list(camp.channels_observed),
            "traps_reached_count": camp.traps_reached_count,
            "independent_sources_count": camp.independent_sources_count,
            "template_variants": list(camp.template_variants),
            "detection_lead_hours": camp.detection_lead_hours,
        }
        for camp in campaigns
        if camp.status in ("indicio", "corroborada")
    ]
    return {
        "bulletin_version": "1.0-demo",
        "synthetic": True,
        "privacy_guarantee": "Sin audios ni datos personales ciudadanos.",
        "active_campaigns_count": len(published),
        "campaigns": published,
    }
