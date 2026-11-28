"""Orquestador principal del motor de inteligencia (process_event y consultas)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.modules.evidence import ChainVerificationResult, EvidenceStore
from app.modules.intel.campaigns import CampaignIndex
from app.modules.intel.confidence import (
    build_authority_package,
    build_epidemiological_bulletin,
    build_impersonated_brand_notice,
    build_institutional_package,
    evaluate_confidence,
)
from app.modules.intel.contracts import (
    AccountVerification,
    CampaignSummary,
    EventInput,
    EventResult,
    ExtractedIndicator,
    Indicator,
    LookupResult,
    coerce_event_input,
)
from app.modules.intel.extractors import (
    build_template_signature,
    classify_threat,
    compute_value_hash,
    extract_indicators,
)
from app.modules.intel.validators import verify_account


class IntelEngine:
    """Motor autónomo que conecta extracción, campañas, confianza y cadena de evidencia."""

    def __init__(self, evidence_db_path: Optional[str | Path] = None) -> None:
        self.campaigns = CampaignIndex()
        self.evidence = EvidenceStore(db_path=evidence_db_path)

    def process_event(self, raw_event: EventInput | dict[str, Any] | Any) -> EventResult:
        """Procesa un evento sanitizado y devuelve EventResult con evidencia encadenada."""
        event = coerce_event_input(raw_event)
        extracted = extract_indicators(event.text_sanitized, channel=event.channel)

        if event.origin_phone_masked:
            extracted.append(
                ExtractedIndicator(
                    type="origin_phone",
                    value_masked=event.origin_phone_masked,
                    value_hash=compute_value_hash("origin_phone", event.origin_phone_masked),
                    is_primary_correlator=False,
                    valid=None,
                    validation_detail="secondary_untrusted_caller_id",
                )
            )

        threat_category, legal_tag, threat_reasons = classify_threat(
            event.text_sanitized,
            event.channel,
            extracted,
        )

        has_actionable_indicator = any(
            ind.type in ("clabe", "card", "url", "requested_data")
            for ind in extracted
        )

        # E08: llamada o evento legítimo sin amenaza ni indicadores de cobro
        if (
            threat_category == "no_aplica"
            and not has_actionable_indicator
            and not event.rate_limited
            and not event.force_unverified
        ):
            sanitized_payload = {
                "event_id": event.event_id,
                "occurred_at": event.occurred_at,
                "channel": event.channel,
                "trap_id": event.trap_id,
                "status": "sin_alerta",
                "threat_category": "no_aplica",
                "synthetic": event.synthetic,
            }
            rec = self.evidence.append(
                event_id=event.event_id,
                occurred_at=event.occurred_at,
                sanitized_payload=sanitized_payload,
            )
            return EventResult(
                event_id=event.event_id,
                campaign_id=None,
                status="sin_alerta",
                confidence=0.0,
                confidence_level="ninguna",
                threat_category="no_aplica",
                legal_tag="sin_tipificacion",
                claimed_brand=event.claimed_brand_hint,
                requested_data=[],
                indicators=[],
                evidence_hash=rec.record_hash,
                evidence_seq=rec.seq,
                match_reason="no_threat_detected",
                reasons=threat_reasons,
                synthetic=event.synthetic,
            )

        claimed_brands = [
            ind.value_masked for ind in extracted if ind.type == "brand"
        ]
        if event.claimed_brand_hint and event.claimed_brand_hint not in claimed_brands:
            claimed_brands.append(event.claimed_brand_hint)

        requested_data = [
            ind.value_masked for ind in extracted if ind.type == "requested_data"
        ]

        template_str, template_shingles = build_template_signature(event.text_sanitized)
        camp, match_reason = self.campaigns.register_or_update(
            event=event,
            extracted=extracted,
            threat_category=threat_category,
            legal_tag=legal_tag,
            template_str=template_str,
            template_shingles=template_shingles,
            claimed_brands=claimed_brands,
        )

        if event.rate_limited or event.force_unverified:
            status, confidence, confidence_level, conf_reasons = evaluate_confidence(
                independent_sources_count=len(camp.independent_sources),
                channels_observed=camp.channels_observed,
                has_valid_financial=camp.has_valid_financial,
                has_sensitive_request=camp.has_sensitive_request,
                rate_limited=event.rate_limited,
                force_unverified=event.force_unverified,
            )
            event_match_reason = "unverified_override"
        else:
            status, confidence, confidence_level, conf_reasons = evaluate_confidence(
                independent_sources_count=len(camp.independent_sources),
                channels_observed=camp.channels_observed,
                has_valid_financial=camp.has_valid_financial,
                has_sensitive_request=camp.has_sensitive_request,
            )
            camp.status = status
            camp.confidence = confidence
            camp.confidence_level = confidence_level
            event_match_reason = match_reason

        public_indicators: list[Indicator] = []
        for idx, ext in enumerate(extracted, start=1):
            ind_id = f"{event.event_id}-ind-{idx}"
            pub = ext.to_public_indicator(
                indicator_id=ind_id,
                source_event_id=event.event_id,
                confidence=confidence,
                status=status,
            )
            public_indicators.append(pub)
            if not event.rate_limited and not event.force_unverified:
                dedup_key = f"{ext.type}:{ext.value_hash}"
                camp.indicators_by_key[dedup_key] = pub

        sanitized_payload = {
            "event_id": event.event_id,
            "occurred_at": event.occurred_at,
            "channel": event.channel,
            "trap_id": event.trap_id,
            "attribution_id": event.attribution_id,
            "campaign_id": camp.campaign_id,
            "status": status,
            "confidence": confidence,
            "threat_category": threat_category,
            "legal_tag": legal_tag,
            "template_signature": template_str,
            "indicators": [ind.to_dict() for ind in public_indicators],
            "synthetic": event.synthetic,
        }
        rec = self.evidence.append(
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            sanitized_payload=sanitized_payload,
        )

        if not event.rate_limited and not event.force_unverified:
            if not any(ref["event_id"] == event.event_id for ref in camp.event_refs):
                camp.event_refs.append(
                    {
                        "event_id": event.event_id,
                        "seq": rec.seq,
                        "evidence_hash": rec.record_hash,
                        "channel": event.channel,
                        "occurred_at": event.occurred_at,
                    }
                )

        all_reasons = threat_reasons + conf_reasons
        return EventResult(
            event_id=event.event_id,
            campaign_id=camp.campaign_id,
            status=status,
            confidence=confidence,
            confidence_level=confidence_level,
            threat_category=threat_category,
            legal_tag=legal_tag,
            claimed_brand=claimed_brands[0] if claimed_brands else None,
            requested_data=requested_data,
            indicators=public_indicators,
            evidence_hash=rec.record_hash,
            evidence_seq=rec.seq,
            match_reason=event_match_reason,
            reasons=all_reasons,
            synthetic=event.synthetic,
        )

    def lookup_indicator(self, query: str) -> LookupResult:
        """Consulta en lenguaje simple si un indicador o texto pertenece a una campaña."""
        return self.campaigns.lookup(query)

    def get_campaign(self, campaign_id: str) -> Optional[CampaignSummary]:
        """Devuelve el resumen consolidado de una campaña."""
        camp = self.campaigns.get(campaign_id)
        return camp.to_summary() if camp is not None else None

    def list_campaigns(self) -> list[CampaignSummary]:
        """Lista todas las campañas detectadas."""
        return self.campaigns.list_summaries()

    def get_institutional_package(self, campaign_id: str) -> Optional[dict[str, Any]]:
        """Construye el paquete de indicadores sintético para una campaña."""
        camp = self.campaigns.get(campaign_id)
        if camp is None:
            return None
        return build_institutional_package(camp.to_summary(), camp.event_refs)

    def get_authority_package(self, campaign_id: str) -> Optional[dict[str, Any]]:
        """Construye el paquete simulado orientado a Fiscalía / UIF / Policía Cibernética."""
        camp = self.campaigns.get(campaign_id)
        if camp is None:
            return None
        return build_authority_package(camp.to_summary(), camp.event_refs)

    def get_impersonated_brand_notice(self, campaign_id: str) -> Optional[dict[str, Any]]:
        """Construye el aviso para institución suplantada con URLs desactivadas."""
        camp = self.campaigns.get(campaign_id)
        if camp is None:
            return None
        return build_impersonated_brand_notice(camp.to_summary())

    def get_epidemiological_bulletin(self) -> dict[str, Any]:
        """Construye el boletín epidemiológico semanal de campañas activas."""
        return build_epidemiological_bulletin(self.list_campaigns())

    def verify_evidence_integrity(self) -> ChainVerificationResult:
        """Verifica la cadena ordenada de hashes de evidencia."""
        return self.evidence.verify_integrity()


_DEFAULT_ENGINE = IntelEngine()


def get_default_engine() -> IntelEngine:
    """Devuelve la instancia compartida por defecto del motor de inteligencia."""
    return _DEFAULT_ENGINE


def reset_default_engine(evidence_db_path: Optional[str | Path] = None) -> IntelEngine:
    """Reinicia el motor por defecto (útil para pruebas y corrida limpia de escenarios)."""
    global _DEFAULT_ENGINE
    _DEFAULT_ENGINE = IntelEngine(evidence_db_path=evidence_db_path)
    return _DEFAULT_ENGINE


def process_event(
    event: EventInput | dict[str, Any] | Any,
    engine: Optional[IntelEngine] = None,
) -> EventResult:
    """Contrato común process_event(event) -> EventResult."""
    target = engine or _DEFAULT_ENGINE
    return target.process_event(event)


def lookup_indicator(
    query: str,
    engine: Optional[IntelEngine] = None,
) -> LookupResult:
    """Consulta ciudadana contra campañas activas."""
    target = engine or _DEFAULT_ENGINE
    return target.lookup_indicator(query)


__all__ = [
    "IntelEngine",
    "extract_indicators",
    "get_default_engine",
    "lookup_indicator",
    "process_event",
    "reset_default_engine",
    "verify_account",
    "AccountVerification",
]
