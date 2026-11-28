"""Adaptador por contrato hacia process_event (Integrantes 1 y 4) y tope de certeza."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from app.modules.intel.contracts import EventInput
from app.modules.intel.service import IntelEngine, get_default_engine
from app.modules.sms.schemas import (
    EngineEventInput,
    EngineVerdict,
    VerificationStatus,
)


class IntelligenceEnginePort(Protocol):
    """Contrato desacoplado para invocar process_event del motor de inteligencia."""

    def process_event(self, event: EngineEventInput) -> EngineVerdict:
        ...


@dataclass(slots=True)
class CampaignRecord:
    """Registro interno de campaña dentro del adaptador local."""

    campaign_id: str
    campaign_name: str
    entity: str
    indicators: set[str] = field(default_factory=set)
    event_count: int = 0
    matched_scenario: str | None = None


class LocalIntelligenceAdapter:
    """Adaptador local por contrato para desarrollo y pruebas independientes.

    Viene precargado con la campaña E01 para validar el cruce de indicadores (E12),
    y crea/actualiza campañas de forma determinista sin declarar fraude confirmado
    de forma unilateral.
    """

    def __init__(self) -> None:
        self._campaigns: dict[str, CampaignRecord] = {
            "CAMP-E01": CampaignRecord(
                campaign_id="CAMP-E01",
                campaign_name="Suplantacion bancaria E01 (cargo no reconocido)",
                entity="banco",
                indicators={
                    "5511223344",
                    "012180009988776655",
                    "banco-seguro-ayuda.xyz",
                    "hxxps://banco-seguro-ayuda.xyz/verificacion",
                },
                event_count=6,
                matched_scenario="E01",
            )
        }
        self._seq = 1

    def _collect_event_keys(self, event: EngineEventInput) -> set[str]:
        keys: set[str] = set()
        for val in (
            event.indicators.domains
            + event.indicators.phones
            + event.indicators.accounts
            + event.indicators.defanged_urls
            + event.indicators.senders
        ):
            norm = val.strip().lower()
            if norm:
                keys.add(norm)
        return keys

    def process_event(self, event: EngineEventInput) -> EngineVerdict:
        # Si esta limitado por tasa, no crea ni infla campañas ni confirma indicios
        if event.rate_limited:
            return EngineVerdict(
                campaign_id=None,
                campaign_name=None,
                status="sin_verificar",
                confidence=0.15,
                corroborated_matches=0,
                notes="Evento marcado como sin verificar por limite de tasa.",
            )

        keys = self._collect_event_keys(event)

        # 1. Buscar coincidencia con campañas existentes (ej. E01 en E12)
        for camp in self._campaigns.values():
            overlap = keys & camp.indicators
            if overlap:
                camp.event_count += 1
                camp.indicators.update(keys)
                confidence = min(0.92, 0.76 + 0.02 * min(camp.event_count, 8))
                return EngineVerdict(
                    campaign_id=camp.campaign_id,
                    campaign_name=camp.campaign_name,
                    status="campana_corroborada",
                    confidence=round(confidence, 2),
                    corroborated_matches=camp.event_count,
                    matched_scenario=camp.matched_scenario,
                    notes=f"Indicador cruzado con {camp.campaign_id} ({', '.join(sorted(overlap))}).",
                )

        # 2. Señales fuertes de imitacion / acortador / prompt injection -> crea o actualiza campaña incipiente
        strong_signals = {
            "domain_imitation",
            "punycode_domain",
            "unicode_homoglyph",
            "shortener_detected",
            "prompt_injection_attempt",
        }
        has_strong_signal = bool(set(event.rule_signals) & strong_signals)

        if has_strong_signal and keys:
            self._seq += 1
            camp_id = f"CAMP-{event.impersonated_entity.upper()}-{self._seq:02d}"
            camp_name = f"Posible suplantacion {event.impersonated_entity} ({event.scam_type})"
            rec = CampaignRecord(
                campaign_id=camp_id,
                campaign_name=camp_name,
                entity=event.impersonated_entity,
                indicators=set(keys),
                event_count=1,
            )
            self._campaigns[camp_id] = rec
            return EngineVerdict(
                campaign_id=camp_id,
                campaign_name=camp_name,
                status="indicio",
                confidence=0.62,
                corroborated_matches=1,
                notes="Nueva campaña en observacion creada por señales de suplantacion.",
            )

        if event.rule_signals and "official_domain_verified" in event.rule_signals and len(event.rule_signals) == 1:
            return EngineVerdict(
                campaign_id=None,
                campaign_name=None,
                status="sin_verificar",
                confidence=0.1,
                corroborated_matches=0,
                notes="Dominio oficial sin señales de suplantacion.",
            )

        # 3. Caso sin evidencia cruzada suficiente (ej. reporte ciudadano aislado)
        return EngineVerdict(
            campaign_id=None,
            campaign_name=None,
            status="sin_verificar",
            confidence=0.3,
            corroborated_matches=0,
            notes="Reporte registrado sin verificacion cruzada suficiente.",
        )


def cap_certainty(
    verdict: EngineVerdict,
    *,
    rate_limited: bool = False,
) -> tuple[VerificationStatus, float]:
    """Asegura que Plan 5 nunca exprese certeza mayor que la recibida del motor."""
    if rate_limited:
        return "sin_verificar", min(verdict.confidence, 0.25)

    conf = max(0.0, min(1.0, verdict.confidence))
    if verdict.status == "campana_corroborada":
        if conf >= 0.65:
            return "campana_corroborada", conf
        if conf >= 0.30:
            return "indicio", conf
        return "sin_verificar", conf
    if verdict.status == "indicio" and conf > 0.0:
        return "indicio", conf
    return "sin_verificar", conf


class IntelEngineAdapter:
    """Adaptador que conecta Plan 5 (SMS y Portal Ciudadano) con el IntelEngine real (Plan 4)."""

    def __init__(self, engine: IntelEngine | None = None) -> None:
        self._engine = engine or get_default_engine()

    def process_event(self, event: EngineEventInput) -> EngineVerdict:
        # Si es un dominio oficial sin señales de suplantación ni cuentas/teléfonos sospechosos
        if (
            event.rule_signals
            and "official_domain_verified" in event.rule_signals
            and len(event.rule_signals) == 1
            and not event.indicators.accounts
        ):
            return EngineVerdict(
                campaign_id=None,
                campaign_name=None,
                status="sin_verificar",
                confidence=0.1,
                corroborated_matches=0,
                notes="Dominio oficial sin señales de suplantación.",
            )

        parts: list[str] = []
        if event.impersonated_entity and event.impersonated_entity != "ninguno":
            parts.append(event.impersonated_entity)
        if event.scam_type and event.scam_type != "desconocido":
            parts.append(event.scam_type.replace("_", " "))
        parts.extend(event.indicators.accounts)
        parts.extend(event.indicators.defanged_urls)
        parts.extend(event.indicators.phones)

        sanitized_text = " ".join(p for p in parts if p).strip() or "reporte ciudadano sin indicadores"
        channel = "portal" if event.source == "citizen_report" else "sms"

        intel_input = EventInput(
            event_id=f"{event.source}-{uuid4().hex[:8]}",
            occurred_at=datetime.now(timezone.utc).isoformat(),
            channel=channel,  # type: ignore[arg-type]
            text_sanitized=sanitized_text,
            source_fingerprint=f"{event.source}:{uuid4().hex[:12]}",
            claimed_brand_hint=(
                event.impersonated_entity
                if event.impersonated_entity and event.impersonated_entity != "ninguno"
                else None
            ),
            rate_limited=event.rate_limited,
        )

        res = self._engine.process_event(intel_input)
        if res.status == "corroborada":
            mapped_status: VerificationStatus = "campana_corroborada"
        elif res.status == "indicio":
            mapped_status = "indicio"
        else:
            mapped_status = "sin_verificar"

        corroborated_matches = 0
        if res.campaign_id:
            camp = self._engine.get_campaign(res.campaign_id)
            if camp is not None:
                corroborated_matches = camp.independent_sources_count

        campaign_name = (
            f"{res.threat_category} ({res.claimed_brand or event.impersonated_entity})"
            if res.campaign_id
            else None
        )
        notes = "; ".join(res.reasons) if res.reasons else res.match_reason

        return EngineVerdict(
            campaign_id=res.campaign_id,
            campaign_name=campaign_name,
            status=mapped_status,
            confidence=res.confidence,
            corroborated_matches=corroborated_matches,
            notes=notes,
        )
