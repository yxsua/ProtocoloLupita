"""Validacion de aceptacion para los escenarios E09-E14."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.modules.citizen.map_adapter import MunicipalMapAdapter
from app.modules.citizen.rate_limit import RateLimiter
from app.modules.citizen.service import InMemorySanitizedReportStore, submit_report
from app.modules.sms.engine_adapter import LocalIntelligenceAdapter
from app.modules.sms.schemas import EngineEventInput
from app.modules.sms.service import analyze_sms

_SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "data" / "scenarios"


def _load_scenario(filename: str) -> dict:
    with (_SCENARIOS_DIR / filename).open("r", encoding="utf-8") as fh:
        return json.load(fh)


class _SpyEngine:
    """Envuelve LocalIntelligenceAdapter para auditar que nunca reciba PII."""

    def __init__(self) -> None:
        self._delegate = LocalIntelligenceAdapter()
        self.recorded_events: list[EngineEventInput] = []

    def process_event(self, event: EngineEventInput):
        self.recorded_events.append(event)
        return self._delegate.process_event(event)


class ScenariosE09ToE14Tests(unittest.TestCase):
    def test_e09_sat_domain_imitation_creates_campaign_and_disables_link(self) -> None:
        data = _load_scenario("E09_sat_domain_imitation.json")
        engine = LocalIntelligenceAdapter()
        res = analyze_sms(data["input"], engine=engine)

        self.assertEqual(res.impersonated_entity, data["expected"]["impersonated_entity"])
        self.assertTrue(res.is_suspicious)
        self.assertIn("domain_imitation", res.rule_signals)
        self.assertIsNotNone(res.campaign_id)
        self.assertEqual(res.indicators.defanged_urls, data["expected"]["defanged_urls"])
        self.assertTrue(res.links_disabled)

    def test_e10_parcel_held_and_shortener_flagged(self) -> None:
        data = _load_scenario("E10_parcel_shortener.json")
        res = analyze_sms(data["input"], engine=LocalIntelligenceAdapter())

        self.assertEqual(res.impersonated_entity, "paqueteria")
        self.assertEqual(res.scam_type, "paquete_retenido")
        self.assertIn("shortener_detected", res.rule_signals)
        self.assertTrue(any(d.is_shortener for d in res.domain_checks))
        self.assertEqual(res.indicators.defanged_urls, data["expected"]["defanged_urls"])

    def test_e11_prompt_injection_ignored_and_flagged_suspicious(self) -> None:
        data = _load_scenario("E11_prompt_injection_sms.json")
        res = analyze_sms(data["input"], engine=LocalIntelligenceAdapter())

        self.assertTrue(res.is_suspicious)
        self.assertTrue(res.untrusted_text_ignored)
        for sig in data["expected"]["rule_signals_include"]:
            self.assertIn(sig, res.rule_signals)
        self.assertTrue(res.links_disabled)

    def test_e12_citizen_pii_discarded_and_crossed_with_e01(self) -> None:
        data = _load_scenario("E12_citizen_pii_sanitization_e01.json")
        store = InMemorySanitizedReportStore()
        spy_engine = _SpyEngine()

        resp = submit_report(
            data["input"],
            store=store,
            rate_limiter=RateLimiter(),
            map_adapter=MunicipalMapAdapter(threshold=5),
            engine=spy_engine,
        )

        self.assertEqual(resp.campaign_id, "CAMP-E01")
        self.assertEqual(resp.verification_status, "campana_corroborada")
        self.assertTrue(resp.links_disabled)

        persisted_dump = json.dumps([r.to_dict() for r in store.list_reports()])
        engine_dump = json.dumps([e.to_dict() for e in spy_engine.recorded_events])
        resp_dump = json.dumps(resp.to_dict())

        for pii in data["expected"]["pii_absent_from_store_and_engine"]:
            self.assertNotIn(pii, persisted_dump)
            self.assertNotIn(pii, engine_dump)
            self.assertNotIn(pii, resp_dump)

    def test_e13_municipality_threshold_5_and_total_preserved(self) -> None:
        data = _load_scenario("E13_municipality_threshold_5.json")
        store = InMemorySanitizedReportStore()
        limiter = RateLimiter(max_reports=100, window_seconds=600)
        map_adapter = MunicipalMapAdapter(threshold=5)
        engine = LocalIntelligenceAdapter()

        idx = 0
        for group in data["inputs"]:
            for _ in range(group["count"]):
                idx += 1
                submit_report(
                    {
                        "channel": "sms",
                        "municipality": group["municipality"],
                        "description": f"Reporte ciudadano sintetico #{idx}",
                        "session_token": f"e13-user-{idx}",
                    },
                    store=store,
                    rate_limiter=limiter,
                    map_adapter=map_adapter,
                    engine=engine,
                )

        agg = map_adapter.get_map_aggregates()
        self.assertEqual(agg.total_reports, data["expected"]["total_reports"])
        self.assertEqual(
            [{"municipality": m.municipality, "count": m.count} for m in agg.visible_municipalities],
            data["expected"]["visible_municipalities"],
        )

    def test_e14_rate_limit_keeps_unverified_and_unlisted_business(self) -> None:
        data = _load_scenario("E14_rate_limit_unverified_business.json")
        store = InMemorySanitizedReportStore()
        limiter = RateLimiter(max_reports=2, window_seconds=600)
        map_adapter = MunicipalMapAdapter(threshold=5)
        engine = LocalIntelligenceAdapter()

        responses = [
            submit_report(
                data["input"],
                store=store,
                rate_limiter=limiter,
                map_adapter=map_adapter,
                engine=engine,
                now=500.0 + i,
            )
            for i in range(data["repeat_count"])
        ]

        last = responses[-1]
        self.assertTrue(last.rate_limited)
        self.assertEqual(last.verification_status, "sin_verificar")
        self.assertFalse(last.business_published)


if __name__ == "__main__":
    unittest.main()
