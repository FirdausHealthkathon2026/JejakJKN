"""SQLAlchemy mappings owned exclusively by encounter-service."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("code_namespace", "external_code"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    code_namespace: Mapped[str] = mapped_column(String(64))
    external_code: Mapped[str] = mapped_column(String(64))
    org_type: Mapped[str] = mapped_column(String(32))
    display_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    participant_lookup_key: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )
    participant_number_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    display_name_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    display_name_normalized_hmac: Mapped[str] = mapped_column(String(64), index=True)
    identity_assurance: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PatientExternalId(Base):
    __tablename__ = "patient_external_ids"
    __table_args__ = (
        UniqueConstraint("source_system_id", "identity_type", "external_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id")
    )
    source_system_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    external_id: Mapped[str] = mapped_column(String(128))
    identity_type: Mapped[str] = mapped_column(String(64))
    assurance: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceSystem(Base):
    __tablename__ = "source_systems"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id")
    )
    client_id: Mapped[str] = mapped_column(String(128), unique=True)
    source_code: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mapping_version: Mapped[str] = mapped_column(String(32), default="map-v1.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Encounter(Base):
    __tablename__ = "encounters"
    __table_args__ = (
        Index(
            "idx_encounters_org_patient_started",
            "organization_id",
            "patient_id",
            "started_at",
            "ended_at",
        ),
        Index("idx_encounters_org_started", "organization_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id")
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id")
    )
    source_system_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_systems.id")
    )
    external_visit_reference: Mapped[str | None] = mapped_column(String(128))
    service_type: Mapped[str] = mapped_column(String(32), default="OUTPATIENT")
    status: Mapped[str] = mapped_column(String(32))
    presence_status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class QrRedemptionReceipt(Base):
    __tablename__ = "qr_redemption_receipts"
    __table_args__ = (UniqueConstraint("scanner_client_id", "idempotency_key"),)

    nonce_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(16))
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id")
    )
    encounter_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("encounters.id")
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id")
    )
    scanner_client_id: Mapped[str] = mapped_column(String(128))
    scanner_external_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    result: Mapped[str] = mapped_column(String(32), default="COMMITTED")
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EncounterException(Base):
    __tablename__ = "encounter_exceptions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    encounter_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("encounters.id"), index=True
    )
    exception_phase: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str] = mapped_column(String(128))
    actor_assurance: Mapped[str] = mapped_column(String(32), default="SOURCE_ASSERTED")
    evidence_ref: Mapped[str | None] = mapped_column(String(256))
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class InboxEvent(Base):
    __tablename__ = "inbox_events"

    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
