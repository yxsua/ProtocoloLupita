"""Clasificador de SMS reglas-primero con interfaz intercambiable de modelo local."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from app.modules.sms.schemas import DomainSignal, ImpersonatedEntity


class LocalClassifierProtocol(Protocol):
    """Interfaz intercambiable para etiqueta opcional de un modelo local."""

    def predict_label(self, sanitized_text: str, domain_checks: list[DomainSignal]) -> str | None:
        """Devuelve una etiqueta auxiliar opcional; nunca controla seguridad ni enlaces."""
        ...


class NullLocalClassifier:
    """Implementacion por defecto cuando no hay modelo local conectado."""

    def predict_label(self, sanitized_text: str, domain_checks: list[DomainSignal]) -> str | None:
        return None


# Patrones de texto no confiable / prompt injection incrustado en el SMS (E11)
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignora\s+(?:todas\s+)?(?:las\s+)?instrucciones"),
    re.compile(r"(?i)\bignore\s+(?:all\s+)?previous\s+instructions"),
    re.compile(r"(?i)\bclasifica\s+(?:este\s+)?(?:sms|mensaje)\s+como\s+(?:seguro|legitimo|valido)"),
    re.compile(r"(?i)\bmark\s+(?:this\s+)?message\s+as\s+safe"),
    re.compile(r"(?i)\bresponde\s+(?:solo|unicamente)\s+que\s+es\s+(?:seguro|oficial)"),
    re.compile(r"(?i)(?:<\s*script|system\s*:|assistant\s*:|developer\s*:)"),
]

_ENTITY_KEYWORDS: dict[ImpersonatedEntity, tuple[str, ...]] = {
    "SAT": ("sat", "buzon tributario", "multa fiscal", "declaracion", "devolucion", "rfc", "adeudo fiscal"),
    "IMSS": ("imss", "vigencia de derechos", "semanas cotizadas", "nss", "subsidio imss", "incapacidad"),
    "CFE": ("cfe", "recibo de luz", "medidor", "corte de energia", "corte de luz", "reconexion"),
    "banco": ("bbva", "banorte", "santander", "citibanamex", "banamex", "hsbc", "scotiabank", "banco azteca", "clabe", "cargo no reconocido", "token"),
    "paqueteria": ("estafeta", "dhl", "fedex", "ups", "correos de mexico", "paquete retenido", "paquete", "aduana", "guia de rastreo", "entrega fallida"),
    "telefonica": ("telcel", "movistar", "at&t", "att", "bait", "linea suspendida", "recarga", "bono de datos"),
}

_URGENCY_KEYWORDS = (
    "urgente",
    "inmediato",
    "de inmediato",
    "2 horas",
    "24 horas",
    "hoy",
    "medianoche",
    "bloqueo",
    "suspendida",
    "cortado",
    "embargo",
    "multa",
    "retenido",
    "vencido",
)

_CREDENTIAL_OR_PAYMENT_KEYWORDS = (
    "pague",
    "pagar",
    "transfiera",
    "clabe",
    "token",
    "nip",
    "valide",
    "confirme",
    "actualice",
    "regularice",
    "cobre",
    "bono",
)

_PRIZE_CLAIM_PATTERN = re.compile(
    r"(?i)\b(?:has\s+sid[oa]\s+ganador[oa]|ganaste|eres?\s+(?:el\s+)?ganador[oa]?|"
    r"ganador(?:es)?|premio|premiada|gratis|winner|you\s+won|congratulations)\b"
)
_LINK_ACTION_PATTERN = re.compile(
    r"(?i)\b(?:click|clic|cliquea|pincha|toca|pulsa|abre|abrir|visita|ingresa|entra|sigue)\b|"
    r"\b(?:siguiente|este|el)\s+(?:enlace|link)\b|\benlace\b|\blink\b"
)


@dataclass(slots=True)
class RuleClassification:
    """Resultado determinista de reglas antes de consultar process_event."""

    impersonated_entity: ImpersonatedEntity
    scam_type: str
    is_suspicious: bool
    rule_signals: list[str]
    untrusted_text_ignored: bool
    model_label: str | None = None


def detect_untrusted_instructions(text: str) -> bool:
    """Detecta intentos de manipulacion o inyeccion de instrucciones dentro del SMS."""
    return any(pattern.search(text or "") for pattern in _PROMPT_INJECTION_PATTERNS)


def _infer_entity(text_lower: str, domain_checks: list[DomainSignal]) -> ImpersonatedEntity:
    for check in domain_checks:
        if not check.is_shortener and check.matched_official_entity in _ENTITY_KEYWORDS:
            return check.matched_official_entity  # type: ignore[return-value]

    scores: dict[ImpersonatedEntity, int] = {}
    for entity, keywords in _ENTITY_KEYWORDS.items():
        hits = sum(
            1
            for kw in keywords
            if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", text_lower)
        )
        if hits > 0:
            scores[entity] = hits

    if not scores:
        return "ninguno"
    return max(scores, key=lambda key: scores[key])


def _infer_scam_type(
    entity: ImpersonatedEntity,
    text_lower: str,
    rule_signals: list[str],
    is_suspicious: bool,
) -> str:
    if not is_suspicious:
        return "informativo_oficial"
    if "prize_link_lure" in rule_signals:
        return "falso_premio_paquete"
    if "prompt_injection_attempt" in rule_signals and entity == "ninguno":
        return "manipulacion_prompt"
    if any(k in text_lower for k in ("paquete retenido", "aduana", "entrega fallida", "paquete")):
        return "paquete_retenido"
    if entity == "SAT" or any(k in text_lower for k in ("multa fiscal", "buzon tributario", "adeudo fiscal")):
        return "urgencia_fiscal_multa"
    if entity == "CFE" or any(k in text_lower for k in ("corte de energia", "corte de luz", "recibo", "reconexion")):
        return "adeudo_corte_servicio"
    if entity == "banco" or any(k in text_lower for k in ("cargo no reconocido", "token", "clabe", "bloqueo de cuenta")):
        return "cargo_no_reconocido_bloqueo"
    if entity == "IMSS":
        return "tramite_imss_subsidio"
    if entity == "telefonica":
        return "suspension_linea_recarga"
    if "shortener_detected" in rule_signals:
        return "enlace_acortado_sospechoso"
    if "prompt_injection_attempt" in rule_signals:
        return "manipulacion_prompt"
    return "sospechoso_general"


def classify_sms_rules(
    body: str,
    domain_checks: list[DomainSignal],
    local_classifier: LocalClassifierProtocol | None = None,
) -> RuleClassification:
    """Clasifica suplantacion y tipo de engaño mediante reglas primero."""
    text = body or ""
    text_lower = text.lower()
    signals: list[str] = []

    untrusted_attempt = detect_untrusted_instructions(text)
    if untrusted_attempt:
        signals.append("prompt_injection_attempt")

    has_shortener = any(d.is_shortener for d in domain_checks)
    has_imitation = any(
        ("typosquatting_or_imitation" in d.reason_codes or "brand_impersonation" in d.reason_codes or "subdomain_spoof" in d.reason_codes)
        for d in domain_checks
    )
    has_punycode = any(d.is_punycode for d in domain_checks)
    has_homoglyphs = any(d.has_homoglyphs for d in domain_checks)
    has_suspicious_tld = any("suspicious_tld" in d.reason_codes for d in domain_checks)
    all_official_exact = bool(domain_checks) and all(d.is_official_exact for d in domain_checks)

    if has_shortener:
        signals.append("shortener_detected")
    if has_imitation:
        signals.append("domain_imitation")
    if has_punycode:
        signals.append("punycode_domain")
    if has_homoglyphs:
        signals.append("unicode_homoglyph")
    if has_suspicious_tld:
        signals.append("suspicious_tld")
    if all_official_exact:
        signals.append("official_domain_verified")

    urgency_hits = [kw for kw in _URGENCY_KEYWORDS if kw in text_lower]
    action_hits = [kw for kw in _CREDENTIAL_OR_PAYMENT_KEYWORDS if kw in text_lower]
    prize_claim = bool(_PRIZE_CLAIM_PATTERN.search(text))
    link_action = bool(_LINK_ACTION_PATTERN.search(text))
    prize_link_lure = prize_claim and link_action
    if urgency_hits:
        signals.append("urgency_pressure")
    if action_hits:
        signals.append("payment_or_credential_lure")
    if prize_claim:
        signals.append("unexpected_prize_claim")
    if link_action:
        signals.append("link_open_requested")
    if prize_link_lure:
        signals.append("prize_link_lure")

    entity = _infer_entity(text_lower, domain_checks)

    # Regla de decision: nunca confiar en instrucciones embebidas ni en dominios no oficiales con señuelo
    is_suspicious = bool(
        untrusted_attempt
        or has_shortener
        or has_imitation
        or has_punycode
        or has_homoglyphs
        or has_suspicious_tld
        or (not all_official_exact and (urgency_hits or action_hits or prize_link_lure))
    )

    scam_type = _infer_scam_type(entity, text_lower, signals, is_suspicious)

    # Interfaz intercambiable de modelo local (solo etiqueta auxiliar, nunca revoca sospecha)
    classifier = local_classifier or NullLocalClassifier()
    model_label = classifier.predict_label(text, domain_checks)

    return RuleClassification(
        impersonated_entity=entity,
        scam_type=scam_type,
        is_suspicious=is_suspicious,
        rule_signals=signals,
        untrusted_text_ignored=untrusted_attempt,
        model_label=model_label,
    )
