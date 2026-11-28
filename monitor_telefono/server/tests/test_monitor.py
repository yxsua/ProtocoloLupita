from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import db
from app.auth import verify_websocket_origin
from app.middleware import (
    RedactSensitiveQueryParamsMiddleware,
    SessionCookieSecurityMiddleware,
)
from app.settings import Settings
from conftest import csrf_from, login, register_device


def _event(
    *,
    kind: str = "notificacion",
    app: str = "com.whatsapp",
    text: str = "Mensaje de prueba",
    when: datetime | None = None,
) -> dict[str, object]:
    return {
        "id_evento": str(uuid.uuid4()),
        "tipo": kind,
        "app": app,
        "remitente": "Contacto de prueba",
        "texto": text,
        "fecha": (when or datetime.now(timezone.utc)).isoformat(),
    }


def test_login_is_required_and_session_and_security_headers_work(client: TestClient) -> None:
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/api/eventos").status_code == 401
    health = client.get("/api/salud")
    assert health.status_code == 200
    assert health.json() == {"estado": "ok"}

    login_page = client.get("/login")
    bad_login = client.post(
        "/login",
        data={"csrf_token": csrf_from(login_page.text), "password": "wrong"},
        follow_redirects=False,
    )
    assert bad_login.status_code == 401
    assert "La contraseña no es correcta" in bad_login.text

    correct_login = client.post(
        "/login",
        data={
            "csrf_token": csrf_from(bad_login.text),
            "password": "test-monitor-password",
        },
        follow_redirects=False,
    )
    assert correct_login.status_code == 303
    assert client.get("/").status_code == 200
    assert client.get("/eventos").status_code == 200
    assert "Content-Security-Policy" in client.get("/").headers
    assert client.cookies.get("monitor_session")


def test_device_number_requires_csrf_and_is_only_an_identifier(client: TestClient) -> None:
    login(client)
    page = client.get("/dispositivos")
    invalid = client.post(
        "/dispositivos",
        data={"csrf_token": csrf_from(page.text), "nombre": "<script>1234567</script>"},
    )
    assert invalid.status_code == 422
    assert "número de teléfono válido" in invalid.text

    missing_csrf = client.post("/dispositivos", data={"nombre": "+52 442 123 4567"})
    assert missing_csrf.status_code == 403

    registered = client.post(
        "/dispositivos",
        data={"csrf_token": csrf_from(page.text), "nombre": "+52 442 123 4567"},
    )
    assert registered.status_code == 200
    assert "No verifica" in registered.text
    assert re.search(r'id="device-token" type="text" value="[^"]+"', registered.text)


def test_device_auth_aliases_idempotency_and_query_key(client: TestClient) -> None:
    token = register_device(client)
    event = _event(text='Una línea con "comillas" y emoji 👋\nsegunda línea')

    no_key = client.post("/api/eventos", json=event)
    wrong_key = client.post(
        "/api/eventos",
        json=event,
        headers={"X-Device-Key": "not-the-device-key"},
    )
    assert no_key.status_code == 401
    assert wrong_key.status_code == 401

    accepted = client.post(
        "/api/eventos",
        json=event,
        headers={"X-Device-Key": token},
    )
    duplicate = client.post(
        "/api/eventos",
        json=event,
        headers={"X-Device-Key": token},
    )
    assert accepted.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicado"] is True

    alias_event = {
        "id_evento": str(uuid.uuid4()),
        "app_name": "com.telegram",
        "sender": "Remitente",
        "content": "Contenido por alias",
    }
    via_query = client.post(
        "/api/eventos?key=" + token,
        json=alias_event,
    )
    assert via_query.status_code == 201
    assert token not in via_query.text

    history = client.get("/api/eventos")
    assert history.status_code == 200
    items = history.json()["items"]
    assert len(items) == 2
    assert items[0]["texto"] == "Contenido por alias"
    assert items[1]["texto"] == event["texto"]
    assert items[1]["dispositivo"] == "+52 442 123 4567"


