from __future__ import annotations

import hashlib
import hmac
import struct
import base64
import secrets
import time
from typing import Any
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request, WebSocket
from starlette.concurrency import run_in_threadpool

from app import db
from app.crypto import decrypt_text

_PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def verify_csrf(request: Request, submitted: str | None) -> None:
    expected = request.session.get("csrf_token")
    if not expected or not submitted or not hmac.compare_digest(expected, submitted):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")


def session_active(request: Request | WebSocket) -> bool:
    return bool(request.session.get("user_id") and request.session.get("role"))


def session_role(request: Request | WebSocket) -> str | None:
    role = request.session.get("role")
    return role if role in {"admin", "revisor"} else None


def require_api_session(request: Request) -> None:
    if not session_active(request):
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")


def require_admin(request: Request) -> None:
    require_api_session(request)
    if session_role(request) != "admin":
        raise HTTPException(status_code=403, detail="Esta acción requiere una cuenta administradora.")


def require_reviewer_or_admin(request: Request) -> None:
    require_api_session(request)
    if session_role(request) not in {"admin", "revisor"}:
        raise HTTPException(status_code=403, detail="No tienes permiso para revisar alertas.")


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("La contraseña debe tener entre 12 y 1024 caracteres.")
    return _PASSWORDS.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _PASSWORDS.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _PASSWORDS.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def verify_totp(secret: str, submitted: str, *, timestamp: int | None = None) -> bool:
    if len(submitted) != 6 or not submitted.isdigit():
        return False
    try:
        key = secret.strip().replace(" ", "").upper()
        decoded = base64.b32decode(
            key + "=" * ((8 - len(key) % 8) % 8),
            casefold=True,
        )
    except (ValueError, base64.binascii.Error):
        return False
    current = int(time.time() if timestamp is None else timestamp) // 30
    for offset in (-1, 0, 1):
        digest = hmac.new(decoded, struct.pack(">Q", current + offset), hashlib.sha1).digest()
        index = digest[-1] & 0x0F
        code = (struct.unpack(">I", digest[index : index + 4])[0] & 0x7FFFFFFF) % 1_000_000
        if hmac.compare_digest(f"{code:06d}", submitted):
            return True
    return False


def account_totp_secret(account: dict[str, Any], encryption_key: str) -> str | None:
    return decrypt_text(account.get("totp_secret_encrypted"), encryption_key)


def verify_websocket_origin(
    websocket: WebSocket,
    public_base_url: str | None = None,
) -> bool:
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    if not origin or not host:
        return False
    parsed = urlsplit(origin)
    scheme = websocket.url.scheme
    expected_scheme = "https" if scheme in {"https", "wss"} else "http"
    allowed_hosts = {host.lower()}
    if public_base_url:
        public_host = urlsplit(public_base_url).netloc
        if public_host:
            allowed_hosts.add(public_host.lower())
    return parsed.scheme == expected_scheme and parsed.netloc.lower() in allowed_hosts


def extract_device_token(request: Request) -> str | None:
    header_token = request.headers.get("x-device-key")
    if header_token:
        return header_token
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
        if bearer:
            return bearer
    return request.scope.get("state", {}).get("query_device_key")


async def authenticate_device(
    request: Request,
    *,
    allow_revoked: bool = False,
) -> dict[str, Any]:
    token = extract_device_token(request)
    if not token or len(token) > 256:
        raise HTTPException(status_code=401, detail="Token de dispositivo inválido.")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    device = await run_in_threadpool(
        db.get_device_by_token_hash,
        request.app.state.settings.database_path,
        token_hash,
    )
    if (
        not device
        or (device["estado"] != "activo" and not allow_revoked)
        or not hmac.compare_digest(device["token_hash"], token_hash)
    ):
        raise HTTPException(status_code=401, detail="Token de dispositivo inválido.")
    if device["estado"] == "activo":
        await run_in_threadpool(
            db.touch_device,
            request.app.state.settings.database_path,
            device["id"],
        )
    return device
