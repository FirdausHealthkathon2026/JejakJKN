"""Small query surface for verification requests and immutable run results."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import (
    CandidateEvaluation,
    ItemEvaluation,
    RuleFinding,
    VerificationRecheck,
    VerificationRequest,
    VerificationRequestItem,
    VerificationRun,
)


class VerificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def request(
        self, request_id: UUID, organization_id: UUID
    ) -> VerificationRequest | None:
        return await self.session.scalar(
            select(VerificationRequest).where(
                VerificationRequest.id == request_id,
                VerificationRequest.verifier_org_id == organization_id,
            )
        )

    async def by_idempotency(
        self, organization_id: UUID, key: str
    ) -> VerificationRequest | None:
        return await self.session.scalar(
            select(VerificationRequest).where(
                VerificationRequest.verifier_org_id == organization_id,
                VerificationRequest.idempotency_key == key,
            )
        )

    async def run(self, request: VerificationRequest) -> VerificationRun | None:
        if not request.latest_run_id:
            return None
        return await self.session.get(VerificationRun, request.latest_run_id)

    async def next_run_number(self, request_id: UUID) -> int:
        return (
            int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(VerificationRun)
                    .where(VerificationRun.request_id == request_id)
                )
                or 0
            )
            + 1
        )

    async def latest_per_claim(
        self, organization_id: UUID, limit: int
    ) -> list[tuple[VerificationRequest, VerificationRun]]:
        rows = (
            await self.session.execute(
                select(VerificationRequest, VerificationRun)
                .join(
                    VerificationRun,
                    VerificationRun.id == VerificationRequest.latest_run_id,
                )
                .where(VerificationRequest.verifier_org_id == organization_id)
                .order_by(VerificationRun.started_at.desc())
                .limit(limit)
            )
        ).all()
        latest: dict[tuple[str, str], tuple] = {}
        for request, run in rows:
            latest.setdefault((request.claim_source, request.claim_id), (request, run))
        return list(latest.values())

    async def finding_codes(self, run_ids: list[UUID]) -> dict[UUID, list[str]]:
        codes: dict[UUID, list[str]] = {}
        if run_ids:
            rows = await self.session.execute(
                select(RuleFinding.run_id, RuleFinding.finding_code).where(
                    RuleFinding.run_id.in_(run_ids)
                )
            )
            for run_id, code in rows.all():
                codes.setdefault(run_id, []).append(code)
        return codes

    async def item_evaluations(self, run_id: UUID) -> list[ItemEvaluation]:
        return list(
            (
                await self.session.scalars(
                    select(ItemEvaluation).where(ItemEvaluation.run_id == run_id)
                )
            ).all()
        )

    async def candidates(self, run_id: UUID) -> list[CandidateEvaluation]:
        return list(
            (
                await self.session.scalars(
                    select(CandidateEvaluation)
                    .where(CandidateEvaluation.run_id == run_id)
                    .order_by(CandidateEvaluation.compared_at)
                )
            ).all()
        )

    async def findings(self, run_id: UUID) -> list[RuleFinding]:
        return list(
            (
                await self.session.scalars(
                    select(RuleFinding)
                    .where(RuleFinding.run_id == run_id)
                    .order_by(RuleFinding.rule_id, RuleFinding.claim_item_ref)
                )
            ).all()
        )

    async def items(self, request_id: UUID) -> list[VerificationRequestItem]:
        return list(
            (
                await self.session.scalars(
                    select(VerificationRequestItem)
                    .where(VerificationRequestItem.request_id == request_id)
                    .order_by(VerificationRequestItem.item_ref)
                )
            ).all()
        )

    async def history(
        self, organization_id: UUID, claim_source: str, claim_id: str
    ) -> list[tuple[VerificationRequest, VerificationRun]]:
        rows = await self.session.execute(
            select(VerificationRequest, VerificationRun)
            .join(VerificationRun, VerificationRun.request_id == VerificationRequest.id)
            .where(
                VerificationRequest.verifier_org_id == organization_id,
                VerificationRequest.claim_source == claim_source,
                VerificationRequest.claim_id == claim_id,
            )
            .order_by(VerificationRun.started_at.desc())
        )
        return list(rows.tuples())

    async def recheck(
        self, organization_id: UUID, key: str
    ) -> VerificationRecheck | None:
        return await self.session.scalar(
            select(VerificationRecheck).where(
                VerificationRecheck.verifier_org_id == organization_id,
                VerificationRecheck.idempotency_key == key,
            )
        )
