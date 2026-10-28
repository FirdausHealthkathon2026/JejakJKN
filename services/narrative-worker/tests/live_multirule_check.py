"""Live Groq test runner for multiple rule mismatch scenarios (R004 Quantity Mismatch, R007 Double Billing, R001 Phantom Billing)."""

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from app.domain.narrator import minimize_package, narrate  # noqa: E402
from app.infrastructure.llm_adapter import (  # noqa: E402
    generate_narrative_sync,
    get_groq_api_key,
)


def _load_dotenv() -> None:
    for candidate in (ROOT / ".env", ROOT / ".env.example"):
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val and not os.getenv(key):
                os.environ[key] = val


TEST_CASES = [
    {
        "id": "CASE-1: R004_QUANTITY_MISMATCH",
        "description": "Tagihan Amoksisilin 30 tablet, namun bukti dispensing farmasi SIMRS hanya mencatat 10 tablet.",
        "package": {
            "participant_number": "SYNTHETIC-10002",
            "patient_name": "Siti Rahma",
            "claim_source": "BPJS_FKRTL_PROD",
            "claim_id": "CLAIM-R004-QTY-2026",
            "assessment": {
                "encounter_match_status": "UNIQUE_MATCH",
                "identity_assurance": "VERIFIED_PARTICIPANT_ID",
                "evidence_reconciliation_status": "ITEM_MISMATCH",
                "duplicate_assessment_status": "NO_REUSE_FOUND_IN_JEJAKJKN_HISTORY",
                "patient_confirmation_status": "CONFIRMED",
                "review_required": True,
                "final_fraud_decision": None,
            },
            "candidates": [
                {
                    "encounter_id": "43b2fa59-a761-57ec-85ca-c9ea02fd1fa4",
                    "match_state": "ELIGIBLE_PARTIAL_MATCH",
                    "reasons": ["Diagnosis matched, medication quantity discrepancy"],
                }
            ],
            "items": [
                {
                    "claim_item_ref": "DX-PRIMARY",
                    "item_type": "DIAGNOSIS",
                    "code_system": "ICD-10",
                    "code": "A09",
                    "display": "Gastroenteritis and colitis of unspecified origin",
                    "match_result": "MATCHED",
                    "reason": "Exact canonical match",
                },
                {
                    "claim_item_ref": "MED-1",
                    "item_type": "MEDICATION",
                    "code_system": "DEMO-MEDICATION-CATALOG",
                    "code": "MED-001",
                    "display": "Amoksisilin 500 mg",
                    "quantity": 30,
                    "unit": "tablet",
                    "match_result": "QUANTITY_MISMATCH",
                    "reason": "Dispensed quantity allocated without reuse: claimed 30 tablet, allocated 10 tablet",
                },
            ],
            "findings": [
                {
                    "rule_id": "R004_QUANTITY_MISMATCH",
                    "severity": "MEDIUM",
                    "finding_code": "QUANTITY_MISMATCH",
                    "claim_item_ref": "MED-1",
                    "explanation_facts": {
                        "claimed": "30",
                        "allocated": "10",
                        "unit": "tablet",
                    },
                    "limitations": "Selisih kuantitas obat memerlukan konfirmasi faktur pengeluaran depo farmasi sebelum menyimpulkan tagihan berlebih.",
                }
            ],
        },
    },
    {
        "id": "CASE-2: R007_ENCOUNTER_REUSED",
        "description": "Double billing: kunjungan pasien digunakan ulang pada berkas klaim kedua yang berkonflik dengan klaim sebelumnya.",
        "package": {
            "participant_number": "SYNTHETIC-10003",
            "patient_name": "Ahmad Dahlan",
            "claim_source": "BPJS_FKRTL_PROD",
            "claim_id": "CLAIM-DUP-R007-999",
            "assessment": {
                "encounter_match_status": "UNIQUE_MATCH",
                "identity_assurance": "VERIFIED_PARTICIPANT_ID",
                "evidence_reconciliation_status": "ITEMS_CONSISTENT",
                "duplicate_assessment_status": "POTENTIAL_ENCOUNTER_REUSE",
                "patient_confirmation_status": "CONFIRMED",
                "review_required": True,
                "final_fraud_decision": None,
            },
            "candidates": [
                {
                    "encounter_id": "ce68fb06-bbf6-59ee-ac3f-90f015b66320",
                    "match_state": "ELIGIBLE_COMPLETE_MATCH",
                    "reasons": ["Encounter and all clinical records already associated with prior claim CLAIM-ORIGINAL-888"],
                }
            ],
            "items": [
                {
                    "claim_item_ref": "DX-PRIMARY",
                    "item_type": "DIAGNOSIS",
                    "code_system": "ICD-10",
                    "code": "I25",
                    "display": "Atherosclerotic heart disease",
                    "match_result": "MATCHED",
                    "reason": "Exact canonical match",
                },
                {
                    "claim_item_ref": "PROC-1",
                    "item_type": "PROCEDURE",
                    "code_system": "ICD-9-CM",
                    "code": "8906",
                    "display": "Konsultasi medis spesialis",
                    "match_result": "MATCHED",
                    "reason": "Exact canonical match",
                },
            ],
            "findings": [
                {
                    "rule_id": "R007_ENCOUNTER_REUSED",
                    "severity": "HIGH",
                    "finding_code": "ENCOUNTER_REUSED",
                    "claim_item_ref": "DX-PRIMARY",
                    "explanation_facts": {
                        "conflicting_claims": ["CLAIM-ORIGINAL-888"],
                    },
                    "limitations": "Verifikasi riwayat klaim sebelumnya untuk memastikan apakah ini klaim revisi resmi atau duplikasi tagihan (double billing).",
                }
            ],
        },
    },
    {
        "id": "CASE-3: R001_NO_ENCOUNTER",
        "description": "Phantom billing: tagihan dikirim untuk diagnosis low back pain, tetapi pasien tidak pernah berobat / tidak ada catatan kunjungan di SIMRS.",
        "package": {
            "participant_number": "SYNTHETIC-10004",
            "patient_name": "Joko Widodo",
            "claim_source": "BPJS_FKRTL_PROD",
            "claim_id": "CLAIM-PHANTOM-R001",
            "assessment": {
                "encounter_match_status": "NO_ENCOUNTER_FOUND",
                "identity_assurance": "VERIFIED_PARTICIPANT_ID",
                "evidence_reconciliation_status": "EVIDENCE_INCOMPLETE",
                "duplicate_assessment_status": "NO_REUSE_FOUND_IN_JEJAKJKN_HISTORY",
                "patient_confirmation_status": "NOT_APPLICABLE",
                "review_required": True,
                "final_fraud_decision": None,
            },
            "candidates": [],
            "items": [
                {
                    "claim_item_ref": "DX-PRIMARY",
                    "item_type": "DIAGNOSIS",
                    "code_system": "ICD-10",
                    "code": "M54",
                    "display": "Low back pain",
                    "match_result": "MISSING",
                    "reason": "No encounter found in hospital evidence",
                }
            ],
            "findings": [
                {
                    "rule_id": "R001_NO_MATCHING_ENCOUNTER",
                    "severity": "HIGH",
                    "finding_code": "NO_ENCOUNTER_FOUND",
                    "claim_item_ref": "DX-PRIMARY",
                    "explanation_facts": {
                        "encounter_match_status": "NO_ENCOUNTER_FOUND",
                    },
                    "limitations": "Pemeriksaan log server SIMRS atau konfirmasi pendaftaran faskes diperlukan sebelum menyimpulkan klaim fiktif.",
                }
            ],
        },
    },
]


