"""Pruebas para la base historica spam.csv y el bucle de analisis circular."""

from __future__ import annotations

import json
import unittest

from app.modules.citizen.map_adapter import MunicipalMapAdapter
from app.modules.citizen.rate_limit import RateLimiter
from app.modules.citizen.service import InMemorySanitizedReportStore, submit_report
from app.modules.sms.circular_store import CircularPatternStore
from app.modules.sms.dataset_classifier import SpamDatasetClassifier
from app.modules.sms.engine_adapter import LocalIntelligenceAdapter
from app.modules.sms.schemas import SmsInput
from app.modules.sms.service import analyze_sms


class CircularAndDatasetTests(unittest.TestCase):
    def test_spam_csv_dataset_loads_and_flags_known_scam_patterns(self) -> None:
        clf = SpamDatasetClassifier()
        self.assertTrue(clf.is_loaded)
        stats = clf.stats()
        self.assertEqual(stats["spam_messages"], 747)
        self.assertEqual(stats["ham_messages"], 4825)

        prob = clf.predict_spam_probability(
            "URGENT! You have won a FREE 1000 cash prize reward. Txt CLAIM to 87121 or call 09061701461 now!"
        )
        self.assertGreaterEqual(prob, 0.80)

        label = clf.predict_label("WINNER!! Claim your free prize at http://promo-win.xyz", [])
        self.assertIsNotNone(label)
        self.assertIn("dataset_spam_match", label or "")

    def test_circular_feedback_warns_second_citizen_without_leaking_pii(self) -> None:
        circular = CircularPatternStore()
        store = InMemorySanitizedReportStore()
        limiter = RateLimiter(max_reports=2, window_seconds=600)
        map_adapter = MunicipalMapAdapter(threshold=5)
        engine = LocalIntelligenceAdapter()

        # 1. Ciudadano A reporta una estafa con datos personales
        submit_report(
            {
                "channel": "sms",
                "municipality": "Guadalajara",
                "reported_sender_or_phone": "3344556677",
                "reported_url": "https://paquete-aduana-mx-pago.xyz/liberar",
                "description": (
                    "Me llamo Carlos Ruiz, CURP RUIC910303HJCRRL02. "
                    "Me llego SMS diciendo que mi paquete esta retenido en aduana y pague envio en https://paquete-aduana-mx-pago.xyz/liberar."
                ),
                "reporter_name": "Carlos Ruiz",
                "reporter_curp": "RUIC910303HJCRRL02",
                "reporter_phone": "3388776655",
                "session_token": "ciudadano-a",
            },
            store=store,
            rate_limiter=limiter,
            map_adapter=map_adapter,
            engine=engine,
            circular_store=circular,
        )

        # 2. Ciudadano B pega un SMS similar para verificar si es estafa
        analysis = analyze_sms(
            SmsInput(
                sender="3344556677",
                body="Tu paquete sigue retenido en aduana, paga envio aqui https://paquete-aduana-mx-pago.xyz/liberar",
            ),
            engine=engine,
            circular_store=circular,
        )

        self.assertTrue(analysis.is_suspicious)
        self.assertIn("circular_pattern_match", analysis.rule_signals)
        self.assertTrue(len(analysis.circular_matches) >= 1)
        self.assertIsNotNone(analysis.preventive_warning)
        self.assertIn("NO abras enlaces", analysis.preventive_warning or "")
        self.assertEqual(
            analysis.indicators.defanged_urls,
            ["hxxps://paquete-aduana-mx-pago.xyz/liberar"],
        )

        # Verificar cero fuga de PII de Ciudadano A
        serialized = json.dumps(analysis.to_dict()) + json.dumps(circular.list_recent_alerts())
        for pii in ("Carlos Ruiz", "RUIC910303HJCRRL02", "3388776655"):
            self.assertNotIn(pii, serialized)

    def test_rate_limited_report_does_not_poison_circular_store(self) -> None:
        circular = CircularPatternStore()
        store = InMemorySanitizedReportStore()
        limiter = RateLimiter(max_reports=2, window_seconds=600)
        map_adapter = MunicipalMapAdapter(threshold=5)
        engine = LocalIntelligenceAdapter()

        payload = {
            "channel": "sms",
            "municipality": "Zapopan",
            "reported_business_name": "Comercio Atacado",
            "description": "Reporte repetido sin pruebas.",
            "session_token": "spammer-1",
        }
        for i in range(3):
            submit_report(
                payload,
                store=store,
                rate_limiter=limiter,
                map_adapter=map_adapter,
                engine=engine,
                circular_store=circular,
                now=100.0 + i,
            )

        alerts = circular.list_recent_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["report_count"], 2)

    def test_official_sat_sms_stays_non_suspicious(self) -> None:
        res = analyze_sms(
            SmsInput(
                sender="SAT",
                body="Recordatorio informativo: consulta tus citas y avisos oficiales ingresando directamente a https://www.sat.gob.mx desde tu navegador.",
            ),
            circular_store=CircularPatternStore(),
        )
        self.assertFalse(res.is_suspicious)
        self.assertIsNone(res.preventive_warning)


if __name__ == "__main__":
    unittest.main()
