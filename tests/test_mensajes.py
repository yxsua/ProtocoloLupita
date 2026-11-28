from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.mensajes.router import HubEventos, hub


@pytest.fixture(autouse=True)
def limpiar_historial():
    hub.historial.clear()
    yield
    hub.historial.clear()


def _evento(texto: str = "Hola, ¿puedes llamarme?") -> dict:
    return {
        "dispositivo": "tel-01",
        "tipo": "notificacion",
        "app": "com.whatsapp",
        "remitente": "Contacto de prueba",
        "texto": texto,
    }


def test_post_sin_clave_configurada_devuelve_401(monkeypatch):
    monkeypatch.delenv("LUPITA_DEVICE_KEY", raising=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/eventos",
            headers={"X-Device-Key": "cualquier-clave"},
            json=_evento(),
        )
    assert response.status_code == 401


def test_post_sin_header_de_clave_devuelve_401(monkeypatch):
    monkeypatch.setenv("LUPITA_DEVICE_KEY", "clave-correcta")
    with TestClient(app) as client:
        response = client.post("/api/eventos", json=_evento())
    assert response.status_code == 401


def test_post_con_clave_incorrecta_devuelve_401(monkeypatch):
    monkeypatch.setenv("LUPITA_DEVICE_KEY", "clave-correcta")
    with TestClient(app) as client:
        response = client.post(
            "/api/eventos",
            headers={"X-Device-Key": "clave-incorrecta"},
            json=_evento(),
        )
    assert response.status_code == 401


def test_post_valido_devuelve_201_y_get_lista_el_evento(monkeypatch):
    monkeypatch.setenv("LUPITA_DEVICE_KEY", "clave-correcta")
    with TestClient(app) as client:
        response = client.post(
            "/api/eventos",
            headers={"X-Device-Key": "clave-correcta"},
            json=_evento(),
        )
        listado = client.get("/api/eventos")

    assert response.status_code == 201
    assert response.json() == {"ok": True}
    assert listado.status_code == 200
    assert listado.json()[0]["texto"] == "Hola, ¿puedes llamarme?"
    assert listado.json()[0]["dispositivo"] == "tel-01"


def test_acepta_sms_y_llamadas_con_sus_campos(monkeypatch):
    monkeypatch.setenv("LUPITA_DEVICE_KEY", "clave-correcta")
    eventos = [
        {
            **_evento("SMS recibido"),
            "tipo": "sms",
            "direccion": "entrante",
        },
        {
            **_evento(""),
            "tipo": "llamada",
            "texto": None,
            "direccion": "saliente",
            "duracion_s": 42,
        },
    ]
    with TestClient(app) as client:
        respuestas = [
            client.post(
                "/api/eventos",
                headers={"X-Device-Key": "clave-correcta"},
                json=evento,
            )
            for evento in eventos
        ]
        listado = client.get("/api/eventos").json()

    assert [respuesta.status_code for respuesta in respuestas] == [201, 201]
    assert [evento["tipo"] for evento in listado] == ["llamada", "sms"]
    assert listado[0]["duracion_s"] == 42
    assert listado[0]["direccion"] == "saliente"


def test_get_ordena_del_mas_reciente_al_mas_antiguo(monkeypatch):
    monkeypatch.setenv("LUPITA_DEVICE_KEY", "clave-correcta")
    with TestClient(app) as client:
        for texto in ("anterior", "reciente"):
            response = client.post(
                "/api/eventos",
                headers={"X-Device-Key": "clave-correcta"},
                json=_evento(texto),
            )
            assert response.status_code == 201
        listado = client.get("/api/eventos")

    assert [evento["texto"] for evento in listado.json()] == ["reciente", "anterior"]


def test_pagina_mensajes_renderiza_plantilla_separada():
    with TestClient(app) as client:
        response = client.get("/mensajes")

    assert response.status_code == 200
    assert "Mensajes, SMS y llamadas" in response.text
    assert "textContent" in response.text


def test_ruta_eventos_anterior_redirige_a_pagina_mensajes():
    with TestClient(app) as client:
        response = client.get("/eventos")

    assert response.status_code == 200
    assert response.url.path == "/mensajes"


def test_historial_se_limita_a_200_eventos(monkeypatch):
    monkeypatch.setenv("LUPITA_DEVICE_KEY", "clave-correcta")
    with TestClient(app) as client:
        for index in range(201):
            response = client.post(
                "/api/eventos",
                headers={"X-Device-Key": "clave-correcta"},
                json=_evento(str(index)),
            )
            assert response.status_code == 201
        listado = client.get("/api/eventos").json()

    assert len(listado) == 200
    assert listado[0]["texto"] == "200"
    assert listado[-1]["texto"] == "1"


def test_websocket_envia_historial_y_eventos_nuevos(monkeypatch):
    monkeypatch.setenv("LUPITA_DEVICE_KEY", "clave-correcta")
    with TestClient(app) as client:
        primera = client.post(
            "/api/eventos",
            headers={"X-Device-Key": "clave-correcta"},
            json=_evento("Evento en historial"),
        )
        assert primera.status_code == 201

        with client.websocket_connect("/ws/eventos") as websocket:
            assert websocket.receive_json()["texto"] == "Evento en historial"
            nueva = client.post(
                "/api/eventos",
                headers={"X-Device-Key": "clave-correcta"},
                json=_evento("Evento en vivo"),
            )
            assert nueva.status_code == 201
            assert websocket.receive_json()["texto"] == "Evento en vivo"


def test_websocket_reproduce_historial_antes_de_eventos_concurrentes():
    eventos = HubEventos()
    eventos.historial.append({"texto": "historial"})
    recibidos: list[str] = []

    class SocketSimulado:
        async def accept(self):
            pass

        async def send_json(self, evento):
            recibidos.append(evento["texto"])
            if evento["texto"] == "historial":
                await eventos.emitir({"texto": "nuevo"})

    async def conectar():
        socket = SocketSimulado()
        await eventos.conectar(socket)
        eventos.desconectar(socket)

    asyncio.run(conectar())
    assert recibidos == ["historial", "nuevo"]
