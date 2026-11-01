"""Tenant-scoped reviewer API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.dependencies import (
    principal_dependency,
    require_roles,
    require_scopes,
)
from jejakjkn_auth.jwt_verifier import Principal

from app.api.schemas import AssignRequest, CaseView, DecisionRequest, DecisionView
from app.application.use_cases import ReviewApplication
from app.config import get_settings
from app.infrastructure.db import get_session

settings = get_settings()
current = principal_dependency(
    settings.keycloak_issuer_url, settings.jwt_audience, settings.keycloak_jwks_url
)
reader = require_roles(
    require_scopes(current, "review:read"), "verifier", "review_supervisor"
)
decider = require_roles(
    require_scopes(current, "review:decide"), "verifier", "review_supervisor"
)
router = APIRouter(prefix="/api/v1/review-cases")


def application(session: AsyncSession = Depends(get_session)) -> ReviewApplication:
    return ReviewApplication(session)


@router.get("", response_model=list[CaseView])
async def list_cases(
    principal: Principal = Depends(reader),
    app: ReviewApplication = Depends(application),
) -> list[dict]:
    return await app.list_cases(principal)


@router.get("/{case_id}", response_model=CaseView)
async def get_case(
    case_id: UUID,
    request: Request,
    purpose: Annotated[
        str, Header(alias="X-Access-Purpose", min_length=3, max_length=64)
    ],
    principal: Principal = Depends(reader),
    app: ReviewApplication = Depends(application),
) -> dict:
    return await app.get_case(case_id, principal, request.state.request_id, purpose)


@router.post("/{case_id}/assign", response_model=CaseView)
async def assign(
    case_id: UUID,
    body: AssignRequest,
    principal: Principal = Depends(decider),
    app: ReviewApplication = Depends(application),
) -> dict:
    return await app.assign(case_id, body, principal)


@router.post("/{case_id}/decisions", response_model=DecisionView, status_code=201)
async def decide(
    case_id: UUID,
    body: DecisionRequest,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    principal: Principal = Depends(decider),
    app: ReviewApplication = Depends(application),
) -> dict:
    result, replay = await app.decide(case_id, body, idempotency_key, principal)
    if replay:
        response.status_code = 200
    return result
