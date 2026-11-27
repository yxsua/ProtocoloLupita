"""Motor de correlación de campañas multicanal y consulta ciudadana."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.modules.intel.contracts import (
    CampaignSummary,
    Channel,
    ConfidenceLevel,
    EventInput,
    ExtractedIndicator,
    Indicator,
    LookupResult,
    ThreatCategory,
)
from app.modules.intel.extractors import (
    build_template_signature,
    classify_threat,
    extract_indicators,
)


def _parse_iso_utc(value: str) -> Optional[datetime]:
    try:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def jaccard_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Calcula similitud de Jaccard entre dos conjuntos de n-gramas."""
    if not a or not b:
        return 0.0
    union_size = len(a | b)
    if union_size == 0:
        return 0.0
    return len(a & b) / union_size


@dataclass
class CampaignState:
    """Estado interno mutable de una campaña detectada."""

    campaign_id: str
    status: str = "sin_verificar"
    confidence: float = 0.0
    confidence_level: ConfidenceLevel = "baja"
    threat_category: ThreatCategory = "no_aplica"
    legal_tag: str = "sin_tipificacion"
    channels_observed: list[Channel] = field(default_factory=list)
    trap_ids: set[str] = field(default_factory=set)
    independent_sources: set[str] = field(default_factory=set)
    claimed_brands: list[str] = field(default_factory=list)
    template_variants: list[str] = field(default_factory=list)
    shingle_sets: list[frozenset[str]] = field(default_factory=list)
    primary_hashes: set[str] = field(default_factory=set)
    indicators_by_key: dict[str, Indicator] = field(default_factory=dict)
    event_refs: list[dict[str, object]] = field(default_factory=list)
    first_trap_seen_at: Optional[str] = None
    first_citizen_report_at: Optional[str] = None
    detection_lead_hours: Optional[float] = None
    has_valid_financial: bool = False
    has_sensitive_request: bool = False

    def to_summary(self) -> CampaignSummary:
        """Proyecta el estado interno al contrato público CampaignSummary."""
        status_typed = (
            self.status
            if self.status in ("sin_verificar", "indicio", "corroborada")
            else "sin_verificar"
        )
        return CampaignSummary(
            campaign_id=self.campaign_id,
            status=status_typed,  # type: ignore[arg-type]
            confidence=self.confidence,
            confidence_level=self.confidence_level,
            threat_category=self.threat_category,
            legal_tag=self.legal_tag,
            channels_observed=list(self.channels_observed),
            traps_reached_count=len(self.trap_ids),
            independent_sources_count=len(self.independent_sources),
            claimed_brands=list(self.claimed_brands),
            template_variants=list(self.template_variants),
            indicators=list(self.indicators_by_key.values()),
            first_trap_seen_at=self.first_trap_seen_at,
            first_citizen_report_at=self.first_citizen_report_at,
            detection_lead_hours=self.detection_lead_hours,
        )


