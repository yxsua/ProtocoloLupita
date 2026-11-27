import sqlite3
from contextlib import contextmanager
import json
from pathlib import Path
from typing import Iterator

from app.core.config import DATABASE_PATH
from app.core.schemas import Campaign, Event, Indicator, ScenarioResult


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    channel TEXT NOT NULL,
    trap_id TEXT,
    attribution_id TEXT,
    campaign_id TEXT,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_hash TEXT,
    municipality_id TEXT,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic IN (0, 1))
);
CREATE TABLE IF NOT EXISTS indicators (
    indicator_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    value_masked TEXT NOT NULL,
    value_fingerprint TEXT,
    source_event_id TEXT NOT NULL REFERENCES events(event_id),
    confidence TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    brand TEXT,
    scam_type TEXT,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS scenario_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id TEXT NOT NULL,
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    expected_json TEXT NOT NULL,
    actual_json TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    ran_at TEXT NOT NULL
);
"""


def connect(database_path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: Path | str = DATABASE_PATH) -> None:
    connection = connect(database_path)
    try:
        connection.executescript(SCHEMA)
    finally:
        connection.close()


def save_event(event: Event, database_path: Path | str = DATABASE_PATH) -> None:
    with database(database_path) as connection:
        connection.execute(
            """INSERT INTO events
               (event_id, occurred_at, channel, trap_id, attribution_id, campaign_id,
                confidence, status, evidence_hash, municipality_id, synthetic)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(event_id) DO UPDATE SET
                occurred_at=excluded.occurred_at, channel=excluded.channel,
                trap_id=excluded.trap_id, attribution_id=excluded.attribution_id,
                campaign_id=excluded.campaign_id, confidence=excluded.confidence,
                status=excluded.status, evidence_hash=excluded.evidence_hash,
                municipality_id=excluded.municipality_id, synthetic=excluded.synthetic""",
            (event.event_id, event.occurred_at.isoformat(), event.channel.value,
             event.trap_id, event.attribution_id, event.campaign_id,
             event.confidence.value, event.status.value, event.evidence_hash,
             event.municipality_id, int(event.synthetic)),
        )


def save_indicator(indicator: Indicator, database_path: Path | str = DATABASE_PATH) -> None:
    with database(database_path) as connection:
        connection.execute(
            """INSERT INTO indicators
               (indicator_id, kind, value_masked, value_fingerprint, source_event_id,
                confidence, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(indicator_id) DO UPDATE SET
                kind=excluded.kind, value_masked=excluded.value_masked,
                value_fingerprint=excluded.value_fingerprint,
                source_event_id=excluded.source_event_id,
                confidence=excluded.confidence, status=excluded.status""",
            (indicator.indicator_id, indicator.kind, indicator.value_masked,
             indicator.value_fingerprint, indicator.source_event_id,
             indicator.confidence.value, indicator.status.value),
        )


def save_campaign(campaign: Campaign, database_path: Path | str = DATABASE_PATH) -> None:
    with database(database_path) as connection:
        connection.execute(
            """INSERT INTO campaigns
               (campaign_id, title, brand, scam_type, confidence, status,
                first_seen, last_seen, event_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(campaign_id) DO UPDATE SET
                title=excluded.title, brand=excluded.brand, scam_type=excluded.scam_type,
                confidence=excluded.confidence, status=excluded.status,
                first_seen=excluded.first_seen, last_seen=excluded.last_seen,
                event_count=excluded.event_count""",
            (campaign.campaign_id, campaign.title, campaign.brand, campaign.scam_type,
             campaign.confidence.value, campaign.status.value,
             campaign.first_seen.isoformat(), campaign.last_seen.isoformat(),
             campaign.event_count),
        )


def record_scenario_result(result: ScenarioResult,
                           database_path: Path | str = DATABASE_PATH) -> None:
    with database(database_path) as connection:
        connection.execute(
            "INSERT INTO scenario_runs "
            "(scenario_id, passed, expected_json, actual_json, duration_ms, ran_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (result.scenario_id, int(result.passed),
             json.dumps(result.expected, ensure_ascii=False),
             json.dumps(result.actual, ensure_ascii=False),
             result.duration_ms, result.ran_at.isoformat()),
        )


def reset_demo_data(database_path: Path | str = DATABASE_PATH) -> None:
    """Clear generated activity while preserving seeded trap-to-copy mappings."""
    with database(database_path) as connection:
        connection.execute("DELETE FROM indicators")
        connection.execute("DELETE FROM events")
        connection.execute("DELETE FROM campaigns")
        connection.execute("DELETE FROM scenario_runs")


def list_scenario_results(limit: int = 100,
                          database_path: Path | str = DATABASE_PATH) -> list[dict]:
    with database(database_path) as connection:
        rows = connection.execute(
            "SELECT scenario_id, passed, expected_json, actual_json, duration_ms, ran_at "
            "FROM scenario_runs ORDER BY run_id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        {"scenario_id": row["scenario_id"], "passed": bool(row["passed"]),
         "expected": json.loads(row["expected_json"]),
         "actual": json.loads(row["actual_json"]),
         "duration_ms": row["duration_ms"], "ran_at": row["ran_at"]}
        for row in rows
    ]


@contextmanager
def database(database_path: Path | str = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    connection = connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