def run_all() -> None:
    _load_dotenv()
    token = get_groq_api_key()
    if not token:
        print("[ERROR] GROQ_API_KEY tidak ditemukan di .env!")
        return

    os.environ["NARRATIVE_PROVIDER"] = "groq"
    print(f"=== Menjalankan Live Test Groq untuk 3 Kasus Rule Mismatch ===")
    print(f"Menggunakan Provider: Groq ({os.getenv('GROQ_MODEL', 'qwen/qwen3.8-27b')})\n")

    for case in TEST_CASES:
        print("=" * 70)
        print(f"[{case['id']}]")
        print(f"Keterangan Skenario: {case['description']}")
        print("-" * 70)

        # 1. Deterministic Fallback check
        det_nar, det_stat, det_dig = narrate(case["package"])
        for banned_ref in ("ITEM-1", "ITEM-2", "DX-PRIMARY", "MED-1", "PROC-1"):
            assert banned_ref not in json.dumps(det_nar)

        # 2. Live Groq generation
        narrative, status, digest, method, model_info = generate_narrative_sync(
            case["package"]
        )

        for banned_ref in ("ITEM-1", "ITEM-2", "DX-PRIMARY", "MED-1", "PROC-1"):
            assert banned_ref not in json.dumps(narrative), f"Found {banned_ref} in narrative output!"

        print(f"Method: {method} | Model: {model_info} | Status: {status}")
        print("\n--- HASIL SUMMARY ---")
        for line in narrative["summary"]:
            print(f"• {line}")

        print("\n--- HASIL FINDINGS ---")
        for line in narrative["findings"]:
            print(f"• {line}")

        print("\n--- PERTANYAAN REKOMENDASI UNTUK VERIFIKATOR ---")
        for line in narrative["questions"]:
            print(f"? {line}")

        print("\n--- BATASAN / LIMITATIONS ---")
        for line in narrative["limitations"]:
            print(f"! {line}")
        print("\n")


if __name__ == "__main__":
    run_all()

