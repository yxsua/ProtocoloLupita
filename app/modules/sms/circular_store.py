"""Almacen de analisis circular: aprende de reportes ciudadanos saneados para alertar a otros."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
import re
from typing import Any

from app.modules.sms.dataset_classifier import (
    SpamDatasetClassifier,
    get_default_dataset_classifier,
)
from app.modules.sms.schemas import ExtractedIndicators, VerificationStatus

_URL_MASK_RE = re.compile(r"(?i)hxxps?://\S+|https?://\S+")
_DIGIT_MASK_RE = re.compile(r"\b\d{4,}\b")
_WORD_RE = re.compile(r"[a-z0-9áéíóúñ]{3,}", re.IGNORECASE)


def normalize_pattern_template(text: str) -> str:
    """Convierte un mensaje saneado en plantilla anonimizada comparable."""
    cleaned = _URL_MASK_RE.sub("<URL>", text or "")
    cleaned = _DIGIT_MASK_RE.sub("<NUM>", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def _token_set(template: str) -> set[str]:
    return {w for w in _WORD_RE.findall(template) if w not in ("url", "num")}


@dataclass(slots=True)
class CircularPattern:
    """Patron anonimizado aprendido de reportes ciudadanos validos (sin PII)."""

    pattern_id: str
    template: str
    safe_excerpt: str
    impersonated_entity: str
    scam_type: str
    indicators: set[str] = field(default_factory=set)
    report_count: int = 1
    latest_status: VerificationStatus = "sin_verificar"


@dataclass(slots=True)
class CircularMatch:
    """Coincidencia preventiva contra reportes ciudadanos previos o base historica."""

    pattern_id: str
    source: str  # "reporte_ciudadano" | "base_historica_spam"
    similarity: float
    report_count: int
    matched_indicators: list[str]
    excerpt: str
    warning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CircularPatternStore:
    """Bucle circular seguro: reporte saneado -> patron anonimo -> alerta preventiva a nuevos SMS."""

    def __init__(self, dataset_classifier: SpamDatasetClassifier | None = None) -> None:
        self._patterns: list[CircularPattern] = []
        self._seq = 0
        self._dataset = dataset_classifier

    def _get_dataset(self) -> SpamDatasetClassifier:
        if self._dataset is None:
            self._dataset = get_default_dataset_classifier()
        return self._dataset

    @staticmethod
    def _collect_indicator_keys(indicators: ExtractedIndicators) -> set[str]:
        keys: set[str] = set()
        for val in (
            indicators.domains
            + indicators.phones
            + indicators.accounts
            + indicators.defanged_urls
            + indicators.senders
        ):
            norm = val.strip().lower()
            if norm:
                keys.add(norm)
        return keys

    def record_citizen_pattern(
        self,
        *,
        sanitized_text: str,
        indicators: ExtractedIndicators,
        impersonated_entity: str,
        scam_type: str,
        verification_status: VerificationStatus,
        rate_limited: bool = False,
    ) -> CircularPattern | None:
        """Registra un patron ciudadano ya saneado. Ignora envios limitados por tasa."""
        if rate_limited:
            return None

        template = normalize_pattern_template(sanitized_text)
        keys = self._collect_indicator_keys(indicators)
        if not template and not keys:
            return None

        # Buscar si ya existe un patron ciudadano similar o con indicador compartido
        q_tokens = _token_set(template)
        for pat in self._patterns:
            overlap = keys & pat.indicators
            seq_sim = SequenceMatcher(None, template, pat.template).ratio() if (template and pat.template) else 0.0
            p_tokens = _token_set(pat.template)
            jaccard = (len(q_tokens & p_tokens) / len(q_tokens | p_tokens)) if (q_tokens and p_tokens) else 0.0

            if overlap or seq_sim >= 0.65 or jaccard >= 0.55:
                pat.report_count += 1
                pat.indicators.update(keys)
                if verification_status == "campana_corroborada" or (
                    verification_status == "indicio" and pat.latest_status == "sin_verificar"
                ):
                    pat.latest_status = verification_status
                return pat

        self._seq += 1
        safe_excerpt = (sanitized_text or "").strip()[:180]
        new_pat = CircularPattern(
            pattern_id=f"PAT-CIRC-{self._seq:03d}",
            template=template,
            safe_excerpt=safe_excerpt,
            impersonated_entity=impersonated_entity,
            scam_type=scam_type,
            indicators=keys,
            report_count=1,
            latest_status=verification_status,
        )
        self._patterns.append(new_pat)
        return new_pat

    def match_patterns(
        self,
        text: str,
        indicators: ExtractedIndicators,
    ) -> list[CircularMatch]:
        """Compara un SMS o reporte contra reportes ciudadanos previos y contra spam.csv."""
        matches: list[CircularMatch] = []
        template = normalize_pattern_template(text)
        keys = self._collect_indicator_keys(indicators)
        q_tokens = _token_set(template)

        # 1. Comparar contra patrones aprendidos de reportes ciudadanos previos
        for pat in self._patterns:
            overlap = sorted(keys & pat.indicators)
            seq_sim = SequenceMatcher(None, template, pat.template).ratio() if (template and pat.template) else 0.0
            p_tokens = _token_set(pat.template)
            jaccard = (len(q_tokens & p_tokens) / len(q_tokens | p_tokens)) if (q_tokens and p_tokens) else 0.0
            sim = round(max(seq_sim, jaccard, 0.95 if overlap else 0.0), 3)

            if overlap or sim >= 0.52:
                matches.append(
                    CircularMatch(
                        pattern_id=pat.pattern_id,
                        source="reporte_ciudadano",
                        similarity=sim,
                        report_count=pat.report_count,
                        matched_indicators=overlap,
                        excerpt=pat.safe_excerpt,
                        warning=(
                            f"Coincide con {pat.report_count} reporte(s) ciudadano(s) previo(s) "
                            f"({pat.scam_type}). Evita abrir enlaces o responder."
                        ),
                    )
                )

        # 2. Comparar contra base historica de mensajes de estafa (spam.csv)
        ds = self._get_dataset()
        if ds.is_loaded:
            spam_prob = ds.predict_spam_probability(text)
            exemplar_match = ds.find_closest_spam_exemplar(text)
            if spam_prob >= 0.78 or exemplar_match is not None:
                ex_excerpt = exemplar_match[0].defanged_excerpt if exemplar_match else "Patron estadistico de la base historica spam.csv"
                ex_id = f"DATASET-SPAM-{exemplar_match[0].row_id}" if exemplar_match else "DATASET-SPAM-NB"
                score = exemplar_match[1] if exemplar_match else spam_prob
                matches.append(
                    CircularMatch(
                        pattern_id=ex_id,
                        source="base_historica_spam",
                        similarity=round(score, 3),
                        report_count=ds.spam_docs,
                        matched_indicators=[],
                        excerpt=ex_excerpt,
                        warning=(
                            f"Patron similar a mensajes conocidos de estafa en la base historica "
                            f"(afinidad {int(round(spam_prob * 100))}%). No abras enlaces."
                        ),
                    )
                )

        matches.sort(key=lambda m: (-m.similarity, -m.report_count))
        return matches

    def list_recent_alerts(self, *, limit: int = 8) -> list[dict[str, Any]]:
        """Devuelve alertas anonimas publicas para prevenir a otros (sin PII ni negocios sin verificar)."""
        alerts: list[dict[str, Any]] = []
        for pat in reversed(self._patterns[-limit:]):
            alerts.append(
                {
                    "pattern_id": pat.pattern_id,
                    "impersonated_entity": pat.impersonated_entity,
                    "scam_type": pat.scam_type,
                    "report_count": pat.report_count,
                    "status": pat.latest_status,
                    "safe_excerpt": pat.safe_excerpt,
                    "warning": "Patron reportado por ciudadania. No abras enlaces hxxp ni compartas codigos.",
                }
            )
        return alerts

    def reset(self) -> None:
        self._patterns.clear()
        self._seq = 0
