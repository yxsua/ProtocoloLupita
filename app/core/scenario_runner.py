import time
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.core.config import SCENARIOS_DIR
from app.core.db import record_scenario_result
from app.core.schemas import Channel, Scenario, ScenarioResult


ScenarioHandler = Callable[[Scenario], dict[str, Any]]
_handlers: dict[Channel, ScenarioHandler] = {}


def register_handler(channel: Channel, handler: ScenarioHandler) -> None:
    """Register the service that exercises a scenario for one channel."""
    _handlers[channel] = handler


def list_scenarios(directory: Path = SCENARIOS_DIR) -> list[Scenario]:
    if not directory.exists():
        return []

    def read_rows(filename: str) -> list[dict[str, Any]]:
        path = directory / filename
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("scenarios", [payload]) if isinstance(payload, dict) else payload
        return [row for row in rows if isinstance(row, dict)]

    call_events = {row["id"]: row for row in read_rows("e01_e08_calls.json") if row.get("id")}
    voice_rows = {row["id"]: row for row in read_rows("e01_e08_voice.json") if row.get("id")}
    sms_events = {row["id"]: row for row in read_rows("e09_e11_sms.json") if row.get("id")}
    correlation = {row["id"]: row for row in read_rows("correlation_fixtures.json") if row.get("id")}

    details: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("E*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = payload.get("scenario_id")
        if scenario_id:
            details[str(scenario_id)] = payload

    scenarios: list[Scenario] = []
    for number in range(1, 15):
        scenario_id = f"E{number:02d}"
        event = call_events.get(scenario_id) or sms_events.get(scenario_id) or correlation.get(scenario_id)
        voice = voice_rows.get(scenario_id)
        detail = details.get(scenario_id)
        if event is None and detail is None:
            continue

        raw_channel = (event or {}).get("channel") or (detail or {}).get("type", "portal")
        channel_aliases = {
            "citizen_report": "portal",
            "citizen_rate_limit": "portal",
            "map_aggregate": "portal",
        }
        channel = channel_aliases.get(raw_channel, raw_channel)
        if channel not in {"call", "sms", "portal"}:
            continue

        if channel == "call":
            scenario_input = {"event": event or {}, "turns": (voice or {}).get("input", [])}
            expected = {
                "intelligence": (event or {}).get("expected", {}),
                "voice": (voice or {}).get("expected", {}),
            }
        elif channel == "sms":
            scenario_input = {"event": event or {}, "sms": (detail or {}).get("input", {})}
            expected = {
                "intelligence": (event or {}).get("expected", {}),
                "sms": (detail or {}).get("expected", {}),
            }
        else:
            scenario_input = {
                "event": event or {},
                "report": (detail or {}).get("input", {}),
                "inputs": (detail or {}).get("inputs", []),
                "repeat_count": (detail or {}).get("repeat_count"),
            }
            expected = {
                "intelligence": (event or {}).get("expected", {}),
                "citizen_or_map": (detail or {}).get("expected", {}),
            }

        scenarios.append(Scenario(
            id=scenario_id,
            channel=channel,
            trap_id=(event or {}).get("trap_id") or (detail or {}).get("input", {}).get("trap_id"),
            input=scenario_input,
            expected=expected,
        ))
    return scenarios


def _matches(expected: Any, actual: Any) -> bool:
    """Compare expected JSON as a recursive subset of the actual result."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _matches(value, actual[key])
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(
            _matches(left, right) for left, right in zip(expected, actual)
        )
    return expected == actual


def run_scenario(scenario: Scenario) -> ScenarioResult:
    handler = _handlers.get(scenario.channel)
    started = time.perf_counter()
    if handler is None:
        actual: dict[str, Any] = {"error": f"No handler registered for {scenario.channel.value}"}
    else:
        try:
            actual = handler(scenario)
        except Exception as exc:  # Do not persist exception text from untrusted input.
            actual = {"error": "handler_failed", "error_type": type(exc).__name__}
    duration_ms = (time.perf_counter() - started) * 1000
    result = ScenarioResult(
        scenario_id=scenario.id,
        passed=handler is not None and _matches(scenario.expected, actual),
        expected=scenario.expected,
        actual=actual,
        duration_ms=duration_ms,
        ran_at=datetime.now(timezone.utc),
    )
    record_scenario_result(result)
    return result


def run_all_scenarios() -> list[ScenarioResult]:
    return [run_scenario(scenario) for scenario in list_scenarios()]

