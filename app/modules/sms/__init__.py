"""Módulo SMS con exports perezosos para evitar ciclos con ciudadanía."""

from app.modules.sms.schemas import DomainSignal, ExtractedIndicators, SmsAnalysis, SmsInput

__all__ = [
    "DomainSignal",
    "ExtractedIndicators",
    "SmsAnalysis",
    "SmsInput",
    "analyze_sms",
    "load_sms_inbox",
]


def __getattr__(name: str):
    if name in {"analyze_sms", "load_sms_inbox"}:
        from app.modules.sms import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
