#!/usr/bin/env bash
set -euo pipefail

if [[ "${APP_ENV:-}" != "local" ]]; then
  echo "Refusing restore drill outside APP_ENV=local" >&2
  exit 1
fi
temporary="$(mktemp -d)"
cleanup() {
  docker compose --profile restore-drill rm -sf restore-postgres >/dev/null 2>&1 || true
  rm -rf "$temporary"
}
trap cleanup EXIT

bash scripts/backup-local.sh "$temporary/all.sql"
docker compose --profile restore-drill up -d --wait restore-postgres
docker compose --profile restore-drill exec -T restore-postgres psql -v ON_ERROR_STOP=1 -U postgres < "$temporary/all.sql" >/dev/null

for database in encounter_db evidence_db verification_db review_db simrs_a_db simrs_b_db; do
  docker compose --profile restore-drill exec -T restore-postgres psql -v ON_ERROR_STOP=1 -U postgres -d "$database" -tAc "SELECT 1" >/dev/null
done

violations="$(docker compose --profile restore-drill exec -T restore-postgres psql -U postgres -d review_db -tAc "SELECT count(*) FROM (SELECT previous_hash, lag(record_hash, 1, repeat('0',64)) OVER (PARTITION BY partition_key ORDER BY sequence_no) expected FROM audit_chain) chain WHERE previous_hash <> expected")"
digests="$(docker compose --profile restore-drill exec -T restore-postgres psql -U postgres -d verification_db -tAc "SELECT count(*) FROM verification_runs WHERE status='COMPLETED' AND length(input_snapshot_digest)<>64")"
test "$violations" = "0"
test "$digests" = "0"
echo "Restore drill passed: isolated databases readable, audit links continuous, verification digests valid."
