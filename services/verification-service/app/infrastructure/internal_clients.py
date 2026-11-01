"""Authenticated /internal/v1 HTTP clients for verification-service."""

import httpx

from app.config import Settings


class InternalClients:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _token(self) -> str:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                self.settings.keycloak_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.internal_client_id,
                    "client_secret": self.settings.internal_client_secret,
                },
            )
            response.raise_for_status()
            return response.json()["access_token"]

    async def search_candidates(self, payload: dict) -> dict:
        return await self._request(
            "POST",
            f"{self.settings.encounter_service_url}/internal/v1/encounters/search-candidates",
            json=payload,
        )

    async def pin_snapshot(self, encounter_id: str) -> dict:
        return await self._request(
            "POST",
            f"{self.settings.evidence_service_url}/internal/v1/encounters/{encounter_id}/evidence-snapshots",
        )

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        token = await self._token()
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(
                method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
            response.raise_for_status()
            return response.json()
