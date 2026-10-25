"""QR-03 live test. VM-17 belongs to Gate 5 and remains unimplemented."""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="requires the Compose stack")
BASE = os.getenv("PUBLIC_BASE_URL", "http://localhost:18080")


async def get_token(client: httpx.AsyncClient, client_id: str, secret: str) -> str:
    response = await client.post("http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token", data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret})
    response.raise_for_status()
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_one_of_100_concurrent_scans_creates_the_encounter() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        patient = await get_token(client, "test-patient-client", os.environ["TEST_PATIENT_CLIENT_SECRET"])
        scanner = await get_token(client, "simrs-a-adapter", os.environ["SIMRS_A_CLIENT_SECRET"])
        issued = await client.post(f"{BASE}/api/v1/patient/qr-tokens", headers={"Authorization": f"Bearer {patient}"}, json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-001"})
        issued.raise_for_status()
        body = {"qr_token": issued.json()["token"], "facility_external_code": "HOSP-DEMO-001", "scanner_external_id": "RACE-SCANNER"}

        async def scan() -> int:
            response = await client.post(f"{BASE}/api/v1/integrations/qr/check-in", headers={"Authorization": f"Bearer {scanner}", "Idempotency-Key": str(uuid4())}, json=body)
            return response.status_code

        statuses = await asyncio.gather(*(scan() for _ in range(100)))
        assert statuses.count(201) == 1
        assert statuses.count(409) == 99
