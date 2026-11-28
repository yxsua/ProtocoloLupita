from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, WebSocket
from starlette.concurrency import run_in_threadpool

from app import db


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
    return bool(request.session.get("authenticated"))


def require_api_session(request: Request) -> None:
    if not session_active(request):
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")


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
