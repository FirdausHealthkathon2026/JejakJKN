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

ITEM_TYPE_LABELS = {
    "PROCEDURE": "Tindakan/prosedur medis",
    "DIAGNOSIS": "Diagnosis klinis",
    "MEDICATION": "Pemberian obat",
    "MEDICATION_DISPENSE": "Penyerahan obat farmasi",
}

REF_FALLBACK_LABELS = {
    "DX-PRIMARY": "Diagnosis utama pada klaim",
    "DX-SECONDARY": "Diagnosis sekunder pada klaim",
    "PROC-1": "Tindakan/prosedur medis pada klaim",
    "PROC-2": "Tindakan/prosedur medis tambahan pada klaim",
    "MED-1": "Pemberian obat pada klaim",
}

MATCH_RESULT_LABELS = {
    "MATCHED": "Sesuai dengan bukti rekam medis",
    "MISSING": "Tidak ditemukan bukti di rekam medis SIMRS",
    "MISSING_IN_EVIDENCE": "Tidak ditemukan bukti pendukung di rekam medis",
    "PATIENT_DISPUTED": "Disanggah oleh pasien (pasien menyatakan tidak menerima layanan/obat)",
    "QUANTITY_MISMATCH": "Jumlah yang ditagihkan tidak sesuai dengan bukti penyerahan",
    "PRESCRIBED_ONLY": "Hanya tercatat diresepkan tetapi tidak ada bukti penyerahan farmasi",
    "UNSUPPORTED_MAPPING": "Kode klaim belum terpetakan pada katalog bukti klinis",
}


