"""Internal narrative materialization API."""

from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.dependencies import principal_dependency, require_roles
from jejakjkn_auth.jwt_verifier import Principal

from app.api.schemas import NarrativeRequest
from app.config import get_settings
from app.infrastructure.db import get_session
from app.infrastructure.models import NarrativeArtifact

settings = get_settings()
internal = require_roles(
    principal_dependency(
        settings.keycloak_issuer_url, settings.jwt_audience, settings.keycloak_jwks_url
    ),
    "internal_service",
)
router = APIRouter(prefix="/internal/v1")


@router.put("/narratives/{assessment_ref}", status_code=204)
async def put_narrative(
    assessment_ref: str,
    body: NarrativeRequest,
    _: Principal = Depends(internal),
    session: AsyncSession = Depends(get_session),
) -> None:
    if str(body.assessment_ref) != assessment_ref:
        from jejakjkn_canonical.problems import Problem

        raise Problem(
            422,
            "ASSESSMENT_REF_MISMATCH",
            "Invalid narrative",
            "Path and body assessment references differ.",
        )
    existing = await session.get(NarrativeArtifact, body.assessment_ref)
    if not existing:
        session.add(
            NarrativeArtifact(
                id=uuid4(),
                assessment_ref=body.assessment_ref,
                method=body.method,
                model_info=body.model_info,
                input_digest=body.input_digest,
                narrative_json=body.narrative,
                validation_status=body.validation_status,
            )
        )
        await session.commit()
