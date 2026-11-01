# HTTP_AND_EVENTS_CONTRACT_SPEC :: v1.0

## 1. HTTP_HEADERS_AND_CONVENTIONS

```yaml
required_request_headers:
  Authorization: "Bearer <jwt>"
  X-Request-Id: "<uuid-v4-or-generated-by-gateway>"
  X-Correlation-Id: "<uuid-v4>"
  Idempotency-Key: "<uuid-v4> (mandatory on POST check-in, check-out, exceptions, responses, verifications, re-evaluate, decisions)"
  If-Match: "\"<revision>\" (optional/conditional version check)"

standard_status_codes:
  200: "Synchronous read or idempotent state transition completed"
  201: "Resource or immutable version created synchronously"
  202: "Asynchronous verification job accepted and queued"
  400: "Malformed syntax, unknown query param, invalid cursor"
  401: "Missing, expired, or invalid JWT signature/issuer/audience"
  403: "Scope missing, tenant organization mismatch, or cross-patient access"
  404: "Resource not found or hidden by tenant isolation"
  409: "QR_ALREADY_CONSUMED | CHECKOUT_SUMMARY_NOT_READY | IDEMPOTENCY_KEY_PAYLOAD_MISMATCH | REVISION_CONFLICT"
  410: "QR_TOKEN_EXPIRED"
  412: "Precondition Failed (If-Match revision mismatch)"
  422: "Domain validation error (e.g. wrong QR purpose, invalid period)"
  429: "Rate limit exceeded (includes Retry-After header)"
  503: "Dependency unavailable (e.g. Redis down during QR redemption -> fail closed)"
```

## 2. PUBLIC_API_PAYLOAD_SPEC (`/api/v1`)

### 2.1 Patient Endpoints (`encounter-service` & `evidence-service`)

```yaml
POST /api/v1/patient/qr-tokens:
  request:
    purpose: "CHECK_IN | CHECK_OUT"
    encounter_id: "UUID | null (required when purpose == CHECK_OUT)"
    facility_hint: "string | null (e.g. HOSP-DEMO-001)"
  response_201:
    token: "string (compact JWS)"
    purpose: "CHECK_IN | CHECK_OUT"
    expires_at: "ISO-8601 UTC"
    ttl_seconds: 60

GET /api/v1/patient/encounters:
  query: { cursor: "string?", limit: "int (1..50, default 20)" }
  response_200:
    items:
      - encounter_id: "UUID"
        facility_display_name: "string"
        service_type: "OUTPATIENT | INPATIENT | EMERGENCY"
        started_at: "ISO-8601 UTC"
        ended_at: "ISO-8601 UTC | null"
        check_in_successful: true
        check_out_successful: "boolean"
        confirmation_status: "NOT_AVAILABLE | READY | INCOMPLETE_SYNC | PROVISIONAL | CONFIRMED | PARTIALLY_DISPUTED | DECLINED | NO_RESPONSE | RECONFIRMATION_REQUIRED"
    next_cursor: "string | null"

GET /api/v1/patient/encounters/{id}/checkout-summary:
  precondition: "encounter.status == CHECKED_OUT and summary_snapshot.status in (READY, PROVISIONAL, RECONFIRMATION_REQUIRED)"
  response_200:
    snapshot_id: "UUID"
    encounter_id: "UUID"
    status: "READY | PROVISIONAL | RECONFIRMATION_REQUIRED"
    evidence_revision: "int"
    presented_at: "ISO-8601 UTC"
    items:
      - evidence_id: "UUID"
        evidence_version_id: "UUID"
        kind: "PROCEDURE | MEDICATION_DISPENSE | DIAGNOSIS"
        description: "string"
        quantity: "number | null"
        unit: "string | null"
        recorded_status: "STAFF_COMPLETED"

POST /api/v1/patient/checkout-summaries/{snapshot_id}/responses:
  request:
    overall_response: "CONFIRMED | PARTIALLY_DISPUTED | DISPUTED | DECLINED"
    items:
      - evidence_id: "UUID"
        response: "CONFIRMED | DISPUTED"
        reason: "SERVICE_NOT_RECEIVED | MEDICATION_NOT_RECEIVED | QUANTITY_DIFFERENT | OTHER | null"
        note: "string | null"
  response_201:
    response_id: "UUID"
    snapshot_id: "UUID"
    overall_response: "string"
    submitted_at: "ISO-8601 UTC"
```

### 2.2 SIMRS / Adapter Integration Endpoints (`encounter-service` & `evidence-service`)

