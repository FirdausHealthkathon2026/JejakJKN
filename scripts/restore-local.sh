#!/usr/bin/env bash
set -euo pipefail

if [[ "${APP_ENV:-}" != "local" ]]; then
  echo "Refusing restore outside APP_ENV=local" >&2
  exit 1
fi
source_file="${1:?usage: restore-local.sh BACKUP.sql}"
if [[ ! -f "$source_file" ]]; then
  echo "Backup not found: $source_file" >&2
  exit 1
fi
docker compose exec -T postgres psql -U postgres < "$source_file"
echo "Restore completed from $source_file"
