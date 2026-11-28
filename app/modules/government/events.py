"""Bus en memoria de eventos sanitizados para las pantallas de demo."""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_events: deque[dict[str, Any]] = deque(maxlen=300)
_next_id = 1
_active_call: dict[str, Any] | None = None
_latest_call: dict[str, Any] | None = None


def publish_event(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Audio y transcripción íntegra no deben entrar a este bus."""
    global _next_id, _active_call, _latest_call
    with _lock:
        event = {
            "id": _next_id,
            "kind": kind,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        json.dumps(event, ensure_ascii=False)
        _events.append(event)
        _next_id += 1
        if kind == "call.started":
            _active_call = event
            _latest_call = event
        elif kind in {"call.turn", "call.indicator", "call.attribution", "call.partial"}:
            _latest_call = event
        elif kind == "call.ended":
            _latest_call = event
            _active_call = None
        return dict(event)


def events_after(event_id: int = 0) -> list[dict[str, Any]]:
    with _lock:
        return [dict(event) for event in _events if int(event["id"]) > event_id]


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "active_call": dict(_active_call) if _active_call else None,
            "latest_call": dict(_latest_call) if _latest_call else None,
            "events": [dict(event) for event in list(_events)[-80:]],
            "last_event_id": _next_id - 1,
        }


def latest_event_for_report(event_id: str) -> dict[str, Any] | None:
    with _lock:
        for event in reversed(_events):
            if event.get("call_id") == event_id or event.get("event_id") == event_id:
                return dict(event)
    return None
