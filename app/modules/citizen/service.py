"""Servicio ciudadano: expone submit_report(input) -> CitizenResponse."""

from __future__ import annotations

from typing import Any

from app.modules.citizen.guided_route import build_guided_route
from app.modules.citizen.map_adapter import MapPort, MunicipalMapAdapter
from app.modules.citizen.rate_limit import RateLimiter
from app.modules.citizen.sanitizer import sanitize_report
from app.modules.citizen.schemas import (
    CitizenReportRaw,
    CitizenResponse,
    MapAggregateResponse,
    ReportInput,
)
from app.modules.sms.circular_store import CircularPatternStore
from app.modules.sms.domains import analyze_domains, load_domain_catalog
from app.modules.sms.engine_adapter import (
    IntelEngineAdapter,
    IntelligenceEnginePort,
    LocalIntelligenceAdapter,
    cap_certainty,
)
from app.modules.sms.rules import classify_sms_rules
from app.modules.sms.schemas import EngineEventInput, VerificationStatus
from app.modules.sms.service import get_default_circular_store


class InMemorySanitizedReportStore:
    """Almacen en memoria que solo acepta objetos ReportInput ya saneados."""

    def __init__(self) -> None:
        self._records: list[ReportInput] = []

    def save(self, report: ReportInput) -> None:
        self._records.append(report)

    def list_reports(self) -> list[ReportInput]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()


_DEFAULT_STORE = InMemorySanitizedReportStore()
_DEFAULT_RATE_LIMITER = RateLimiter()
_DEFAULT_MAP_ADAPTER = MunicipalMapAdapter(threshold=5)
_DEFAULT_ENGINE = IntelEngineAdapter()


def _build_citizen_explanation(
    *,
    status: VerificationStatus,
    confidence: float,
    campaign_id: str | None,
    rate_limited: bool,
    discarded_count: int,
    business_name: str | None,
    circular_count: int,
) -> str:
    parts: list[str] = []

    if discarded_count > 0:
        parts.append(
            "Tus datos personales fueron descartados antes de guardar el reporte."
        )

    if rate_limited:
        parts.append(
            "Se activo el limite de tasa por reportes repetidos; este envio permanece como 'sin verificar'."
        )
        if business_name:
            parts.append("El comercio o entidad reportada no fue publicada.")
        return " ".join(parts)

    pct = int(round(confidence * 100))
    if status == "campana_corroborada":
        parts.append(
            f"El indicador coincide con la campaña corroborada {campaign_id or ''} (confianza {pct}%). "
            "No se declara certeza absoluta fuera del motor."
        )
    elif status == "indicio":
        parts.append(
            f"El reporte suma indicios en seguimiento ({campaign_id or 'en revision'}, confianza {pct}%)."
        )
    else:
        parts.append(
            f"El reporte fue recibido en estado 'sin verificar' (confianza {pct}%)."
        )
        if business_name:
            parts.append("Por precaucion, el negocio o entidad reportada no se publica mientras siga sin verificar.")

    if circular_count > 0:
        parts.append(
            "Ademas, este reporte coincide con patrones previos y ayudara a prevenir a otras personas."
        )
    else:
        parts.append(
            "El patron anonimizado se integro al analisis circular para alertar a otras personas si reciben un mensaje similar."
        )

    return " ".join(parts)


