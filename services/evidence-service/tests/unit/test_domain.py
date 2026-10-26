from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.schemas import ItemResponseRequest, PatientResponseRequest
from app.application.use_cases import _contiguous
from app.domain.policies import VISIBLE_SUMMARY_KINDS, internal_kind, mapping_status


def test_contiguous_watermark_stops_at_first_gap() -> None:
    assert _contiguous([]) == 0
    assert _contiguous([1, 2, 4, 5]) == 2
    assert _contiguous([1, 2, 3]) == 3


def test_prescription_is_not_a_dispense_summary_item() -> None:
    assert internal_kind("MEDICATION_PRESCRIBED") not in VISIBLE_SUMMARY_KINDS
    assert internal_kind("MEDICATION_DISPENSED") == "MEDICATION_DISPENSE"
    assert internal_kind("MEDICATION_DISPENSED") in VISIBLE_SUMMARY_KINDS


def test_unknown_code_system_is_retained_but_marked_unsupported() -> None:
    assert mapping_status("UNKNOWN-HOSPITAL-CATALOG") == "UNSUPPORTED_MAPPING"


def test_dispute_requires_reason_and_consistent_overall_result() -> None:
    evidence_id = uuid4()
    with pytest.raises(ValidationError):
        ItemResponseRequest(evidence_id=evidence_id, response="DISPUTED")
    disputed = ItemResponseRequest(
        evidence_id=evidence_id, response="DISPUTED", reason="OTHER"
    )
    confirmed = ItemResponseRequest(evidence_id=uuid4(), response="CONFIRMED")
    PatientResponseRequest(
        overall_response="PARTIALLY_DISPUTED", items=[disputed, confirmed]
    )
    with pytest.raises(ValidationError):
        PatientResponseRequest(overall_response="PARTIALLY_DISPUTED", items=[disputed])
    with pytest.raises(ValidationError):
        PatientResponseRequest(overall_response="DISPUTED", items=[disputed, confirmed])
