"""Fixtures locales deterministas y catálogo oficial de los 18 municipios de Querétaro.

Permiten que los módulos ``planting``, ``dashboard`` y ``map`` funcionen de manera
independiente antes de conectar los módulos de los demás integrantes.
"""

from __future__ import annotations

QUERETARO_MUNICIPALITIES: list[dict[str, str]] = [
    {"municipality_code": "22001", "municipality_name": "Amealco de Bonfil"},
    {"municipality_code": "22002", "municipality_name": "Pinal de Amoles"},
    {"municipality_code": "22003", "municipality_name": "Arroyo Seco"},
    {"municipality_code": "22004", "municipality_name": "Cadereyta de Montes"},
    {"municipality_code": "22005", "municipality_name": "Colón"},
    {"municipality_code": "22006", "municipality_name": "Corregidora"},
    {"municipality_code": "22007", "municipality_name": "Ezequiel Montes"},
    {"municipality_code": "22008", "municipality_name": "Huimilpan"},
    {"municipality_code": "22009", "municipality_name": "Jalpan de Serra"},
    {"municipality_code": "22010", "municipality_name": "Landa de Matamoros"},
    {"municipality_code": "22011", "municipality_name": "El Marqués"},
    {"municipality_code": "22012", "municipality_name": "Pedro Escobedo"},
    {"municipality_code": "22013", "municipality_name": "Peñamiller"},
    {"municipality_code": "22014", "municipality_name": "Querétaro"},
    {"municipality_code": "22015", "municipality_name": "San Joaquín"},
    {"municipality_code": "22016", "municipality_name": "San Juan del Río"},
    {"municipality_code": "22017", "municipality_name": "Tequisquiapan"},
    {"municipality_code": "22018", "municipality_name": "Tolimán"},
]

# Copias semilla clave alineadas con los escenarios E01–E14 (100% ficticias).
CORE_SCENARIO_SEEDS: list[dict[str, str]] = [
    {
        "copy_id": "COPY-2026-10-001",
        "provider": "Proveedor A",
        "dataset_name": "padrón predial",
        "seed_period": "2026-10",
        "trap_id": "+52 442 000 0101",
        "trap_display": "+52 442 XXX 0101 (ficticio)",
        "persona_alias": "Don Ramiro",
        "municipality_code": "22014",
        "profile_note": "Escenario E01 — cobro de piso (ficticio)",
    },
    {
        "copy_id": "COPY-2026-10-002",
        "provider": "Proveedor B",
        "dataset_name": "programas sociales",
        "seed_period": "2026-10",
        "trap_id": "+52 442 000 0102",
        "trap_display": "+52 442 XXX 0102 (ficticio)",
        "persona_alias": "Doña Lupita",
        "municipality_code": "22006",
        "profile_note": "Escenarios E02–E07 y E09 — voz y SMS (ficticio)",
    },
    {
        "copy_id": "COPY-2026-10-003",
        "provider": "Proveedor C",
        "dataset_name": "padrón licencias",
        "seed_period": "2026-10",
        "trap_id": "+52 442 000 0103",
        "trap_display": "+52 442 XXX 0103 (ficticio)",
        "persona_alias": "Sra. Esperanza",
        "municipality_code": "22011",
        "profile_note": "Escenarios E08, E10 y E11 — llamadas/SMS (ficticio)",
    },
]

SAMPLE_INDICATORS: dict[str, dict[str, str]] = {
    "IND-001": {
        "id": "IND-001",
        "type": "clabe",
        "value_masked": "999180******0012 (sintética)",
        "confidence": "alta",
        "status": "corroborado",
    },
    "IND-002": {
        "id": "IND-002",
        "type": "dominio",
        "value_masked": "hxxp://sat-devolucion-qro[.]sim (no abierto)",
        "confidence": "media",
        "status": "indicio",
    },
    "IND-003": {
        "id": "IND-003",
        "type": "acortador",
        "value_masked": "hxxp://paq-qro[.]sim/r/9x (no abierto)",
        "confidence": "baja",
        "status": "indicio",
    },
    "IND-004": {
        "id": "IND-004",
        "type": "telefono_reportado",
        "value_masked": "+52 442 *** 8899 (tasa excedida)",
        "confidence": "baja",
        "status": "sin_verificar",
    },
}

