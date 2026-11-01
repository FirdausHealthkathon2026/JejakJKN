"""Extract 1,000 random samples from data_klaim_asli.parquet,
generate 1,000 synthetic encounters and evidence in JejakJKN database with ~10% anomalies,
and save the claims fixture for benchmark testing.
"""

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
import pandas as pd
import pyarrow.parquet as pq
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HMAC_KEY = "0d70fe6c79ac335cbf6894b35f18c20a470000094d55f8a85ee7b937359baa8c"
ENC_KEY = "76e615c41c9303747950656b727151dc65aced28b91aa891429beca78a695b7c"

FACILITY_MAP = {
    "0": {"code": "HOSP-DEMO-001", "org_id": "00000000-0000-4000-8000-000000000001", "source_id": "20000000-0000-4000-8000-000000000001", "adapter": "simrs-a-adapter"},
    "1": {"code": "HOSP-DEMO-002", "org_id": "00000000-0000-4000-8000-000000000002", "source_id": "20000000-0000-4000-8000-000000000002", "adapter": "simrs-b-adapter"},
}


def blind_index(value: str, key_hex: str) -> str:
    normalized = value.strip().upper()
    return hmac.new(bytes.fromhex(key_hex), normalized.encode(), hashlib.sha256).hexdigest()


def encrypt_field(value: str, key_hex: str, aad: str) -> bytes:
    nonce = os.urandom(12)
    ciphertext = AESGCM(bytes.fromhex(key_hex)).encrypt(nonce, value.encode(), aad.encode())
    return nonce + ciphertext


def escape_sql(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, bytes):
        return f"'\\x{val.hex()}'"
    s = str(val).replace("'", "''")
    return f"'{s}'"


def parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)


def clean_procedure(proc_str) -> tuple[str, str] | None:
    if pd.isna(proc_str) or not proc_str or str(proc_str).strip().upper() in {"NONE", "NAN", ""}:
        return None
    s = str(proc_str).strip()
    if " - " in s:
        code, display = s.split(" - ", 1)
        return code.strip(), display.strip()
    match = re.match(r"^(\d+)\s*(.*)$", s)
    if match:
        return match.group(1).strip(), match.group(2).strip() or "Prosedur Medis"
    return s[:10].strip(), s


