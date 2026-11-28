from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from app import db
from app.hub import EventHub
from app.limits import FailureLockout
from app.middleware import (
    RedactSensitiveQueryParamsMiddleware,
    SessionCookieSecurityMiddleware,
)
from app.routes.api import DeviceRateLimiter, router as api_router
from app.routes.ui import router as ui_router
from app.settings import APP_DIR, Settings

logger = logging.getLogger("monitor_telefono")


async def _retention_worker(settings: Settings) -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        try:
            deleted = await asyncio.to_thread(
                db.cleanup_privacy_retention,
                settings.database_path,
                settings.retention_days,
                settings.retention_text_hours,
                settings.retention_alert_days,
            )
        except sqlite3.Error:
            logger.exception("No se pudo completar la limpieza periódica de eventos.")
        else:
            logger.info("Limpieza periódica completada; eventos eliminados: %s", deleted)


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(
            db.initialize,
            configured.database_path,
            configured.data_encryption_key,
        )
        deleted = await asyncio.to_thread(
            db.cleanup_privacy_retention,
            configured.database_path,
            configured.retention_days,
            configured.retention_text_hours,
            configured.retention_alert_days,
        )
        logger.info("Limpieza inicial completada; eventos eliminados: %s", deleted)
        retention_task = asyncio.create_task(_retention_worker(configured))
        try:
            yield
        finally:
            retention_task.cancel()
            with suppress(asyncio.CancelledError):
                await retention_task

    application = FastAPI(
        title="Monitor de teléfono",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.settings = configured
    application.state.hub = EventHub()
    application.state.rate_limiter = DeviceRateLimiter()
    application.state.login_lockout = FailureLockout()
    application.state.enrollment_lockout = FailureLockout()
    application.add_middleware(
        SessionMiddleware,
        secret_key=configured.secret_key,
        session_cookie="monitor_session",
        max_age=12 * 60 * 60,
        same_site="strict",
        https_only=False,
    )
    application.add_middleware(
        SessionCookieSecurityMiddleware,
        session_cookie="monitor_session",
        force_secure=configured.cookie_secure,
    )
    application.add_middleware(RedactSensitiveQueryParamsMiddleware)
    application.mount(
        "/static",
        StaticFiles(directory=str(APP_DIR / "static")),
        name="static",
    )
    application.include_router(api_router)
    application.include_router(ui_router)

    @application.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self' ws: wss:; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; frame-ancestors 'none'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        return response

    return application


app = create_app()
