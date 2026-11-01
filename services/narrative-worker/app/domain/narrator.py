"""Deterministic, factual narrative with a certainty-language and hallucination guard."""

import hashlib
import json
import re
from typing import Any

from app.domain.seed_catalog import SEEDED_CODE_CATALOG

BANNED = (
    "terbukti fraud",
    "pasti fraud",
    "definitively fraudulent",
    "guilty of fraud",
    "confirmed fraud",
    "penipuan terbukti",
    "klaim ditolak otomatis",
)
PII_KEYS = {
    "participant_number",
    "patient_name",
    "display_name",
    "name",
    "nik",
    "participant_number_ciphertext",
    "display_name_ciphertext",
    "note_ciphertext",
}
RULE_ID_PATTERN = re.compile(r"\bR\d{3}(?:_[A-Z0-9_]+)?\b")
INTERNAL_ITEM_REF_PATTERN = re.compile(
    r"\b(?:ITEM[-_]\d+|DX[-_]PRIMARY|DX[-_]SECONDARY|DX[-_]\d+|PROC[-_]\d+|MED[-_]\d+)\b",
    re.IGNORECASE,
)
MAX_SECTION_ITEMS = 20
MAX_ITEM_CHARS = 600

# Status tokens and rule identifiers must never reach a reviewer-facing narrative.
RAW_CODE_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b|\bR\d{3}\b")
SESUAI_PREFIX = "YANG SESUAI: "
TIDAK_SESUAI_PREFIX = "YANG TIDAK SESUAI: "

ITEM_TYPE_LABELS = {
    "PROCEDURE": "Tindakan",
    "DIAGNOSIS": "Diagnosis",
    "MEDICATION": "Obat",
    "MEDICATION_DISPENSE": "Obat",
}

CANONICAL_NAMES = {
    "JJKN-DIAG-V1:DIAG-H10-9": "Konjungtivitis",
    "JJKN-DIAG-V1:DIAG-J06-9": "ISPA akut",
    "JJKN-PROC-V1:PROC-CONSULT-GP": "Konsultasi dokter umum",
    "JJKN-PROC-V1:PROC-EXAM-EYE": "Pemeriksaan mata",
    "JJKN-PROC-V1:PROC-SLIT-LAMP": "Biomikroskopi slit lamp",
    "JJKN-PROC-V1:PROC-ECG": "Elektrokardiografi",
    "JJKN-PROC-V1:PROC-CBC": "Darah lengkap",
    "JJKN-MED-V1:MED-PARACETAMOL-500": "Paracetamol 500 mg",
    "JJKN-MED-V1:MED-AMOXICILLIN-500": "Amoxicillin 500 mg",
    "JJKN-MED-V1:MED-LEVOFLOXACIN-ED": "Levofloxacin tetes mata 5 mL",
}

REF_FALLBACK_LABELS = {
    "DX-PRIMARY": "Diagnosis utama pada klaim",
    "DX-SECONDARY": "Diagnosis sekunder pada klaim",
    "PROC-1": "Tindakan pada klaim",
    "PROC-2": "Tindakan tambahan pada klaim",
    "MED-1": "Obat pada klaim",
}

MATCH_RESULT_LABELS = {
    "MISSING": "tidak ada di catatan faskes",
    "PATIENT_DISPUTED": "disanggah pasien",
    "QUANTITY_MISMATCH": "jumlah yang diklaim berbeda dengan yang diserahkan",
    "PRESCRIBED_ONLY": "hanya tercatat diresepkan, belum ada catatan penyerahan",
    "UNSUPPORTED_MAPPING": "kode klaim belum dapat dipetakan ke katalog",
}

