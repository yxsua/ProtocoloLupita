"""Validadores de CLABE (18 dígitos + dígito verificador) y Luhn para tarjetas.

Genera únicamente cuentas sintéticas con prefijos ficticios para pruebas.
"""

from __future__ import annotations

import re
from typing import Literal

from .contracts import AccountVerification

CLABE_WEIGHTS = (3, 7, 1)

SYNTHETIC_BANKS: dict[str, str] = {
    "999": "Banco Demo Lupita (Sintético)",
    "998": "Banco Prueba Querétaro (Sintético)",
    "997": "Institución Ficticia Demo (Sintético)",
}

SYNTHETIC_CARD_BINS: tuple[str, ...] = ("400000", "555555", "411111")


def clean_digits(value: str) -> str:
    """Elimina espacios, guiones y separadores comunes conservando el texto si hay letras."""
    return re.sub(r"[\s\-._]", "", value.strip())


def mask_account_value(digits: str, kind: Literal["clabe", "card"]) -> str:
    """Enmascara una cuenta o tarjeta para exhibición segura en interfaz y reportes."""
    if not digits:
        return ""
    if kind == "clabe":
        if len(digits) <= 8:
            return "*" * len(digits)
        return f"{digits[:4]}{'*' * (len(digits) - 8)}{digits[-4:]}"
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def compute_clabe_check_digit(first_17: str) -> str:
    """Calcula el dígito verificador oficial Banxico (módulo 10, pesos 3-7-1)."""
    if len(first_17) != 17 or not first_17.isdigit():
        raise ValueError("Se requieren exactamente 17 dígitos numéricos para calcular el DV.")
    weighted_sum = sum(
        (int(char) * CLABE_WEIGHTS[idx % 3]) % 10
        for idx, char in enumerate(first_17)
    )
    check_digit = (10 - (weighted_sum % 10)) % 10
    return str(check_digit)


def verify_clabe(value: str) -> AccountVerification:
    """Valida longitud de 18 dígitos y dígito verificador de una CLABE."""
    cleaned = clean_digits(value)
    if not cleaned.isdigit():
        return AccountVerification(
            kind="clabe",
            valid=False,
            value_masked=mask_account_value(re.sub(r"\D", "", cleaned), "clabe"),
            reason="non_numeric",
        )
    if len(cleaned) != 18:
        return AccountVerification(
            kind="clabe",
            valid=False,
            value_masked=mask_account_value(cleaned, "clabe"),
            reason="invalid_length",
        )

    expected_dv = compute_clabe_check_digit(cleaned[:17])
    bank_code = cleaned[:3]
    synthetic_bank = SYNTHETIC_BANKS.get(bank_code)
    if cleaned[17] != expected_dv:
        return AccountVerification(
            kind="clabe",
            valid=False,
            value_masked=mask_account_value(cleaned, "clabe"),
            reason="invalid_check_digit",
            synthetic_bank=synthetic_bank,
        )

    return AccountVerification(
        kind="clabe",
        valid=True,
        value_masked=mask_account_value(cleaned, "clabe"),
        reason="ok",
        synthetic_bank=synthetic_bank,
    )


def compute_luhn_check_digit(partial_digits: str) -> str:
    """Calcula el dígito de control Luhn para completar una tarjeta sintética."""
    if not partial_digits.isdigit() or not partial_digits:
        raise ValueError("Se requieren dígitos numéricos para calcular dígito Luhn.")
    total = 0
    # Al calcular el dígito final (derecha), el último dígito de partial se duplica.
    for idx, ch in enumerate(reversed(partial_digits)):
        num = int(ch)
        if idx % 2 == 0:
            num *= 2
            if num > 9:
                num -= 9
        total += num
    return str((10 - (total % 10)) % 10)


def verify_luhn(value: str) -> AccountVerification:
    """Valida una tarjeta de 13 a 19 dígitos mediante el algoritmo de Luhn."""
    cleaned = clean_digits(value)
    if not cleaned.isdigit():
        return AccountVerification(
            kind="card",
            valid=False,
            value_masked=mask_account_value(re.sub(r"\D", "", cleaned), "card"),
            reason="non_numeric",
        )
    if not (13 <= len(cleaned) <= 19):
        return AccountVerification(
            kind="card",
            valid=False,
            value_masked=mask_account_value(cleaned, "card"),
            reason="invalid_length",
        )

    total = 0
    for idx, ch in enumerate(reversed(cleaned)):
        num = int(ch)
        if idx % 2 == 1:
            num *= 2
            if num > 9:
                num -= 9
        total += num

    is_valid = total % 10 == 0
    synthetic_bank = (
        "Tarjeta de Prueba Sintética"
        if cleaned.startswith(SYNTHETIC_CARD_BINS)
        else None
    )
    return AccountVerification(
        kind="card",
        valid=is_valid,
        value_masked=mask_account_value(cleaned, "card"),
        reason="ok" if is_valid else "invalid_luhn",
        synthetic_bank=synthetic_bank,
    )


def verify_account(value: str, kind: str) -> AccountVerification:
    """Contrato común verify_account(value, kind) para CLABE o tarjeta."""
    normalized_kind = kind.strip().lower()
    if normalized_kind == "clabe":
        return verify_clabe(value)
    if normalized_kind == "card":
        return verify_luhn(value)
    raise ValueError(f"Tipo de cuenta no soportado: {kind!r}. Use 'clabe' o 'card'.")


def generate_synthetic_clabe(
    bank_code: str = "999",
    branch_code: str = "001",
    account_body: str = "00000000001",
) -> str:
    """Genera una CLABE sintética válida usando un código de banco ficticio."""
    if bank_code not in SYNTHETIC_BANKS:
        raise ValueError(
            f"El código {bank_code!r} no está registrado como banco ficticio sintético."
        )
    if len(branch_code) != 3 or not branch_code.isdigit():
        raise ValueError("branch_code debe tener 3 dígitos.")
    if len(account_body) != 11 or not account_body.isdigit():
        raise ValueError("account_body debe tener 11 dígitos.")
    first_17 = f"{bank_code}{branch_code}{account_body}"
    return f"{first_17}{compute_clabe_check_digit(first_17)}"


def generate_synthetic_card(
    bin_prefix: str = "400000",
    account_body: str = "123456789",
) -> str:
    """Genera un número de tarjeta sintético válido por Luhn con BIN de prueba."""
    if bin_prefix not in SYNTHETIC_CARD_BINS:
        raise ValueError(f"El BIN {bin_prefix!r} no es un prefijo sintético permitido.")
    partial = f"{bin_prefix}{account_body}"
    if not (12 <= len(partial) <= 18) or not partial.isdigit():
        raise ValueError("La longitud parcial de tarjeta sintética debe estar entre 12 y 18.")
    return f"{partial}{compute_luhn_check_digit(partial)}"
