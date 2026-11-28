"""Acceptance journey for the private two-screen call simulation."""

from __future__ import annotations

from collections import deque
import base64
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core import db
from app.main import app
from app.modules.government import events
from app.modules.government import router as government_router
from app.modules.voice import router as voice_router


class _DemoIntelEngine:
    """Keep this acceptance check deterministic and independent of external models."""

    def process_event(self, _event):
        return SimpleNamespace(
            indicators=[],
            campaign_id="campaign-acceptance-demo",
            status="indicio",
            confidence_level="baja",
            confidence=0.2,
            threat_category="extorsion_simulada",
            evidence_hash="sha256:acceptance-demo",
        )


def test_private_two_screen_call_remains_queryable_after_hangup(
    monkeypatch, tmp_path
):
    """Run a fixture call on one client and verify it from the government screen."""
    username = "acceptance-government"
    password = "local-demo-secret"
    monkeypatch.setenv("GOV_PANEL_USERNAME", username)
    monkeypatch.setenv("GOV_PANEL_PASSWORD", password)

    database_path = tmp_path / "acceptance.sqlite3"
    db.initialize_database(database_path)
    record_report = db.record_government_report
    get_report = db.get_government_report
    list_reports = db.list_government_reports

    def save_report(**kwargs):
        record_report(**kwargs, database_path=database_path)

    monkeypatch.setattr(voice_router, "record_government_report", save_report)
    monkeypatch.setattr(government_router, "record_government_report", save_report)
    monkeypatch.setattr(
        government_router,
        "get_government_report",
        lambda report_id: get_report(report_id, database_path=database_path),
    )
    monkeypatch.setattr(
        government_router,
        "list_government_reports",
        lambda **kwargs: list_reports(**kwargs, database_path=database_path),
    )
    monkeypatch.setattr(voice_router, "get_default_engine", _DemoIntelEngine)

    # Isolate in-memory call/event state from other tests and local activity.
    monkeypatch.setattr(voice_router, "_sessions", {})
    monkeypatch.setattr(voice_router, "_call_metadata", {})
    monkeypatch.setattr(voice_router, "_scenario_runs", {})
    monkeypatch.setattr(events, "_events", deque(maxlen=300))
    monkeypatch.setattr(events, "_next_id", 1)
    monkeypatch.setattr(events, "_active_call", None)
    monkeypatch.setattr(events, "_latest_call", None)

    authorization = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    with (
        TestClient(app) as simulator_screen,
        TestClient(app) as government_screen,
    ):
        assert government_screen.get("/gobierno").status_code == 401
        assert simulator_screen.post(
            "/voice/scenario/start", data={"scenario_id": "E01"}
        ).status_code == 401
        simulator_screen.headers["Authorization"] = authorization
        government_screen.headers["Authorization"] = authorization
        simulator = simulator_screen.get("/gobierno/simulador")
        dashboard = government_screen.get("/gobierno")
        assert simulator.status_code == 200
        assert "simulator" in simulator.text
        assert dashboard.status_code == 200
        assert "call-timeline" in dashboard.text

        start = simulator_screen.post("/voice/scenario/start", data={"scenario_id": "E01"})
        assert start.status_code == 200, start.text
        call = start.json()
        session_id = call["session_id"]
        assert call["turn_count"] >= 3

        started_snapshot = government_screen.get("/api/gobierno/snapshot").json()
        assert any(
            event.get("kind") == "call.started" and event.get("call_id") == session_id
            for event in started_snapshot["events"]
        )

        for _ in range(call["turn_count"]):
            turn = simulator_screen.post(
                "/voice/scenario/next", data={"session_id": session_id}
            )
            assert turn.status_code == 200, turn.text
            turn_data = turn.json()
            assert turn_data.get("attacker_line")
            assert turn_data.get("victim_line")
            live_snapshot = government_screen.get("/api/gobierno/snapshot").json()
            live_turns = [
                event for event in live_snapshot["events"]
                if event.get("kind") == "call.turn" and event.get("call_id") == session_id
            ]
            assert live_turns
            assert live_turns[-1]["transcript"] == turn_data["attacker_line"]
            assert live_turns[-1]["agent_response"] == turn_data["victim_line"]

        ended_snapshot = government_screen.get("/api/gobierno/snapshot").json()
        ended = [
            event for event in ended_snapshot["events"]
            if event.get("kind") == "call.ended" and event.get("call_id") == session_id
        ]
        assert ended

        # The separate reports screen sees the saved record after the call ends.
        history = government_screen.get("/api/gobierno/reportes-guardados").json()
        assert any(row["report_id"] == session_id for row in history["items"])

        # Simulate loss/rotation of the in-memory event bus; the saved report must
        # remain available from SQLite, including the sanitized full conversation.
        events._events.clear()
        events._latest_call = None
        persisted = government_screen.get(f"/api/gobierno/reportes/{session_id}")
        assert persisted.status_code == 200, persisted.text
        report = persisted.json()["report"]
        assert report["report_id"] == session_id
        assert report["synthetic"] is True
        transcript = report["details"]["transcript"]
        assert len(transcript) >= 7
        assert {line["speaker"] for line in transcript} == {"atacante", "victima"}
        assert "012180001122334451" not in persisted.text

        exported = government_screen.post(
            f"/api/gobierno/reportes/{session_id}/borrador"
        )
        assert exported.status_code == 200, exported.text
        assert exported.json()["report"]["details"]["draft_status"] == "borrador_exportado"
        assert exported.json()["synthetic_demo"] is True

