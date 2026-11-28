from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from getpass import getpass

from app import db
from app.auth import hash_password
from app.crypto import encrypt_text
from app.settings import Settings

_USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


def _password_from_args(args: argparse.Namespace) -> str:
    if args.password_env:
        value = os.getenv(args.password_env, "")
        if not value:
            raise ValueError(f"La variable {args.password_env} no está configurada.")
        return value
    password = getpass("Contraseña del administrador (mínimo 12 caracteres): ")
    confirmation = getpass("Confirma la contraseña: ")
    if password != confirmation:
        raise ValueError("Las contraseñas no coinciden.")
    return password


def _validate_totp_secret(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().replace(" ", "").upper()
    try:
        base64.b32decode(
            normalized + "=" * ((8 - len(normalized) % 8) % 8),
            casefold=True,
        )
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("--totp-secret debe ser Base32 válido.") from exc
    return normalized


def create_admin(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    db.initialize(settings.database_path, settings.data_encryption_key)
    if db.has_admin(settings.database_path):
        raise ValueError("Ya existe una cuenta administradora.")
    if not _USERNAME.fullmatch(args.username):
        raise ValueError("El usuario debe tener 3-64 caracteres: letras, números, punto, guion o guion bajo.")
    password = _password_from_args(args)
    password_hash = hash_password(password)
    totp_secret = _validate_totp_secret(args.totp_secret)
    encrypted_totp = encrypt_text(totp_secret, settings.data_encryption_key)
    db.create_account(
        settings.database_path,
        args.username,
        password_hash,
        "admin",
        encrypted_totp,
    )
    print(f"Cuenta administradora creada: {args.username}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-admin", help="Crea el primer administrador")
    create.add_argument("--username", default="admin")
    create.add_argument(
        "--password-env",
        help="Lee la contraseña desde esta variable de entorno, sin imprimirla.",
    )
    create.add_argument("--totp-secret", help="Secreto TOTP Base32 opcional.")
    args = parser.parse_args(argv)
    try:
        if args.command == "create-admin":
            return create_admin(args)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
