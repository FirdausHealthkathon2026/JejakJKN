from decimal import Decimal

from app.domain.reconciliation import classify_candidates, reconcile_items
from app.domain.rules_engine import evaluate_rules


def claim(ref: str, kind: str, code: str, quantity: str = "1", unit: str = "1") -> dict:
    return {
        "item_ref": ref,
        "item_type": kind,
        "code_system": "LOCAL",
        "code": code,
        "quantity": Decimal(quantity),
        "unit": unit,
    }


def evidence(
    ref: str, kind: str, code: str, quantity: str = "1", unit: str = "1"
) -> dict:
    return {
        "evidence_id": f"e-{ref}",
        "evidence_version_id": ref,
        "kind": kind,
        "status": "ACTIVE",
        "code_system": "LOCAL",
        "code": code,
        "canonical_code_system": "LOCAL",
        "canonical_code": code,
        "mapping_status": "MAPPED",
        "canonical_quantity": quantity,
        "canonical_unit": unit,
    }


def test_maximum_matching_does_not_reuse_indivisible_evidence() -> None:
    results = reconcile_items(
        [claim("a", "PROCEDURE", "P1"), claim("b", "PROCEDURE", "P1")],
        [evidence("v1", "PROCEDURE", "P1")],
    )
    assert [row["match_result"] for row in results].count("MATCHED") == 1
    assert [row["match_result"] for row in results].count("MISSING") == 1


def test_medicine_quantity_is_allocated_across_evidence_without_double_counting() -> (
    None
):
    results = reconcile_items(
        [
            claim("a", "MEDICATION", "M1", "6", "tablet"),
            claim("b", "MEDICATION", "M1", "5", "tablet"),
        ],
        [
            evidence("v1", "MEDICATION_DISPENSE", "M1", "4", "tablet"),
            evidence("v2", "MEDICATION_DISPENSE", "M1", "6", "tablet"),
        ],
    )
    assert results[0]["match_result"] == "MATCHED"
    assert results[0]["allocated_evidence_quantity"] == 6
    assert results[1]["match_result"] == "QUANTITY_MISMATCH"
    assert results[1]["allocated_evidence_quantity"] == 4


def test_prescription_is_not_dispense_evidence() -> None:
    results = reconcile_items(
        [claim("a", "MEDICATION", "M1", "2", "tablet")],
        [evidence("v1", "MEDICATION_PRESCRIBED", "M1", "2", "tablet")],
    )
    assert results[0]["match_result"] == "PRESCRIBED_ONLY"


def test_corrected_current_version_remains_eligible() -> None:
    current = evidence("v2", "PROCEDURE", "P1") | {"status": "CORRECTED"}
    assert (
        reconcile_items([claim("a", "PROCEDURE", "P1")], [current])[0]["match_result"]
        == "MATCHED"
    )


def test_candidate_safety_and_identity_prevent_auto_match() -> None:
    candidates = [{"match_state": "ELIGIBLE_COMPLETE_MATCH"}]
    assert (
        classify_candidates(candidates, truncated=True, strong_identity=True)[0]
        == "TOO_MANY_CANDIDATES"
    )
    assert (
        classify_candidates(candidates, truncated=False, strong_identity=False)[0]
        == "IDENTITY_INSUFFICIENT"
    )
    assert (
        classify_candidates(candidates * 2, truncated=False, strong_identity=True)[0]
        == "AMBIGUOUS_MATCH"
    )


def test_rules_are_explanatory_and_never_a_fraud_decision() -> None:
    findings = evaluate_rules(
        {
            "encounter_match_status": "NO_SUITABLE_ENCOUNTER",
            "identity_assurance": "INSUFFICIENT",
            "item_results": [],
            "data_freshness": "CURRENT",
            "patient_confirmation_status": "NO_RESPONSE",
        }
    )
    assert {row["rule_id"] for row in findings} == {"R001", "R002", "R013"}
    assert all("not a fraud decision" in row["limitations_text"] for row in findings)
