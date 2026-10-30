#!/usr/bin/env bash
# One command to start the whole demo: secrets, containers, schemas, and seed data.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

bash scripts/bootstrap-dev.sh
docker compose build
docker compose up -d --wait postgres redis rabbitmq keycloak

for service in encounter-api evidence-api verification-api review-api simrs-a-api simrs-b-api; do
  docker compose run --rm "$service" alembic upgrade head
done
docker compose run --rm encounter-api python -m app.seed
docker compose up -d --wait

docker compose exec -T postgres psql -q -U encounter_app -d encounter_db < scripts/generated/seed_encounter_1000.sql > /dev/null
docker compose exec -T postgres psql -q -U evidence_app -d evidence_db < scripts/generated/seed_evidence_1000.sql > /dev/null

echo "Pasien      http://localhost:5173  (patient01 / synthetic-patient-01)"
echo "SIMRS A     http://localhost:5174"
echo "Verifikator http://localhost:5175"
echo "SIMRS B     http://localhost:5176"
