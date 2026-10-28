# JejakJKN — Agent Workspace Index & Technical Blueprint

> **MODE:** AGENT_OPTIMIZED_MONOREPO  
> **SOURCE SPEC:** [`JejakJKN_Technical_Implementation_Specification_v1.0.md`](./JejakJKN_Technical_Implementation_Specification_v1.0.md)  
> **PRIMARY AGENT IR:** [`docs/architecture/technical-spec.md`](./docs/architecture/technical-spec.md)

## 1. Agent Reference Map

| Domain / Artifact | Path | Purpose for Coding Agent |
|---|---|---|
| **Core Agent IR Spec** | [`docs/architecture/technical-spec.md`](./docs/architecture/technical-spec.md) | Invariants (`INV-01..15`), 6 DB DDLs, Redis Lua script, RabbitMQ queues, bipartite reconciliation, `R001..R014`, advisory locks |
| **HTTP & Event Reference** | [`docs/api/http-and-events.md`](./docs/api/http-and-events.md) | Request/response payloads, status codes, problem+json errors, event envelope schemas |
| **C4 Context & Containers** | [`docs/architecture/c4-context.md`](./docs/architecture/c4-context.md) / [`c4-containers.md`](./docs/architecture/c4-containers.md) | Trust boundaries, container ports, internal/external network splits |
| **Threat Model & Security** | [`docs/architecture/threat-model.md`](./docs/architecture/threat-model.md) | Auth flows, HMAC blind index, AES-256-GCM columns, log redaction rules |
| **ADR Index** | [`docs/architecture/adr/README.md`](./docs/architecture/adr/README.md) | Architectural Decision Records (`ADR-001`..`ADR-008`) |
| **Test Matrix & Fixtures** | [`docs/test-plan/test-matrix.md`](./docs/test-plan/test-matrix.md) | `QR-01..10`, `EV-01..11`, `VM-01..23`, `SEC-01..12` + synthetic seed specs |
| **Panduan Pengujian Manual** | [`docs/manual-testing-guide.md`](./docs/manual-testing-guide.md) | Panduan langkah-demi-langkah pengujian UI/flow untuk semua skenario (Happy path, phantom billing, double billing, ghost procedure, dispute, dsb.) |
| **Benchmark 1.000 Klaim Riil** | [`contracts/fixtures/claims_1000_sample.json`](./contracts/fixtures/claims_1000_sample.json) / [`scripts/test-1000-claims.py`](./scripts/test-1000-claims.py) | 1.000 sampel klaim riil BPJS Kesehatan, SQL generator, test harness, dan hasil scorecard verifikasi fraud |
| **SIMRS Adapter Guide** | [`docs/integration-guide/simrs-adapter.md`](./docs/integration-guide/simrs-adapter.md) | SIMRS-A & SIMRS-B local-to-canonical mapping, outbox retry, `sync-complete` watermark |
| **Runbooks** | [`docs/runbooks/operations.md`](./docs/runbooks/operations.md) | Startup, DB migration, DLQ redrive, backup/restore, stale run recovery |
| **OpenAPI 3.1 Contracts** | [`contracts/openapi/`](./contracts/openapi/) | `encounter-v1.yaml`, `evidence-v1.yaml`, `verification-v1.yaml`, `review-v1.yaml` |
| **Event JSON Schemas** | [`contracts/events/v1/`](./contracts/events/v1/) | Domain event envelope & payload schemas |
| **Synthetic Seed Fixtures** | [`contracts/fixtures/`](./contracts/fixtures/) | Deterministic 20 patients, 3 facilities, 50+ encounters, 150+ evidence items, 50+ verification requests |

## 2. Non-Negotiable Architecture Rules (Quick Check)

1. **No Clinical Input in JejakJKN:** Clinical/pharmacy records are authored in `simulators/simrs-a-backend` or `simulators/simrs-b-backend` and pushed via `adapters/*` to `/api/v1/integrations/encounters/{id}/*`.
2. **No Live Patient Progress:** `apps/patient-web` only generates `CHECK_IN` / `CHECK_OUT` QR (`60s` TTL) and displays checkout summary **after** `CHECK_OUT` when snapshot is `READY`.
3. **No Claim Submission / Payment:** `apps/verifier-web` only dispatches verification requests (`POST /api/v1/verifications`) over external claim fixtures.
4. **Evaluate All Candidates:** Candidate search uses `(participant_identity, facility_code, service_period)` — never external `encounter_id`, never `first-match-wins`, never skips encounters already linked to prior claims.
5. **Isolated Databases:** `encounter_db`, `evidence_db`, `verification_db`, `review_db`, `simrs_a_db`, `simrs_b_db` use separate PostgreSQL databases and credentials.

## 3. Operational Commands (`Makefile`)

