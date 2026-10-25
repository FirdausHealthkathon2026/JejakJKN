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
make up               # Start the Gate 0/1 Docker Compose stack
make migrate          # Run the Encounter Service Gate 1 migration
make seed             # Seed 3 organizations, 2 sources, and 20 synthetic patients
make test-unit        # Run implemented Gate 1 unit and redaction tests
make test-contract    # Validate OpenAPI 3.1 + JSON Schema event contracts
make test-integration # Run live Gate 1 QR and database-isolation tests
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
- **Planned:** Evidence/checkout summaries (Gate 2–3), claim verification (Gate 4–5), human review (Gate 6), second adapter and hardening (Gate 7).

Run `make bootstrap install up migrate seed`, then open Patient Web on `http://localhost:5173` and SIMRS-A scanner on `http://localhost:5174`. The public API defaults to `http://localhost:18080` and can be changed with `API_GATEWAY_PORT`. The synthetic browser account is `patient01` / `synthetic-patient-01`.
