from __future__ import annotations

import base64
import io
import re
import sqlite3
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool

import segno
from app import db
from app.auth import (
    account_totp_secret,
    ensure_csrf_token,
    hash_password,
    require_admin,
    require_reviewer_or_admin,
    session_active,
    session_role,
    verify_csrf,
    verify_password,
    verify_totp,
)
from app.crypto import encrypt_text
from app.fraude.csv_source import load_rules_csv, parse_rules_csv
from app.privacy import consent_text, consent_version
from app.settings import APP_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
_PHONE_DIGITS = re.compile(r"\D")
_PHONE_FORMAT = re.compile(r"\+?[0-9][0-9\s().-]{5,32}")
_ENROLLMENT_CODE = re.compile(r"^[A-HJ-NP-Z2-9]{8}$")
_APP_PACKAGE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_SUGGESTED_APPS = (
    ("com.whatsapp", "WhatsApp"),
    ("org.telegram.messenger", "Telegram"),
    ("com.google.android.apps.messaging", "Mensajes de Google"),
    ("com.android.messaging", "Mensajes"),
    ("com.facebook.orca", "Messenger"),
    ("com.instagram.android", "Instagram"),
    ("com.google.android.gm", "Gmail"),
)
_DUMMY_PASSWORD_HASH = hash_password("Password-ficticia-no-usar-123!")


def _render(
    request: Request,
    name: str,
    *,
    status_code: int = 200,
    **context: Any,
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name=name,
        status_code=status_code,
        context={
            "authenticated": session_active(request),
            "role": session_role(request),
            "csrf_token": ensure_csrf_token(request),
            **context,
        },
    )


def _unauthenticated_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


def _require_admin_page(request: Request) -> None:
    if not session_active(request):
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    require_admin(request)


def _form_text(form: Any, key: str) -> str | None:
    value = form.get(key)
    return value if isinstance(value, str) else None


@router.get("/login", name="login")
async def login_page(request: Request) -> Response:
    if session_active(request):
        destination = "/revisiones" if session_role(request) == "revisor" else "/"
        return RedirectResponse(url=destination, status_code=303)
    has_admin = await run_in_threadpool(
        db.has_admin,
        request.app.state.settings.database_path,
    )
    return _render(request, "login.html", error=None, needs_admin=not has_admin)


@router.post("/login")
async def login(request: Request) -> Response:
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    key = request.client.host if request.client else "unknown"
    retry_after = request.app.state.login_lockout.retry_after(key)
    if retry_after:
        response = _render(
            request,
            "login.html",
            error="Demasiados intentos. Espera 15 minutos antes de volver a intentarlo.",
            status_code=429,
        )
        response.headers["Retry-After"] = str(retry_after)
        return response
    username = (_form_text(form, "username") or "").strip()
    password = _form_text(form, "password") or ""
    account = await run_in_threadpool(
        db.get_account_by_username,
        request.app.state.settings.database_path,
        username,
    )
    password_ok = verify_password(
        password[:1024],
        account["password_hash"] if account else _DUMMY_PASSWORD_HASH,
    )
    totp_secret = (
        account_totp_secret(account, request.app.state.settings.data_encryption_key)
        if account
        else None
    )
    totp_ok = (
        verify_totp(totp_secret, _form_text(form, "totp_code") or "")
        if totp_secret
        else True
    )
    if not account or not account["activa"] or not password_ok or not totp_ok:
        response = _render(
            request,
            "login.html",
            error="La contraseña no es correcta.",
            status_code=401,
            needs_admin=False,
        )
        retry_after = request.app.state.login_lockout.record_failure(key)
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    request.app.state.login_lockout.reset(key)
    request.session.clear()
    request.session["user_id"] = account["id"]
    request.session["username"] = account["usuario"]
    request.session["role"] = account["rol"]
    await run_in_threadpool(
        db.record_account_login,
        request.app.state.settings.database_path,
        account["id"],
    )
    ensure_csrf_token(request)
    destination = "/revisiones" if account["rol"] == "revisor" else "/"
    return RedirectResponse(url=destination, status_code=303)


@router.post("/logout")
async def logout(request: Request) -> Response:
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/", name="home")
async def home(request: Request) -> Response:
    if not session_active(request):
        return _unauthenticated_redirect()
    if session_role(request) == "revisor":
        return RedirectResponse(url="/revisiones", status_code=303)
    require_admin(request)
    devices, apps = await run_in_threadpool(
        lambda: (
            db.list_devices(request.app.state.settings.database_path),
            db.list_apps(request.app.state.settings.database_path),
        )
    )
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "admin"),
        action="view_dashboard",
        entity_type="devices",
        entity_ids=[device["id"] for device in devices],
    )
    return _render(request, "index.html", devices=devices, apps=apps)


