from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

from app.fraude.csv_source import FraudRule, load_rules_csv

URL_PATTERN = re.compile(
    r"(?i)\b(?:https?://|www\.)[^\s<>\"']+|"
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|mx|net|org|io|app|info|site|top|xyz|link)\b"
)
SHORTENER_DOMAINS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "cutt.ly",
    "is.gd",
    "rebrand.ly",
    "rb.gy",
}
TRUSTED_ENTITIES = {
    "bbva": {"bbva.mx"},
    "banorte": {"banorte.com", "banorte.com.mx"},
    "santander": {"santander.com.mx", "santander.com"},
    "citibanamex": {"citibanamex.com"},
    "banco azteca": {"bancoazteca.com.mx"},
    "mercado pago": {"mercadopago.com.mx", "mercadopago.com"},
    "cfe": {"cfe.mx"},
    "dhl": {"dhl.com", "dhl.com.mx"},
    "estafeta": {"estafeta.com"},
    "correos de mexico": {"correosdemexico.gob.mx"},
}
HEURISTICS = (
    (
        "heuristic.urgency",
        re.compile(r"\b(?:urgente|ahora mismo|de inmediato|ultim[oa] aviso|hoy mismo)\b"),
        12,
        "Usa lenguaje de urgencia para presionar una acción inmediata.",
    ),
    (
        "heuristic.credentials",
        re.compile(r"\b(?:comparte|envia|dicta|proporciona|confirma|captura)\b.{0,50}\b(?:codigo|nip|password|contrasena|token|clave)\b|\b(?:nip|contrasena|token)\b.{0,35}\b(?:comparte|envia|dicta|confirma)\b"),
        28,
        "Solicita compartir un código, contraseña, NIP o token.",
    ),
    (
        "heuristic.payment",
        re.compile(r"\b(?:transfiere|transferencia|deposit[oa]|paga|pago|tarjeta de regalo|gift card|cripto)\b"),
        22,
        "Solicita una transferencia, pago o medio difícil de revertir.",
    ),
    (
        "heuristic.install-app",
        re.compile(r"\b(?:instala|descarga)\b.{0,50}\b(?:aplicacion|app|archivo|apk|soporte)\b"),
        18,
        "Pide instalar una app o archivo fuera de un canal verificado.",
    ),
    (
        "heuristic.family-emergency",
        re.compile(r"\b(?:soy tu hijo|soy tu hija|soy tu nieto|soy tu nieta|cambie de numero|me robaron el celular|estoy detenido|tuve un accidente)\b"),
        24,
        "El mensaje coincide con un guion de familiar en apuros.",
    ),
    (
        "heuristic.account-threat",
        re.compile(r"\b(?:bloquearemos|bloqueada|bloqueo de cuenta|suspenderemos|cancelaremos|tarjeta bloqueada)\b"),
        16,
        "Amenaza con bloquear o suspender una cuenta o tarjeta.",
    ),
    (
        "heuristic.prize",
        re.compile(r"\b(?:ganaste|ganador|premio|bono|apoyo pendiente|reclama tu premio|sorteo)\b"),
        18,
        "Asegura que hay un premio o apoyo que requiere una acción.",
    ),
)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_mexican_number(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if digits.startswith("0052"):
        digits = digits[2:]
    if digits.startswith("521") and len(digits) == 13:
        digits = "52" + digits[3:]
    elif digits.startswith("044") or digits.startswith("045"):
        digits = digits[3:]
    elif digits.startswith("01") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10:
        return "+52" + digits
    if len(digits) == 12 and digits.startswith("52"):
        return "+" + digits
    if value.strip().startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    return None


def _domains(text: str) -> list[str]:
    result: list[str] = []
    for match in URL_PATTERN.findall(text):
        candidate = match.rstrip(".,;:!?)]}")
        try:
            parsed = urlsplit(candidate if "://" in candidate else "https://" + candidate)
            host = (parsed.hostname or "").rstrip(".").casefold()
        except ValueError:
            continue
        if not host:
            continue
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            pass
        if host not in result:
            result.append(host)
    return result


def _domain_matches(domain: str, expected: str) -> bool:
    return domain == expected or domain.endswith("." + expected)


def _trusted_domain_suspicion(domain: str, text: str) -> tuple[str, str] | None:
    normalized_host = normalize_text(domain.replace("xn--", " "))
    mentions = [
        (entity, domains)
        for entity, domains in TRUSTED_ENTITIES.items()
        if normalize_text(entity) in normalize_text(text)
    ]
    for entity, official_domains in mentions:
        if any(_domain_matches(domain, official) for official in official_domains):
            continue
        if "xn--" in domain:
            return entity, "El enlace usa un dominio punycode mientras menciona una entidad conocida."
        labels = [label for label in normalized_host.split(".")[:-1] if label]
        for official in official_domains:
            official_label = normalize_text(official.split(".")[0])
            if any(
                label != official_label
                and SequenceMatcher(None, label, official_label).ratio() >= 0.72
                for label in labels
            ):
                return entity, "El dominio se parece al de una entidad conocida, pero no coincide."
        return entity, "Menciona una entidad conocida, pero el enlace no usa su dominio oficial."
    return None


def evaluate_event(
    event: dict[str, Any],
    *,
    rules_path: Path,
    medium_threshold: int = 40,
    high_threshold: int = 70,
) -> dict[str, Any]:
    text = str(event.get("texto") or "")
    sender = str(event.get("remitente") or "")
    normalized_text = normalize_text(text)
    normalized_sender = normalize_mexican_number(sender)
    domains = _domains(text)
    rules = load_rules_csv(rules_path)
    hits: dict[str, tuple[int, str]] = {}

    def add(rule_id: str, score: int, reason: str) -> None:
        hits.setdefault(rule_id, (score, reason))

    for rule in rules:
        if _matches_rule(rule, sender, normalized_sender, text, normalized_text, domains):
            add(rule.rule_id, rule.score, rule.label)

    for rule_id, pattern, score, reason in HEURISTICS:
        if pattern.search(normalized_text):
            add(rule_id, score, reason)

    for domain in domains:
        if any(_domain_matches(domain, shortener) for shortener in SHORTENER_DOMAINS):
            add(
                "heuristic.url-shortener",
                24,
                "Incluye un enlace acortado que oculta el dominio de destino.",
            )
        if "xn--" in domain:
            add(
                "heuristic.punycode",
                20,
                "El enlace contiene un dominio punycode que puede ocultar caracteres similares.",
            )
        suspicion = _trusted_domain_suspicion(domain, text)
        if suspicion:
            entity, reason = suspicion
            add(
                f"heuristic.impersonation.{normalize_text(entity).replace(' ', '-')}",
                28,
                reason,
            )
        if normalized_sender or not sender:
            add(
                "heuristic.unknown-sender-link",
                8,
                "Incluye un enlace enviado desde un número o remitente no verificado.",
            )

    risk = min(100, sum(score for score, _ in hits.values()))
    level = "alto" if risk >= high_threshold else "medio" if risk >= medium_threshold else "bajo"
    reasons = [
        {"regla": rule_id, "detalle": reason}
        for rule_id, (_, reason) in sorted(hits.items())
    ]
    return {
        "riesgo": risk,
        "nivel": level,
        "razones": reasons,
        "reglas": [
            {"id": rule_id, "etiqueta": reason[:200]}
            for rule_id, (_, reason) in sorted(hits.items())
        ],
    }


def _matches_rule(
    rule: FraudRule,
    sender: str,
    normalized_sender: str | None,
    text: str,
    normalized_text: str,
    domains: list[str],
) -> bool:
    if rule.kind == "sender":
        expected = normalize_mexican_number(rule.value)
        return expected is not None and normalized_sender == expected
    if rule.kind == "domain":
        expected = rule.value.casefold().encode("idna").decode("ascii")
        return any(_domain_matches(domain, expected) for domain in domains)
    if rule.kind == "phrase":
        return normalize_text(rule.value) in normalized_text
    if rule.kind == "regex":
        return re.search(normalize_text(rule.value), normalized_text) is not None
    if rule.kind == "entity":
        entity = normalize_text(rule.value)
        if entity not in normalized_text:
            return False
        if rule.entity:
            expected_domain = rule.entity.casefold().encode("idna").decode("ascii")
            return bool(domains) and not any(
                _domain_matches(domain, expected_domain) for domain in domains
            )
        return True
    return False
