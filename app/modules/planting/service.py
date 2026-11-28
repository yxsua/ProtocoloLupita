"""Servicio público de siembra y atribución por número trampa receptor."""

from __future__ import annotations

from pathlib import Path
import secrets
from typing import Optional

from app.modules.planting.generator import DEFAULT_PERIOD, DEFAULT_SEED, generate_synthetic_batch
from app.modules.planting.repository import (
    get_connection,
    get_manifest_hash,
    list_copies,
    list_seed_batches,
    lookup_by_trap_id,
    normalize_trap_id,
    persist_batch,
    seed_period_exists,
    seed_if_empty,
)
from app.modules.planting.schemas import AttributionResult, SeedBatchListItem, SeedBatchSummary, SeedCopyRecord


def ensure_seeded(db_path: Optional[str | Path] = None) -> SeedBatchSummary:
    """Garantiza que exista la siembra determinista inicial y su fixture JSON."""
    conn = get_connection(db_path)
    try:
        return seed_if_empty(conn)
    finally:
        conn.close()


def reseed_period(
    *,
    seed_period: str = DEFAULT_PERIOD,
    total_copies: int = 15,
    seed: int = DEFAULT_SEED,
    db_path: Optional[str | Path] = None,
) -> SeedBatchSummary:
    """Genera o actualiza un lote determinista para un periodo dado."""
    conn = get_connection(db_path)
    try:
        personas, copies, manifest_hash = generate_synthetic_batch(
            seed_period=seed_period,
            total_copies=total_copies,
            seed=seed,
        )
        return persist_batch(conn, personas, copies, manifest_hash)
    finally:
        conn.close()


def create_seed_batch(
    *,
    seed_period: str,
    total_copies: int = 3,
    db_path: Optional[str | Path] = None,
) -> SeedBatchListItem:
    """Crea un lote nuevo e inmutable; cada número queda único entre todos los lotes."""
    conn = get_connection(db_path)
    try:
        if seed_period_exists(conn, seed_period):
            raise ValueError("Ya existe un lote con ese identificador. Elige otro para conservar la atribución anterior.")

        used_traps = {
            normalize_trap_id(copy.trap_id)
            for copy in list_copies(conn)
        }
        for _ in range(100):
            personas, copies, manifest_hash = generate_synthetic_batch(
                seed_period=seed_period,
                total_copies=total_copies,
                seed=secrets.randbits(31),
                include_core_scenarios=False,
            )
            new_traps = {normalize_trap_id(copy.trap_id) for copy in copies}
            if len(new_traps) == len(copies) and not (new_traps & used_traps):
                break
        else:
            raise RuntimeError("No se pudieron asignar números trampa únicos para este lote.")

        persist_batch(conn, personas, copies, manifest_hash)
        batch = next(
            item for item in list_seed_batches(conn)
            if item["seed_period"] == seed_period
        )
        return SeedBatchListItem(**batch)
    finally:
        conn.close()


def get_seed_batches(db_path: Optional[str | Path] = None) -> list[SeedBatchListItem]:
    """Lista lotes disponibles sin exponer números trampa."""
    conn = get_connection(db_path)
    try:
        seed_if_empty(conn)
        return [SeedBatchListItem(**item) for item in list_seed_batches(conn)]
    finally:
        conn.close()


def get_batch_copies(
    seed_period: str,
    db_path: Optional[str | Path] = None,
) -> list[SeedCopyRecord]:
    """Obtiene el mapa interno de una sola copia sembrada para su exportación protegida."""
    conn = get_connection(db_path)
    try:
        return list_copies(conn, seed_period=seed_period)
    finally:
        conn.close()


def get_seed_manifest_hash(db_path: Optional[str | Path] = None) -> str:
    """Devuelve el hash público SHA-256 del manifiesto de siembra."""
    conn = get_connection(db_path)
    try:
        seed_if_empty(conn)
        return get_manifest_hash(conn)
    finally:
        conn.close()


def get_seeded_copies(
    *,
    seed_period: Optional[str] = None,
    db_path: Optional[str | Path] = None,
) -> list[SeedCopyRecord]:
    """Lista las copias sembradas (para uso interno de Contraloría / tablero)."""
    conn = get_connection(db_path)
    try:
        seed_if_empty(conn)
        return list_copies(conn, seed_period=seed_period)
    finally:
        conn.close()


def attribute(
    trap_id: Optional[str],
    *,
    db_path: Optional[str | Path] = None,
) -> AttributionResult:
    """Atribuye exclusivamente por el número trampa receptor.

    Nunca deduce identidad por número de origen. Si ``trap_id`` es nulo,
    vacío o desconocido, devuelve ``status="no_atribuido"`` de forma segura.
    """
    raw_value = (trap_id or "").strip()
    norm = normalize_trap_id(raw_value)

    conn = get_connection(db_path)
    try:
        seed_if_empty(conn)
        manifest_hash = get_manifest_hash(conn)
        if not norm:
            return AttributionResult(
                trap_id=raw_value,
                copy_id=None,
                provider=None,
                seed_period=None,
                synthetic=True,
                attribution_id=None,
                manifest_hash=manifest_hash,
                status="no_atribuido",
                trap_display="Sin número trampa",
            )

        row = lookup_by_trap_id(conn, raw_value)
        if row is None:
            return AttributionResult(
                trap_id=raw_value,
                copy_id=None,
                provider=None,
                seed_period=None,
                synthetic=True,
                attribution_id=None,
                manifest_hash=manifest_hash,
                status="no_atribuido",
                trap_display=f"{raw_value} (no sembrado)",
            )

        provider_full = f"{row['provider']} - {row['dataset_name']} - {row['seed_period']}"
        return AttributionResult(
            trap_id=row["trap_id"],
            copy_id=row["copy_id"],
            provider=provider_full,
            seed_period=row["seed_period"],
            synthetic=bool(row["synthetic"]),
            attribution_id=row["copy_id"],
            manifest_hash=manifest_hash,
            status="atribuido",
            trap_display=row["trap_display"],
            persona_alias=row["persona_alias"],
            source_dataset=row["dataset_name"],
        )
    finally:
        conn.close()
