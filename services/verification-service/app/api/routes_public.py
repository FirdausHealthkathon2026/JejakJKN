"""Verifier-owned request and assessment routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.dependencies import (
    principal_dependency,
    require_roles,
    require_scopes,
)
from jejakjkn_auth.jwt_verifier import Principal

from app.api.schemas import (
    AssessmentView,
    CandidateView,
    FindingView,
    QueuedVerification,
    VerificationRequestBody,
)
from app.application.use_cases import VerificationApplication
from app.config import get_settings
from app.infrastructure.db import get_session

settings = get_settings()
current = principal_dependency(
    settings.keycloak_issuer_url, settings.jwt_audience, settings.keycloak_jwks_url
)
creator = require_roles(require_scopes(current, "verification:create"), "verifier")
reader = require_roles(require_scopes(current, "verification:read"), "verifier")
rechecker = require_roles(require_scopes(current, "verification:recheck"), "verifier")
router = APIRouter(prefix="/api/v1/verifications")


def application(
    session: AsyncSession = Depends(get_session),
) -> VerificationApplication:
    return VerificationApplication(session, settings)


@router.post("", response_model=QueuedVerification, status_code=202)
async def submit(
    body: VerificationRequestBody,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    principal: Principal = Depends(creator),
    app: VerificationApplication = Depends(application),
) -> dict:
    result, replay = await app.submit(body, idempotency_key, principal)
    if replay:
        response.status_code = 200
    return result


@router.get("/history", response_model=list[AssessmentView])
async def history(
    claim_source: str,
    claim_id: str,
    principal: Principal = Depends(reader),
    app: VerificationApplication = Depends(application),
) -> list[dict]:
    return await app.history(claim_source, claim_id, principal)


@router.get("/{verification_id}", response_model=AssessmentView)
async def assessment(
    verification_id: UUID,
    principal: Principal = Depends(reader),
    app: VerificationApplication = Depends(application),
) -> dict:
    return await app.assessment(verification_id, principal)


@router.get("/{verification_id}/candidates", response_model=list[CandidateView])
async def candidates(
    verification_id: UUID,
    principal: Principal = Depends(reader),
    app: VerificationApplication = Depends(application),
) -> list[dict]:
    return await app.candidates(verification_id, principal)


@router.get("/{verification_id}/findings", response_model=list[FindingView])
async def findings(
    verification_id: UUID,
    principal: Principal = Depends(reader),
    app: VerificationApplication = Depends(application),
) -> list[dict]:
    return await app.findings(verification_id, principal)


@router.post(
    "/{verification_id}/re-evaluate", response_model=QueuedVerification, status_code=202
)
async def recheck(
    verification_id: UUID,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    principal: Principal = Depends(rechecker),
    app: VerificationApplication = Depends(application),
) -> dict:
    result, replay = await app.recheck(verification_id, idempotency_key, principal)
    if replay:
        response.status_code = 200
    return result
