# SIMRS_ADAPTER_SPEC :: v1.0

## 1. ADAPTER_ARCHITECTURE (`adapters/common-sdk`, `adapters/simrs-a`, `adapters/simrs-b`)

1. **Source Persistence First:** Both `simrs-a-backend` and `simrs-b-backend` write clinical activity to their local database (`simrs_a_db` / `simrs_b_db`) and append a row to `simrs_sync_outbox` with a monotonic per-visit `source_sequence`.
2. **Machine Identity:** Adapters authenticate to `api-gateway` using OAuth2 `client_credentials` (`simrs-a-adapter` bound to `HOSP-DEMO-001`, `simrs-b-adapter` bound to `HOSP-DEMO-002`).
3. **Schema Translation:**
   - **SIMRS-A input:** canonical-like `event_type`, `code_system`, `code`, `quantity`, and `unit` fields.
   - **SIMRS-B input:** local Indonesian `jenis`, `kode`, `jumlah`, `satuan`, `petugas`, and `id_rekam` fields.
   - Both translate into the canonical `/api/v1/integrations/encounters/{id}/events` contract while preserving `source_event_id`, `external_record_id`, `record_version`, and `source_sequence`.
4. **End-of-Visit Watermark:** When discharge is completed in SIMRS, the adapter calls `POST /api/v1/integrations/encounters/{id}/sync-complete` with `last_source_sequence` so `evidence-service` can transition the summary snapshot from `INCOMPLETE_SYNC` to `READY`.

## 2. Onboarding a new facility

1. Allocate a synthetic organization UUID and facility code; never reuse another tenant's identity.
2. Register a confidential Keycloak service client with only the scanner/evidence scopes it needs and hard-coded `org_id`/`org_type` claims.
3. Implement an explicit source-code table. Unknown codes or units must become `UNSUPPORTED_MAPPING`; do not use fuzzy display-name matching.
4. Persist source data and an outbox transactionally, with monotonically increasing sequence numbers per encounter.
5. Send a final watermark after all visit records are queued. Corrections after that point must create new evidence revisions.
6. Run tenant-isolation, replay, out-of-order, outage, and end-to-end tests before enabling the adapter.

SIMRS-B demonstrates this contract through `/api/pindai/masuk`, `/api/kunjungan/{id}/catatan`, and `/api/kunjungan/{id}/sinkronisasi-selesai`.