@router.get("/revisiones", name="review_queue")
async def review_queue(request: Request) -> Response:
    if not session_active(request):
        return _unauthenticated_redirect()
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
    actor_id = request.session.get("user_id")
    actor = request.session.get("username", "cuenta")
    visible_ids = [
        event_id
        for item in entries
        for event_id in [item["id_evento"]]
    ]
    visible_ids.extend(
        previous["id_evento"]
        for item in entries
        for previous in item["contexto"]
    )
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=actor_id,
        actor=actor,
        action="view_review_queue",
        entity_type="events",
        entity_ids=visible_ids,
    )
    return _render(
        request,
        "review.html",
        entries=entries,
        reviewers_see_all=request.app.state.settings.reviewers_see_all,
    )


@router.post("/revisiones/{event_id}/marcar")
async def mark_review_from_form(request: Request, event_id: str) -> Response:
    if not session_active(request):
        return _unauthenticated_redirect()
    require_reviewer_or_admin(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    status = _form_text(form, "estado") or ""
    if status not in {"confirmado", "falso_positivo", "necesita_contacto"}:
        raise HTTPException(status_code=422, detail="Estado de revisión inválido.")
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
    changed, rules = await run_in_threadpool(
        db.mark_event_review,
        request.app.state.settings.database_path,
        event_id,
        int(request.session["user_id"]),
        status,
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
        entity_ids={"id_evento": event_id, "estado": status, "reglas": rules},
    )
    return RedirectResponse(url="/revisiones", status_code=303)


@router.get("/cuentas", name="accounts")
async def accounts_page(request: Request) -> Response:
    _require_admin_page(request)
    users = await run_in_threadpool(
        db.list_accounts,
        request.app.state.settings.database_path,
    )
    return _render(request, "accounts.html", users=users, error=None)


@router.post("/cuentas/revisores", name="create_reviewer")
async def create_reviewer(request: Request) -> Response:
    _require_admin_page(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    username = (_form_text(form, "username") or "").strip()
    password = _form_text(form, "password") or ""
    totp_secret = (_form_text(form, "totp_secret") or "").strip().replace(" ", "").upper()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", username):
        raise HTTPException(status_code=422, detail="El usuario debe tener de 3 a 64 caracteres válidos.")
    if len(password) < 12 or len(password) > 1024:
        raise HTTPException(status_code=422, detail="La contraseña debe tener entre 12 y 1024 caracteres.")
    encrypted_totp = None
    if totp_secret:
        try:
            base64.b32decode(
                totp_secret + "=" * ((8 - len(totp_secret) % 8) % 8),
                casefold=True,
            )
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(status_code=422, detail="El secreto TOTP debe ser Base32 válido.") from exc
        encrypted_totp = encrypt_text(
            totp_secret,
            request.app.state.settings.data_encryption_key,
        )
    try:
        account_id = await run_in_threadpool(
            db.create_account,
            request.app.state.settings.database_path,
            username,
            hash_password(password),
            "revisor",
            encrypted_totp,
        )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="Ese nombre de usuario ya existe.") from exc
        raise
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "admin"),
        action="create_reviewer",
        entity_type="account",
        entity_ids=[str(account_id)],
    )
    return RedirectResponse(url="/cuentas", status_code=303)


@router.post("/cuentas/revisores/{account_id}/estado")
async def set_reviewer_status(request: Request, account_id: int) -> Response:
    _require_admin_page(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    account = await run_in_threadpool(
        db.get_account,
        request.app.state.settings.database_path,
        account_id,
    )
    if not account or account["rol"] != "revisor":
        raise HTTPException(status_code=404, detail="Cuenta revisora no encontrada.")
    active = _form_text(form, "active") == "true"
    await run_in_threadpool(
        db.set_account_active,
        request.app.state.settings.database_path,
        account_id,
        active,
    )
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "admin"),
        action="enable_reviewer" if active else "disable_reviewer",
        entity_type="account",
        entity_ids=[str(account_id)],
    )
    return RedirectResponse(url="/cuentas", status_code=303)


@router.get("/auditoria", name="audit_log")
async def audit_log_page(request: Request) -> Response:
    _require_admin_page(request)
    entries = await run_in_threadpool(
        db.list_audit,
        request.app.state.settings.database_path,
        500,
    )
    return _render(request, "audit.html", entries=entries)


