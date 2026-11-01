#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_name="${COMPOSE_PROJECT_NAME:-jejakjkn}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker belum terpasang. Pasang dan jalankan Docker Desktop, lalu ulangi bash scripts.sh." >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker/Compose belum siap. Jalankan Docker Desktop atau Docker Engine, lalu ulangi bash scripts.sh." >&2
  exit 1
fi

has_database=0
if docker volume inspect "${project_name}_postgres-data" >/dev/null 2>&1; then
  has_database=1
fi

docker_project_dir="$project_dir"
case "${OSTYPE:-}" in
  msys*|cygwin*)
    docker_project_dir="$(cygpath -m "$project_dir")"
    export MSYS_NO_PATHCONV=1
    ;;
esac

# Use Node's built-in crypto inside Docker; no host Node, Python, or OpenSSL needed.
docker run --rm \
  --mount "type=bind,source=$docker_project_dir,target=/workspace" \
  --mount "type=volume,source=${project_name}_bootstrap-data,target=/state" \
  --workdir /workspace \
  -e "LOCAL_UID=$(id -u)" -e "LOCAL_GID=$(id -g)" -e "HAS_DATABASE=$has_database" \
  node:22-alpine node scripts/bootstrap-dev.mjs
