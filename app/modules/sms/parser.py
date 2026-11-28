"""Extraccion pura de indicadores y desactivacion segura de URLs (hxxp)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.modules.sms.schemas import ExtractedIndicators

# Detecta URLs con esquema http/https/hxxp/hxxps o dominios con ruta/parametros sin esquema
_URL_PATTERN = re.compile(
    r"(?i)\b(?:h(?:tt|xx)ps?://)[^\s<>\"'\]\)]+"
    r"|(?<![@\w.])(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\[\.\]|\.))+(?:com\.mx|gob\.mx|org\.mx|edu\.mx|net\.mx|mx|com|org|net|gob|xyz|top|click|online|site|club|icu|buzz|cfd|tk|ml|ga|ly|co|gd|at|me)(?:/[^\s<>\"'\]\)]*)?"
)

# Telefonos MX: 10 digitos o prefijo +52 / 521, evitando cortar CLABEs o tarjetas largas
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?52\s*1?\s*[-.]?\s*)?(?:\(?\d{2,3}\)?[\s.-]*\d{3,4}[\s.-]*\d{4})(?!\d)"
)

# Cuentas: CLABE (18 digitos), tarjeta (16 digitos) o referencia explicita de cuenta
_CLABE_OR_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d{18}|\d{16})(?!\d)")
_LABELED_ACCOUNT_PATTERN = re.compile(
    r"(?i)\b(?:clabe|cuenta|tarjeta|referencia|folio\s+de\s+pago)\s*[:#]?\s*([0-9* -]{8,24})"
)

_TRAILING_PUNCT = ".,;:!?\"')]"


def defang_url(raw_url: str) -> str:
    """Convierte cualquier URL a formato desactivado hxxp:// o hxxps://."""
    cleaned = raw_url.strip().rstrip(_TRAILING_PUNCT)
    cleaned = cleaned.replace("[.]", ".")
    lower = cleaned.lower()
    if lower.startswith("https://"):
        return "hxxps://" + cleaned[8:]
    if lower.startswith("http://"):
        return "hxxp://" + cleaned[7:]
    if lower.startswith("hxxps://") or lower.startswith("hxxp://"):
        return lower[:8] + cleaned[8:] if lower.startswith("hxxps://") else lower[:7] + cleaned[7:]
    return "hxxp://" + cleaned


def extract_domain(url_or_defanged: str) -> str:
    """Extrae el host normalizado en minusculas sin abrir ni resolver el enlace."""
    normalized = url_or_defanged.strip().rstrip(_TRAILING_PUNCT).replace("[.]", ".")
    lower = normalized.lower()
    if lower.startswith("hxxps://"):
        parse_target = "https://" + normalized[8:]
    elif lower.startswith("hxxp://"):
        parse_target = "http://" + normalized[7:]
    elif lower.startswith(("http://", "https://")):
        parse_target = normalized
    else:
        parse_target = "http://" + normalized

    parsed = urlparse(parse_target)
    host = (parsed.hostname or "").strip(".").lower()
    return host


def _normalize_phone(raw_phone: str) -> str | None:
    digits = re.sub(r"\D", "", raw_phone)
    if digits.startswith("521") and len(digits) == 13:
        digits = digits[3:]
    elif digits.startswith("52") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10:
        return digits
    return None


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def extract_indicators(
    body: str,
    *,
    sender: str | None = None,
    extra_urls: list[str] | None = None,
    extra_phones: list[str] | None = None,
    extra_accounts: list[str] | None = None,
) -> ExtractedIndicators:
    """Extrae remitente, enlaces desactivados (hxxp), dominios, telefonos y cuentas."""
    text = body or ""

    senders: list[str] = []
    if sender and sender.strip():
        senders.append(sender.strip())

    raw_urls = [m.group(0) for m in _URL_PATTERN.finditer(text)]
    if extra_urls:
        raw_urls.extend(u for u in extra_urls if u and u.strip())

    defanged_urls: list[str] = []
    domains: list[str] = []
    for raw_url in raw_urls:
        defanged = defang_url(raw_url)
        domain = extract_domain(defanged)
        if domain:
            defanged_urls.append(defanged)
            domains.append(domain)

    # Extraer cuentas primero para evitar falsos positivos con telefonos dentro de CLABEs
    accounts: list[str] = []
    for match in _CLABE_OR_CARD_PATTERN.finditer(text):
        accounts.append(match.group(0))
    for match in _LABELED_ACCOUNT_PATTERN.finditer(text):
        compact = re.sub(r"[\s-]+", "", match.group(1))
        if len(compact) >= 8:
            accounts.append(compact)
    if extra_accounts:
        for acc in extra_accounts:
            compact = re.sub(r"[\s-]+", "", acc or "")
            if compact:
                accounts.append(compact)

    phones: list[str] = []
    for match in _PHONE_PATTERN.finditer(text):
        norm = _normalize_phone(match.group(0))
        if norm:
            phones.append(norm)
    if extra_phones:
        for ph in extra_phones:
            cleaned = (ph or "").strip()
            norm = _normalize_phone(cleaned)
            phones.append(norm if norm else cleaned)

    return ExtractedIndicators(
        senders=_dedupe_preserve_order(senders),
        defanged_urls=_dedupe_preserve_order(defanged_urls),
        domains=_dedupe_preserve_order(domains),
        phones=_dedupe_preserve_order(phones),
        accounts=_dedupe_preserve_order(accounts),
    )
