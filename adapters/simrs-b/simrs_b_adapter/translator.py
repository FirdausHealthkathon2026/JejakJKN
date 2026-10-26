"""Translate SIMRS-B's local Indonesian fields into canonical evidence."""

from datetime import UTC, datetime
from uuid import uuid4

CATALOG = {
    ("TINDAKAN", "MATA-01"): (
        "PROCEDURE",
        "JJKN-PROC-V1",
        "PROC-EXAM-EYE",
        "Pemeriksaan mata",
        "service",
    ),
    ("OBAT", "OB-PCT500"): (
        "MEDICATION_DISPENSED",
        "JJKN-MED-V1",
        "MED-PARACETAMOL-500",
        "Paracetamol 500 mg",
        "tablet",
    ),
    ("DIAGNOSIS", "H10.9"): (
        "DIAGNOSIS",
        "JJKN-DIAG-V1",
        "DIAG-H10-9",
        "Konjungtivitis",
        None,
    ),
}


def translate(local: dict) -> dict:
    category, code = str(local["jenis"]).upper(), str(local["kode"])
    try:
        event_type, code_system, canonical_code, display, default_unit = CATALOG[
            (category, code)
        ]
    except KeyError as exc:
        raise ValueError(f"unsupported SIMRS-B code: {category}/{code}") from exc
    sequence = int(local["urutan"])
    if sequence < 1:
        raise ValueError("urutan must be positive")
    return {
        "source_event_id": str(local.get("id_peristiwa") or f"SIMRS-B-EVT-{uuid4()}"),
        "source_system": "SIMRS-B",
        "source_sequence": sequence,
        "external_record_id": str(local["id_rekam"]),
        "event_type": event_type,
        "record_version": 1,
        "occurred_at": str(local.get("waktu") or datetime.now(UTC).isoformat()),
        "actor": {
            "external_id": str(local.get("petugas", "PETUGAS-B-01")),
            "role": str(local.get("peran", "CLINICIAN")),
        },
        "content": {
            "code_system": code_system,
            "code": canonical_code,
            "display": display,
            "quantity": local.get("jumlah"),
            "unit": local.get("satuan", default_unit),
        },
        "stage_completion": None,
    }
