"""Evidence and frozen patient-summary persistence."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CareEpisode(Base):
    __tablename__ = "care_episodes"

    encounter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    patient_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    encounter_status: Mapped[str] = mapped_column(String(32), default="OPEN")
    presence_status: Mapped[str] = mapped_column(String(32), default="QR_VERIFIED")
    current_revision: Mapped[int] = mapped_column(Integer, default=0)
    last_acked_source_sequence: Mapped[int] = mapped_column(Integer, default=0)
    expected_final_sequence: Mapped[int | None] = mapped_column(Integer)
    sync_status: Mapped[str] = mapped_column(String(32), default="RECEIVING")
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    __table_args__ = (UniqueConstraint("organization_id", "source_system_id", "external_record_id"), Index("idx_evidence_records_enc", "encounter_id", "status"))

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    encounter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("care_episodes.encounter_id"))
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    source_system_id: Mapped[str] = mapped_column(String(64))
    external_record_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EvidenceVersion(Base):
    __tablename__ = "evidence_versions"
    __table_args__ = (UniqueConstraint("evidence_id", "version"), UniqueConstraint("encounter_id", "source_event_id"), UniqueConstraint("encounter_id", "source_sequence"), Index("idx_evidence_versions_enc", "encounter_id", "version"))

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence_records.id"))
    encounter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("care_episodes.encounter_id"))
    version: Mapped[int] = mapped_column(Integer)
    source_event_id: Mapped[str] = mapped_column(String(128))
    source_sequence: Mapped[int] = mapped_column(Integer)
    event_action: Mapped[str] = mapped_column(String(32))
    code_system: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(64))
    canonical_code_system: Mapped[str | None] = mapped_column(String(64))
    canonical_code: Mapped[str | None] = mapped_column(String(64))
    mapping_status: Mapped[str] = mapped_column(String(32), default="MAPPED")
    display_text: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    unit: Mapped[str | None] = mapped_column(String(32))
    canonical_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    canonical_unit: Mapped[str | None] = mapped_column(String(32))
    stage_completion: Mapped[str | None] = mapped_column(String(32))
    source_actor_id: Mapped[str] = mapped_column(String(128))
    source_actor_role: Mapped[str] = mapped_column(String(64))
    actor_assurance: Mapped[str] = mapped_column(String(32), default="SOURCE_ASSERTED")
    change_reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payload_digest: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceQuarantine(Base):
    __tablename__ = "evidence_quarantine"
    __table_args__ = (UniqueConstraint("organization_id", "source_system", "source_event_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    encounter_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_system: Mapped[str] = mapped_column(String(64))
    source_event_id: Mapped[str] = mapped_column(String(128))
    external_record_id: Mapped[str] = mapped_column(String(128))
    received_version: Mapped[int] = mapped_column(Integer)
    current_known_version: Mapped[int | None] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String(64))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CareStage(Base):
    __tablename__ = "care_stages"
    __table_args__ = (Index("idx_care_stages_enc", "encounter_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    encounter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("care_episodes.encounter_id"))
    stage_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[str] = mapped_column(String(128))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SummarySnapshot(Base):
    __tablename__ = "summary_snapshots"
    __table_args__ = (UniqueConstraint("encounter_id", "evidence_revision"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    encounter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("care_episodes.encounter_id"), index=True)
    evidence_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    items_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    content_digest: Mapped[str] = mapped_column(String(64))
    presented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PatientResponse(Base):
    __tablename__ = "patient_responses"
    __table_args__ = (Index("idx_patient_responses_enc", "encounter_id", "submitted_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("summary_snapshots.id"))
    encounter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("care_episodes.encounter_id"))
    patient_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    response_type: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(32), default="PATIENT_APP")
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    request_digest: Mapped[str] = mapped_column(String(64))
    superseded_by_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("summary_snapshots.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PatientItemResponse(Base):
    __tablename__ = "patient_item_responses"
    __table_args__ = (UniqueConstraint("response_id", "evidence_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    response_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patient_responses.id", ondelete="CASCADE"))
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence_records.id"))
    evidence_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence_versions.id"))
    result: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str | None] = mapped_column(String(64))
    note_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)


class EvidenceOutbox(Base):
    __tablename__ = "evidence_outbox"

    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128))
    aggregate_id: Mapped[str] = mapped_column(String(128))
    aggregate_revision: Mapped[int] = mapped_column(Integer)
    organization_id: Mapped[str] = mapped_column(String(128))
    correlation_id: Mapped[str] = mapped_column(String(128))
    causation_id: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class EvidenceInbox(Base):
    __tablename__ = "evidence_inbox"

    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