class CampaignIndex:
    """Índice en memoria para agrupar eventos por indicadores fuertes y similitud de plantilla."""

    def __init__(self) -> None:
        self._campaigns: dict[str, CampaignState] = {}
        self._primary_hash_to_campaign: dict[str, str] = {}
        self._seq_counter: int = 0

    def _next_campaign_id(self) -> str:
        self._seq_counter += 1
        return f"CMP-{self._seq_counter:03d}"

    def find_match(
        self,
        extracted: list[ExtractedIndicator],
        template_shingles: frozenset[str],
        threat_category: ThreatCategory,
        claimed_brands: set[str],
    ) -> tuple[Optional[CampaignState], str]:
        """Busca una campaña existente por indicador fuerte o por similitud de plantilla."""
        # Etapa 1: coincidencia exacta de indicador fuerte (nunca origin_phone)
        for ind in extracted:
            if not ind.is_primary_correlator:
                continue
            existing_id = self._primary_hash_to_campaign.get(ind.value_hash)
            if existing_id and existing_id in self._campaigns:
                return self._campaigns[existing_id], "exact_indicator"

        # Etapa 2: similitud de plantilla de guion/SMS (agrupa SMS con enlaces distintos)
        best_campaign: Optional[CampaignState] = None
        best_score = 0.0
        for camp in self._campaigns.values():
            if not camp.shingle_sets:
                continue
            max_sim = max(
                jaccard_similarity(template_shingles, ref) for ref in camp.shingle_sets
            )
            shares_brand = bool(claimed_brands & set(camp.claimed_brands))
            shares_threat = (
                threat_category != "no_aplica"
                and camp.threat_category == threat_category
            )
            threshold = 0.60 if (shares_brand or shares_threat) else 0.75
            if max_sim >= threshold and max_sim > best_score:
                best_score = max_sim
                best_campaign = camp

        if best_campaign is not None:
            return best_campaign, "template_similarity"

        return None, "new_campaign"

    def register_or_update(
        self,
        event: EventInput,
        extracted: list[ExtractedIndicator],
        threat_category: ThreatCategory,
        legal_tag: str,
        template_str: str,
        template_shingles: frozenset[str],
        claimed_brands: list[str],
    ) -> tuple[CampaignState, str]:
        """Asocia el evento a una campaña existente o crea una nueva y actualiza métricas."""
        brand_set = set(claimed_brands)
        camp, match_reason = self.find_match(
            extracted=extracted,
            template_shingles=template_shingles,
            threat_category=threat_category,
            claimed_brands=brand_set,
        )

        if camp is None:
            camp_id = self._next_campaign_id()
            camp = CampaignState(
                campaign_id=camp_id,
                threat_category=threat_category,
                legal_tag=legal_tag,
            )
            self._campaigns[camp_id] = camp
        elif camp.threat_category == "no_aplica" and threat_category != "no_aplica":
            camp.threat_category = threat_category
            camp.legal_tag = legal_tag

        if event.channel not in camp.channels_observed:
            camp.channels_observed.append(event.channel)

        if event.trap_id and not event.rate_limited and not event.force_unverified:
            camp.trap_ids.add(event.trap_id)

        if not event.rate_limited and not event.force_unverified:
            camp.independent_sources.add(event.source_fingerprint)
            self._update_lead_times(camp, event)

        for brand in claimed_brands:
            if brand not in camp.claimed_brands:
                camp.claimed_brands.append(brand)

        if template_str and template_str not in camp.template_variants:
            camp.template_variants.append(template_str)
            camp.shingle_sets.append(template_shingles)

        for ind in extracted:
            if ind.type in ("clabe", "card") and ind.valid is True:
                camp.has_valid_financial = True
            if ind.type == "requested_data":
                camp.has_sensitive_request = True
            if ind.is_primary_correlator:
                camp.primary_hashes.add(ind.value_hash)
                # No sobreescribe campaña previa si ya existía, solo indexa si es nuevo
                self._primary_hash_to_campaign.setdefault(ind.value_hash, camp.campaign_id)

        return camp, match_reason

    def _update_lead_times(self, camp: CampaignState, event: EventInput) -> None:
        """Actualiza marcas de primer contacto en trampa vs primer reporte ciudadano."""
        dt_ev = _parse_iso_utc(event.occurred_at)
        if dt_ev is None:
            return

        if event.channel in ("call", "sms") and event.trap_id:
            if camp.first_trap_seen_at is None:
                camp.first_trap_seen_at = event.occurred_at
            else:
                dt_first = _parse_iso_utc(camp.first_trap_seen_at)
                if dt_first is not None and dt_ev < dt_first:
                    camp.first_trap_seen_at = event.occurred_at

        if event.channel == "portal":
            if camp.first_citizen_report_at is None:
                camp.first_citizen_report_at = event.occurred_at
            else:
                dt_first_rep = _parse_iso_utc(camp.first_citizen_report_at)
                if dt_first_rep is not None and dt_ev < dt_first_rep:
                    camp.first_citizen_report_at = event.occurred_at

        if camp.first_trap_seen_at and camp.first_citizen_report_at:
            dt_trap = _parse_iso_utc(camp.first_trap_seen_at)
            dt_rep = _parse_iso_utc(camp.first_citizen_report_at)
            if dt_trap is not None and dt_rep is not None:
                diff_hours = (dt_rep - dt_trap).total_seconds() / 3600.0
                camp.detection_lead_hours = round(diff_hours, 2)

    def get(self, campaign_id: str) -> Optional[CampaignState]:
        """Obtiene una campaña por ID."""
        return self._campaigns.get(campaign_id)

    def list_summaries(self) -> list[CampaignSummary]:
        """Lista todas las campañas ordenadas por ID."""
        return [
            camp.to_summary()
            for _, camp in sorted(self._campaigns.items(), key=lambda item: item[0])
        ]

    def lookup(self, query: str) -> LookupResult:
        """Consulta si un indicador o texto coincide con alguna campaña conocida."""
        extracted = extract_indicators(query, channel="portal")
        template_str, shingles = build_template_signature(query)
        threat_cat, _, _ = classify_threat(query, "portal", extracted)
        brands = {ind.value_masked for ind in extracted if ind.type == "brand"}

        camp, match_reason = self.find_match(
            extracted=extracted,
            template_shingles=shingles,
            threat_category=threat_cat,
            claimed_brands=brands,
        )
        if camp is None:
            return LookupResult(
                found=False,
                status="sin_alerta",
                confidence_level="ninguna",
                threat_category="no_aplica",
                message="Sin coincidencias previas en campañas detectadas.",
            )

        matched_by: str = (
            "exact_indicator"
            if match_reason == "exact_indicator"
            else "template_similarity"
        )
        if camp.status == "sin_verificar":
            msg = (
                "Coincidencia registrada como sin verificar (por límite de tasa o "
                "falta de validación independiente); no se publica como campaña confirmada."
            )
        elif camp.status == "indicio":
            msg = (
                f"Indicio detectado ({camp.threat_category}) con una sola fuente; "
                "pendiente de corroboración independiente."
            )
        else:
            msg = (
                f"Campaña corroborada ({camp.threat_category}) por "
                f"{len(camp.independent_sources)} fuentes independientes. No abras enlaces ni deposites."
            )

        status_typed = (
            camp.status
            if camp.status in ("sin_alerta", "sin_verificar", "indicio", "corroborada")
            else "sin_verificar"
        )
        return LookupResult(
            found=True,
            campaign_id=camp.campaign_id,
            status=status_typed,  # type: ignore[arg-type]
            confidence_level=camp.confidence_level,
            threat_category=camp.threat_category,
            matched_by=matched_by,  # type: ignore[arg-type]
            message=msg,
        )
