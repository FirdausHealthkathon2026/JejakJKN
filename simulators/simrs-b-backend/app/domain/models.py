"""SIMRS-B local request model."""

from typing import Any

from pydantic import BaseModel, Field


class LocalClinicalInput(BaseModel):
    jenis: str
    kode: str
    urutan: int = Field(ge=1)
    id_rekam: str = Field(min_length=1, max_length=128)
    id_peristiwa: str | None = None
    waktu: str | None = None
    petugas: str = "PETUGAS-B-01"
    peran: str = "CLINICIAN"
    jumlah: Any = None
    satuan: str | None = None


class LocalScanInput(BaseModel):
    token_qr: str = Field(min_length=32)
    id_pemindai: str = "PEMINDAI-B-01"
    referensi_kunjungan: str | None = None
