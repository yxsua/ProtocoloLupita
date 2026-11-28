from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

APP_DIR = Path(__file__).resolve().parent
SERVER_DIR = APP_DIR.parent


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_path: Path
    retention_days: int
    port: int
    cookie_secure: bool
    events_per_minute: int = 120
    base_url_publica: str | None = None
    android_download_url: str | None = None
    data_encryption_key: str = ""
    retention_text_hours: int = 24
    retention_alert_days: int = 90
    reviewers_see_all: bool = False
    risk_medium_threshold: int = 40
    risk_high_threshold: int = 70
    fraud_rules_path: Path = SERVER_DIR / "data" / "reglas_fraude.csv"
    lupita_events_url: str | None = None
    lupita_events_key: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        secret_key = os.getenv("SECRET_KEY", "")
        if len(secret_key) < 32:
            raise RuntimeError(
                "Falta SECRET_KEY o es demasiado corta; usa al menos 32 caracteres aleatorios."
            )
        encryption_key = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
        if not encryption_key:
            raise RuntimeError(
                "Falta DATA_ENCRYPTION_KEY. Genera una clave Fernet y configúrala en el entorno."
            )
        from app.crypto import _cipher

        _cipher(encryption_key)

        try:
            retention_days = int(os.getenv("RETENCION_DIAS", "30"))
            port = int(os.getenv("PUERTO", "8100"))
            events_per_minute = int(os.getenv("EVENTOS_POR_MINUTO", "120"))
            retention_text_hours = int(os.getenv("RETENCION_TEXTO_NORMAL_HORAS", "24"))
            retention_alert_days = int(os.getenv("RETENCION_ALERTAS_DIAS", "90"))
            risk_medium_threshold = int(os.getenv("RIESGO_UMBRAL_MEDIO", "40"))
            risk_high_threshold = int(os.getenv("RIESGO_UMBRAL_ALTO", "70"))
        except ValueError as exc:
            raise RuntimeError(
                "Los límites de retención, puerto y riesgo deben ser enteros."
            ) from exc
        if retention_days < 1:
            raise RuntimeError("RETENCION_DIAS debe ser al menos 1.")
        if retention_text_hours < 1 or retention_alert_days < 1:
            raise RuntimeError("Las retenciones de texto y alertas deben ser positivas.")
        if not 1 <= risk_medium_threshold < risk_high_threshold <= 100:
            raise RuntimeError(
                "RIESGO_UMBRAL_MEDIO y RIESGO_UMBRAL_ALTO deben estar ordenados entre 1 y 100."
            )
        if not 1 <= port <= 65535:
            raise RuntimeError("PUERTO debe estar entre 1 y 65535.")
        if events_per_minute < 1:
            raise RuntimeError("EVENTOS_POR_MINUTO debe ser al menos 1.")

        database_path = Path(
            os.getenv("DATABASE_PATH", str(SERVER_DIR / "data" / "monitor.sqlite3"))
        ).expanduser()
        fraud_rules_value = os.getenv("REGLAS_FRAUDE_CSV", "").strip()
        fraud_rules_path = Path(
            fraud_rules_value or str(SERVER_DIR / "data" / "reglas_fraude.csv")
        ).expanduser()
        public_base_url = os.getenv("BASE_URL_PUBLICA", "").strip()
        android_download_url = os.getenv("ANDROID_DOWNLOAD_URL", "").strip()
        lupita_events_url = os.getenv("LUPITA_EVENTS_URL", "").strip()
        lupita_events_key = os.getenv("LUPITA_EVENTS_KEY", "").strip()
        if bool(lupita_events_url) != bool(lupita_events_key):
            raise RuntimeError(
                "LUPITA_EVENTS_URL y LUPITA_EVENTS_KEY deben configurarse juntos."
            )
        if lupita_events_key and len(lupita_events_key) < 32:
            raise RuntimeError("LUPITA_EVENTS_KEY debe tener al menos 32 caracteres aleatorios.")
        if lupita_events_url:
            try:
                parsed_lupita_url = urlsplit(lupita_events_url)
                parsed_lupita_url.port
            except ValueError as exc:
                raise RuntimeError("LUPITA_EVENTS_URL debe ser una URL válida.") from exc
            if (
                parsed_lupita_url.scheme not in {"http", "https"}
                or not parsed_lupita_url.netloc
                or not parsed_lupita_url.hostname
                or parsed_lupita_url.username
                or parsed_lupita_url.password
                or parsed_lupita_url.path.rstrip("/") != "/api/eventos"
                or parsed_lupita_url.query
                or parsed_lupita_url.fragment
            ):
                raise RuntimeError(
                    "LUPITA_EVENTS_URL debe apuntar al endpoint /api/eventos, sin credenciales ni parámetros."
                )
            if parsed_lupita_url.scheme == "http":
                host = parsed_lupita_url.hostname.lower()
                try:
                    local_http = host == "localhost" or ipaddress.ip_address(host).is_loopback
                except ValueError:
                    local_http = False
                if not local_http:
                    raise RuntimeError(
                        "LUPITA_EVENTS_URL solo admite HTTP en loopback; usa HTTPS para otro host."
                    )
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
            secret_key=secret_key,
            database_path=database_path,
            retention_days=retention_days,
            port=port,
            cookie_secure=os.getenv("COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
            events_per_minute=events_per_minute,
            base_url_publica=public_base_url or None,
            android_download_url=android_download_url or None,
            data_encryption_key=encryption_key,
            retention_text_hours=retention_text_hours,
            retention_alert_days=retention_alert_days,
            reviewers_see_all=os.getenv("REVISORES_VEN_TODO", "").lower()
            in {"1", "true", "yes"},
            risk_medium_threshold=risk_medium_threshold,
            risk_high_threshold=risk_high_threshold,
            fraud_rules_path=fraud_rules_path,
            lupita_events_url=lupita_events_url or None,
            lupita_events_key=lupita_events_key or None,
        )
