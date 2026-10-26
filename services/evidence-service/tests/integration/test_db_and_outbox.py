"""Live Gate 2/3 acceptance flow through SIMRS-A and the public gateway."""

import asyncio
import os
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


async def eventually(call, predicate, *, attempts: int = 80):
    last = None
    for _ in range(attempts):
        last = await call()
        if predicate(last):
            return last
        await asyncio.sleep(0.25)
    pytest.fail(
        f"condition was not reached; last response: {getattr(last, 'text', last)}"
    )


@pytest.mark.asyncio
async def test_explicit_watermark_frozen_summary_confirmation_and_reconfirmation() -> (
    None
):
    async with httpx.AsyncClient(timeout=20) as client:
        patient = await token(
            client, "test-patient-client", "TEST_PATIENT_CLIENT_SECRET"
        )
        patient_two = await token(
            client, "test-patient-2-client", "TEST_PATIENT_2_CLIENT_SECRET"
        )
        scanner = await token(client, "simrs-a-adapter", "SIMRS_A_CLIENT_SECRET")
        scanner_b = await token(client, "simrs-b-adapter", "SIMRS_B_CLIENT_SECRET")
        patient_headers = {"Authorization": f"Bearer {patient}"}
        scanner_headers = {"Authorization": f"Bearer {scanner}"}

        issued = await client.post(
            f"{BASE}/api/v1/patient/qr-tokens",
            headers=patient_headers,
            json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-001"},
        )
        assert issued.status_code == 201, issued.text
        checked_in = await client.post(
            f"{SIMRS}/scan/check-in",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "qr_token": issued.json()["token"],
                "scanner_external_id": "GATE23-TEST",
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
        cross_tenant = await client.get(
            f"{BASE}/api/v1/integrations/encounters/{encounter_id}/ingestion-status",
            headers={"Authorization": f"Bearer {scanner_b}"},
        )
        assert cross_tenant.status_code == 404

        events = [
            {
                "event_type": "PROCEDURE",
                "code_system": "DEMO-PROCEDURE-CATALOG",
                "code": "PROC-001",
                "display": "Konsultasi dokter",
            },
            {
                "event_type": "DIAGNOSIS",
                "code_system": "DEMO-DIAGNOSIS-CATALOG",
                "code": "DIAG-001",
                "display": "Diagnosis ISPA",
            },
            {
                "event_type": "MEDICATION_PRESCRIBED",
                "code_system": "DEMO-MEDICATION-CATALOG",
                "code": "MED-001",
                "display": "Resep amoksisilin",
                "quantity": "10",
                "unit": "tablet",
            },
            {
                "event_type": "MEDICATION_DISPENSED",
                "code_system": "DEMO-MEDICATION-CATALOG",
                "code": "MED-001",
                "display": "Amoksisilin diserahkan",
                "quantity": "10",
                "unit": "tablet",
            },
        ]
        created = []
        for event in events:
            response = await client.post(
                f"{SIMRS}/visits/{encounter_id}/clinical-events", json=event
            )
            assert response.status_code == 201, response.text
            created.append(response.json())
        await eventually(
            lambda: client.get(f"{SIMRS}/visits/{encounter_id}/sync-status"),
            lambda response: response.status_code == 200
            and response.json()["pending"] == 0
            and response.json()["delivered"] == 4,
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
        assert checkout_qr.status_code == 201, checkout_qr.text
        checked_out = await client.post(
            f"{SIMRS}/scan/check-out",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "qr_token": checkout_qr.json()["token"],
                "scanner_external_id": "GATE23-TEST",
            },
        )
        assert checked_out.status_code == 200, checked_out.text

        unavailable = await client.get(
            f"{BASE}/api/v1/patient/encounters/{encounter_id}/checkout-summary",
            headers=patient_headers,
        )
        assert unavailable.status_code == 409
        assert "items" not in unavailable.json()

        gap = await client.post(
            f"{BASE}/api/v1/integrations/encounters/{encounter_id}/sync-complete",
            headers=scanner_headers,
            json={
                "source_system": "SIMRS-A",
                "last_source_sequence": 5,
                "marked_complete_at": "2026-10-26T00:00:00Z",
            },
        )
        assert gap.status_code == 200
        assert gap.json()["sync_status"] == "INCOMPLETE_SYNC"
        still_unavailable = await client.get(
            f"{BASE}/api/v1/patient/encounters/{encounter_id}/checkout-summary",
            headers=patient_headers,
        )
        assert (
            still_unavailable.status_code == 409
            and "items" not in still_unavailable.json()
        )

        completed = await client.post(f"{SIMRS}/visits/{encounter_id}/sync-complete")
        assert completed.status_code == 200, completed.text
        await eventually(
            lambda: client.get(f"{SIMRS}/visits/{encounter_id}/sync-status"),
            lambda response: response.status_code == 200
            and response.json()["pending"] == 0
            and response.json()["sync_status"] == "SYNC_COMPLETE",
        )
        summary_response = await eventually(
            lambda: client.get(
                f"{BASE}/api/v1/patient/encounters/{encounter_id}/checkout-summary",
                headers=patient_headers,
            ),
            lambda response: response.status_code == 200,
        )
        summary = summary_response.json()
        assert summary["status"] == "READY"
        assert {item["kind"] for item in summary["items"]} == {
            "DIAGNOSIS",
            "PROCEDURE",
            "MEDICATION_DISPENSE",
        }
        assert all("Resep" not in item["description"] for item in summary["items"])
        repeated_watermark = await client.post(
            f"{BASE}/api/v1/integrations/encounters/{encounter_id}/sync-complete",
            headers=scanner_headers,
            json={
                "source_system": "SIMRS-A",
                "last_source_sequence": 4,
                "marked_complete_at": "2026-10-26T00:01:00Z",
            },
        )
        assert repeated_watermark.status_code == 200
        assert repeated_watermark.json()["snapshot_id"] == summary["snapshot_id"]

        unauthorized = await client.get(
            f"{BASE}/api/v1/patient/encounters/{encounter_id}/checkout-summary",
            headers={"Authorization": f"Bearer {patient_two}"},
        )
        assert unauthorized.status_code == 404

        items = [
            {
                "evidence_id": item["evidence_id"],
                "response": "DISPUTED",
                "reason": "MEDICATION_NOT_RECEIVED",
            }
            if item["kind"] == "MEDICATION_DISPENSE"
            else {"evidence_id": item["evidence_id"], "response": "CONFIRMED"}
            for item in summary["items"]
        ]
        response_key = str(uuid4())
        recorded = await client.post(
            f"{BASE}/api/v1/patient/checkout-summaries/{summary['snapshot_id']}/responses",
            headers=patient_headers | {"Idempotency-Key": response_key},
            json={"overall_response": "PARTIALLY_DISPUTED", "items": items},
        )
        assert recorded.status_code == 201, recorded.text
        replay = await client.post(
            f"{BASE}/api/v1/patient/checkout-summaries/{summary['snapshot_id']}/responses",
            headers=patient_headers | {"Idempotency-Key": response_key},
            json={"overall_response": "PARTIALLY_DISPUTED", "items": items},
        )
        assert replay.status_code == 200

        correction = await client.post(
            f"{SIMRS}/clinical-records/{created[0]['record_id']}/corrections",
            json={
                "code_system": "DEMO-PROCEDURE-CATALOG",
                "code": "PROC-002",
                "display": "Konsultasi dokter dikoreksi",
                "change_reason": "Koreksi administrasi",
            },
        )
        assert correction.status_code == 201, correction.text
        await eventually(
            lambda: client.get(f"{SIMRS}/visits/{encounter_id}/sync-status"),
            lambda response: response.status_code == 200
            and response.json()["pending"] == 0
            and any(row["version"] == 2 for row in response.json()["records"]),
        )
        outdated = await client.get(
            f"{BASE}/api/v1/patient/encounters/{encounter_id}/checkout-summary",
            headers=patient_headers,
        )
        assert outdated.status_code == 409

        assert (
            await client.post(f"{SIMRS}/visits/{encounter_id}/sync-complete")
        ).status_code == 200
        await eventually(
            lambda: client.get(f"{SIMRS}/visits/{encounter_id}/sync-status"),
            lambda response: response.status_code == 200
            and response.json()["pending"] == 0
            and response.json()["sync_status"] == "SYNC_COMPLETE",
        )
        revised_response = await eventually(
            lambda: client.get(
                f"{BASE}/api/v1/patient/encounters/{encounter_id}/checkout-summary",
                headers=patient_headers,
            ),
            lambda response: response.status_code == 200
            and response.json()["evidence_revision"] == 5,
        )
        assert revised_response.json()["snapshot_id"] != summary["snapshot_id"]
        assert any(
            item["description"] == "Konsultasi dokter dikoreksi"
            for item in revised_response.json()["items"]
        )
        old_response = await client.get(
            f"{BASE}/api/v1/patient/checkout-summaries/{summary['snapshot_id']}/response",
            headers=patient_headers,
        )
        assert old_response.status_code == 200
        assert old_response.json()["snapshot_status"] == "RECONFIRMATION_REQUIRED"
        declined = await client.post(
            f"{BASE}/api/v1/patient/checkout-summaries/{revised_response.json()['snapshot_id']}/responses",
            headers=patient_headers | {"Idempotency-Key": str(uuid4())},
            json={"overall_response": "DECLINED", "items": []},
        )
        assert (
            declined.status_code == 201
            and declined.json()["overall_response"] == "DECLINED"
        )
        encounters = await client.get(
            f"{BASE}/api/v1/patient/encounters", headers=patient_headers
        )
        assert (
            next(
                item
                for item in encounters.json()["items"]
                if item["encounter_id"] == encounter_id
            )["status"]
            == "CHECKED_OUT"
        )

        quarantined = await client.post(
            f"{BASE}/api/v1/integrations/encounters/{encounter_id}/corrections",
            headers=scanner_headers,
            json={
                "source_event_id": f"OUT-OF-ORDER-{uuid4()}",
                "source_system": "SIMRS-A",
                "source_sequence": 6,
                "external_record_id": created[0]["external_record_id"],
                "record_version": 4,
                "occurred_at": "2026-10-26T00:02:00Z",
                "source_updated_at": "2026-10-26T00:02:00Z",
                "change_reason": "Simulated missing version",
                "actor": {"external_id": "TEST", "role": "CLINICIAN"},
                "content": {
                    "code_system": "DEMO-PROCEDURE-CATALOG",
                    "code": "PROC-004",
                    "display": "Out of order",
                },
            },
        )
        assert (
            quarantined.status_code == 201
            and quarantined.json()["status"] == "QUARANTINED"
        )
        quarantine_status = await client.post(
            f"{BASE}/api/v1/integrations/encounters/{encounter_id}/sync-complete",
            headers=scanner_headers,
            json={
                "source_system": "SIMRS-A",
                "last_source_sequence": 6,
                "marked_complete_at": "2026-10-26T00:03:00Z",
            },
        )
        assert (
            quarantine_status.status_code == 200
            and quarantine_status.json()["sync_status"] == "QUARANTINE_PENDING"
        )
        blocked = await client.get(
            f"{BASE}/api/v1/patient/encounters/{encounter_id}/checkout-summary",
            headers=patient_headers,
        )
        assert blocked.status_code == 409 and "items" not in blocked.json()

        duplicate_payload = {
            "source_event_id": f"DUPLICATE-{uuid4()}",
            "source_system": "SIMRS-A",
            "source_sequence": 7,
            "external_record_id": f"DIRECT-{uuid4()}",
            "event_type": "DOCUMENT_FINGERPRINT",
            "record_version": 1,
            "occurred_at": "2026-10-26T00:04:00Z",
            "actor": {"external_id": "TEST", "role": "SYSTEM"},
            "content": {
                "code_system": "LOCAL",
                "code": "DOC-001",
                "display": "Document fingerprint",
            },
        }
        first_delivery = await client.post(
            f"{BASE}/api/v1/integrations/encounters/{encounter_id}/events",
            headers=scanner_headers,
            json=duplicate_payload,
        )
        replay_delivery = await client.post(
            f"{BASE}/api/v1/integrations/encounters/{encounter_id}/events",
            headers=scanner_headers,
            json=duplicate_payload,
        )
        assert first_delivery.status_code == 201 and replay_delivery.status_code == 200
        assert (
            replay_delivery.json()["evidence_id"]
            == first_delivery.json()["evidence_id"]
        )
