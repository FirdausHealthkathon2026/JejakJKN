import os
from uuid import uuid4

import httpx
import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1", reason="requires local stack"
)


@pytest.mark.asyncio
async def test_review_read_audit_and_idempotent_human_decision() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            "http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "test-verifier-client",
                "client_secret": os.environ["TEST_VERIFIER_CLIENT_SECRET"],
            },
        )
        token_response.raise_for_status()
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        cases = await client.get(
            "http://localhost:18080/api/v1/review-cases", headers=headers
        )
        assert cases.status_code == 200 and cases.json()
        case_id = cases.json()[0]["id"]
        detail = await client.get(
            f"http://localhost:18080/api/v1/review-cases/{case_id}",
            headers=headers | {"X-Access-Purpose": "integration-test"},
        )
        assert detail.status_code == 200
        assert (
            detail.json()["review_package"]["assessment"]["final_fraud_decision"]
            is None
        )
        key = str(uuid4())
        body = {
            "decision": "ESCALATE",
            "reason": "Synthetic integration review requires escalation.",
        }
        created = await client.post(
            f"http://localhost:18080/api/v1/review-cases/{case_id}/decisions",
            headers=headers | {"Idempotency-Key": key},
            json=body,
        )
        replay = await client.post(
            f"http://localhost:18080/api/v1/review-cases/{case_id}/decisions",
            headers=headers | {"Idempotency-Key": key},
            json=body,
        )
        assert created.status_code == 201
        assert replay.status_code == 200
        assert replay.json()["id"] == created.json()["id"]
