from __future__ import annotations

import base64
import hmac
import io
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

import segno
from app import db
from app.auth import ensure_csrf_token, session_active, verify_csrf
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
            "csrf_token": ensure_csrf_token(request),
            **context,
        },
    )


def _unauthenticated_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


def _form_text(form: Any, key: str) -> str | None:
    value = form.get(key)
    return value if isinstance(value, str) else None


@router.get("/login", name="login")
async def login_page(request: Request) -> Response:
    if session_active(request):
        return RedirectResponse(url="/", status_code=303)
    return _render(request, "login.html", error=None)


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
    password = _form_text(form, "password") or ""
    expected = request.app.state.settings.monitor_password
    if not hmac.compare_digest(password.encode("utf-8"), expected.encode("utf-8")):
        response = _render(
            request,
            "login.html",
            error="La contraseña no es correcta.",
            status_code=401,
        )
        retry_after = request.app.state.login_lockout.record_failure(key)
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    request.app.state.login_lockout.reset(key)
    request.session.clear()
    request.session["authenticated"] = True
    ensure_csrf_token(request)
    return RedirectResponse(url="/", status_code=303)


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
    devices, apps = await run_in_threadpool(
        lambda: (
            db.list_devices(request.app.state.settings.database_path),
            db.list_apps(request.app.state.settings.database_path),
        )
    )
    return _render(request, "index.html", devices=devices, apps=apps)


@router.get("/eventos", name="events_page")
async def events_page(request: Request) -> Response:
    return await home(request)


@router.get("/dispositivos", name="devices")
async def devices_page(request: Request) -> Response:
    if not session_active(request):
        return _unauthenticated_redirect()
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
        pending_enrollment=None,
        enrollment_error=None,
    )


@router.post("/enrolamientos")
async def create_enrollment(request: Request) -> Response:
    if not session_active(request):
        return _unauthenticated_redirect()
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
    )


@router.post("/dispositivos")
async def register_device(request: Request) -> Response:
    if not session_active(request):
        return _unauthenticated_redirect()
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
    if not session_active(request):
        return _unauthenticated_redirect()
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
    if not session_active(request):
        return _unauthenticated_redirect()
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
    if not session_active(request):
        return _unauthenticated_redirect()
    form = await request.form()
    verify_csrf(request, _form_text(form, "csrf_token"))
    await run_in_threadpool(
        db.delete_all_events,
        request.app.state.settings.database_path,
    )
    return RedirectResponse(url="/dispositivos", status_code=303)
