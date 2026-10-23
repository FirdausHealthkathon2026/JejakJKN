# JEJAKJKN_AGENT_SPEC :: v1.0-AGENT-IR
# FORMAT: COMPACT_DETERMINISTIC_SPEC (OPTIMIZED FOR LLM/CODING-AGENT CONTEXT & CODEGEN)
# SOURCE_OF_TRUTH: JejakJKN_Technical_Implementation_Specification_v1.0.md

---

## 0. SYSTEM_INVARIANTS [HARD_CONSTRAINTS]

```yaml
invariants:
  INV-01_NO_CLINICAL_UI_IN_CORE:
    rule: "Core JejakJKN services NEVER expose clinical data entry forms. All clinical/pharmacy records originate in external SIMRS simulators (simrs-a, simrs-b) and enter ONLY via authenticated adapter API (/api/v1/integrations/*)."
  INV-02_PATIENT_NO_LIVE_STAGE:
    rule: "Patient app (/api/v1/patient/*) NEVER exposes live care stage progress during an active encounter. Patient sees only check_in_successful, check_out_successful, and confirmation_status. Clinical summary is accessible ONLY AFTER valid QR_OUT redemption and snapshot status == READY."
  INV-03_VERIFIER_REQUEST_ONLY:
    rule: "JejakJKN is NOT a claim submission, adjudication, or payment system. Verifier submits a claim verification request (POST /api/v1/verifications) for an external claim. No POST /claims/submit or payment lifecycle exists."
  INV-04_INTERNAL_ENCOUNTER_ID:
    rule: "encounter_id (UUID) is internal to JejakJKN (returned to SIMRS for operational correlation). External claim verification requests do NOT require or assume encounter_id; matching uses (participant_identity, facility_code, service_period)."
  INV-05_EVALUATE_ALL_CANDIDATES:
    rule: "Candidate search MUST evaluate ALL eligible encounters matching (identity, facility, time_window). NEVER use first-match-wins. NEVER skip or deprioritize encounters already associated with prior claims. If candidate count > safety_limit, return TOO_MANY_CANDIDATES (never silently truncate)."
  INV-06_NO_1_TO_1_CLAIM_ENCOUNTER_LOCK:
    rule: "DB schema and engine MUST NOT enforce UNIQUE(encounter_id) on claim_encounter_associations. Multiple claims on the same encounter are recorded to detect POTENTIAL_ENCOUNTER_REUSE / POTENTIAL_EVIDENCE_REUSE."
  INV-07_FOUR_ORTHOGONAL_DIMENSIONS:
    rule: "Verification output separates 4 orthogonal dimensions: (A) encounter_match, (B) evidence_reconciliation, (C) duplicate_assessment, (D) patient_confirmation. final_fraud_decision is ALWAYS null."
  INV-08_NO_DOUBLE_COUNTING_EVIDENCE:
    rule: "Within a single verification run, one indivisible evidence record CANNOT satisfy two claim items. Quantitative items (e.g., dispensed medication) use bounded capacity allocation without over-allocating."
  INV-09_PRESCRIBED_NEQ_DISPENSED:
    rule: "MEDICATION_PRESCRIBED is NOT evidence of medication delivery. Only MEDICATION_DISPENSED counts as dispensed medication evidence."
  INV-10_STRICT_DB_ISOLATION:
    rule: "4 core services own 4 isolated PostgreSQL databases (encounter_db, evidence_db, verification_db, review_db) with distinct DB users/credentials. Zero cross-DB SQL joins or foreign keys."
  INV-11_APPEND_ONLY_VERSIONS:
    rule: "Evidence corrections/cancellations create new immutable evidence_versions rows (monotonic version). Out-of-order older source versions NEVER overwrite newer versions; they go to quarantine/reconciliation."
  INV-12_QR_2PHASE_ATOMICITY:
    rule: "QR tokens (60s TTL, JWS/opaque, zero PHI) use Redis atomic reservation (RESERVED -> COMMITTED) + PostgreSQL qr_redemption_receipts idempotency so DB failure after Redis reserve never allows cross-scanner token theft or duplicate encounters."
  INV-13_DEPENDENCY_FINGERPRINT_CACHE:
    rule: "Prior verification run is reused ONLY IF (claim_source, claim_id, canonical_claim_digest, ruleset_version, candidate_id_revision_set, evidence_snapshot_digests, association_watermark) are 100% identical."
  INV-14_ORDERED_ADVISORY_LOCKS:
    rule: "Finalizing a verification run acquires pg_advisory_xact_lock on sorted candidate encounter UUID hashes inside verification_db transaction, re-reads active associations, recomputes duplicate flags if changed, and commits atomically with outbox."
  INV-15_AI_NARRATIVE_BOUNDARY:
    rule: "Narrative worker is optional (default: template). Receives only de-identified deterministic findings. Never adds findings, never alters dispositions, never outputs definitive fraud verdicts."
```

---

## 1. SERVICE_TOPOLOGY & NETWORK_BOUNDARIES

| Service / App | Dir Path | Runtime Stack | Internal Port | Host Port (Dev) | Owned DB / State | DB Role |
|---|---|---|---:|---:|---|---|
| `api-gateway` | `infrastructure/gateway` | Nginx / Traefik | `8080` | `8080` | Stateless | — |
| `keycloak` | `infrastructure/keycloak` | Keycloak 26 | `8080` | `8081` | `keycloak_db` | `kc_user` |
| `encounter-service` | `services/encounter-service` | Python 3.12, FastAPI, SQLAlchemy 2 Async | `8001` | — | `encounter_db`, Redis DB `0` | `encounter_app` / `encounter_migrator` |
| `evidence-service` | `services/evidence-service` | Python 3.12, FastAPI, SQLAlchemy 2 Async | `8002` | — | `evidence_db` | `evidence_app` / `evidence_migrator` |
| `verification-service` | `services/verification-service` | Python 3.12, FastAPI, SQLAlchemy 2 Async | `8003` | — | `verification_db` | `verification_app` / `verification_migrator` |
| `review-service` | `services/review-service` | Python 3.12, FastAPI, SQLAlchemy 2 Async | `8004` | — | `review_db` | `review_app` / `review_migrator` |
| `narrative-worker` | `services/narrative-worker` | Python 3.12 Async Consumer | — | — | Writes via `review-service` / `review_db` | `review_app` |
| `simrs-a-backend` | `simulators/simrs-a-backend` | Python 3.12, FastAPI + `adapters/simrs-a` | `8101` | `8101` | `simrs_a_db` | `simrs_a_app` |
| `simrs-b-backend` | `simulators/simrs-b-backend` | Python 3.12, FastAPI + `adapters/simrs-b` | `8102` | `8102` | `simrs_b_db` | `simrs_b_app` |
| `patient-web` | `apps/patient-web` | React 18, TS, Vite, TanStack Query | `5173` | `5173` | Browser (`sessionStorage`) | — |
| `simrs-a-web` | `apps/simrs-a-web` | React 18, TS, Vite, TanStack Query | `5174` | `5174` | Browser (`sessionStorage`) | — |
| `verifier-web` | `apps/verifier-web` | React 18, TS, Vite, TanStack Query | `5175` | `5175` | Browser (`sessionStorage`) | — |
| `simrs-b-demo` | `apps/simrs-b-demo` | React 18, TS, Vite | `5176` | `5176` | Browser (`sessionStorage`) | — |

---

## 2. IDENTITY, OIDC/KEYCLOAK & RBAC_SCOPES