@router.get("/reglas", name="fraud_rules")
async def fraud_rules_page(request: Request) -> Response:
    _require_admin_page(request)
    settings = request.app.state.settings
    rules = await run_in_threadpool(load_rules_csv, settings.fraud_rules_path)
    stats = await run_in_threadpool(
        db.review_rule_statistics,
        settings.database_path,
    )
    return _render(
        request,
        "rules.html",
        rules=rules,
        stats=stats,
        rules_path=str(settings.fraud_rules_path),
        error=None,
    )


@router.post("/reglas", name="replace_fraud_rules")
async def replace_fraud_rules(request: Request) -> Response:
    _require_admin_page(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    upload = form.get("rules_csv")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=422, detail="Selecciona un archivo CSV.")
    content = await upload.read(1_000_001)
    if len(content) > 1_000_000:
        raise HTTPException(status_code=413, detail="El CSV supera el tamaño máximo de 1 MB.")
    try:
        decoded = content.decode("utf-8-sig")
        rules = parse_rules_csv(decoded)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    destination = request.app.state.settings.fraud_rules_path
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(decoded, encoding="utf-8", newline="")
    temporary.replace(destination)
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "admin"),
        action="replace_fraud_rules",
        entity_type="fraud_rules",
        entity_ids=[rule.rule_id for rule in rules],
    )
    return RedirectResponse(url="/reglas", status_code=303)


@router.get("/datos/exportar/{device_id}", name="export_person_data")
async def export_person_data(request: Request, device_id: str) -> Response:
    _require_admin_page(request)
    events = await run_in_threadpool(
        db.export_device_events,
        request.app.state.settings.database_path,
        device_id,
        request.app.state.settings.data_encryption_key,
    )
    if not events and not await run_in_threadpool(
        db.get_device,
        request.app.state.settings.database_path,
        device_id,
    ):
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "admin"),
        action="export_person_data",
        entity_type="device_events",
        entity_ids=[{"device_id": device_id, "event_count": len(events)}],
    )
    return JSONResponse(
        content={"dispositivo_id": device_id, "eventos": events},
        headers={"Content-Disposition": f'attachment; filename="eventos-{device_id}.json"'},
    )


