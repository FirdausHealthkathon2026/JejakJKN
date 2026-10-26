"""Deterministic candidate classification and claim/evidence reconciliation."""

from decimal import Decimal
from typing import Any


def classify_candidates(
    candidates: list[dict[str, Any]], *, truncated: bool, strong_identity: bool
) -> tuple[str, dict[str, Any] | None]:
    if truncated:
        return "TOO_MANY_CANDIDATES", None
    if not strong_identity:
        return "IDENTITY_INSUFFICIENT", None
    complete = [
        candidate
        for candidate in candidates
        if candidate["match_state"] == "ELIGIBLE_COMPLETE_MATCH"
    ]
    partial = [
        candidate
        for candidate in candidates
        if candidate["match_state"] == "ELIGIBLE_PARTIAL_MATCH"
    ]
    pool = complete or partial
    if len(pool) == 1:
        return "UNIQUE_MATCH", pool[0]
    if len(pool) > 1:
        return "AMBIGUOUS_MATCH", None
    return ("NO_ENCOUNTER_FOUND" if not candidates else "NO_SUITABLE_ENCOUNTER"), None


def reconcile_items(
    claim_items: list[dict[str, Any]], evidence_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Match indivisible items maximally, then allocate medicine quantities without reuse."""
    active = [
        item for item in evidence_items if item.get("status") in {"ACTIVE", "CORRECTED"}
    ]
    results: dict[str, dict[str, Any]] = {}
    indivisible = [
        item
        for item in claim_items
        if item["item_type"] not in {"MEDICATION", "MEDICATION_DISPENSE"}
    ]
    edges = {
        item["item_ref"]: [
            evidence
            for evidence in active
            if _eligible(item, evidence)
            and evidence.get("kind")
            not in {"MEDICATION_PRESCRIBED", "MEDICATION_DISPENSE"}
        ]
        for item in indivisible
    }
    owner: dict[str, str] = {}

    def assign(item_ref: str, seen: set[str]) -> bool:
        for evidence in edges[item_ref]:
            ref = evidence["evidence_version_id"]
            if ref in seen:
                continue
            seen.add(ref)
            if ref not in owner or assign(owner[ref], seen):
                owner[ref] = item_ref
                return True
        return False

    for item in sorted(indivisible, key=lambda row: row["item_ref"]):
        assign(item["item_ref"], set())
    evidence_by_ref = {item["evidence_version_id"]: item for item in active}
    claimed_by_ref = {item["item_ref"]: item for item in claim_items}
    for evidence_ref, item_ref in owner.items():
        evidence = evidence_by_ref[evidence_ref]
        results[item_ref] = _result(
            claimed_by_ref[item_ref],
            "MATCHED",
            evidence,
            Decimal("1"),
            "Exact canonical match",
        )

    remaining: dict[str, Decimal] = {
        item["evidence_version_id"]: Decimal(
            str(item.get("canonical_quantity") or item.get("quantity") or 0)
        )
        for item in active
        if item.get("kind") == "MEDICATION_DISPENSE"
    }
    for item in sorted(
        (
            row
            for row in claim_items
            if row["item_type"] in {"MEDICATION", "MEDICATION_DISPENSE"}
        ),
        key=lambda row: row["item_ref"],
    ):
        needed = Decimal(str(item.get("quantity") or 0))
        allocations: list[tuple[dict[str, Any], Decimal]] = []
        for evidence in active:
            ref = evidence["evidence_version_id"]
            if (
                remaining.get(ref, Decimal()) <= 0
                or not _eligible(item, evidence)
                or evidence.get("kind") != "MEDICATION_DISPENSE"
            ):
                continue
            amount = min(needed, remaining[ref])
            allocations.append((evidence, amount))
            remaining[ref] -= amount
            needed -= amount
            if needed <= 0:
                break
        allocated = sum((amount for _, amount in allocations), Decimal())
        first = allocations[0][0] if allocations else None
        prescribed = any(
            _eligible(item, evidence)
            and evidence.get("kind") == "MEDICATION_PRESCRIBED"
            for evidence in active
        )
        unsupported = any(
            _same_source_code(item, evidence)
            and evidence.get("mapping_status") == "UNSUPPORTED_MAPPING"
            for evidence in active
        )
        status = (
            "MATCHED"
            if needed <= 0
            else "QUANTITY_MISMATCH"
            if allocated
            else "UNSUPPORTED_MAPPING"
            if unsupported
            else "PRESCRIBED_ONLY"
            if prescribed
            else "MISSING"
        )
        results[item["item_ref"]] = _result(
            item, status, first, allocated, "Dispensed quantity allocated without reuse"
        )
        results[item["item_ref"]]["allocations"] = [
            {
                "evidence_id": evidence["evidence_id"],
                "evidence_version_ref": evidence["evidence_version_id"],
                "quantity": amount,
            }
            for evidence, amount in allocations
        ]

    for item in claim_items:
        if item["item_ref"] in results:
            continue
        unsupported = any(
            _same_source_code(item, evidence)
            and evidence.get("mapping_status") == "UNSUPPORTED_MAPPING"
            for evidence in active
        )
        prescribed = item["item_type"] in {"MEDICATION", "MEDICATION_DISPENSE"} and any(
            _eligible(item, evidence)
            and evidence.get("kind") == "MEDICATION_PRESCRIBED"
            for evidence in active
        )
        status = (
            "UNSUPPORTED_MAPPING"
            if unsupported
            else "PRESCRIBED_ONLY"
            if prescribed
            else "MISSING"
        )
        results[item["item_ref"]] = _result(
            item, status, None, Decimal(), status.replace("_", " ").title()
        )
    return [results[item["item_ref"]] for item in claim_items]


def _eligible(claim: dict[str, Any], evidence: dict[str, Any]) -> bool:
    kinds = {
        "DIAGNOSIS": {"DIAGNOSIS"},
        "PROCEDURE": {"PROCEDURE"},
        "MEDICATION": {"MEDICATION_PRESCRIBED", "MEDICATION_DISPENSE"},
        "MEDICATION_DISPENSE": {"MEDICATION_PRESCRIBED", "MEDICATION_DISPENSE"},
    }
    return (
        evidence.get("kind") in kinds[claim["item_type"]]
        and evidence.get("mapping_status") == "MAPPED"
        and claim["code_system"] == evidence.get("canonical_code_system")
        and claim["code"] == evidence.get("canonical_code")
        and (
            claim["item_type"] not in {"MEDICATION", "MEDICATION_DISPENSE"}
            or claim.get("unit") == evidence.get("canonical_unit")
        )
    )


def _same_source_code(claim: dict[str, Any], evidence: dict[str, Any]) -> bool:
    return claim["code_system"] == evidence.get("code_system") and claim[
        "code"
    ] == evidence.get("code")


def _result(
    claim: dict[str, Any],
    status: str,
    evidence: dict[str, Any] | None,
    allocated: Decimal,
    reason: str,
) -> dict[str, Any]:
    return {
        "claim_item_ref": claim["item_ref"],
        "match_result": status,
        "claimed_quantity": Decimal(str(claim.get("quantity") or 1)),
        "allocated_evidence_quantity": allocated,
        "evidence_id": evidence.get("evidence_id") if evidence else None,
        "evidence_version_ref": evidence.get("evidence_version_id")
        if evidence
        else None,
        "patient_response": evidence.get("patient_response") if evidence else None,
        "reason": reason,
        "allocations": [
            {
                "evidence_id": evidence["evidence_id"],
                "evidence_version_ref": evidence["evidence_version_id"],
                "quantity": allocated,
            }
        ]
        if evidence
        else [],
    }
