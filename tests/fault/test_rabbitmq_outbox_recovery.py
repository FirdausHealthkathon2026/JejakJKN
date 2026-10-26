import asyncio
import os
import subprocess
from uuid import uuid4

import httpx
import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_FAULT_TESTS") != "1",
    reason="requires destructive local fault injection",
)
BASE = os.getenv("PUBLIC_BASE_URL", "http://localhost:18080")


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args], check=True, capture_output=True, text=True
    )


@pytest.mark.asyncio
async def test_domain_commit_survives_broker_outage_and_outbox_recovers() -> None:
    async with httpx.AsyncClient(timeout=20) as client:

        async def token(client_id: str, secret: str) -> str:
            response = await client.post(
                "http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": secret,
                },
            )
            response.raise_for_status()
            return response.json()["access_token"]

        patient = await token(
            "test-patient-client", os.environ["TEST_PATIENT_CLIENT_SECRET"]
        )
        scanner = await token("simrs-a-adapter", os.environ["SIMRS_A_CLIENT_SECRET"])
        issued = await client.post(
            f"{BASE}/api/v1/patient/qr-tokens",
            headers={"Authorization": f"Bearer {patient}"},
            json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-001"},
        )
        issued.raise_for_status()
        docker("stop", "rabbitmq")
        try:
            created = await client.post(
                f"{BASE}/api/v1/integrations/qr/check-in",
                headers={
                    "Authorization": f"Bearer {scanner}",
                    "Idempotency-Key": str(uuid4()),
                },
                json={
                    "qr_token": issued.json()["token"],
                    "facility_external_code": "HOSP-DEMO-001",
                    "scanner_external_id": "FAULT-TEST",
                },
            )
            assert created.status_code == 201
            encounter_id = created.json()["encounter_id"]
            pending = docker(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "postgres",
                "-d",
                "encounter_db",
                "-tAc",
                f"SELECT count(*) FROM outbox_events WHERE aggregate_id='{encounter_id}' AND published_at IS NULL",
            ).stdout.strip()
            assert pending == "1"
        finally:
            docker("start", "rabbitmq")
        for _ in range(40):
            published = docker(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "postgres",
                "-d",
                "encounter_db",
                "-tAc",
                f"SELECT count(*) FROM outbox_events WHERE aggregate_id='{encounter_id}' AND published_at IS NOT NULL",
            ).stdout.strip()
            if published == "1":
                break
            await asyncio.sleep(0.25)
        assert published == "1"
