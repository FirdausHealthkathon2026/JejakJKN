import json
import pytest

from app.domain.narrator import minimize_package, narrate, validate_narrative
from app.infrastructure.llm_adapter import generate_narrative


def _sample_package() -> dict:
    return {
        "participant_number": "SYNTHETIC-10001",
        "patient_name": "Budi Santoso",
        "assessment": {
            "encounter_match_status": "UNIQUE_MATCH",
            "identity_assurance": "VERIFIED_PARTICIPANT_ID",
            "evidence_reconciliation_status": "ITEM_MISMATCH",
            "duplicate_assessment_status": "NO_REUSE_FOUND_IN_JEJAKJKN_HISTORY",
            "patient_confirmation_status": "CONFIRMED",
            "review_required": True,
            "final_fraud_decision": None,
        },
        "items": [
            {
                "claim_item_ref": "ITEM-1",
                "match_result": "MISSING_IN_EVIDENCE",
                "reason": "No matching procedure evidence found",
            }
        ],
        "findings": [
            {
                "rule_id": "R003_ITEM_MISSING",
                "severity": "HIGH",
                "finding_code": "CLAIM_ITEM_UNSUPPORTED_BY_EVIDENCE",
                "claim_item_ref": "ITEM-1",
                "explanation_facts": {"item_ref": "ITEM-1"},
                "limitations": "Periksa kelengkapan sinkronisasi SIMRS.",
            }
        ],
    }


def _package_r004_quantity_mismatch() -> dict:
    return {
        "participant_number": "SYNTHETIC-10002",
        "patient_name": "Siti Rahma",
        "claim_id": "CLAIM-R004-QTY-001",
        "assessment": {
            "encounter_match_status": "UNIQUE_MATCH",
            "identity_assurance": "VERIFIED_PARTICIPANT_ID",
            "evidence_reconciliation_status": "ITEM_MISMATCH",
            "duplicate_assessment_status": "NO_REUSE_FOUND_IN_JEJAKJKN_HISTORY",
            "patient_confirmation_status": "CONFIRMED",
            "review_required": True,
            "final_fraud_decision": None,
        },
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
                "limitations": "Selisih jumlah obat memerlukan konfirmasi faktur pengeluaran depo farmasi sebelum menyimpulkan tagihan berlebih.",
            }
        ],
    }


def _package_r007_double_billing() -> dict:
    return {
        "participant_number": "SYNTHETIC-10003",
        "patient_name": "Ahmad Dahlan",
        "claim_id": "CLAIM-DUP-R007-002",
        "assessment": {
            "encounter_match_status": "UNIQUE_MATCH",
            "identity_assurance": "VERIFIED_PARTICIPANT_ID",
            "evidence_reconciliation_status": "ITEMS_CONSISTENT",
            "duplicate_assessment_status": "POTENTIAL_ENCOUNTER_REUSE",
            "patient_confirmation_status": "CONFIRMED",
            "review_required": True,
            "final_fraud_decision": None,
        },
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
                    "conflicting_claims": ["CLAIM-ORIGINAL-999"],
                },
                "limitations": "Verifikasi riwayat klaim sebelumnya untuk memastikan apakah ini klaim revisi resmi atau duplikasi tagihan (double billing).",
            }
        ],
    }


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


def test_minimize_package_strips_pii_and_internal_item_refs() -> None:
    pkg = _sample_package()
    minimized = minimize_package(pkg)
    dumped = str(minimized)
    assert "SYNTHETIC-10001" not in dumped
    assert "Budi Santoso" not in dumped
    assert "ITEM-1" not in dumped
    assert "hal_yang_sesuai" in minimized
    assert "hal_yang_tidak_sesuai" in minimized
    assert minimized["assessment"]["final_fraud_decision"] is None


def test_rule_r004_quantity_mismatch_formatting() -> None:
    pkg = _package_r004_quantity_mismatch()
    minimized = minimize_package(pkg)
    dumped_min = json.dumps(minimized, ensure_ascii=False)
    assert "SYNTHETIC-10002" not in dumped_min
    assert "DX-PRIMARY" not in dumped_min
    assert "MED-1" not in dumped_min
    assert "Amoksisilin" in dumped_min

    narrative, status, digest = narrate(pkg)
    assert status == "VALID" and len(digest) == 64
    dumped_nar = json.dumps(narrative, ensure_ascii=False)
    assert "DX-PRIMARY" not in dumped_nar
    assert "MED-1" not in dumped_nar
    assert "Amoksisilin" in dumped_nar
    assert any("YANG SESUAI" in s for s in narrative["summary"])
    assert any("YANG TIDAK SESUAI" in s for s in narrative["summary"])


def test_rule_r007_double_billing_formatting() -> None:
    pkg = _package_r007_double_billing()
    minimized = minimize_package(pkg)
    dumped_min = json.dumps(minimized, ensure_ascii=False)
    assert "SYNTHETIC-10003" not in dumped_min
    assert "DX-PRIMARY" not in dumped_min
    assert "PROC-1" not in dumped_min

    narrative, status, digest = narrate(pkg)
    assert status == "VALID" and len(digest) == 64
    dumped_nar = json.dumps(narrative, ensure_ascii=False)
    assert "DX-PRIMARY" not in dumped_nar
    assert "PROC-1" not in dumped_nar
    assert "POTENTIAL_ENCOUNTER_REUSE" not in dumped_nar
    assert "dipakai klaim lain" in dumped_nar
    assert any("YANG SESUAI" in s for s in narrative["summary"])
    assert any("YANG TIDAK SESUAI" in s for s in narrative["summary"])


