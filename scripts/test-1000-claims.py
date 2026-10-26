"""Benchmark & Test Harness for 1,000 BPJS Claim Samples on JejakJKN.

Validates end-to-end fraud screening accuracy across 4 dimensions:
  1. Encounter Matching (Phantom billing & timing anomaly detection)
  2. Evidence Reconciliation (Ghost procedure & upcoding detection)
  3. Duplicate Claim Assessment (Double billing detection)
  4. Identity & Presence Assurance (Absent patient detection)
"""

import argparse
import asyncio
import json
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx

GATEWAY_URL = "http://localhost:18080"
KEYCLOAK_URL = "http://localhost:8081"
FIXTURES_PATH = "contracts/fixtures/claims_1000_sample.json"


def get_verifier_token() -> str:
    url = f"{KEYCLOAK_URL}/realms/jejakjkn-dev/protocol/openid-connect/token"
    payload = {
        "client_id": "verifier-web",
        "grant_type": "password",
        "username": "verifier01",
        "password": "synthetic-verifier-01",
    }
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(url, data=payload)
        resp.raise_for_status()
        return resp.json()["access_token"]


def verify_single_claim(client: httpx.Client, token: str, claim: dict) -> dict:
    import uuid

    req_body = claim["request_payload"]
    idx = claim["index"]
    scenario = claim["scenario"]
    expected_status = claim["expected_status"]
    amount = claim["claim_amount_rp"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
    }

    # 1. Submit claim verification
    t0 = time.time()
    post_resp = None
    for attempt in range(5):
        post_resp = client.post(
            f"{GATEWAY_URL}/api/v1/verifications", json=req_body, headers=headers
        )
        if post_resp.status_code == 429:
            time.sleep(0.3 * (attempt + 1))
            continue
        break

    if not post_resp or post_resp.status_code != 202:
        return {
            "index": idx,
            "claim_id": claim["claim_id"],
            "scenario": scenario,
            "expected_status": expected_status,
            "amount": amount,
            "status": "ERROR_SUBMIT",
            "detected_as_fraud": False,
            "findings": [],
            "error": post_resp.text if post_resp else "No response",
        }

    verif_id = post_resp.json()["verification_id"]

    # 2. Poll until completed
    assessment = None
    for _ in range(40):
        time.sleep(0.3)
        get_resp = client.get(
            f"{GATEWAY_URL}/api/v1/verifications/{verif_id}", headers=headers
        )
        if get_resp.status_code == 429:
            time.sleep(0.5)
            continue
        if get_resp.status_code == 200:
            data = get_resp.json()
            if data.get("status") in {"COMPLETED", "FAILED"}:
                assessment = data
                break

    if not assessment or assessment.get("status") != "COMPLETED":
        return {
            "index": idx,
            "claim_id": claim["claim_id"],
            "scenario": scenario,
            "expected_status": expected_status,
            "amount": amount,
            "status": "TIMEOUT",
            "detected_as_fraud": False,
            "findings": [],
        }

    # 3. Retrieve findings
    findings_resp = client.get(
        f"{GATEWAY_URL}/api/v1/verifications/{verif_id}/findings", headers=headers
    )
    findings = findings_resp.json() if findings_resp.status_code == 200 else []

    high_findings = [f for f in findings if f.get("severity") in {"HIGH", "MEDIUM"}]
    rule_codes = [f.get("rule_id") for f in high_findings]

    enc_match = assessment.get("encounter_match_status")
    ev_recon = assessment.get("evidence_reconciliation_status")

    # A claim is flagged as fraud/anomaly if it has HIGH/MEDIUM findings
    # or encounter is not uniquely matched, or evidence has items missing
    is_fraud = bool(high_findings) or (enc_match != "UNIQUE_MATCH") or (ev_recon != "ITEMS_CONSISTENT")

    elapsed = round(time.time() - t0, 2)
    return {
        "index": idx,
        "claim_id": claim["claim_id"],
        "scenario": scenario,
        "expected_status": expected_status,
        "amount": amount,
        "status": "COMPLETED",
        "encounter_match": enc_match,
        "evidence_recon": ev_recon,
        "detected_as_fraud": is_fraud,
        "findings": rule_codes,
        "elapsed_sec": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="Test 1,000 BPJS Claim Samples against JejakJKN")
    parser.add_argument("--limit", type=int, default=1000, help="Number of claims to test (default 1000)")
    parser.add_argument("--offset", type=int, default=0, help="Offset index to start from (default 0)")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent worker threads (default 10)")
    parser.add_argument("--out", type=str, default="contracts/fixtures/benchmark_results.json", help="Output JSON path")
    args = parser.parse_args()

    print(f"=== JEJAKJKN 1,000 REAL BPJS CLAIM VERIFICATION BENCHMARK ===")
    print(f"1. Authenticating as BPJS Verifier...")
    token = get_verifier_token()
    print("   [OK] Token acquired.")

    print(f"2. Loading fixtures from {FIXTURES_PATH}...")
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        all_claims = json.load(f)

    test_subset = all_claims[args.offset : args.offset + args.limit]
    total_count = len(test_subset)
    print(f"   [OK] {total_count} claims loaded (Offset {args.offset}, Testing with {args.workers} workers)...")

    results = []
    t_start = time.time()

    with httpx.Client(timeout=15.0) as client:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_claim = {
                executor.submit(verify_single_claim, client, token, c): c
                for c in test_subset
            }
            completed = 0
            for future in as_completed(future_to_claim):
                res = future.result()
                results.append(res)
                completed += 1
                if completed % 25 == 0 or completed == total_count:
                    pct = (completed / total_count) * 100
                    print(f"   Progress: {completed}/{total_count} ({pct:.1f}%) claims verified...")

    t_total = time.time() - t_start
    print(f"\n   [FINISHED] Verified {total_count} claims in {t_total:.1f} seconds ({total_count/t_total:.1f} claims/sec)!\n")

    # Metrics computation
    tp = sum(1 for r in results if r["expected_status"] == "FLAGGED" and r["detected_as_fraud"])
    fn = sum(1 for r in results if r["expected_status"] == "FLAGGED" and not r["detected_as_fraud"])
    tn = sum(1 for r in results if r["expected_status"] == "CLEAR" and not r["detected_as_fraud"])
    fp = sum(1 for r in results if r["expected_status"] == "CLEAR" and r["detected_as_fraud"])

    accuracy = (tp + tn) / total_count if total_count else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0

    total_amount = sum(r["amount"] for r in results)
    fraud_amount = sum(r["amount"] for r in results if r["scenario"] != "VALID")
    saved_amount = sum(r["amount"] for r in results if r["detected_as_fraud"])

    print("=" * 70)
    print("                    EXECUTIVE FRAUD SCORECARD                     ")
    print("=" * 70)
    print(f"Total Klaim Diuji         : {total_count:,} Klaim")
    print(f"Total Nilai Tagihan RS    : Rp {total_amount:,.2f}")
    print(f"Total Potensi Fraud Nilai : Rp {fraud_amount:,.2f} ({fraud_amount/total_amount*100:.1f}%)")
    print(f"Nilai Berhasil Diselamatkan : Rp {saved_amount:,.2f}")
    print("-" * 70)
    print(f"Akurasi Deteksi (Accuracy): {accuracy * 100:.2f}%")
    print(f"Presisi (Precision)       : {precision * 100:.2f}%")
    print(f"Recall (Tingkat Deteksi)  : {recall * 100:.2f}%")
    print(f"F1-Score                  : {f1 * 100:.2f}%")
    print("=" * 70)

    print("\nBREAKDOWN HASIL PER SKENARIO FRAUD:")
    print("-" * 70)
    scenarios = set(r["scenario"] for r in results)
    for sc in sorted(scenarios):
        sc_subset = [r for r in results if r["scenario"] == sc]
        caught = sum(1 for r in sc_subset if r["detected_as_fraud"])
        total_sc = len(sc_subset)
        sc_val = sum(r["amount"] for r in sc_subset)
        pct = (caught / total_sc) * 100 if total_sc else 0
        status_lbl = "CLEAN (Auto-Approve)" if sc == "VALID" else "FRAUD / FLAGGED"
        print(f"  * {sc:18} [{status_lbl:20}]: {caught}/{total_sc} ({pct:.1f}%) | Rp {sc_val:,.2f}")

    print("=" * 70)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({
                "summary": {
                    "total_count": total_count,
                    "total_amount_rp": total_amount,
                    "fraud_amount_rp": fraud_amount,
                    "saved_amount_rp": saved_amount,
                    "accuracy": accuracy,
                    "precision": precision,
                    "recall": recall,
                    "f1_score": f1,
                    "duration_sec": t_total,
                },
                "results": results
            }, f, indent=2)
        print(f"Results saved to {args.out}")


if __name__ == "__main__":
    main()
