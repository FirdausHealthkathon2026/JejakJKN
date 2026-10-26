"""Fetch a minimized package and store its deterministic narrative."""

import os

import httpx

from app.domain.narrator import narrate


async def handle(envelope: dict) -> None:
    token_url = os.getenv(
        "KEYCLOAK_TOKEN_URL",
        "http://keycloak:8080/realms/jejakjkn-dev/protocol/openid-connect/token",
    )
    run_id = envelope["data"].get("run_id", envelope["aggregate_id"])
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": os.getenv("INTERNAL_CLIENT_ID", "review-service"),
                "client_secret": os.getenv(
                    "INTERNAL_CLIENT_SECRET", "change-me-local-only"
                ),
            },
        )
        token_response.raise_for_status()
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        response = await client.get(
            f"{os.getenv('VERIFICATION_SERVICE_URL', 'http://verification-api:8003')}/internal/v1/verifications/{run_id}/review-package",
            headers=headers,
        )
        response.raise_for_status()
        package = response.json()
        narrative, status, digest = narrate(package)
        stored = await client.put(
            f"{os.getenv('REVIEW_SERVICE_URL', 'http://review-api:8004')}/internal/v1/narratives/{run_id}",
            headers=headers,
            json={
                "assessment_ref": run_id,
                "method": "TEMPLATE",
                "model_info": "deterministic-v1",
                "input_digest": digest,
                "narrative": narrative,
                "validation_status": status,
            },
        )
        stored.raise_for_status()
