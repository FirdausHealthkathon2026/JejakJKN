import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "libs/python-observability"))

from jejakjkn_observability.logging import redact  # noqa: E402


def test_sensitive_fields_and_embedded_jws_are_redacted() -> None:
    result = redact(
        {
            "participant_number": "SYNTHETIC-10001",
            "nested": {"authorization": "Bearer secret"},
            "message": "seen eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
            "safe": "request-123",
        }
    )
    assert result["participant_number"] == "[REDACTED]"
    assert result["nested"]["authorization"] == "[REDACTED]"
    assert result["message"] == "seen [REDACTED_JWS]"
    assert result["safe"] == "request-123"
