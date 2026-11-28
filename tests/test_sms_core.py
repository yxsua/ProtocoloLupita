"""Pruebas unitarias puras para parser, dominios, reglas y techo de certeza SMS."""

from __future__ import annotations

import unittest

from app.modules.sms.domains import analyze_domain
from app.modules.sms.engine_adapter import cap_certainty
from app.modules.sms.parser import defang_url, extract_indicators
from app.modules.sms.rules import LocalClassifierProtocol, classify_sms_rules
from app.modules.sms.schemas import DomainSignal, EngineVerdict, SmsInput
from app.modules.sms.service import analyze_sms


class _StubLocalClassifier(LocalClassifierProtocol):
    def predict_label(self, sanitized_text: str, domain_checks: list[DomainSignal]) -> str | None:
        return "local_phishing_candidate"


class SmsCoreTests(unittest.TestCase):
    def test_defang_url_and_extract_indicators(self) -> None:
        self.assertEqual(defang_url("https://sat-falso.xyz/pago"), "hxxps://sat-falso.xyz/pago")
        self.assertEqual(defang_url("http://bit.ly/3abc"), "hxxp://bit.ly/3abc")

        ind = extract_indicators(
            "Pague en https://sat-falso.xyz/buzon o marque +52 55 1234 5678, CLABE 012180001234567899.",
            sender="SAT-AVISO",
        )
        self.assertEqual(ind.senders, ["SAT-AVISO"])
        self.assertEqual(ind.defanged_urls, ["hxxps://sat-falso.xyz/buzon"])
        self.assertEqual(ind.domains, ["sat-falso.xyz"])
        self.assertEqual(ind.phones, ["5512345678"])
        self.assertEqual(ind.accounts, ["012180001234567899"])

    def test_domain_signals_official_punycode_homoglyph_and_subdomain_spoof(self) -> None:
        official = analyze_domain("www.sat.gob.mx")
        self.assertTrue(official.is_official_exact)
        self.assertEqual(official.matched_official_entity, "SAT")

        spoof = analyze_domain("sat.gob.mx.verificacion.xyz")
        self.assertFalse(spoof.is_official_exact)
        self.assertIn("subdomain_spoof", spoof.reason_codes)

        puny = analyze_domain("xn--bbv-seguridad-8hb.com")
        self.assertTrue(puny.is_punycode)
        self.assertIn("punycode", puny.reason_codes)

        homoglyph = analyze_domain("s\u0430t.gob.mx")  # Cyrillic 'а'
        self.assertTrue(homoglyph.has_homoglyphs)
        self.assertFalse(homoglyph.is_official_exact)

        shortener = analyze_domain("bit.ly")
        self.assertTrue(shortener.is_shortener)

    def test_local_classifier_interface_and_certainty_cap(self) -> None:
        res = analyze_sms(
            SmsInput(
                sender="SAT-URG",
                body="SAT multa urgente en https://sat-gob-mx-alerta.xyz/pago",
            ),
            local_classifier=_StubLocalClassifier(),
        )
        self.assertEqual(res.model_label, "local_phishing_candidate")
        self.assertTrue(res.links_disabled)

        # Techo de certeza: si el motor da confianza baja, nunca sube a campana_corroborada
        status, conf = cap_certainty(
            EngineVerdict(
                campaign_id="C1",
                campaign_name="Test",
                status="campana_corroborada",
                confidence=0.55,
            )
        )
        self.assertEqual(status, "indicio")
        self.assertEqual(conf, 0.55)

        # Con rate_limited siempre queda sin_verificar
        rl_status, rl_conf = cap_certainty(
            EngineVerdict(
                campaign_id="C1",
                campaign_name="Test",
                status="campana_corroborada",
                confidence=0.95,
            ),
            rate_limited=True,
        )
        self.assertEqual(rl_status, "sin_verificar")
        self.assertLessEqual(rl_conf, 0.25)

    def test_benign_official_sms_not_marked_suspicious(self) -> None:
        checks = [analyze_domain("www.sat.gob.mx")]
        rule_res = classify_sms_rules(
            "Recordatorio informativo: consulta tus citas en https://www.sat.gob.mx.",
            checks,
        )
        self.assertFalse(rule_res.is_suspicious)
        self.assertEqual(rule_res.scam_type, "informativo_oficial")


if __name__ == "__main__":
    unittest.main()
