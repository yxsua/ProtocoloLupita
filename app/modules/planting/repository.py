"""Repositorio SQLite local para siembra, trampas y manifiesto de integridad."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.modules.planting.generator import (
    DEFAULT_PERIOD,
    DEFAULT_SEED,
    compute_manifest_hash,
    generate_synthetic_batch,
)
from app.modules.planting.schemas import PersonaRecord, SeedBatchSummary, SeedCopyRecord


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "protocolo_lupita.sqlite3"
DEFAULT_FIXTURE_PATH = REPO_ROOT / "data" / "planting" / "seed_copies.json"


def normalize_trap_id(raw_trap_id: Optional[str]) -> str:
    """Normaliza un identificador de número trampa ficticio a su forma canónica de 10 dígitos.

    Acepta variantes como ``"+52 442 XXX 0101 (ficticio)"``, ``"+52 442 000 0101"``,
    ``"524420000101"`` o ``"442-000-0101"``.
    """
    if not raw_trap_id:
        return ""
    cleaned = re.sub(r"\((?:ficticio|sint[eé]tico)\)|\[(?:ficticio|sint[eé]tico)\]", "", raw_trap_id, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s\-\.\(\)]+", "", cleaned).upper()
    # Permite resolver la notación ilustrativa '+52 442 XXX 0101' al rango sintético 4420000101.
    cleaned = re.sub(r"^(\+?52)?442XXX(\d{4})$", r"442000\2", cleaned)
    if cleaned.startswith("+52"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("52") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    return cleaned


def get_connection(db_path: Optional[str | Path] = None) -> sqlite3.Connection:
    """Abre una conexión SQLite local intentando reutilizar ``app.core.db`` si existe."""
    if db_path is None:
        try:  # pragma: no cover - integración con Plan 1 cuando exista
            from app.core.db import get_db_connection

            return get_db_connection()
        except ImportError:
            pass
    target = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_planting_db(conn: sqlite3.Connection) -> None:
    """Crea de forma idempotente las tablas del módulo de siembra y atribución."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS seed_personas (
            persona_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            alias TEXT NOT NULL,
            municipality_code TEXT NOT NULL,
            profile_note TEXT NOT NULL,
            synthetic INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS seed_copies (
            copy_id TEXT PRIMARY KEY,
            persona_id TEXT NOT NULL,
            persona_alias TEXT NOT NULL,
            provider TEXT NOT NULL,
            dataset_name TEXT NOT NULL,
            seed_period TEXT NOT NULL,
            trap_id TEXT NOT NULL,
            trap_display TEXT NOT NULL,
            channel_scope TEXT NOT NULL DEFAULT 'call|sms',
            synthetic INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (persona_id) REFERENCES seed_personas(persona_id)
        );

        CREATE TABLE IF NOT EXISTS trap_assignments (
            normalized_trap_id TEXT PRIMARY KEY,
            trap_id TEXT NOT NULL,
            trap_display TEXT NOT NULL,
            copy_id TEXT NOT NULL UNIQUE,
            seed_period TEXT NOT NULL,
            synthetic INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (copy_id) REFERENCES seed_copies(copy_id)
        );

        CREATE TABLE IF NOT EXISTS seed_manifests (
            seed_period TEXT PRIMARY KEY,
            manifest_hash TEXT NOT NULL,
            total_copies INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def export_seed_fixture(
    copies: list[SeedCopyRecord],
    manifest_hash: str,
    fixture_path: Optional[Path] = None,
) -> Path:
    """Guarda el fixture JSON compartido para escenarios e integrantes del equipo."""
    target = fixture_path or DEFAULT_FIXTURE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "synthetic": True,
        "manifest_hash": manifest_hash,
        "total_copies": len(copies),
        "copies": [copy.model_dump() for copy in copies],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def persist_batch(
    conn: sqlite3.Connection,
    personas: list[PersonaRecord],
    copies: list[SeedCopyRecord],
    manifest_hash: str,
    *,
    export_fixture: bool = True,
    fixture_path: Optional[Path] = None,
) -> SeedBatchSummary:
    """Persiste un lote de siembra en SQLite preservando el mapeo 1:1 copia <-> trampa."""
    init_planting_db(conn)
    for persona in personas:
        conn.execute(
            """
            INSERT OR REPLACE INTO seed_personas
            (persona_id, full_name, alias, municipality_code, profile_note, synthetic)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                persona.persona_id,
                persona.full_name,
                persona.alias,
                persona.municipality_code,
                persona.profile_note,
                1 if persona.synthetic else 0,
            ),
        )

    for copy in copies:
        norm = normalize_trap_id(copy.trap_id)
        conn.execute(
            """
            INSERT OR REPLACE INTO seed_copies
            (copy_id, persona_id, persona_alias, provider, dataset_name, seed_period, trap_id, trap_display, channel_scope, synthetic, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                copy.copy_id,
                copy.persona_id,
                copy.persona_alias,
                copy.provider,
                copy.dataset_name,
                copy.seed_period,
                copy.trap_id,
                copy.trap_display,
                copy.channel_scope,
                1 if copy.synthetic else 0,
                copy.created_at,
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO trap_assignments
            (normalized_trap_id, trap_id, trap_display, copy_id, seed_period, synthetic)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                norm,
                copy.trap_id,
                copy.trap_display,
                copy.copy_id,
                copy.seed_period,
                1 if copy.synthetic else 0,
            ),
        )

    all_copies = list_copies(conn)
    global_hash = compute_manifest_hash(all_copies)
    seed_period = copies[0].seed_period if copies else DEFAULT_PERIOD
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO seed_manifests (seed_period, manifest_hash, total_copies, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (seed_period, manifest_hash, len(copies), now_iso),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO seed_manifests (seed_period, manifest_hash, total_copies, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        ("GLOBAL", global_hash, len(all_copies), now_iso),
    )
    conn.commit()

    if export_fixture:
        export_seed_fixture(all_copies, global_hash, fixture_path=fixture_path)

    return SeedBatchSummary(
        seed_period=seed_period,
        total_copies=len(copies),
        manifest_hash=global_hash,
        synthetic=True,
        copies=copies,
    )


def seed_if_empty(
    conn: sqlite3.Connection,
    *,
    seed_period: str = DEFAULT_PERIOD,
    total_copies: int = 15,
    seed: int = DEFAULT_SEED,
    export_fixture: bool = True,
    fixture_path: Optional[Path] = None,
) -> SeedBatchSummary:
    """Siembra el lote determinista inicial solo si aún no hay copias registradas."""
    init_planting_db(conn)
    row = conn.execute("SELECT COUNT(*) AS total FROM seed_copies").fetchone()
    if row and row["total"] > 0:
        copies = list_copies(conn)
        return SeedBatchSummary(
            seed_period=seed_period,
            total_copies=len(copies),
            manifest_hash=get_manifest_hash(conn),
            synthetic=True,
            copies=copies,
        )

    personas, copies, manifest_hash = generate_synthetic_batch(
        seed_period=seed_period,
        total_copies=total_copies,
        seed=seed,
    )
    return persist_batch(
        conn,
        personas,
        copies,
        manifest_hash,
        export_fixture=export_fixture,
        fixture_path=fixture_path,
    )


def list_copies(conn: sqlite3.Connection, seed_period: Optional[str] = None) -> list[SeedCopyRecord]:
    """Devuelve las copias sembradas registradas en SQLite."""
    init_planting_db(conn)
    if seed_period:
        rows = conn.execute(
            "SELECT * FROM seed_copies WHERE seed_period = ? ORDER BY copy_id ASC",
            (seed_period,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM seed_copies ORDER BY seed_period ASC, copy_id ASC").fetchall()

    return [
        SeedCopyRecord(
            copy_id=row["copy_id"],
            persona_id=row["persona_id"],
            persona_alias=row["persona_alias"],
            provider=row["provider"],
            dataset_name=row["dataset_name"],
            seed_period=row["seed_period"],
            trap_id=row["trap_id"],
            trap_display=row["trap_display"],
            channel_scope=row["channel_scope"],
            synthetic=bool(row["synthetic"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_manifest_hash(conn: sqlite3.Connection) -> str:
    """Obtiene el hash SHA-256 vigente del manifiesto global de siembra."""
    init_planting_db(conn)
    row = conn.execute(
        "SELECT manifest_hash FROM seed_manifests WHERE seed_period = 'GLOBAL'"
    ).fetchone()
    if row:
        return str(row["manifest_hash"])
    return compute_manifest_hash(list_copies(conn))


def lookup_by_trap_id(conn: sqlite3.Connection, raw_trap_id: Optional[str]) -> Optional[sqlite3.Row]:
    """Busca la copia asignada a un número trampa receptor normalizado."""
    norm = normalize_trap_id(raw_trap_id)
    if not norm:
        return None
    init_planting_db(conn)
    return conn.execute(
        """
        SELECT
            ta.normalized_trap_id,
            ta.trap_id,
            ta.trap_display,
            sc.copy_id,
            sc.provider,
            sc.dataset_name,
            sc.seed_period,
            sc.persona_alias,
            sc.synthetic
        FROM trap_assignments ta
        JOIN seed_copies sc ON sc.copy_id = ta.copy_id
        WHERE ta.normalized_trap_id = ?
        """,
        (norm,),
    ).fetchone()
