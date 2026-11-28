from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import (
    authenticate_device,
    require_admin,
    require_api_session,
    require_reviewer_or_admin,
    session_active,
    session_role,
    verify_csrf,
    verify_websocket_origin,
)
from app.fraude.detector import evaluate_event
from app.privacy import consent_text, consent_version

router = APIRouter()
MAX_EVENT_BODY_BYTES = 64 * 1024
MAX_EVENT_TEXT = 4000
PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 100


class EventInput(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=False)

    id_evento: UUID | None = None
    tipo: Literal["notificacion", "sms", "llamada"] = "notificacion"
    app: str = Field(default="desconocida", min_length=1, max_length=128)
    remitente: str | None = Field(default=None, max_length=256)
    texto: str | None = Field(default=None, max_length=MAX_EVENT_TEXT)
    direccion: Literal["entrante", "saliente", "perdida"] | None = None
    duracion_s: int | None = Field(default=None, ge=0, le=86400)
    fecha: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("fecha")
    @classmethod
    def fecha_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def detalles_solo_en_llamadas(self) -> "EventInput":
        if self.tipo != "llamada" and (self.direccion is not None or self.duracion_s is not None):
            raise ValueError("direccion y duracion_s solo se aceptan para llamadas.")
        return self


class EventQuery(BaseModel):
    dispositivo: str | None = None
    app: str | None = Field(default=None, max_length=128)
    tipo: Literal["notificacion", "sms", "llamada"] | None = None
    texto: str | None = Field(default=None, max_length=200)
    desde: str | None = None
    hasta: str | None = None
    cursor: str | None = None
    limit: int = Field(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX)


class EnrollmentCodeInput(BaseModel):
    code: str = Field(min_length=8, max_length=8, pattern=r"^[A-HJ-NP-Z2-9]{8}$")

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: Any) -> Any:
        return value.strip().replace(" ", "").upper() if isinstance(value, str) else value


class EnrollmentInput(EnrollmentCodeInput):
    nombre: str = Field(min_length=1, max_length=80)
    apps_permitidas: list[str] = Field(default_factory=list, max_length=100)
    consentimiento: bool = False
    consentimiento_version: str = Field(default="", max_length=64)

    @field_validator("nombre")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("apps_permitidas")
    @classmethod
    def validate_apps(cls, values: list[str]) -> list[str]:
        package_pattern = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
        normalized = [value.strip() for value in values]
        if any(len(value) > 128 or not package_pattern.fullmatch(value) for value in normalized):
            raise ValueError("Cada aplicación debe ser un nombre de paquete Android válido.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("La lista de aplicaciones contiene duplicados.")
        return normalized


class ReviewInput(BaseModel):
    estado: Literal["confirmado", "falso_positivo", "necesita_contacto"]


class OwnerDeleteInput(BaseModel):
    confirmar: bool = False


class DeviceRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, device_id: str, limit: int) -> bool:
        now = time.monotonic()
        async with self._lock:
            entries = self._events[device_id]
            while entries and now - entries[0] >= 60:
                entries.popleft()
            if len(entries) >= limit:
                return False
            entries.append(now)
            return True


def _normalize_aliases(value: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(value)
    aliases = {
        "tipo": ("type",),
        "remitente": ("from", "sender", "number"),
        "texto": ("message", "body", "content"),
        "app": ("package", "app_name"),
    }
    for field, names in aliases.items():
        if field not in normalized:
            for name in names:
                if name in normalized:
                    normalized[field] = normalized[name]
                    break
    return normalized


async def _read_limited_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_EVENT_BODY_BYTES:
                raise HTTPException(status_code=413, detail="El cuerpo excede el límite permitido.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Content-Length inválido.")

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_EVENT_BODY_BYTES:
            raise HTTPException(status_code=413, detail="El cuerpo excede el límite permitido.")
    return bytes(body)


async def _parse_event(request: Request) -> EventInput:
    raw_body = await _read_limited_body(request)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    payload: Any
    if content_type == "application/json" or content_type.endswith("+json"):
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"texto": raw_body.decode("utf-8", errors="replace")[:MAX_EVENT_TEXT]}
        if not isinstance(payload, dict):
            payload = {"texto": raw_body.decode("utf-8", errors="replace")[:MAX_EVENT_TEXT]}
    elif content_type in {"application/x-www-form-urlencoded", "multipart/form-data"}:
        sent = False

        async def receive_body():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": raw_body, "more_body": False}

        form_request = Request(request.scope, receive=receive_body)
        form = await form_request.form()
        payload = {
            key: value
            for key, value in form.multi_items()
            if isinstance(value, str)
        }
    else:
        payload = {"texto": raw_body.decode("utf-8", errors="replace")[:MAX_EVENT_TEXT]}

    payload.pop("dispositivo", None)
    normalized = _normalize_aliases(payload)
    try:
        return EventInput.model_validate(normalized)
    except ValidationError as exc:
        errors = [
            {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
            for error in exc.errors(include_input=False)
        ]
        raise HTTPException(status_code=422, detail=errors) from exc


def _event_identifier(device_id: str, event: EventInput) -> str:
    if event.id_evento:
        return str(event.id_evento)
    basis = "\x1f".join(
        (device_id, event.app, event.fecha.isoformat(), event.texto or "")
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _normalize_filter_date(value: str | None, field_name: str) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} debe ser una fecha ISO válida.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


@router.get("/api/salud")
async def health() -> dict[str, str]:
    return {"estado": "ok"}


@router.get("/api/dispositivos/estado")
async def device_status(request: Request) -> dict[str, Any]:
    require_admin(request)
    devices = await run_in_threadpool(
        db.list_devices,
        request.app.state.settings.database_path,
    )
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "admin"),
        action="view_devices",
        entity_type="devices",
        entity_ids=[device["id"] for device in devices],
    )
    return {"dispositivos": devices}


