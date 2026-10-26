"""Pydantic v2 request/response DTOs for verification-service."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ClaimRelationship(BaseModel):
    type: Literal["ORIGINAL", "CORRECTION", "REVERSAL"] = "ORIGINAL"
    related_claim_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def valid_relation(self):
        if (self.type == "ORIGINAL") == bool(self.related_claim_id):
            raise ValueError(
                "related_claim_id is required only for CORRECTION or REVERSAL"
            )
        return self


class PatientIdentity(BaseModel):
    participant_number: str | None = Field(default=None, min_length=3, max_length=64)
    full_name: str | None = Field(default=None, min_length=2, max_length=255)

    @model_validator(mode="after")
    def has_identity(self):
        if not self.participant_number and not self.full_name:
            raise ValueError("participant_number or full_name is required")
        return self


class Facility(BaseModel):
    namespace: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)


class ServicePeriod(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end:
            raise ValueError("service period start must not be after end")
        return self


class ClaimItem(BaseModel):
    item_ref: str = Field(min_length=1, max_length=64)
    item_type: Literal["DIAGNOSIS", "PROCEDURE", "MEDICATION", "MEDICATION_DISPENSE"]
    code_system: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit: str = Field(default="1", min_length=1, max_length=32)
    service_date_start: datetime | None = None
    service_date_end: datetime | None = None


class VerificationRequestBody(BaseModel):
    claim_source: str = Field(min_length=1, max_length=64)
    claim_id: str = Field(min_length=1, max_length=128)
    claim_revision: str = Field(min_length=1, max_length=64)
    relationship: ClaimRelationship = Field(default_factory=ClaimRelationship)
    patient: PatientIdentity
    facility: Facility
    service_period: ServicePeriod
    items: list[ClaimItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_items(self):
        refs = [item.item_ref for item in self.items]
        if len(refs) != len(set(refs)):
            raise ValueError("item_ref values must be unique")
        return self


class QueuedVerification(BaseModel):
    verification_id: UUID
    run_id: UUID
    status: str


class AssessmentView(BaseModel):
    verification_id: UUID
    run_id: UUID
    status: str
    claim_source: str
    claim_id: str
    claim_revision: str
    encounter_match_status: str
    selected_encounter_id: UUID | None
    candidate_count: int
    evaluated_candidate_count: int
    identity_assurance: str
    evidence_reconciliation_status: str
    matched_items_count: int
    unmatched_items_count: int
    duplicate_assessment_status: str
    conflicting_claims: list[str]
    patient_confirmation_status: str
    review_required: bool
    final_fraud_decision: None = None
    data_freshness: str
    ruleset_version: str
    mapping_version: str
    created_at: datetime
    completed_at: datetime | None
    candidates_url: str
    findings_url: str


class CandidateView(BaseModel):
    encounter_id: UUID
    evidence_snapshot_id: UUID
    encounter_revision: int
    evidence_revision: int
    identity_assurance: str
    presence_status: str
    patient_confirmation_status: str
    match_state: str
    reasons: list[str]


class FindingView(BaseModel):
    rule_id: str
    rule_version: str
    severity: str
    finding_code: str
    encounter_id: UUID | None
    claim_item_ref: str | None
    evidence_refs: list[str]
    explanation_facts: dict
    limitations: str
