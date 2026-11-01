"""Contract test for narrative JSON output and Review Service schema compatibility."""

import json

from app.domain.narrator import narrate, validate_narrative


def test_narrative_output_matches_review_service_contract() -> None:
    package = {
        "assessment": {"encounter_match_status": "UNIQUE_MATCH"},
        "items": [
            {
                "claim_item_ref": "ITEM-1",
                "match_result": "MATCHED",
                "reason": "Matched procedure evidence",
            }
        ],
        "findings": [
            {
                "rule_id": "R009_DUPLICATE_EXTERNAL_CLAIM",
                "severity": "INFO",
                "finding_code": "IDENTICAL_CLAIM_REVERIFIED",
            }
        ],
    }
    narrative, status, digest = narrate(package)
    assert status in {"VALID", "FALLBACK"}
    assert len(digest) == 64
    assert set(narrative.keys()) == {"summary", "findings", "questions", "limitations"}
    assert "ITEM-1" not in json.dumps(narrative)
    validated, ok = validate_narrative(narrative, package)
    assert ok is True
    assert validated == narrative
