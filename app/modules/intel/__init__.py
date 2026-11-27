"""Módulo de extracción, validación, correlación de campañas y confianza."""

from .contracts import (
    AccountVerification,
    CampaignSummary,
    EventInput,
    EventResult,
    ExtractedIndicator,
    Indicator,
    LookupResult,
)
from .extractors import extract_indicators
from .service import (
    IntelEngine,
    get_default_engine,
    lookup_indicator,
    process_event,
    reset_default_engine,
)
from .validators import generate_synthetic_card, generate_synthetic_clabe, verify_account

__all__ = [
    "AccountVerification",
    "CampaignSummary",
    "EventInput",
    "EventResult",
    "ExtractedIndicator",
    "Indicator",
    "IntelEngine",
    "LookupResult",
    "extract_indicators",
    "generate_synthetic_card",
    "generate_synthetic_clabe",
    "get_default_engine",
    "lookup_indicator",
    "process_event",
    "reset_default_engine",
    "verify_account",
]
