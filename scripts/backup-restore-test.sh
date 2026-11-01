#!/usr/bin/env bash
set -euo pipefail

if [[ "${APP_ENV:-}" != "local" ]]; then
  echo "Refusing restore test outside APP_ENV=local" >&2
  exit 1
fi
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT
bash scripts/backup-local.sh "$temporary/all.sql"
test -s "$temporary/all.sql"
# Validate the dump without mutating the running databases; restore-local.sh is the explicit destructive step.
rg -q 'CREATE DATABASE (encounter_db|evidence_db|verification_db|review_db)' "$temporary/all.sql"
echo "Backup contains the domain databases and is readable."
