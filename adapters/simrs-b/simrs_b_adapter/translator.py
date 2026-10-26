"""Translate SIMRS-B's local Indonesian fields into canonical evidence."""

from datetime import UTC, datetime
from uuid import uuid4

CATALOG = {
    ("TINDAKAN", "RJ-DOK-001"): (
        "PROCEDURE",
        "JJKN-PROC-V1",
        "PROC-CONSULT-GP",
        "Konsultasi dokter umum",
        "service",
        1,
    ),
    ("TINDAKAN", "MATA-01"): (
        "PROCEDURE",
        "JJKN-PROC-V1",
        "PROC-EXAM-EYE",
        "Pemeriksaan mata",
        "service",
        1,
    ),
    ("TINDAKAN", "MATA-SLIT"): (
        "PROCEDURE",
        "JJKN-PROC-V1",
        "PROC-SLIT-LAMP",
        "Biomikroskopi slit lamp",
        "service",
        1,
    ),
    ("TINDAKAN", "JANTUNG-EKG"): (
        "PROCEDURE",
        "JJKN-PROC-V1",
        "PROC-ECG",
        "Elektrokardiografi",
        "service",
        1,
    ),
    ("LAB", "DL-001"): (
        "PROCEDURE",
        "JJKN-PROC-V1",
        "PROC-CBC",
        "Darah lengkap",
        "service",
        1,
    ),
    ("OBAT", "OB-PCT500"): (
        "MEDICATION_DISPENSED",
        "JJKN-MED-V1",
        "MED-PARACETAMOL-500",
        "Paracetamol 500 mg",
        "tablet",
        1,
    ),
    ("OBAT", "OB-PCT500-STR"): (
        "MEDICATION_DISPENSED",
        "JJKN-MED-V1",
        "MED-PARACETAMOL-500",
        "Paracetamol 500 mg",
        "tablet",
        10,
    ),
    ("OBAT", "OB-AMX500"): (
        "MEDICATION_DISPENSED",
        "JJKN-MED-V1",
        "MED-AMOXICILLIN-500",
        "Amoxicillin 500 mg",
        "tablet",
        1,
    ),
    ("OBAT", "OB-LFX-ED"): (
        "MEDICATION_DISPENSED",
        "JJKN-MED-V1",
        "MED-LEVOFLOXACIN-ED",
        "Levofloxacin eye drops 5 mL",
        "bottle",
        1,
    ),
    ("DIAGNOSIS", "H10.9"): (
        "DIAGNOSIS",
        "JJKN-DIAG-V1",
        "DIAG-H10-9",
        "Konjungtivitis",
        "code",
        1,
    ),
    ("DIAGNOSIS", "J06.9"): (
        "DIAGNOSIS",
        "JJKN-DIAG-V1",
        "DIAG-J06-9",
        "ISPA akut",
        "code",
        1,
    ),
}


def translate(local: dict) -> dict:
    category, code = str(local["jenis"]).upper(), str(local["kode"])
    try:
        event_type, code_system, canonical_code, display, default_unit, multiplier = (
            CATALOG[(category, code)]
        )
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
            "quantity": float(local["jumlah"]) * multiplier
            if local.get("jumlah") is not None
            else None,
            "unit": default_unit,
        },
        "stage_completion": None,
    }
