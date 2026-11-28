from fastapi.testclient import TestClient

from app.main import app


def test_integrated_module_routes_respond():
    paths = (
        "/",
        "/api/health",
        "/planting",
        "/voice/",
        "/intel/campaigns",
        "/sms",
        "/citizen",
        "/dashboard",
        "/api/map",
        "/api/dashboard",
        "/api/planting/copies",
    )
    with TestClient(app) as client:
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)


def test_all_scenarios_pass_through_integrated_runner():
    with TestClient(app) as client:
        response = client.post("/api/scenarios/run-all")

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 14
    assert all(result["passed"] for result in results)
