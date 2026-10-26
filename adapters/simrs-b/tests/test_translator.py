import pytest

from simrs_b_adapter.translator import translate


def test_local_medication_maps_to_canonical_catalog() -> None:
    result = translate(
        {
            "jenis": "OBAT",
            "kode": "OB-PCT500",
            "urutan": 3,
            "id_rekam": "RX-1",
            "jumlah": 10,
        }
    )
    assert result["event_type"] == "MEDICATION_DISPENSED"
    assert result["content"]["code_system"] == "JJKN-MED-V1"
    assert result["content"]["code"] == "MED-PARACETAMOL-500"


def test_unknown_local_code_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        translate({"jenis": "OBAT", "kode": "UNKNOWN", "urutan": 1, "id_rekam": "RX-2"})
