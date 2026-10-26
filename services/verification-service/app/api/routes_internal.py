"""Materialized, minimized packages for the Review service."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.dependencies import principal_dependency, require_roles
from jejakjkn_auth.jwt_verifier import Principal
from jejakjkn_canonical.problems import Problem

from app.config import get_settings
from app.infrastructure.db import get_session
from app.infrastructure.models import (
    CandidateEvaluation,
    ItemEvaluation,
    RuleFinding,
    VerificationRequest,
    VerificationRun,
)

settings = get_settings()
internal = require_roles(
    principal_dependency(
        settings.keycloak_issuer_url, settings.jwt_audience, settings.keycloak_jwks_url
    ),
    "internal_service",
)
router = APIRouter(prefix="/internal/v1")


@router.get("/verifications/{run_id}/review-package")
async def review_package(
    run_id: UUID,
    _: Principal = Depends(internal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    run = await session.get(VerificationRun, run_id)
    if not run or run.status != "COMPLETED":
        raise Problem(
            404,
            "VERIFICATION_RUN_NOT_FOUND",
            "Verification run not found",
            "A completed verification run was not found.",
        )
    request = await session.get(VerificationRequest, run.request_id)
    candidates = (
        await session.scalars(
            select(CandidateEvaluation).where(CandidateEvaluation.run_id == run.id)
        )
    ).all()
    items = (
        await session.scalars(
            select(ItemEvaluation).where(ItemEvaluation.run_id == run.id)
        )
    ).all()
    findings = (
        await session.scalars(
            select(RuleFinding)
            .where(RuleFinding.run_id == run.id)
            .order_by(RuleFinding.rule_id)
        )
    ).all()
    return {
        "verification_id": str(request.id),
        "verification_run_id": str(run.id),
        "owner_org": str(request.verifier_org_id),
        "claim_source": request.claim_source,
        "claim_id": request.claim_id,
        "claim_revision": request.claim_revision,
        "input_snapshot_digest": run.input_snapshot_digest,
        "data_freshness": run.data_freshness,
        "assessment": {
            "encounter_match_status": run.encounter_match_status,
            "selected_encounter_id": str(run.selected_encounter_id)
            if run.selected_encounter_id
            else None,
            "identity_assurance": run.identity_assurance,
            "evidence_reconciliation_status": run.evidence_reconciliation_status,
            "duplicate_assessment_status": run.duplicate_assessment_status,
            "patient_confirmation_status": run.patient_confirmation_status,
            "review_required": run.review_required,
            "final_fraud_decision": None,
        },
        "candidates": [
            {
                "encounter_id": str(row.encounter_id),
                "evidence_snapshot_id": str(row.evidence_snapshot_id),
                "match_state": row.match_state,
                "reasons": row.reasons_json,
            }
            for row in candidates
        ],
        "items": [
            {
                "claim_item_ref": row.claim_item_ref,
                "match_result": row.match_result,
                "evidence_version_ref": str(row.evidence_version_ref)
                if row.evidence_version_ref
                else None,
                "reason": row.reason,
            }
            for row in items
        ],
        "findings": [
            {
                "rule_id": row.rule_id,
                "severity": row.severity,
                "finding_code": row.finding_code,
                "claim_item_ref": row.claim_item_ref,
                "explanation_facts": row.explanation_facts_json,
                "limitations": row.limitations_text,
            }
            for row in findings
        ],
    }
