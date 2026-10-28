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


def test_minimize_package_strips_pii() -> None:
    pkg = _sample_package()
    minimized = minimize_package(pkg)
    dumped = str(minimized)
    assert "SYNTHETIC-10001" not in dumped
    assert "Budi Santoso" not in dumped
    assert minimized["assessment"]["final_fraud_decision"] is None


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
                                '  "summary": ["Kunjungan cocok unik (UNIQUE_MATCH), namun ITEM-1 belum didukung bukti."],\n'
                                '  "findings": ["R003_ITEM_MISSING [HIGH]: Item klaim ITEM-1 tidak ditemukan pada bukti klinis."],\n'
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
    assert "UNIQUE_MATCH" in narrative["summary"][0]
    assert client.captured_headers is not None
    assert client.captured_headers["Authorization"] == "Bearer gsk_test_token_123"
    assert "Budi Santoso" not in str(client.captured_json)
    assert "SYNTHETIC-10001" not in str(client.captured_json)


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
