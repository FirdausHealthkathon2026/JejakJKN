from app.domain.narrator import narrate


def test_narrator_is_factual_and_never_returns_fraud_verdict() -> None:
    result, status, digest = narrate(
        {
            "assessment": {"encounter_match_status": "NO_ENCOUNTER_FOUND"},
            "items": [],
            "findings": [],
        }
    )
    assert status == "VALID"
    assert len(digest) == 64
    assert "terbukti fraud" not in str(result).lower()
