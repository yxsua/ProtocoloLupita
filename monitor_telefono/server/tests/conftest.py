from __future__ import annotations

import re
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONITOR_PASSWORD", "test-monitor-password")
os.environ.setdefault("SECRET_KEY", "test-signing-key-that-is-at-least-32-characters")

from app.main import create_app
from app.settings import Settings


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        monitor_password="test-monitor-password",
        secret_key="test-signing-key-that-is-at-least-32-characters",
        database_path=tmp_path / "monitor.sqlite3",
        retention_days=30,
        port=8100,
        cookie_secure=False,
        events_per_minute=120,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "No se encontró el token CSRF en el formulario."
    return match.group(1)


def login(client: TestClient) -> None:
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": csrf_from(page.text),
            "password": "test-monitor-password",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def register_device(client: TestClient, phone: str = "+52 442 123 4567") -> str:
    login(client)
    page = client.get("/dispositivos")
    response = client.post(
        "/dispositivos",
        data={"csrf_token": csrf_from(page.text), "nombre": phone},
    )
    assert response.status_code == 200
    match = re.search(r'id="device-token" type="text" value="([^"]+)"', response.text)
    assert match, "No se mostró la clave nueva del dispositivo."
    return match.group(1)
