"""QR-10 disruptive live check; explicitly opt in with RUN_DISRUPTIVE_TESTS=1."""

import os
import subprocess
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_DISRUPTIVE_TESTS") != "1", reason="stops the Compose Redis container")
BASE = os.getenv("PUBLIC_BASE_URL", "http://localhost:18080")


@pytest.mark.asyncio
async def test_qr_redeem_fails_closed_when_redis_is_down() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        async def access_token(client_id: str, secret: str) -> str:
            response = await client.post("http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token", data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret})
            response.raise_for_status()
            return response.json()["access_token"]

        patient = await access_token("test-patient-client", os.environ["TEST_PATIENT_CLIENT_SECRET"])
        scanner = await access_token("simrs-a-adapter", os.environ["SIMRS_A_CLIENT_SECRET"])
        issued = await client.post(f"{BASE}/api/v1/patient/qr-tokens", headers={"Authorization": f"Bearer {patient}"}, json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-001"})
        issued.raise_for_status()
        subprocess.run(["docker", "compose", "stop", "redis"], check=True)
        try:
            response = await client.post(f"{BASE}/api/v1/integrations/qr/check-in", headers={"Authorization": f"Bearer {scanner}", "Idempotency-Key": str(uuid4())}, json={"qr_token": issued.json()["token"], "facility_external_code": "HOSP-DEMO-001", "scanner_external_id": "OUTAGE-TEST"})
            assert response.status_code == 503
            encounter_id = response.json().get("encounter_id")
            assert encounter_id is None
        finally:
            subprocess.run(["docker", "compose", "start", "redis"], check=True)
