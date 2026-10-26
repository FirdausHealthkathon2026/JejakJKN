"""Lean second-vendor adapter path with a deliberately different local schema."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.models import (
    LocalClinicalInput,
    LocalRecord,
    LocalScanInput,
    SimrsBVisit,
    SyncOutbox,
)
from app.infrastructure.db import get_session
from simrs_b_adapter.translator import translate

router = APIRouter(prefix="/api")
settings = get_settings()


async def token(client: httpx.AsyncClient) -> str:
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


@router.post("/pindai/masuk")
async def check_in(
    body: LocalScanInput,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            access_token = await token(client)
            response = await client.post(
                f"{settings.jejakjkn_api_url}/api/v1/integrations/qr/check-in",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Idempotency-Key": str(idempotency_key),
                },
                json={
                    "qr_token": body.token_qr,
                    "scanner_external_id": body.id_pemindai,
                    "facility_external_code": "HOSP-DEMO-002",
                    "external_visit_reference": body.referensi_kunjungan,
                },
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                503, "JejakJKN or identity provider is unavailable"
            ) from exc
    if response.is_error:
        raise HTTPException(response.status_code, response.json())
    result = response.json()
    encounter_id = UUID(result["encounter_id"])
    if not await session.get(SimrsBVisit, encounter_id):
        session.add(SimrsBVisit(encounter_id=encounter_id))
        await session.commit()
    return result


@router.post("/kunjungan/{encounter_id}/catatan", status_code=201)
async def create_record(
    encounter_id: UUID,
    body: LocalClinicalInput,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(encounter_id)}
    )
    visit = await session.get(SimrsBVisit, encounter_id, with_for_update=True)
    if not visit:
        raise HTTPException(404, "SIMRS-B visit not found")
    existing = await session.scalar(
        select(LocalRecord).where(
            LocalRecord.encounter_id == encounter_id,
            LocalRecord.external_record_id == body.id_rekam,
        )
    )
    if existing:
        payload = translate(existing.local_payload)
        return {
            "record_id": existing.id,
            "canonical_payload": payload,
            "delivery": {"status": "REPLAYED", "mapping_status": "MAPPED"},
        }
    local = body.model_dump()
    local["urutan"], local["id_peristiwa"] = (
        visit.next_source_sequence,
        body.id_peristiwa or str(idempotency_key),
    )
    visit.next_source_sequence += 1
    payload = translate(local)
    record = LocalRecord(
        id=uuid4(),
        encounter_id=encounter_id,
        external_record_id=body.id_rekam,
        local_payload=local,
    )
    session.add_all(
        [
            record,
            SyncOutbox(
                id=uuid4(),
                encounter_id=encounter_id,
                target_path=f"/api/v1/integrations/encounters/{encounter_id}/events",
                payload=payload,
            ),
        ]
    )
    visit.sync_status = "PENDING"
    await session.commit()
    return {
        "record_id": record.id,
        "canonical_payload": payload,
        "delivery": {"status": "PENDING", "mapping_status": "MAPPED"},
    }


@router.post("/kunjungan/{encounter_id}/sinkronisasi-selesai", status_code=202)
async def complete_sync(
    encounter_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(encounter_id)}
    )
    visit = await session.get(SimrsBVisit, encounter_id, with_for_update=True)
    if not visit:
        raise HTTPException(404, "SIMRS-B visit not found")
    sequence = visit.next_source_sequence - 1
    payload = {
        "source_system": "SIMRS-B",
        "last_source_sequence": sequence,
        "marked_complete_at": datetime.now(UTC).isoformat(),
    }
    session.add(
        SyncOutbox(
            id=uuid4(),
            encounter_id=encounter_id,
            target_path=f"/api/v1/integrations/encounters/{encounter_id}/sync-complete",
            payload=payload,
        )
    )
    visit.sync_status = "PENDING"
    await session.commit()
    return {
        "encounter_id": encounter_id,
        "last_source_sequence": sequence,
        "delivery_status": "PENDING",
    }


@router.get("/kunjungan/{encounter_id}/status-sinkronisasi")
async def sync_status(
    encounter_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    visit = await session.get(SimrsBVisit, encounter_id)
    if not visit:
        raise HTTPException(404, "SIMRS-B visit not found")
    counts = dict(
        (
            await session.execute(
                select(SyncOutbox.delivery_status, func.count())
                .where(SyncOutbox.encounter_id == encounter_id)
                .group_by(SyncOutbox.delivery_status)
            )
        ).all()
    )
    records = list(
        (
            await session.scalars(
                select(LocalRecord)
                .where(LocalRecord.encounter_id == encounter_id)
                .order_by(LocalRecord.created_at)
            )
        ).all()
    )
    return {
        "encounter_id": encounter_id,
        "sync_status": visit.sync_status,
        "last_error": visit.last_error,
        "pending": counts.get("PENDING", 0),
        "failed": counts.get("FAILED", 0),
        "delivered": counts.get("DELIVERED", 0),
        "records": [
            {
                "record_id": row.id,
                "external_record_id": row.external_record_id,
                "jenis": row.local_payload["jenis"],
                "kode": row.local_payload["kode"],
                "status": row.status,
            }
            for row in records
        ],
    }
