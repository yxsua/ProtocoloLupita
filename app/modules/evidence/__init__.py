"""Módulo de evidencia reproducible mediante cadena ordenada de hashes SHA-256."""

from .chain import (
    DEMO_INTEGRITY_NOTE,
    GENESIS_HASH,
    ChainVerificationResult,
    EvidenceRecord,
    build_evidence_record,
    canonical_json,
    compute_payload_hash,
    compute_record_hash,
    verify_chain,
)
from .store import EvidenceStore

__all__ = [
    "DEMO_INTEGRITY_NOTE",
    "GENESIS_HASH",
    "ChainVerificationResult",
    "EvidenceRecord",
    "EvidenceStore",
    "build_evidence_record",
    "canonical_json",
    "compute_payload_hash",
    "compute_record_hash",
    "verify_chain",
]
