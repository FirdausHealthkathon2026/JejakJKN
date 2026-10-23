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
make bootstrap        # Initialize dev secrets & Keycloak realm fixtures
make up               # Start full Docker Compose stack
make migrate          # Run Alembic migrations across all 4 core + 2 simulator DBs
make seed             # Populate deterministic synthetic dataset (seed=2026)
make test-unit        # Run unit tests across services, libs, adapters, and web apps
make test-contract    # Validate OpenAPI 3.1 + JSON Schema event contracts
make test-integration # Run DB/Redis/RabbitMQ integration tests
make test-concurrency # Run QR 100-concurrent scan & parallel claim verification race tests
make test-security    # Run RBAC, tenant isolation, IDOR, and log redaction tests
make test-e2e         # Run Playwright end-to-end tests across all 3 simulators
make lint             # Run ruff, mypy, eslint, and tsc
make down             # Stop stack
make reset-dev-data   # Wipe and re-seed local synthetic databases
```