FINDING_LABELS = {
    "NO_ENCOUNTER": "kunjungan yang cocok tidak ditemukan",
    "WEAK_IDENTITY": "identitas pasien belum cukup kuat",
    "MISSING_OR_PRESCRIBED_ONLY": "layanan tidak ada di catatan faskes",
    "QUANTITY_MISMATCH": "jumlah yang diklaim berbeda dengan catatan faskes",
    "PATIENT_DISPUTED": "layanan disanggah pasien",
    "TIME_INCONSISTENCY": "waktu layanan di luar rentang klaim",
    "ENCOUNTER_REUSED": "kunjungan juga dipakai klaim lain",
    "EVIDENCE_REUSED": "catatan layanan juga dipakai klaim lain",
    "CLAIM_REVERIFIED": "klaim ini pernah diperiksa sebelumnya",
    "STALE_OR_LATE_EVIDENCE": "data kunjungan berubah setelah pemeriksaan",
    "DOCUMENT_CROSS_PATIENT": "dokumen yang sama muncul pada pasien lain",
    "CHECKOUT_EXCEPTION": "kehadiran pasien belum terverifikasi dengan QR",
    "PATIENT_NO_RESPONSE": "pasien belum memberi tanggapan",
    "UNSUPPORTED_MAPPING": "kode klaim belum dapat dipetakan ke katalog",
}


