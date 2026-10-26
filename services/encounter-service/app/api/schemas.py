"""Pydantic request and response models for Gate 1."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class IssueQrRequest(BaseModel):
    purpose: Literal["CHECK_IN", "CHECK_OUT"]
    encounter_id: UUID | None = None
    facility_hint: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def checkout_requires_encounter(self) -> "IssueQrRequest":
        if self.purpose == "CHECK_OUT" and self.encounter_id is None:
            raise ValueError("encounter_id is required for CHECK_OUT")
        if self.purpose == "CHECK_IN" and self.encounter_id is not None:
            raise ValueError("encounter_id is not accepted for CHECK_IN")
        return self


class QrTokenResponse(BaseModel):
    token: str
    purpose: str
    expires_at: datetime
    ttl_seconds: int


class RedeemQrRequest(BaseModel):
    qr_token: str = Field(min_length=32)
    facility_external_code: str = Field(min_length=1, max_length=64)
    scanner_external_id: str = Field(min_length=1, max_length=128)
    external_visit_reference: str | None = Field(default=None, max_length=128)


class CheckInResponse(BaseModel):
    encounter_id: UUID
    check_in_status: Literal["QR_VERIFIED"] = "QR_VERIFIED"
    encounter_status: Literal["OPEN"] = "OPEN"
    created_at: datetime


class CheckOutResponse(BaseModel):
    encounter_id: UUID
    encounter_status: Literal["CHECKED_OUT"] = "CHECKED_OUT"
    checked_out_at: datetime


class EncounterSummary(BaseModel):
    encounter_id: UUID
    facility_code: str
    facility_display_name: str
    service_type: str
    status: str
    presence_status: str
    started_at: datetime
    ended_at: datetime | None
    check_in_successful: bool
    check_out_successful: bool
    confirmation_status: Literal["NOT_AVAILABLE"] = "NOT_AVAILABLE"


class EncounterListResponse(BaseModel):
    items: list[EncounterSummary]
    next_cursor: UUID | None = None


class ExceptionRequest(BaseModel):
    exception_phase: Literal["CHECK_IN", "CHECK_OUT"]
    reason_code: Literal["NO_SMARTPHONE", "EMERGENCY_UNCONSCIOUS", "QR_DEVICE_FAILURE", "NETWORK_OUTAGE", "PATIENT_INCAPACITATED"]
    patient_id: UUID | None = None
    facility_external_code: str = Field(min_length=1, max_length=64)
    service_type: Literal["OUTPATIENT", "INPATIENT", "EMERGENCY"] = "OUTPATIENT"
    approved_by: str = Field(min_length=1, max_length=128)
    evidence_ref: str | None = Field(default=None, max_length=256)
    notes: str | None = Field(default=None, max_length=500)


class ExceptionResponse(BaseModel):
    encounter_id: UUID
    encounter_status: str
    presence_status: Literal["EXCEPTION_DOCUMENTED"] = "EXCEPTION_DOCUMENTED"


class CandidateSearchRequest(BaseModel):
    participant_lookup_key: str | None = Field(default=None, min_length=64, max_length=64)
    patient_name_hmac: str | None = Field(default=None, min_length=64, max_length=64)
    facility_namespace: str = Field(min_length=1, max_length=64)
    facility_code: str = Field(min_length=1, max_length=64)
    service_period_start: datetime
    service_period_end: datetime
    safety_limit: int = Field(default=10, ge=1, le=10)

    @model_validator(mode="after")
    def valid_period(self) -> "CandidateSearchRequest":
        if self.service_period_end < self.service_period_start:
            raise ValueError("service_period_end must not precede service_period_start")
        if bool(self.participant_lookup_key) == bool(self.patient_name_hmac):
            raise ValueError("provide exactly one patient identity lookup key")
        return self


class CandidateEncounter(BaseModel):
    encounter_id: UUID
    patient_id: UUID
    organization_id: UUID
    status: str
    presence_status: str
    service_type: str
    started_at: datetime
    ended_at: datetime | None
    revision: int


class CandidateSearchResponse(BaseModel):
    candidates: list[CandidateEncounter]
    truncated_by_limit: bool


class EligibilityResponse(CandidateEncounter):
    eligible: bool
