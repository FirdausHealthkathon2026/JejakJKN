# ADR_INDEX :: v1.0

| ADR | Status | Decision |
|---|---|---|
| `ADR-001` | Accepted | **Four Isolated Core Microservices + Databases:** `encounter-service`, `evidence-service`, `verification-service`, `review-service` each own an isolated PostgreSQL DB with zero cross-DB SQL joins or foreign keys. |
| `ADR-002` | Accepted | **API-Only Clinical Ingestion via SIMRS Adapters:** Core JejakJKN exposes no clinical input UI. SIMRS simulators persist to their own DB first and push events via OAuth2 Client Credentials adapters. |
| `ADR-003` | Accepted | **Post-Checkout Patient Summary Only:** Patient app never renders live care stage progress during an active visit; summary snapshot is visible only after valid `CHECK_OUT` QR redemption. |
| `ADR-004` | Accepted | **Verifier Claim Inspection Only:** Platform accepts verification requests (`POST /api/v1/verifications`) over external claims; it never submits, adjudicates, or pays BPJS claims. |
| `ADR-005` | Accepted | **Exhaustive Candidate Evaluation & Non-Exclusive Associations:** Candidate search evaluates all matching encounters without `first-match-wins` or skipping previously associated encounters; `claim_encounter_associations` does not enforce `UNIQUE(encounter_id)`. |
| `ADR-006` | Accepted | **2-Phase Redis + DB QR Redemption:** Redis Lua script transitions nonce `ISSUED -> RESERVED -> COMMITTED` bound to `(scanner_client_id, idempotency_key)` and durable `qr_redemption_receipts` row. |
| `ADR-007` | Accepted | **Bipartite Item Matching & 4-Dimensional Verdict Separation:** Item reconciliation uses maximum bipartite matching / bounded capacity allocation; output separates `encounter_match`, `evidence_reconciliation`, `duplicate_assessment`, and `patient_confirmation` with `final_fraud_decision = null`. |
| `ADR-008` | Accepted | **Ordered Advisory Locks & Dependency Fingerprint Reuse:** Verification run finalization acquires sorted `pg_advisory_xact_lock` on candidate encounters; prior runs are reused only when full `dependency_fingerprint` matches. |
