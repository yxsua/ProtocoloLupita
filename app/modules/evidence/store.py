"""Almacenamiento y consulta de registros de evidencia en memoria o SQLite."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

from .chain import (
    DEMO_INTEGRITY_NOTE,
    GENESIS_HASH,
    ChainVerificationResult,
    EvidenceRecord,
    build_evidence_record,
    verify_chain,
)


class EvidenceStore:
    """Repositorio ordenado para registrar y consultar la cadena de evidencia."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self._db_path = str(db_path) if db_path is not None else None
        self._records: list[EvidenceRecord] = []
        if self._db_path is not None:
            self._init_sqlite()
            self._load_from_sqlite()

    def _connect(self) -> sqlite3.Connection:
        assert self._db_path is not None
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self) -> None:
        assert self._db_path is not None
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_chain (
                    seq INTEGER PRIMARY KEY,
                    event_id TEXT UNIQUE NOT NULL,
                    occurred_at TEXT NOT NULL,
                    algorithm TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    demo_integrity_note TEXT NOT NULL
                )
                """
            )

    def _load_from_sqlite(self) -> None:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT seq, event_id, occurred_at, algorithm, prev_hash,
                       payload_hash, record_hash, payload_json, demo_integrity_note
                FROM evidence_chain
                ORDER BY seq ASC
                """
            ).fetchall()
        self._records = [
            EvidenceRecord(
                seq=int(row["seq"]),
                event_id=str(row["event_id"]),
                occurred_at=str(row["occurred_at"]),
                algorithm=str(row["algorithm"]),
                prev_hash=str(row["prev_hash"]),
                payload_hash=str(row["payload_hash"]),
                record_hash=str(row["record_hash"]),
                payload=json.loads(row["payload_json"]),
                demo_integrity_note=str(row["demo_integrity_note"] or DEMO_INTEGRITY_NOTE),
            )
            for row in rows
        ]

    def append(
        self,
        event_id: str,
        occurred_at: str,
        sanitized_payload: dict[str, Any],
    ) -> EvidenceRecord:
        """Agrega un nuevo evento sanitizado al final de la cadena."""
        existing = self.get_by_event_id(event_id)
        if existing is not None:
            return existing

        seq = len(self._records) + 1
        prev_hash = self._records[-1].record_hash if self._records else GENESIS_HASH
        record = build_evidence_record(
            seq=seq,
            event_id=event_id,
            occurred_at=occurred_at,
            sanitized_payload=sanitized_payload,
            prev_hash=prev_hash,
        )
        self._records.append(record)
        if self._db_path is not None:
            with closing(self._connect()) as conn, conn:
                conn.execute(
                    """
                    INSERT INTO evidence_chain (
                        seq, event_id, occurred_at, algorithm, prev_hash,
                        payload_hash, record_hash, payload_json, demo_integrity_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.seq,
                        record.event_id,
                        record.occurred_at,
                        record.algorithm,
                        record.prev_hash,
                        record.payload_hash,
                        record.record_hash,
                        json.dumps(record.payload, sort_keys=True, ensure_ascii=False),
                        record.demo_integrity_note,
                    ),
                )
        return record

    def list_records(self) -> list[EvidenceRecord]:
        """Devuelve todos los registros en orden secuencial."""
        if self._db_path is not None:
            self._load_from_sqlite()
        return list(self._records)

    def get_by_event_id(self, event_id: str) -> Optional[EvidenceRecord]:
        """Consulta un registro de evidencia por su identificador de evento."""
        for rec in self.list_records():
            if rec.event_id == event_id:
                return rec
        return None

    def verify_integrity(self) -> ChainVerificationResult:
        """Verifica la integridad completa de los registros almacenados."""
        return verify_chain(self.list_records())
