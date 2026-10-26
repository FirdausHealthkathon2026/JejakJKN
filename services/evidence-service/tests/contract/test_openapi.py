from app.main import app


def test_gate_2_4_routes_include_verification_snapshots() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/integrations/encounters/{encounter_id}/events" in paths
    assert "/api/v1/patient/encounters/{encounter_id}/checkout-summary" in paths
    assert "/internal/v1/encounters/{encounter_id}/evidence-snapshots" in paths
    assert "/internal/v1/evidence-snapshots/{snapshot_id}" in paths
