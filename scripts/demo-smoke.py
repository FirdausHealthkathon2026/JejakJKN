"""End-to-end check of the demo journey against a running stack.

Walks the same calls the web apps make: QR in, SIMRS records, QR out, patient
response, claim submission, verification, review case, AI summary, and decision.
"""

import sys
import time
import uuid

import httpx

GATEWAY = "http://localhost:18080"
TOKEN_URL = "http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token"
SIMRS_A = "http://localhost:8101/api"
SIMRS_B = "http://localhost:8102/api"
CLAIMS = "http://localhost:8103/api"
CLAIM_SOURCE = "BPJS_FKRTL_PROD"

client = httpx.Client(timeout=30)


def token(client_id: str, username: str, password: str) -> dict:
    response = client.post(
        TOKEN_URL,
        data={"grant_type": "password", "client_id": client_id, "username": username, "password": password},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def ok(response: httpx.Response) -> dict:
    assert response.is_success, f"{response.request.method} {response.url} -> {response.status_code}: {response.text[:300]}"
    return response.json()


def idem() -> dict:
    return {"Idempotency-Key": str(uuid.uuid4())}


def wait(check, label: str, seconds: int = 90):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for {label}")


def qr(patient: dict, purpose: str, encounter_id: str | None = None) -> str:
    body = {"purpose": purpose, "encounter_id": encounter_id}
    return ok(client.post(f"{GATEWAY}/api/v1/patient/qr-tokens", headers=patient, json=body))["token"]


def confirm_summary(patient: dict, encounter_id: str, dispute: bool) -> None:
    summary = wait(
        lambda: (lambda r: r.json() if r.status_code == 200 else None)(
            client.get(f"{GATEWAY}/api/v1/patient/encounters/{encounter_id}/checkout-summary", headers=patient)
        ),
        "checkout summary",
    )
    items, overall = [], "CONFIRMED"
    for item in summary["items"]:
        if dispute and item["kind"] == "MEDICATION_DISPENSE":
            items.append({"evidence_id": item["evidence_id"], "response": "DISPUTED", "reason": "QUANTITY_DIFFERENT"})
            overall = "PARTIALLY_DISPUTED"
        else:
            items.append({"evidence_id": item["evidence_id"], "response": "CONFIRMED"})
    ok(client.post(
        f"{GATEWAY}/api/v1/patient/checkout-summaries/{summary['snapshot_id']}/responses",
        headers=patient | idem(),
        json={"overall_response": overall, "items": items},
    ))


def verify(verifier: dict, claim: dict) -> dict:
    body = {
        "claim_source": CLAIM_SOURCE,
        "claim_id": claim["id"],
        "claim_revision": claim["revision"],
        "relationship": {"type": "ORIGINAL", "related_claim_id": None},
        "patient": {"participant_number": claim["participant_number"]},
        "facility": {"namespace": "DEMO-FASKES", "code": claim["facility_code"]},
        "service_period": {"start": claim["service_start"], "end": claim["service_end"]},
        "items": [
            {k: item[k] for k in ("item_ref", "item_type", "code_system", "code", "display", "quantity", "unit")}
            for item in claim["items"]
        ],
    }
    queued = ok(client.post(f"{GATEWAY}/api/v1/verifications", headers=verifier | idem(), json=body))
    url = f"{GATEWAY}/api/v1/verifications/{queued['verification_id']}"
    return wait(lambda: (lambda a: a if a["status"] not in {"QUEUED", "RUNNING"} else None)(ok(client.get(url, headers=verifier))), "verification")


def simrs_a_journey(patient: dict, verifier: dict) -> None:
    print("[A] QR masuk, catat layanan, QR keluar")
    scan = ok(client.post(f"{SIMRS_A}/scan/check-in", headers=idem(), json={"qr_token": qr(patient, "CHECK_IN"), "external_visit_reference": f"VISIT-{int(time.time())}"}))
    encounter = scan["encounter_id"]
    assert scan["participant_number"], "check-in must return the participant number"
    records = [
        ("DIAGNOSIS", "DEMO-DIAGNOSIS-CATALOG", "H10.9", "Konjungtivitis", None, None),
        ("PROCEDURE", "DEMO-PROCEDURE-CATALOG", "PROC-EYE-01", "Pemeriksaan mata", None, None),
        ("MEDICATION_DISPENSED", "DEMO-MEDICATION-CATALOG", "MED-PCT-500", "Paracetamol 500 mg", "10", "tablet"),
    ]
    for event_type, system, code, display, quantity, unit in records:
        ok(client.post(f"{SIMRS_A}/visits/{encounter}/clinical-events", json={"event_type": event_type, "code_system": system, "code": code, "display": display, "quantity": quantity, "unit": unit}))
    ok(client.post(f"{SIMRS_A}/scan/check-out", headers=idem(), json={"qr_token": qr(patient, "CHECK_OUT", encounter)}))
    ok(client.post(f"{SIMRS_A}/visits/{encounter}/sync-complete"))
    visit = wait(lambda: next((v for v in ok(client.get(f"{SIMRS_A}/visits")) if v["encounter_id"] == encounter and v["sync_status"] == "SYNC_COMPLETE"), None), "sync complete")
    assert len(visit["records"]) == 3, visit

    print("[A] Pasien menyanggah obat, klaim diajukan dengan jumlah berlebih")
    confirm_summary(patient, encounter, dispute=True)
    claim = ok(client.post(f"{CLAIMS}/claims", json={
        "participant_number": visit["participant_number"], "facility_code": "HOSP-DEMO-001", "visit_reference": visit["external_visit_reference"], "encounter_id": encounter,
        "service_start": visit["checked_in_at"], "service_end": visit["checked_out_at"], "care_type": "RJ", "amount": 215000,
        "items": [
            {"item_ref": "DX-1", "item_type": "DIAGNOSIS", "code_system": "DEMO-DIAGNOSIS-CATALOG", "code": "H10.9", "display": "Konjungtivitis"},
            {"item_ref": "PROC-1", "item_type": "PROCEDURE", "code_system": "DEMO-PROCEDURE-CATALOG", "code": "PROC-EYE-01", "display": "Pemeriksaan mata"},
            {"item_ref": "MED-1", "item_type": "MEDICATION_DISPENSE", "code_system": "DEMO-MEDICATION-CATALOG", "code": "MED-PCT-500", "display": "Paracetamol 500 mg", "quantity": 20, "unit": "tablet"},
        ],
    }))
    print(f"[A] Klaim {claim['id']} diterima simulator BPJS")

    assessment = verify(verifier, claim)
    assert assessment["status"] == "COMPLETED", assessment
    findings = ok(client.get(f"{GATEWAY}/api/v1/verifications/{assessment['verification_id']}/findings", headers=verifier))
    codes = {row["finding_code"] for row in findings}
    assert {"QUANTITY_MISMATCH", "PATIENT_DISPUTED"} <= codes, codes
    print(f"[V] Temuan: {sorted(codes)}")
    items = ok(client.get(f"{GATEWAY}/api/v1/verifications/{assessment['verification_id']}/items", headers=verifier))
    assert any(i["match_result"] == "QUANTITY_MISMATCH" for i in items), items
    assert claim["id"] in {row["claim_id"] for row in ok(client.get(f"{GATEWAY}/api/v1/verifications", headers=verifier))}

    case = wait(lambda: next((c for c in ok(client.get(f"{GATEWAY}/api/v1/review-cases", headers=verifier)) if c["claim_id"] == claim["id"]), None), "review case")
    print("[V] Kasus terbuka, menunggu Ringkasan AI")
    purpose = {"X-Access-Purpose": "FRAUD_REVIEW"}
    detail = wait(lambda: (lambda c: c if c.get("narrative") else None)(ok(client.get(f"{GATEWAY}/api/v1/review-cases/{case['id']}", headers=verifier | purpose))), "AI summary", 120)
    print(f"[V] Ringkasan ditulis oleh: {detail['narrative_method']} ({detail['narrative_status']})")
    summary = " ".join(detail["narrative"]["summary"])
    assert "YANG TIDAK SESUAI" in summary, summary
    for raw in ("UNIQUE_MATCH", "QUANTITY_MISMATCH", "PROC-1", "MED-1"):
        assert raw not in summary, raw

    ok(client.post(f"{GATEWAY}/api/v1/review-cases/{case['id']}/assign", headers=verifier, json={"assignee": "verifier01"}))
    ok(client.post(f"{GATEWAY}/api/v1/review-cases/{case['id']}/decisions", headers=verifier | idem(), json={"decision": "REQUEST_CLARIFICATION", "reason": "Minta penjelasan faskes soal selisih jumlah."}))
    final = ok(client.get(f"{GATEWAY}/api/v1/review-cases/{case['id']}", headers=verifier | purpose))
    assert final["state"] == "NEEDS_MORE_EVIDENCE", final["state"]
    assert final["assigned_name"] == "verifier01", final["assigned_name"]
    assert {e["kind"] for e in final["events"]} >= {"ASSIGN", "DECISION", "ACCESS"}, final["events"]
    ok(client.post(f"{CLAIMS}/claims/{claim['id']}/status", json={"status": "VERIFYING"}))
    print("[V] Tindak lanjut tersimpan")


def simrs_b_journey(patient: dict, verifier: dict) -> None:
    print("[B] QR masuk, catatan lokal diterjemahkan adapter")
    scan = ok(client.post(f"{SIMRS_B}/pindai/masuk", headers=idem(), json={"token_qr": qr(patient, "CHECK_IN"), "referensi_kunjungan": f"RJ-{int(time.time())}"}))
    encounter = scan["encounter_id"]
    entries = [("DIAGNOSIS", "J06.9", None), ("TINDAKAN", "RJ-DOK-001", 1), ("OBAT", "OB-PCT500-STR", 1)]
    for jenis, kode, jumlah in entries:
        ok(client.post(f"{SIMRS_B}/kunjungan/{encounter}/catatan", headers=idem(), json={"jenis": jenis, "kode": kode, "jumlah": jumlah, "urutan": 1, "id_rekam": f"SIMRS-B-{uuid.uuid4()}"}))
    ok(client.post(f"{SIMRS_B}/pindai/keluar", headers=idem(), json={"token_qr": qr(patient, "CHECK_OUT", encounter)}))
    ok(client.post(f"{SIMRS_B}/kunjungan/{encounter}/sinkronisasi-selesai"))
    visit = wait(lambda: next((v for v in ok(client.get(f"{SIMRS_B}/kunjungan")) if v["encounter_id"] == encounter and v["sync_status"] == "SYNC_COMPLETE"), None), "simrs b sync")
    confirm_summary(patient, encounter, dispute=False)

    items = []
    for index, record in enumerate(visit["records"]):
        canonical = record["canonical"]
        is_drug = canonical["event_type"] == "MEDICATION_DISPENSED"
        items.append({
            "item_ref": f"ITEM-{index + 1}",
            "item_type": {"DIAGNOSIS": "DIAGNOSIS", "PROCEDURE": "PROCEDURE", "MEDICATION_DISPENSED": "MEDICATION_DISPENSE"}[canonical["event_type"]],
            "code_system": canonical["content"]["code_system"], "code": canonical["content"]["code"], "display": canonical["content"]["display"],
            "quantity": canonical["content"]["quantity"] if is_drug else 1, "unit": canonical["content"]["unit"] if is_drug else "1",
        })
    assert any(i["quantity"] == 10 and i["unit"] == "tablet" for i in items), items
    claim = ok(client.post(f"{CLAIMS}/claims", json={
        "participant_number": visit["participant_number"], "facility_code": "HOSP-DEMO-002", "visit_reference": visit["external_visit_reference"], "encounter_id": encounter,
        "service_start": visit["checked_in_at"], "service_end": visit["checked_out_at"], "amount": 168000, "items": items,
    }))
    assessment = verify(verifier, claim)
    findings = ok(client.get(f"{GATEWAY}/api/v1/verifications/{assessment['verification_id']}/findings", headers=verifier))
    assert assessment["matched_items_count"] == len(items), (assessment, findings)
    assert not assessment["review_required"], findings
    print(f"[B] Klaim {claim['id']} sesuai tanpa temuan")


def main() -> int:
    patient = token("patient-web", "patient01", "synthetic-patient-01")
    verifier = token("verifier-web", "verifier01", "synthetic-verifier-01")
    simrs_a_journey(patient, verifier)
    simrs_b_journey(patient, verifier)
    print("SEMUA ALUR UTAMA LOLOS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
