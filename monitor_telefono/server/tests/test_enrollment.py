from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import db
from conftest import csrf_from, login


def _create_enrollment(
    client: TestClient,
    *,
    name: str = "Teléfono de prueba",
    apps: list[str] | None = None,
) -> tuple[str, str]:
    login(client)
    page = client.get("/dispositivos")
    response = client.post(
        "/enrolamientos",
        data={
            "csrf_token": csrf_from(page.text),
            "nombre_sugerido": name,
            "apps_sugeridas": apps or [],
        },
    )
    assert response.status_code == 200
    code = re.search(
        r'id="enrollment-code" type="text" value="([A-HJ-NP-Z2-9]{8})"',
        response.text,
    )
    assert code
    assert "data:image/svg+xml;base64," in response.text
    return code.group(1), response.text


def _redeem(client: TestClient, code: str, *, accepted: bool = True):
    return client.post(
        "/api/enrolar",
        json={
            "code": code,
            "nombre": "Teléfono enrolado",
            "apps_permitidas": ["com.whatsapp"],
            "consentimiento": accepted,
        },
    )


def test_enrollment_is_hashed_single_use_and_token_can_send_events(client: TestClient) -> None:
    code, _ = _create_enrollment(client, apps=["com.whatsapp"])
    path = client.app.state.settings.database_path
    enrollment = db.get_enrollment(path, code)
    assert enrollment is not None
    assert enrollment["apps_sugeridas"] == ["com.whatsapp"]

    preview = client.post("/api/enrolar/preview", json={"code": f" {code.lower()} "})
    assert preview.status_code == 200
    assert preview.json()["apps_sugeridas"] == ["com.whatsapp"]
    assert _redeem(client, code, accepted=False).status_code == 400

    redeemed = _redeem(client, code)
    assert redeemed.status_code == 200
    token = redeemed.json()["token"]
    assert token
    with sqlite3.connect(path) as connection:
        stored_code_hash = connection.execute(
            "SELECT codigo_hash FROM enrolamientos"
        ).fetchone()[0]
        stored_token_hash = connection.execute(
            "SELECT token_hash FROM dispositivos"
        ).fetchone()[0]
    assert stored_code_hash != code
    assert stored_token_hash != token

    duplicate = _redeem(client, code)
    assert duplicate.status_code == 409
    event = {
        "id_evento": str(uuid.uuid4()),
        "tipo": "notificacion",
        "app": "com.whatsapp",
        "texto": "Evento posterior al enrolamiento",
        "fecha": datetime.now(timezone.utc).isoformat(),
    }
    accepted_event = client.post(
        "/api/eventos",
        json=event,
        headers={"X-Device-Key": token},
    )
    assert accepted_event.status_code == 201


def test_enrollment_expires_with_clear_error(client: TestClient) -> None:
    code, _ = _create_enrollment(client)
    path = client.app.state.settings.database_path
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE enrolamientos SET expira_en = ? ", (expired,))

    preview = client.post("/api/enrolar/preview", json={"code": code})
    assert preview.status_code == 410
    assert "caducó" in preview.json()["detail"]
    assert _redeem(client, code).status_code == 410


def test_enrollment_attempts_are_locked_after_five_failures(client: TestClient) -> None:
    for _ in range(5):
        response = client.post("/api/enrolar/preview", json={"code": "AAAAAAAA"})
        assert response.status_code == 404
    limited = client.post("/api/enrolar/preview", json={"code": "BBBBBBBB"})
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0


def test_heartbeat_online_offline_and_unlink(client: TestClient) -> None:
    assert client.get("/api/dispositivos/estado").status_code == 401
    code, _ = _create_enrollment(client)
    response = _redeem(client, code)
    token = response.json()["token"]
    device_id = response.json()["dispositivo"]["id"]
    path = client.app.state.settings.database_path

    devices_page = client.get("/dispositivos")
    assert "Sin conexión" in devices_page.text
    heartbeat = client.post("/api/latido", headers={"X-Device-Key": token})
    assert heartbeat.status_code == 200
    assert heartbeat.json()["ultimo_contacto"]
    assert "En línea" in client.get("/dispositivos").text

    stale = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE dispositivos SET ultimo_contacto = ? WHERE id = ?",
            (stale, device_id),
        )
    assert "Sin conexión" in client.get("/dispositivos").text

    unlinked = client.post("/api/desvincular", headers={"X-Device-Key": token})
    assert unlinked.status_code == 200
    assert client.post("/api/desvincular", headers={"X-Device-Key": token}).status_code == 200
    rejected = client.post(
        "/api/latido",
        headers={"X-Device-Key": token},
    )
    assert rejected.status_code == 401
    assert "revocado" in client.get("/dispositivos").text


def test_https_responses_include_hsts_and_secure_session_cookie(client: TestClient) -> None:
    response = client.get("https://testserver/login")
    assert response.status_code == 200
    assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
    cookie = response.headers["set-cookie"]
    assert "monitor_session=" in cookie
    assert "secure" in cookie.lower()


def test_public_enrollment_page_uses_redacted_code_query(client: TestClient) -> None:
    code, _ = _create_enrollment(client)
    page = client.get(f"/enroll?code={code}")
    assert page.status_code == 200
    assert "Abrir en la app" in page.text
    assert "monitortelefono://enroll" in page.text


def test_login_temporarily_locks_after_five_bad_passwords(client: TestClient) -> None:
    page = client.get("/login")
    csrf = csrf_from(page.text)
    for _ in range(5):
        failed = client.post(
            "/login",
            data={"csrf_token": csrf, "password": "wrong"},
            follow_redirects=False,
        )
        assert failed.status_code == 401
    locked = client.post(
        "/login",
        data={"csrf_token": csrf, "password": "test-monitor-password"},
        follow_redirects=False,
    )
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0
