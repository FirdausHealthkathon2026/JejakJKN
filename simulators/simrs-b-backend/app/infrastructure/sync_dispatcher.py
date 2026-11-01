"""Durably deliver translated SIMRS-B records in source order."""

import asyncio
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.domain.models import SimrsBVisit, SyncOutbox
from app.infrastructure.db import SessionFactory


async def _token(client: httpx.AsyncClient) -> str:
    settings = get_settings()
    response = await client.post(
        settings.keycloak_token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": "simrs-b-adapter",
            "client_secret": settings.simrs_client_secret,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def dispatch_forever() -> None:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            row = None
            try:
                async with SessionFactory() as session:
                    row = await session.scalar(
                        select(SyncOutbox)
                        .where(SyncOutbox.delivery_status == "PENDING")
                        .order_by(SyncOutbox.created_at, SyncOutbox.id)
                        .limit(1)
                        .with_for_update(skip_locked=True)
                    )
                    if row is None:
                        await asyncio.sleep(0.5)
                        continue
                    visit = await session.get(
                        SimrsBVisit, row.encounter_id, with_for_update=True
                    )
                    row.attempts += 1
                    try:
                        response = await client.post(
                            f"{settings.jejakjkn_api_url}{row.target_path}",
                            json=row.payload,
                            headers={"Authorization": f"Bearer {await _token(client)}"},
                        )
                        if response.is_success:
                            row.delivery_status, row.delivered_at, row.last_error = (
                                "DELIVERED",
                                datetime.now(UTC),
                                None,
                            )
                            visit.sync_status = (
                                response.json().get("sync_status", "PENDING")
                                if row.target_path.endswith("/sync-complete")
                                else "PENDING"
                            )
                            visit.last_error = None
                        elif response.status_code >= 500 or response.status_code == 409:
                            row.last_error = f"HTTP {response.status_code}"
                            visit.last_error = row.last_error
                        else:
                            row.delivery_status, row.last_error = (
                                "FAILED",
                                f"HTTP {response.status_code}",
                            )
                            visit.sync_status, visit.last_error = (
                                "FAILED",
                                row.last_error,
                            )
                    except httpx.HTTPError as exc:
                        row.last_error = type(exc).__name__
                        visit.last_error = row.last_error
                    await session.commit()
            except SQLAlchemyError:
                await asyncio.sleep(2)
                continue
            await asyncio.sleep(min(0.25 * (row.attempts if row else 1), 2))
