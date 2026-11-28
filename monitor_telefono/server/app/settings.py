from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

APP_DIR = Path(__file__).resolve().parent
SERVER_DIR = APP_DIR.parent


@dataclass(frozen=True)
class Settings:
    monitor_password: str
    secret_key: str
    database_path: Path
    retention_days: int
    port: int
    cookie_secure: bool
    events_per_minute: int = 120
    base_url_publica: str | None = None
    android_download_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        password = os.getenv("MONITOR_PASSWORD", "")
        secret_key = os.getenv("SECRET_KEY", "")
        if not password:
            raise RuntimeError(
                "Falta MONITOR_PASSWORD. Configúrala en el entorno antes de arrancar."
            )
        if len(secret_key) < 32:
            raise RuntimeError(
                "Falta SECRET_KEY o es demasiado corta; usa al menos 32 caracteres aleatorios."
            )

        try:
            retention_days = int(os.getenv("RETENCION_DIAS", "30"))
            port = int(os.getenv("PUERTO", "8100"))
            events_per_minute = int(os.getenv("EVENTOS_POR_MINUTO", "120"))
        except ValueError as exc:
            raise RuntimeError(
                "RETENCION_DIAS, PUERTO y EVENTOS_POR_MINUTO deben ser enteros."
            ) from exc
        if retention_days < 1:
            raise RuntimeError("RETENCION_DIAS debe ser al menos 1.")
        if not 1 <= port <= 65535:
            raise RuntimeError("PUERTO debe estar entre 1 y 65535.")
        if events_per_minute < 1:
            raise RuntimeError("EVENTOS_POR_MINUTO debe ser al menos 1.")

        database_path = Path(
            os.getenv("DATABASE_PATH", str(SERVER_DIR / "data" / "monitor.sqlite3"))
        ).expanduser()
        public_base_url = os.getenv("BASE_URL_PUBLICA", "").strip()
        android_download_url = os.getenv("ANDROID_DOWNLOAD_URL", "").strip()
        if public_base_url:
            try:
                parsed_public_url = urlsplit(public_base_url)
                parsed_public_url.port
            except ValueError as exc:
                raise RuntimeError("BASE_URL_PUBLICA debe ser una URL pública válida.") from exc
            if (
                parsed_public_url.scheme not in {"http", "https"}
                or not parsed_public_url.netloc
                or not parsed_public_url.hostname
                or parsed_public_url.username
                or parsed_public_url.password
                or parsed_public_url.path not in {"", "/"}
                or parsed_public_url.query
                or parsed_public_url.fragment
            ):
                raise RuntimeError(
                    "BASE_URL_PUBLICA debe ser el origen público, sin ruta, credenciales ni parámetros."
                )
        if android_download_url:
            try:
                parsed_download_url = urlsplit(android_download_url)
                parsed_download_url.port
            except ValueError as exc:
                raise RuntimeError("ANDROID_DOWNLOAD_URL debe ser una URL HTTPS válida.") from exc
            if (
                parsed_download_url.scheme != "https"
                or not parsed_download_url.netloc
                or not parsed_download_url.hostname
                or parsed_download_url.username
                or parsed_download_url.password
                or parsed_download_url.fragment
            ):
                raise RuntimeError(
                    "ANDROID_DOWNLOAD_URL debe ser HTTPS y no incluir credenciales ni fragmentos."
                )
        return cls(
            monitor_password=password,
            secret_key=secret_key,
            database_path=database_path,
            retention_days=retention_days,
            port=port,
            cookie_secure=os.getenv("COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
            events_per_minute=events_per_minute,
            base_url_publica=public_base_url or None,
            android_download_url=android_download_url or None,
        )
