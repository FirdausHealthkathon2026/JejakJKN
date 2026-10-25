"""Evidence mapping and summary visibility rules."""

VISIBLE_SUMMARY_KINDS = {"DIAGNOSIS", "PROCEDURE", "MEDICATION_DISPENSE"}
MAPPED_CODE_SYSTEMS = {"DEMO-DIAGNOSIS-CATALOG", "DEMO-PROCEDURE-CATALOG", "DEMO-MEDICATION-CATALOG", "DEMO-STAGE-CATALOG"}


def internal_kind(event_type: str) -> str:
    return "MEDICATION_DISPENSE" if event_type == "MEDICATION_DISPENSED" else event_type


def mapping_status(code_system: str) -> str:
    return "MAPPED" if code_system in MAPPED_CODE_SYSTEMS else "UNSUPPORTED_MAPPING"