@router.post("/api/eventos")
async def receive_event(request: Request) -> JSONResponse:
    device = await authenticate_device(request)
    if not await request.app.state.rate_limiter.allow(
        device["id"],
        request.app.state.settings.events_per_minute,
    ):
        raise HTTPException(status_code=429, detail="Límite de eventos por dispositivo excedido.")

    event = await _parse_event(request)
    event_data = event.model_dump(mode="json")
    event_id = _event_identifier(device["id"], event)
    settings = request.app.state.settings
    verdict = evaluate_event(
        event_data,
        rules_path=settings.fraud_rules_path,
        medium_threshold=settings.risk_medium_threshold,
        high_threshold=settings.risk_high_threshold,
    )
    inserted, stored = await run_in_threadpool(
        db.insert_event,
        request.app.state.settings.database_path,
        device["id"],
        event_data,
        event_id,
        verdict,
        settings.data_encryption_key,
    )
    if inserted and stored:
        await request.app.state.hub.publish(stored)
    return JSONResponse(
        status_code=201 if inserted else 200,
        content={
            "ok": True,
            "duplicado": not inserted,
            "veredicto": {
                "riesgo": verdict["riesgo"] if inserted else (stored or {}).get("riesgo", 0),
                "nivel": verdict["nivel"] if inserted else (stored or {}).get("nivel_riesgo", "bajo"),
                "razones": verdict["razones"] if inserted else (stored or {}).get("razones_riesgo", []),
            },
        },
    )


def _client_attempt_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_enrollment_lockout(request: Request) -> None:
    retry_after = request.app.state.enrollment_lockout.retry_after(
        _client_attempt_key(request)
    )
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos de enrolamiento. Intenta de nuevo más tarde.",
            headers={"Retry-After": str(retry_after)},
        )


def _record_enrollment_failure(request: Request) -> None:
    request.app.state.enrollment_lockout.record_failure(_client_attempt_key(request))


@router.post("/api/enrolar/preview")
async def preview_enrollment(
    payload: EnrollmentCodeInput,
    request: Request,
) -> dict[str, Any]:
    _check_enrollment_lockout(request)
    enrollment = await run_in_threadpool(
        db.get_enrollment,
        request.app.state.settings.database_path,
        payload.code,
    )
    if not enrollment:
        _record_enrollment_failure(request)
        raise HTTPException(status_code=404, detail="El código de enrolamiento no es válido.")
    if enrollment["estado"] == "caducado":
        _record_enrollment_failure(request)
        raise HTTPException(status_code=410, detail="El código de enrolamiento caducó.")
    if enrollment["estado"] != "pendiente":
        _record_enrollment_failure(request)
        raise HTTPException(status_code=409, detail="El código de enrolamiento ya fue utilizado.")
    return {
        "nombre_sugerido": enrollment["nombre_sugerido"],
        "apps_sugeridas": enrollment["apps_sugeridas"],
        "expira_en": enrollment["expira_en"],
        "consentimiento_texto": consent_text(request.app.state.settings),
        "consentimiento_version": consent_version(request.app.state.settings),
    }


