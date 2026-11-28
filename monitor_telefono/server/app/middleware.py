from __future__ import annotations

from urllib.parse import parse_qsl, urlencode


class RedactSensitiveQueryParamsMiddleware:
    """Redacta credenciales y texto de búsqueda antes de que Uvicorn registre la URL."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("query_string"):
            pairs = parse_qsl(scope["query_string"].decode("latin-1"), keep_blank_values=True)
            state = scope.setdefault("state", {})
            sanitized = []
            for name, value in pairs:
                if name.lower() in {"key", "code", "token"}:
                    state.setdefault(
                        "query_device_key" if name.lower() == "key" else "enrollment_code",
                        value,
                    )
                    continue
                if name == "texto":
                    state["query_text_filter"] = value
                    value = "REDACTED"
                sanitized.append((name, value))
            scope["query_string"] = urlencode(sanitized).encode("ascii")
        await self.app(scope, receive, send)


class SessionCookieSecurityMiddleware:
    """Marca la cookie de sesión como Secure en solicitudes HTTPS."""

    def __init__(self, app, session_cookie: str, force_secure: bool = False):
        self.app = app
        self.session_cookie = f"{session_cookie}=".encode("ascii")
        self.force_secure = force_secure

    async def __call__(self, scope, receive, send):
        secure = self.force_secure or scope.get("scheme") in {"https", "wss"}

        async def send_with_cookie_security(message):
            if scope["type"] == "http" and message["type"] == "http.response.start":
                headers = []
                for name, value in message.get("headers", []):
                    if name.lower() == b"set-cookie" and value.startswith(self.session_cookie):
                        parts = [part.strip() for part in value.split(b";")]
                        has_secure = any(part.lower() == b"secure" for part in parts[1:])
                        if secure and not has_secure:
                            parts.append(b"Secure")
                        elif not secure and has_secure:
                            parts = [part for part in parts if part.lower() != b"secure"]
                        value = b"; ".join(parts)
                    headers.append((name, value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cookie_security)
