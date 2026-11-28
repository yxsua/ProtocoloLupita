"""Clasificador local offline entrenado sobre la base historica spam.csv."""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import re

from app.modules.sms.parser import defang_url
from app.modules.sms.schemas import DomainSignal

_DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "datasets" / "spam.csv"
)

_TOKEN_RE = re.compile(r"[a-z0-9áéíóúñ]{2,}", re.IGNORECASE)
_URL_RE = re.compile(r"(?i)(?:https?://|hxxps?://|www\.)[^\s<>\"']+")
_PHONE_RE = re.compile(r"\b\d{5,13}\b")
_MONEY_RE = re.compile(r"(?:[$£€]\s*\d+|\b(?:mxn|usd|pesos|pounds|cash|premio|prize|bono)\b)", re.IGNORECASE)


def _tokenize_with_signals(text: str) -> list[str]:
    lowered = (text or "").lower()
    tokens = _TOKEN_RE.findall(lowered)
    if _URL_RE.search(lowered):
        tokens.append("__has_url__")
    if _PHONE_RE.search(lowered):
        tokens.append("__has_number__")
    if _MONEY_RE.search(lowered):
        tokens.append("__has_money_or_prize__")
    if any(w in lowered for w in ("urgent", "urgente", "ahora", "hoy", "2 horas", "immediately")):
        tokens.append("__urgency__")
    if any(w in lowered for w in ("claim", "winner", "free", "gratis", "ganaste", "reclama", "premio")):
        tokens.append("__lure__")
    return tokens


@dataclass(frozen=True, slots=True)
class DatasetExemplar:
    """Ejemplo historico anonimizado/desactivado de la base spam.csv."""

    row_id: int
    defanged_excerpt: str
    tokens: frozenset[str]


class SpamDatasetClassifier:
    """Modelo Naive Bayes local + similitud contra spam.csv (sin red ni dependencias externas)."""

    def __init__(self, dataset_path: Path | None = None) -> None:
        self.dataset_path = dataset_path or _DEFAULT_DATASET_PATH
        self.spam_counts: Counter[str] = Counter()
        self.ham_counts: Counter[str] = Counter()
        self.spam_total_tokens = 0
        self.ham_total_tokens = 0
        self.spam_docs = 0
        self.ham_docs = 0
        self.vocab: set[str] = set()
        self.spam_exemplars: list[DatasetExemplar] = []
        self._loaded = False

        if self.dataset_path.exists():
            self._load_and_train(self.dataset_path)

    def _load_and_train(self, path: Path) -> None:
        with path.open("r", encoding="latin-1", newline="") as fh:
            reader = csv.reader(fh)
            next(reader, None)  # saltar encabezado v1,v2
            for idx, row in enumerate(reader, start=1):
                if len(row) < 2:
                    continue
                label = row[0].strip().lower()
                text = row[1].strip()
                if label not in ("spam", "ham") or not text:
                    continue

                toks = _tokenize_with_signals(text)
                self.vocab.update(toks)
                if label == "spam":
                    self.spam_docs += 1
                    self.spam_counts.update(toks)
                    self.spam_total_tokens += len(toks)
                    # Desactivar URLs dentro del ejemplar historico antes de guardarlo
                    safe_text = _URL_RE.sub(lambda m: defang_url(m.group(0)), text)
                    self.spam_exemplars.append(
                        DatasetExemplar(
                            row_id=idx,
                            defanged_excerpt=safe_text[:180],
                            tokens=frozenset(toks),
                        )
                    )
                else:
                    self.ham_docs += 1
                    self.ham_counts.update(toks)
                    self.ham_total_tokens += len(toks)

        self._loaded = (self.spam_docs + self.ham_docs) > 0

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def stats(self) -> dict[str, int]:
        return {
            "total_messages": self.spam_docs + self.ham_docs,
            "spam_messages": self.spam_docs,
            "ham_messages": self.ham_docs,
        }

    def predict_spam_probability(self, text: str) -> float:
        """Calcula probabilidad Naive Bayes [0.0, 1.0] de coincidencia con spam historico."""
        if not self._loaded or not (text or "").strip():
            return 0.0

        toks = _tokenize_with_signals(text)
        if not toks:
            return 0.0

        vocab_size = max(1, len(self.vocab))
        total_docs = self.spam_docs + self.ham_docs
        log_spam = math.log(self.spam_docs / total_docs)
        log_ham = math.log(self.ham_docs / total_docs)

        denom_spam = self.spam_total_tokens + vocab_size
        denom_ham = self.ham_total_tokens + vocab_size

        for tok in toks:
            log_spam += math.log((self.spam_counts[tok] + 1) / denom_spam)
            log_ham += math.log((self.ham_counts[tok] + 1) / denom_ham)

        # Estabilidad numerica log-sum-exp
        max_log = max(log_spam, log_ham)
        p_spam = math.exp(log_spam - max_log)
        p_ham = math.exp(log_ham - max_log)
        return round(p_spam / (p_spam + p_ham), 4)

    def find_closest_spam_exemplar(self, text: str, *, min_jaccard: float = 0.28) -> tuple[DatasetExemplar, float] | None:
        """Busca el mensaje mas parecido dentro de la base spam.csv por similitud de tokens."""
        if not self._loaded:
            return None
        query_tokens = frozenset(_tokenize_with_signals(text))
        if len(query_tokens) < 3:
            return None

        best_item: DatasetExemplar | None = None
        best_score = 0.0
        for ex in self.spam_exemplars:
            inter = len(query_tokens & ex.tokens)
            if inter == 0:
                continue
            union = len(query_tokens | ex.tokens)
            score = inter / union if union else 0.0
            if score > best_score:
                best_score = score
                best_item = ex

        if best_item is not None and best_score >= min_jaccard:
            return best_item, round(best_score, 3)
        return None

    def predict_label(self, sanitized_text: str, domain_checks: list[DomainSignal]) -> str | None:
        """Implementa LocalClassifierProtocol para aportar etiqueta auxiliar."""
        if not self._loaded:
            return None
        prob = self.predict_spam_probability(sanitized_text)
        pct = int(round(prob * 100))
        if prob >= 0.70:
            return f"dataset_spam_match ({pct}%)"
        if prob <= 0.25:
            return f"dataset_ham_like ({pct}%)"
        return f"dataset_uncertain ({pct}%)"


@lru_cache(maxsize=1)
def get_default_dataset_classifier() -> SpamDatasetClassifier:
    """Devuelve instancia compartida y cacheada del clasificador de spam.csv."""
    return SpamDatasetClassifier()