def main():
    print("Reading data_klaim_asli.parquet...")
    table = pq.read_table("data_klaim_asli.parquet")
    df = table.to_pandas()
    print(f"Total rows in parquet: {len(df):,}")

    # Deterministic sample of 1000 rows
    sample_df = df.sample(n=1000, random_state=42).reset_index(drop=True)

    # Assign fraud scenarios:
    # 0..899 (900): VALID
    # 900..934 (35): PHANTOM_BILLING (no encounter in DB)
    # 935..959 (25): DOUBLE_BILLING (conflicting claim)
    # 960..979 (20): GHOST_PROCEDURE (procedure on claim, but missing in SIMRS evidence)
    # 980..989 (10): ABSENT_PATIENT (patient unverified / absent)
    # 990..999 (10): TIMING_MISMATCH (encounter date far outside claim window)

    scenarios = []
    for idx in range(1000):
        if idx < 900:
            scenarios.append("VALID")
        elif idx < 935:
            scenarios.append("PHANTOM_BILLING")
        elif idx < 960:
            scenarios.append("DOUBLE_BILLING")
        elif idx < 980:
            scenarios.append("GHOST_PROCEDURE")
        elif idx < 990:
            scenarios.append("ABSENT_PATIENT")
        else:
            scenarios.append("TIMING_MISMATCH")

    sample_df["scenario"] = scenarios

    patients_to_insert = {}
    encounters_sql = []
    care_episodes_sql = []
    evidence_records_sql = []
    evidence_versions_sql = []
    summary_snapshots_sql = []
    verif_snapshots_sql = []
    claims_fixtures = []

    # List for double billing targets
    valid_targets = []

    print("Generating synthetic data for 1,000 claims...")

    for idx, row in sample_df.iterrows():
        scenario = row["scenario"]
        p_num = str(int(row["PSTV01"]))
        claim_id = str(row["FKL02"])
        tgl_masuk = parse_date(str(row["FKL03"]))
        tgl_pulang = parse_date(str(row["FKL04"]))
        if tgl_pulang < tgl_masuk:
            tgl_pulang = tgl_masuk

        biaya_klaim = float(row["FKL48"]) if pd.notna(row["FKL48"]) else 207900.0
        service_type = "OUTPATIENT" if str(row["FKL10"]).strip() == "RJTL" else "INPATIENT"

        # Alternate facility
        faskes = FACILITY_MAP[str(idx % 2)]
        facility_code = faskes["code"]
        org_id = faskes["org_id"]
        source_id = faskes["source_id"]
        adapter_name = faskes["adapter"]

        # Parse Diagnosis Utama
        diag_code = str(row["FKL15A"]).strip()[:60] if pd.notna(row["FKL15A"]) else "Z09"
        diag_display = str(row["FKL16A"]).strip()[:240] if pd.notna(row["FKL16A"]) else "Pemeriksaan Tindak Lanjut"

        # Parse Prosedur (if any)
        proc = clean_procedure(row["FKL30"])
        proc_code = proc[0][:60] if proc else None
        proc_display = proc[1][:240] if proc else None

        # Construct Claim Items
        claim_items = [
            {
                "item_ref": "DX-PRIMARY",
                "item_type": "DIAGNOSIS",
                "code_system": "ICD-10",
                "code": diag_code,
                "display": diag_display,
                "quantity": 1,
                "unit": "1",
            }
        ]

        if proc:
            claim_items.append(
                {
                    "item_ref": "PROC-1",
                    "item_type": "PROCEDURE",
                    "code_system": "ICD-9-CM",
                    "code": proc_code,
                    "display": proc_display,
                    "quantity": 1,
                    "unit": "1",
                }
            )
        elif scenario == "GHOST_PROCEDURE":
            # Add an expensive hemodialysis / surgical procedure to the claim that will NOT be in evidence
            claim_items.append(
                {
                    "item_ref": "PROC-1",
                    "item_type": "PROCEDURE",
                    "code_system": "ICD-9-CM",
                    "code": "3995",
                    "display": "Hemodialysis (Tindakan Fiktif / Upcoding)",
                    "quantity": 1,
                    "unit": "1",
                }
            )

        # Service period in claim
        service_period_start = (tgl_masuk + timedelta(hours=0)).isoformat()
        service_period_end = (tgl_pulang + timedelta(hours=23, minutes=59, seconds=59)).isoformat()

        if scenario == "DOUBLE_BILLING" and valid_targets:
            # Overwrite claim target with a previous valid encounter to create intentional double billing
            target = valid_targets[idx % len(valid_targets)]
            p_num = target["p_num"]
            facility_code = target["facility_code"]
            service_period_start = target["start"]
            service_period_end = target["end"]
            claim_items = target["items"]
            claim_id = f"CLAIM-DUP-{idx}-{claim_id}"

        if scenario == "VALID" and len(valid_targets) < 20:
            valid_targets.append({
                "p_num": p_num,
                "facility_code": facility_code,
                "start": service_period_start,
                "end": service_period_end,
                "items": claim_items,
            })

        # Patient UUID & registration
        p_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bpjs-patient-{p_num}"))
        if p_id not in patients_to_insert:
            lookup_key = blind_index(p_num, HMAC_KEY)
            p_cipher = encrypt_field(p_num, ENC_KEY, f"patients:{p_id}:participant_number_ciphertext:v1")
            name_text = f"Peserta {p_num}"
            name_cipher = encrypt_field(name_text, ENC_KEY, f"patients:{p_id}:display_name_ciphertext:v1")
            name_hmac = hmac.new(bytes.fromhex(HMAC_KEY), name_text.strip().lower().encode(), hashlib.sha256).hexdigest()
            patients_to_insert[p_id] = {
                "id": p_id,
                "lookup_key": lookup_key,
                "p_cipher": p_cipher,
                "name_cipher": name_cipher,
                "name_hmac": name_hmac,
            }

        # Expected rule outcomes
        expected_rules = []
        expected_status = "CLEAR"
        if scenario == "PHANTOM_BILLING":
            expected_rules.append("R001")
            expected_status = "FLAGGED"
        elif scenario == "DOUBLE_BILLING":
            expected_rules.append("R007")
            expected_status = "FLAGGED"
        elif scenario == "GHOST_PROCEDURE":
            expected_rules.append("R003")
            expected_status = "FLAGGED"
        elif scenario == "ABSENT_PATIENT":
            expected_rules.append("R012")
            expected_status = "FLAGGED"
        elif scenario == "TIMING_MISMATCH":
            expected_rules.append("R001")
            expected_status = "FLAGGED"

        # Record in claims fixture
        claim_request = {
            "claim_source": "BPJS_FKRTL_PROD",
            "claim_id": claim_id,
            "claim_revision": "1",
            "patient": {"participant_number": p_num},
            "facility": {"namespace": "DEMO-FASKES", "code": facility_code},
            "service_period": {"start": service_period_start, "end": service_period_end},
            "items": [
                {
                    "item_ref": it["item_ref"],
                    "item_type": it["item_type"],
                    "code_system": it["code_system"],
                    "code": it["code"],
                    "quantity": it["quantity"],
                    "unit": it["unit"],
                }
                for it in claim_items
            ],
        }

        claims_fixtures.append(
            {
                "index": idx + 1,
                "claim_id": claim_id,
                "scenario": scenario,
                "expected_status": expected_status,
                "expected_rules": expected_rules,
                "claim_amount_rp": biaya_klaim,
                "request_payload": claim_request,
            }
        )

        # ----------------------------------------------------
        # DB Encounter & Evidence Synthesis
        # ----------------------------------------------------
        if scenario == "PHANTOM_BILLING":
            # Intentional: NO encounter or evidence in database!
            continue

        enc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bpjs-enc-{claim_id}"))

        # Dates for Encounter in DB
        if scenario == "TIMING_MISMATCH":
            # Encounter happened 60 days before the claimed window
            enc_start = tgl_masuk - timedelta(days=60, hours=9)
            enc_end = tgl_masuk - timedelta(days=60, hours=7)
        else:
            enc_start = tgl_masuk.replace(hour=8, minute=30, second=0)
            enc_end = (tgl_pulang.replace(hour=11, minute=45, second=0) if service_type == "OUTPATIENT" 
                       else tgl_pulang.replace(hour=14, minute=0, second=0))

        # Presence status
        presence = "UNVERIFIED" if scenario == "ABSENT_PATIENT" else "QR_VERIFIED"

        if scenario == "DOUBLE_BILLING":
            # The encounter and evidence already exist in the database from a previous valid encounter!
            continue

        # Items in SIMRS evidence
        evidence_items_for_db = []
        # Diagnosis is always recorded in evidence
        evidence_items_for_db.append(claim_items[0])

        if proc and scenario != "GHOST_PROCEDURE":
            evidence_items_for_db.append(proc_item if (proc_item := next((x for x in claim_items if x["item_type"] == "PROCEDURE"), None)) else None)
        evidence_items_for_db = [x for x in evidence_items_for_db if x]

        # 1. Encounter Table
        enc_sql = (
            f"INSERT INTO encounters (id, patient_id, organization_id, source_system_id, external_visit_reference, "
            f"service_type, status, presence_status, started_at, ended_at, revision, created_by, created_at, updated_at) "
            f"VALUES ({escape_sql(enc_id)}, {escape_sql(p_id)}, {escape_sql(org_id)}, {escape_sql(source_id)}, {escape_sql(claim_id)}, "
            f"{escape_sql(service_type)}, 'CHECKED_OUT', {escape_sql(presence)}, {escape_sql(enc_start.isoformat())}, "
            f"{escape_sql(enc_end.isoformat())}, 1, 'SIMRS_SYNTHETIC_INGEST', NOW(), NOW()) "
            f"ON CONFLICT (id) DO NOTHING;"
        )
        encounters_sql.append(enc_sql)

        # 2. Evidence Care Episode
        care_sql = (
            f"INSERT INTO care_episodes (encounter_id, organization_id, patient_id, encounter_status, presence_status, "
            f"current_revision, last_acked_source_sequence, expected_final_sequence, sync_status, checked_out_at, "
            f"sync_completed_at, created_at, updated_at) "
            f"VALUES ({escape_sql(enc_id)}, {escape_sql(org_id)}, {escape_sql(p_id)}, 'CHECKED_OUT', {escape_sql(presence)}, "
            f"1, {len(evidence_items_for_db)}, {len(evidence_items_for_db)}, 'SYNC_COMPLETE', {escape_sql(enc_end.isoformat())}, "
            f"{escape_sql(enc_end.isoformat())}, NOW(), NOW()) "
            f"ON CONFLICT (encounter_id) DO NOTHING;"
        )
        care_episodes_sql.append(care_sql)

        # 3. Evidence Records & Versions
        pinned_items = []
        for seq, item in enumerate(evidence_items_for_db, start=1):
            rec_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bpjs-rec-{enc_id}-{seq}"))
            ver_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bpjs-ver-{enc_id}-{seq}"))
            ext_rec = f"REC-{enc_id}-{seq}"
            evt_id = f"EVT-{enc_id}-{seq}"

            rec_sql = (
                f"INSERT INTO evidence_records (id, encounter_id, organization_id, source_system_id, external_record_id, "
                f"kind, current_version, status, created_at, updated_at) "
                f"VALUES ({escape_sql(rec_id)}, {escape_sql(enc_id)}, {escape_sql(org_id)}, {escape_sql(adapter_name)}, "
                f"{escape_sql(ext_rec)}, {escape_sql(item['item_type'])}, 1, 'ACTIVE', NOW(), NOW()) "
                f"ON CONFLICT (organization_id, source_system_id, external_record_id) DO NOTHING;"
            )
            evidence_records_sql.append(rec_sql)

            ver_sql = (
                f"INSERT INTO evidence_versions (id, evidence_id, encounter_id, version, source_event_id, source_sequence, "
                f"event_action, code_system, code, canonical_code_system, canonical_code, mapping_status, display_text, "
                f"quantity, unit, canonical_quantity, canonical_unit, source_actor_id, source_actor_role, actor_assurance, "
                f"payload, payload_digest, occurred_at, recorded_at) "
                f"VALUES ({escape_sql(ver_id)}, {escape_sql(rec_id)}, {escape_sql(enc_id)}, 1, {escape_sql(evt_id)}, {seq}, "
                f"'RECORDED', {escape_sql(item['code_system'])}, {escape_sql(item['code'])}, {escape_sql(item['code_system'])}, "
                f"{escape_sql(item['code'])}, 'MAPPED', {escape_sql(item['display'])}, 1, '1', 1, '1', 'DR-001', 'DOCTOR', "
                f"'SOURCE_ASSERTED', '{{}}', {escape_sql(hashlib.sha256(b'{}').hexdigest())}, {escape_sql(enc_start.isoformat())}, NOW()) "
                f"ON CONFLICT (evidence_id, version) DO NOTHING;"
            )
            evidence_versions_sql.append(ver_sql)

            pinned_items.append({
                "evidence_id": rec_id,
                "evidence_version_id": ver_id,
                "version": 1,
                "kind": item["item_type"],
                "status": "ACTIVE",
                "code_system": item["code_system"],
                "code": item["code"],
                "canonical_code_system": item["code_system"],
                "canonical_code": item["code"],
                "mapping_status": "MAPPED",
                "description": item["display"],
                "quantity": "1",
                "unit": "1",
                "canonical_quantity": "1",
                "canonical_unit": "1",
                "occurred_at": enc_start.isoformat(),
                "recorded_at": enc_start.isoformat(),
                "patient_response": "CONFIRMED",
            })

        # 4. Snapshots
        snap_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bpjs-snap-{enc_id}"))
        verif_snap_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bpjs-vsnap-{enc_id}"))
        summary_items_json = [
            {
                "evidence_id": p["evidence_id"],
                "evidence_version_id": p["evidence_version_id"],
                "version": 1,
                "kind": p["kind"],
                "description": p["description"],
                "quantity": "1",
                "unit": "1",
                "recorded_status": "STAFF_COMPLETED",
            }
            for p in pinned_items
        ]
        sum_digest = hashlib.sha256(json.dumps(summary_items_json, sort_keys=True).encode()).hexdigest()

        sum_sql = (
            f"INSERT INTO summary_snapshots (id, encounter_id, evidence_revision, status, items_json, content_digest, "
            f"presented_at, created_at) "
            f"VALUES ({escape_sql(snap_id)}, {escape_sql(enc_id)}, 1, 'READY', {escape_sql(json.dumps(summary_items_json))}, "
            f"{escape_sql(sum_digest)}, {escape_sql(enc_end.isoformat())}, NOW()) "
            f"ON CONFLICT (encounter_id, evidence_revision) DO NOTHING;"
        )
        summary_snapshots_sql.append(sum_sql)

        attestation = {
            "summary_snapshot_id": snap_id,
            "summary_status": "READY",
            "response_id": None,
            "response_type": "CONFIRMED",
            "checked_out_at": enc_end.isoformat(),
        }
        verif_digest = hashlib.sha256(json.dumps({
            "revision": 1,
            "sync": "SYNC_COMPLETE",
            "items": pinned_items,
            "attestation": attestation,
        }, sort_keys=True).encode()).hexdigest()

        verif_sql = (
            f"INSERT INTO verification_evidence_snapshots (id, encounter_id, evidence_revision, episode_sync_status, "
            f"presence_status, patient_confirmation_status, pinned_items_json, pinned_attestation_json, content_digest, created_at) "
            f"VALUES ({escape_sql(verif_snap_id)}, {escape_sql(enc_id)}, 1, 'SYNC_COMPLETE', {escape_sql(presence)}, 'CONFIRMED', "
            f"{escape_sql(json.dumps(pinned_items))}, {escape_sql(json.dumps(attestation))}, {escape_sql(verif_digest)}, NOW()) "
            f"ON CONFLICT (encounter_id, evidence_revision, content_digest) DO NOTHING;"
        )
        verif_snapshots_sql.append(verif_sql)

    # Patient SQL statements
    patient_sqls = []
    for p in patients_to_insert.values():
        p_sql = (
            f"INSERT INTO patients (id, participant_lookup_key, participant_number_ciphertext, display_name_ciphertext, "
            f"display_name_normalized_hmac, identity_assurance, status, created_at, updated_at) "
            f"VALUES ({escape_sql(p['id'])}, {escape_sql(p['lookup_key'])}, {escape_sql(p['p_cipher'])}, "
            f"{escape_sql(p['name_cipher'])}, {escape_sql(p['name_hmac'])}, 'VERIFIED_PARTICIPANT_ID', 'ACTIVE', NOW(), NOW()) "
            f"ON CONFLICT (id) DO NOTHING;"
        )
        patient_sqls.append(p_sql)

    # Write files
    os.makedirs("contracts/fixtures", exist_ok=True)
    os.makedirs("scripts/generated", exist_ok=True)

    fixtures_path = "contracts/fixtures/claims_1000_sample.json"
    with open(fixtures_path, "w", encoding="utf-8") as f:
        json.dump(claims_fixtures, f, indent=2)
    print(f"Saved {len(claims_fixtures)} claim requests to {fixtures_path}")

    encounter_sql_path = "scripts/generated/seed_encounter_1000.sql"
    with open(encounter_sql_path, "w", encoding="utf-8") as f:
        f.write("BEGIN;\n")
        for s in patient_sqls:
            f.write(s + "\n")
        for s in encounters_sql:
            f.write(s + "\n")
        f.write("COMMIT;\n")
    print(f"Saved encounter seed SQL to {encounter_sql_path}")

    evidence_sql_path = "scripts/generated/seed_evidence_1000.sql"
    with open(evidence_sql_path, "w", encoding="utf-8") as f:
        f.write("BEGIN;\n")
        for s in care_episodes_sql:
            f.write(s + "\n")
        for s in evidence_records_sql:
            f.write(s + "\n")
        for s in evidence_versions_sql:
            f.write(s + "\n")
        for s in summary_snapshots_sql:
            f.write(s + "\n")
        for s in verif_snapshots_sql:
            f.write(s + "\n")
        f.write("COMMIT;\n")
    print(f"Saved evidence seed SQL to {evidence_sql_path}")

    # Summary
    print("\n=== SUMMARY GENERATION ===")
    counts = sample_df["scenario"].value_counts()
    for sc, count in counts.items():
        pct = (count / len(sample_df)) * 100
        print(f"  - {sc:20}: {count} ({pct:.1f}%)")
    total_val = sample_df["FKL48"].sum()
    fraud_val = sample_df[sample_df["scenario"] != "VALID"]["FKL48"].sum()
    print(f"\nTotal Klaim 1,000 Sampel: Rp {total_val:,.2f}")
    print(f"Total Nilai Klaim Bermasalah (~10%): Rp {fraud_val:,.2f} ({fraud_val/total_val*100:.1f}%)")


if __name__ == "__main__":
    main()
