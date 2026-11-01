# TEST_MATRIX_AND_SYNTHETIC_FIXTURES_SPEC :: v1.0

## 1. CRITICAL_TEST_MATRIX_IDS

### 1.1 Encounter & QR (`QR-01` .. `QR-10`)
- `QR-01`: Valid first-time `CHECK_IN` QR -> creates 1 `OPEN` encounter (`presence_status=QR_VERIFIED`).
- `QR-02`: Same `CHECK_IN` QR re-scanned with same `(scanner_client_id, Idempotency-Key)` -> returns idempotent receipt, 0 duplicate encounters; different scanner/key -> `409 QR_ALREADY_CONSUMED`.
- `QR-03`: 100 concurrent scans on 1 `CHECK_IN` token -> exactly 1 `201 Created`, 99 `409 Conflict`, 1 encounter row in DB.
- `QR-04`: Expired token (`>60s`) -> `410 QR_TOKEN_EXPIRED`.
- `QR-05`: Facility B scanner attempts to redeem token hinted/bound to Facility A -> `403 FACILITY_MISMATCH`.
- `QR-06`: Tampered 1-byte JWS signature -> `401 INVALID_QR_SIGNATURE`.
- `QR-07`: Patient B requests/uses `CHECK_OUT` QR for Patient A's encounter -> `403 FORBIDDEN`.
- `QR-08`: `CHECK_OUT` QR on non-open encounter -> `409 INVALID_ENCOUNTER_STATE`.
- `QR-09`: Authorized exception (`NO_SMARTPHONE`) -> creates encounter with `presence_status=EXCEPTION_DOCUMENTED` and `encounter_exceptions` audit row.
- `QR-10`: Redis down during QR redemption -> `503 SERVICE_UNAVAILABLE` (fail closed).

### 1.2 SIMRS & Patient Evidence (`EV-01` .. `EV-11`)
- `EV-01`: SIMRS sends `DIAGNOSIS`, `PROCEDURE`, `MEDICATION_DISPENSED` -> persisted and shown in checkout summary after `CHECK_OUT`.
- `EV-02`: `MEDICATION_PRESCRIBED` without `MEDICATION_DISPENSED` -> NOT treated as dispensed medication evidence.
- `EV-03`: Duplicate `source_event_id` redelivery -> idempotent `200/201`, 1 logical record version.
- `EV-04`: Quantity correction `v1 -> v2` -> both `evidence_versions` rows preserved, `current_version = 2`.
- `EV-05`: Out-of-order `v3` before `v2` -> routed to `evidence_quarantine`, `v1` not overwritten.
- `EV-06`: Late evidence after `CHECK_OUT` -> prior snapshot immutable, new snapshot created, prior response marked `RECONFIRMATION_REQUIRED`.
- `EV-07`: Patient queries encounter while `OPEN` -> only `check_in_successful=true`, zero live clinical stages.
- `EV-08`: Patient confirms all items after `CHECK_OUT` -> `CONFIRMED` bound to `(snapshot_id, evidence_version_id)`.
- `EV-09`: Patient disputes specific medication -> `PARTIALLY_DISPUTED` per item without mutating SIMRS evidence.
- `EV-10`: Patient `NO_RESPONSE` / `DECLINED` -> `CHECKED_OUT` status remains valid.
- `EV-11`: Patient A requests Patient B checkout summary -> `404/403` with zero data leakage.

### 1.3 Candidate Matching, Reconciliation & Duplicates (`VM-01` .. `VM-23`)
- `VM-01`: Exact participant + facility + date + items -> `UNIQUE_MATCH` + `ITEMS_CONSISTENT`.
- `VM-02`: 2 encounters same day, only `E2` items match -> both evaluated, `UNIQUE_MATCH` = `E2`.
- `VM-03`: 2 encounters same day, both match identically -> `AMBIGUOUS_MATCH`, `selected_encounter_id = null`.
- `VM-04`: `E1` already linked to `C1`, `E2` unlinked, both match `C2` identically -> **still `AMBIGUOUS_MATCH`** (never auto-pick `E2`).
- `VM-05`: Two patients with identical display name, different `participant_number` -> never merged.
- `VM-06`: Claim request with name only (`participant_number = null`) -> `LOW_IDENTITY_ASSURANCE`, `IDENTITY_INSUFFICIENT`, `R002_IDENTITY_WEAK`.
- `VM-07`: Zero candidate encounters -> `NO_ENCOUNTER_FOUND` (`R001_NO_ENCOUNTER`), `final_fraud_decision = null`.
- `VM-08`: Candidate encounter found, procedure missing -> `ITEM_MISMATCH` (`R003_ITEM_MISSING`).
- `VM-09`: Claimed qty `10`, dispensed qty `5` -> `QUANTITY_MISMATCH` (`R004_QUANTITY_MISMATCH`).
- `VM-10`: 2 identical procedure claim lines vs 1 recorded procedure -> bipartite matching matches 1 and flags 1 `MISSING_IN_EVIDENCE`.
- `VM-11`: Identical claim re-verified with unchanged `dependency_fingerprint` -> reuses prior completed run.
- `VM-12`: Same `claim_id` with revised quantity -> creates new `run_number`, old run immutable.
- `VM-13`: Late evidence arrives after run -> old run marked `STALE_INPUT`, `re-evaluate` creates new run.
- `VM-14`: Distinct claims `C1` and `C2` match `E1` -> `POTENTIAL_ENCOUNTER_REUSE` (`R007_ENCOUNTER_REUSE`).
- `VM-15`: Distinct claims `C1` and `C2` consume same dispense evidence `EV-MED-01` -> `POTENTIAL_EVIDENCE_REUSE` (`R008_EVIDENCE_REUSE`).
- `VM-16`: Valid `CORRECTION` / `REVERSAL` referencing `related_claim_id` -> `KNOWN_REVISION_OR_REVERSAL`, old association marked `SUPERSEDED`/`RETRACTED`.
- `VM-17`: 2 verifiers submit concurrent claims targeting `E1` -> ordered `pg_advisory_xact_lock` serializes association check; conflict detected deterministically.
- `VM-18`: 11+ candidate encounters (limit=10) -> `TOO_MANY_CANDIDATES` (never silent truncation).
- `VM-19`: Unmapped medication unit -> `UNSUPPORTED_MAPPING` (`R014_MAPPING_UNSUPPORTED`).
- `VM-20`: Same `claim_id` string from different `claim_source` -> treated as distinct external claims.
- `VM-21`: First-time claim with no reuse in JejakJKN -> `NO_REUSE_FOUND_IN_JEJAKJKN_HISTORY`.
- `VM-22`: Multi-day inpatient encounter crossing midnight -> time-window overlap matches accurately.
- `VM-23`: Claimed item disputed by patient -> `R005_PATIENT_DISPUTE`, `review_required = true`, `final_fraud_decision = null`.

### 1.4 Security & Resilience (`SEC-01` .. `SEC-12`)
- `SEC-01`..`SEC-03`: Role/scope/tenant isolation (`403` + `access_audit` row).
- `SEC-04`: Zero PHI/JWT/QR tokens in structured JSON logs.
- `SEC-05`..`SEC-07`: Outbox/Inbox idempotency across RabbitMQ/DB restarts.
- `SEC-08`: Narrative worker fallback when LLM disabled/offline.
- `SEC-09`: Fuzzing participant lookup -> no SQLi, no enumeration.
- `SEC-10`: `audit_chain` hash verification detects row tampering.
- `SEC-11`..`SEC-12`: Rate limiting (`429`) and backup/restore verification.
