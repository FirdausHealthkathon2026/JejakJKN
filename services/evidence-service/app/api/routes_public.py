"""Patient summary and SIMRS evidence routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.dependencies import principal_dependency, require_roles, require_scopes
from jejakjkn_auth.jwt_verifier import Principal

from app.application.use_cases import EvidenceApplication
from app.config import get_settings
from app.infrastructure.db import get_session

from .schemas import CancellationRequest, CheckoutSummaryResponse, ClinicalEventRequest, CorrectionRequest, EvidenceWriteResponse, PatientResponseRequest, PatientResponseView, SyncCompleteRequest, SyncStatusResponse

settings = get_settings()
current_principal = principal_dependency(settings.keycloak_issuer_url, settings.jwt_audience, settings.keycloak_jwks_url)
patient_principal = require_roles(current_principal, "patient")
writer_principal = require_roles(require_scopes(current_principal, "evidence:write"), "simrs_clinical_sender", "simrs_pharmacy_sender")
corrector_principal = require_roles(require_scopes(current_principal, "evidence:correct"), "simrs_clinical_sender", "simrs_pharmacy_sender")
canceller_principal = require_roles(require_scopes(current_principal, "evidence:cancel"), "simrs_clinical_sender", "simrs_pharmacy_sender")
status_principal = require_roles(require_scopes(current_principal, "evidence:readstatus"), "simrs_clinical_sender", "simrs_pharmacy_sender")

router = APIRouter(prefix="/api/v1")


def application(session: AsyncSession = Depends(get_session)) -> EvidenceApplication:
    return EvidenceApplication(session, settings)


@router.post("/integrations/encounters/{encounter_id}/events", response_model=EvidenceWriteResponse, status_code=201)
async def ingest_event(encounter_id: UUID, body: ClinicalEventRequest, response: Response, principal: Principal = Depends(writer_principal), app: EvidenceApplication = Depends(application)) -> dict:
    result, replay = await app.ingest(encounter_id, body, principal, "RECORDED")
    if replay:
        response.status_code = 200
    return result


@router.post("/integrations/encounters/{encounter_id}/corrections", response_model=EvidenceWriteResponse, status_code=201)
async def ingest_correction(encounter_id: UUID, body: CorrectionRequest, response: Response, principal: Principal = Depends(corrector_principal), app: EvidenceApplication = Depends(application)) -> dict:
    result, replay = await app.ingest(encounter_id, body, principal, "CORRECTED")
    if replay:
        response.status_code = 200
    return result


@router.post("/integrations/encounters/{encounter_id}/cancellations", response_model=EvidenceWriteResponse)
async def ingest_cancellation(encounter_id: UUID, body: CancellationRequest, principal: Principal = Depends(canceller_principal), app: EvidenceApplication = Depends(application)) -> dict:
    result, _ = await app.ingest(encounter_id, body, principal, "CANCELLED")
    return result


@router.post("/integrations/encounters/{encounter_id}/sync-complete", response_model=SyncStatusResponse)
async def sync_complete(encounter_id: UUID, body: SyncCompleteRequest, principal: Principal = Depends(writer_principal), app: EvidenceApplication = Depends(application)) -> dict:
    return await app.mark_sync_complete(encounter_id, body, principal)


@router.get("/integrations/encounters/{encounter_id}/ingestion-status", response_model=SyncStatusResponse)
async def ingestion_status(encounter_id: UUID, principal: Principal = Depends(status_principal), app: EvidenceApplication = Depends(application)) -> dict:
    return await app.ingestion_status(encounter_id, principal)


@router.get("/patient/encounters/{encounter_id}/checkout-summary", response_model=CheckoutSummaryResponse)
async def checkout_summary(encounter_id: UUID, principal: Principal = Depends(patient_principal), app: EvidenceApplication = Depends(application)) -> dict:
    return await app.checkout_summary(encounter_id, principal)


@router.post("/patient/checkout-summaries/{snapshot_id}/responses", response_model=PatientResponseView, status_code=201)
async def submit_response(
    snapshot_id: UUID,
    body: PatientResponseRequest,
    response: Response,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    principal: Principal = Depends(patient_principal),
    app: EvidenceApplication = Depends(application),
) -> dict:
    result, replay = await app.submit_response(snapshot_id, body, str(idempotency_key), principal)
    if replay:
        response.status_code = 200
    return result


@router.get("/patient/checkout-summaries/{snapshot_id}/response", response_model=PatientResponseView)
async def get_response(snapshot_id: UUID, principal: Principal = Depends(patient_principal), app: EvidenceApplication = Depends(application)) -> dict:
    return await app.get_response(snapshot_id, principal)
