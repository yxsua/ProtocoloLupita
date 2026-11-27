"""Cadena ordenada de hashes SHA-256 para detectar alteraciones en eventos de demo.

Nota: Este mecanismo verifica integridad reproducible dentro del prototipo y
no constituye por sí mismo cadena de custodia legal.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Optional, Sequence

GENESIS_HASH = "GENESIS"
HASH_ALGORITHM = "SHA-256"
DEMO_INTEGRITY_NOTE = (
    "Registro reproducible con hash y sello de tiempo para demo; "
    "no constituye cadena de custodia legal sin intervención de la autoridad competente."
)


@dataclass(frozen=True)
class EvidenceRecord:
    """Registro inmutable de un evento dentro de la cadena de integridad."""

    seq: int
    event_id: str
    occurred_at: str
    payload_hash: str
    prev_hash: str
    record_hash: str
    payload: dict[str, Any]
    algorithm: str = HASH_ALGORITHM
    demo_integrity_note: str = DEMO_INTEGRITY_NOTE

    def to_dict(self) -> dict[str, Any]:
        """Convierte el registro a diccionario serializable."""
        return asdict(self)


@dataclass(frozen=True)
class ChainVerificationResult:
    """Resultado de verificar la secuencia y los hashes de una cadena de evidencia."""

    intact: bool
    checked_count: int
    broken_at_seq: Optional[int] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convierte el resultado a diccionario serializable."""
        return asdict(self)


def canonical_json(payload: dict[str, Any]) -> str:
    """Serializa un diccionario de forma determinista para cálculo de hash."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Calcula el SHA-256 del payload sanitizado en JSON canónico."""
    encoded = canonical_json(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_record_hash(
    seq: int,
    algorithm: str,
    prev_hash: str,
    payload_hash: str,
) -> str:
    """Calcula el hash encadenado combinando secuencia, algoritmo, hash previo y payload."""
    material = f"{seq}|{algorithm}|{prev_hash}|{payload_hash}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def build_evidence_record(
    seq: int,
    event_id: str,
    occurred_at: str,
    sanitized_payload: dict[str, Any],
    prev_hash: str = GENESIS_HASH,
) -> EvidenceRecord:
    """Construye un EvidenceRecord enlazado al hash previo."""
    if seq < 1:
        raise ValueError("La secuencia de evidencia debe iniciar en 1.")
    payload_hash = compute_payload_hash(sanitized_payload)
    record_hash = compute_record_hash(seq, HASH_ALGORITHM, prev_hash, payload_hash)
    return EvidenceRecord(
        seq=seq,
        event_id=event_id,
        occurred_at=occurred_at,
        payload_hash=payload_hash,
        prev_hash=prev_hash,
        record_hash=record_hash,
        payload=sanitized_payload,
        algorithm=HASH_ALGORITHM,
        demo_integrity_note=DEMO_INTEGRITY_NOTE,
    )


def verify_chain(records: Sequence[EvidenceRecord | dict[str, Any]]) -> ChainVerificationResult:
    """Verifica orden estricto, enlace de hash previo e integridad de cada registro."""
    if not records:
        return ChainVerificationResult(intact=True, checked_count=0)

    expected_prev = GENESIS_HASH
    for idx, raw in enumerate(records, start=1):
        rec = raw.to_dict() if isinstance(raw, EvidenceRecord) else dict(raw)
        seq = rec.get("seq")
        if seq != idx:
            return ChainVerificationResult(
                intact=False,
                checked_count=idx - 1,
                broken_at_seq=seq if isinstance(seq, int) else idx,
                reason=f"Secuencia inesperada: se esperaba {idx} y se encontró {seq}.",
            )

        if rec.get("algorithm") != HASH_ALGORITHM:
            return ChainVerificationResult(
                intact=False,
                checked_count=idx - 1,
                broken_at_seq=idx,
                reason=f"Algoritmo no soportado en seq={idx}: {rec.get('algorithm')}.",
            )

        if rec.get("prev_hash") != expected_prev:
            return ChainVerificationResult(
                intact=False,
                checked_count=idx - 1,
                broken_at_seq=idx,
                reason=f"Ruptura de enlace prev_hash en seq={idx}.",
            )

        payload = rec.get("payload")
        if not isinstance(payload, dict):
            return ChainVerificationResult(
                intact=False,
                checked_count=idx - 1,
                broken_at_seq=idx,
                reason=f"Payload inválido o ausente en seq={idx}.",
            )

        recomputed_payload_hash = compute_payload_hash(payload)
        if rec.get("payload_hash") != recomputed_payload_hash:
            return ChainVerificationResult(
                intact=False,
                checked_count=idx - 1,
                broken_at_seq=idx,
                reason=f"Alteración detectada en el contenido (payload_hash) en seq={idx}.",
            )

        recomputed_record_hash = compute_record_hash(
            idx,
            HASH_ALGORITHM,
            expected_prev,
            recomputed_payload_hash,
        )
        if rec.get("record_hash") != recomputed_record_hash:
            return ChainVerificationResult(
                intact=False,
                checked_count=idx - 1,
                broken_at_seq=idx,
                reason=f"Alteración detectada en record_hash en seq={idx}.",
            )

        expected_prev = recomputed_record_hash

    return ChainVerificationResult(intact=True, checked_count=len(records))
