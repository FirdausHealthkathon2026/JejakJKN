import asyncio
import os
from uuid import uuid4

import httpx
import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1", reason="requires local stack"
)


@pytest.mark.asyncio
async def test_simrs_b_alternative_schema_reaches_canonical_evidence() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            "http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "test-patient-client",
                "client_secret": os.environ["TEST_PATIENT_CLIENT_SECRET"],
            },
        )
        token_response.raise_for_status()
        patient_headers = {
            "Authorization": f"Bearer {token_response.json()['access_token']}"
        }
        issued = await client.post(
            "http://localhost:18080/api/v1/patient/qr-tokens",
            headers=patient_headers,
            json={"purpose": "CHECK_IN", "facility_hint": "HOSP-DEMO-002"},
        )
        assert issued.status_code == 201
        checked_in = await client.post(
            "http://localhost:8102/api/pindai/masuk",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "token_qr": issued.json()["token"],
                "referensi_kunjungan": f"RSB-{uuid4()}",
            },
        )
        assert checked_in.status_code == 200, checked_in.text
        encounter_id = checked_in.json()["encounter_id"]
        event_id, record_id, key = f"EVT-{uuid4()}", f"RX-{uuid4()}", str(uuid4())
        for _ in range(20):
            recorded = await client.post(
                f"http://localhost:8102/api/kunjungan/{encounter_id}/catatan",
                headers={"Idempotency-Key": key},
                json={
                    "jenis": "OBAT",
                    "kode": "OB-PCT500",
                    "urutan": 1,
                    "id_rekam": record_id,
                    "id_peristiwa": event_id,
                    "jumlah": 10,
                },
            )
            if recorded.status_code == 201:
                break
            await asyncio.sleep(0.25)
        assert recorded.status_code == 201, recorded.text
        assert (
            recorded.json()["canonical_payload"]["content"]["code_system"]
            == "JJKN-MED-V1"
        )
        assert recorded.json()["delivery"]["mapping_status"] == "MAPPED"