```yaml
keycloak:
  realm: "jejakjkn-dev"
  issuer_url: "http://localhost:8081/realms/jejakjkn-dev"
  public_clients:
    - client_id: "patient-web"
      flow: "authorization_code_pkce"
      roles: ["patient"]
    - client_id: "verifier-web"
      flow: "authorization_code_pkce"
      roles: ["verifier", "review_supervisor", "platform_admin"]
  confidential_clients:
    - client_id: "simrs-a-adapter"
      flow: "client_credentials"
      bound_organization_code: "DEMO-FASKES:HOSP-DEMO-001"
      roles: ["simrs_scanner", "simrs_clinical_sender", "simrs_pharmacy_sender"]
      scopes: ["encounter:checkin", "encounter:checkout", "encounter:exception", "evidence:write", "evidence:correct", "evidence:cancel", "evidence:readstatus"]
    - client_id: "simrs-b-adapter"
      flow: "client_credentials"
      bound_organization_code: "DEMO-FASKES:HOSP-DEMO-002"
      roles: ["simrs_scanner", "simrs_clinical_sender", "simrs_pharmacy_sender"]
      scopes: ["encounter:checkin", "encounter:checkout", "encounter:exception", "evidence:write", "evidence:correct", "evidence:cancel", "evidence:readstatus"]
    - client_id: "internal-encounter-client"
      audience: ["evidence-api", "verification-api"]
      roles: ["internal_service"]
    - client_id: "internal-verification-client"
      audience: ["encounter-api", "evidence-api", "review-api"]
      roles: ["internal_service"]
    - client_id: "internal-review-client"
      audience: ["verification-api", "evidence-api"]
      roles: ["internal_service"]

jwt_custom_claims:
  sub: "UUID"
  org_id: "UUID (tenant organization_id, mandatory for FASKES & VERIFIER_ORG)"
  org_type: "FASKES | VERIFIER_ORG | SYSTEM"
  patient_id: "UUID (present only when role == patient)"
  roles: "list[str]"
  scope: "space-delimited scopes"
  azp: "client_id"

actor_assurance_enum:
  - FEDERATED_VERIFIED      # Directly authenticated via OIDC user token
  - SOURCE_ASSERTED         # Machine token from SIMRS asserting staff metadata (actor.external_id, actor.role)
```

---

## 3. POSTGRESQL_DDL_SPEC [4 CORE DBS + 2 SIMULATOR DBS]

### 3.1 `encounter_db` (Owner: `encounter-service`)