```yaml
POST /api/v1/integrations/qr/check-in:
  scope: "encounter:checkin"
  request:
    qr_token: "string"
    facility_external_code: "string"
    scanner_external_id: "string"
    external_visit_reference: "string | null"
  response_201:
    encounter_id: "UUID"
    check_in_status: "QR_VERIFIED"
    encounter_status: "OPEN"
    created_at: "ISO-8601 UTC"

POST /api/v1/integrations/qr/check-out:
  scope: "encounter:checkout"
  request:
    qr_token: "string"
    facility_external_code: "string"
    scanner_external_id: "string"
  response_200:
    encounter_id: "UUID"
    encounter_status: "CHECKED_OUT"
    checked_out_at: "ISO-8601 UTC"

POST /api/v1/integrations/encounters/{id}/events:
  scope: "evidence:write"
  request:
    source_event_id: "string"
    source_system: "string"
    source_sequence: "int | null"
    external_record_id: "string"
    event_type: "DIAGNOSIS | PROCEDURE | MEDICATION_PRESCRIBED | MEDICATION_DISPENSED | STAGE_COMPLETION | DOCUMENT_FINGERPRINT"
    record_version: 1
    occurred_at: "ISO-8601"
    actor:
      external_id: "string"
      role: "string"
    content:
      code_system: "string"
      code: "string"
      display: "string"
      quantity: "number | null"
      unit: "string | null"
      document_fingerprint_sha256: "string | null"
    stage_completion: "STARTED | STAFF_COMPLETED | null"
  response_201:
    evidence_id: "UUID"
    evidence_version_id: "UUID"
    record_version: 1
    encounter_evidence_revision: "int"
    mapping_status: "MAPPED | UNSUPPORTED_MAPPING"

POST /api/v1/integrations/encounters/{id}/corrections:
  scope: "evidence:correct"
  request:
    source_event_id: "string"
    source_system: "string"
    source_sequence: "int | null"
    external_record_id: "string"
    record_version: "int (>= 2)"
    occurred_at: "ISO-8601"
    source_updated_at: "ISO-8601"
    change_reason: "string"
    actor: { external_id: "string", role: "string" }
    content: { code_system: "string", code: "string", display: "string", quantity: "number | null", unit: "string | null" }
  response_201:
    evidence_id: "UUID"
    evidence_version_id: "UUID"
    record_version: "int"
    status: "CORRECTED | QUARANTINED"

POST /api/v1/integrations/encounters/{id}/cancellations:
  scope: "evidence:cancel"
  request:
    source_event_id: "string"
    source_system: "string"
    source_sequence: "int | null"
    external_record_id: "string"
    record_version: "int (>= 2)"
    source_updated_at: "ISO-8601"
    cancel_reason: "string"
    actor: { external_id: "string", role: "string" }
  response_200:
    evidence_id: "UUID"
    record_version: "int"
    status: "CANCELLED"

POST /api/v1/integrations/encounters/{id}/sync-complete:
  scope: "evidence:write"
  request:
    source_system: "string"
    last_source_sequence: "int"
    marked_complete_at: "ISO-8601"
  response_200:
    encounter_id: "UUID"
    sync_status: "SYNC_COMPLETE | INCOMPLETE_SYNC"
    snapshot_id: "UUID | null"
```

### 2.3 Verifier & Review Endpoints (`verification-service` & `review-service`)

```yaml
POST /api/v1/verifications:
  scope: "verification:create"
  request:
    claim_source: "string"
    claim_id: "string"
    claim_revision: "string"
    claim_relationship:
      type: "ORIGINAL | CORRECTION | REVERSAL"
      related_claim_id: "string | null"
    patient:
      participant_number: "string | null"
      name: "string | null"
    facility:
      code_namespace: "string"
      code: "string"
    service_period:
      start: "ISO-8601"
      end: "ISO-8601"
    items:
      - item_ref: "string"
        kind: "PROCEDURE | MEDICATION_DISPENSE | DIAGNOSIS | PACKAGE_TARIFF"
        code_system: "string"
        code: "string"
        quantity: "number"
        unit: "string"
  response_202:
    verification_id: "UUID"
    run_id: "UUID"
    status: "QUEUED | COMPLETED"
    status_url: "string"

GET /api/v1/verifications/{id}:
  scope: "verification:read"
  response_200:
    verification_id: "UUID"
    run_id: "UUID"
    status: "QUEUED | RUNNING | COMPLETED | FAILED"
    encounter_match:
      status: "UNIQUE_MATCH | AMBIGUOUS_MATCH | NO_ENCOUNTER_FOUND | NO_SUITABLE_ENCOUNTER | IDENTITY_INSUFFICIENT | TOO_MANY_CANDIDATES"
      selected_encounter_id: "UUID | null"
      candidate_count: "int"
      evaluated_candidate_count: "int"
      identity_assurance: "VERIFIED_PARTICIPANT_ID | VERIFIED_EXTERNAL_ID | LOW_IDENTITY_ASSURANCE | INSUFFICIENT"
    evidence_reconciliation:
      status: "ITEMS_CONSISTENT | ITEM_MISMATCH | PARTIAL_MATCH | UNSUPPORTED_MAPPING | EVIDENCE_INCOMPLETE"
      matched_items: "int"
      unmatched_items: "int"
    duplicate_assessment:
      status: "NO_REUSE_FOUND_IN_JEJAKJKN_HISTORY | POTENTIAL_ENCOUNTER_REUSE | POTENTIAL_EVIDENCE_REUSE | KNOWN_REVISION_OR_REVERSAL | DUPLICATION_UNDETERMINED"
      scope_notice: "Tidak ditemukan penggunaan ulang dalam histori pemeriksaan JejakJKN (bukan jaminan nasional di luar histori JejakJKN)."
      conflicting_claims: "list[str]"
    patient_confirmation: "CONFIRMED | PARTIALLY_DISPUTED | DISPUTED | DECLINED | NO_RESPONSE | SNAPSHOT_OUTDATED | NOT_APPLICABLE"
    review_required: "boolean"
    final_fraud_decision: null
    ruleset_version: "rules-1.0.0"
    data_freshness: "CURRENT | STALE_INPUT"
    findings_url: "string"

POST /api/v1/review-cases/{id}/decisions:
  scope: "review:decide"
  request:
    decision: "NO_ACTION | REQUEST_CLARIFICATION | ESCALATE | CLOSE_REVIEW"
    reason: "string (min 10 chars)"
    supersedes_decision_id: "UUID | null"
  response_201:
    decision_id: "UUID"
    case_id: "UUID"
    state: "OPEN | IN_REVIEW | NEEDS_MORE_EVIDENCE | COMPLETED"
    audit_record_hash: "string"
```