def compute_digest(package: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(package, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _lookup_code_name(code_system: str, code: str) -> str | None:
    key = f"{code_system}:{code}"
    return (
        CANONICAL_NAMES.get(key)
        or SEEDED_CODE_CATALOG.get(key)
        or SEEDED_CODE_CATALOG.get(code)
    )


def _quantity_text(item: dict[str, Any]) -> str:
    qty = item.get("quantity") or item.get("claimed_quantity")
    unit = str(item.get("unit") or "").strip()
    if not qty or not unit or unit in {"1", "unit"}:
        return ""
    return f" sejumlah {float(qty):g} {unit}"


def _describe_item_subject(item: dict[str, Any]) -> str:
    """Name a claim item from metadata or the seeded catalogs, never by its code."""
    ref = str(item.get("claim_item_ref") or item.get("item_ref") or "").upper()
    item_type = str(item.get("item_type") or "").upper()
    if not item_type:
        prefix = {"DX": "DIAGNOSIS", "PROC": "PROCEDURE", "MED": "MEDICATION"}
        item_type = next((v for k, v in prefix.items() if ref.startswith(k)), "")
    label = ITEM_TYPE_LABELS.get(item_type, "Layanan")

    name = next(
        (
            str(item[key]).strip()
            for key in ("display", "item_name", "description", "name")
            if isinstance(item.get(key), str)
            and item[key].strip()
            and not INTERNAL_ITEM_REF_PATTERN.fullmatch(item[key].strip())
        ),
        None,
    ) or _lookup_code_name(
        str(item.get("code_system") or "").strip(),
        str(item.get("code") or "").strip(),
    )
    if name:
        return f"{label} {name}{_quantity_text(item)}"
    return REF_FALLBACK_LABELS.get(ref, f"{label} pada klaim")


def _build_item_ref_map(package: dict[str, Any]) -> dict[str, str]:
    ref_map: dict[str, str] = dict(REF_FALLBACK_LABELS)
    for item in package.get("items", []):
        ref = str(item.get("claim_item_ref") or item.get("item_ref") or "").strip()
        if ref:
            ref_map[ref] = _describe_item_subject(item)
    return ref_map


def _replace_internal_item_refs(text: str, ref_map: dict[str, str]) -> str:
    out = text
    for ref, subject in sorted(ref_map.items(), key=lambda kv: -len(kv[0])):
        if ref:
            out = re.sub(rf"\b{re.escape(ref)}\b", subject, out, flags=re.IGNORECASE)
    out = INTERNAL_ITEM_REF_PATTERN.sub("layanan klaim terkait", out)
    return out


def _classify_sesuai_dan_tidak_sesuai(
    package: dict[str, Any],
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Return plain-language (sesuai, tidak_sesuai, detailed_items) without any code."""
    assessment = package.get("assessment", {})
    yang_sesuai: list[str] = []
    yang_tidak_sesuai: list[str] = []
    detailed_items: list[dict[str, Any]] = []

    enc_status = assessment.get("encounter_match_status")
    if enc_status == "UNIQUE_MATCH":
        yang_sesuai.append("Kunjungan pasien cocok dengan catatan kehadiran di faskes.")
    elif enc_status == "NO_ENCOUNTER_FOUND":
        yang_tidak_sesuai.append(
            "Tidak ada catatan kunjungan pasien di faskes dan tanggal yang diklaim."
        )
    elif enc_status == "AMBIGUOUS_MATCH":
        yang_tidak_sesuai.append(
            "Ada lebih dari satu kunjungan yang sama-sama cocok dengan klaim."
        )
    elif enc_status == "IDENTITY_INSUFFICIENT":
        yang_tidak_sesuai.append(
            "Identitas pasien belum pasti, jadi kunjungan belum dapat dikaitkan."
        )
    elif enc_status:
        yang_tidak_sesuai.append("Kunjungan pasien belum dapat dipastikan.")

    if assessment.get("identity_assurance") in {"STRONG", "VERIFIED_PARTICIPANT_ID"}:
        yang_sesuai.append("Identitas peserta terverifikasi.")

    if assessment.get("duplicate_assessment_status") in {
        "POTENTIAL_ENCOUNTER_REUSE",
        "POTENTIAL_EVIDENCE_REUSE",
    }:
        yang_tidak_sesuai.append(
            "Kunjungan atau catatan layanan yang sama juga dipakai klaim lain."
        )

    for item in package.get("items", []):
        subject = _describe_item_subject(item)
        match_result = str(item.get("match_result") or "UNKNOWN").upper()
        if match_result == "MATCHED":
            desc = f"{subject} sesuai catatan faskes."
            yang_sesuai.append(desc)
            status = "SESUAI"
        else:
            label = MATCH_RESULT_LABELS.get(match_result, "belum dapat dipastikan")
            desc = f"{subject}: {label}."
            yang_tidak_sesuai.append(desc)
            status = "TIDAK_SESUAI"
        detailed_items.append(
            {"status_kecocokan": status, "layanan_atau_item": subject, "penjelasan": desc}
        )

    return yang_sesuai, yang_tidak_sesuai, detailed_items


def minimize_package(package: dict[str, Any]) -> dict[str, Any]:
    """Strip any potential PII and retain only de-identified explicit facts for LLM input."""
    ref_map = _build_item_ref_map(package)
    yang_sesuai, yang_tidak_sesuai, detailed_items = _classify_sesuai_dan_tidak_sesuai(
        package
    )

    def _scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: _scrub(v)
                for k, v in value.items()
                if k.lower() not in PII_KEYS
                and k not in {"claim_item_ref", "item_ref"}
            }
        if isinstance(value, list):
            return [_scrub(item) for item in value]
        if isinstance(value, str):
            return _replace_internal_item_refs(value, ref_map)
        return value

    assessment = package.get("assessment", {})
    minimized = {
        "data_freshness": package.get("data_freshness", "CURRENT"),
        "assessment": {
            "encounter_match_status": assessment.get("encounter_match_status"),
            "identity_assurance": assessment.get("identity_assurance"),
            "evidence_reconciliation_status": assessment.get(
                "evidence_reconciliation_status"
            ),
            "duplicate_assessment_status": assessment.get(
                "duplicate_assessment_status"
            ),
            "patient_confirmation_status": assessment.get(
                "patient_confirmation_status"
            ),
            "review_required": assessment.get("review_required", True),
            "final_fraud_decision": None,
        },
        "hal_yang_sesuai": yang_sesuai,
        "hal_yang_tidak_sesuai": yang_tidak_sesuai,
        "candidates": [
            {
                "candidate_index": idx + 1,
                "match_state": row.get("match_state"),
                "reasons": row.get("reasons", []),
            }
            for idx, row in enumerate(package.get("candidates", []))
        ],
        "items": detailed_items,
        "findings": [
            {
                "rule_id": row.get("rule_id"),
                "severity": row.get("severity"),
                "finding_code": row.get("finding_code"),
                "layanan_terkait": ref_map.get(
                    str(row.get("claim_item_ref") or "").strip(),
                    "Kunjungan/klaim secara umum",
                ),
                "explanation_facts": row.get("explanation_facts"),
                "limitations": row.get("limitations"),
            }
            for row in package.get("findings", [])
        ],
    }
    return _scrub(minimized)


def fallback_narrative() -> dict[str, list[str]]:
    return {
        "summary": ["Ringkasan otomatis tidak dapat ditampilkan."],
        "findings": [],
        "questions": ["Silakan telaah paket bukti."],
        "limitations": ["Keputusan harus dibuat oleh reviewer manusia."],
    }


def validate_narrative(
    candidate: Any, package: dict[str, Any]
) -> tuple[dict[str, list[str]], bool]:
    """Validate structure, length bounds, rule references, and certainty-language guard."""
    if not isinstance(candidate, dict):
        return fallback_narrative(), False

    ref_map = _build_item_ref_map(package)
    required_keys = ("summary", "findings", "questions", "limitations")
    cleaned: dict[str, list[str]] = {}
    for key in required_keys:
        val = candidate.get(key)
        if not isinstance(val, list) or len(val) > MAX_SECTION_ITEMS:
            return fallback_narrative(), False
        lines: list[str] = []
        for entry in val:
            if not isinstance(entry, str):
                return fallback_narrative(), False
            text = _replace_internal_item_refs(entry.strip(), ref_map)
            if (
                not text
                or len(text) > MAX_ITEM_CHARS
                or (key != "findings" and RAW_CODE_PATTERN.search(text))
            ):
                return fallback_narrative(), False
            lines.append(text)
        cleaned[key] = lines

    if not cleaned["summary"] or not cleaned["questions"] or not cleaned["limitations"]:
        return fallback_narrative(), False

    serialized = json.dumps(cleaned, ensure_ascii=False)
    lowered = serialized.lower()
    if any(term in lowered for term in BANNED):
        return fallback_narrative(), False

    for pii_key in PII_KEYS:
        if (
            pii_key in package
            and isinstance(package[pii_key], str)
            and package[pii_key]
        ):
            if package[pii_key].lower() in lowered:
                return fallback_narrative(), False

    allowed_rules: set[str] = set()
    for row in package.get("findings", []):
        rule_id = row.get("rule_id")
        if rule_id:
            rule_str = str(rule_id)
            allowed_rules.add(rule_str)
            allowed_rules.add(rule_str.split("_", 1)[0])
    mentioned_rules = set(RULE_ID_PATTERN.findall(serialized))
    if not mentioned_rules.issubset(allowed_rules):
        return fallback_narrative(), False

    return cleaned, True


def narrate(package: dict[str, Any]) -> tuple[dict[str, list[str]], str, str]:
    ref_map = _build_item_ref_map(package)
    yang_sesuai, yang_tidak_sesuai, _ = _classify_sesuai_dan_tidak_sesuai(package)

    findings_lines: list[str] = []
    for row in package.get("findings", []):
        subject = ref_map.get(str(row.get("claim_item_ref") or "").strip())
        label = FINDING_LABELS.get(
            str(row.get("finding_code")), "perlu ditinjau verifikator"
        )
        findings_lines.append(f"{subject}: {label}." if subject else f"{label.capitalize()}.")

    result = {
        # One entry per fact: a single joined sentence overflows MAX_ITEM_CHARS on large claims.
        "summary": [SESUAI_PREFIX + line for line in yang_sesuai]
        + [TIDAK_SESUAI_PREFIX + line for line in yang_tidak_sesuai],
        "findings": findings_lines,
        "questions": ["Apakah bukti klinis tambahan tersedia?"],
        "limitations": [
            "Ringkasan ini membantu telaah manusia dan bukan keputusan fraud atau pembayaran."
        ],
    }
    if not result["summary"]:
        result["summary"] = ["YANG SESUAI: Belum ada data untuk diringkas."]
    validated, is_valid = validate_narrative(result, package)
    status = "VALID" if is_valid else "FALLBACK"
    digest = compute_digest(package)
    return validated, status, digest
