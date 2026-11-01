from app.main import app


def test_gate_4_5_verification_routes_are_exposed() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/verifications" in paths
    assert "/api/v1/verifications/history" in paths
    assert "/api/v1/verifications/{verification_id}/candidates" in paths
    assert "/api/v1/verifications/{verification_id}/findings" in paths
    assert "/api/v1/verifications/{verification_id}/re-evaluate" in paths
