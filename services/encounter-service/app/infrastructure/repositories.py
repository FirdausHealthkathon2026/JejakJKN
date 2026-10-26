"""Encounter database queries; no other service database is imported."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Encounter, Organization, Patient, QrRedemptionReceipt, SourceSystem


class EncounterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def patient(self, patient_id: UUID) -> Patient | None:
        return await self.session.get(Patient, patient_id)

    async def organization(self, namespace: str, code: str) -> Organization | None:
        return await self.session.scalar(select(Organization).where(Organization.code_namespace == namespace, Organization.external_code == code, Organization.status == "ACTIVE"))

    async def source_system(self, client_id: str) -> SourceSystem | None:
        return await self.session.scalar(select(SourceSystem).where(SourceSystem.client_id == client_id, SourceSystem.enabled.is_(True)))

    async def encounter(self, encounter_id: UUID) -> Encounter | None:
        return await self.session.get(Encounter, encounter_id)

    async def encounter_for_update(self, encounter_id: UUID) -> Encounter | None:
        return await self.session.scalar(select(Encounter).where(Encounter.id == encounter_id).with_for_update())

    async def receipt(self, digest: str) -> QrRedemptionReceipt | None:
        return await self.session.get(QrRedemptionReceipt, digest)

    async def receipt_by_idempotency(self, scanner_client_id: str, idempotency_key: str) -> QrRedemptionReceipt | None:
        return await self.session.scalar(select(QrRedemptionReceipt).where(QrRedemptionReceipt.scanner_client_id == scanner_client_id, QrRedemptionReceipt.idempotency_key == idempotency_key))

    async def patient_encounters(self, patient_id: UUID, limit: int, cursor: UUID | None) -> list[tuple[Encounter, Organization]]:
        query: Select[tuple[Encounter, Organization]] = select(Encounter, Organization).join(Organization, Organization.id == Encounter.organization_id).where(Encounter.patient_id == patient_id)
        if cursor:
            cursor_row = await self.encounter(cursor)
            if cursor_row:
                query = query.where(Encounter.started_at < cursor_row.started_at)
        result = await self.session.execute(query.order_by(Encounter.started_at.desc(), Encounter.id).limit(limit + 1))
        return list(result.tuples())

    async def search_candidates(
        self,
        *,
        participant_lookup_key: str | None,
        patient_name_hmac: str | None,
        organization_id: UUID,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[Encounter]:
        query = (
            select(Encounter)
            .join(Patient, Patient.id == Encounter.patient_id)
            .where(
                Patient.participant_lookup_key == participant_lookup_key if participant_lookup_key else Patient.display_name_normalized_hmac == patient_name_hmac,
                Encounter.organization_id == organization_id,
                Encounter.started_at <= end,
                or_(Encounter.ended_at.is_(None), Encounter.ended_at >= start),
            )
            .order_by(Encounter.started_at, Encounter.id)
            .limit(limit + 1)
        )
        return list((await self.session.scalars(query)).all())
