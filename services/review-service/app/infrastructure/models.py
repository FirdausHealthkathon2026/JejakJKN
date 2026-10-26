from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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


class ReviewCase(Base):
    __tablename__ = "review_cases"
    __table_args__ = (
        Index("idx_review_cases_org_state", "owner_org", "state", "opened_at"),
        CheckConstraint(
            "state IN ('OPEN','IN_REVIEW','NEEDS_MORE_EVIDENCE','COMPLETED')"
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    verification_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    verification_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True)
    claim_source: Mapped[str] = mapped_column(String(64))
    claim_id: Mapped[str] = mapped_column(String(128))
    owner_org: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    assigned_to: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    state: Mapped[str] = mapped_column(String(32), default="OPEN")
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    review_package_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('NO_ACTION','REQUEST_CLARIFICATION','ESCALATE','CLOSE_REVIEW')"
        ),
        CheckConstraint("length(reason) >= 10"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("review_cases.id"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    actor_role: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    evidence_digest: Mapped[str] = mapped_column(String(64))
    supersedes_decision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("review_decisions.id")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NarrativeArtifact(Base):
    __tablename__ = "narrative_artifacts"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    assessment_ref: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True)
    method: Mapped[str] = mapped_column(String(32))
    model_info: Mapped[str] = mapped_column(String(128))
    input_digest: Mapped[str] = mapped_column(String(64))
    narrative_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    validation_status: Mapped[str] = mapped_column(String(32))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AccessAudit(Base):
    __tablename__ = "access_audit"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    actor_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    purpose: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_ref: Mapped[str] = mapped_column(String(128))
    request_id: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditChain(Base):
    __tablename__ = "audit_chain"
    __table_args__ = (
        UniqueConstraint("record_id"),
        Index("idx_audit_chain_partition", "partition_key", "sequence_no"),
    )
    sequence_no: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    partition_key: Mapped[str] = mapped_column(String(64))
    record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    record_type: Mapped[str] = mapped_column(String(64))
    payload_digest: Mapped[str] = mapped_column(String(64))
    previous_hash: Mapped[str] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64))
    signature_ref: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewOutbox(Base):
    __tablename__ = "review_outbox"
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
        DateTime(timezone=True), server_default=func.now()
    )


class ReviewInbox(Base):
    __tablename__ = "review_inbox"
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
