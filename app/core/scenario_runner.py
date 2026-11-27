import time
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
    return [
        Scenario.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


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