def test_malformed_json_limits_filters_and_cursor(client: TestClient) -> None:
    token = register_device(client)
    malformed = client.post(
        "/api/eventos",
        content=b'{"mensaje incompleto',
        headers={"X-Device-Key": token, "Content-Type": "application/json"},
    )
    assert malformed.status_code == 201

    now = datetime.now(timezone.utc)
    first = _event(
        kind="sms",
        app="com.whatsapp",
        text="texto filtrable",
        when=now - timedelta(days=10),
    )
    second = _event(
        kind="llamada",
        app="com.android.phone",
        text="llamada de prueba",
        when=now - timedelta(days=2),
    )
    second["direccion"] = "perdida"
    second["duracion_s"] = 0
    assert client.post("/api/eventos", json=first, headers={"X-Device-Key": token}).status_code == 201
    assert client.post("/api/eventos", json=second, headers={"X-Device-Key": token}).status_code == 201

    too_long = _event(text="x" * 4001)
    response = client.post(
        "/api/eventos",
        json=too_long,
        headers={"X-Device-Key": token},
    )
    assert response.status_code == 422
    invalid_call_fields = _event(kind="sms")
    invalid_call_fields["direccion"] = "entrante"
    response = client.post(
        "/api/eventos",
        json=invalid_call_fields,
        headers={"X-Device-Key": token},
    )
    assert response.status_code == 422

    page_one = client.get("/api/eventos?limit=1")
    assert page_one.status_code == 200
    assert len(page_one.json()["items"]) == 1
    cursor = page_one.json()["next_cursor"]
    assert cursor
    page_two = client.get("/api/eventos", params={"limit": 1, "cursor": cursor})
    assert len(page_two.json()["items"]) == 1
    assert page_two.json()["items"][0]["id_evento"] != page_one.json()["items"][0]["id_evento"]

    filtered = client.get(
        "/api/eventos",
        params={"app": "com.whatsapp", "tipo": "sms", "texto": "filtrable"},
    )
    assert [item["texto"] for item in filtered.json()["items"]] == ["texto filtrable"]
    date_filtered = client.get(
        "/api/eventos",
        params={
            "desde": (now - timedelta(days=5)).isoformat(),
            "hasta": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert [item["texto"] for item in date_filtered.json()["items"]] == ["llamada de prueba"]
    device_id = date_filtered.json()["items"][0]["dispositivo_id"]
    device_filtered = client.get("/api/eventos", params={"dispositivo": device_id})
    assert len(device_filtered.json()["items"]) == 3
    malformed_item = client.get("/api/eventos", params={"texto": "mensaje incompleto"})
    assert malformed_item.json()["items"][0]["texto"] == '{"mensaje incompleto'
    too_long_filter = client.get("/api/eventos", params={"texto": "x" * 201})
    assert too_long_filter.status_code == 422


def test_search_body_requires_csrf_and_filters_messages(client: TestClient) -> None:
    token = register_device(client)
    event = _event(text="frase privada para filtrar")
    assert client.post("/api/eventos", json=event, headers={"X-Device-Key": token}).status_code == 201

    csrf_token = csrf_from(client.get("/").text)
    body = {"texto": "frase privada", "limit": 10}
    denied = client.post("/api/eventos/buscar", json=body)
    assert denied.status_code == 403

    response = client.post(
        "/api/eventos/buscar",
        json=body,
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200
    assert [item["texto"] for item in response.json()["items"]] == [
        "frase privada para filtrar"
    ]


def test_sensitive_query_values_are_redacted_before_access_logging() -> None:
    captured: dict[str, object] = {}

    async def downstream(scope, _receive, _send):
        captured["query_string"] = scope["query_string"]
        captured["state"] = dict(scope["state"])

    async def unused(*_args):
        return None

    scope = {
        "type": "http",
        "query_string": b"texto=mensaje%20privado&limit=5&key=device-token&code=ABCD2345",
        "state": {},
    }
    middleware = RedactSensitiveQueryParamsMiddleware(downstream)
    asyncio.run(middleware(scope, unused, unused))

    sanitized = captured["query_string"]
    assert isinstance(sanitized, bytes)
    sanitized_params = parse_qs(sanitized.decode("ascii"))
    assert sanitized_params == {"texto": ["REDACTED"], "limit": ["5"]}
    assert b"mensaje" not in sanitized
    assert b"device-token" not in sanitized
    assert b"ABCD2345" not in sanitized
    assert captured["state"]["query_text_filter"] == "mensaje privado"
    assert captured["state"]["query_device_key"] == "device-token"
    assert captured["state"]["enrollment_code"] == "ABCD2345"


def test_session_cookie_is_secure_only_for_https_requests() -> None:
    async def app(scope, _receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"set-cookie", b"monitor_session=value; Path=/; HttpOnly")],
            }
        )

    async def unused(*_args):
        return None

    for scheme, expect_secure in (("https", True), ("http", False)):
        sent = []

        async def capture(message):
            sent.append(message)

        scope = {"type": "http", "scheme": scheme}
        middleware = SessionCookieSecurityMiddleware(app, "monitor_session")
        asyncio.run(middleware(scope, unused, capture))
        cookie = dict(sent[0]["headers"])[b"set-cookie"]
        assert (b"; Secure" in cookie) is expect_secure


def test_websocket_origin_accepts_public_base_url_host() -> None:
    websocket = SimpleNamespace(
        headers={
            "origin": "https://monitor.example.ts.net",
            "host": "127.0.0.1:8100",
        },
        url=SimpleNamespace(scheme="wss"),
    )
    assert verify_websocket_origin(websocket, "https://monitor.example.ts.net")
    assert not verify_websocket_origin(websocket, "https://other.example.ts.net")