SAMPLE_CAMPAIGNS: list[dict[str, object]] = [
    {
        "campaign_id": "CAMP-EXT-01",
        "title": "Extorsión telefónica con cobro por CLABE sintética 999",
        "brand": "Cobro de piso / falso grupo",
        "channels": ["call", "portal"],
        "event_count": 2,
        "traps_reached_count": 1,
        "script_variants": ["cobro_de_piso_v1"],
        "first_trap_contact_at": "2026-11-27T08:00:00-06:00",
        "first_citizen_report_at": "2026-11-27T14:30:00-06:00",
        "lead_time_hours": 6.5,
        "confidence": "alta",
        "status": "corroborado",
        "indicator_ids": ["IND-001"],
    },
    {
        "campaign_id": "CAMP-SAT-02",
        "title": "Smishing suplantando devolución del SAT",
        "brand": "SAT (suplantación)",
        "channels": ["sms"],
        "event_count": 1,
        "traps_reached_count": 1,
        "script_variants": ["sat_devolucion_sms_v1"],
        "first_trap_contact_at": "2026-11-27T10:15:00-06:00",
        "first_citizen_report_at": None,
        "lead_time_hours": None,
        "confidence": "media",
        "status": "indicio",
        "indicator_ids": ["IND-002"],
    },
    {
        "campaign_id": "CAMP-SINVER-03",
        "title": "Reportes repetidos sujetos a límite de tasa",
        "brand": "Comercio local (sin verificar)",
        "channels": ["portal"],
        "event_count": 1,
        "traps_reached_count": 0,
        "script_variants": ["reporte_masivo_tasa_excedida"],
        "first_trap_contact_at": None,
        "first_citizen_report_at": "2026-11-27T16:10:00-06:00",
        "lead_time_hours": None,
        "confidence": "baja",
        "status": "sin_verificar",
        "indicator_ids": ["IND-004"],
    },
]

SAMPLE_EVENTS: list[dict[str, object]] = [
    {
        "id": "EVT-E01",
        "occurred_at": "2026-11-27T08:00:00-06:00",
        "channel": "call",
        "trap_id": "+52 442 XXX 0101 (ficticio)",
        "attribution_id": "COPY-2026-10-001",
        "indicator_ids": ["IND-001"],
        "campaign_id": "CAMP-EXT-01",
        "confidence": "baja",
        "status": "indicio",
        "evidence_hash": "sha256:9f82c1d0e4a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456",
    },
    {
        "id": "EVT-E09",
        "occurred_at": "2026-11-27T10:15:00-06:00",
        "channel": "sms",
        "trap_id": "+52 442 000 0102",
        "attribution_id": "COPY-2026-10-002",
        "indicator_ids": ["IND-002"],
        "campaign_id": "CAMP-SAT-02",
        "confidence": "media",
        "status": "indicio",
        "evidence_hash": "sha256:4b3a2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b",
    },
    {
        "id": "EVT-E12",
        "occurred_at": "2026-11-27T14:30:00-06:00",
        "channel": "portal",
        "trap_id": None,
        "attribution_id": None,
        "indicator_ids": ["IND-001"],
        "campaign_id": "CAMP-EXT-01",
        "confidence": "alta",
        "status": "corroborado",
        "evidence_hash": "sha256:7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d",
    },
    {
        "id": "EVT-E14",
        "occurred_at": "2026-11-27T16:10:00-06:00",
        "channel": "portal",
        "trap_id": None,
        "attribution_id": None,
        "indicator_ids": ["IND-004"],
        "campaign_id": "CAMP-SINVER-03",
        "confidence": "baja",
        "status": "sin_verificar",
        "evidence_hash": "sha256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b",
    },
]

# Reportes municipales saneados de muestra para demostrar E13 (umbral >= 5) y E14.
SAMPLE_MUNICIPAL_REPORTS: list[dict[str, object]] = [
    {"municipality_code": "22014", "count": 14, "rate_limited_excluded": 0},
    {"municipality_code": "22006", "count": 7, "rate_limited_excluded": 0},
    {"municipality_code": "22011", "count": 6, "rate_limited_excluded": 0},
    {"municipality_code": "22016", "count": 5, "rate_limited_excluded": 0},
    # E13: municipio con 3 reportes (< 5) — suprimido individualmente pero suma al total estatal
    {"municipality_code": "22017", "count": 3, "rate_limited_excluded": 0},
    # E14: reportes bloqueados por límite de tasa (no inflan conteos válidos)
    {"municipality_code": "22012", "count": 0, "rate_limited_excluded": 20},
]
