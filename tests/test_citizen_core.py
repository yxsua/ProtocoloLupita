"""Pruebas unitarias puras para saneamiento PII, limite de tasa y mapa municipal."""

from __future__ import annotations

import unittest

from app.modules.citizen.map_adapter import MunicipalMapAdapter
from app.modules.citizen.rate_limit import RateLimiter
from app.modules.citizen.sanitizer import sanitize_report
from app.modules.citizen.schemas import CitizenReportRaw
from app.modules.citizen.service import InMemorySanitizedReportStore, submit_report
from app.modules.sms.engine_adapter import LocalIntelligenceAdapter


class CitizenCoreTests(unittest.TestCase):
    def test_sanitize_report_discards_all_pii_fields_and_inline_pii(self) -> None:
        raw = CitizenReportRaw(
            channel="sms",
            municipality="Guadalajara",
            description=(
                "Soy Maria Perez, mi CURP es PEMM850202MDFRRL01, mi correo maria@ejemplo.com "
                "y mi numero es 3311223344. Me mandaron https://sat-falso.xyz/pago."
            ),
            reported_sender_or_phone="5589012345",
            reported_url="https://sat-falso.xyz/pago",
            reporter_name="Maria Perez",
            reporter_curp="PEMM850202MDFRRL01",
            reporter_phone="3311223344",
            reporter_email="maria@ejemplo.com",
            reporter_address="Calle Falsa 123",
            extra_fields={"rfc_personal": "PEMM850202AAA"},
        )
        sanitized = sanitize_report(raw)
        serialized = str(sanitized.to_dict())

        for secret in (
            "Maria Perez",
            "PEMM850202MDFRRL01",
            "3311223344",
            "maria@ejemplo.com",
            "Calle Falsa 123",
            "PEMM850202AAA",
            "https://",
        ):
            self.assertNotIn(secret, serialized)

        self.assertIn("hxxps://sat-falso.xyz/pago", sanitized.indicators.defanged_urls)
        self.assertIn("5589012345", sanitized.indicators.phones)
        self.assertIn("nombre", sanitized.discarded_pii_fields)
        self.assertIn("curp", sanitized.discarded_pii_fields)

    def test_rate_limiter_and_unverified_business_protection(self) -> None:
        store = InMemorySanitizedReportStore()
        limiter = RateLimiter(max_reports=2, window_seconds=300)
        map_adapter = MunicipalMapAdapter(threshold=5)
        engine = LocalIntelligenceAdapter()

        payload = {
            "channel": "sms",
            "municipality": "Zapopan",
            "reported_business_name": "Tienda Dudosa",
            "description": "Cobro indebido reportado.",
            "session_token": "tok-1",
        }
        r1 = submit_report(payload, store=store, rate_limiter=limiter, map_adapter=map_adapter, engine=engine, now=100.0)
        r2 = submit_report(payload, store=store, rate_limiter=limiter, map_adapter=map_adapter, engine=engine, now=110.0)
        r3 = submit_report(payload, store=store, rate_limiter=limiter, map_adapter=map_adapter, engine=engine, now=120.0)

        self.assertFalse(r1.rate_limited)
        self.assertFalse(r2.rate_limited)
        self.assertTrue(r3.rate_limited)
        self.assertEqual(r3.verification_status, "sin_verificar")
        self.assertFalse(r3.business_published)

    def test_municipal_threshold_5_keeps_global_total(self) -> None:
        adapter = MunicipalMapAdapter(threshold=5)
        for _ in range(5):
            adapter.record_report("Guadalajara")
        for _ in range(4):
            adapter.record_report("Tlaquepaque")

        agg = adapter.get_map_aggregates()
        self.assertEqual(agg.total_reports, 9)
        self.assertEqual([(m.municipality, m.count) for m in agg.visible_municipalities], [("Guadalajara", 5)])
        self.assertEqual(agg.hidden_municipalities_count, 1)


if __name__ == "__main__":
    unittest.main()
