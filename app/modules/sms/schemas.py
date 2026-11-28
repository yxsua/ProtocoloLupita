"""Esquemas y contratos de entrada/salida para analisis de SMS."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ImpersonatedEntity = Literal[
    "SAT",
    "IMSS",
    "CFE",
    "banco",
    "paqueteria",
    "telefonica",
    "otro",
    "ninguno",
]

VerificationStatus = Literal["sin_verificar", "indicio", "campana_corroborada"]


@dataclass(slots=True)
class SmsInput:
    """Entrada del analizador de SMS (bandeja fixture o texto pegado)."""

    body: str
    sender: str | None = None
    message_id: str | None = None
    received_at: str | None = None
    channel: Literal["sms"] = "sms"
    municipality: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExtractedIndicators:
    """Indicadores extraidos del mensaje. Todas las URLs estan desactivadas (hxxp)."""

    senders: list[str] = field(default_factory=list)
    defanged_urls: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    accounts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DomainSignal:
    """Resultado de comparacion offline de un dominio contra catalogo local."""

    domain: str
    is_official_exact: bool = False
    is_shortener: bool = False
    is_punycode: bool = False
    has_homoglyphs: bool = False
    matched_official_entity: str | None = None
    matched_official_domain: str | None = None
    similarity_score: float = 0.0
    reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GuidedStep:
    """Paso individual en la ruta de respuesta ciudadana."""

    order: int
    title: str
    detail: str
    official_channel: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GuidedRoute:
    """Ruta guiada local para protegerse o reportar sin ejecutar enlaces."""

    summary: str
    do_not_actions: list[str] = field(default_factory=list)
    steps: list[GuidedStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EngineEventInput:
    """Evento saneado enviado al motor de inteligencia (process_event)."""

    source: Literal["sms", "citizen_report"]
    channel: Literal["sms", "llamada"]
    impersonated_entity: str
    scam_type: str
    indicators: ExtractedIndicators
    municipality: str | None = None
    reported_business_name: str | None = None
    rate_limited: bool = False
    rule_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EngineVerdict:
    """Respuesta autoritativa recibida desde process_event (Integrantes 1/4)."""

    campaign_id: str | None
    campaign_name: str | None
    status: VerificationStatus
    confidence: float
    corroborated_matches: int = 0
    matched_scenario: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SmsAnalysis:
    """Contrato de salida de analyze_sms(input) -> SmsAnalysis."""

    message_id: str | None
    impersonated_entity: ImpersonatedEntity
    scam_type: str
    is_suspicious: bool
    rule_signals: list[str]
    model_label: str | None
    indicators: ExtractedIndicators
    domain_checks: list[DomainSignal]
    campaign_id: str | None
    campaign_name: str | None
    verification_status: VerificationStatus
    engine_confidence: float
    explanation: str
    guided_route: GuidedRoute
    links_disabled: Literal[True] = True
    untrusted_text_ignored: bool = False
    circular_matches: list[dict[str, Any]] = field(default_factory=list)
    preventive_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
