"""Durably deliver SIMRS-A source events to JejakJKN in sequence."""

import asyncio
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.domain.models import SimrsVisit, SyncOutbox
from app.infrastructure.db import SessionFactory


async def _token(client: httpx.AsyncClient) -> str:
    settings = get_settings()
    response = await client.post(settings.keycloak_token_url, data={"grant_type": "client_credentials", "client_id": settings.simrs_client_id, "client_secret": settings.simrs_client_secret})
    response.raise_for_status()
    return response.json()["access_token"]


async def dispatch_forever() -> None:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            row = None
            try:
                async with SessionFactory() as session:
                    row = await session.scalar(select(SyncOutbox).where(SyncOutbox.delivery_status == "PENDING").order_by(SyncOutbox.created_at, SyncOutbox.id).limit(1).with_for_update(skip_locked=True))
                    if row is None:
                        await asyncio.sleep(0.5)
                        continue
                    visit = await session.get(SimrsVisit, row.encounter_id, with_for_update=True)
                    row.attempts += 1
                    try:
                        token = await _token(client)
                        response = await client.post(f"{settings.jejakjkn_api_url}{row.target_path}", json=row.payload, headers={"Authorization": f"Bearer {token}"})
                        if response.is_success:
                            row.delivery_status = "DELIVERED"
                            row.delivered_at = datetime.now(UTC)
                            row.last_error = None
                            if row.target_path.endswith("/sync-complete"):
                                visit.sync_status = response.json()["sync_status"]
                            elif visit.sync_status == "LOCAL_ONLY":
                                visit.sync_status = "PENDING"
                            visit.last_error = None
                        elif response.status_code >= 500 or (response.status_code == 409 and _error_code(response) == "CARE_EPISODE_NOT_READY"):
                            row.last_error = f"HTTP {response.status_code}"
                            visit.last_error = row.last_error
                        else:
                            row.delivery_status = "FAILED"
                            row.last_error = f"HTTP {response.status_code}"
                            visit.sync_status = "FAILED"
                            visit.last_error = row.last_error
                    except httpx.HTTPError as exc:
                        row.last_error = type(exc).__name__
                        visit.last_error = row.last_error
                    await session.commit()
            except SQLAlchemyError:
                await asyncio.sleep(2)
                continue
            await asyncio.sleep(min(0.25 * (row.attempts if row else 1), 2))


def _error_code(response: httpx.Response) -> str | None:
    try:
        return response.json().get("error_code")
    except ValueError:
        return None
