from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Channel(StrEnum):
    CALL = "call"
    SMS = "sms"
    PORTAL = "portal"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventStatus(StrEnum):
    NEW = "new"
    INDICATIVE = "indicative"
    CORROBORATED = "corroborated"
    UNVERIFIED = "unverified"
    DISMISSED = "dismissed"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Scenario(Contract):
    id: str
    channel: Channel
    trap_id: str | None = None
    input: dict[str, Any]
    expected: dict[str, Any]


class Event(Contract):
    event_id: str
    occurred_at: datetime
    channel: Channel
    trap_id: str | None = None
    attribution_id: str | None = None
    indicator_ids: list[str] = Field(default_factory=list)
    campaign_id: str | None = None
    confidence: Confidence = Confidence.LOW
    status: EventStatus = EventStatus.NEW
    evidence_hash: str | None = None
    municipality_id: str | None = None
    synthetic: bool = True

    @field_validator("occurred_at")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class Indicator(Contract):
    indicator_id: str
    kind: str
    value_masked: str
    value_fingerprint: str | None = None
    source_event_id: str
    confidence: Confidence = Confidence.LOW
    status: EventStatus = EventStatus.INDICATIVE


class AttributionResult(Contract):
    trap_id: str
    copy_id: str
    provider: str
    dataset: str
    seed_period: str
    synthetic: bool = True


class Campaign(Contract):
    campaign_id: str
    title: str
    brand: str | None = None
    scam_type: str | None = None
    confidence: Confidence = Confidence.LOW
    status: EventStatus = EventStatus.INDICATIVE
    first_seen: datetime
    last_seen: datetime
    event_count: int = Field(default=0, ge=0)


class EventResult(Contract):
    event: Event
    indicators: list[Indicator] = Field(default_factory=list)
    campaign: Campaign | None = None


class ScenarioResult(Contract):
    scenario_id: str
    passed: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    duration_ms: float = Field(ge=0)
    ran_at: datetime

    @field_validator("ran_at")
    @classmethod
    def ran_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ran_at must include a timezone")
        return value


class CallInput(Contract):
    scenario_id: str | None = None
    trap_id: str
    transcript: str | None = None


class CallResult(Contract):
    transcript: str
    selected_intent: str
    response_text: str
    event: Event
    audio_asset: str | None = None
    duration_ms: float = Field(ge=0)
    ended: bool = False


class SmsInput(Contract):
    scenario_id: str | None = None
    trap_id: str
    sender: str
    text: str


class SmsAnalysis(Contract):
    impersonated_brand: str | None = None
    scam_type: str | None = None
    links_deactivated: list[str] = Field(default_factory=list)
    indicator_ids: list[str] = Field(default_factory=list)
    event: Event
    safe_summary: str


class CitizenReportInput(Contract):
    channel: Channel
    trap_id: str | None = None
    municipality_id: str | None = None
    text: str


class CitizenResponse(Contract):
    event: Event
    campaign_id: str | None = None
    route_steps: list[str] = Field(default_factory=list)
    personal_data_removed: bool


class DashboardFilters(Contract):
    channel: Channel | None = None
    municipality_id: str | None = None


class DashboardSnapshot(Contract):
    event_count: int = 0
    campaign_count: int = 0
    attributed_copy_count: int = 0
    events_by_channel: dict[str, int] = Field(default_factory=dict)
    campaigns: list[dict[str, Any]] = Field(default_factory=list)
    municipalities: list[dict[str, Any]] = Field(default_factory=list)

