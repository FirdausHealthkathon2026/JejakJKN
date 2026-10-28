"""Deterministic, factual narrative with a certainty-language and hallucination guard."""

import hashlib
import json
import re
from typing import Any

BANNED = (
    "terbukti fraud",
    "pasti fraud",
    "definitively fraudulent",
    "guilty of fraud",
    "confirmed fraud",
    "penipuan terbukti",
    "klaim ditolak otomatis",
)
PII_KEYS = {
    "participant_number",
    "patient_name",
    "display_name",
    "name",
    "nik",
    "participant_number_ciphertext",
    "display_name_ciphertext",
    "note_ciphertext",
}
RULE_ID_PATTERN = re.compile(r"\bR\d{3}(?:_[A-Z0-9_]+)?\b")
MAX_SECTION_ITEMS = 20
MAX_ITEM_CHARS = 600


def compute_digest(package: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(package, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def minimize_package(package: dict[str, Any]) -> dict[str, Any]:
    """Strip any potential PII and retain only de-identified deterministic facts for LLM input."""

    def _scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: _scrub(v)
                for k, v in value.items()
                if k.lower() not in PII_KEYS
            }
        if isinstance(value, list):
            return [_scrub(item) for item in value]
        return value

    assessment = package.get("assessment", {})
    minimized = {
        "data_freshness": package.get("data_freshness", "CURRENT"),
        "assessment": {
            "encounter_match_status": assessment.get("encounter_match_status"),
            "identity_assurance": assessment.get("identity_assurance"),
            "evidence_reconciliation_status": assessment.get(
                "evidence_reconciliation_status"
            ),
            "duplicate_assessment_status": assessment.get(
                "duplicate_assessment_status"
            ),
            "patient_confirmation_status": assessment.get(
                "patient_confirmation_status"
            ),
            "review_required": assessment.get("review_required", True),
            "final_fraud_decision": None,
        },
        "candidates": [
            {
                "candidate_index": idx + 1,
                "match_state": row.get("match_state"),
                "reasons": row.get("reasons", []),
            }
            for idx, row in enumerate(package.get("candidates", []))
        ],
        "items": [
            {
                "claim_item_ref": item.get("claim_item_ref"),
                "match_result": item.get("match_result"),
                "reason": item.get("reason"),
            }
            for item in package.get("items", [])
        ],
        "findings": [
            {
                "rule_id": row.get("rule_id"),
                "severity": row.get("severity"),
                "finding_code": row.get("finding_code"),
                "claim_item_ref": row.get("claim_item_ref"),
                "explanation_facts": row.get("explanation_facts"),
                "limitations": row.get("limitations"),
            }
            for row in package.get("findings", [])
        ],
    }
    return _scrub(minimized)


def fallback_narrative() -> dict[str, list[str]]:
    return {
        "summary": ["Ringkasan otomatis tidak dapat ditampilkan."],
        "findings": [],
        "questions": ["Silakan telaah paket bukti."],
        "limitations": ["Keputusan harus dibuat oleh reviewer manusia."],
    }


def validate_narrative(
    candidate: Any, package: dict[str, Any]
) -> tuple[dict[str, list[str]], bool]:
    """Validate structure, length bounds, rule references, and certainty-language guard."""
    if not isinstance(candidate, dict):
        return fallback_narrative(), False

    required_keys = ("summary", "findings", "questions", "limitations")
    cleaned: dict[str, list[str]] = {}
    for key in required_keys:
        val = candidate.get(key)
        if not isinstance(val, list) or len(val) > MAX_SECTION_ITEMS:
            return fallback_narrative(), False
        lines: list[str] = []
        for entry in val:
            if not isinstance(entry, str):
                return fallback_narrative(), False
            text = entry.strip()
            if not text or len(text) > MAX_ITEM_CHARS:
                return fallback_narrative(), False
            lines.append(text)
        cleaned[key] = lines

    if not cleaned["summary"] or not cleaned["questions"] or not cleaned["limitations"]:
        return fallback_narrative(), False

    serialized = json.dumps(cleaned, ensure_ascii=False)
    lowered = serialized.lower()
    if any(term in lowered for term in BANNED):
        return fallback_narrative(), False

    for pii_key in PII_KEYS:
        if pii_key in package and isinstance(package[pii_key], str) and package[pii_key]:
            if package[pii_key].lower() in lowered:
                return fallback_narrative(), False

    allowed_rules: set[str] = set()
    for row in package.get("findings", []):
        rule_id = row.get("rule_id")
        if rule_id:
            rule_str = str(rule_id)
            allowed_rules.add(rule_str)
            allowed_rules.add(rule_str.split("_", 1)[0])
    mentioned_rules = set(RULE_ID_PATTERN.findall(serialized))
    if not mentioned_rules.issubset(allowed_rules):
        return fallback_narrative(), False

    return cleaned, True


def narrate(package: dict[str, Any]) -> tuple[dict[str, list[str]], str, str]:
    facts = [
        f"Status pencocokan kunjungan: {package['assessment']['encounter_match_status']}."
    ]
    facts.extend(
        f"{item['claim_item_ref']}: {item['match_result']} ({item['reason']})."
        for item in package.get("items", [])
    )
    result = {
        "summary": facts,
        "findings": [
            f"{row['rule_id']} [{row['severity']}]: {row['finding_code']}."
            for row in package.get("findings", [])
        ],
        "questions": ["Apakah bukti klinis tambahan tersedia?"],
        "limitations": [
            "Ringkasan ini membantu telaah manusia dan bukan keputusan fraud atau pembayaran."
        ],
    }
    validated, is_valid = validate_narrative(result, package)
    status = "VALID" if is_valid else "FALLBACK"
    digest = compute_digest(package)
    return validated, status, digest