@router.post("/datos/borrar/{device_id}", name="delete_person_data")
async def delete_person_data(request: Request, device_id: str) -> Response:
    _require_admin_page(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    device = await run_in_threadpool(
        db.get_device,
        request.app.state.settings.database_path,
        device_id,
    )
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    count = await run_in_threadpool(
        db.delete_device_data,
        request.app.state.settings.database_path,
        device_id,
    )
    await run_in_threadpool(
        db.append_audit,
        request.app.state.settings.database_path,
        actor_id=request.session.get("user_id"),
        actor=request.session.get("username", "admin"),
        action="delete_person_data",
        entity_type="device_events",
        entity_ids=[{"device_id": device_id, "event_count": count}],
    )
    return RedirectResponse(url="/dispositivos", status_code=303)


@router.get("/eventos", name="events_page")
async def events_page(request: Request) -> Response:
    if not session_active(request):
        return _unauthenticated_redirect()
    require_admin(request)
    return await home(request)


@router.get("/dispositivos", name="devices")
async def devices_page(request: Request) -> Response:
    _require_admin_page(request)
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
    return _render(
        request,
        "devices.html",
        devices=devices,
        error=None,
        created_device=None,
        new_token=None,
        ingest_url=None,
        pending_enrollment=None,
        enrollment_error=None,
    )


@router.post("/enrolamientos")
async def create_enrollment(request: Request) -> Response:
    _require_admin_page(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    name = (_form_text(form, "nombre_sugerido") or "Teléfono nuevo").strip()
    apps = list(dict.fromkeys(form.getlist("apps_sugeridas")))
    if not name or len(name) > 80:
        raise HTTPException(status_code=422, detail="El nombre sugerido debe tener entre 1 y 80 caracteres.")
    if len(apps) > 20 or any(not _APP_PACKAGE.fullmatch(app) or len(app) > 128 for app in apps):
        raise HTTPException(status_code=422, detail="La lista de aplicaciones sugeridas no es válida.")

    enrollment, code = await run_in_threadpool(
        db.create_enrollment,
        request.app.state.settings.database_path,
        name,
        apps,
    )
    public_base = (
        request.app.state.settings.base_url_publica
        or str(request.base_url).rstrip("/")
    )
    enroll_url = f"{public_base}/enroll?code={quote(code)}"
    qr = segno.make(enroll_url, error="m")
    svg = io.BytesIO()
    qr.save(svg, kind="svg", scale=5, border=2, xmldecl=False)
    qr_data = base64.b64encode(svg.getvalue()).decode("ascii")
    app_link = (
        "monitortelefono://enroll?server="
        f"{quote(public_base, safe='')}&code={quote(code)}"
    )
    devices = await run_in_threadpool(
        db.list_devices,
        request.app.state.settings.database_path,
    )
    return _render(
        request,
        "devices.html",
        devices=devices,
        error=None,
        created_device=None,
        new_token=None,
        ingest_url=None,
        pending_enrollment={
            **enrollment,
            "code": code,
            "url": enroll_url,
            "qr_data": qr_data,
            "app_link": app_link,
        },
        enrollment_error=None,
    )


@router.get("/enroll", name="public_enrollment")
async def public_enrollment_page(request: Request) -> Response:
    code = getattr(request.state, "enrollment_code", "")
    code = code.strip().replace(" ", "").upper() if isinstance(code, str) else ""
    enrollment = None
    error = None
    if not _ENROLLMENT_CODE.fullmatch(code):
        error = "El enlace de enrolamiento no es válido o está incompleto."
    else:
        key = request.client.host if request.client else "unknown"
        retry_after = request.app.state.enrollment_lockout.retry_after(key)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos. Intenta de nuevo más tarde.",
                headers={"Retry-After": str(retry_after)},
            )
        enrollment = await run_in_threadpool(
            db.get_enrollment,
            request.app.state.settings.database_path,
            code,
        )
        if not enrollment:
            request.app.state.enrollment_lockout.record_failure(key)
            error = "El código de enrolamiento no es válido."
        elif enrollment["estado"] == "caducado":
            request.app.state.enrollment_lockout.record_failure(key)
            error = "El código de enrolamiento caducó. Pide uno nuevo al administrador."
        elif enrollment["estado"] != "pendiente":
            request.app.state.enrollment_lockout.record_failure(key)
            error = "El código de enrolamiento ya fue utilizado."

    base_url = (
        request.app.state.settings.base_url_publica
        or str(request.base_url).rstrip("/")
    )
    app_link = (
        f"monitortelefono://enroll?server={quote(base_url, safe='')}"
        f"&code={quote(code)}"
    ) if enrollment else None
    return _render(
        request,
        "enroll.html",
        error=error,
        enrollment=enrollment if enrollment and enrollment["estado"] == "pendiente" else None,
        app_link=app_link,
        download_url=request.app.state.settings.android_download_url,
        consent_text=consent_text(request.app.state.settings),
    )


@router.post("/dispositivos")
async def register_device(request: Request) -> Response:
    _require_admin_page(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    name = (_form_text(form, "nombre") or "").strip()
    digits = _PHONE_DIGITS.sub("", name)
    if (
        len(name) > 80
        or not _PHONE_FORMAT.fullmatch(name)
        or not 7 <= len(digits) <= 15
    ):
        devices = await run_in_threadpool(
            db.list_devices,
            request.app.state.settings.database_path,
        )
        return _render(
            request,
            "devices.html",
            devices=devices,
            error="Ingresa un número de teléfono válido de 7 a 15 dígitos.",
            created_device=None,
            new_token=None,
            ingest_url=None,
            status_code=422,
        )

    device, token = await run_in_threadpool(
        db.create_device,
        request.app.state.settings.database_path,
        name,
    )
    return _render(
        request,
        "devices.html",
        devices=await run_in_threadpool(db.list_devices, request.app.state.settings.database_path),
        error=None,
        created_device=device,
        new_token=token,
        ingest_url=str(request.url_for("receive_event")),
    )


@router.post("/dispositivos/{device_id}/revocar")
async def revoke_device(request: Request, device_id: str) -> Response:
    _require_admin_page(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    changed = await run_in_threadpool(
        db.revoke_device,
        request.app.state.settings.database_path,
        device_id,
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    return RedirectResponse(url="/dispositivos", status_code=303)


@router.post("/dispositivos/{device_id}/eliminar")
async def delete_device(request: Request, device_id: str) -> Response:
    _require_admin_page(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    deleted = await run_in_threadpool(
        db.delete_device,
        request.app.state.settings.database_path,
        device_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    return RedirectResponse(url="/dispositivos", status_code=303)


@router.post("/datos/borrar")
async def delete_all_data(request: Request) -> Response:
    _require_admin_page(request)
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    await run_in_threadpool(
        db.delete_all_events,
        request.app.state.settings.database_path,
    )
    return RedirectResponse(url="/dispositivos", status_code=303)
