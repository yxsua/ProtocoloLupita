"""Pruebas unitarias de validadores CLABE, Luhn y generadores sintéticos."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.intel.validators import (
    compute_clabe_check_digit,
    generate_synthetic_card,
    generate_synthetic_clabe,
    verify_account,
)


class ValidatorsTests(unittest.TestCase):
    def test_valid_synthetic_clabe(self) -> None:
        clabe = generate_synthetic_clabe("999", "001", "00000000001")
        self.assertEqual(clabe, "999001000000000013")
        res = verify_account(clabe, "clabe")
        self.assertTrue(res.valid)
        self.assertEqual(res.reason, "ok")
        self.assertEqual(res.value_masked, "9990**********0013")
        self.assertIn("Sintético", res.synthetic_bank or "")

    def test_invalid_clabe_check_digit_e05(self) -> None:
        res = verify_account("999001000000000019", "clabe")
        self.assertFalse(res.valid)
        self.assertEqual(res.reason, "invalid_check_digit")

    def test_clabe_length_and_non_numeric(self) -> None:
        self.assertEqual(verify_account("999001000", "clabe").reason, "invalid_length")
        self.assertEqual(verify_account("99900100000000001X", "clabe").reason, "non_numeric")
        self.assertEqual(compute_clabe_check_digit("99901218000000001"), "6")

    def test_valid_and_invalid_luhn_card(self) -> None:
        card = generate_synthetic_card("400000", "123456789")
        res_ok = verify_account(card, "card")
        self.assertTrue(res_ok.valid)
        self.assertEqual(res_ok.reason, "ok")
        self.assertEqual(res_ok.value_masked, "************7899")

        bad_card = card[:-1] + ("0" if card[-1] != "0" else "1")
        res_bad = verify_account(bad_card, "card")
        self.assertFalse(res_bad.valid)
        self.assertEqual(res_bad.reason, "invalid_luhn")


if __name__ == "__main__":
    unittest.main()
