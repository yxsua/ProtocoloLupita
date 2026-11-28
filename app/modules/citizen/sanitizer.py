"""Saneamiento estricto de datos personales (PII) antes de persistir o llamar al motor."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any
import uuid

from app.modules.citizen.schemas import CitizenReportRaw, ReportInput
from app.modules.sms.parser import defang_url, extract_indicators

_CURP_REGEX = re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d\b", re.IGNORECASE)
_RFC_REGEX = re.compile(r"\b[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}\b", re.IGNORECASE)
_EMAIL_REGEX = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_SELF_NAME_REGEX = re.compile(
    r"(?i)\b(?:me\s+llamo|mi\s+nombre\s+es|soy)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3}"
)
_SELF_PHONE_REGEX = re.compile(
    r"(?i)\b(?:mi\s+(?:tel[eé]fono|cel|celular|n[uú]mero)(?:\s+es)?|ll[aá]menme\s+al)\s*[:#]?\s*(?:\+?52\s*1?\s*[-.]?\s*)?(?:\(?\d{2,3}\)?[\s.-]*\d{3,4}[\s.-]*\d{4})\b"
)
_URL_IN_TEXT_REGEX = re.compile(r"(?i)\bhttps?://[^\s<>\"'\]\)]+")

_PII_FIELDS = (
    ("reporter_name", "nombre"),
    ("reporter_curp", "curp"),
    ("reporter_phone", "telefono_reportante"),
    ("reporter_email", "correo"),
    ("reporter_address", "domicilio"),
)


def _hash_fingerprint(raw: CitizenReportRaw) -> str:
    seed = (
        (raw.session_token or "").strip()
        or (raw.reporter_curp or "").strip().upper()
        or re.sub(r"\D", "", raw.reporter_phone or "")
        or (raw.reporter_email or "").strip().lower()
        or "anon"
    )
    return hashlib.sha256(f"plan5-anon:{seed}".encode("utf-8")).hexdigest()[:16]


def _scrub_inline_pii(text: str, raw: CitizenReportRaw) -> tuple[str, list[str]]:
    redacted_types: list[str] = []
    cleaned = text or ""

    # Redactar coincidencias exactas de los valores PII declarados si aparecen en el texto
    exact_pairs = [
        (raw.reporter_curp, "[CURP_REDACTADA]", "curp_en_texto"),
        (raw.reporter_email, "[CORREO_REDACTADO]", "correo_en_texto"),
        (raw.reporter_phone, "[TEL_REDACTADO]", "telefono_en_texto"),
        (raw.reporter_name, "[NOMBRE_REDACTADO]", "nombre_en_texto"),
        (raw.reporter_address, "[DOMICILIO_REDACTADO]", "domicilio_en_texto"),
    ]
    for value, token, label in exact_pairs:
        if value and value.strip() and value.strip().lower() in cleaned.lower():
            pattern = re.compile(re.escape(value.strip()), re.IGNORECASE)
            cleaned = pattern.sub(token, cleaned)
            redacted_types.append(label)

    # Redactar patrones PII incidentales
    if _CURP_REGEX.search(cleaned):
        cleaned = _CURP_REGEX.sub("[CURP_REDACTADA]", cleaned)
        redacted_types.append("curp_patron")
    if _RFC_REGEX.search(cleaned):
        cleaned = _RFC_REGEX.sub("[RFC_REDACTADO]", cleaned)
        redacted_types.append("rfc_patron")
    if _EMAIL_REGEX.search(cleaned):
        cleaned = _EMAIL_REGEX.sub("[CORREO_REDACTADO]", cleaned)
        redacted_types.append("correo_patron")
    if _SELF_NAME_REGEX.search(cleaned):
        cleaned = _SELF_NAME_REGEX.sub("[NOMBRE_REDACTADO]", cleaned)
        redacted_types.append("nombre_patron")
    if _SELF_PHONE_REGEX.search(cleaned):
        cleaned = _SELF_PHONE_REGEX.sub("[TEL_REDACTADO]", cleaned)
        redacted_types.append("telefono_reportante_patron")

    # Desactivar cualquier URL dentro del resumen libre para nunca guardar http/https vivo
    cleaned = _URL_IN_TEXT_REGEX.sub(lambda m: defang_url(m.group(0)), cleaned)

    # Preservar orden unico
    seen: set[str] = set()
    unique_redacted = [t for t in redacted_types if not (t in seen or seen.add(t))]
    return cleaned.strip(), unique_redacted


def coerce_raw_report(raw_input: CitizenReportRaw | dict[str, Any]) -> CitizenReportRaw:
    """Normaliza dict o dataclass a CitizenReportRaw separando campos extra."""
    if isinstance(raw_input, CitizenReportRaw):
        return raw_input

    known = {
        "channel",
        "municipality",
        "description",
        "reported_sender_or_phone",
        "reported_url",
        "reported_account",
        "reported_business_name",
        "reporter_name",
        "reporter_curp",
        "reporter_phone",
        "reporter_email",
        "reporter_address",
        "session_token",
    }
    kwargs = {k: v for k, v in raw_input.items() if k in known}
    extra = {k: v for k, v in raw_input.items() if k not in known}
    return CitizenReportRaw(**kwargs, extra_fields=extra)


def sanitize_report(
    raw_input: CitizenReportRaw | dict[str, Any],
    *,
    report_id: str | None = None,
    created_at: str | None = None,
) -> ReportInput:
    """Funcion pura: descarta PII personal del reportante y produce ReportInput saneado."""
    raw = coerce_raw_report(raw_input)

    discarded_fields: list[str] = []
    for attr_name, public_label in _PII_FIELDS:
        val = getattr(raw, attr_name)
        if val is not None and str(val).strip():
            discarded_fields.append(public_label)

    for extra_key, extra_val in raw.extra_fields.items():
        if extra_val is not None and str(extra_val).strip():
            discarded_fields.append(f"extra:{extra_key}")

    sanitized_summary, redacted_inline = _scrub_inline_pii(raw.description, raw)

    extra_urls = [raw.reported_url] if raw.reported_url and raw.reported_url.strip() else []
    extra_accounts = (
        [raw.reported_account] if raw.reported_account and raw.reported_account.strip() else []
    )

    # Distinguir si reported_sender_or_phone es telefono numerico o remitente alfanumerico
    extra_phones: list[str] = []
    sender_val: str | None = None
    if raw.reported_sender_or_phone and raw.reported_sender_or_phone.strip():
        candidate = raw.reported_sender_or_phone.strip()
        digits = re.sub(r"\D", "", candidate)
        if len(digits) >= 10:
            extra_phones.append(candidate)
        else:
            sender_val = candidate

    indicators = extract_indicators(
        sanitized_summary,
        sender=sender_val,
        extra_urls=extra_urls,
        extra_phones=extra_phones,
        extra_accounts=extra_accounts,
    )

    business = raw.reported_business_name.strip() if raw.reported_business_name else None
    municipality = (raw.municipality or "").strip() or "No especificado"

    return ReportInput(
        report_id=report_id or f"REP-{uuid.uuid4().hex[:10].upper()}",
        channel=raw.channel,
        municipality=municipality,
        sanitized_summary=sanitized_summary,
        indicators=indicators,
        reported_business_name=business or None,
        discarded_pii_fields=discarded_fields,
        redacted_inline_pii=redacted_inline,
        rate_limited=False,
        fingerprint_hash=_hash_fingerprint(raw),
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )
