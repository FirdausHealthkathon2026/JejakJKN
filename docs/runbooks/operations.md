# OPERATIONS_RUNBOOK_SPEC :: v1.0

```yaml
runbooks:
  RB-01_REDIS_OUTAGE_DURING_QR:
    symptom: "POST /api/v1/integrations/qr/check-in returns 503 SERVICE_UNAVAILABLE"
    invariant: "Fail closed for QR redemption; never create unverified encounter silently."
    mitigation: "Authorized SIMRS staff uses POST /api/v1/integrations/encounters/{id}/exceptions with reason_code=NETWORK_OUTAGE or QR_DEVICE_FAILURE; encounter presence_status becomes EXCEPTION_DOCUMENTED."

  RB-02_LATE_OR_OUT_OF_ORDER_SIMRS_DELIVERY:
    symptom: "SIMRS delivers medication/procedure after QR_OUT or sends record_version=3 before v2"
    behavior:
      - "Late post-checkout delivery increments care_episodes.current_revision, keeps old summary_snapshot immutable, creates new snapshot, marks prior confirmed response RECONFIRMATION_REQUIRED, and emits evidence.recorded.v1 -> marks dependent verification_runs STALE_INPUT."
      - "Out-of-order version (v3 before v2) inserts into evidence_quarantine with reason_code=OUT_OF_ORDER_VERSION without overwriting v1."

  RB-03_DLQ_REDRIVE:
    queues: ["evidence.encounter-events.dlq", "verification.domain-events.dlq", "review.verification-events.dlq", "narrative.verification-events.dlq"]
    procedure: "Inspect dead-lettered message headers (x-death, event_id, correlation_id), fix upstream schema/state, and replay into primary queue; inbox_events table guarantees idempotency."

  RB-04_BACKUP_AND_RESTORE:
    script: "scripts/backup-restore-test.sh"
    target_dbs: ["encounter_db", "evidence_db", "verification_db", "review_db"]
    verification: "Verify audit_chain SHA-256 continuity and verification_runs snapshot digest integrity post-restore."
```
