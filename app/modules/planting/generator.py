"""Generador determinista de personajes y copias sembradas con Faker('es_MX')."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from typing import Iterable

from faker import Faker

from app.modules.planting.fixtures_local import CORE_SCENARIO_SEEDS, QUERETARO_MUNICIPALITIES
from app.modules.planting.schemas import PersonaRecord, SeedCopyRecord


DEFAULT_SEED = 2026
DEFAULT_PERIOD = "2026-10"
DEFAULT_PROVIDERS = ("Proveedor A", "Proveedor B", "Proveedor C", "Proveedor D")
DEFAULT_DATASETS = (
    "padrón predial",
    "programas sociales",
    "padrón licencias",
    "ventanilla trámites",
)


def compute_manifest_hash(copies: Iterable[SeedCopyRecord]) -> str:
    """Calcula un SHA-256 determinista del mapeo copia <-> número trampa."""
    canonical = [
        {
            "copy_id": item.copy_id,
            "provider": item.provider,
            "dataset_name": item.dataset_name,
            "seed_period": item.seed_period,
            "trap_id": item.trap_id,
            "synthetic": item.synthetic,
        }
        for item in sorted(copies, key=lambda c: (c.seed_period, c.copy_id))
    ]
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def generate_synthetic_batch(
    *,
    seed_period: str = DEFAULT_PERIOD,
    total_copies: int = 15,
    seed: int = DEFAULT_SEED,
    include_core_scenarios: bool = True,
) -> tuple[list[PersonaRecord], list[SeedCopyRecord], str]:
    """Genera un lote determinista de personajes y copias asociadas 1:1 a trampas +52 442."""
    if total_copies < 1:
        raise ValueError("total_copies debe ser al menos 1")

    faker = Faker("es_MX")
    faker.seed_instance(seed)
    rng = random.Random(seed)
    timestamp = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc).isoformat()

    personas: list[PersonaRecord] = []
    copies: list[SeedCopyRecord] = []
    used_numbers: set[str] = set()
    period_slug = seed_period.replace(" ", "-")

    if include_core_scenarios and seed_period == DEFAULT_PERIOD:
        for idx, base in enumerate(CORE_SCENARIO_SEEDS, start=1):
            if len(copies) >= total_copies:
                break
            persona_id = f"PER-{period_slug}-{idx:03d}"
            full_name = faker.name()
            personas.append(
                PersonaRecord(
                    persona_id=persona_id,
                    full_name=full_name,
                    alias=base["persona_alias"],
                    municipality_code=base["municipality_code"],
                    profile_note=base["profile_note"],
                    synthetic=True,
                )
            )
            copies.append(
                SeedCopyRecord(
                    copy_id=base["copy_id"],
                    persona_id=persona_id,
                    persona_alias=base["persona_alias"],
                    provider=base["provider"],
                    dataset_name=base["dataset_name"],
                    seed_period=seed_period,
                    trap_id=base["trap_id"],
                    trap_display=base["trap_display"],
                    channel_scope="call|sms",
                    synthetic=True,
                    created_at=timestamp,
                )
            )
            used_numbers.add(base["trap_id"])

    counter = len(copies) + 1
    while len(copies) < total_copies:
        muni = QUERETARO_MUNICIPALITIES[(counter - 1) % len(QUERETARO_MUNICIPALITIES)]
        provider = DEFAULT_PROVIDERS[(counter - 1) % len(DEFAULT_PROVIDERS)]
        dataset = DEFAULT_DATASETS[(counter - 1) % len(DEFAULT_DATASETS)]

        suffix = 100 + counter + (0 if seed_period == DEFAULT_PERIOD else rng.randint(200, 899))
        while True:
            trap_id = f"+52 442 000 {suffix:04d}"
            if trap_id not in used_numbers:
                used_numbers.add(trap_id)
                break
            suffix += 1

        full_name = faker.name()
        first_name = full_name.split()[0]
        alias = f"{first_name} ({muni['municipality_name']})"
        persona_id = f"PER-{period_slug}-{counter:03d}"
        copy_id = f"COPY-{period_slug}-{counter:03d}"

        personas.append(
            PersonaRecord(
                persona_id=persona_id,
                full_name=full_name,
                alias=alias,
                municipality_code=muni["municipality_code"],
                profile_note=f"Señuelo sintético en {dataset} ({muni['municipality_name']})",
                synthetic=True,
            )
        )
        copies.append(
            SeedCopyRecord(
                copy_id=copy_id,
                persona_id=persona_id,
                persona_alias=alias,
                provider=provider,
                dataset_name=dataset,
                seed_period=seed_period,
                trap_id=trap_id,
                trap_display=f"+52 442 XXX {suffix:04d} (ficticio)",
                channel_scope="call|sms",
                synthetic=True,
                created_at=timestamp,
            )
        )
        counter += 1

    manifest_hash = compute_manifest_hash(copies)
    return personas, copies, manifest_hash
