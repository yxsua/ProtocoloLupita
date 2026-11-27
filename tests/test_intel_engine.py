"""Pruebas punta a punta del motor de inteligencia sobre escenarios E01-E14."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.modules.intel import IntelEngine


def _load_scenarios(filename: str) -> list[dict]:
    data = json.loads((ROOT / "data" / "scenarios" / filename).read_text(encoding="utf-8"))
    return data["scenarios"]


class IntelEngineScenariosTests(unittest.TestCase):
    def test_calls_e01_to_e08_and_correlation_e12_e14(self) -> None:
        engine = IntelEngine()
        calls = {sc["id"]: sc for sc in _load_scenarios("e01_e08_calls.json")}
        corr = {sc["id"]: sc for sc in _load_scenarios("correlation_fixtures.json")}

        # E01: indicio con CLABE válida
        r1 = engine.process_event(calls["E01"])
        self.assertEqual(r1.status, "indicio")
        self.assertEqual(r1.threat_category, "extorsion_cobro_piso")
        self.assertEqual(r1.legal_tag, "posible_extorsion_ley_general_2025")
        self.assertTrue(any(i.type == "clabe" and i.valid for i in r1.indicators))
        self.assertIsNotNone(r1.campaign_id)

        # E02: secuestro virtual etiquetado
        r2 = engine.process_event(calls["E02"])
        self.assertEqual(r2.threat_category, "secuestro_virtual")
        self.assertEqual(r2.legal_tag, "posible_extorsion_ley_general_2025")

        # E03: falso ejecutivo bancario pidiendo NIP
        r3 = engine.process_event(calls["E03"])
        self.assertEqual(r3.threat_category, "falso_ejecutivo_bancario")
        self.assertEqual(r3.claimed_brand, "Banco Demo")
        self.assertIn("NIP", r3.requested_data)

        # E04: CLABE dictada en palabras
        r4 = engine.process_event(calls["E04"])
        clabes_e4 = [i for i in r4.indicators if i.type == "clabe"]
        self.assertEqual(len(clabes_e4), 1)
        self.assertTrue(clabes_e4[0].valid)
        self.assertEqual(clabes_e4[0].value_masked, "9990**********0016")

        # E05: dígito verificador incorrecto
        r5 = engine.process_event(calls["E05"])
        clabes_e5 = [i for i in r5.indicators if i.type == "clabe"]
        self.assertEqual(len(clabes_e5), 1)
        self.assertFalse(clabes_e5[0].valid)
        self.assertEqual(clabes_e5[0].validation_detail, "invalid_check_digit")

        # E06: prompt injection ignorado + comparte CLABE de E01 (corrobora campaña)
        r6 = engine.process_event(calls["E06"])
        self.assertEqual(r6.campaign_id, r1.campaign_id)

        # E07: fuente única queda como indicio de confianza baja
        r7 = engine.process_event(calls["E07"])
        self.assertEqual(r7.status, "indicio")
        self.assertEqual(r7.confidence_level, "baja")
        self.assertLess(r7.confidence, 0.5)

        # E08: llamada legítima sin alerta ni campaña
        r8 = engine.process_event(calls["E08"])
        self.assertEqual(r8.status, "sin_alerta")
        self.assertIsNone(r8.campaign_id)
        self.assertEqual(r8.threat_category, "no_aplica")

        # E12: reporte ciudadano que cruza con E01 y calcula ventaja de tiempo (2.5 h)
        r12 = engine.process_event(corr["E12"])
        self.assertEqual(r12.campaign_id, r1.campaign_id)
        self.assertEqual(r12.status, "corroborada")
        self.assertLessEqual(r12.confidence, 0.90)
        camp_e01 = engine.get_campaign(r1.campaign_id)  # type: ignore[arg-type]
        self.assertIsNotNone(camp_e01)
        self.assertEqual(camp_e01.detection_lead_hours, 2.5)

        # E14: límite de tasa mantiene estado sin_verificar y excluye de boletín
        r14 = engine.process_event(corr["E14"])
        self.assertEqual(r14.status, "sin_verificar")
        self.assertEqual(r14.match_reason, "unverified_override")
        bulletin = engine.get_epidemiological_bulletin()
        bulletin_ids = {c["campaign_id"] for c in bulletin["campaigns"]}
        self.assertNotIn(r14.campaign_id, bulletin_ids)

        # Verificador ciudadano + paquete autoridad + cadena de evidencia íntegra
        lookup = engine.lookup_indicator("999001000000000013")
        self.assertTrue(lookup.found)
        self.assertEqual(lookup.campaign_id, r1.campaign_id)
        self.assertEqual(lookup.status, "corroborada")

        auth_pkg = engine.get_authority_package(r1.campaign_id)  # type: ignore[arg-type]
        self.assertIsNotNone(auth_pkg)
        self.assertTrue(auth_pkg["synthetic"])
        self.assertIn("no bloquea", auth_pkg["notice"].lower())
        self.assertTrue(engine.verify_evidence_integrity().intact)

    def test_sms_e09_grouping_with_different_urls_and_origin_phone_isolation(self) -> None:
        engine = IntelEngine()
        sms_list = {sc["id"]: sc for sc in _load_scenarios("e09_e11_sms.json")}

        res_e09 = engine.process_event(sms_list["E09"])
        res_e09_var = engine.process_event(sms_list["E09-VAR"])
        self.assertEqual(res_e09.claimed_brand, "SAT")
        self.assertEqual(res_e09.threat_category, "smishing")
        self.assertEqual(res_e09_var.campaign_id, res_e09.campaign_id)
        self.assertEqual(res_e09_var.match_reason, "template_similarity")
        self.assertEqual(res_e09_var.status, "corroborada")

        notice = engine.get_impersonated_brand_notice(res_e09.campaign_id)  # type: ignore[arg-type]
        self.assertIsNotNone(notice)
        self.assertEqual(len(notice["defanged_urls"]), 2)
        self.assertTrue(all(u.startswith("hxxps://") for u in notice["defanged_urls"]))

        res_e10 = engine.process_event(sms_list["E10"])
        self.assertEqual(res_e10.claimed_brand, "DHL")
        self.assertEqual(res_e10.threat_category, "falso_premio_paquete")

        res_e11 = engine.process_event(sms_list["E11"])
        self.assertEqual(res_e11.claimed_brand, "BBVA")
        self.assertEqual(res_e11.threat_category, "falso_ejecutivo_bancario")
        self.assertEqual(res_e11.status, "indicio")

        # El número de origen por sí solo no debe fusionar dos campañas distintas
        a = engine.process_event(
            {
                "event_id": "orig-1",
                "occurred_at": "2026-11-27T17:00:00Z",
                "channel": "call",
                "trap_id": "TRAP-1",
                "origin_phone_masked": "+52 442 000 5555 (ficticio)",
                "source_fingerprint": "s1",
                "text_sanitized": "Deposite el rescate de su nieto a 998001000000000072.",
            }
        )
        b = engine.process_event(
            {
                "event_id": "orig-2",
                "occurred_at": "2026-11-27T17:05:00Z",
                "channel": "sms",
                "trap_id": "TRAP-2",
                "origin_phone_masked": "+52 442 000 5555 (ficticio)",
                "source_fingerprint": "s2",
                "text_sanitized": "DHL: paquete retenido en aduana, revise http://bit.ly/dhl-fake",
            }
        )
        self.assertNotEqual(a.campaign_id, b.campaign_id)

    def test_router_handlers_roundtrip(self) -> None:
        from app.modules.intel.router import (
            handle_extract_indicators,
            handle_get_bulletin,
            handle_lookup_indicator,
            handle_process_event,
            handle_verify_account,
            handle_verify_evidence,
        )

        isolated = IntelEngine()
        ver = handle_verify_account("999001000000000013", "clabe")
        self.assertTrue(ver["valid"])

        ext = handle_extract_indicators("Deposite a 999001000000000013", "call")
        self.assertEqual(ext[0]["type"], "clabe")

        res = handle_process_event(
            {
                "event_id": "r-1",
                "occurred_at": "2026-11-27T18:00:00Z",
                "channel": "call",
                "trap_id": "TRAP-R1",
                "source_fingerprint": "src-r1",
                "text_sanitized": "Cobro de piso, deposite a 999001000000000013.",
            },
            engine=isolated,
        )
        self.assertEqual(res["status"], "indicio")
        self.assertTrue(handle_lookup_indicator("999001000000000013", engine=isolated)["found"])
        self.assertEqual(handle_get_bulletin(engine=isolated)["active_campaigns_count"], 1)
        self.assertTrue(handle_verify_evidence(engine=isolated)["intact"])


if __name__ == "__main__":
    unittest.main()
