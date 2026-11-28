"""Recepción y transmisión en memoria de eventos Android."""

from __future__ import annotations

import os
import secrets
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator

router = APIRouter(tags=["mensajes y dispositivos"])
_APP_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(_APP_DIR / "templates"))


class Evento(BaseModel):
    """Campos limitados que puede enviar el bridge Android."""

    model_config = ConfigDict(extra="forbid")

    dispositivo: str = Field(min_length=1, max_length=64)
    tipo: Literal["notificacion", "sms", "llamada"]
    app: str = Field(default="desconocida", min_length=1, max_length=128)
    remitente: Optional[str] = Field(default=None, max_length=256)
    texto: Optional[str] = Field(default=None, max_length=4000)
    direccion: Optional[Literal["entrante", "saliente", "perdida"]] = None
    duracion_s: Optional[int] = Field(default=None, ge=0, le=86400)
    fecha: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("fecha")
    @classmethod
    def fecha_en_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class HubEventos:
    """Mantiene como máximo 200 eventos y limpia sockets desconectados."""

    def __init__(self, maximo: int = 200) -> None:
        self.clientes: set[WebSocket] = set()
        self.historial: deque[dict] = deque(maxlen=maximo)
        self._pendientes: dict[WebSocket, list[dict]] = {}

    async def conectar(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clientes.add(websocket)
        self._pendientes[websocket] = []
        historial = list(self.historial)
        for evento in historial:
            await websocket.send_json(evento)
        while self._pendientes[websocket]:
            pendientes = self._pendientes[websocket][:]
            self._pendientes[websocket].clear()
            for evento in pendientes:
                await websocket.send_json(evento)
        self._pendientes.pop(websocket, None)

    def desconectar(self, websocket: WebSocket) -> None:
        self.clientes.discard(websocket)
        self._pendientes.pop(websocket, None)

    async def emitir(self, evento: dict) -> None:
        self.historial.append(evento)
        caidos: list[WebSocket] = []
        for websocket in tuple(self.clientes):
            if websocket in self._pendientes:
                self._pendientes[websocket].append(evento)
                continue
            try:
                await websocket.send_json(evento)
            except (WebSocketDisconnect, RuntimeError, OSError):
                caidos.append(websocket)
        for websocket in caidos:
            self.desconectar(websocket)


hub = HubEventos()


def _clave_valida(clave: Optional[str]) -> bool:
    clave_configurada = os.getenv("LUPITA_DEVICE_KEY", "")
    if not clave_configurada or not clave:
        return False
    return secrets.compare_digest(clave, clave_configurada)


@router.post("/api/eventos", status_code=201)
async def recibir_evento(
    evento: Evento,
    x_device_key: Optional[str] = Header(default=None),
) -> dict[str, bool]:
    if not _clave_valida(x_device_key):
        raise HTTPException(status_code=401, detail="Clave de dispositivo inválida.")
    await hub.emitir(evento.model_dump(mode="json"))
    return {"ok": True}


@router.get("/api/eventos")
async def listar_eventos() -> list[dict]:
    """Devuelve los eventos desde el más reciente hasta el más antiguo."""
    return list(reversed(hub.historial))


@router.websocket("/ws/eventos")
async def eventos_en_vivo(websocket: WebSocket) -> None:
    try:
        await hub.conectar(websocket)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.desconectar(websocket)


@router.get("/mensajes")
async def pantalla_mensajes(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="mensajes/index.html",
        context={},
    )


@router.get("/eventos", include_in_schema=False)
async def pagina_eventos_legacy():
    return RedirectResponse(url="/mensajes", status_code=307)
