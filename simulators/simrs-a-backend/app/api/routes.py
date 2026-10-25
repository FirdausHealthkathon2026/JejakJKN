"""SIMRS-A owns clinical input and relays QR scans server-side."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.models import ClinicalRecord, ClinicalVersion, SimrsVisit, SyncOutbox
from app.infrastructure.db import get_session

router = APIRouter(prefix="/api")
settings = get_settings()


class ScanRequest(BaseModel):
    qr_token: str = Field(min_length=32)
    scanner_external_id: str = Field(default="SIMRS-A-SCANNER-01", min_length=1, max_length=128)
    external_visit_reference: str | None = Field(default=None, max_length=128)


class ClinicalInput(BaseModel):
    event_type: Literal["DIAGNOSIS", "PROCEDURE", "MEDICATION_PRESCRIBED", "MEDICATION_DISPENSED", "STAGE_COMPLETION"]
    code_system: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    display: str = Field(min_length=1, max_length=255)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=32)
    stage_completion: Literal["STARTED", "STAFF_COMPLETED"] | None = None
    actor_external_id: str = Field(default="STAFF-DEMO-01", min_length=1, max_length=128)
    actor_role: str = Field(default="CLINICIAN", min_length=1, max_length=64)
    external_record_id: str | None = Field(default=None, max_length=128)


class CorrectionInput(BaseModel):
    code_system: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    display: str = Field(min_length=1, max_length=255)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=32)
    change_reason: str = Field(min_length=1, max_length=500)
    actor_external_id: str = Field(default="STAFF-DEMO-01", min_length=1, max_length=128)
    actor_role: str = Field(default="CLINICIAN", min_length=1, max_length=64)


class CancellationInput(BaseModel):
    cancel_reason: str = Field(min_length=1, max_length=500)
    actor_external_id: str = Field(default="STAFF-DEMO-01", min_length=1, max_length=128)
    actor_role: str = Field(default="CLINICIAN", min_length=1, max_length=64)


async def _access_token(client: httpx.AsyncClient) -> str:
    response = await client.post(settings.keycloak_token_url, data={"grant_type": "client_credentials", "client_id": settings.simrs_client_id, "client_secret": settings.simrs_client_secret})
    response.raise_for_status()
    return response.json()["access_token"]


async def _scan(kind: str, body: ScanRequest, idempotency_key: UUID) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            token = await _access_token(client)
            payload = body.model_dump()
            payload["facility_external_code"] = settings.facility_external_code
            if kind == "check-out":
                payload.pop("external_visit_reference", None)
            response = await client.post(f"{settings.jejakjkn_api_url}/api/v1/integrations/qr/{kind}", json=payload, headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(idempotency_key)})
        except httpx.HTTPError as exc:
            raise HTTPException(503, "JejakJKN or identity provider is unavailable") from exc
    if response.is_error:
        raise HTTPException(response.status_code, response.json())
    return response.json()


@router.post("/scan/check-in")
async def check_in(body: ScanRequest, idempotency_key: UUID = Header(alias="Idempotency-Key"), session: AsyncSession = Depends(get_session)) -> dict:
    result = await _scan("check-in", body, idempotency_key)
    encounter_id = UUID(result["encounter_id"])
    if not await session.get(SimrsVisit, encounter_id):
        session.add(SimrsVisit(encounter_id=encounter_id))
        await session.commit()
    return result


@router.post("/scan/check-out")
async def check_out(body: ScanRequest, idempotency_key: UUID = Header(alias="Idempotency-Key")) -> dict:
    return await _scan("check-out", body, idempotency_key)


@router.post("/visits/{encounter_id}/clinical-events", status_code=201)
async def create_clinical_event(encounter_id: UUID, body: ClinicalInput, session: AsyncSession = Depends(get_session)) -> dict:
    visit, sequence = await _next_sequence(session, encounter_id)
    record_id = uuid4()
    external_record_id = body.external_record_id or f"SIMRS-A-{record_id}"
    record = ClinicalRecord(id=record_id, encounter_id=encounter_id, external_record_id=external_record_id, event_type=body.event_type)
    now = datetime.now(UTC)
    payload = {
        "source_event_id": f"SIMRS-A-EVT-{uuid4()}", "source_system": "SIMRS-A", "source_sequence": sequence,
        "external_record_id": external_record_id, "event_type": body.event_type, "record_version": 1,
        "occurred_at": now.isoformat(), "actor": {"external_id": body.actor_external_id, "role": body.actor_role},
        "content": {"code_system": body.code_system, "code": body.code, "display": body.display, "quantity": str(body.quantity) if body.quantity is not None else None, "unit": body.unit},
        "stage_completion": body.stage_completion,
    }
    session.add(record)
    session.add(ClinicalVersion(id=uuid4(), record_id=record.id, version=1, source_event_id=payload["source_event_id"], source_sequence=sequence, action="RECORDED", payload=payload))
    session.add(SyncOutbox(id=uuid4(), encounter_id=encounter_id, target_path=f"/api/v1/integrations/encounters/{encounter_id}/events", payload=payload))
    visit.sync_status = "PENDING"
    await session.commit()
    return {"record_id": record.id, "external_record_id": external_record_id, "record_version": 1, "source_sequence": sequence, "delivery_status": "PENDING"}


@router.post("/clinical-records/{record_id}/corrections", status_code=201)
async def correct_clinical_record(record_id: UUID, body: CorrectionInput, session: AsyncSession = Depends(get_session)) -> dict:
    record = await session.get(ClinicalRecord, record_id, with_for_update=True)
    if not record or record.status == "CANCELLED":
        raise HTTPException(404, "Clinical record not found")
    visit, sequence = await _next_sequence(session, record.encounter_id)
    version_number = record.current_version + 1
    now = datetime.now(UTC)
    payload = {
        "source_event_id": f"SIMRS-A-EVT-{uuid4()}", "source_system": "SIMRS-A", "source_sequence": sequence,
        "external_record_id": record.external_record_id, "record_version": version_number,
        "occurred_at": now.isoformat(), "source_updated_at": now.isoformat(), "change_reason": body.change_reason,
        "actor": {"external_id": body.actor_external_id, "role": body.actor_role},
        "content": {"code_system": body.code_system, "code": body.code, "display": body.display, "quantity": str(body.quantity) if body.quantity is not None else None, "unit": body.unit},
        "stage_completion": None,
    }
    record.current_version, record.status = version_number, "CORRECTED"
    session.add(ClinicalVersion(id=uuid4(), record_id=record.id, version=version_number, source_event_id=payload["source_event_id"], source_sequence=sequence, action="CORRECTED", payload=payload))
    session.add(SyncOutbox(id=uuid4(), encounter_id=record.encounter_id, target_path=f"/api/v1/integrations/encounters/{record.encounter_id}/corrections", payload=payload))
    visit.sync_status = "PENDING"
    await session.commit()
    return {"record_id": record.id, "record_version": version_number, "source_sequence": sequence, "delivery_status": "PENDING"}


@router.post("/clinical-records/{record_id}/cancellations")
async def cancel_clinical_record(record_id: UUID, body: CancellationInput, session: AsyncSession = Depends(get_session)) -> dict:
    record = await session.get(ClinicalRecord, record_id, with_for_update=True)
    if not record or record.status == "CANCELLED":
        raise HTTPException(404, "Clinical record not found")
    visit, sequence = await _next_sequence(session, record.encounter_id)
    version_number = record.current_version + 1
    now = datetime.now(UTC)
    payload = {
        "source_event_id": f"SIMRS-A-EVT-{uuid4()}", "source_system": "SIMRS-A", "source_sequence": sequence,
        "external_record_id": record.external_record_id, "record_version": version_number,
        "source_updated_at": now.isoformat(), "cancel_reason": body.cancel_reason,
        "actor": {"external_id": body.actor_external_id, "role": body.actor_role},
    }
    record.current_version, record.status = version_number, "CANCELLED"
    session.add(ClinicalVersion(id=uuid4(), record_id=record.id, version=version_number, source_event_id=payload["source_event_id"], source_sequence=sequence, action="CANCELLED", payload=payload))
    session.add(SyncOutbox(id=uuid4(), encounter_id=record.encounter_id, target_path=f"/api/v1/integrations/encounters/{record.encounter_id}/cancellations", payload=payload))
    visit.sync_status = "PENDING"
    await session.commit()
    return {"record_id": record.id, "record_version": version_number, "source_sequence": sequence, "delivery_status": "PENDING"}


@router.post("/visits/{encounter_id}/sync-complete")
async def complete_sync(encounter_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(encounter_id)})
    visit = await session.get(SimrsVisit, encounter_id, with_for_update=True)
    if not visit:
        raise HTTPException(404, "SIMRS visit not found")
    final_sequence = visit.next_source_sequence - 1
    payload = {"source_system": "SIMRS-A", "last_source_sequence": final_sequence, "marked_complete_at": datetime.now(UTC).isoformat()}
    session.add(SyncOutbox(id=uuid4(), encounter_id=encounter_id, target_path=f"/api/v1/integrations/encounters/{encounter_id}/sync-complete", payload=payload))
    visit.sync_status = "PENDING"
    await session.commit()
    return {"encounter_id": encounter_id, "last_source_sequence": final_sequence, "delivery_status": "PENDING"}


@router.get("/visits/{encounter_id}/sync-status")
async def sync_status(encounter_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    visit = await session.get(SimrsVisit, encounter_id)
    if not visit:
        raise HTTPException(404, "SIMRS visit not found")
    counts = dict((await session.execute(select(SyncOutbox.delivery_status, func.count()).where(SyncOutbox.encounter_id == encounter_id).group_by(SyncOutbox.delivery_status))).all())
    records = list((await session.scalars(select(ClinicalRecord).where(ClinicalRecord.encounter_id == encounter_id).order_by(ClinicalRecord.created_at))).all())
    return {
        "encounter_id": encounter_id, "sync_status": visit.sync_status, "last_error": visit.last_error,
        "pending": counts.get("PENDING", 0), "failed": counts.get("FAILED", 0), "delivered": counts.get("DELIVERED", 0),
        "records": [{"record_id": row.id, "event_type": row.event_type, "external_record_id": row.external_record_id, "version": row.current_version, "status": row.status} for row in records],
    }


async def _next_sequence(session: AsyncSession, encounter_id: UUID) -> tuple[SimrsVisit, int]:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(encounter_id)})
    visit = await session.get(SimrsVisit, encounter_id, with_for_update=True)
    if not visit:
        raise HTTPException(404, "SIMRS visit not found")
    sequence = visit.next_source_sequence
    visit.next_source_sequence += 1
    return visit, sequence
