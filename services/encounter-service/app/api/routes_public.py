"""Patient and SIMRS scanner routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.dependencies import (
    principal_dependency,
    require_roles,
    require_scopes,
)
from jejakjkn_auth.jwt_verifier import Principal
from jejakjkn_canonical.problems import Problem

from app.application.use_cases import EncounterApplication
from app.config import get_settings
from app.infrastructure.db import get_session
from app.infrastructure.repositories import EncounterRepository

from .schemas import (
    CheckInResponse,
    CheckOutResponse,
    EncounterListResponse,
    EncounterSummary,
    ExceptionRequest,
    ExceptionResponse,
    IssueQrRequest,
    QrTokenResponse,
    RedeemQrRequest,
)

settings = get_settings()
current_principal = principal_dependency(
    settings.keycloak_issuer_url, settings.jwt_audience, settings.keycloak_jwks_url
)
patient_principal = require_roles(current_principal, "patient")
checkin_principal = require_roles(
    require_scopes(current_principal, "encounter:checkin"), "simrs_scanner"
)
checkout_principal = require_roles(
    require_scopes(current_principal, "encounter:checkout"), "simrs_scanner"
)
exception_principal = require_roles(
    require_scopes(current_principal, "encounter:exception"), "simrs_scanner"
)

router = APIRouter(prefix="/api/v1")


def application(
    request: Request, session: AsyncSession = Depends(get_session)
) -> EncounterApplication:
    return EncounterApplication(
        session, request.app.state.qr_store, request.app.state.qr_signer, settings
    )


@router.post("/patient/qr-tokens", response_model=QrTokenResponse, status_code=201)
async def issue_qr(
    body: IssueQrRequest,
    principal: Principal = Depends(patient_principal),
    app: EncounterApplication = Depends(application),
) -> dict:
    return await app.issue_qr(body, principal)


@router.get("/patient/encounters", response_model=EncounterListResponse)
async def list_encounters(
    principal: Principal = Depends(patient_principal),
    session: AsyncSession = Depends(get_session),
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: UUID | None = None,
) -> dict:
    if principal.patient_id is None:
        raise Problem(
            403,
            "PATIENT_CONTEXT_REQUIRED",
            "Forbidden",
            "The token is not bound to a patient.",
        )
    rows = await EncounterRepository(session).patient_encounters(
        principal.patient_id, limit, cursor
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    items = [
        _summary(encounter, organization.external_code, organization.display_name)
        for encounter, organization in visible
    ]
    return {"items": items, "next_cursor": visible[-1][0].id if has_more else None}


@router.get("/patient/encounters/{encounter_id}", response_model=EncounterSummary)
async def get_encounter(
    encounter_id: UUID,
    principal: Principal = Depends(patient_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    repo = EncounterRepository(session)
    encounter = await repo.encounter(encounter_id)
    if not encounter or encounter.patient_id != principal.patient_id:
        raise Problem(
            404,
            "ENCOUNTER_NOT_FOUND",
            "Encounter not found",
            "The encounter was not found.",
        )
    from app.infrastructure.models import Organization

    organization = await session.get(Organization, encounter.organization_id)
    return _summary(encounter, organization.external_code, organization.display_name)


@router.post(
    "/integrations/qr/check-in", response_model=CheckInResponse, status_code=201
)
async def check_in(
    body: RedeemQrRequest,
    response: Response,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    principal: Principal = Depends(checkin_principal),
    app: EncounterApplication = Depends(application),
) -> dict:
    result, replay = await app.redeem(body, str(idempotency_key), principal, "CHECK_IN")
    if replay:
        response.status_code = 200
    participant_number = await app.participant_number(UUID(result["encounter_id"]))
    return result | {"participant_number": participant_number}


@router.post("/integrations/qr/check-out", response_model=CheckOutResponse)
async def check_out(
    body: RedeemQrRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    principal: Principal = Depends(checkout_principal),
    app: EncounterApplication = Depends(application),
) -> dict:
    result, _ = await app.redeem(body, str(idempotency_key), principal, "CHECK_OUT")
    return result


@router.post(
    "/integrations/encounters/{encounter_id}/exceptions",
    response_model=ExceptionResponse,
    status_code=201,
)
async def record_exception(
    encounter_id: UUID,
    body: ExceptionRequest,
    principal: Principal = Depends(exception_principal),
    app: EncounterApplication = Depends(application),
) -> dict:
    return await app.record_exception(encounter_id, body, principal)


def _summary(encounter, facility_code: str, facility_name: str) -> dict:
    return {
        "encounter_id": encounter.id,
        "facility_code": facility_code,
        "facility_display_name": facility_name,
        "service_type": encounter.service_type,
        "status": encounter.status,
        "presence_status": encounter.presence_status,
        "started_at": encounter.started_at,
        "ended_at": encounter.ended_at,
        "check_in_successful": encounter.presence_status == "QR_VERIFIED",
        "check_out_successful": encounter.status
        in {"CHECKED_OUT", "CLOSED_WITH_EXCEPTION"},
        "confirmation_status": "NOT_AVAILABLE",
    }
