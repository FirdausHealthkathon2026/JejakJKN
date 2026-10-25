"""Evidence-service database queries."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CareEpisode, EvidenceQuarantine, EvidenceRecord, EvidenceVersion, PatientResponse, SummarySnapshot


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def episode(self, encounter_id: UUID, *, lock: bool = False) -> CareEpisode | None:
        query = select(CareEpisode).where(CareEpisode.encounter_id == encounter_id)
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def record(self, organization_id: UUID, source_system: str, external_record_id: str, *, lock: bool = False) -> EvidenceRecord | None:
        query = select(EvidenceRecord).where(EvidenceRecord.organization_id == organization_id, EvidenceRecord.source_system_id == source_system, EvidenceRecord.external_record_id == external_record_id)
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def version_by_event(self, encounter_id: UUID, source_event_id: str) -> EvidenceVersion | None:
        return await self.session.scalar(select(EvidenceVersion).where(EvidenceVersion.encounter_id == encounter_id, EvidenceVersion.source_event_id == source_event_id))

    async def quarantine_by_event(self, organization_id: UUID, source_system: str, source_event_id: str) -> EvidenceQuarantine | None:
        return await self.session.scalar(select(EvidenceQuarantine).where(EvidenceQuarantine.organization_id == organization_id, EvidenceQuarantine.source_system == source_system, EvidenceQuarantine.source_event_id == source_event_id))

    async def version_by_sequence(self, encounter_id: UUID, source_sequence: int) -> EvidenceVersion | None:
        return await self.session.scalar(select(EvidenceVersion).where(EvidenceVersion.encounter_id == encounter_id, EvidenceVersion.source_sequence == source_sequence))

    async def latest_version(self, evidence_id: UUID) -> EvidenceVersion | None:
        return await self.session.scalar(select(EvidenceVersion).where(EvidenceVersion.evidence_id == evidence_id).order_by(EvidenceVersion.version.desc()).limit(1))

    async def sequences(self, encounter_id: UUID) -> list[int]:
        values = await self.session.scalars(select(EvidenceVersion.source_sequence).where(EvidenceVersion.encounter_id == encounter_id, EvidenceVersion.source_sequence.is_not(None)).distinct().order_by(EvidenceVersion.source_sequence))
        return [value for value in values if value is not None]

    async def current_versions(self, encounter_id: UUID) -> list[tuple[EvidenceRecord, EvidenceVersion]]:
        result = await self.session.execute(
            select(EvidenceRecord, EvidenceVersion)
            .join(EvidenceVersion, (EvidenceVersion.evidence_id == EvidenceRecord.id) & (EvidenceVersion.version == EvidenceRecord.current_version))
            .where(EvidenceRecord.encounter_id == encounter_id, EvidenceRecord.status != "CANCELLED")
            .order_by(EvidenceVersion.occurred_at, EvidenceRecord.id)
        )
        return list(result.tuples())

    async def latest_snapshot(self, encounter_id: UUID) -> SummarySnapshot | None:
        return await self.session.scalar(select(SummarySnapshot).where(SummarySnapshot.encounter_id == encounter_id).order_by(SummarySnapshot.evidence_revision.desc(), SummarySnapshot.created_at.desc()).limit(1))

    async def snapshot(self, snapshot_id: UUID, *, lock: bool = False) -> SummarySnapshot | None:
        query = select(SummarySnapshot).where(SummarySnapshot.id == snapshot_id)
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def has_unresolved_quarantine(self, encounter_id: UUID) -> bool:
        return await self.session.scalar(select(EvidenceQuarantine.id).where(EvidenceQuarantine.encounter_id == encounter_id, EvidenceQuarantine.resolved.is_(False)).limit(1)) is not None

    async def response_for_snapshot(self, snapshot_id: UUID) -> PatientResponse | None:
        return await self.session.scalar(select(PatientResponse).where(PatientResponse.snapshot_id == snapshot_id).order_by(PatientResponse.submitted_at.desc()).limit(1))

    async def response_by_idempotency(self, key: str) -> PatientResponse | None:
        return await self.session.scalar(select(PatientResponse).where(PatientResponse.idempotency_key == key))

    async def expired_unanswered_snapshots(self, cutoff: datetime) -> list[tuple[SummarySnapshot, CareEpisode]]:
        result = await self.session.execute(
            select(SummarySnapshot, CareEpisode)
            .join(CareEpisode, CareEpisode.encounter_id == SummarySnapshot.encounter_id)
            .outerjoin(PatientResponse, PatientResponse.snapshot_id == SummarySnapshot.id)
            .where(SummarySnapshot.status == "READY", CareEpisode.sync_status == "SYNC_COMPLETE", SummarySnapshot.presented_at.is_not(None), SummarySnapshot.presented_at <= cutoff, PatientResponse.id.is_(None))
            .with_for_update(of=SummarySnapshot, skip_locked=True)
        )
        return list(result.tuples())
