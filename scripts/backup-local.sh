#!/usr/bin/env bash
set -euo pipefail

if [[ "${APP_ENV:-}" != "local" ]]; then
  echo "Refusing backup outside APP_ENV=local" >&2
  exit 1
fi
destination="${1:-backups/jejakjkn-$(date -u +%Y%m%dT%H%M%SZ).sql}"
mkdir -p "$(dirname "$destination")"
docker compose exec -T postgres pg_dumpall -U postgres > "$destination"
echo "Backup written to $destination"
