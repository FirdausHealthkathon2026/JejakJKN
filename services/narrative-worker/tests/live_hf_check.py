"""Run unit checks and (if GROQ_API_KEY is set) a live Groq narrative generation test."""

import json
import os
from pathlib import Path
import sys
import urllib.error

ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from app.domain.narrator import minimize_package, narrate, validate_narrative  # noqa: E402
from app.infrastructure.llm_adapter import (  # noqa: E402
    _build_request,
    _post_urllib,
    generate_narrative,
    generate_narrative_sync,
    get_groq_api_key,
)


def _step_sync(coro):
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    raise RuntimeError("Coroutine did not complete synchronously")


def _load_dotenv_if_present() -> None:
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


SAMPLE_PACKAGE = {
    "participant_number": "SYNTHETIC-10001",
    "patient_name": "Budi Santoso",
    "data_freshness": "CURRENT",
    "assessment": {
        "encounter_match_status": "UNIQUE_MATCH",
        "identity_assurance": "VERIFIED_PARTICIPANT_ID",
        "evidence_reconciliation_status": "ITEM_MISMATCH",
        "duplicate_assessment_status": "NO_REUSE_FOUND_IN_JEJAKJKN_HISTORY",
        "patient_confirmation_status": "PARTIALLY_DISPUTED",
        "review_required": True,
        "final_fraud_decision": None,
    },
    "candidates": [
        {
            "encounter_id": "8cf5dc3e-0d47-4b21-8143-b232452a2e73",
            "match_state": "ELIGIBLE_PARTIAL_MATCH",
            "reasons": ["Procedure matched, medication disputed by patient"],
        }
    ],
    "items": [
        {
            "claim_item_ref": "ITEM-1",
            "match_result": "MATCHED",
            "reason": "Matched procedure PROC-EXAM-EYE",
        },
        {
            "claim_item_ref": "ITEM-2",
            "match_result": "PATIENT_DISPUTED",
            "reason": "Patient disputed receiving Paracetamol 500 mg (10 tablet)",
        },
    ],
    "findings": [
        {
            "rule_id": "R005_PATIENT_DISPUTE",
            "severity": "HIGH",
            "finding_code": "PATIENT_DISPUTED_CLAIMED_ITEM",
            "claim_item_ref": "ITEM-2",
            "explanation_facts": {
                "item_ref": "ITEM-2",
                "patient_response": "DISPUTED",
                "reason_code": "MEDICATION_NOT_RECEIVED",
            },
            "limitations": "Sanggahan pasien memerlukan klarifikasi bukti penyerahan farmasi SIMRS, bukan bukti otomatis layanan fiktif.",
        }
    ],
}


def run_offline_checks() -> None:
    minimized = minimize_package(SAMPLE_PACKAGE)
    assert "SYNTHETIC-10001" not in json.dumps(minimized)
    assert "Budi Santoso" not in json.dumps(minimized)
    det_narrative, det_status, det_digest = narrate(SAMPLE_PACKAGE)
    assert det_status == "VALID" and len(det_digest) == 64
    _, ok = validate_narrative(det_narrative, SAMPLE_PACKAGE)
    assert ok is True

    prev_key = os.environ.get("GROQ_API_KEY")
    prev_provider = os.environ.get("NARRATIVE_PROVIDER")
    try:
        os.environ["GROQ_API_KEY"] = "gsk_mock_token"
        os.environ["NARRATIVE_PROVIDER"] = "groq"

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "<think>Menganalisis temuan...</think>\n```json\n"
                                    + json.dumps(
                                        {
                                            "summary": [
                                                "Kunjungan cocok unik (UNIQUE_MATCH), namun ITEM-2 disanggah oleh pasien."
                                            ],
                                            "findings": [
                                                "R005_PATIENT_DISPUTE [HIGH]: Pasien menyanggah penerimaan obat pada ITEM-2."
                                            ],
                                            "questions": [
                                                "Apakah bukti penyerahan obat di instalasi farmasi SIMRS sesuai dengan klaim?"
                                            ],
                                            "limitations": [
                                                "Ringkasan AI ini merangkum temuan deterministik dan bukan keputusan fraud."
                                            ],
                                        }
                                    )
                                    + "\n```"
                                )
                            }
                        }
                    ]
                }

        class FakeClient:
            async def post(self, url: str, *, headers: dict, json: dict, timeout: float):
                return FakeResponse()

        narrative, status, digest, method, model_info = _step_sync(
            generate_narrative(SAMPLE_PACKAGE, client=FakeClient())
        )
        assert status == "VALID" and method == "LLM" and len(digest) == 64
        assert model_info.startswith("groq:")
    finally:
        if prev_key is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = prev_key
        if prev_provider is None:
            os.environ.pop("NARRATIVE_PROVIDER", None)
        else:
            os.environ["NARRATIVE_PROVIDER"] = prev_provider

    print("[OK] Offline narrator, PII minimization, mock Groq LLM, and schema guardrails passed.")


def main() -> None:
    _load_dotenv_if_present()
    run_offline_checks()

    if os.getenv("SKIP_LIVE_GROQ") == "1" or os.getenv("SKIP_LIVE_HF") == "1":
        return

    token = get_groq_api_key()
    if not token:
        print("[INFO] GROQ_API_KEY is not set. Skipping live Groq API call.")
        return

    os.environ.setdefault("NARRATIVE_PROVIDER", "groq")
    print("[INFO] Calling Groq Chat Completions API...")

    api_url, model_name, headers, payload, timeout_seconds, digest = _build_request(
        SAMPLE_PACKAGE
    )
    try:
        raw_body = _post_urllib(api_url, headers, payload, timeout_seconds)
        print("[DEBUG] Raw Groq message:", raw_body["choices"][0]["message"]["content"])
    except urllib.error.HTTPError as e:
        print(f"[DEBUG] HTTPError {e.code}: {e.read().decode('utf-8', errors='replace')}")
    except Exception as e:
        print(f"[DEBUG] Exception {type(e).__name__}: {e}")

    narrative, status, digest, method, model_info = generate_narrative_sync(
        SAMPLE_PACKAGE
    )
    print(
        json.dumps(
            {
                "method": method,
                "model_info": model_info,
                "validation_status": status,
                "input_digest": digest,
                "narrative": narrative,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

