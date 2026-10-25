"""Gate 2/3 integration and patient DTOs."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class Actor(BaseModel):
    external_id: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=64)


class EvidenceContent(BaseModel):
    code_system: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    display: str = Field(min_length=1, max_length=255)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=32)


class ClinicalEventRequest(BaseModel):
    source_event_id: str = Field(min_length=1, max_length=128)
    source_system: str = Field(min_length=1, max_length=64)
    source_sequence: int = Field(ge=1)
    external_record_id: str = Field(min_length=1, max_length=128)
    event_type: Literal["DIAGNOSIS", "PROCEDURE", "MEDICATION_PRESCRIBED", "MEDICATION_DISPENSED", "STAGE_COMPLETION", "DOCUMENT_FINGERPRINT"]
    record_version: Literal[1] = 1
    occurred_at: datetime
    actor: Actor
    content: EvidenceContent
    stage_completion: Literal["STARTED", "STAFF_COMPLETED"] | None = None


class CorrectionRequest(BaseModel):
    source_event_id: str = Field(min_length=1, max_length=128)
    source_system: str = Field(min_length=1, max_length=64)
    source_sequence: int = Field(ge=1)
    external_record_id: str = Field(min_length=1, max_length=128)
    record_version: int = Field(ge=2)
    occurred_at: datetime
    source_updated_at: datetime
    change_reason: str = Field(min_length=1, max_length=500)
    actor: Actor
    content: EvidenceContent
    stage_completion: Literal["STARTED", "STAFF_COMPLETED"] | None = None


class CancellationRequest(BaseModel):
    source_event_id: str = Field(min_length=1, max_length=128)
    source_system: str = Field(min_length=1, max_length=64)
    source_sequence: int = Field(ge=1)
    external_record_id: str = Field(min_length=1, max_length=128)
    record_version: int = Field(ge=2)
    source_updated_at: datetime
    cancel_reason: str = Field(min_length=1, max_length=500)
    actor: Actor


class EvidenceWriteResponse(BaseModel):
    evidence_id: UUID | None
    evidence_version_id: UUID | None = None
    record_version: int
    encounter_evidence_revision: int
    status: str
    mapping_status: str | None = None


class SyncCompleteRequest(BaseModel):
    source_system: str = Field(min_length=1, max_length=64)
    last_source_sequence: int = Field(ge=0)
    marked_complete_at: datetime


class SyncStatusResponse(BaseModel):
    encounter_id: UUID
    sync_status: str
    current_revision: int
    last_acked_source_sequence: int
    expected_final_sequence: int | None
    snapshot_id: UUID | None


class SummaryItem(BaseModel):
    evidence_id: UUID
    evidence_version_id: UUID
    version: int
    kind: str
    description: str
    quantity: Decimal | None
    unit: str | None
    recorded_status: str


class CheckoutSummaryResponse(BaseModel):
    snapshot_id: UUID
    encounter_id: UUID
    status: str
    evidence_revision: int
    presented_at: datetime | None
    items: list[SummaryItem]


class ItemResponseRequest(BaseModel):
    evidence_id: UUID
    response: Literal["CONFIRMED", "DISPUTED"]
    reason: Literal["SERVICE_NOT_RECEIVED", "MEDICATION_NOT_RECEIVED", "QUANTITY_DIFFERENT", "OTHER"] | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def dispute_needs_reason(self) -> "ItemResponseRequest":
        if self.response == "DISPUTED" and self.reason is None:
            raise ValueError("reason is required for a disputed item")
        if self.response == "CONFIRMED" and self.reason is not None:
            raise ValueError("reason is only valid for a disputed item")
        return self


class PatientResponseRequest(BaseModel):
    overall_response: Literal["CONFIRMED", "PARTIALLY_DISPUTED", "DISPUTED", "DECLINED"]
    items: list[ItemResponseRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_overall_response(self) -> "PatientResponseRequest":
        disputed = sum(item.response == "DISPUTED" for item in self.items)
        if self.overall_response == "CONFIRMED" and disputed:
            raise ValueError("CONFIRMED cannot contain disputed items")
        if self.overall_response in {"PARTIALLY_DISPUTED", "DISPUTED"} and not disputed:
            raise ValueError("a disputed overall response needs at least one disputed item")
        if self.overall_response == "PARTIALLY_DISPUTED" and disputed == len(self.items):
            raise ValueError("PARTIALLY_DISPUTED needs at least one confirmed item")
        if self.overall_response == "DISPUTED" and disputed != len(self.items):
            raise ValueError("DISPUTED cannot contain confirmed items")
        if self.overall_response == "DECLINED" and self.items:
            raise ValueError("DECLINED must not contain item responses")
        return self


class PatientResponseView(BaseModel):
    response_id: UUID
    snapshot_id: UUID
    overall_response: str
    submitted_at: datetime
    snapshot_status: str
