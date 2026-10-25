"""Live Gate 1 flow; run after make up/migrate/seed with RUN_LIVE_TESTS=1."""

import os
import subprocess
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="requires the Compose stack")
BASE = os.getenv("PUBLIC_BASE_URL", "http://localhost:18080")


async def token(client: httpx.AsyncClient, client_id: str, secret_env: str) -> str:
    response = await client.post(
        "http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token",
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": os.environ[secret_env]},
    )
    response.raise_for_status()
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_qr_checkin_replay_checkout_and_patient_visibility() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        patient_token = await token(client, "test-patient-client", "TEST_PATIENT_CLIENT_SECRET")
        scanner_token = await token(client, "simrs-a-adapter", "SIMRS_A_CLIENT_SECRET")
        issued = await client.post(
            f"{BASE}/api/v1/patient/qr-tokens",
            headers={"Authorization": f"Bearer {patient_token}"},
            json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-001"},
        )
        assert issued.status_code == 201, issued.text
        idempotency_key = str(uuid4())
        scan_body = {"qr_token": issued.json()["token"], "facility_external_code": "HOSP-DEMO-001", "scanner_external_id": "TEST-SCANNER", "external_visit_reference": f"VISIT-{uuid4()}"}
        first = await client.post(f"{BASE}/api/v1/integrations/qr/check-in", headers={"Authorization": f"Bearer {scanner_token}", "Idempotency-Key": idempotency_key}, json=scan_body)
        assert first.status_code == 201, first.text
        replay = await client.post(f"{BASE}/api/v1/integrations/qr/check-in", headers={"Authorization": f"Bearer {scanner_token}", "Idempotency-Key": idempotency_key}, json=scan_body)
        assert replay.status_code == 200
        conflict = await client.post(f"{BASE}/api/v1/integrations/qr/check-in", headers={"Authorization": f"Bearer {scanner_token}", "Idempotency-Key": str(uuid4())}, json=scan_body)
        assert conflict.status_code == 409

        encounter_id = first.json()["encounter_id"]
        listed = await client.get(f"{BASE}/api/v1/patient/encounters", headers={"Authorization": f"Bearer {patient_token}"})
        assert listed.status_code == 200
        item = next(item for item in listed.json()["items"] if item["encounter_id"] == encounter_id)
        assert item["status"] == "OPEN" and "stages" not in item

        checkout_qr = await client.post(
            f"{BASE}/api/v1/patient/qr-tokens",
            headers={"Authorization": f"Bearer {patient_token}"},
            json={"purpose": "CHECK_OUT", "encounter_id": encounter_id, "facility_hint": "HOSP-DEMO-001"},
        )
        assert checkout_qr.status_code == 201
        checkout = await client.post(
            f"{BASE}/api/v1/integrations/qr/check-out",
            headers={"Authorization": f"Bearer {scanner_token}", "Idempotency-Key": str(uuid4())},
            json={"qr_token": checkout_qr.json()["token"], "facility_external_code": "HOSP-DEMO-001", "scanner_external_id": "TEST-SCANNER"},
        )
        assert checkout.status_code == 200, checkout.text
        assert checkout.json()["encounter_status"] == "CHECKED_OUT"

        command = ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "encounter_db", "-Atc", f"SELECT (SELECT count(*) FROM encounters WHERE id='{encounter_id}') || ':' || (SELECT count(*) FROM outbox_events WHERE aggregate_id='{encounter_id}')"]
        counts = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
        assert counts == "1:2"


@pytest.mark.asyncio
async def test_facility_binding_tamper_ownership_invalid_state_and_exception() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        patient = await token(client, "test-patient-client", "TEST_PATIENT_CLIENT_SECRET")
        patient_two = await token(client, "test-patient-2-client", "TEST_PATIENT_2_CLIENT_SECRET")
        scanner = await token(client, "simrs-a-adapter", "SIMRS_A_CLIENT_SECRET")

        facility_bound = await client.post(f"{BASE}/api/v1/patient/qr-tokens", headers={"Authorization": f"Bearer {patient}"}, json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-002"})
        denied = await client.post(f"{BASE}/api/v1/integrations/qr/check-in", headers={"Authorization": f"Bearer {scanner}", "Idempotency-Key": str(uuid4())}, json={"qr_token": facility_bound.json()["token"], "facility_external_code": "HOSP-DEMO-001", "scanner_external_id": "TEST"})
        assert denied.status_code == 403 and denied.json()["error_code"] == "FACILITY_MISMATCH"

        issued = await client.post(f"{BASE}/api/v1/patient/qr-tokens", headers={"Authorization": f"Bearer {patient}"}, json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-001"})
        original = issued.json()["token"]
        header, payload, signature = original.split(".")
        payload = ("A" if payload[0] != "A" else "B") + payload[1:]
        tampered = ".".join((header, payload, signature))
        invalid = await client.post(f"{BASE}/api/v1/integrations/qr/check-in", headers={"Authorization": f"Bearer {scanner}", "Idempotency-Key": str(uuid4())}, json={"qr_token": tampered, "facility_external_code": "HOSP-DEMO-001", "scanner_external_id": "TEST"})
        assert invalid.status_code == 401

        scan = await client.post(f"{BASE}/api/v1/integrations/qr/check-in", headers={"Authorization": f"Bearer {scanner}", "Idempotency-Key": str(uuid4())}, json={"qr_token": original, "facility_external_code": "HOSP-DEMO-001", "scanner_external_id": "TEST"})
        encounter_id = scan.json()["encounter_id"]
        other_patient = await client.post(f"{BASE}/api/v1/patient/qr-tokens", headers={"Authorization": f"Bearer {patient_two}"}, json={"purpose": "CHECK_OUT", "encounter_id": encounter_id, "facility_hint": "HOSP-DEMO-001"})
        assert other_patient.status_code == 404

        checkout_qr = await client.post(f"{BASE}/api/v1/patient/qr-tokens", headers={"Authorization": f"Bearer {patient}"}, json={"purpose": "CHECK_OUT", "encounter_id": encounter_id, "facility_hint": "HOSP-DEMO-001"})
        checkout = await client.post(f"{BASE}/api/v1/integrations/qr/check-out", headers={"Authorization": f"Bearer {scanner}", "Idempotency-Key": str(uuid4())}, json={"qr_token": checkout_qr.json()["token"], "facility_external_code": "HOSP-DEMO-001", "scanner_external_id": "TEST"})
        assert checkout.status_code == 200
        invalid_state = await client.post(f"{BASE}/api/v1/patient/qr-tokens", headers={"Authorization": f"Bearer {patient}"}, json={"purpose": "CHECK_OUT", "encounter_id": encounter_id, "facility_hint": "HOSP-DEMO-001"})
        assert invalid_state.status_code == 409

        exception_id = str(uuid4())
        exception = await client.post(
            f"{BASE}/api/v1/integrations/encounters/{exception_id}/exceptions",
            headers={"Authorization": f"Bearer {scanner}"},
            json={"exception_phase": "CHECK_IN", "reason_code": "NO_SMARTPHONE", "patient_id": "10000000-0000-4000-8000-000000000001", "facility_external_code": "HOSP-DEMO-001", "approved_by": "STAFF-TEST"},
        )
        assert exception.status_code == 201, exception.text
        assert exception.json()["presence_status"] == "EXCEPTION_DOCUMENTED"