@router.post("/api/enrolar")
async def redeem_enrollment(
    payload: EnrollmentInput,
    request: Request,
) -> dict[str, Any]:
    _check_enrollment_lockout(request)
    if not payload.consentimiento:
        raise HTTPException(
            status_code=400,
            detail="Debes aceptar el consentimiento explícito antes de vincular el teléfono.",
        )
    expected_consent_version = consent_version(request.app.state.settings)
    if payload.consentimiento_version != expected_consent_version:
        raise HTTPException(
            status_code=409,
            detail="El consentimiento cambió; vuelve a revisar y aceptar el texto actualizado.",
        )
    if not payload.nombre:
        raise HTTPException(status_code=422, detail="El nombre del teléfono no puede estar vacío.")

    status, device, token = await run_in_threadpool(
        db.redeem_enrollment,
        request.app.state.settings.database_path,
        payload.code,
        payload.nombre,
        payload.apps_permitidas,
        expected_consent_version,
    )
    if status != "ok":
        _record_enrollment_failure(request)
        messages = {
            "invalido": (404, "El código de enrolamiento no es válido."),
            "caducado": (410, "El código de enrolamiento caducó."),
            "usado": (409, "El código de enrolamiento ya fue utilizado."),
        }
        code, message = messages[status]
        raise HTTPException(status_code=code, detail=message)
    request.app.state.enrollment_lockout.reset(_client_attempt_key(request))
    return {
        "dispositivo": device,
        "token": token,
        "mensaje": "Teléfono vinculado. El token se entrega una sola vez.",
    }


@router.post("/api/latido")
async def device_heartbeat(request: Request) -> dict[str, Any]:
    device = await authenticate_device(request)
    last_contact = await run_in_threadpool(
        db.touch_device,
        request.app.state.settings.database_path,
        device["id"],
    )
    updates = await run_in_threadpool(
        db.review_updates_for_device,
        request.app.state.settings.database_path,
        device["id"],
    )
    return {
        "ok": True,
        "ultimo_contacto": last_contact,
        "actualizaciones_revision": updates,
    }


@router.post("/api/desvincular")
async def unlink_device(request: Request) -> dict[str, bool]:
    device = await authenticate_device(request, allow_revoked=True)
    revoked = await run_in_threadpool(
        db.revoke_device,
        request.app.state.settings.database_path,
        device["id"],
    )
    if not revoked:
        raise HTTPException(status_code=401, detail="El dispositivo ya no está vinculado.")
    return {"ok": True}


@router.get("/api/eventos")
async def get_events(
    request: Request,
    dispositivo: str | None = None,
    app: str | None = Query(default=None, max_length=128),
    tipo: Literal["notificacion", "sms", "llamada"] | None = None,
    texto: str | None = Query(default=None, max_length=200),
    desde: str | None = None,
    hasta: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
) -> dict[str, Any]:
    require_admin(request)
    text_filter = getattr(request.state, "query_text_filter", texto)
    if text_filter is not None and len(text_filter) > 200:
        raise HTTPException(status_code=422, detail="texto no puede exceder 200 caracteres.")
    filters = EventQuery(
        dispositivo=dispositivo,
        app=app,
        tipo=tipo,
        texto=text_filter,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limit=limit,
    )
    return await _query_events(request, filters)


@router.post("/api/eventos/buscar")
async def search_events(request: Request, filters: EventQuery) -> dict[str, Any]:
    require_admin(request)
    verify_csrf(request, request.headers.get("x-csrf-token"))
    return await _query_events(request, filters)


async def _query_events(request: Request, filters: EventQuery) -> dict[str, Any]:
    cursor_id = None
    if filters.cursor:
        try:
            cursor_id = int(filters.cursor)
            if cursor_id < 1:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="cursor inválido.") from exc
    result = await run_in_threadpool(
        db.query_events,
        request.app.state.settings.database_path,
        request.app.state.settings.data_encryption_key,
        device_id=filters.dispositivo,
        app=filters.app,
        event_type=filters.tipo,
        text=filters.texto,
        since=_normalize_filter_date(filters.desde, "desde"),
        until=_normalize_filter_date(filters.hasta, "hasta"),
        cursor_id=cursor_id,
        limit=filters.limit,
    )
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "admin"),
        action="view_events",
        entity_type="events",
        entity_ids=[item["id_evento"] for item in result["items"]],
    )
    return result


@router.get("/api/revisiones")
async def review_alerts(request: Request) -> dict[str, Any]:
    require_reviewer_or_admin(request)
    entries = await run_in_threadpool(
        db.query_review_queue,
        request.app.state.settings.database_path,
        request.app.state.settings.data_encryption_key,
        reviewers_see_all=request.app.state.settings.reviewers_see_all,
        full_access_consent_version=(
            consent_version(request.app.state.settings)
            if request.app.state.settings.reviewers_see_all
            else None
        ),
    )
    audit_ids: list[str] = []
    for item in entries:
        audit_ids.append(item["id_evento"])
        audit_ids.extend(previous["id_evento"] for previous in item["contexto"])
        item.pop("dispositivo_id", None)
        item.pop("id", None)
        for previous in item["contexto"]:
            previous.pop("id_evento", None)
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "revisor"),
        action="view_review_queue",
        entity_type="events",
        entity_ids=audit_ids,
    )
    return {"items": entries}