```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY,
    code_namespace VARCHAR(64) NOT NULL,
    external_code VARCHAR(64) NOT NULL,
    org_type VARCHAR(32) NOT NULL CHECK (org_type IN ('FASKES', 'VERIFIER_ORG', 'SYSTEM')),
    display_name VARCHAR(160) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DISABLED')),
    schema_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (code_namespace, external_code)
);

CREATE TABLE patients (
    id UUID PRIMARY KEY,
    participant_lookup_key CHAR(64) NOT NULL UNIQUE, -- HMAC-SHA256(pepper, normalized_participant_number)
    participant_number_ciphertext BYTEA NOT NULL,    -- AES-256-GCM envelope
    display_name_ciphertext BYTEA NOT NULL,          -- AES-256-GCM envelope
    display_name_normalized_hmac CHAR(64) NOT NULL,  -- HMAC-SHA256(pepper, lower_trimmed_name) for low-assurance fallback search
    identity_assurance VARCHAR(32) NOT NULL CHECK (identity_assurance IN ('VERIFIED_PARTICIPANT_ID', 'VERIFIED_EXTERNAL_ID', 'LOW_IDENTITY_ASSURANCE')),
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    schema_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_patients_name_hmac ON patients (display_name_normalized_hmac);

CREATE TABLE patient_external_ids (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    source_system_id UUID NOT NULL,
    external_id VARCHAR(128) NOT NULL,
    identity_type VARCHAR(64) NOT NULL, -- 'JKN_SYNTHETIC' | 'SIMRS_MRN' | 'NATIONAL_ID_SYNTHETIC'
    assurance VARCHAR(32) NOT NULL CHECK (assurance IN ('VERIFIED_EXTERNAL_ID', 'SOURCE_ASSERTED', 'LOW_IDENTITY_ASSURANCE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_system_id, identity_type, external_id)
);
CREATE INDEX idx_patient_ext_lookup ON patient_external_ids (patient_id);

CREATE TABLE source_systems (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    client_id VARCHAR(128) NOT NULL UNIQUE,
    source_code VARCHAR(64) NOT NULL UNIQUE, -- e.g. 'SIMRS-A', 'SIMRS-B'
    kind VARCHAR(32) NOT NULL CHECK (kind IN ('SIMRS_ADAPTER', 'SCANNER_TERMINAL', 'VERIFIER_PORTAL')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    mapping_version VARCHAR(32) NOT NULL DEFAULT 'map-v1.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE encounters (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    source_system_id UUID REFERENCES source_systems(id),
    external_visit_reference VARCHAR(128),
    service_type VARCHAR(32) NOT NULL DEFAULT 'OUTPATIENT' CHECK (service_type IN ('OUTPATIENT', 'INPATIENT', 'EMERGENCY')),
    status VARCHAR(32) NOT NULL CHECK (status IN ('OPEN', 'CHECKED_OUT', 'CLOSED_WITH_EXCEPTION', 'CANCELLED')),
    presence_status VARCHAR(32) NOT NULL CHECK (presence_status IN ('QR_VERIFIED', 'EXCEPTION_DOCUMENTED', 'UNVERIFIED')),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    revision INT NOT NULL DEFAULT 1,
    created_by VARCHAR(128) NOT NULL,
    schema_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Intentionally NO UNIQUE(patient_id, organization_id, date(started_at)) per §11
CREATE INDEX idx_encounters_org_patient_started ON encounters (organization_id, patient_id, started_at, ended_at);
CREATE INDEX idx_encounters_org_started ON encounters (organization_id, started_at);

CREATE TABLE qr_redemption_receipts (
    nonce_digest CHAR(64) PRIMARY KEY, -- SHA-256(nonce)
    purpose VARCHAR(16) NOT NULL CHECK (purpose IN ('CHECK_IN', 'CHECK_OUT')),
    patient_id UUID NOT NULL REFERENCES patients(id),
    encounter_id UUID NOT NULL REFERENCES encounters(id),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    scanner_client_id VARCHAR(128) NOT NULL,
    scanner_external_id VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    result VARCHAR(32) NOT NULL CHECK (result IN ('COMMITTED', 'REJECTED')),
    response_payload JSONB NOT NULL,
    redeemed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (scanner_client_id, idempotency_key)
);

CREATE TABLE encounter_exceptions (
    id UUID PRIMARY KEY,
    encounter_id UUID NOT NULL REFERENCES encounters(id),
    exception_phase VARCHAR(16) NOT NULL CHECK (exception_phase IN ('CHECK_IN', 'CHECK_OUT')),
    reason_code VARCHAR(64) NOT NULL CHECK (reason_code IN ('NO_SMARTPHONE', 'EMERGENCY_UNCONSCIOUS', 'QR_DEVICE_FAILURE', 'NETWORK_OUTAGE', 'PATIENT_INCAPACITATED')),
    approved_by VARCHAR(128) NOT NULL,
    actor_assurance VARCHAR(32) NOT NULL DEFAULT 'SOURCE_ASSERTED',
    evidence_ref VARCHAR(256),
    notes TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_encounter_exceptions_enc ON encounter_exceptions (encounter_id);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    aggregate_revision INT NOT NULL,
    organization_id VARCHAR(128) NOT NULL,
    correlation_id VARCHAR(128) NOT NULL,
    causation_id VARCHAR(128),
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    retry_count INT NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_encounter_outbox_pending ON outbox_events (created_at) WHERE published_at IS NULL;

CREATE TABLE inbox_events (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.2 `evidence_db` (Owner: `evidence-service`)

```sql
CREATE TABLE care_episodes (
    encounter_id UUID PRIMARY KEY, -- Shadow ref from encounter-service (no cross-DB FK)
    organization_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    encounter_status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
    presence_status VARCHAR(32) NOT NULL DEFAULT 'QR_VERIFIED',
    current_revision INT NOT NULL DEFAULT 0,
    last_acked_source_sequence INT NOT NULL DEFAULT 0,
    expected_final_sequence INT,
    sync_status VARCHAR(32) NOT NULL DEFAULT 'RECEIVING' CHECK (sync_status IN ('RECEIVING', 'SYNC_COMPLETE', 'INCOMPLETE_SYNC', 'PROVISIONAL', 'QUARANTINE_PENDING')),
    checked_out_at TIMESTAMPTZ,
    sync_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE evidence_records (
    id UUID PRIMARY KEY,
    encounter_id UUID NOT NULL REFERENCES care_episodes(encounter_id),
    organization_id UUID NOT NULL,
    source_system_id VARCHAR(64) NOT NULL,
    external_record_id VARCHAR(128) NOT NULL,
    kind VARCHAR(32) NOT NULL CHECK (kind IN ('DIAGNOSIS', 'PROCEDURE', 'MEDICATION_PRESCRIBED', 'MEDICATION_DISPENSE', 'STAGE_COMPLETION', 'DOCUMENT_FINGERPRINT')),
    current_version INT NOT NULL DEFAULT 1,
    status VARCHAR(32) NOT NULL CHECK (status IN ('ACTIVE', 'CORRECTED', 'CANCELLED', 'QUARANTINED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, source_system_id, external_record_id)
);
CREATE INDEX idx_evidence_records_enc ON evidence_records (encounter_id, status);

CREATE TABLE evidence_versions (
    id UUID PRIMARY KEY,
    evidence_id UUID NOT NULL REFERENCES evidence_records(id),
    encounter_id UUID NOT NULL REFERENCES care_episodes(encounter_id),
    version INT NOT NULL,
    source_event_id VARCHAR(128) NOT NULL,
    source_sequence INT,
    event_action VARCHAR(32) NOT NULL CHECK (event_action IN ('RECORDED', 'CORRECTED', 'CANCELLED')),
    code_system VARCHAR(64) NOT NULL,
    code VARCHAR(64) NOT NULL,
    canonical_code_system VARCHAR(64),
    canonical_code VARCHAR(64),
    mapping_status VARCHAR(32) NOT NULL DEFAULT 'MAPPED' CHECK (mapping_status IN ('MAPPED', 'UNSUPPORTED_MAPPING')),
    display_text VARCHAR(255) NOT NULL,
    quantity NUMERIC(12, 4),
    unit VARCHAR(32),
    canonical_quantity NUMERIC(12, 4),
    canonical_unit VARCHAR(32),
    stage_completion VARCHAR(32),
    source_actor_id VARCHAR(128) NOT NULL,
    source_actor_role VARCHAR(64) NOT NULL,
    actor_assurance VARCHAR(32) NOT NULL DEFAULT 'SOURCE_ASSERTED',
    change_reason TEXT,
    payload JSONB NOT NULL,
    payload_digest CHAR(64) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    source_updated_at TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (evidence_id, version),
    UNIQUE (encounter_id, source_event_id)
);
CREATE INDEX idx_evidence_versions_enc ON evidence_versions (encounter_id, version);

CREATE TABLE evidence_quarantine (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL,
    encounter_id UUID,
    source_system VARCHAR(64) NOT NULL,
    source_event_id VARCHAR(128) NOT NULL,
    external_record_id VARCHAR(128) NOT NULL,
    received_version INT NOT NULL,
    current_known_version INT,
    reason_code VARCHAR(64) NOT NULL CHECK (reason_code IN ('OUT_OF_ORDER_VERSION', 'UNKNOWN_ENCOUNTER', 'SCHEMA_MISMATCH')),
    raw_payload JSONB NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, source_system, source_event_id)
);

CREATE TABLE care_stages (
    id UUID PRIMARY KEY,
    encounter_id UUID NOT NULL REFERENCES care_episodes(encounter_id),
    stage_type VARCHAR(64) NOT NULL, -- 'ADMISSION', 'CLINICAL_EXAM', 'DIAGNOSTIC_LAB', 'PHARMACY_DISPENSE', 'DISCHARGE'
    status VARCHAR(32) NOT NULL CHECK (status IN ('STARTED', 'STAFF_COMPLETED', 'CANCELLED')),
    source_ref VARCHAR(128) NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_care_stages_enc ON care_stages (encounter_id);

CREATE TABLE summary_snapshots (
    id UUID PRIMARY KEY,
    encounter_id UUID NOT NULL REFERENCES care_episodes(encounter_id),
    evidence_revision INT NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN (' NOT_AVAILABLE', 'READY', 'INCOMPLETE_SYNC', 'PROVISIONAL', 'OUTDATED', 'RECONFIRMATION_REQUIRED')),
    items_json JSONB NOT NULL, -- Pinned list of {evidence_id, evidence_version_id, version, kind, description, quantity, unit, recorded_status}
    content_digest CHAR(64) NOT NULL,
    presented_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (encounter_id, evidence_revision)
);

CREATE TABLE verification_evidence_snapshots (
    id UUID PRIMARY KEY,
    encounter_id UUID NOT NULL REFERENCES care_episodes(encounter_id),
    evidence_revision INT NOT NULL,
    episode_sync_status VARCHAR(32) NOT NULL,
    presence_status VARCHAR(32) NOT NULL,
    patient_confirmation_status VARCHAR(32) NOT NULL,
    pinned_items_json JSONB NOT NULL,
    pinned_attestation_json JSONB,
    snapshot_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_verif_ev_snapshots_enc ON verification_evidence_snapshots (encounter_id, evidence_revision);

CREATE TABLE patient_responses (
    id UUID PRIMARY KEY,
    snapshot_id UUID NOT NULL REFERENCES summary_snapshots(id),
    encounter_id UUID NOT NULL REFERENCES care_episodes(encounter_id),
    patient_id UUID NOT NULL,
    response_type VARCHAR(32) NOT NULL CHECK (response_type IN ('CONFIRMED', 'PARTIALLY_DISPUTED', 'DISPUTED', 'DECLINED', 'NO_RESPONSE')),
    method VARCHAR(32) NOT NULL DEFAULT 'PATIENT_APP',
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    superseded_by_snapshot_id UUID REFERENCES summary_snapshots(id),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_patient_responses_enc ON patient_responses (encounter_id, submitted_at DESC);

CREATE TABLE patient_item_responses (
    id UUID PRIMARY KEY,
    response_id UUID NOT NULL REFERENCES patient_responses(id) ON DELETE CASCADE,
    evidence_id UUID NOT NULL REFERENCES evidence_records(id),
    evidence_version_id UUID NOT NULL REFERENCES evidence_versions(id),
    result VARCHAR(32) NOT NULL CHECK (result IN ('CONFIRMED', 'DISPUTED')),
    reason_code VARCHAR(64), -- 'SERVICE_NOT_RECEIVED' | 'MEDICATION_NOT_RECEIVED' | 'QUANTITY_DIFFERENT' | 'OTHER'
    note_ciphertext BYTEA,
    UNIQUE (response_id, evidence_id)
);

CREATE TABLE evidence_outbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    aggregate_revision INT NOT NULL,
    organization_id VARCHAR(128) NOT NULL,
    correlation_id VARCHAR(128) NOT NULL,
    causation_id VARCHAR(128),
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    retry_count INT NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_evidence_outbox_pending ON evidence_outbox (created_at) WHERE published_at IS NULL;

CREATE TABLE evidence_inbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.3 `verification_db` (Owner: `verification-service`)

```sql
CREATE TABLE rule_catalog_versions (
    version VARCHAR(32) PRIMARY KEY, -- e.g. 'rules-1.0.0'
    mapping_version VARCHAR(32) NOT NULL,
    configuration_json JSONB NOT NULL,
    configuration_digest CHAR(64) NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE verification_requests (
    id UUID PRIMARY KEY,
    claim_source VARCHAR(64) NOT NULL,
    claim_id VARCHAR(128) NOT NULL,
    claim_revision VARCHAR(64) NOT NULL,
    claim_relationship_type VARCHAR(32) NOT NULL DEFAULT 'ORIGINAL' CHECK (claim_relationship_type IN ('ORIGINAL', 'CORRECTION', 'REVERSAL')),
    related_claim_id VARCHAR(128),
    claim_digest CHAR(64) NOT NULL, -- Canonical SHA-256 of normalized request payload
    participant_lookup_key CHAR(64),
    patient_name_hmac CHAR(64),
    facility_namespace VARCHAR(64) NOT NULL,
    facility_code VARCHAR(64) NOT NULL,
    service_period_start TIMESTAMPTZ NOT NULL,
    service_period_end TIMESTAMPTZ NOT NULL,
    requested_by UUID NOT NULL,
    verifier_org_id UUID NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_status VARCHAR(32) NOT NULL CHECK (request_status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'STALE')),
    latest_run_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (verifier_org_id, idempotency_key)
);
CREATE INDEX idx_verif_req_claim ON verification_requests (claim_source, claim_id, created_at DESC);

CREATE TABLE verification_request_items (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES verification_requests(id) ON DELETE CASCADE,
    item_ref VARCHAR(64) NOT NULL,
    item_type VARCHAR(32) NOT NULL CHECK (item_type IN ('PROCEDURE', 'MEDICATION_DISPENSE', 'DIAGNOSIS', 'PACKAGE_TARIFF')),
    code_system VARCHAR(64) NOT NULL,
    code VARCHAR(64) NOT NULL,
    quantity NUMERIC(12, 4) NOT NULL DEFAULT 1,
    unit VARCHAR(32) NOT NULL,
    service_date_start TIMESTAMPTZ,
    service_date_end TIMESTAMPTZ,
    UNIQUE (request_id, item_ref)
);

CREATE TABLE verification_runs (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES verification_requests(id),
    run_number INT NOT NULL,
    ruleset_version VARCHAR(32) NOT NULL REFERENCES rule_catalog_versions(version),
    mapping_version VARCHAR(32) NOT NULL,
    input_snapshot_digest CHAR(64) NOT NULL,
    dependency_fingerprint CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')),
    encounter_match_status VARCHAR(32) NOT NULL CHECK (encounter_match_status IN ('UNIQUE_MATCH', 'AMBIGUOUS_MATCH', 'NO_ENCOUNTER_FOUND', 'NO_SUITABLE_ENCOUNTER', 'IDENTITY_INSUFFICIENT', 'TOO_MANY_CANDIDATES')),
    selected_encounter_id UUID,
    candidate_count INT NOT NULL DEFAULT 0,
    evaluated_candidate_count INT NOT NULL DEFAULT 0,
    identity_assurance VARCHAR(32) NOT NULL,
    evidence_reconciliation_status VARCHAR(32) NOT NULL CHECK (evidence_reconciliation_status IN ('ITEMS_CONSISTENT', 'ITEM_MISMATCH', 'PARTIAL_MATCH', 'UNSUPPORTED_MAPPING', 'EVIDENCE_INCOMPLETE')),
    matched_items_count INT NOT NULL DEFAULT 0,
    unmatched_items_count INT NOT NULL DEFAULT 0,
    duplicate_assessment_status VARCHAR(32) NOT NULL CHECK (duplicate_assessment_status IN ('NO_REUSE_FOUND_IN_JEJAKJKN_HISTORY', 'POTENTIAL_ENCOUNTER_REUSE', 'POTENTIAL_EVIDENCE_REUSE', 'KNOWN_REVISION_OR_REVERSAL', 'DUPLICATION_UNDETERMINED')),
    conflicting_claims_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    patient_confirmation_status VARCHAR(32) NOT NULL CHECK (patient_confirmation_status IN ('CONFIRMED', 'PARTIALLY_DISPUTED', 'DISPUTED', 'DECLINED', 'NO_RESPONSE', 'SNAPSHOT_OUTDATED', 'NOT_APPLICABLE')),
    review_required BOOLEAN NOT NULL DEFAULT TRUE,
    final_fraud_decision VARCHAR(32) CHECK (final_fraud_decision IS NULL), -- Enforced NULL per INV-07
    data_freshness VARCHAR(32) NOT NULL DEFAULT 'CURRENT' CHECK (data_freshness IN ('CURRENT', 'STALE_INPUT')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    UNIQUE (request_id, run_number)
);
CREATE INDEX idx_verif_runs_dep_fp ON verification_runs (dependency_fingerprint) WHERE status = 'COMPLETED' AND data_freshness = 'CURRENT';

CREATE TABLE candidate_evaluations (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES verification_runs(id) ON DELETE CASCADE,
    encounter_id UUID NOT NULL,
    evidence_snapshot_id UUID NOT NULL,
    encounter_revision INT NOT NULL,
    evidence_revision INT NOT NULL,
    identity_assurance VARCHAR(32) NOT NULL,
    presence_status VARCHAR(32) NOT NULL,
    patient_confirmation_status VARCHAR(32) NOT NULL,
    match_state VARCHAR(32) NOT NULL CHECK (match_state IN ('ELIGIBLE_COMPLETE_MATCH', 'ELIGIBLE_PARTIAL_MATCH', 'REJECTED_TIME_MISMATCH', 'REJECTED_ITEM_MISMATCH', 'REJECTED_IDENTITY_WEAK')),
    score_facts_json JSONB NOT NULL,
    reasons_json JSONB NOT NULL,
    compared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, encounter_id)
);
CREATE INDEX idx_cand_eval_enc ON candidate_evaluations (encounter_id, evidence_revision);

CREATE TABLE item_evaluations (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES verification_runs(id) ON DELETE CASCADE,
    encounter_id UUID,
    claim_item_ref VARCHAR(64) NOT NULL,
    evidence_version_ref UUID,
    evidence_id UUID,
    match_result VARCHAR(32) NOT NULL CHECK (match_result IN ('MATCHED', 'QUANTITY_MISMATCH', 'MISSING_IN_EVIDENCE', 'PRESCRIBED_ONLY_NOT_DISPENSED', 'PATIENT_DISPUTED', 'UNSUPPORTED_MAPPING', 'TIME_OUT_OF_BOUNDS')),
    claimed_quantity NUMERIC(12, 4) NOT NULL,
    allocated_evidence_quantity NUMERIC(12, 4),
    reason VARCHAR(255) NOT NULL
);
CREATE INDEX idx_item_eval_run ON item_evaluations (run_id, encounter_id);

CREATE TABLE rule_findings (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES verification_runs(id) ON DELETE CASCADE,
    rule_id VARCHAR(64) NOT NULL,
    rule_version VARCHAR(32) NOT NULL,
    severity VARCHAR(16) NOT NULL CHECK (severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH')),
    finding_code VARCHAR(64) NOT NULL,
    encounter_id UUID,
    claim_item_ref VARCHAR(64),
    evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    explanation_facts_json JSONB NOT NULL,
    limitations_text TEXT NOT NULL
);
CREATE INDEX idx_rule_findings_run ON rule_findings (run_id);

-- Intentionally NO UNIQUE(encounter_id) per INV-06 / §30
CREATE TABLE claim_encounter_associations (
    id UUID PRIMARY KEY,
    claim_source VARCHAR(64) NOT NULL,
    claim_id VARCHAR(128) NOT NULL,
    claim_revision VARCHAR(64) NOT NULL,
    encounter_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('CANDIDATE', 'MATCHED', 'AMBIGUOUS', 'SUPERSEDED', 'RETRACTED')),
    effective_from_run UUID NOT NULL REFERENCES verification_runs(id),
    superseded_by UUID REFERENCES claim_encounter_associations(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_claim_enc_assoc_enc ON claim_encounter_associations (encounter_id, status);
CREATE INDEX idx_claim_enc_assoc_claim ON claim_encounter_associations (claim_source, claim_id, status);

CREATE TABLE claim_evidence_associations (
    id UUID PRIMARY KEY,
    association_id UUID NOT NULL REFERENCES claim_encounter_associations(id) ON DELETE CASCADE,
    claim_source VARCHAR(64) NOT NULL,
    claim_id VARCHAR(128) NOT NULL,
    claim_item_ref VARCHAR(64) NOT NULL,
    evidence_ref UUID NOT NULL, -- evidence_records.id
    evidence_version_ref UUID NOT NULL, -- evidence_versions.id
    allocated_quantity NUMERIC(12, 4) NOT NULL,
    relationship VARCHAR(32) NOT NULL CHECK (relationship IN ('CONSUMED_FULL', 'CONSUMED_PARTIAL', 'CANDIDATE_LINK')),
    status VARCHAR(32) NOT NULL CHECK (status IN ('ACTIVE', 'SUPERSEDED', 'RETRACTED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_claim_ev_assoc_ev ON claim_evidence_associations (evidence_ref, status);

CREATE TABLE verification_outbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    aggregate_revision INT NOT NULL,
    organization_id VARCHAR(128) NOT NULL,
    correlation_id VARCHAR(128) NOT NULL,
    causation_id VARCHAR(128),
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    retry_count INT NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_verif_outbox_pending ON verification_outbox (created_at) WHERE published_at IS NULL;

CREATE TABLE verification_inbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.4 `review_db` (Owner: `review-service`)

```sql
CREATE TABLE review_cases (
    id UUID PRIMARY KEY,
    verification_id UUID NOT NULL,
    verification_run_id UUID NOT NULL UNIQUE,
    claim_source VARCHAR(64) NOT NULL,
    claim_id VARCHAR(128) NOT NULL,
    owner_org UUID NOT NULL,
    assigned_to UUID,
    state VARCHAR(32) NOT NULL CHECK (state IN ('OPEN', 'IN_REVIEW', 'NEEDS_MORE_EVIDENCE', 'COMPLETED')),
    is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    review_package_json JSONB NOT NULL, -- Materialized snapshot from verification-service
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_review_cases_org_state ON review_cases (owner_org, state, opened_at DESC);

CREATE TABLE review_decisions (
    id UUID PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES review_cases(id),
    actor_id UUID NOT NULL,
    actor_role VARCHAR(64) NOT NULL,
    decision VARCHAR(32) NOT NULL CHECK (decision IN ('NO_ACTION', 'REQUEST_CLARIFICATION', 'ESCALATE', 'CLOSE_REVIEW')),
    reason TEXT NOT NULL CHECK (char_length(trim(reason)) >= 10),
    evidence_digest CHAR(64) NOT NULL,
    supersedes_decision_id UUID REFERENCES review_decisions(id),
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_review_decisions_case ON review_decisions (case_id, created_at DESC);

CREATE TABLE narrative_artifacts (
    id UUID PRIMARY KEY,
    assessment_ref UUID NOT NULL UNIQUE, -- verification_run_id
    method VARCHAR(32) NOT NULL CHECK (method IN ('template', 'model')),
    model_info VARCHAR(128) NOT NULL,
    input_digest CHAR(64) NOT NULL,
    narrative_json JSONB NOT NULL, -- {summary_id, factual_bullets_id, verification_questions_id, limitation_notice_id}
    validation_status VARCHAR(32) NOT NULL CHECK (validation_status IN ('VALIDATED', 'FALLBACK_USED')),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE access_audit (
    id UUID PRIMARY KEY,
    actor_id UUID NOT NULL,
    actor_org_id UUID NOT NULL,
    purpose VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_ref VARCHAR(128) NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    outcome VARCHAR(32) NOT NULL CHECK (outcome IN ('ALLOWED', 'DENIED')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_access_audit_resource ON access_audit (resource_type, resource_ref, occurred_at DESC);

CREATE TABLE audit_chain (
    sequence_no BIGSERIAL PRIMARY KEY,
    partition_key VARCHAR(64) NOT NULL, -- organization_id or 'SYSTEM'
    record_id UUID NOT NULL UNIQUE,
    record_type VARCHAR(64) NOT NULL,   -- 'REVIEW_DECISION' | 'SENSITIVE_READ' | 'CASE_STATE_CHANGE'
    payload_digest CHAR(64) NOT NULL,
    previous_hash CHAR(64) NOT NULL,
    record_hash CHAR(64) NOT NULL,      -- SHA-256(partition_key || ':' || previous_hash || ':' || record_id || ':' || payload_digest || ':' || created_at_iso)
    signature_ref VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_chain_partition ON audit_chain (partition_key, sequence_no DESC);

CREATE TABLE review_outbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    aggregate_revision INT NOT NULL,
    organization_id VARCHAR(128) NOT NULL,
    correlation_id VARCHAR(128) NOT NULL,
    causation_id VARCHAR(128),
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    retry_count INT NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE review_inbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.5 `simrs_a_db` & `simrs_b_db` (Owned by Simulator Backends)

```sql
CREATE TABLE simrs_visits (
    id UUID PRIMARY KEY,
    external_visit_ref VARCHAR(128) NOT NULL UNIQUE,
    participant_number VARCHAR(64) NOT NULL,
    patient_name VARCHAR(160) NOT NULL,
    facility_code VARCHAR(64) NOT NULL,
    jejakjkn_encounter_id UUID,
    visit_status VARCHAR(32) NOT NULL DEFAULT 'REGISTERED', -- 'REGISTERED' | 'CHECKED_IN' | 'IN_CARE' | 'CHECKED_OUT'
    last_sequence INT NOT NULL DEFAULT 0,
    sync_complete_sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE simrs_clinical_records (
    id UUID PRIMARY KEY,
    visit_id UUID NOT NULL REFERENCES simrs_visits(id),
    external_record_id VARCHAR(128) NOT NULL,
    record_version INT NOT NULL DEFAULT 1,
    category VARCHAR(32) NOT NULL, -- SIMRS-A: 'DIAGNOSIS'|'PROCEDURE'|'MEDICATION_DISPENSED'|'STAGE'; SIMRS-B uses local field names mapped by adapter
    local_code VARCHAR(64) NOT NULL,
    local_display VARCHAR(255) NOT NULL,
    qty NUMERIC(12, 4),
    uom VARCHAR(32),
    staff_id VARCHAR(64) NOT NULL,
    staff_role VARCHAR(64) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (visit_id, external_record_id, record_version)
);

CREATE TABLE simrs_sync_outbox (
    id UUID PRIMARY KEY,
    visit_id UUID NOT NULL REFERENCES simrs_visits(id),
    source_event_id VARCHAR(128) NOT NULL UNIQUE,
    source_sequence INT NOT NULL,
    target_endpoint VARCHAR(128) NOT NULL,
    canonical_payload JSONB NOT NULL,
    delivery_status VARCHAR(32) NOT NULL DEFAULT 'PENDING' CHECK (delivery_status IN ('PENDING', 'DELIVERED', 'REJECTED', 'FAILED_RETRYABLE')),
    http_status INT,
    error_detail TEXT,
    attempts INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 4. REDIS_KEYSPACE & QR_2PHASE_PROTOCOL

### 4.1 Token Format & Keyspace

- **QR Token Format:** Compact JWS (`RS256` or `EdDSA` with `kid` header) over payload:
  ```json
  {
    "iss": "jejakjkn-encounter-service",
    "aud": "jejakjkn-qr-redemption",
    "jti": "<128-bit-csprng-nonce>",
    "sub": "<internal-patient-uuid>",
    "pur": "CHECK_IN | CHECK_OUT",
    "enc": "<encounter-uuid-if-CHECK_OUT-else-null>",
    "fch": "<facility-external-code-hint-or-null>",
    "iat": 1792458000,
    "exp": 1792458060
  }
  ```
- **Redis Keys (`Encounter Service` only):**
  - `qr:nonce:{sha256(jti)}` -> Hash:
    - `state`: `ISSUED` | `RESERVED` | `COMMITTED`
    - `patient_id`: UUID
    - `purpose`: `CHECK_IN` | `CHECK_OUT`
    - `encounter_id`: UUID (pre-allocated on reserve for `CHECK_IN`, or bound for `CHECK_OUT`)
    - `reserved_by_scanner`: `{client_id}:{idempotency_key}`
    - `facility_hint`: string
    - TTL: `60s` on issue; extended to `300s` on `RESERVED`/`COMMITTED` for idempotent replay window.
  - `rl:qr_scan:{client_id}` -> Sliding window counter (limit: 30 req / 10s).
  - `rl:verifier_search:{actor_id}` -> Sliding window counter (limit: 60 req / 60s).

### 4.2 Atomic Lua Script for QR Redemption (`RESERVE_OR_REPLAY`)

```lua
-- KEYS[1] = "qr:nonce:" .. nonce_digest
-- ARGV[1] = scanner_reservation_key (client_id .. ":" .. idempotency_key)
-- ARGV[2] = expected_purpose ("CHECK_IN" or "CHECK_OUT")
-- ARGV[3] = preallocated_encounter_id (for CHECK_IN)
-- ARGV[4] = facility_external_code

local exists = redis.call("EXISTS", KEYS[1])
if exists == 0 then
    return {"EXPIRED_OR_UNKNOWN"}
end

local state = redis.call("HGET", KEYS[1], "state")
local purpose = redis.call("HGET", KEYS[1], "purpose")
local fch = redis.call("HGET", KEYS[1], "facility_hint")
local reserved_by = redis.call("HGET", KEYS[1], "reserved_by_scanner")

if purpose ~= ARGV[2] then
    return {"WRONG_PURPOSE", purpose}
end

if fch ~= "" and fch ~= ARGV[4] then
    return {"FACILITY_MISMATCH", fch}
end

if state == "ISSUED" then
    redis.call("HSET", KEYS[1], "state", "RESERVED", "reserved_by_scanner", ARGV[1])
    if ARGV[2] == "CHECK_IN" then
        redis.call("HSET", KEYS[1], "encounter_id", ARGV[3])
    end
    redis.call("EXPIRE", KEYS[1], 300)
    return {"RESERVED", redis.call("HGET", KEYS[1], "patient_id"), redis.call("HGET", KEYS[1], "encounter_id")}
end

if reserved_by == ARGV[1] then
    return {"IDEMPOTENT_RETRY", state, redis.call("HGET", KEYS[1], "patient_id"), redis.call("HGET", KEYS[1], "encounter_id")}
end

return {"ALREADY_CONSUMED_BY_OTHER"}
```

**Post-Lua DB Step:**
1. If Lua returns `RESERVED` or `IDEMPOTENT_RETRY`:
   - Begin `encounter_db` transaction.
   - Check `qr_redemption_receipts` by `nonce_digest`. If committed row exists and matches `(scanner_client_id, idempotency_key)`, return stored `response_payload` (`200 OK` or `201 Created`).
   - Otherwise insert/update `encounters`, insert `qr_redemption_receipts`, insert `outbox_events`, `COMMIT`.
   - Update Redis `HSET qr:nonce:{digest} state COMMITTED`.
2. If DB transaction fails after `RESERVED`, the nonce remains bound to `reserved_by_scanner` (`client_id:idempotency_key`):
   - Another scanner/facility gets `409 QR_ALREADY_CONSUMED`.
   - The SAME scanner retrying with the same `Idempotency-Key` receives `IDEMPOTENT_RETRY` from Lua and completes the DB commit cleanly!
3. If Redis is unreachable -> **Fail closed (`503 SERVICE_UNAVAILABLE`)**; never create unverified encounter silently.

---

## 5. RABBITMQ_TOPOLOGY & EVENT_CONTRACTS

```yaml
exchange:
  name: "jejakjkn.domain.v1"
  type: "topic"
  durable: true

queues:
  - name: "evidence.encounter-events.q"
    bindings: ["encounter.opened.v1", "encounter.checked_out.v1", "encounter.exception_recorded.v1"]
    dlq: "evidence.encounter-events.dlq"
  - name: "verification.domain-events.q"
    bindings: ["encounter.exception_recorded.v1", "evidence.recorded.v1", "evidence.corrected.v1", "evidence.cancelled.v1", "patient.confirmation_recorded.v1", "verification.requested.v1"]
    dlq: "verification.domain-events.dlq"
  - name: "review.verification-events.q"
    bindings: ["verification.completed.v1", "verification.stale.v1", "evidence.corrected.v1"]
    dlq: "review.verification-events.dlq"
  - name: "narrative.verification-events.q"
    bindings: ["verification.completed.v1"]
    dlq: "narrative.verification-events.dlq"
```

---

## 6. HTTP_API_CONTRACTS (`/api/v1` & `/internal/v1`)

### 6.1 Error Format (`application/problem+json` — RFC 9457)
```json
{
  "type": "https://jejakjkn.local/problems/qr-already-consumed",
  "title": "QR Token Already Consumed",
  "status": 409,
  "detail": "The single-use QR token has already been redeemed.",
  "instance": "/api/v1/integrations/qr/check-in",
  "error_code": "QR_ALREADY_CONSUMED",
  "request_id": "req-0192a8f0...",
  "correlation_id": "corr-0192a8f0..."
}
```

### 6.2 Route Matrix

| Service | Method | Path | Auth Role / Scope | Success Status | Idempotency / Version Header |
|---|---|---|---|---|---|
| `encounter` | `POST` | `/api/v1/patient/qr-tokens` | `patient` | `201 Created` | — |
| `encounter` | `GET` | `/api/v1/patient/encounters` | `patient` | `200 OK` | Cursor pagination |
| `encounter` | `GET` | `/api/v1/patient/encounters/{id}` | `patient` | `200 OK` | No live clinical stages! |
| `evidence` | `GET` | `/api/v1/patient/encounters/{id}/checkout-summary` | `patient` | `200 OK` / `409` if not checked out | — |
| `evidence` | `POST` | `/api/v1/patient/checkout-summaries/{snapshot_id}/responses` | `patient` | `201 Created` | `Idempotency-Key` |
| `evidence` | `GET` | `/api/v1/patient/checkout-summaries/{snapshot_id}/response` | `patient` | `200 OK` | — |
| `encounter` | `POST` | `/api/v1/integrations/qr/check-in` | `encounter:checkin` | `201 Created` | `Idempotency-Key` |
| `encounter` | `POST` | `/api/v1/integrations/qr/check-out` | `encounter:checkout` | `200 OK` | `Idempotency-Key` |
| `encounter` | `POST` | `/api/v1/integrations/encounters/{id}/exceptions` | `encounter:exception` | `201 Created` | `Idempotency-Key` |
| `evidence` | `POST` | `/api/v1/integrations/encounters/{id}/events` | `evidence:write` | `201 Created` | `source_event_id` in body |
| `evidence` | `POST` | `/api/v1/integrations/encounters/{id}/corrections` | `evidence:correct` | `201 Created` | `source_event_id` + `record_version` |
| `evidence` | `POST` | `/api/v1/integrations/encounters/{id}/cancellations` | `evidence:cancel` | `200 OK` | `source_event_id` + `record_version` |
| `evidence` | `POST` | `/api/v1/integrations/encounters/{id}/sync-complete` | `evidence:write` | `200 OK` | `last_source_sequence` |
| `evidence` | `GET` | `/api/v1/integrations/encounters/{id}/ingestion-status` | `evidence:readstatus` | `200 OK` | — |
| `verification` | `POST` | `/api/v1/verifications` | `verification:create` | `202 Accepted` | `Idempotency-Key` |
| `verification` | `GET` | `/api/v1/verifications/{id}` | `verification:read` | `200 OK` | — |
| `verification` | `GET` | `/api/v1/verifications/{id}/candidates` | `verification:read` | `200 OK` | — |
| `verification` | `GET` | `/api/v1/verifications/{id}/findings` | `verification:read` | `200 OK` | — |
| `verification` | `POST` | `/api/v1/verifications/{id}/re-evaluate` | `verification:recheck` | `202 Accepted` | `Idempotency-Key` |
| `verification` | `GET` | `/api/v1/verifications/history` | `verification:read` | `200 OK` | `?claim_source=&claim_id=` |
| `review` | `GET` | `/api/v1/review-cases` | `review:read` | `200 OK` | Cursor pagination |
| `review` | `GET` | `/api/v1/review-cases/{id}` | `review:read` | `200 OK` | Writes `access_audit` |
| `review` | `POST` | `/api/v1/review-cases/{id}/decisions` | `review:decide` | `201 Created` | `Idempotency-Key` |
| `encounter` | `GET` | `/internal/v1/encounters/{id}/eligibility` | `internal_service` | `200 OK` | — |
| `encounter` | `POST` | `/internal/v1/encounters/search-candidates` | `internal_service` | `200 OK` | Safety limit = `10` |
| `evidence` | `POST` | `/internal/v1/encounters/{id}/evidence-snapshots` | `internal_service` | `201 Created` | Pins immutable snapshot |
| `evidence` | `GET` | `/internal/v1/evidence-snapshots/{id}` | `internal_service` | `200 OK` | — |
| `verification` | `GET` | `/internal/v1/verifications/{run_id}/review-package` | `internal_service` | `200 OK` | — |
| `review` | `POST` | `/internal/v1/narratives` | `internal_service` | `201 Created` | From `narrative-worker` |

---

## 7. RECONCILIATION_ALGORITHMS & DETERMINISTIC_RULES (`rules-1.0.0`)

### 7.1 Candidate Search & Episode Match Classification

```python
SAFETY_CANDIDATE_LIMIT = 10

def classify_episode_match(
    identity_assurance: str,
    truncated_by_limit: bool,
    candidates: list[CandidateEvaluation],
) -> tuple[str, UUID | None]:
    if truncated_by_limit:
        return ("TOO_MANY_CANDIDATES", None)
    if identity_assurance == "INSUFFICIENT":
        return ("IDENTITY_INSUFFICIENT", None)
    if not candidates:
        return ("NO_ENCOUNTER_FOUND", None)
    if identity_assurance == "LOW_IDENTITY_ASSURANCE":
        # Name-only match NEVER produces UNIQUE_MATCH automatically (§17.5, §21, VM-06)
        return ("IDENTITY_INSUFFICIENT", None)

    complete_matches = [c for c in candidates if c.match_state == "ELIGIBLE_COMPLETE_MATCH"]
    partial_matches = [c for c in candidates if c.match_state == "ELIGIBLE_PARTIAL_MATCH"]

    # CRITICAL INV-05: Never filter out or deprioritize candidates with existing claim associations!
    if len(complete_matches) == 1:
        return ("UNIQUE_MATCH", complete_matches[0].encounter_id)
    if len(complete_matches) > 1:
        return ("AMBIGUOUS_MATCH", None)
    if len(partial_matches) == 1:
        return ("UNIQUE_MATCH", partial_matches[0].encounter_id)
    if len(partial_matches) > 1:
        return ("AMBIGUOUS_MATCH", None)
    return ("NO_SUITABLE_ENCOUNTER", None)
```

### 7.2 Item-Level Bipartite Matching & Capacity Allocation (`reconcile_items`)

1. Filter active evidence versions from `pinned_items_json` (`status != 'CANCELLED'`).
2. Separate `MEDICATION_PRESCRIBED` from `MEDICATION_DISPENSE`:
   - If a claimed `MEDICATION_DISPENSE` item only matches a `MEDICATION_PRESCRIBED` record and no `MEDICATION_DISPENSE` record exists, classify item as `PRESCRIBED_ONLY_NOT_DISPENSED` -> triggers `R003_ITEM_MISSING`.
3. Map `(code_system, code, unit)` -> `(canonical_code_system, canonical_code, canonical_unit, conversion_factor)`.
   - If mapping is missing or `item_type == 'PACKAGE_TARIFF'` without explicit decomposition rule -> classify item as `UNSUPPORTED_MAPPING` -> triggers `R014_MAPPING_UNSUPPORTED`.
4. For **indivisible items (`PROCEDURE`)**:
   - Build bipartite graph $G = (C_{proc}, E_{proc}, \text{Edges})$ where $(c, e) \in \text{Edges}$ iff `c.canonical_code == e.canonical_code` and `e.occurred_at` within claim `service_period` tolerance.
   - Solve Maximum Cardinality Bipartite Matching (Hopcroft-Karp / augmenting path) with deterministic tie-breaking (by `occurred_at ASC, evidence_id ASC`).
   - Each $e \in E_{proc}$ can be matched to **at most 1** $c \in C_{proc}$ (`VM-10`).
5. For **quantitative items (`MEDICATION_DISPENSE`)**:
   - Group active `MEDICATION_DISPENSE` evidence by `canonical_code` ordered by `occurred_at ASC, evidence_id ASC`.
   - Maintain remaining available quantity `rem[e.id] = e.canonical_quantity`.
   - For each claimed medication item $c$: allocate greedily from compatible $e$ with `rem[e.id] > 0`.
   - If `allocated == c.canonical_quantity` -> `MATCHED`.
   - If `0 < allocated < c.canonical_quantity` -> `QUANTITY_MISMATCH` (`R004_QUANTITY_MISMATCH`).
   - If `allocated == 0` -> `MISSING_IN_EVIDENCE` (`R003_ITEM_MISSING`).

### 7.3 Deterministic Rule Catalog (`rules-1.0.0`)

| Rule ID | Severity | Finding Code | Trigger Predicate |
|---|---|---|---|
| `R001_NO_ENCOUNTER` | `HIGH` | `ENCOUNTER_NOT_FOUND` | `encounter_match_status == 'NO_ENCOUNTER_FOUND'` |
| `R002_IDENTITY_WEAK` | `MEDIUM` | `IDENTITY_ASSURANCE_LOW` | `identity_assurance in ('LOW_IDENTITY_ASSURANCE', 'INSUFFICIENT')` |
| `R003_ITEM_MISSING` | `HIGH` | `CLAIM_ITEM_UNSUPPORTED_BY_EVIDENCE` | Any `item_evaluation.match_result in ('MISSING_IN_EVIDENCE', 'PRESCRIBED_ONLY_NOT_DISPENSED')` |
| `R004_QUANTITY_MISMATCH` | `HIGH` | `CLAIMED_QUANTITY_EXCEEDS_EVIDENCE` | Any `item_evaluation.match_result == 'QUANTITY_MISMATCH'` |
| `R005_PATIENT_DISPUTE` | `HIGH` | `PATIENT_DISPUTED_CLAIMED_ITEM` | Any matched evidence item has patient item response `DISPUTED` |
| `R006_TIME_INCONSISTENCY` | `MEDIUM` | `ACTIVITY_TIMESTAMP_OUT_OF_BOUNDS` | Evidence `occurred_at` outside encounter `[started_at - 15m, ended_at + 2h]` or claim `service_period` |
| `R007_ENCOUNTER_REUSE` | `HIGH` | `POTENTIAL_ENCOUNTER_REUSE` | Active `claim_encounter_associations` exists for same `encounter_id` with different `(claim_source, claim_id)` and not a valid `CORRECTION`/`REVERSAL` of that claim |
| `R008_EVIDENCE_REUSE` | `HIGH` | `POTENTIAL_EVIDENCE_REUSE` | Active `claim_evidence_associations` exists for same `evidence_ref` where cumulative allocated quantity across non-superseded claims > evidence quantity |
| `R009_DUPLICATE_EXTERNAL_CLAIM` | `INFO` | `IDENTICAL_CLAIM_REVERIFIED` | Prior run exists for same `(claim_source, claim_id)` with identical `claim_digest` |
| `R010_EVIDENCE_LATE_OR_STALE` | `MEDIUM` | `EVIDENCE_MODIFIED_AFTER_CHECKOUT_OR_RUN` | Evidence `recorded_at > encounter.ended_at` or `data_freshness == 'STALE_INPUT'` |
| `R011_DOCUMENT_FINGERPRINT` | `MEDIUM` | `IDENTICAL_DOCUMENT_FINGERPRINT_CROSS_PATIENT` | `DOCUMENT_FINGERPRINT` digest matches another encounter of a different `patient_id` (excluding allowlisted template hashes) |
| `R012_CHECKOUT_EXCEPTION` | `MEDIUM` | `PRESENCE_EXCEPTION_RECORDED` | Candidate encounter `presence_status != 'QR_VERIFIED'` or status == `'CLOSED_WITH_EXCEPTION'` |
| `R013_PATIENT_NO_RESPONSE` | `LOW` | `PATIENT_ATTESTATION_UNAVAILABLE` | `patient_confirmation_status in ('NO_RESPONSE', 'DECLINED')` |
| `R014_MAPPING_UNSUPPORTED` | `MEDIUM` | `CODE_OR_UNIT_MAPPING_UNSUPPORTED` | Any `item_evaluation.match_result == 'UNSUPPORTED_MAPPING'` |

### 7.4 Concurrency & Advisory Lock Finalization Protocol (§31)

```python
async def finalize_verification_run(session: AsyncSession, run_draft: RunDraft) -> VerificationRun:
    # 1. Sort all candidate encounter UUIDs deterministically to prevent deadlocks
    sorted_enc_ids = sorted({c.encounter_id for c in run_draft.candidates})
    for enc_id in sorted_enc_ids:
        lock_key = int.from_bytes(hashlib.sha256(enc_id.bytes).digest()[:8], "big", signed=True)
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

    # 2. Re-read active claim_encounter_associations and claim_evidence_associations inside the lock
    active_enc_assocs = await repo.get_active_encounter_associations(session, sorted_enc_ids)
    active_ev_assocs = await repo.get_active_evidence_associations(session, run_draft.used_evidence_ids)

    # 3. Re-evaluate duplicate assessment & R007/R008 findings against latest committed state
    duplicate_result, r007_r008_findings = evaluate_reuse_and_duplicates(
        request=run_draft.request,
        episode_match=run_draft.episode_match,
        item_evaluations=run_draft.item_evaluations,
        active_enc_assocs=active_enc_assocs,
        active_ev_assocs=active_ev_assocs,
    )

    # 4. Persist verification_runs, candidate_evaluations, item_evaluations, rule_findings,
    #    claim_encounter_associations, claim_evidence_associations, and verification_outbox atomically
    run = await repo.persist_run_atomic(session, run_draft, duplicate_result, r007_r008_findings)
    await session.commit()
    return run
```

---

## 8. CANONICAL_CODE_MAPPINGS (SYNTHETIC MVP CATALOG)

| Domain | Canonical System | Canonical Code | Display | SIMRS-A `(system, code, uom)` | SIMRS-B `(system, code, uom)` | Conversion |
|---|---|---|---|---|---|---|
| Procedure | `JJKN-PROC-V1` | `PROC-CONSULT-GP` | Konsultasi Dokter Umum | `(SIMRS-A-PROC, POLI-UMUM-01, visit)` | `(RSB-TINDAKAN, RJ-DOK-001, kali)` | `1.0 -> service` |
| Procedure | `JJKN-PROC-V1` | `PROC-EXAM-EYE` | Pemeriksaan Mata Dasar | `(SIMRS-A-PROC, EXAM-EYE, service)` | `(RSB-TINDAKAN, MATA-01, tindakan)` | `1.0 -> service` |
| Procedure | `JJKN-PROC-V1` | `PROC-SLIT-LAMP` | Biomikroskopi Slit Lamp | `(SIMRS-A-PROC, EYE-SLIT-02, service)` | `(RSB-TINDAKAN, MATA-SLIT, tindakan)` | `1.0 -> service` |
| Procedure | `JJKN-PROC-V1` | `PROC-ECG` | Elektrokardiografi (EKG) | `(SIMRS-A-PROC, CARD-ECG-01, service)` | `(RSB-TINDAKAN, JANTUNG-EKG, tindakan)` | `1.0 -> service` |
| Procedure | `JJKN-PROC-V1` | `PROC-CBC` | Darah Lengkap (CBC) | `(SIMRS-A-LAB, LAB-CBC-01, test)` | `(RSB-LAB, DL-001, pemeriksaan)` | `1.0 -> service` |
| Medication | `JJKN-MED-V1` | `MED-PARACETAMOL-500` | Paracetamol 500 mg Tablet | `(SIMRS-A-MED, MED-001, tablet)` | `(RSB-OBAT, OB-PCT500, tab)` | `1.0 -> tablet` |
| Medication | `JJKN-MED-V1` | `MED-PARACETAMOL-500` | Paracetamol 500 mg (Strip=10) | `(SIMRS-A-MED, MED-001-STRIP, strip)` | `(RSB-OBAT, OB-PCT500-STR, strip10)` | `10.0 -> tablet` |
| Medication | `JJKN-MED-V1` | `MED-AMOXICILLIN-500` | Amoxicillin 500 mg Kaplet | `(SIMRS-A-MED, MED-002, tablet)` | `(RSB-OBAT, OB-AMX500, kaplet)` | `1.0 -> tablet` |
| Medication | `JJKN-MED-V1` | `MED-LEVOFLOXACIN-ED` | Levofloxacin Eye Drops 5 mL | `(SIMRS-A-MED, MED-003, bottle)` | `(RSB-OBAT, OB-LFX-ED, fls)` | `1.0 -> bottle` |
| Diagnosis | `JJKN-DIAG-V1` | `DIAG-H10-9` | Conjunctivitis, unspecified | `(ICD10-DEMO, H10.9, code)` | `(ICD10-RSB, H10.9, diag)` | `1.0 -> code` |
| Diagnosis | `JJKN-DIAG-V1` | `DIAG-J06-9` | ISPA Akut | `(ICD10-DEMO, J06.9, code)` | `(ICD10-RSB, J06.9, diag)` | `1.0 -> code` |

---

## 9. SPRINT_EXECUTION_GATES

- **S0:** Audit & ADR baseline, contracts frozen (`contracts/openapi/*.yaml`, `contracts/events/v1/*.json`).
- **S1:** Compose stack up, 4 Postgres DBs + 2 SIMRS DBs isolated, Keycloak realm provisioned, shared `libs/*` tested.
- **S2:** `encounter-service` QR issue/redeem (`QR-01..QR-10`), `patient-web` QR IN/OUT (no live stage).
- **S3:** `simrs-a-backend` + `adapters/simrs-a` + `evidence-service` ingestion, versioning, quarantine (`EV-01..EV-05`).
- **S4:** Checkout summary snapshots, `sync-complete` watermark, patient confirmation/dispute (`EV-06..EV-11`).
- **S5:** `verification-service` candidate search, bipartite item matching, rules `R001..R006, R010, R012..R014` (`VM-01..VM-10, VM-18..19, VM-22..23`).
- **S6:** Claim-encounter & claim-evidence associations, dependency fingerprint cache, advisory locks, `R007..R009, R011` (`VM-11..VM-17, VM-20..21`).
- **S7:** `review-service`, `verifier-web`, `narrative-worker` (template + optional LLM guard), `audit_chain` (`SEC-01..SEC-10`).
- **S8:** `simrs-b-backend` + `adapters/simrs-b`, E2E Playwright, concurrency/fault injection, backup/restore (`SEC-11..SEC-12`).
