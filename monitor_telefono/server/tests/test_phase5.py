from __future__ import annotations

import sqlite3
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from argparse import Namespace

from fastapi.testclient import TestClient

from app import db
from app.auth import hash_password
from app.cli import create_admin
from cryptography.fernet import Fernet
from app.fraude.csv_source import load_rules_csv
from app.fraude.detector import evaluate_event
from app.privacy import consent_version
from conftest import TEST_PASSWORD, TEST_USERNAME, csrf_from, login, register_device

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "reglas_fraude.csv"


def test_console_command_creates_first_argon2_admin(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "bootstrap.sqlite3"
    monkeypatch.setenv("SECRET_KEY", "temporary-test-secret-key-at-least-32")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    passwords = iter(("secure-admin-password-123", "secure-admin-password-123"))
    monkeypatch.setattr("app.cli.getpass", lambda _prompt: next(passwords))

    assert create_admin(
        Namespace(username="bootstrap-admin", password_env=None, totp_secret=None)
    ) == 0
    account = db.get_account_by_username(database_path, "bootstrap-admin")
    assert account is not None
    assert account["rol"] == "admin"
    assert account["password_hash"] != "secure-admin-password-123"


def _send_event(
    client: TestClient,
    token: str,
    text: str,
    *,
    sender: str = "+52 442 123 4567",
) -> dict:
    event = {
        "id_evento": str(uuid.uuid4()),
        "tipo": "notificacion",
        "app": "com.whatsapp",
        "remitente": sender,
        "texto": text,
        "fecha": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post(
        "/api/eventos",
        json=event,
        headers={"X-Device-Key": token},
    )
    assert response.status_code == 201
    return {**event, "veredicto": response.json()["veredicto"]}


def _login_as(client: TestClient, username: str, password: str) -> None:
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": csrf_from(page.text),
            "username": username,
            "password": password,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_mexican_fraud_examples_and_legitimate_messages() -> None:
    suspicious = [
        "BBVA detectó un cargo no reconocido; comparte el código de seguridad ahora en https://bit.ly/autorizar",
        "Soy tu nieto, cambié de número. Estoy detenido; transfiere dinero ahora a esta cuenta.",
        "Ganaste un premio, paga con tarjeta de regalo hoy mismo para liberarlo.",
        "Tu paquete de Estafeta está retenido; instala esta aplicación para reprogramar https://cutt.ly/paquete",
        "Paga una tarjeta de regalo ahora mismo o publicaré tus fotos.",
    ]
    for text in suspicious:
        verdict = evaluate_event(
            {"texto": text, "remitente": "+52 442 000 0000"},
            rules_path=RULES_PATH,
        )
        assert verdict["riesgo"] > 0
        assert verdict["nivel"] in {"medio", "alto"}
        assert verdict["razones"]

    threshold_event = {
        "texto": suspicious[0],
        "remitente": "+52 442 000 0000",
    }
    baseline = evaluate_event(threshold_event, rules_path=RULES_PATH)
    score = baseline["riesgo"]
    assert evaluate_event(
        threshold_event,
        rules_path=RULES_PATH,
        medium_threshold=score,
        high_threshold=score + 1,
    )["nivel"] == "medio"
    assert evaluate_event(
        threshold_event,
        rules_path=RULES_PATH,
        medium_threshold=score - 1,
        high_threshold=score,
    )["nivel"] == "alto"

    legitimate = [
        "BBVA: Tu código de verificación es 123456. No lo compartas con nadie.",
        "BBVA: Se realizó una compra por $350.00 en una terminal. Si no la reconoces, consulta la app oficial.",
    ]
    for text in legitimate:
        verdict = evaluate_event(
            {"texto": text, "remitente": "BBVA"},
            rules_path=RULES_PATH,
        )
        assert verdict["nivel"] == "bajo"
        assert verdict["riesgo"] < 40

    malformed_url = evaluate_event(
        {"texto": "Aviso con enlace mal formado https://[::1", "remitente": "desconocido"},
        rules_path=RULES_PATH,
    )
    assert 0 <= malformed_url["riesgo"] <= 100


def test_admin_can_replace_valid_fraud_rules_csv(client: TestClient) -> None:
    login(client)
    test_rules_path = client.app.state.settings.database_path.parent / "test-rules.csv"
    client.app.state.settings = replace(
        client.app.state.settings,
        fraud_rules_path=test_rules_path,
    )
    page = client.get("/reglas")
    csv_content = (
        "rule_id,kind,value,entity,score,reason,enabled\n"
        "test.rule,phrase,codigo de seguridad,,35,Petición de código sospechosa,true\n"
    )
    response = client.post(
        "/reglas",
        data={"csrf_token": csrf_from(page.text)},
        files={"rules_csv": ("reglas.csv", csv_content, "text/csv")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    loaded = load_rules_csv(client.app.state.settings.fraud_rules_path)
    assert [rule.rule_id for rule in loaded] == ["test.rule"]


def test_event_api_returns_explainable_verdict_and_stores_text_encrypted(client: TestClient) -> None:
    token = register_device(client)
    event = _send_event(
        client,
        token,
        "Tu cuenta está bloqueada. Comparte tu código ahora mismo en https://bit.ly/bbva",
    )
    assert event["veredicto"]["nivel"] in {"medio", "alto"}
    assert event["veredicto"]["riesgo"] >= 40
    assert event["veredicto"]["razones"]

    with sqlite3.connect(client.app.state.settings.database_path) as connection:
        plain, encrypted = connection.execute(
            "SELECT texto, texto_cifrado FROM eventos WHERE id_evento = ?",
            (event["id_evento"],),
        ).fetchone()
    assert plain is None
    assert encrypted and event["texto"] not in encrypted


def test_reviewer_is_restricted_audited_and_can_mark_alerts(client: TestClient) -> None:
    token = register_device(client)
    sender = "+52 442 765 4321"
    for index in range(4):
        _send_event(client, token, f"Conversación previa legítima {index}", sender=sender)
    alert = _send_event(
        client,
        token,
        "BBVA: comparte tu código ahora mismo para evitar el bloqueo https://bit.ly/seguro",
        sender=sender,
    )

    db.create_account(
        client.app.state.settings.database_path,
        "revisor-uno",
        hash_password("password-revisor-seguro-123"),
        "revisor",
    )
    admin_page = client.get("/")
    client.post(
        "/logout",
        data={"csrf_token": csrf_from(admin_page.text)},
        follow_redirects=False,
    )
    _login_as(client, "revisor-uno", "password-revisor-seguro-123")

    assert client.get("/api/eventos").status_code == 403
    assert client.get("/dispositivos").status_code == 403
    assert client.get("/auditoria").status_code == 403

    queue_page = client.get("/revisiones")
    assert queue_page.status_code == 200
    queue = client.get("/api/revisiones")
    assert queue.status_code == 200
    items = queue.json()["items"]
    assert len(items) == 1
    assert items[0]["id_evento"] == alert["id_evento"]
    assert len(items[0]["contexto"]) == 3
    assert "dispositivo_id" not in items[0]
    assert [previous["texto"] for previous in items[0]["contexto"]] == [
        "Conversación previa legítima 3",
        "Conversación previa legítima 2",
        "Conversación previa legítima 1",
    ]

    marked = client.post(
        f"/api/revisiones/{alert['id_evento']}/marcar",
        json={"estado": "confirmado"},
        headers={"X-CSRF-Token": csrf_from(queue_page.text)},
    )
    assert marked.status_code == 200
    assert marked.json()["revision_estado"] == "confirmado"
    audit = db.list_audit(client.app.state.settings.database_path)
    assert any(entry["accion"] == "view_review_queue" and entry["actor"] == "revisor-uno" for entry in audit)
    assert any(entry["accion"] == "mark_event" and entry["actor"] == "revisor-uno" for entry in audit)
    with sqlite3.connect(client.app.state.settings.database_path) as connection:
        try:
            connection.execute("UPDATE auditoria SET accion = 'tampered' WHERE id = 1")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("La bitácora permitió modificar una entrada existente.")
    try:
        with sqlite3.connect(client.app.state.settings.database_path) as connection:
            connection.execute("DELETE FROM auditoria WHERE id = 1")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("La bitácora permitió borrar una entrada existente.")

    client.post(
        "/logout",
        data={"csrf_token": csrf_from(queue_page.text)},
        follow_redirects=False,
    )
    _login_as(client, TEST_USERNAME, TEST_PASSWORD)
    statistics = client.get("/api/admin/reglas/estadisticas")
    assert statistics.status_code == 200
    assert any(rule["confirmados"] == 1 for rule in statistics.json()["reglas"])


def test_reviewers_see_all_only_for_devices_with_matching_consent(client: TestClient) -> None:
    login(client)
    original_settings = client.app.state.settings
    old_device, old_token = db.create_device(original_settings.database_path, "Consentimiento anterior")
    old_normal = _send_event(client, old_token, "Aviso normal anterior")
    old_alert = _send_event(
        client,
        old_token,
        "BBVA solicita tu código ahora mismo https://bit.ly/alerta",
    )

    updated_settings = replace(original_settings, reviewers_see_all=True)
    client.app.state.settings = updated_settings
    new_device, new_token = db.create_device(updated_settings.database_path, "Consentimiento actualizado")
    current_version = consent_version(updated_settings)
    with sqlite3.connect(updated_settings.database_path) as connection:
        connection.execute(
            "UPDATE dispositivos SET consentimiento_version = ? WHERE id = ?",
            (current_version, new_device["id"]),
        )
    new_normal = _send_event(client, new_token, "Aviso normal con consentimiento actualizado")

    db.create_account(
        updated_settings.database_path,
        "revisor-dos",
        hash_password("password-revisor-seguro-456"),
        "revisor",
    )
    admin_page = client.get("/")
    client.post(
        "/logout",
        data={"csrf_token": csrf_from(admin_page.text)},
        follow_redirects=False,
    )
    _login_as(client, "revisor-dos", "password-revisor-seguro-456")
    response = client.get("/api/revisiones")
    assert response.status_code == 200
    visible_ids = {item["id_evento"] for item in response.json()["items"]}
    assert old_alert["id_evento"] in visible_ids
    assert new_normal["id_evento"] in visible_ids
    assert old_normal["id_evento"] not in visible_ids


def test_owner_can_view_export_and_delete_only_their_device_data(client: TestClient) -> None:
    settings = client.app.state.settings
    device, token = db.create_device(settings.database_path, "Teléfono propietario")
    other_device, other_token = db.create_device(settings.database_path, "Otro teléfono")
    own = _send_event(client, token, "Mensaje privado del propietario")
    other = _send_event(client, other_token, "Mensaje de otra persona")

    own_events = client.get("/api/mis-eventos", headers={"X-Device-Key": token})
    assert own_events.status_code == 200
    assert [item["id_evento"] for item in own_events.json()["items"]] == [own["id_evento"]]
    exported = client.get("/api/mis-eventos/exportar", headers={"X-Device-Key": token})
    assert exported.status_code == 200
    assert exported.json()["eventos"][0]["texto"] == own["texto"]

    deleted = client.post(
        "/api/mis-datos/borrar",
        json={"confirmar": True},
        headers={"X-Device-Key": token},
    )
    assert deleted.status_code == 200
    assert deleted.json()["eventos_borrados"] == 1
    assert client.get("/api/mis-eventos", headers={"X-Device-Key": token}).status_code == 401
    remaining = db.query_events(
        settings.database_path,
        settings.data_encryption_key,
        limit=10,
    )["items"]
    assert [item["id_evento"] for item in remaining] == [other["id_evento"]]
    assert db.get_device(settings.database_path, device["id"]) is None
    assert db.get_device(settings.database_path, other_device["id"]) is not None


def test_privacy_retention_clears_normal_text_and_expires_old_alerts(client: TestClient) -> None:
    token = register_device(client)
    normal = _send_event(client, token, "Aviso normal sin alerta")
    alert = _send_event(
        client,
        token,
        "BBVA: comparte tu código ahora mismo https://bit.ly/cuenta",
    )
    path = client.app.state.settings.database_path
    old_normal = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    old_alert = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE eventos SET recibido_en = ? WHERE id_evento = ?",
            (old_normal, normal["id_evento"]),
        )
        connection.execute(
            "UPDATE eventos SET recibido_en = ? WHERE id_evento = ?",
            (old_alert, alert["id_evento"]),
        )

    db.cleanup_privacy_retention(path, retention_days=30, normal_text_hours=24, alert_days=90)
    normal_result = db.query_events(
        path,
        client.app.state.settings.data_encryption_key,
        limit=10,
    )["items"]
    by_id = {item["id_evento"]: item for item in normal_result}
    assert by_id[normal["id_evento"]]["texto"] is None
    assert alert["id_evento"] not in by_id