def compute_digest(package: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(package, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _lookup_seeded_code_display(code_system: str, code: str) -> str | None:
    if code_system and code:
        hit = SEEDED_CODE_CATALOG.get(f"{code_system}:{code}")
        if hit:
            return hit
    if code:
        hit = SEEDED_CODE_CATALOG.get(code)
        if hit:
            return hit
    return None


def _describe_item_subject(item: dict[str, Any]) -> str:
    """Build an explicit human-readable subject for a claim item using seeded catalogs and item metadata."""
    for key in ("display", "item_name", "description", "name"):
        val = item.get(key)
        if (
            isinstance(val, str)
            and val.strip()
            and not INTERNAL_ITEM_REF_PATTERN.fullmatch(val.strip())
        ):
            return val.strip()

    item_type = str(item.get("item_type") or "").upper()
    code_system = str(item.get("code_system") or "").strip()
    code = str(item.get("code") or "").strip()
    qty = item.get("quantity") or item.get("claimed_quantity")
    unit = str(item.get("unit") or "").strip()
    ref = str(item.get("claim_item_ref") or item.get("item_ref") or "").upper()

    if not item_type:
        if ref.startswith("DX"):
            item_type = "DIAGNOSIS"
        elif ref.startswith("PROC"):
            item_type = "PROCEDURE"
        elif ref.startswith("MED"):
            item_type = "MEDICATION"

    if item_type or code:
        type_label = ITEM_TYPE_LABELS.get(
            item_type, item_type.title() or "Layanan medis"
        )
        seeded_display = _lookup_seeded_code_display(code_system, code)
        parts = [type_label]
        if seeded_display:
            if code and code not in seeded_display:
                cs_prefix = f"{code_system} " if code_system else ""
                parts.append(f"{seeded_display} ({cs_prefix}{code})")
            else:
                parts.append(f"{seeded_display}")
        elif code and not INTERNAL_ITEM_REF_PATTERN.fullmatch(code):
            cs_prefix = f"{code_system} " if code_system else ""
            parts.append(f"({cs_prefix}{code})")
        if qty and unit and unit not in {"1", "unit"}:
            parts.append(f"sejumlah {qty} {unit}")
        return " ".join(parts)

    reason = str(item.get("reason") or "").strip()
    cleaned_reason = INTERNAL_ITEM_REF_PATTERN.sub("", reason).strip(" :,-")
    if cleaned_reason:
        lower = cleaned_reason.lower()
        if lower in {"exact canonical match", "missing"}:
            return REF_FALLBACK_LABELS.get(ref, "Layanan/tindakan medis pada klaim")
        if lower.startswith("matched procedure "):
            proc = cleaned_reason[len("matched procedure ") :].strip()
            if proc.lower() == "evidence":
                return "Tindakan/prosedur medis yang ditagihkan"
            seeded_display = _lookup_seeded_code_display("", proc)
            if seeded_display:
                return f"Tindakan/prosedur {seeded_display}"
            return f"Tindakan/prosedur {proc}"
        if lower.startswith("patient disputed receiving "):
            med = cleaned_reason[len("patient disputed receiving ") :].strip()
            return f"Pemberian obat/layanan {med}"
        if "procedure" in lower:
            return f"Tindakan/prosedur medis ({cleaned_reason})"
        if (
            "medication" in lower
            or "dispensed" in lower
            or "tablet" in lower
            or "mg" in lower
        ):
            return f"Pemberian obat ({cleaned_reason})"
        return cleaned_reason

    return REF_FALLBACK_LABELS.get(ref, "Layanan/tindakan medis pada klaim")


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
    """Return explicit (hal_yang_sesuai, hal_yang_tidak_sesuai, detailed_items) without internal ref tokens."""
    ref_map = _build_item_ref_map(package)
    assessment = package.get("assessment", {})
    yang_sesuai: list[str] = []
    yang_tidak_sesuai: list[str] = []
    detailed_items: list[dict[str, Any]] = []

    enc_status = assessment.get("encounter_match_status")
    if enc_status == "UNIQUE_MATCH":
        yang_sesuai.append(
            "Kunjungan pasien cocok secara unik (UNIQUE_MATCH) dengan catatan kehadiran di rumah sakit."
        )
    elif enc_status == "NO_ENCOUNTER_FOUND":
        yang_tidak_sesuai.append(
            "Kunjungan pasien tidak ditemukan sama sekali pada database rumah sakit/SIMRS (NO_ENCOUNTER_FOUND / indikasi klaim tanpa kunjungan)."
        )
    elif enc_status:
        yang_tidak_sesuai.append(
            f"Pencocokan kunjungan pasien tidak cocok unik ({enc_status})."
        )

    id_status = assessment.get("identity_assurance")
    if id_status == "VERIFIED_PARTICIPANT_ID":
        yang_sesuai.append(
            "Identitas kepesertaan pasien telah terverifikasi valid (VERIFIED_PARTICIPANT_ID)."
        )
    elif id_status:
        yang_tidak_sesuai.append(
            f"Verifikasi identitas kepesertaan belum memadai ({id_status})."
        )

    dup_status = assessment.get("duplicate_assessment_status")
    if dup_status in {"POTENTIAL_ENCOUNTER_REUSE", "POTENTIAL_EVIDENCE_REUSE"}:
        yang_tidak_sesuai.append(
            f"Terdeteksi potensi penggunaan ulang kunjungan/bukti klinis pada klaim berbeda ({dup_status})."
        )

    for item in package.get("items", []):
        subject = _describe_item_subject(item)
        match_result = str(item.get("match_result") or "UNKNOWN").upper()
        raw_reason = str(item.get("reason") or "").strip()
        clean_reason = _replace_internal_item_refs(raw_reason, ref_map)
        result_label = MATCH_RESULT_LABELS.get(match_result, match_result)

        if match_result == "MATCHED":
            detail = (
                result_label
                if clean_reason.lower() in {"", "exact canonical match"}
                else clean_reason
            )
            desc = f"{subject} sesuai dengan bukti rekam medis ({detail})."
            yang_sesuai.append(desc)
            detailed_items.append(
                {
                    "status_kecocokan": "SESUAI",
                    "layanan_atau_item": subject,
                    "match_result": match_result,
                    "penjelasan": desc,
                }
            )
        else:
            detail = (
                result_label
                if clean_reason.lower() in {"", "missing", match_result.lower()}
                else f"{result_label}; detail: {clean_reason}"
            )
            desc = f"{subject} tidak sesuai bukti ({detail})."
            yang_tidak_sesuai.append(desc)
            detailed_items.append(
                {
                    "status_kecocokan": "TIDAK_SESUAI",
                    "layanan_atau_item": subject,
                    "match_result": match_result,
                    "penjelasan": desc,
                }
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
            if not text or len(text) > MAX_ITEM_CHARS:
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

    facts: list[str] = []
    if yang_sesuai:
        facts.append("YANG SESUAI: " + " | ".join(yang_sesuai))
    else:
        facts.append(
            "YANG SESUAI: Belum ada butir klaim atau kunjungan yang terverifikasi cocok penuh."
        )

    if yang_tidak_sesuai:
        facts.append(
            "YANG TIDAK SESUAI: " + " | ".join(yang_tidak_sesuai)
        )
    else:
        facts.append(
            "YANG TIDAK SESUAI: Tidak ditemukan ketidaksesuaian pada rincian item klaim."
        )

    findings_lines: list[str] = []
    for row in package.get("findings", []):
        ref = str(row.get("claim_item_ref") or "").strip()
        subject = ref_map.get(ref, "")
        target_info = f" pada {subject}" if subject else ""
        findings_lines.append(
            f"{row['rule_id']} [{row['severity']}]{target_info}: {row['finding_code']}."
        )

    result = {
        "summary": facts,
        "findings": findings_lines,
        "questions": ["Apakah bukti klinis tambahan tersedia?"],
        "limitations": [
            "Ringkasan ini membantu telaah manusia dan bukan keputusan fraud atau pembayaran."
        ],
    }
    validated, is_valid = validate_narrative(result, package)
    status = "VALID" if is_valid else "FALLBACK"
    digest = compute_digest(package)
    return validated, status, digest
