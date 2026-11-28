from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

REQUIRED_COLUMNS = {"rule_id", "kind", "value", "entity", "score", "reason", "enabled"}
ALLOWED_KINDS = {"sender", "domain", "phrase", "regex", "entity"}
_RULE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
MAX_RULE_FILE_BYTES = 1_000_000
MAX_RULES = 2_000


@dataclass(frozen=True)
class FraudRule:
    rule_id: str
    kind: str
    value: str
    entity: str
    score: int
    reason: str

    @property
    def label(self) -> str:
        return self.reason or f"{self.kind}: {self.value}"


def parse_rules_csv(content: str) -> list[FraudRule]:
    reader = csv.DictReader(content.splitlines())
    if reader.fieldnames is None:
        raise ValueError("El CSV debe incluir encabezados.")
    headers = {name.strip() for name in reader.fieldnames if name}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise ValueError("Faltan columnas requeridas: " + ", ".join(sorted(missing)))

    rules: list[FraudRule] = []
    seen: set[str] = set()
    for row_number, raw in enumerate(reader, start=2):
        if row_number > MAX_RULES + 1:
            raise ValueError(f"El CSV supera el máximo de {MAX_RULES} reglas.")
        row = {str(key).strip(): (value or "").strip() for key, value in raw.items() if key}
        if row.get("enabled", "true").casefold() not in {"1", "true", "yes", "si", "sí"}:
            continue
        rule_id = row.get("rule_id", "")
        kind = row.get("kind", "").casefold()
        value = row.get("value", "")
        entity = row.get("entity", "")
        reason = row.get("reason", "")
        if not _RULE_ID.fullmatch(rule_id):
            raise ValueError(f"El rule_id de la fila {row_number} no es válido.")
        if rule_id in seen:
            raise ValueError(f"El rule_id {rule_id} está duplicado.")
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"El kind de la fila {row_number} debe ser uno de {sorted(ALLOWED_KINDS)}.")
        if not value or len(value) > 256 or len(entity) > 128 or len(reason) > 240:
            raise ValueError(f"Los campos de texto de la fila {row_number} exceden su límite.")
        try:
            score = int(row.get("score", ""))
        except ValueError as exc:
            raise ValueError(f"El score de la fila {row_number} debe ser entero.") from exc
        if not 1 <= score <= 100:
            raise ValueError(f"El score de la fila {row_number} debe estar entre 1 y 100.")
        if kind == "regex":
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"La regex de la fila {row_number} no es válida.") from exc
        seen.add(rule_id)
        rules.append(FraudRule(rule_id, kind, value, entity, score, reason))
    return rules


def load_rules_csv(path: Path) -> list[FraudRule]:
    try:
        if path.stat().st_size > MAX_RULE_FILE_BYTES:
            raise ValueError("El CSV de reglas supera el tamaño máximo de 1 MB.")
    except FileNotFoundError:
        return []
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RuntimeError(f"No se pudo leer el CSV de reglas: {path}") from exc
    return parse_rules_csv(content)
