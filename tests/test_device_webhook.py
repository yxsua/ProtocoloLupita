"""Pruebas para el webhook de recepcion automatica desde telefono."""

from __future__ import annotations

import json
import unittest

from app.modules.sms.circular_store import CircularPatternStore
from app.modules.sms.engine_adapter import LocalIntelligenceAdapter
from app.modules.sms.service import InMemoryLiveSmsInbox, ingest_device_sms


class DeviceWebhookTests(unittest.TestCase):
    def test_ingest_device_sms_sanitizes_pii_defangs_urls_and_updates_inbox(self) -> None:
        inbox = InMemoryLiveSmsInbox()
        circular = CircularPatternStore()
        engine = LocalIntelligenceAdapter()

        entry = ingest_device_sms(
            {
                "sender": "5512349988",
                "municipality": "Guadalajara",
                "body": (
                    "SAT: Soy Juan Perez CURP PERJ900101HDFRRL01, regulariza tu multa en "
                    "https://sat-gob-mx-multa.xyz/pagar ahora."
                ),
                "reporter_name": "Juan Perez",
                "reporter_curp": "PERJ900101HDFRRL01",
            },
            live_inbox=inbox,
            engine=engine,
            circular_store=circular,
        )

        items = inbox.list_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(entry["source"], "dispositivo")
        self.assertTrue(entry["analysis"]["is_suspicious"])
        self.assertEqual(
            entry["analysis"]["indicators"]["defanged_urls"],
            ["hxxps://sat-gob-mx-multa.xyz/pagar"],
        )

        serialized = json.dumps(items)
        self.assertNotIn("Juan Perez", serialized)
        self.assertNotIn("PERJ900101HDFRRL01", serialized)
        self.assertNotIn("https://", serialized)


if __name__ == "__main__":
    unittest.main()
