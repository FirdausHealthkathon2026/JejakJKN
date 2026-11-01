"""Deterministic findings for the versioned rules-1.0.0 catalog."""

from typing import Any

RULES = {
    "R001": ("HIGH", "NO_ENCOUNTER"),
    "R002": ("HIGH", "WEAK_IDENTITY"),
    "R003": ("HIGH", "MISSING_OR_PRESCRIBED_ONLY"),
    "R004": ("MEDIUM", "QUANTITY_MISMATCH"),
    "R005": ("HIGH", "PATIENT_DISPUTED"),
    "R006": ("MEDIUM", "TIME_INCONSISTENCY"),
    "R007": ("HIGH", "ENCOUNTER_REUSED"),
    "R008": ("HIGH", "EVIDENCE_REUSED"),
    "R009": ("INFO", "CLAIM_REVERIFIED"),
    "R010": ("MEDIUM", "STALE_OR_LATE_EVIDENCE"),
    "R011": ("HIGH", "DOCUMENT_CROSS_PATIENT"),
    "R012": ("MEDIUM", "CHECKOUT_EXCEPTION"),
    "R013": ("INFO", "PATIENT_NO_RESPONSE"),
    "R014": ("MEDIUM", "UNSUPPORTED_MAPPING"),
}


def evaluate_rules(facts: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(
        rule_id: str,
        explanation: dict[str, Any],
        *,
        item_ref: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> None:
        severity, code = RULES[rule_id]
        findings.append(
            {
                "rule_id": rule_id,
                "rule_version": "1.0.0",
                "severity": severity,
                "finding_code": code,
                "claim_item_ref": item_ref,
                "evidence_refs": evidence_refs or [],
                "explanation_facts": explanation,
                "limitations_text": "Deterministic screening signal; not a fraud decision.",
            }
        )

    if facts["encounter_match_status"] in {
        "NO_ENCOUNTER_FOUND",
        "NO_SUITABLE_ENCOUNTER",
        "TOO_MANY_CANDIDATES",
    }:
        add("R001", {"match_status": facts["encounter_match_status"]})
    if facts["identity_assurance"] != "STRONG":
        add("R002", {"identity_assurance": facts["identity_assurance"]})
    for item in facts.get("item_results", []):
        if item["match_result"] in {"MISSING", "PRESCRIBED_ONLY"}:
            add(
                "R003",
                {"result": item["match_result"]},
                item_ref=item["claim_item_ref"],
            )
        if item["match_result"] == "QUANTITY_MISMATCH":
            add(
                "R004",
                {
                    "claimed": str(item["claimed_quantity"]),
                    "allocated": str(item["allocated_evidence_quantity"]),
                },
                item_ref=item["claim_item_ref"],
            )
        if item.get("patient_response") == "DISPUTED":
            add(
                "R005",
                {"patient_response": "DISPUTED"},
                item_ref=item["claim_item_ref"],
                evidence_refs=[str(item["evidence_version_ref"])],
            )
        if item["match_result"] == "UNSUPPORTED_MAPPING":
            add(
                "R014",
                {"result": "UNSUPPORTED_MAPPING"},
                item_ref=item["claim_item_ref"],
            )
    if facts.get("time_inconsistent"):
        add("R006", {"reason": facts["time_inconsistent"]})
    if facts.get("encounter_reused"):
        add("R007", {"conflicting_claims": facts.get("conflicting_claims", [])})
    if facts.get("evidence_reused"):
        add(
            "R008",
            {"evidence_refs": facts.get("reused_evidence_refs", [])},
            evidence_refs=facts.get("reused_evidence_refs", []),
        )
    if facts.get("claim_reverified"):
        add("R009", {"prior_run_id": facts.get("prior_run_id")})
    if facts.get("data_freshness") != "CURRENT" or facts.get("late_evidence"):
        add("R010", {"data_freshness": facts.get("data_freshness")})
    if facts.get("document_cross_patient"):
        add("R011", {"fingerprints": facts.get("cross_patient_fingerprints", [])})
    if facts.get("presence_status") and facts.get("presence_status") not in {
        "QR_VERIFIED",
        "UNKNOWN",
    }:
        add("R012", {"presence_status": facts.get("presence_status")})
    if facts.get("patient_confirmation_status") in {
        "NOT_APPLICABLE",
        "NO_RESPONSE",
        "DECLINED",
    }:
        add(
            "R013",
            {"patient_confirmation_status": facts.get("patient_confirmation_status")},
        )
    return findings
