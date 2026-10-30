"""Review API boundary models."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DecisionRequest(BaseModel):
    decision: Literal["NO_ACTION", "REQUEST_CLARIFICATION", "ESCALATE", "CLOSE_REVIEW"]
    reason: str = Field(min_length=10, max_length=2000)


class AssignRequest(BaseModel):
    assignee: str = Field(min_length=2, max_length=128)


class CaseEventView(BaseModel):
    kind: str
    actor_name: str
    code: str | None = None
    detail: str | None = None
    created_at: datetime


class CaseView(BaseModel):
    id: UUID
    verification_id: UUID
    verification_run_id: UUID
    claim_source: str
    claim_id: str
    state: str
    is_stale: bool
    opened_at: datetime
    assigned_name: str | None = None
    finding_codes: list[str] = Field(default_factory=list)
    review_package: dict[str, Any] | None = None
    narrative: dict[str, Any] | None = None
    narrative_method: str | None = None
    narrative_status: str | None = None
    narrative_generated_at: datetime | None = None
    events: list[CaseEventView] = Field(default_factory=list)


class DecisionView(BaseModel):
    id: UUID
    case_id: UUID
    decision: str
    reason: str
    evidence_digest: str
    created_at: datetime


class NarrativeRequest(BaseModel):
    assessment_ref: UUID
    method: Literal["TEMPLATE", "LLM"] = "TEMPLATE"
    model_info: str = "deterministic-v1"
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    narrative: dict[str, Any]
    validation_status: Literal["VALID", "FALLBACK"]
