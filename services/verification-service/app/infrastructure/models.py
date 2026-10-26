"""Verification runs, findings, associations, and durable messaging."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RuleCatalogVersion(Base):
    __tablename__ = "rule_catalog_versions"
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    mapping_version: Mapped[str] = mapped_column(String(32))
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    configuration_digest: Mapped[str] = mapped_column(String(64))
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VerificationRequest(Base):
    __tablename__ = "verification_requests"
    __table_args__ = (
        UniqueConstraint("verifier_org_id", "idempotency_key"),
        Index("idx_verif_req_claim", "claim_source", "claim_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    claim_source: Mapped[str] = mapped_column(String(64))
    claim_id: Mapped[str] = mapped_column(String(128))
    claim_revision: Mapped[str] = mapped_column(String(64))
    claim_relationship_type: Mapped[str] = mapped_column(String(32), default="ORIGINAL")
    related_claim_id: Mapped[str | None] = mapped_column(String(128))
    claim_digest: Mapped[str] = mapped_column(String(64))
    participant_lookup_key: Mapped[str | None] = mapped_column(String(64))
    patient_name_hmac: Mapped[str | None] = mapped_column(String(64))
    facility_namespace: Mapped[str] = mapped_column(String(64))
    facility_code: Mapped[str] = mapped_column(String(64))
    service_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    service_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    verifier_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    latest_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VerificationRequestItem(Base):
    __tablename__ = "verification_request_items"
    __table_args__ = (UniqueConstraint("request_id", "item_ref"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("verification_requests.id", ondelete="CASCADE"),
        index=True,
    )
    item_ref: Mapped[str] = mapped_column(String(64))
    item_type: Mapped[str] = mapped_column(String(32))
    code_system: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=1)
    unit: Mapped[str] = mapped_column(String(32))
    service_date_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_date_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    __table_args__ = (
        UniqueConstraint("request_id", "run_number"),
        Index("idx_verif_runs_dep_fp", "dependency_fingerprint"),
        CheckConstraint(
            "final_fraud_decision IS NULL", name="ck_no_automated_fraud_decision"
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("verification_requests.id"), index=True
    )
    run_number: Mapped[int] = mapped_column(Integer)
    ruleset_version: Mapped[str] = mapped_column(
        String(32), ForeignKey("rule_catalog_versions.version")
    )
    mapping_version: Mapped[str] = mapped_column(String(32))
    input_snapshot_digest: Mapped[str] = mapped_column(String(64), default="0" * 64)
    dependency_fingerprint: Mapped[str] = mapped_column(String(64), default="0" * 64)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    encounter_match_status: Mapped[str] = mapped_column(
        String(32), default="NO_ENCOUNTER_FOUND"
    )
    selected_encounter_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    evaluated_candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    identity_assurance: Mapped[str] = mapped_column(String(32), default="INSUFFICIENT")
    evidence_reconciliation_status: Mapped[str] = mapped_column(
        String(32), default="EVIDENCE_INCOMPLETE"
    )
    matched_items_count: Mapped[int] = mapped_column(Integer, default=0)
    unmatched_items_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_assessment_status: Mapped[str] = mapped_column(
        String(64), default="DUPLICATION_UNDETERMINED"
    )
    conflicting_claims_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    patient_confirmation_status: Mapped[str] = mapped_column(
        String(32), default="NOT_APPLICABLE"
    )
    review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    final_fraud_decision: Mapped[str | None] = mapped_column(String(32))
    data_freshness: Mapped[str] = mapped_column(String(32), default="CURRENT")
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CandidateEvaluation(Base):
    __tablename__ = "candidate_evaluations"
    __table_args__ = (
        UniqueConstraint("run_id", "encounter_id"),
        Index("idx_cand_eval_enc", "encounter_id", "evidence_revision"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        index=True,
    )
    encounter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    evidence_snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    encounter_revision: Mapped[int] = mapped_column(Integer)
    evidence_revision: Mapped[int] = mapped_column(Integer)
    identity_assurance: Mapped[str] = mapped_column(String(32))
    presence_status: Mapped[str] = mapped_column(String(32))
    patient_confirmation_status: Mapped[str] = mapped_column(String(32))
    match_state: Mapped[str] = mapped_column(String(32))
    score_facts_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reasons_json: Mapped[list[str]] = mapped_column(JSONB)
    compared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ItemEvaluation(Base):
    __tablename__ = "item_evaluations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        index=True,
    )
    encounter_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    claim_item_ref: Mapped[str] = mapped_column(String(64))
    evidence_version_ref: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    evidence_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    match_result: Mapped[str] = mapped_column(String(32))
    claimed_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    allocated_evidence_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    reason: Mapped[str] = mapped_column(String(255))


class RuleFinding(Base):
    __tablename__ = "rule_findings"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    finding_code: Mapped[str] = mapped_column(String(64))
    encounter_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    claim_item_ref: Mapped[str | None] = mapped_column(String(64))
    evidence_refs_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    explanation_facts_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    limitations_text: Mapped[str] = mapped_column(Text)


class ClaimEncounterAssociation(Base):
    __tablename__ = "claim_encounter_associations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    claim_source: Mapped[str] = mapped_column(String(64))
    claim_id: Mapped[str] = mapped_column(String(128))
    claim_revision: Mapped[str] = mapped_column(String(64))
    encounter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(32))
    effective_from_run: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("verification_runs.id")
    )
    superseded_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("claim_encounter_associations.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ClaimEvidenceAssociation(Base):
    __tablename__ = "claim_evidence_associations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    association_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("claim_encounter_associations.id", ondelete="CASCADE"),
    )
    claim_source: Mapped[str] = mapped_column(String(64))
    claim_id: Mapped[str] = mapped_column(String(128))
    claim_item_ref: Mapped[str] = mapped_column(String(64))
    evidence_ref: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    evidence_version_ref: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    allocated_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    relationship: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VerificationRecheck(Base):
    __tablename__ = "verification_rechecks"
    __table_args__ = (UniqueConstraint("verifier_org_id", "idempotency_key"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("verification_requests.id")
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("verification_runs.id")
    )
    verifier_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VerificationOutbox(Base):
    __tablename__ = "verification_outbox"
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


class VerificationInbox(Base):
    __tablename__ = "verification_inbox"
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
