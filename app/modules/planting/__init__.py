"""Módulo de siembra sintética y atribución de fugas (Plan 2)."""

from app.modules.planting.router import get_routers, register_routes, router
from app.modules.planting.schemas import AttributionResult, PersonaRecord, SeedBatchSummary, SeedCopyRecord
from app.modules.planting.service import (
    attribute,
    ensure_seeded,
    get_seed_manifest_hash,
    get_seeded_copies,
    reseed_period,
)

__all__ = [
    "AttributionResult",
    "PersonaRecord",
    "SeedBatchSummary",
    "SeedCopyRecord",
    "attribute",
    "ensure_seeded",
    "get_routers",
    "get_seed_manifest_hash",
    "get_seeded_copies",
    "register_routes",
    "reseed_period",
    "router",
]
