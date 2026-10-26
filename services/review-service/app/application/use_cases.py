"""Human review use cases; no automated fraud or payment mutation lives here."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.jwt_verifier import Principal
from jejakjkn_canonical.problems import Problem

from app.api.schemas import DecisionRequest
from app.domain.audit_chain import GENESIS, digest_payload, record_hash
from app.infrastructure.models import (
    AccessAudit,
    AuditChain,
    NarrativeArtifact,
    ReviewCase,
    ReviewDecision,
    ReviewOutbox,
)


class ReviewApplication:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _org(principal: Principal) -> UUID:
        if not principal.organization_id:
            raise Problem(
                403,
                "ORGANIZATION_REQUIRED",
                "Forbidden",
                "An organization claim is required.",
            )
        return principal.organization_id

    @staticmethod
    def _case(
        row: ReviewCase, *, detail: bool = False, narrative: dict | None = None
    ) -> dict:
        return {
            "id": row.id,
            "verification_id": row.verification_id,
            "verification_run_id": row.verification_run_id,
            "claim_source": row.claim_source,
            "claim_id": row.claim_id,
            "state": row.state,
            "is_stale": row.is_stale,
            "opened_at": row.opened_at,
            "review_package": row.review_package_json if detail else None,
            "narrative": narrative if detail else None,
        }

    async def list_cases(self, principal: Principal) -> list[dict]:
        rows = (
            await self.session.scalars(
                select(ReviewCase)
                .where(ReviewCase.owner_org == self._org(principal))
                .order_by(ReviewCase.opened_at.desc())
            )
        ).all()
        return [self._case(row) for row in rows]

    async def get_case(
        self, case_id: UUID, principal: Principal, request_id: str, purpose: str
    ) -> dict:
        row = await self.session.scalar(
            select(ReviewCase).where(
                ReviewCase.id == case_id, ReviewCase.owner_org == self._org(principal)
            )
        )
        if not row:
            raise Problem(
                404,
                "REVIEW_CASE_NOT_FOUND",
                "Review case not found",
                "No review case was found.",
            )
        narrative = await self.session.scalar(
            select(NarrativeArtifact).where(
                NarrativeArtifact.assessment_ref == row.verification_run_id
            )
        )
        audit = AccessAudit(
            id=uuid4(),
            actor_id=UUID(principal.subject),
            actor_org_id=self._org(principal),
            purpose=purpose,
            action="READ",
            resource_type="REVIEW_CASE",
            resource_ref=str(row.id),
            request_id=request_id,
            outcome="ALLOWED",
        )
        self.session.add(audit)
        await self._append_audit(
            str(row.owner_org),
            audit.id,
            "SENSITIVE_READ",
            {"case_id": str(row.id), "actor": principal.subject, "purpose": purpose},
        )
        await self.session.commit()
        return self._case(
            row, detail=True, narrative=narrative.narrative_json if narrative else None
        )

    async def decide(
        self, case_id: UUID, body: DecisionRequest, key: str, principal: Principal
    ) -> tuple[dict, bool]:
        replay = await self.session.scalar(
            select(ReviewDecision).where(ReviewDecision.idempotency_key == key)
        )
        if replay:
            if replay.case_id != case_id:
                raise Problem(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "Conflict",
                    "The key belongs to another case.",
                )
            return self._decision(replay), True
        row = await self.session.scalar(
            select(ReviewCase)
            .where(
                ReviewCase.id == case_id, ReviewCase.owner_org == self._org(principal)
            )
            .with_for_update()
        )
        if not row:
            raise Problem(
                404,
                "REVIEW_CASE_NOT_FOUND",
                "Review case not found",
                "No review case was found.",
            )
        previous = await self.session.scalar(
            select(ReviewDecision)
            .where(ReviewDecision.case_id == case_id)
            .order_by(ReviewDecision.created_at.desc())
            .limit(1)
        )
        decision = ReviewDecision(
            id=uuid4(),
            case_id=case_id,
            actor_id=UUID(principal.subject),
            actor_role="review_supervisor"
            if "review_supervisor" in principal.roles
            else "verifier",
            decision=body.decision,
            reason=body.reason,
            evidence_digest=digest_payload(row.review_package_json),
            supersedes_decision_id=previous.id if previous else None,
            idempotency_key=key,
        )
        row.state = {
            "REQUEST_CLARIFICATION": "NEEDS_MORE_EVIDENCE",
            "ESCALATE": "IN_REVIEW",
            "NO_ACTION": "COMPLETED",
            "CLOSE_REVIEW": "COMPLETED",
        }[body.decision]
        now = datetime.now(UTC)
        self.session.add_all(
            [
                decision,
                ReviewOutbox(
                    event_id=uuid4(),
                    event_type="review.decision_recorded.v1",
                    aggregate_id=str(case_id),
                    aggregate_revision=1,
                    organization_id=str(row.owner_org),
                    correlation_id=str(row.verification_id),
                    causation_id=None,
                    payload={
                        "case_id": str(case_id),
                        "decision": body.decision,
                        "final_fraud_decision": None,
                    },
                    occurred_at=now,
                ),
            ]
        )
        await self.session.flush()
        await self._append_audit(
            str(row.owner_org),
            decision.id,
            "REVIEW_DECISION",
            {"case_id": str(case_id), "decision": body.decision, "reason": body.reason},
        )
        await self.session.commit()
        return self._decision(decision), False

    async def _append_audit(
        self, partition: str, record_id: UUID, record_type: str, payload: dict
    ) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:partition))"),
            {"partition": partition},
        )
        previous = await self.session.scalar(
            select(AuditChain)
            .where(AuditChain.partition_key == partition)
            .order_by(AuditChain.sequence_no.desc())
            .limit(1)
        )
        created = datetime.now(UTC)
        payload_digest = digest_payload(payload)
        prior = previous.record_hash if previous else GENESIS
        self.session.add(
            AuditChain(
                partition_key=partition,
                record_id=record_id,
                record_type=record_type,
                payload_digest=payload_digest,
                previous_hash=prior,
                record_hash=record_hash(
                    partition, prior, str(record_id), payload_digest, created
                ),
                created_at=created,
            )
        )

    @staticmethod
    def _decision(row: ReviewDecision) -> dict:
        return {
            "id": row.id,
            "case_id": row.case_id,
            "decision": row.decision,
            "reason": row.reason,
            "evidence_digest": row.evidence_digest,
            "created_at": row.created_at,
        }
