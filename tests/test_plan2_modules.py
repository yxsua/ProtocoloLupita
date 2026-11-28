"""Pruebas unitarias e integración local de Plan 2 (siembra, atribución, tablero y mapa)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.modules.dashboard import get_dashboard, register_routes as register_dashboard_routes
from app.modules.map import get_map_summary, load_queretaro_geojson, register_routes as register_map_routes
from app.modules.planting import attribute, ensure_seeded, get_seed_manifest_hash, register_routes as register_planting_routes
from app.modules.planting.generator import generate_synthetic_batch


def _build_test_app() -> FastAPI:
    app = FastAPI()
    static_dir = Path(__file__).resolve().parents[1] / "app" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    register_planting_routes(app)
    register_dashboard_routes(app)
    register_map_routes(app)
    return app


def test_deterministic_seeding_and_manifest_hash(tmp_path: Path) -> None:
    db_file = tmp_path / "test_seed.db"
    _, copies_a, hash_a = generate_synthetic_batch(seed_period="2026-10", total_copies=15, seed=2026)
    _, copies_b, hash_b = generate_synthetic_batch(seed_period="2026-10", total_copies=15, seed=2026)

    assert len(copies_a) == 15
    assert hash_a == hash_b
    assert [c.model_dump() for c in copies_a] == [c.model_dump() for c in copies_b]
    assert all(c.synthetic for c in copies_a)
    assert len({c.trap_id for c in copies_a}) == 15

    ensure_seeded(db_path=db_file)
    assert get_seed_manifest_hash(db_path=db_file) == hash_a


def test_attribution_variants_and_unattributed_handling(tmp_path: Path) -> None:
    db_file = tmp_path / "test_attr.db"
    ensure_seeded(db_path=db_file)

    variants = [
        "+52 442 XXX 0101 (ficticio)",
        "+52 442 000 0101",
        "442-000-0101",
        "524420000101",
    ]
    results = [attribute(v, db_path=db_file) for v in variants]
    assert all(r.status == "atribuido" for r in results)
    assert all(r.copy_id == "COPY-2026-10-001" for r in results)
    assert all(r.provider == "Proveedor A - padrón predial - 2026-10" for r in results)
    assert all(r.synthetic is True for r in results)

    # E09 SMS sobre copia 2
    sms_attr = attribute("+52 442 000 0102", db_path=db_file)
    assert sms_attr.status == "atribuido"
    assert sms_attr.copy_id == "COPY-2026-10-002"

    # Portal sin número trampa o número desconocido
    missing_attr = attribute(None, db_path=db_file)
    unknown_attr = attribute("+52 442 999 9999", db_path=db_file)
    assert missing_attr.status == "no_atribuido"
    assert missing_attr.copy_id is None
    assert unknown_attr.status == "no_atribuido"


def test_dashboard_does_not_reclassify_and_handles_empty_filters(tmp_path: Path) -> None:
    db_file = tmp_path / "test_dash.db"
    resp = get_dashboard(db_path=db_file)

    assert resp.synthetic is True
    assert resp.empty_state is None
    assert resp.summary.total_events == 4
    assert resp.summary.best_lead_time_hours == 6.5

    by_id = {row.event_id: row for row in resp.attributions}
    assert by_id["EVT-E01"].copy_id == "COPY-2026-10-001"
    assert by_id["EVT-E01"].status == "indicio"
    assert by_id["EVT-E01"].confidence == "baja"
    assert by_id["EVT-E14"].status == "sin_verificar"

    empty_resp = get_dashboard({"campaign_id": "CAMP-INEXISTENTE"}, db_path=db_file)
    assert empty_resp.attributions == []
    assert empty_resp.empty_state is not None


def test_map_18_municipalities_and_threshold_5() -> None:
    geojson = load_queretaro_geojson()
    assert len(geojson["features"]) == 18

    summary = get_map_summary()
    assert summary.state_name == "Querétaro"
    assert len(summary.municipalities) == 18
    assert summary.threshold == 5

    # 14 + 7 + 6 + 5 + 3 (Tequisquiapan suprimido) = 35
    assert summary.state_total == 35
    assert summary.excluded_rate_limited_count == 20

    by_code = {m.municipality_code: m for m in summary.municipalities}
    tequis = by_code["22017"]
    assert tequis.municipality_name == "Tequisquiapan"
    assert tequis.suppressed is True
    assert tequis.count is None

    # Verificar que tampoco se filtre el conteo < 5 dentro del GeoJSON serializado
    geojson_props = {
        f["properties"]["municipality_code"]: f["properties"]
        for f in summary.geojson["features"]
    }
    assert geojson_props["22017"]["suppressed"] is True
    assert geojson_props["22017"]["count"] is None
    assert geojson_props["22014"]["count"] == 14


def test_http_endpoints_and_offline_assets() -> None:
    app = _build_test_app()
    client = TestClient(app)

    r_planting = client.get("/planting")
    assert r_planting.status_code == 200
    assert "FICTICIO" in r_planting.text

    r_dash = client.get("/dashboard")
    assert r_dash.status_code == 200
    assert "/static/dashboard.js" in r_dash.text
    # Cero dependencias externas en HTML
    assert "https://" not in r_dash.text
    assert "http://" not in r_dash.text

    r_map = client.get("/api/map")
    assert r_map.status_code == 200
    payload = json.loads(r_map.text)
    assert payload["state_total"] == 35
    tequis_feature = next(
        f for f in payload["geojson"]["features"] if f["properties"]["municipality_code"] == "22017"
    )
    assert tequis_feature["properties"]["count"] is None
    assert tequis_feature["properties"]["suppressed"] is True