@router.post("/api/revisiones/{event_id}/marcar")
async def mark_review(
    event_id: str,
    payload: ReviewInput,
    request: Request,
) -> dict[str, Any]:
    require_reviewer_or_admin(request)
    verify_csrf(request, request.headers.get("x-csrf-token"))
    metadata = await run_in_threadpool(
        db.event_review_metadata,
        request.app.state.settings.database_path,
        event_id,
    )
    if not metadata:
        raise HTTPException(status_code=404, detail="Evento no encontrado.")
    if (
        session_role(request) == "revisor"
        and metadata["nivel_riesgo"] == "bajo"
        and (
            not request.app.state.settings.reviewers_see_all
            or metadata["consentimiento_version"]
            != consent_version(request.app.state.settings)
        )
    ):
        raise HTTPException(status_code=403, detail="Este evento no está disponible para revisión.")
    changed, rule_ids = await run_in_threadpool(
        db.mark_event_review,
        request.app.state.settings.database_path,
        event_id,
        int(request.session["user_id"]),
        payload.estado,
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Evento no encontrado.")
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "revisor"),
        action="mark_event",
        entity_type="event",
        entity_ids={"id_evento": event_id, "estado": payload.estado, "reglas": rule_ids},
    )
    return {"ok": True, "id_evento": event_id, "revision_estado": payload.estado}


@router.get("/api/mis-eventos")
async def owner_events(request: Request) -> dict[str, Any]:
    device = await authenticate_device(request)
    items = await run_in_threadpool(
        db.owner_event_updates,
        request.app.state.settings.database_path,
        device["id"],
        request.app.state.settings.data_encryption_key,
        100,
    )
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=None,
        actor=f"device:{device['id']}",
        action="owner_view_events",
        entity_type="events",
        entity_ids=[item["id_evento"] for item in items],
    )
    return {"items": items}


@router.get("/api/mis-eventos/exportar")
async def owner_export(request: Request) -> JSONResponse:
    device = await authenticate_device(request)
    events = await run_in_threadpool(
        db.export_device_events,
        request.app.state.settings.database_path,
        device["id"],
        request.app.state.settings.data_encryption_key,
    )
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=None,
        actor=f"device:{device['id']}",
        action="owner_export_events",
        entity_type="events",
        entity_ids=[item["id_evento"] for item in events],
    )
    return JSONResponse(
        content={"eventos": events},
        headers={"Content-Disposition": 'attachment; filename="mis-eventos.json"'},
    )


@router.post("/api/mis-datos/borrar")
async def owner_delete_data(payload: OwnerDeleteInput, request: Request) -> dict[str, Any]:
    device = await authenticate_device(request)
    if not payload.confirmar:
        raise HTTPException(status_code=400, detail="Confirma explícitamente el borrado definitivo.")
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=None,
        actor=f"device:{device['id']}",
        action="owner_delete_data",
        entity_type="device_events",
        entity_ids=[device["id"]],
    )
    deleted = await run_in_threadpool(
        db.delete_device_data,
        request.app.state.settings.database_path,
        device["id"],
    )
    return {"ok": True, "eventos_borrados": deleted, "dispositivo_desvinculado": True}


@router.get("/api/admin/reglas/estadisticas")
async def fraud_rule_statistics(request: Request) -> dict[str, Any]:
    require_admin(request)
    return {
        "reglas": await run_in_threadpool(
            db.review_rule_statistics,
            request.app.state.settings.database_path,
        )
    }


@router.websocket("/ws/eventos")
async def event_stream(websocket: WebSocket) -> None:
    if not session_active(websocket):
        await websocket.close(code=4401, reason="Sesión requerida.")
        return
    if session_role(websocket) != "admin":
        await websocket.close(code=4403, reason="Se requiere una cuenta administradora.")
        return
    if not verify_websocket_origin(
        websocket,
        websocket.app.state.settings.base_url_publica,
    ):
        await websocket.close(code=4403, reason="Origin inválido.")
        return

    queue = websocket.app.state.hub.subscribe()
    await websocket.accept()
    try:
        while True:
            event = await queue.get()
            if event is None:
                await websocket.close(code=1013, reason="Conexión lenta; vuelve a cargar el feed.")
                break
            await websocket.send_json(event)
            await run_in_threadpool(
                db.append_audit,
                websocket.app.state.settings.database_path,
                actor_id=websocket.session.get("user_id"),
                actor=websocket.session.get("username", "admin"),
                action="view_event_live",
                entity_type="event",
                entity_ids=[event.get("id_evento", "")],
            )
    except WebSocketDisconnect:
        pass
    finally:
        websocket.app.state.hub.unsubscribe(queue)
