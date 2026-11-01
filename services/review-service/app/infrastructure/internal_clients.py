"""Authenticated verification client."""

import httpx

from app.config import Settings


class VerificationClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def review_package(self, run_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                self.settings.keycloak_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.internal_client_id,
                    "client_secret": self.settings.internal_client_secret,
                },
            )
            token_response.raise_for_status()
            response = await client.get(
                f"{self.settings.verification_service_url}/internal/v1/verifications/{run_id}/review-package",
                headers={
                    "Authorization": f"Bearer {token_response.json()['access_token']}"
                },
            )
            response.raise_for_status()
            return response.json()
