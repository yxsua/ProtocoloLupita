"""Comparacion local de dominios sin abrir enlaces ni hacer consultas de red."""

from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from app.modules.sms.schemas import DomainSignal

_DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "fixtures" / "official_domains.json"
)

# Mapa minimo de homografos comunes (cirilico/griego -> ASCII) para detectar imitaciones IDN
_CONFUSABLE_MAP = str.maketrans(
    {
        "\u0430": "a",  # Cyrillic а
        "\u0435": "e",  # Cyrillic е
        "\u043e": "o",  # Cyrillic о
        "\u0440": "p",  # Cyrillic р
        "\u0441": "c",  # Cyrillic с
        "\u0445": "x",  # Cyrillic х
        "\u0456": "i",  # Cyrillic і
        "\u0443": "y",  # Cyrillic у
        "\u03b1": "a",  # Greek α
        "\u03bf": "o",  # Greek ο
        "\u03b5": "e",  # Greek ε
        "0": "o",
        "1": "l",
    }
)


@lru_cache(maxsize=1)
def load_domain_catalog(catalog_path: Path | None = None) -> dict[str, Any]:
    """Carga el catalogo local de dominios oficiales, acortadores y TLDs sospechosos."""
    target = catalog_path or _DEFAULT_CATALOG_PATH
    with target.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _to_ascii_skeleton(domain: str) -> str:
    return domain.lower().translate(_CONFUSABLE_MAP)


def _is_official_host(host: str, official_domain: str) -> bool:
    return host == official_domain or host.endswith("." + official_domain)


def analyze_domain(domain: str, catalog: dict[str, Any] | None = None) -> DomainSignal:
    """Evalua un dominio exclusivamente contra catalogo y heuristicas locales."""
    cfg = catalog or load_domain_catalog()
    host = domain.strip().lower().rstrip(".")
    reasons: list[str] = []

    is_punycode = any(label.startswith("xn--") for label in host.split("."))
    has_homoglyphs = any(ord(ch) > 127 for ch in host)
    if is_punycode:
        reasons.append("punycode")
    if has_homoglyphs:
        reasons.append("unicode_homoglyph")

    shorteners = {s.lower() for s in cfg.get("shorteners", [])}
    is_shortener = any(host == s or host.endswith("." + s) for s in shorteners)
    if is_shortener:
        reasons.append("shortener")
        return DomainSignal(
            domain=host,
            is_official_exact=False,
            is_shortener=True,
            is_punycode=is_punycode,
            has_homoglyphs=has_homoglyphs,
            matched_official_entity=None,
            matched_official_domain=None,
            similarity_score=0.0,
            reason_codes=reasons,
        )

    entities: dict[str, dict[str, Any]] = cfg.get("official_entities", {})

    # 1. Coincidencia exacta oficial (solo si no contiene homografos ni punycode engañoso)
    if not has_homoglyphs and not is_punycode:
        for entity_key, info in entities.items():
            for off_dom in info.get("domains", []):
                off_low = off_dom.lower()
                if _is_official_host(host, off_low):
                    return DomainSignal(
                        domain=host,
                        is_official_exact=True,
                        is_shortener=False,
                        is_punycode=False,
                        has_homoglyphs=False,
                        matched_official_entity=entity_key,
                        matched_official_domain=off_low,
                        similarity_score=1.0,
                        reason_codes=["official_exact"],
                    )

    # 2. Comparacion por similitud, tokens de marca y subdominios engañosos
    skeleton = _to_ascii_skeleton(host)
    best_score = 0.0
    best_entity: str | None = None
    best_official: str | None = None

    for entity_key, info in entities.items():
        for off_dom in info.get("domains", []):
            off_low = off_dom.lower()
            # Compara dominio completo y etiqueta principal
            full_ratio = SequenceMatcher(None, skeleton, off_low).ratio()
            host_root = skeleton.split(".")[0]
            off_root = off_low.split(".")[0]
            root_ratio = SequenceMatcher(None, host_root, off_root).ratio()
            score = max(full_ratio, root_ratio)

            # Deteccion de dominio oficial incrustado como prefijo (ej: sat.gob.mx.verificacion.xyz)
            if off_low in host and not _is_official_host(host, off_low):
                score = max(score, 0.92)
                if "subdomain_spoof" not in reasons:
                    reasons.append("subdomain_spoof")

            if score > best_score:
                best_score = score
                best_entity = entity_key
                best_official = off_low

        # Deteccion por tokens de marca dentro de dominio no oficial
        if not is_shortener:
            tokens = [t.lower() for t in info.get("brand_tokens", []) if len(t) >= 3]
            matched_tokens = [tok for tok in tokens if tok in skeleton]
            if matched_tokens:
                # Si incluye la marca y al menos otro token o separador típico de phishing
                if len(matched_tokens) >= 2 or "-" in host or has_homoglyphs or is_punycode:
                    if best_score < 0.78:
                        best_score = 0.78
                        best_entity = entity_key
                        best_official = (info.get("domains") or [None])[0]
                    if "brand_impersonation" not in reasons:
                        reasons.append("brand_impersonation")

    tld = host.rsplit(".", 1)[-1] if "." in host else ""
    suspicious_tlds = {t.lower() for t in cfg.get("suspicious_tlds", [])}
    if tld in suspicious_tlds:
        reasons.append("suspicious_tld")

    if best_score >= 0.72 and not is_shortener:
        reasons.append("typosquatting_or_imitation")
    elif not is_shortener:
        # Limpiar entidad si la similitud es demasiado baja y no hubo tokens de marca
        if "brand_impersonation" not in reasons and "subdomain_spoof" not in reasons:
            best_entity = None
            best_official = None

    return DomainSignal(
        domain=host,
        is_official_exact=False,
        is_shortener=is_shortener,
        is_punycode=is_punycode,
        has_homoglyphs=has_homoglyphs,
        matched_official_entity=best_entity,
        matched_official_domain=best_official,
        similarity_score=round(best_score, 3),
        reason_codes=reasons,
    )


def analyze_domains(domains: list[str], catalog: dict[str, Any] | None = None) -> list[DomainSignal]:
    """Analiza una lista de dominios sin ejecutar peticiones de red."""
    cfg = catalog or load_domain_catalog()
    return [analyze_domain(dom, cfg) for dom in domains]
