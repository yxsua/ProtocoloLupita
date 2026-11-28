"""Esquemas y contratos del portal ciudadano, saneamiento y mapa municipal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.modules.sms.schemas import ExtractedIndicators, GuidedRoute, VerificationStatus


@dataclass(slots=True)
class CitizenReportRaw:
    """Entrada cruda del formulario ciudadano. Nunca debe persistirse tal cual."""

    channel: Literal["sms", "llamada"]
    municipality: str
    description: str
    reported_sender_or_phone: str | None = None
    reported_url: str | None = None
    reported_account: str | None = None
    reported_business_name: str | None = None
    # Campos personales (PII) que deben descartarse antes de persistir o enviar al motor
    reporter_name: str | None = None
    reporter_curp: str | None = None
    reporter_phone: str | None = None
    reporter_email: str | None = None
    reporter_address: str | None = None
    session_token: str | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReportInput:
    """Reporte ciudadano saneado: sin PII del reportante, listo para persistir y enviar al motor."""

    report_id: str
    channel: Literal["sms", "llamada"]
    municipality: str
    sanitized_summary: str
    indicators: ExtractedIndicators
    reported_business_name: str | None = None
    discarded_pii_fields: list[str] = field(default_factory=list)
    redacted_inline_pii: list[str] = field(default_factory=list)
    rate_limited: bool = False
    fingerprint_hash: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CitizenResponse:
    """Contrato de salida de submit_report(input) -> CitizenResponse."""

    report_id: str
    channel: Literal["sms", "llamada"]
    municipality: str
    verification_status: VerificationStatus
    rate_limited: bool
    business_published: bool
    campaign_id: str | None
    campaign_name: str | None
    engine_confidence: float
    explanation: str
    guided_route: GuidedRoute
    indicators: ExtractedIndicators
    discarded_pii_fields: list[str]
    redacted_inline_pii: list[str]
    links_disabled: Literal[True] = True
    circular_matches: list[dict[str, Any]] = field(default_factory=list)
    preventive_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MunicipalAggregate:
    """Conteo municipal publicado para el mapa de Integrante 2 (solo si count >= umbral)."""

    municipality: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MapAggregateResponse:
    """Respuesta agregada hacia mapa/tablero respetando umbral minimo de privacidad."""

    threshold: int
    visible_municipalities: list[MunicipalAggregate]
    total_reports: int
    hidden_municipalities_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