def submit_report(
    raw_input: CitizenReportRaw | dict[str, Any],
    *,
    store: InMemorySanitizedReportStore | None = None,
    rate_limiter: RateLimiter | None = None,
    map_adapter: MapPort | None = None,
    engine: IntelligenceEnginePort | None = None,
    circular_store: CircularPatternStore | None = None,
    now: float | None = None,
) -> CitizenResponse:
    """Sanea PII, valida limite de tasa, cruza indicadores con el motor y retroalimenta patrones circulares."""
    active_store = store or _DEFAULT_STORE
    active_limiter = rate_limiter or _DEFAULT_RATE_LIMITER
    active_map = map_adapter or _DEFAULT_MAP_ADAPTER
    active_engine = engine or _DEFAULT_ENGINE
    active_circular = circular_store or get_default_circular_store()

    # 1. Saneamiento estricto ANTES de persistencia y ANTES de process_event
    sanitized = sanitize_report(raw_input)

    # 2. Control de limite de tasa
    is_rate_limited = active_limiter.check_and_record(sanitized, now=now)
    sanitized.rate_limited = is_rate_limited

    # 3. Persistir unicamente ReportInput saneado
    active_store.save(sanitized)

    # 4. Clasificacion auxiliar de reglas sobre texto saneado e indicadores
    catalog = load_domain_catalog()
    domain_checks = analyze_domains(sanitized.indicators.domains, catalog)
    rule_res = classify_sms_rules(sanitized.sanitized_summary, domain_checks)

    # 5. Buscar coincidencias circulares previas (ciudadania + base historica spam.csv)
    prior_matches = (
        active_circular.match_patterns(sanitized.sanitized_summary, sanitized.indicators)
        if not is_rate_limited
        else []
    )
    signals = list(rule_res.rule_signals)
    if prior_matches and "circular_pattern_match" not in signals:
        signals.append("circular_pattern_match")

    # 6. Invocar process_event solo con campos saneados
    event = EngineEventInput(
        source="citizen_report",
        channel=sanitized.channel,
        impersonated_entity=rule_res.impersonated_entity,
        scam_type=rule_res.scam_type,
        indicators=sanitized.indicators,
        municipality=sanitized.municipality,
        reported_business_name=sanitized.reported_business_name,
        rate_limited=is_rate_limited,
        rule_signals=signals,
    )
    verdict = active_engine.process_event(event)
    status, capped_conf = cap_certainty(verdict, rate_limited=is_rate_limited)

    # Nunca publicar comercio/entidad cuando esta sin verificar o limitado por tasa
    business_published = bool(
        sanitized.reported_business_name
        and not is_rate_limited
        and status == "campana_corroborada"
    )

    # 7. Retroalimentar el analisis circular SOLO con datos ya saneados y NO limitados por tasa
    if not is_rate_limited:
        active_circular.record_citizen_pattern(
            sanitized_text=sanitized.sanitized_summary,
            indicators=sanitized.indicators,
            impersonated_entity=rule_res.impersonated_entity,
            scam_type=rule_res.scam_type,
            verification_status=status,
            rate_limited=False,
        )

    # 8. Actualizar agregado municipal (umbral >= 5 aplicado al consultar mapa)
    active_map.record_report(sanitized.municipality, rate_limited=is_rate_limited)

    preventive_warning: str | None = None
    if prior_matches and not is_rate_limited:
        preventive_warning = (
            "Coincide con estafas reportadas anteriormente. No abras enlaces ni respondas."
        )

    explanation = _build_citizen_explanation(
        status=status,
        confidence=capped_conf,
        campaign_id=verdict.campaign_id,
        rate_limited=is_rate_limited,
        discarded_count=len(sanitized.discarded_pii_fields) + len(sanitized.redacted_inline_pii),
        business_name=sanitized.reported_business_name,
        circular_count=len(prior_matches),
    )

    guided_route = build_guided_route(
        impersonated_entity=rule_res.impersonated_entity,
        channel=sanitized.channel,
        verification_status=status,
        rate_limited=is_rate_limited,
    )

    return CitizenResponse(
        report_id=sanitized.report_id,
        channel=sanitized.channel,
        municipality=sanitized.municipality,
        verification_status=status,
        rate_limited=is_rate_limited,
        business_published=business_published,
        campaign_id=verdict.campaign_id,
        campaign_name=verdict.campaign_name,
        engine_confidence=capped_conf,
        explanation=explanation,
        guided_route=guided_route,
        indicators=sanitized.indicators,
        discarded_pii_fields=sanitized.discarded_pii_fields,
        redacted_inline_pii=sanitized.redacted_inline_pii,
        links_disabled=True,
        circular_matches=[m.to_dict() for m in prior_matches],
        preventive_warning=preventive_warning,
    )


def get_map_aggregates(map_adapter: MapPort | None = None) -> MapAggregateResponse:
    """Devuelve agregados municipales cumpliendo el umbral minimo."""
    active_map = map_adapter or _DEFAULT_MAP_ADAPTER
    return active_map.get_map_aggregates()
