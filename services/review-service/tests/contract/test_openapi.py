from app.main import app


def test_gate_6_review_routes_are_exposed() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/review-cases" in paths
    assert "/api/v1/review-cases/{case_id}" in paths
    assert "/api/v1/review-cases/{case_id}/decisions" in paths
    assert "/internal/v1/narratives/{assessment_ref}" in paths
