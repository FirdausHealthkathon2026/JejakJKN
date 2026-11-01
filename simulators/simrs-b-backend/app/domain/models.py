"""SIMRS-B local request and persistence models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
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


class SimrsBVisit(Base):
    __tablename__ = "simrs_b_visits"

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


class LocalRecord(Base):
    __tablename__ = "local_records"
    __table_args__ = (UniqueConstraint("encounter_id", "external_record_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    encounter_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("simrs_b_visits.encounter_id")
    )
    external_record_id: Mapped[str] = mapped_column(String(128))
    local_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    encounter_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("simrs_b_visits.encounter_id")
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


class LocalClinicalInput(BaseModel):
    jenis: str
    kode: str
    urutan: int = Field(ge=1)
    id_rekam: str = Field(min_length=1, max_length=128)
    id_peristiwa: str | None = None
    waktu: str | None = None
    petugas: str = "PETUGAS-B-01"
    peran: str = "CLINICIAN"
    jumlah: Any = None
    satuan: str | None = None


class LocalScanInput(BaseModel):
    token_qr: str = Field(min_length=32)
    id_pemindai: str = "PEMINDAI-B-01"
    referensi_kunjungan: str | None = None
