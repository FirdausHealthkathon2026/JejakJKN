"""Private candidate and eligibility routes."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.dependencies import principal_dependency, require_roles
from jejakjkn_auth.jwt_verifier import Principal
from jejakjkn_canonical.problems import Problem

from app.config import get_settings
from app.infrastructure.db import get_session
from app.infrastructure.repositories import EncounterRepository

from .schemas import CandidateSearchRequest, CandidateSearchResponse, EligibilityResponse

settings = get_settings()
internal_principal = require_roles(principal_dependency(settings.keycloak_issuer_url, settings.jwt_audience, settings.keycloak_jwks_url), "internal_service")
router = APIRouter(prefix="/internal/v1")


@router.get("/encounters/{encounter_id}/eligibility", response_model=EligibilityResponse)
async def eligibility(encounter_id: UUID, _: Principal = Depends(internal_principal), session: AsyncSession = Depends(get_session)) -> dict:
    encounter = await EncounterRepository(session).encounter(encounter_id)
    if not encounter:
        raise Problem(404, "ENCOUNTER_NOT_FOUND", "Encounter not found", "The encounter was not found.")
    return _candidate(encounter) | {"eligible": encounter.status in {"CHECKED_OUT", "CLOSED_WITH_EXCEPTION"}}


@router.post("/encounters/search-candidates", response_model=CandidateSearchResponse)
async def search_candidates(body: CandidateSearchRequest, _: Principal = Depends(internal_principal), session: AsyncSession = Depends(get_session)) -> dict:
    repo = EncounterRepository(session)
    organization = await repo.organization(body.facility_namespace, body.facility_code)
    if not organization:
        return {"candidates": [], "truncated_by_limit": False}
    encounters = await repo.search_candidates(
        participant_lookup_key=body.participant_lookup_key,
        patient_name_hmac=body.patient_name_hmac,
        organization_id=organization.id,
        start=body.service_period_start,
        end=body.service_period_end,
        limit=body.safety_limit,
    )
    return {"candidates": [_candidate(item) for item in encounters[:body.safety_limit]], "truncated_by_limit": len(encounters) > body.safety_limit}


def _candidate(encounter) -> dict:
    return {
        "encounter_id": encounter.id,
        "patient_id": encounter.patient_id,
        "organization_id": encounter.organization_id,
        "status": encounter.status,
        "presence_status": encounter.presence_status,
        "service_type": encounter.service_type,
        "started_at": encounter.started_at,
        "ended_at": encounter.ended_at,
        "revision": encounter.revision,
    }
