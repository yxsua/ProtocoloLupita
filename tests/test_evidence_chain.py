"""Pruebas de cadena ordenada de hashes y detección de alteración deliberada."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.evidence import EvidenceStore, verify_chain


class EvidenceChainTests(unittest.TestCase):
    def test_chain_integrity_and_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "evidence.sqlite3"
            store = EvidenceStore(db_path=db_path)
            r1 = store.append("evt-1", "2026-11-27T10:00:00Z", {"campaign": "CMP-001", "val": 1})
            r2 = store.append("evt-2", "2026-11-27T10:05:00Z", {"campaign": "CMP-001", "val": 2})

            self.assertEqual(r1.seq, 1)
            self.assertEqual(r2.prev_hash, r1.record_hash)
            self.assertTrue(store.verify_integrity().intact)

            # Reabrir desde SQLite confirma persistencia determinista
            reloaded = EvidenceStore(db_path=db_path)
            self.assertTrue(reloaded.verify_integrity().intact)

            # Alteración deliberada de un fixture/registro
            records = [rec.to_dict() for rec in reloaded.list_records()]
            records[1]["payload"]["val"] = 999
            check = verify_chain(records)
            self.assertFalse(check.intact)
            self.assertEqual(check.broken_at_seq, 2)
            self.assertIn("payload_hash", check.reason or "")


if __name__ == "__main__":
    unittest.main()
