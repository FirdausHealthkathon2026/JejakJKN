# Staging deployment and rollback

## Preconditions

- Synthetic data only; no real participant or clinical records.
- `make lint test-unit test-contract` and the live acceptance targets pass.
- `make restore-drill` passes.
- `make release` produces a signed manifest and `make verify-release MANIFEST=...` succeeds.

## Deploy

1. Record `git rev-parse HEAD` and retain the signed artifact from `releases/`.
2. Run `docker compose build --pull` and `make migrate` before switching traffic.
3. Run `docker compose up -d --wait`; verify `/health`, `/ready`, `/metrics`, Prometheus targets, Grafana, and Tempo.
4. Execute `make test-e2e test-security test-concurrency` against staging.
5. Record the release manifest, migration revisions, operator, and timestamp.

## Roll back

1. Stop new traffic at the gateway.
2. Restore the prior signed artifact and verify its signature.
3. Do not downgrade a database unless the migration's downgrade was tested against a restored backup. Prefer forward fixes for append-only evidence/audit data.
4. Start the prior images, run readiness and smoke tests, then reopen traffic.
5. Preserve failed-release logs, traces, outbox rows, and the database backup for incident review.

No step authorizes deployment with real data; that requires institutional, privacy, legal, and security approval.