def test_validate_narrative_rejects_banned_phrases_and_hallucinated_rules() -> None:
    pkg = _sample_package()
    banned_candidate = {
        "summary": ["Kasus ini terbukti fraud berdasarkan pemeriksaan."],
        "findings": ["R003_ITEM_MISSING [HIGH]: CLAIM_ITEM_UNSUPPORTED_BY_EVIDENCE."],
        "questions": ["Apakah bukti tersedia?"],
        "limitations": ["Keputusan di tangan manusia."],
    }
    _, valid_banned = validate_narrative(banned_candidate, pkg)
    assert not valid_banned

    hallucinated_rule_candidate = {
        "summary": ["Terdapat temuan R999_FAKE_RULE pada klaim."],
        "findings": ["R999_FAKE_RULE [HIGH]: FAKE."],
        "questions": ["Apakah bukti tersedia?"],
        "limitations": ["Keputusan di tangan manusia."],
    }
    _, valid_rule = validate_narrative(hallucinated_rule_candidate, pkg)
    assert not valid_rule


@pytest.mark.asyncio
async def test_generate_narrative_uses_groq_llm_when_api_key_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_token_123")
    monkeypatch.setenv("NARRATIVE_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "<think>Menganalisis paket deterministik...</think>\n"
                                "```json\n"
                                "{\n"
                                '  "summary": [\n'
                                '    "YANG SESUAI: Kunjungan pasien cocok dan identitas kepesertaan terverifikasi.",\n'
                                '    "YANG TIDAK SESUAI: Tindakan belum memiliki catatan di faskes."\n'
                                "  ],\n"
                                '  "findings": ["R003_ITEM_MISSING [HIGH]: Tindakan/prosedur medis yang ditagihkan tidak ditemukan pada bukti klinis."],\n'
                                '  "questions": ["Apakah terdapat keterlambatan sinkronisasi bukti tindakan dari SIMRS?"],\n'
                                '  "limitations": ["Ringkasan AI ini hanya merangkum indikator deterministik dan bukan keputusan fraud."]\n'
                                "}\n"
                                "```"
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self) -> None:
            self.captured_headers: dict | None = None
            self.captured_json: dict | None = None

        async def post(self, url: str, *, headers: dict, json: dict, timeout: float):
            self.captured_headers = headers
            self.captured_json = json
            return FakeResponse()

    client = FakeClient()
    pkg = _sample_package()
    narrative, status, digest, method, model_info = await generate_narrative(
        pkg, client=client  # type: ignore[arg-type]
    )
    assert status == "VALID"
    assert method == "LLM"
    assert model_info == "groq:llama-3.3-70b-versatile"
    assert len(digest) == 64
    assert narrative["summary"][0].startswith("YANG SESUAI: ")
    assert "ITEM-1" not in str(narrative)
    assert client.captured_headers is not None
    assert client.captured_headers["Authorization"] == "Bearer gsk_test_token_123"
    assert "Budi Santoso" not in str(client.captured_json)
    assert "SYNTHETIC-10001" not in str(client.captured_json)
    assert "ITEM-1" not in client.captured_json["messages"][1]["content"]


@pytest.mark.asyncio
async def test_generate_narrative_falls_back_to_template_on_llm_error_or_banned_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_token_123")
    monkeypatch.setenv("NARRATIVE_PROVIDER", "groq")

    class BadVerdictResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"summary": ["Klaim ini pasti fraud."], "findings": [], "questions": ["?"], "limitations": ["."]}'
                        }
                    }
                ]
            }

    class BadClient:
        async def post(self, url: str, *, headers: dict, json: dict, timeout: float):
            return BadVerdictResponse()

    pkg = _sample_package()
    narrative, status, digest, method, model_info = await generate_narrative(
        pkg, client=BadClient()  # type: ignore[arg-type]
    )
    assert status == "FALLBACK"
    assert method == "TEMPLATE"
    assert model_info == "deterministic-v1-fallback"
    assert len(digest) == 64
    assert "pasti fraud" not in str(narrative).lower()
    assert "ITEM-1" not in str(narrative)


def test_template_stays_valid_for_large_claims_and_has_no_raw_codes() -> None:
    items = [
        {
            "claim_item_ref": f"PROC-{index}",
            "item_type": "PROCEDURE",
            "code_system": "ICD-9-CM",
            "code": "3995",
            "match_result": "MATCHED",
            "reason": "Exact canonical match",
        }
        for index in range(1, 7)
    ]
    package = {
        "assessment": {
            "encounter_match_status": "UNIQUE_MATCH",
            "identity_assurance": "STRONG",
        },
        "items": items,
        "findings": [],
    }
    narrative, status, _ = narrate(package)
    assert status == "VALID"
    assert all(len(line) <= 600 for line in narrative["summary"])
    dumped = json.dumps(narrative)
    assert "UNIQUE_MATCH" not in dumped
    assert "3995" not in dumped
    assert "Hemodialysis" in dumped


def test_llm_output_with_status_codes_is_rejected() -> None:
    candidate = {
        "summary": ["YANG SESUAI: Kunjungan cocok (UNIQUE_MATCH)."],
        "findings": [],
        "questions": [],
        "limitations": [],
    }
    _, ok = validate_narrative(candidate, _sample_package())
    assert ok is False
