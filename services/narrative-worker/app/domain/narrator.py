"""Deterministic, factual narrative with a certainty-language guard."""

import hashlib
import json

BANNED = ("terbukti fraud", "pasti fraud", "definitively fraudulent", "guilty of fraud")


def narrate(package: dict) -> tuple[dict, str, str]:
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
    status = "VALID"
    if any(term in json.dumps(result, ensure_ascii=False).lower() for term in BANNED):
        result = {
            "summary": ["Ringkasan otomatis tidak dapat ditampilkan."],
            "findings": [],
            "questions": ["Silakan telaah paket bukti."],
            "limitations": ["Keputusan harus dibuat oleh reviewer manusia."],
        }
        status = "FALLBACK"
    digest = hashlib.sha256(
        json.dumps(package, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result, status, digest
