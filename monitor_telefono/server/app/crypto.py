from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


def _cipher(key: str) -> Fernet:
    try:
        return Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as exc:
        raise RuntimeError("DATA_ENCRYPTION_KEY no es una clave Fernet válida.") from exc


def encrypt_text(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    return _cipher(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    try:
        return _cipher(key).decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
        raise RuntimeError(
            "No se pudo descifrar un mensaje; verifica DATA_ENCRYPTION_KEY."
        ) from exc