def test_settings_load_and_validate_public_base_url(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_PASSWORD", "strong-enough-test-password")
    monkeypatch.setenv("SECRET_KEY", "test-signing-key-that-is-at-least-32-characters")
    monkeypatch.setenv("BASE_URL_PUBLICA", "https://monitor.example.ts.net/")
    assert Settings.from_env().base_url_publica == "https://monitor.example.ts.net/"

    monkeypatch.setenv("BASE_URL_PUBLICA", "https://monitor.example.ts.net/path")
    with pytest.raises(RuntimeError, match="BASE_URL_PUBLICA"):
        Settings.from_env()


def test_per_device_rate_limit(client: TestClient) -> None:
    token = register_device(client)
    client.app.state.settings = replace(
        client.app.state.settings,
        events_per_minute=1,
    )
    first = client.post(
        "/api/eventos",
        json=_event(),
        headers={"X-Device-Key": token},
    )
    second = client.post(
        "/api/eventos",
        json=_event(),
        headers={"X-Device-Key": token},
    )
    assert first.status_code == 201
    assert second.status_code == 429


def test_form_encoded_event_is_accepted(client: TestClient) -> None:
    token = register_device(client)
    response = client.post(
        "/api/eventos",
        data={
            "type": "sms",
            "package": "com.android.messaging",
            "from": "+52 442 000 0000",
            "body": "SMS de formulario",
        },
        headers={"X-Device-Key": token},
    )
    assert response.status_code == 201
    result = client.get("/api/eventos")
    assert result.json()["items"][0]["texto"] == "SMS de formulario"
    assert result.json()["items"][0]["remitente"] == "+52 442 000 0000"
    assert result.json()["items"][0]["tipo"] == "sms"


def test_websocket_requires_session_and_streams_new_events(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(
            "/ws/eventos",
            headers={"origin": "http://testserver"},
        ) as websocket:
            websocket.receive_text()
    assert denied.value.code == 4401

    token = register_device(client)
    existing = _event(text="Evento del historial")
    assert client.post(
        "/api/eventos",
        json=existing,
        headers={"X-Device-Key": token},
    ).status_code == 201
    history = client.get("/api/eventos")
    assert history.json()["items"][0]["texto"] == "Evento del historial"

    with client.websocket_connect(
        "/ws/eventos",
        headers={"origin": "http://testserver"},
    ) as websocket:
        live = _event(text="Evento en vivo")
        response = client.post(
            "/api/eventos",
            json=live,
            headers={"X-Device-Key": token},
        )
        assert response.status_code == 201
        received = websocket.receive_json()
        assert received["texto"] == "Evento en vivo"


def test_websocket_rejects_foreign_origin(client: TestClient) -> None:
    login(client)
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(
            "/ws/eventos",
            headers={"origin": "https://foreign.example"},
        ) as websocket:
            websocket.receive_text()
    assert denied.value.code == 4403


def test_revoke_delete_and_retention_remove_data(client: TestClient) -> None:
    token = register_device(client)
    event = _event()
    assert client.post("/api/eventos", json=event, headers={"X-Device-Key": token}).status_code == 201

    devices_page = client.get("/dispositivos")
    csrf = csrf_from(devices_page.text)
    device_id_match = re.search(r'action="/dispositivos/([^/]+)/revocar"', devices_page.text)
    assert device_id_match
    device_id = device_id_match.group(1)
    revoked = client.post(
        f"/dispositivos/{device_id}/revocar",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert revoked.status_code == 303
    assert client.post(
        "/api/eventos",
        json=_event(),
        headers={"X-Device-Key": token},
    ).status_code == 401

    settings: Settings = client.app.state.settings
    old_event = _event(when=datetime.now(timezone.utc) - timedelta(days=45))
    active_device, active_token = db.create_device(settings.database_path, "+52 442 987 6543")
    old_event["id_evento"] = str(uuid.uuid4())
    inserted, _ = db.insert_event(
        settings.database_path,
        active_device["id"],
        old_event,
        old_event["id_evento"],
    )
    assert inserted
    assert db.cleanup_retention(settings.database_path, 30) == 1

    delete_all = client.post(
        "/datos/borrar",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert delete_all.status_code == 303
    assert client.get("/api/eventos").json()["items"] == []

    deleted = client.post(
        f"/dispositivos/{active_device['id']}/eliminar",
        data={"csrf_token": csrf_from(devices_page.text)},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert client.post(
        "/api/eventos",
        json=_event(),
        headers={"X-Device-Key": active_token},
    ).status_code == 401
