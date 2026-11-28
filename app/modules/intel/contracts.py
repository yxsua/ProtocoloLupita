"""Contratos de datos puros para el módulo de inteligencia y su integración."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

Channel = Literal["call", "sms", "portal"]
IntelStatus = Literal["sin_alerta", "sin_verificar", "indicio", "corroborada"]
ConfidenceLevel = Literal["ninguna", "baja", "media", "alta"]
IndicatorType = Literal[
    "clabe",
    "card",
    "contact_phone",
    "origin_phone",
    "url",
    "brand",
    "requested_data",
]
ThreatCategory = Literal[
    "no_aplica",
    "extorsion_cobro_piso",
    "secuestro_virtual",
    "falso_ejecutivo_bancario",
    "smishing",
    "falso_premio_paquete",
    "robo_whatsapp",
    "suplantacion_familiar",
    "montadeudas_empleo_inversion",
]


@dataclass
class EventInput:
    """Entrada sanitizada enviada por Voz, SMS o Portal hacia process_event."""

    event_id: str
    occurred_at: str
    channel: Channel
    text_sanitized: str = ""
    source_fingerprint: str = ""
    trap_id: Optional[str] = None
    attribution_id: Optional[str] = None
    origin_phone_masked: Optional[str] = None
    sender_masked: Optional[str] = None
    claimed_brand_hint: Optional[str] = None
    rate_limited: bool = False
    force_unverified: bool = False
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serializa el evento de entrada."""
        return asdict(self)


@dataclass(frozen=True)
class AccountVerification:
    """Resultado de verify_account(value, kind) para validación temprana de cuentas."""

    kind: Literal["clabe", "card"]
    valid: bool
    value_masked: str
    reason: str
    synthetic_bank: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa el resultado de verificación."""
        return asdict(self)


@dataclass(frozen=True)
class Indicator:
    """Indicador público compatible con app/core/schemas.py."""

    id: str
    type: IndicatorType
    value_masked: str
    source_event_id: str
    confidence: float
    status: str
    valid: Optional[bool] = None
    validation_detail: Optional[str] = None
    is_primary_correlator: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serializa el indicador público."""
        return asdict(self)


@dataclass(frozen=True)
class ExtractedIndicator:
    """Indicador extraído antes de persistencia, con hash interno para correlación."""

    type: IndicatorType
    value_masked: str
    value_hash: str
    is_primary_correlator: bool
    valid: Optional[bool] = None
    validation_detail: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)

    def to_public_indicator(
        self,
        indicator_id: str,
        source_event_id: str,
        confidence: float,
        status: str,
    ) -> Indicator:
        """Convierte a Indicator público omitiendo value_hash y metadatos sensibles."""
        return Indicator(
            id=indicator_id,
            type=self.type,
            value_masked=self.value_masked,
            source_event_id=source_event_id,
            confidence=confidence,
            status=status,
            valid=self.valid,
            validation_detail=self.validation_detail,
            is_primary_correlator=self.is_primary_correlator,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializa el indicador extraído."""
        return asdict(self)


@dataclass(frozen=True)
class EventResult:
    """Salida estándar de process_event(event) para Voz, SMS, Portal y Tablero."""

    event_id: str
    campaign_id: Optional[str]
    status: IntelStatus
    confidence: float
    confidence_level: ConfidenceLevel
    threat_category: ThreatCategory
    legal_tag: str
    claimed_brand: Optional[str]
    requested_data: list[str]
    indicators: list[Indicator]
    evidence_hash: str
    evidence_seq: int
    match_reason: str
    reasons: list[str]
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serializa EventResult y sus indicadores públicos."""
        data = asdict(self)
        data["indicators"] = [ind.to_dict() for ind in self.indicators]
        return data


@dataclass(frozen=True)
class CampaignSummary:
    """Resumen consolidado de campaña para tablero, boletín y métrica de ventaja."""

    campaign_id: str
    status: Literal["sin_verificar", "indicio", "corroborada"]
    confidence: float
    confidence_level: ConfidenceLevel
    threat_category: ThreatCategory
    legal_tag: str
    channels_observed: list[Channel]
    traps_reached_count: int
    independent_sources_count: int
    claimed_brands: list[str]
    template_variants: list[str]
    indicators: list[Indicator]
    first_trap_seen_at: Optional[str] = None
    first_citizen_report_at: Optional[str] = None
    detection_lead_hours: Optional[float] = None
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serializa el resumen de campaña."""
        data = asdict(self)
        data["indicators"] = [ind.to_dict() for ind in self.indicators]
        return data


@dataclass(frozen=True)
class LookupResult:
    """Salida de lookup_indicator(...) para el Verificador ciudadano."""

    found: bool
    campaign_id: Optional[str] = None
    status: IntelStatus = "sin_alerta"
    confidence_level: ConfidenceLevel = "ninguna"
    threat_category: ThreatCategory = "no_aplica"
    matched_by: Optional[Literal["exact_indicator", "template_similarity"]] = None
    message: str = ""
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serializa la respuesta del verificador ciudadano."""
        return asdict(self)


def coerce_event_input(raw: EventInput | dict[str, Any] | Any) -> EventInput:
    """Adapta dict, dataclass o modelo Pydantic externo a EventInput."""
    if isinstance(raw, EventInput):
        return raw
    if hasattr(raw, "model_dump") and callable(raw.model_dump):
        data = dict(raw.model_dump())
    elif isinstance(raw, dict):
        data = dict(raw)
    else:
        data = {
            field_name: getattr(raw, field_name)
            for field_name in (
                "event_id",
                "occurred_at",
                "channel",
                "text_sanitized",
                "source_fingerprint",
                "trap_id",
                "attribution_id",
                "origin_phone_masked",
                "sender_masked",
                "claimed_brand_hint",
                "rate_limited",
                "force_unverified",
                "synthetic",
            )
            if hasattr(raw, field_name)
        }

    event_id = str(data.get("event_id") or data.get("id") or "")
    if not event_id:
        raise ValueError("El evento debe incluir 'event_id' o 'id'.")

    occurred_at = str(data.get("occurred_at") or "")
    if not occurred_at:
        raise ValueError("El evento debe incluir 'occurred_at' en formato ISO-8601.")

    channel = data.get("channel")
    if channel not in ("call", "sms", "portal"):
        raise ValueError(f"Canal no soportado: {channel!r}.")

    text_sanitized = str(
        data.get("text_sanitized")
        if data.get("text_sanitized") is not None
        else data.get("text", "")
    )
    trap_id = data.get("trap_id")
    source_fp = str(data.get("source_fingerprint") or "").strip()
    if not source_fp:
        source_fp = f"fallback:{channel}:{trap_id or event_id}"

    return EventInput(
        event_id=event_id,
        occurred_at=occurred_at,
        channel=channel,
        text_sanitized=text_sanitized,
        source_fingerprint=source_fp,
        trap_id=str(trap_id) if trap_id is not None else None,
        attribution_id=(
            str(data["attribution_id"]) if data.get("attribution_id") is not None else None
        ),
        origin_phone_masked=(
            str(data["origin_phone_masked"])
            if data.get("origin_phone_masked") is not None
            else None
        ),
        sender_masked=(
            str(data["sender_masked"]) if data.get("sender_masked") is not None else None
        ),
        claimed_brand_hint=(
            str(data["claimed_brand_hint"])
            if data.get("claimed_brand_hint") is not None
            else None
        ),
        rate_limited=bool(data.get("rate_limited", False)),
        force_unverified=bool(data.get("force_unverified", False)),
        synthetic=bool(data.get("synthetic", True)),
    )
