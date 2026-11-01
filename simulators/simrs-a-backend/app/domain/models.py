"""SIMRS-A source records and durable delivery outbox."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SimrsVisit(Base):
    __tablename__ = "simrs_visits"

    encounter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    participant_number: Mapped[str | None] = mapped_column(String(64))
    external_visit_reference: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    presence_status: Mapped[str] = mapped_column(String(32), default="QR_VERIFIED")
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_source_sequence: Mapped[int] = mapped_column(Integer, default=1)
    sync_status: Mapped[str] = mapped_column(String(32), default="LOCAL_ONLY")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClinicalRecord(Base):
    __tablename__ = "clinical_records"
    __table_args__ = (UniqueConstraint("encounter_id", "external_record_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    encounter_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("simrs_visits.encounter_id")
    )
    external_record_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(32))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClinicalVersion(Base):
    __tablename__ = "clinical_versions"
    __table_args__ = (UniqueConstraint("record_id", "version"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    record_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clinical_records.id")
    )
    version: Mapped[int] = mapped_column(Integer)
    source_event_id: Mapped[str] = mapped_column(String(128), unique=True)
    source_sequence: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    encounter_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("simrs_visits.encounter_id")
    )
    target_path: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    delivery_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
