from app.main import app


def test_gate_2_3_routes_are_exposed_without_gate_4_internal_snapshot_routes() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/integrations/encounters/{encounter_id}/events" in paths
    assert "/api/v1/patient/encounters/{encounter_id}/checkout-summary" in paths
    assert not any(path.startswith("/internal/") for path in paths)
