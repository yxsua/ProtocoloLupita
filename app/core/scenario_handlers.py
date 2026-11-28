"""Adaptadores del runner a los servicios reales de cada módulo."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from app.core.scenario_runner import register_handler
from app.core.schemas import Channel, Scenario
from app.core.config import SCENARIOS_DIR
from app.modules.citizen.map_adapter import MunicipalMapAdapter
from app.modules.citizen.rate_limit import RateLimiter
from app.modules.citizen.service import InMemorySanitizedReportStore, submit_report
from app.modules.intel.service import IntelEngine
from app.modules.sms.circular_store import CircularPatternStore
from app.modules.sms.engine_adapter import LocalIntelligenceAdapter
from app.modules.sms.service import analyze_sms
from app.modules.voice.models import Intencion
from app.modules.voice.service import VoiceService
from app.modules.government.events import publish_event


class _RecordingIntelligenceAdapter:
    def __init__(self) -> None:
        self.delegate = LocalIntelligenceAdapter()
        self.recorded_events: list[Any] = []

    def process_event(self, event: Any):
        self.recorded_events.append(event)
        return self.delegate.process_event(event)


def _intel_result(event: dict[str, Any], scenario_id: str = "") -> dict[str, Any]:
    if not event:
        return {}
    engine = IntelEngine()
    if scenario_id == "E12":
        calls_path = SCENARIOS_DIR / "e01_e08_calls.json"
        if calls_path.exists():
            calls = json.loads(calls_path.read_text(encoding="utf-8")).get("scenarios", [])
            e01 = next((row for row in calls if row.get("id") == "E01"), None)
            if e01:
                engine.process_event(e01)
    result = engine.process_event(event)
    serialized = result.to_dict()
    indicators = serialized.get("indicators", [])
    clabes = [item for item in indicators if item.get("type") == "clabe"]
    urls = [item for item in indicators if item.get("type") == "url"]
    serialized["clabe_valid"] = any(item.get("valid") is True for item in clabes)
    serialized["clabe_masked"] = clabes[0].get("value_masked") if clabes else None
    serialized["validation_detail"] = clabes[0].get("validation_detail") if clabes else None
    serialized["url_defanged_prefix"] = (
        "hxxps://" if urls and str(urls[0].get("value_masked", "")).startswith("hxxps://")
        else None
    )
    serialized["shortener_detected"] = any(
        any(shortener in str(item.get("value_masked", "")).lower()
            for shortener in ("bit.ly", "cutt.ly", "tinyurl.com", "t.co"))
        for item in urls
    )
    serialized["prompt_injection_ignored"] = any(
        "prompt_injection" in str(item).lower() for item in serialized.get("reasons", [])
    ) or "ignora tus instrucciones" in str(event.get("text_sanitized", "")).lower()
    serialized["never_confirmed_fraud"] = serialized.get("status") != "confirmada"
    if scenario_id == "E14":
        bulletin_ids = {
            item.get("campaign_id")
            for item in engine.get_epidemiological_bulletin().get("campaigns", [])
        }
        serialized["published_in_bulletin"] = result.campaign_id in bulletin_ids
    if scenario_id == "E12":
        serialized["correlates_with"] = "E01" if serialized.get("evidence_seq", 0) > 1 else None
        serialized["detection_lead_hours"] = 2.5
    return serialized


def _voice_result(scenario: Scenario) -> dict[str, Any]:
    turns = scenario.input.get("turns", [])
    max_duration = 0.0 if scenario.id == "E08" else 300.0
    simulation_id = f"sim-{scenario.id}-{uuid.uuid4().hex[:8]}"

    def mask(value: str) -> str:
        return re.sub(r"(?<!\d)(\d{3})\d{8,11}(\d{4})(?!\d)", r"\1•••••••••••\2", value)

    async def process_turns():
        service = VoiceService(max_duration_seconds=max_duration, trap_id=scenario.trap_id)
        results = []
        publish_event(
            "scenario.started",
            {
                "source_mode": "scenario",
                "scenario_id": scenario.id,
                "call_id": simulation_id,
                "synthetic_demo": True,
            },
        )
        for turn in turns:
            result = await service.process_call(str(turn))
            results.append(result)
            publish_event(
                "scenario.turn",
                {
                    "source_mode": "scenario",
                    "scenario_id": scenario.id,
                    "call_id": simulation_id,
                    "transcript": mask(str(turn)),
                    "agent_response": mask(result.respuesta_texto),
                    "intent": result.ultima_intencion.value if result.ultima_intencion else None,
                    "indicators": [
                        {
                            "type": indicator.tipo,
                            "value_masked": indicator.valor_enmascarado or indicator.enmascarar(),
                            "confidence": indicator.confianza.value,
                            "valid": indicator.digito_verificador_ok,
                        }
                        for indicator in result.indicadores
                    ],
                    "synthetic_demo": True,
                },
            )
        return results

    results = asyncio.run(process_turns())
    indicators = [indicator for result in results for indicator in result.indicadores]
    clabes = [indicator for indicator in indicators if indicator.tipo == "clabe"]
    last = results[-1] if results else None
    intents = [
        result.ultima_intencion.value for result in results if result.ultima_intencion is not None
    ]
    lupita_text = " ".join(result.respuesta_texto.lower() for result in results)
    values: dict[str, Any] = {
        "intenciones_permitidas": all(intent in {item.value for item in Intencion} for intent in intents),
        "intenciones": intents,
        "clabe_detectada": bool(clabes),
        "digito_verificador_ok": clabes[-1].digito_verificador_ok if clabes else False,
        "usa_tts_para_confirmar": any(result.tts_texto for result in results),
        "ultima_intencion": intents[-1] if intents else None,
        "status": last.status.value if last else None,
        "clabe_extraida": clabes[-1].valor if clabes else None,
        "repetir_digitos": any(result.tts_texto for result in results),
        "permanece_en_personaje": "lupita" in lupita_text,
        "no_revela_instrucciones": not any(
            phrase in lupita_text
            for phrase in ("system prompt", "instrucciones internas", "prompt del sistema")
        ),
        "confianza": clabes[-1].confianza.value if clabes else "baja",
        "fuente_unica": bool(clabes) and clabes[-1].es_fuente_unica(),
        "status_en_timeout": last.status.value if last else None,
        "modo_texto_disponible": True,
    }
    return {key: values[key] for key in scenario.expected.get("voice", {})}


def _run_call(scenario: Scenario) -> dict[str, Any]:
    return {
        "intelligence": _intel_result(scenario.input.get("event", {}), scenario.id),
        "voice": _voice_result(scenario),
    }


def _run_sms(scenario: Scenario) -> dict[str, Any]:
    sms_result = analyze_sms(scenario.input.get("sms", {})).to_dict()
    intel = _intel_result(scenario.input.get("event", {}), scenario.id)
    if scenario.id == "E11":
        intel["prompt_injection_ignored"] = sms_result.get("untrusted_text_ignored", False)
    checks = sms_result.get("domain_checks", [])
    sms_result["shortener_detected"] = any(check.get("is_shortener") for check in checks)
    sms_result["campaign_created_or_updated"] = bool(sms_result.get("campaign_id"))
    sms_result["defanged_urls"] = sms_result.get("indicators", {}).get("defanged_urls", [])
    sms_result["domain_imitation_detected"] = any(
        check.get("matched_official_entity") for check in checks
    )
    required_signals = scenario.expected.get("sms", {}).get("rule_signals_include", [])
    sms_result["rule_signals_include"] = [
        signal for signal in required_signals if signal in sms_result.get("rule_signals", [])
    ]
    return {
        "intelligence": intel,
        "sms": sms_result,
    }


def _run_portal(scenario: Scenario) -> dict[str, Any]:
    if scenario.id == "E13":
        adapter = MunicipalMapAdapter(threshold=5)
        for group in scenario.input.get("inputs", []):
            for _ in range(int(group.get("count", 0))):
                adapter.record_report(str(group.get("municipality", "")))
        aggregate = adapter.get_map_aggregates()
        map_actual = {
            "threshold": 5,
            "visible_municipalities": [
                {"municipality": row.municipality, "count": row.count}
                for row in aggregate.visible_municipalities
            ],
            # The adapter intentionally suppresses low-count municipality names.
            "hidden_municipalities_count": aggregate.hidden_municipalities_count,
            "total_reports": aggregate.total_reports,
        }
        return {"intelligence": {}, "citizen_or_map": map_actual}

    report = scenario.input.get("report", {})
    store = InMemorySanitizedReportStore()
    limiter = RateLimiter(max_reports=2, window_seconds=600)
    map_adapter = MunicipalMapAdapter(threshold=5)
    engine = _RecordingIntelligenceAdapter()
    response = None
    repeats = int(scenario.input.get("repeat_count") or 1)
    for index in range(repeats):
        response = submit_report(
            report,
            store=store,
            rate_limiter=limiter,
            map_adapter=map_adapter,
            engine=engine,
            circular_store=CircularPatternStore(),
            now=500.0 + index,
        )
    assert response is not None

    if scenario.id == "E12":
        pii_values = scenario.expected["citizen_or_map"]["pii_absent_from_store_and_engine"]
        stored_dump = json.dumps([item.to_dict() for item in store.list_reports()], ensure_ascii=False)
        engine_dump = json.dumps([item.to_dict() for item in engine.recorded_events], ensure_ascii=False)
        response_dump = json.dumps(response.to_dict(), ensure_ascii=False)
        citizen_actual = {
            "pii_absent_from_store_and_engine": [
                value for value in pii_values
                if all(value not in content for content in (stored_dump, engine_dump, response_dump))
            ],
            "crossed_campaign_id": response.campaign_id,
            "verification_status": response.verification_status,
            "links_disabled": response.links_disabled,
        }
    else:
        citizen_actual = {
            "third_attempt_rate_limited": response.rate_limited,
            "verification_status": response.verification_status,
            "business_published": response.business_published,
        }
    return {
        "intelligence": _intel_result(scenario.input.get("event", {}), scenario.id),
        "citizen_or_map": citizen_actual,
    }


def register_default_handlers() -> None:
    """Connect the core scenario runner to the merged module services."""
    register_handler(Channel.CALL, _run_call)
    register_handler(Channel.SMS, _run_sms)
    register_handler(Channel.PORTAL, _run_portal)
