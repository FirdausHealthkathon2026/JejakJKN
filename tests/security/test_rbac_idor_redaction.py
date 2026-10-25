"""Gate 1 live role-boundary checks; later security cases stay in later gates."""

import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="requires the Compose stack")
BASE = os.getenv("PUBLIC_BASE_URL", "http://localhost:18080")


async def get_token(client: httpx.AsyncClient, client_id: str, secret: str) -> str:
    response = await client.post("http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token", data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret})
    response.raise_for_status()
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_patient_cannot_call_scanner_and_scanner_cannot_issue_patient_qr() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        patient = await get_token(client, "test-patient-client", os.environ["TEST_PATIENT_CLIENT_SECRET"])
        scanner = await get_token(client, "simrs-a-adapter", os.environ["SIMRS_A_CLIENT_SECRET"])
        scanner_call = await client.post(
            f"{BASE}/api/v1/integrations/qr/check-in",
            headers={"Authorization": f"Bearer {patient}", "Idempotency-Key": "00000000-0000-4000-8000-000000000001"},
            json={"qr_token": "x" * 32, "facility_external_code": "HOSP-DEMO-001", "scanner_external_id": "BAD"},
        )
        assert scanner_call.status_code == 403
        patient_call = await client.post(
            f"{BASE}/api/v1/patient/qr-tokens",
            headers={"Authorization": f"Bearer {scanner}"},
            json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-001"},
        )
        assert patient_call.status_code == 403
