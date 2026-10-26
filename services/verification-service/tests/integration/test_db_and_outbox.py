"""Live Gate 4/5 verifier flow through public and internal service boundaries."""

import asyncio
import os
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1", reason="requires the Compose stack"
)
BASE = os.getenv("PUBLIC_BASE_URL", "http://localhost:18080")
SIMRS = "http://localhost:8101/api"


async def token(client: httpx.AsyncClient, client_id: str, secret_env: str) -> str:
    response = await client.post(
        "http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": os.environ[secret_env],
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def eventually(call, predicate, attempts: int = 100):
    last = None
    for _ in range(attempts):
        last = await call()
        if predicate(last):
            return last
        await asyncio.sleep(0.25)
    pytest.fail(f"condition not reached: {getattr(last, 'text', last)}")


@pytest.mark.asyncio
async def test_candidate_snapshot_assessment_duplicates_cache_and_staleness() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        patient = await token(
            client, "test-patient-client", "TEST_PATIENT_CLIENT_SECRET"
        )
        scanner = await token(client, "simrs-a-adapter", "SIMRS_A_CLIENT_SECRET")
        verifier = await token(
            client, "test-verifier-client", "TEST_VERIFIER_CLIENT_SECRET"
        )
        patient_headers, scanner_headers, verifier_headers = (
            {"Authorization": f"Bearer {patient}"},
            {"Authorization": f"Bearer {scanner}"},
            {"Authorization": f"Bearer {verifier}"},
        )

        issued = await client.post(
            f"{BASE}/api/v1/patient/qr-tokens",
            headers=patient_headers,
            json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-001"},
        )
        checked_in = await client.post(
            f"{SIMRS}/scan/check-in",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "qr_token": issued.json()["token"],
                "scanner_external_id": "GATE45-TEST",
                "external_visit_reference": f"VISIT-{uuid4()}",
            },
        )
        assert checked_in.status_code == 200, checked_in.text
        encounter_id = checked_in.json()["encounter_id"]
        await eventually(
            lambda: client.get(
                f"{BASE}/api/v1/integrations/encounters/{encounter_id}/ingestion-status",
                headers=scanner_headers,
            ),
            lambda response: response.status_code == 200,
        )
        clinical = await client.post(
            f"{SIMRS}/visits/{encounter_id}/clinical-events",
            json={
                "event_type": "PROCEDURE",
                "code_system": "DEMO-PROCEDURE-CATALOG",
                "code": "PROC-001",
                "display": "Konsultasi dokter",
            },
        )
        assert clinical.status_code == 201, clinical.text
        await eventually(
            lambda: client.get(f"{SIMRS}/visits/{encounter_id}/sync-status"),
            lambda response: response.status_code == 200
            and response.json()["pending"] == 0,
        )
        checkout_qr = await client.post(
            f"{BASE}/api/v1/patient/qr-tokens",
            headers=patient_headers,
            json={
                "purpose": "CHECK_OUT",
                "encounter_id": encounter_id,
                "facility_hint": "HOSP-DEMO-001",
            },
        )
        checked_out = await client.post(
            f"{SIMRS}/scan/check-out",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "qr_token": checkout_qr.json()["token"],
                "scanner_external_id": "GATE45-TEST",
            },
        )
        assert checked_out.status_code == 200
        assert (
            await client.post(f"{SIMRS}/visits/{encounter_id}/sync-complete")
        ).status_code == 200
        await eventually(
            lambda: client.get(f"{SIMRS}/visits/{encounter_id}/sync-status"),
            lambda response: response.status_code == 200
            and response.json()["sync_status"] == "SYNC_COMPLETE",
        )

        started_at = datetime.fromisoformat(checked_in.json()["created_at"])
        ended_at = datetime.fromisoformat(checked_out.json()["checked_out_at"])
        body = {
            "claim_source": "SYNTHETIC-VERIFIER",
            "claim_id": f"CLAIM-{uuid4()}",
            "claim_revision": "1",
            "patient": {"participant_number": "SYNTHETIC-10001"},
            "facility": {"namespace": "DEMO-FASKES", "code": "HOSP-DEMO-001"},
            "service_period": {
                "start": (started_at - timedelta(seconds=1)).isoformat(),
                "end": (ended_at + timedelta(seconds=1)).isoformat(),
            },
            "items": [
                {
                    "item_ref": "ITEM-1",
                    "item_type": "PROCEDURE",
                    "code_system": "DEMO-PROCEDURE-CATALOG",
                    "code": "PROC-001",
                    "quantity": 1,
                    "unit": "1",
                }
            ],
        }
        key = str(uuid4())
        queued = await client.post(
            f"{BASE}/api/v1/verifications",
            headers=verifier_headers | {"Idempotency-Key": key},
            json=body,
        )
        assert queued.status_code == 202, queued.text
        replay = await client.post(
            f"{BASE}/api/v1/verifications",
            headers=verifier_headers | {"Idempotency-Key": key},
            json=body,
        )
        assert (
            replay.status_code == 200
            and replay.json()["verification_id"] == queued.json()["verification_id"]
        )
        verification_id = queued.json()["verification_id"]
        assessment_response = await eventually(
            lambda: client.get(
                f"{BASE}/api/v1/verifications/{verification_id}",
                headers=verifier_headers,
            ),
            lambda response: response.status_code == 200
            and response.json()["status"] == "COMPLETED",
        )
        assessment = assessment_response.json()
        assert assessment["encounter_match_status"] == "UNIQUE_MATCH"
        assert assessment["selected_encounter_id"] == encounter_id
        assert assessment["evidence_reconciliation_status"] == "ITEMS_CONSISTENT"
        assert assessment["final_fraud_decision"] is None
        candidates = await client.get(
            f"{BASE}/api/v1/verifications/{verification_id}/candidates",
            headers=verifier_headers,
        )
        assert (
            candidates.status_code == 200
            and len(candidates.json()) == assessment["evaluated_candidate_count"] == 1
        )

        cached = await client.post(
            f"{BASE}/api/v1/verifications",
            headers=verifier_headers | {"Idempotency-Key": str(uuid4())},
            json=body,
        )
        cached_assessment = await eventually(
            lambda: client.get(
                f"{BASE}/api/v1/verifications/{cached.json()['verification_id']}",
                headers=verifier_headers,
            ),
            lambda response: response.status_code == 200
            and response.json()["status"] == "COMPLETED",
        )
        assert cached_assessment.json()["run_id"] == assessment["run_id"]

        duplicate_body = body | {"claim_id": f"CLAIM-{uuid4()}"}
        duplicate = await client.post(
            f"{BASE}/api/v1/verifications",
            headers=verifier_headers | {"Idempotency-Key": str(uuid4())},
            json=duplicate_body,
        )
        duplicate_id = duplicate.json()["verification_id"]
        duplicate_assessment = await eventually(
            lambda: client.get(
                f"{BASE}/api/v1/verifications/{duplicate_id}", headers=verifier_headers
            ),
            lambda response: response.status_code == 200
            and response.json()["status"] == "COMPLETED",
        )
        assert duplicate_assessment.json()["duplicate_assessment_status"] in {
            "POTENTIAL_ENCOUNTER_REUSE",
            "POTENTIAL_EVIDENCE_REUSE",
        }
        findings = (
            await client.get(
                f"{BASE}/api/v1/verifications/{duplicate_id}/findings",
                headers=verifier_headers,
            )
        ).json()
        assert {row["rule_id"] for row in findings}.intersection({"R007", "R008"})

        correction = await client.post(
            f"{SIMRS}/clinical-records/{clinical.json()['record_id']}/corrections",
            json={
                "code_system": "DEMO-PROCEDURE-CATALOG",
                "code": "PROC-002",
                "display": "Konsultasi dikoreksi",
                "change_reason": "Gate 5 stale test",
            },
        )
        assert correction.status_code == 201
        stale = await eventually(
            lambda: client.get(
                f"{BASE}/api/v1/verifications/{verification_id}",
                headers=verifier_headers,
            ),
            lambda response: response.status_code == 200
            and response.json()["data_freshness"] == "STALE_INPUT",
        )
        assert stale.json()["final_fraud_decision"] is None
        rechecked = await client.post(
            f"{BASE}/api/v1/verifications/{verification_id}/re-evaluate",
            headers=verifier_headers | {"Idempotency-Key": str(uuid4())},
            json={},
        )
        assert rechecked.status_code == 202
        revised = await eventually(
            lambda: client.get(
                f"{BASE}/api/v1/verifications/{verification_id}",
                headers=verifier_headers,
            ),
            lambda response: response.status_code == 200
            and response.json()["status"] == "COMPLETED"
            and response.json()["run_id"] == rechecked.json()["run_id"],
        )
        assert (
            revised.json()["data_freshness"] == "CURRENT"
            and revised.json()["run_id"] != assessment["run_id"]
        )
        history = await client.get(
            f"{BASE}/api/v1/verifications/history",
            headers=verifier_headers,
            params={"claim_source": body["claim_source"], "claim_id": body["claim_id"]},
        )
        assert history.status_code == 200 and len(history.json()) >= 2
