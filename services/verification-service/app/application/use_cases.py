"""Verifier request intake, idempotency, ownership, and read models."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.jwt_verifier import Principal
from jejakjkn_canonical.problems import Problem

from app.api.schemas import VerificationRequestBody
from app.config import Settings
from app.infrastructure.models import (
    VerificationOutbox,
    VerificationRecheck,
    VerificationRequest,
    VerificationRequestItem,
    VerificationRun,
)
from app.infrastructure.repositories import VerificationRepository


class VerificationApplication:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session, self.settings, self.repo = (
            session,
            settings,
            VerificationRepository(session),
        )

    async def submit(
        self, body: VerificationRequestBody, key: str, principal: Principal
    ) -> tuple[dict, bool]:
        org_id = _organization(principal)
        digest = _digest(body.model_dump(mode="json"))
        existing = await self.repo.by_idempotency(org_id, key)
        if existing:
            if existing.claim_digest != digest:
                raise Problem(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency key conflict",
                    "The key was already used with a different payload.",
                )
            run = await self.repo.run(existing)
            return _queued(existing, run), True
        request_id, run_id = uuid4(), uuid4()
        request = VerificationRequest(
            id=request_id,
            claim_source=body.claim_source,
            claim_id=body.claim_id,
            claim_revision=body.claim_revision,
            claim_relationship_type=body.relationship.type,
            related_claim_id=body.relationship.related_claim_id,
            claim_digest=digest,
            participant_lookup_key=_blind(
                body.patient.participant_number,
                self.settings.participant_lookup_hmac_key,
            )
            if body.patient.participant_number
            else None,
            patient_name_hmac=_blind(
                body.patient.full_name,
                self.settings.participant_lookup_hmac_key,
                lower=True,
            )
            if body.patient.full_name
            else None,
            facility_namespace=body.facility.namespace,
            facility_code=body.facility.code,
            service_period_start=body.service_period.start,
            service_period_end=body.service_period.end,
            requested_by=UUID(principal.subject),
            verifier_org_id=org_id,
            idempotency_key=key,
            latest_run_id=run_id,
        )
        run = VerificationRun(
            id=run_id,
            request_id=request_id,
            run_number=1,
            ruleset_version=self.settings.ruleset_version,
            mapping_version=self.settings.mapping_version,
        )
        self.session.add_all(
            [request, run]
            + [
                VerificationRequestItem(
                    id=uuid4(), request_id=request_id, **item.model_dump()
                )
                for item in body.items
            ]
        )
        self.session.add(
            _event("verification.requested.v1", request, run, principal.subject)
        )
        await self.session.commit()
        return _queued(request, run), False

    async def assessment(self, request_id: UUID, principal: Principal) -> dict:
        request = await self._owned(request_id, principal)
        run = await self.repo.run(request)
        if not run:
            raise Problem(
                404,
                "VERIFICATION_RUN_NOT_FOUND",
                "Run not found",
                "No run exists for this verification.",
            )
        return _assessment(request, run)

    async def candidates(self, request_id: UUID, principal: Principal) -> list[dict]:
        request = await self._owned(request_id, principal)
        run = await self.repo.run(request)
        return (
            [
                {
                    "encounter_id": row.encounter_id,
                    "evidence_snapshot_id": row.evidence_snapshot_id,
                    "encounter_revision": row.encounter_revision,
                    "evidence_revision": row.evidence_revision,
                    "identity_assurance": row.identity_assurance,
                    "presence_status": row.presence_status,
                    "patient_confirmation_status": row.patient_confirmation_status,
                    "match_state": row.match_state,
                    "reasons": row.reasons_json,
                    "started_at": row.score_facts_json.get("started_at"),
                    "ended_at": row.score_facts_json.get("ended_at"),
                    "service_type": row.score_facts_json.get("service_type"),
                }
                for row in await self.repo.candidates(run.id)
            ]
            if run
            else []
        )

    async def findings(self, request_id: UUID, principal: Principal) -> list[dict]:
        request = await self._owned(request_id, principal)
        run = await self.repo.run(request)
        return (
            [
                {
                    "rule_id": row.rule_id,
                    "rule_version": row.rule_version,
                    "severity": row.severity,
                    "finding_code": row.finding_code,
                    "encounter_id": row.encounter_id,
                    "claim_item_ref": row.claim_item_ref,
                    "evidence_refs": row.evidence_refs_json,
                    "explanation_facts": row.explanation_facts_json,
                    "limitations": row.limitations_text,
                }
                for row in await self.repo.findings(run.id)
            ]
            if run
            else []
        )

    async def recheck(
        self, request_id: UUID, key: str, principal: Principal
    ) -> tuple[dict, bool]:
        request = await self._owned(request_id, principal)
        existing = await self.repo.recheck(request.verifier_org_id, key)
        if existing:
            return _queued(
                request, await self.session.get(VerificationRun, existing.run_id)
            ), True
        run = VerificationRun(
            id=uuid4(),
            request_id=request.id,
            run_number=await self.repo.next_run_number(request.id),
            ruleset_version=self.settings.ruleset_version,
            mapping_version=self.settings.mapping_version,
        )
        request.latest_run_id, request.request_status = run.id, "QUEUED"
        self.session.add(run)
        await self.session.flush()
        self.session.add_all(
            [
                VerificationRecheck(
                    id=uuid4(),
                    request_id=request.id,
                    run_id=run.id,
                    verifier_org_id=request.verifier_org_id,
                    idempotency_key=key,
                ),
                _event("verification.requested.v1", request, run, principal.subject),
            ]
        )
        await self.session.commit()
        return _queued(request, run), False

    async def worklist(self, principal: Principal, limit: int) -> list[dict]:
        rows = await self.repo.latest_per_claim(_organization(principal), limit)
        findings = await self.repo.finding_codes([run.id for _, run in rows])
        return [
            _assessment(request, run) | {"finding_codes": findings.get(run.id, [])}
            for request, run in rows
        ]

    async def item_results(self, request_id: UUID, principal: Principal) -> list[dict]:
        request = await self._owned(request_id, principal)
        run = await self.repo.run(request)
        if not run:
            return []
        items = {row.item_ref: row for row in await self.repo.items(request.id)}
        return [
            {
                "claim_item_ref": row.claim_item_ref,
                "match_result": row.match_result,
                "claimed_quantity": row.claimed_quantity,
                "allocated_evidence_quantity": row.allocated_evidence_quantity,
                "unit": items[row.claim_item_ref].unit
                if row.claim_item_ref in items
                else None,
                "item_type": items[row.claim_item_ref].item_type
                if row.claim_item_ref in items
                else None,
            }
            for row in await self.repo.item_evaluations(run.id)
        ]

    async def history(
        self, claim_source: str, claim_id: str, principal: Principal
    ) -> list[dict]:
        return [
            _assessment(request, run)
            for request, run in await self.repo.history(
                _organization(principal), claim_source, claim_id
            )
        ]

    async def _owned(
        self, request_id: UUID, principal: Principal
    ) -> VerificationRequest:
        request = await self.repo.request(request_id, _organization(principal))
        if not request:
            raise Problem(
                404,
                "VERIFICATION_NOT_FOUND",
                "Verification not found",
                "The verification was not found.",
            )
        return request


def _organization(principal: Principal) -> UUID:
    if not principal.organization_id:
        raise Problem(
            403,
            "ORGANIZATION_REQUIRED",
            "Organization required",
            "Verifier token has no organization.",
        )
    return principal.organization_id


def _blind(value: str, key_hex: str, *, lower: bool = False) -> str:
    normalized = value.strip().lower() if lower else value.strip().upper()
    return hmac.new(
        bytes.fromhex(key_hex), normalized.encode(), hashlib.sha256
    ).hexdigest()


def _digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _queued(request: VerificationRequest, run: VerificationRun) -> dict:
    return {"verification_id": request.id, "run_id": run.id, "status": run.status}


def _assessment(request: VerificationRequest, run: VerificationRun) -> dict:
    base = f"/api/v1/verifications/{request.id}"
    return {
        "verification_id": request.id,
        "run_id": run.id,
        "status": run.status,
        "claim_source": request.claim_source,
        "claim_id": request.claim_id,
        "claim_revision": request.claim_revision,
        "encounter_match_status": run.encounter_match_status,
        "selected_encounter_id": run.selected_encounter_id,
        "candidate_count": run.candidate_count,
        "evaluated_candidate_count": run.evaluated_candidate_count,
        "identity_assurance": run.identity_assurance,
        "evidence_reconciliation_status": run.evidence_reconciliation_status,
        "matched_items_count": run.matched_items_count,
        "unmatched_items_count": run.unmatched_items_count,
        "duplicate_assessment_status": run.duplicate_assessment_status,
        "conflicting_claims": run.conflicting_claims_json,
        "patient_confirmation_status": run.patient_confirmation_status,
        "review_required": run.review_required,
        "final_fraud_decision": None,
        "data_freshness": run.data_freshness,
        "ruleset_version": run.ruleset_version,
        "mapping_version": run.mapping_version,
        "created_at": run.started_at,
        "completed_at": run.ended_at,
        "candidates_url": f"{base}/candidates",
        "findings_url": f"{base}/findings",
    }


def _event(
    event_type: str, request: VerificationRequest, run: VerificationRun, actor: str
) -> VerificationOutbox:
    now = datetime.now(UTC)
    return VerificationOutbox(
        event_id=uuid4(),
        event_type=event_type,
        aggregate_id=str(run.id),
        aggregate_revision=run.run_number,
        organization_id=str(request.verifier_org_id),
        correlation_id=str(request.id),
        causation_id=None,
        payload={
            "verification_id": str(request.id),
            "run_id": str(run.id),
            "actor_id": actor,
        },
        occurred_at=now,
    )
