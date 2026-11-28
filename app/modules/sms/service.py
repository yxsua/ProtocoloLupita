"""Servicio principal de analisis de SMS: expone analyze_sms(input) -> SmsAnalysis."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from app.modules.sms.circular_store import CircularMatch, CircularPatternStore
from app.modules.sms.dataset_classifier import get_default_dataset_classifier
from app.modules.sms.domains import analyze_domains, load_domain_catalog
from app.modules.sms.engine_adapter import (
    IntelEngineAdapter,
    IntelligenceEnginePort,
    LocalIntelligenceAdapter,
    cap_certainty,
)
from app.modules.sms.parser import extract_indicators
from app.modules.sms.rules import LocalClassifierProtocol, classify_sms_rules
from app.modules.sms.schemas import (
    DomainSignal,
    EngineEventInput,
    SmsAnalysis,
    SmsInput,
    VerificationStatus,
)

_DEFAULT_INBOX_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "fixtures" / "sms_inbox.json"
)

_DEFAULT_ENGINE = IntelEngineAdapter()
_DEFAULT_CIRCULAR_STORE = CircularPatternStore()


def get_default_circular_store() -> CircularPatternStore:
    """Devuelve el almacen circular compartido entre SMS y portal ciudadano."""
    return _DEFAULT_CIRCULAR_STORE


def load_sms_inbox(inbox_path: Path | None = None) -> list[dict[str, Any]]:
    """Carga mensajes sinteticos desde fixtures locales."""
    target = inbox_path or _DEFAULT_INBOX_PATH
    with target.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _build_preventive_warning(
    *,
    is_suspicious: bool,
    circular_matches: list[CircularMatch],
    all_official_exact: bool,
) -> str | None:
    if all_official_exact and not is_suspicious:
        return None
    if circular_matches:
        top = circular_matches[0]
        if top.source == "reporte_ciudadano":
            return (
                f"Alerta preventiva ciudadana: coincide con {top.report_count} reporte(s) previo(s). "
                "Posible estafa: NO abras enlaces ni respondas."
            )
        return (
            "Alerta preventiva por base historica: este mensaje coincide con patrones conocidos de estafa. "
            "NO abras enlaces ni compartas datos."
        )
    if is_suspicious:
        return "Precaucion: se detectaron señales de riesgo. NO abras enlaces ni respondas el mensaje."
    return None


def _build_sms_explanation(
    *,
    entity: str,
    scam_type: str,
    is_suspicious: bool,
    domain_checks: list[DomainSignal],
    verification_status: VerificationStatus,
    confidence: float,
    campaign_id: str | None,
    untrusted_ignored: bool,
    circular_matches: list[CircularMatch],
) -> str:
    parts: list[str] = []

    if not is_suspicious:
        parts.append(
            "No se detectaron señales de suplantacion ni enlaces sospechosos en las reglas locales."
        )
    else:
        entity_txt = entity if entity != "ninguno" else "entidad no especificada"
        parts.append(
            f"Posible engaño tipo '{scam_type}' suplantando a {entity_txt}."
        )

    for dc in domain_checks:
        if dc.is_shortener:
            parts.append(
                f"El dominio '{dc.domain}' es un acortador que oculta el destino real y no fue abierto."
            )
        elif dc.is_punycode or dc.has_homoglyphs:
            parts.append(
                f"El dominio '{dc.domain}' usa codificacion internacional (punycode/homoglifos) para imitar otro sitio."
            )
        elif not dc.is_official_exact and dc.matched_official_domain:
            parts.append(
                f"El dominio '{dc.domain}' imita al dominio oficial '{dc.matched_official_domain}'."
            )

    if untrusted_ignored:
        parts.append(
            "El mensaje contenia instrucciones incrustadas intentando alterar el analisis; fueron ignoradas y marcadas como sospechosas."
        )

    if circular_matches:
        parts.append(circular_matches[0].warning)

    pct = int(round(confidence * 100))
    if verification_status == "campana_corroborada":
        parts.append(
            f"Estado del motor: campaña corroborada ({campaign_id or 'activa'}, confianza {pct}%). "
            "No se afirma certeza absoluta; valida siempre en canales oficiales."
        )
    elif verification_status == "indicio":
        parts.append(
            f"Estado del motor: indicio en seguimiento ({campaign_id or 'sin campaña'}, confianza {pct}%). "
            "No constituye confirmacion definitiva."
        )
    else:
        parts.append(
            f"Estado del motor: sin verificar (confianza {pct}%). Se recomienda precaucion sin emitir acusacion confirmada."
        )

    return " ".join(parts)


def analyze_sms(
    sms_input: SmsInput | dict[str, Any],
    *,
    engine: IntelligenceEnginePort | None = None,
    local_classifier: LocalClassifierProtocol | None = None,
    domain_catalog: dict[str, Any] | None = None,
    circular_store: CircularPatternStore | None = None,
) -> SmsAnalysis:
    """Analiza un SMS sintetico o pegado por usuario sin abrir enlaces ni responder SMS."""
    if isinstance(sms_input, dict):
        sms = SmsInput(**sms_input)
    else:
        sms = sms_input

    indicators = extract_indicators(sms.body, sender=sms.sender)
    catalog = domain_catalog or load_domain_catalog()
    domain_checks = analyze_domains(indicators.domains, catalog)

    active_classifier = local_classifier or get_default_dataset_classifier()
    rule_res = classify_sms_rules(
        sms.body,
        domain_checks,
        local_classifier=active_classifier,
    )

    all_official_exact = bool(domain_checks) and all(d.is_official_exact for d in domain_checks)
    active_circular = circular_store or _DEFAULT_CIRCULAR_STORE
    circular_matches: list[CircularMatch] = []
    if not (all_official_exact and not rule_res.is_suspicious):
        circular_matches = active_circular.match_patterns(sms.body, indicators)

    rule_signals = list(rule_res.rule_signals)
    is_suspicious = rule_res.is_suspicious
    if circular_matches:
        if "circular_pattern_match" not in rule_signals:
            rule_signals.append("circular_pattern_match")
        is_suspicious = True

    active_engine = engine or _DEFAULT_ENGINE
    event = EngineEventInput(
        source="sms",
        channel="sms",
        impersonated_entity=rule_res.impersonated_entity,
        scam_type=rule_res.scam_type,
        indicators=indicators,
        municipality=sms.municipality,
        rate_limited=False,
        rule_signals=rule_signals,
    )
    verdict = active_engine.process_event(event)
    status, capped_conf = cap_certainty(verdict, rate_limited=False)

    # Si no es sospechoso por reglas ni patron circular y el motor no lo corrobora, mantener sin_verificar
    if not is_suspicious and status != "campana_corroborada":
        status = "sin_verificar"

    preventive_warning = _build_preventive_warning(
        is_suspicious=is_suspicious,
        circular_matches=circular_matches,
        all_official_exact=all_official_exact,
    )

    explanation = _build_sms_explanation(
        entity=rule_res.impersonated_entity,
        scam_type=rule_res.scam_type,
        is_suspicious=is_suspicious,
        domain_checks=domain_checks,
        verification_status=status,
        confidence=capped_conf,
        campaign_id=verdict.campaign_id,
        untrusted_ignored=rule_res.untrusted_text_ignored,
        circular_matches=circular_matches,
    )

    from app.modules.citizen.guided_route import build_guided_route

    guided_route = build_guided_route(
        impersonated_entity=rule_res.impersonated_entity,
        channel="sms",
        verification_status=status,
    )

    return SmsAnalysis(
        message_id=sms.message_id,
        impersonated_entity=rule_res.impersonated_entity,
        scam_type=rule_res.scam_type,
        is_suspicious=is_suspicious,
        rule_signals=rule_signals,
        model_label=rule_res.model_label,
        indicators=indicators,
        domain_checks=domain_checks,
        campaign_id=verdict.campaign_id,
        campaign_name=verdict.campaign_name,
        verification_status=status,
        engine_confidence=capped_conf,
        explanation=explanation,
        guided_route=guided_route,
        links_disabled=True,
        untrusted_text_ignored=rule_res.untrusted_text_ignored,
        circular_matches=[m.to_dict() for m in circular_matches],
        preventive_warning=preventive_warning,
    )


class InMemoryLiveSmsInbox:
    """Bandeja en memoria para SMS reenviados desde telefono (ya saneados y con URLs hxxp)."""

    def __init__(self, *, max_items: int = 50) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=max_items)

    def add(self, entry: dict[str, Any]) -> None:
        self._items.appendleft(entry)

    def list_items(self) -> list[dict[str, Any]]:
        return list(self._items)

    def clear(self) -> None:
        self._items.clear()


_DEFAULT_LIVE_INBOX = InMemoryLiveSmsInbox()


def get_default_live_inbox() -> InMemoryLiveSmsInbox:
    """Devuelve la bandeja en vivo compartida para mensajes recibidos via webhook."""
    return _DEFAULT_LIVE_INBOX


def ingest_device_sms(
    payload: dict[str, Any],
    *,
    live_inbox: InMemoryLiveSmsInbox | None = None,
    engine: IntelligenceEnginePort | None = None,
    circular_store: CircularPatternStore | None = None,
) -> dict[str, Any]:
    """Recibe SMS desde puente de telefono (MacroDroid/Atajos), sanea PII, analiza y guarda sin links vivos."""
    import re as _re
    from app.modules.sms.parser import defang_url as _defang_url

    raw_body = str(payload.get("body", "")).strip()
    raw_sender = str(payload.get("sender", "")).strip() or "DESCONOCIDO"
    municipality = str(payload.get("municipality", "")).strip() or "No especificado"

    # Saneamiento basico de PII inline (evita import circular con citizen.sanitizer)
    _CURP = _re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d\b", _re.IGNORECASE)
    _RFC  = _re.compile(r"\b[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}\b", _re.IGNORECASE)
    _EMAIL = _re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
    _URL_LIVE = _re.compile(r"(?i)\bhttps?://[^\s<>\"'\]\)]+")
    _SELF_NAME = _re.compile(
        r"(?i)\b(?:me\s+llamo|mi\s+nombre\s+es|soy)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3}"
    )

    cleaned = raw_body
    cleaned = _CURP.sub("[CURP_REDACTADA]", cleaned)
    cleaned = _RFC.sub("[RFC_REDACTADO]", cleaned)
    cleaned = _EMAIL.sub("[CORREO_REDACTADO]", cleaned)
    cleaned = _SELF_NAME.sub("[NOMBRE_REDACTADO]", cleaned)
    # Desactivar URLs vivas
    cleaned = _URL_LIVE.sub(lambda m: _defang_url(m.group(0)), cleaned)
    # Eliminar campos PII opcionales que vengan en el payload (no se usan, solo se descartan)
    for _pii_key in ("reporter_name", "reporter_curp", "reporter_phone", "reporter_email", "reporter_address"):
        payload.pop(_pii_key, None)

    msg_id = str(payload.get("message_id") or f"SMS-DEV-{uuid.uuid4().hex[:6].upper()}")
    received_at = str(payload.get("received_at") or datetime.now(timezone.utc).isoformat())

    active_circular = circular_store or _DEFAULT_CIRCULAR_STORE
    analysis = analyze_sms(
        SmsInput(
            message_id=msg_id,
            sender=raw_sender,
            body=cleaned,
            received_at=received_at,
            municipality=municipality,
        ),
        engine=engine,
        circular_store=active_circular,
    )

    if analysis.is_suspicious:
        active_circular.record_citizen_pattern(
            sanitized_text=cleaned,
            indicators=analysis.indicators,
            impersonated_entity=analysis.impersonated_entity,
            scam_type=analysis.scam_type,
            verification_status=analysis.verification_status,
            rate_limited=False,
        )

    entry = {
        "source": "dispositivo",
        "raw": {
            "message_id": msg_id,
            "sender": raw_sender,
            "received_at": received_at,
            "municipality": municipality,
            "body": cleaned,
        },
        "analysis": analysis.to_dict(),
    }
    target_inbox = live_inbox or _DEFAULT_LIVE_INBOX
    target_inbox.add(entry)
    return entry