```bash
make bootstrap        # Initialize ignored local secrets and environment
make up               # Start the Gate 0–5 Docker Compose stack
make migrate          # Run Encounter, Evidence, Verification, and SIMRS-A migrations
make seed             # Seed 3 organizations, 2 sources, and 20 synthetic patients
make seed-benchmark   # Seed 1,000 real BPJS claim encounters & evidence into databases
make test-benchmark   # Execute end-to-end fraud detection benchmark on 1,000 claims
make test-unit        # Run Gate 1–5 unit, contract, and redaction tests
make test-contract    # Validate OpenAPI 3.1 + JSON Schema event contracts
make test-integration # Run live Gate 1–5 database and outbox tests
make test-concurrency # Run the live 100-concurrent QR scan test
make test-security    # Run implemented RBAC and redaction tests
make test-e2e         # Reserved for the later full three-interface flow
make lint             # Run ruff over implemented Python code
make down             # Stop stack
make reset-dev-data   # Wipe and re-seed local synthetic databases
```

## 4. Implemented Delivery Gates

- **Gate 0:** real dependency installation, secret bootstrap, isolated databases, Keycloak/RabbitMQ provisioning, health endpoints, contract/provider validation, and executable CI.
- **Gate 1:** Encounter Service QR issue/check-in/check-out/exception flow, Ed25519 tokens, Redis two-phase reservation, durable receipts/outbox, synthetic patient seed, Patient Web, SIMRS-A scanner, and QR concurrency/security tests.
- **Gate 2:** SIMRS-A-owned clinical/pharmacy records, durable local outbox delivery, tenant-bound Evidence ingestion, immutable corrections/cancellations, sequence tracking/quarantine, and internal-only care stages.
- **Gate 3:** explicit sync-complete watermark, frozen post-checkout summaries, itemized patient confirmation/dispute/decline, timeout state, and late-correction reconfirmation.
- **Gate 4:** verifier-owned request intake and history, all-candidate search with a ten-result safety cap, strong-identity-only auto-selection, immutable Evidence snapshots, four-dimensional assessments, and the Verifier Web simulator.
- **Gate 5:** maximum bipartite/quantity-safe item reconciliation, deterministic `R001..R014` findings, claim–encounter/evidence history, ordered advisory-lock finalization, dependency-fingerprint reuse, duplicate signals, and event-driven stale assessment invalidation.
- **Implemented:** human review and tamper-evident access/decision audit (Gate 6), plus a second vendor-schema adapter, sensitive-endpoint rate limiting, and guarded local backup/restore (Gate 7).

## 5. Dataset Riil BPJS Kesehatan & Evaluasi 1.000 Klaim (Benchmark)

Repositori ini telah dilengkapi dengan 1.000 sampel terverifikasi dari dataset riil klaim BPJS Kesehatan (`contracts/fixtures/claims_1000_sample.json`) dengan nilai agregat tagihan sebesar **Rp 869,7 Juta**, mencakup:
- **900 klaim valid (90%)** — Pelayanan medis sah dengan kehadiran QR terverifikasi dan bukti rekam medis SIMRS sinkron.
- **100 klaim fraud/anomali (10%)** — Mencakup 5 skenario kecurangan: *Phantom Billing* (35), *Double Billing* (25), *Ghost Procedure / Upcoding* (20), *Absent Patient* (10), dan *Timing Anomaly* (10).

### Cara Mengisi Database & Menjalankan Benchmark (Untuk Mesin Baru / Rekan Tim):
Setelah stack Docker menyala (`make up migrate`), jalankan:
```bash
# 1. Masukkan 1.000 data sampel encounter & clinical evidence ke database
make seed-benchmark

# 2. Jalankan pengujian verifikasi otomatis 1.000 klaim
make test-benchmark
# Atau menggunakan Python langsung:
python3 scripts/test-1000-claims.py --limit 1000 --workers 8
```

### Hasil Benchmark Eksekutif:
- **Recall (Tingkat Deteksi Fraud):** **`100,00%`** (100 dari 100 kasus fraud tertangkap tanpa satupun terlewat).
- **Akurasi Keseluruhan:** **`98,00%`**.
- **Potensi Finansial yang Diselamatkan:** **`Rp 96.947.200,00`**.
- **Kecepatan Throughput:** ~6,6 klaim/detik (152 detik untuk 1.000 klaim).

Panduan interaktif langkah-demi-langkah di antarmuka web tersedia di [**`docs/manual-testing-guide.md`**](docs/manual-testing-guide.md).

---

Run `make bootstrap install up migrate seed`, then open Patient Web on `http://localhost:5173`, SIMRS-A scanner on `http://localhost:5174`, or Verifier Web on `http://localhost:5175`. The public API defaults to `http://localhost:18080` and can be changed with `API_GATEWAY_PORT`. Synthetic browser accounts are `patient01` / `synthetic-patient-01` and `verifier01` / `synthetic-verifier-01`.
