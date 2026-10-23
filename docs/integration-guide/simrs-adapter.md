# SIMRS_ADAPTER_SPEC :: v1.0

## 1. ADAPTER_ARCHITECTURE (`adapters/common-sdk`, `adapters/simrs-a`, `adapters/simrs-b`)

1. **Source Persistence First:** Both `simrs-a-backend` and `simrs-b-backend` write clinical activity to their local database (`simrs_a_db` / `simrs_b_db`) and append a row to `simrs_sync_outbox` with a monotonic per-visit `source_sequence`.
2. **Machine Identity:** Adapters authenticate to `api-gateway` using OAuth2 `client_credentials` (`simrs-a-adapter` bound to `HOSP-DEMO-001`, `simrs-b-adapter` bound to `HOSP-DEMO-002`).
3. **Schema Translation:**
   - **SIMRS-APayload:** `{ visit_no, kd_tindakan, nm_tindakan, jml, satuan, petugas_id, jabatan, waktu_pelayanan }`
   - **SIMRS-BPayload:** `{ episode_ref, item_code, item_label, quantity_val, uom_code, practitioner_code, practitioner_type, timestamp_wib }`
   - Both translate into the canonical `/api/v1/integrations/encounters/{id}/events` contract while preserving `source_event_id`, `external_record_id`, `record_version`, and `source_sequence`.
4. **End-of-Visit Watermark:** When discharge is completed in SIMRS, the adapter calls `POST /api/v1/integrations/encounters/{id}/sync-complete` with `last_source_sequence` so `evidence-service` can transition the summary snapshot from `INCOMPLETE_SYNC` to `READY`.
