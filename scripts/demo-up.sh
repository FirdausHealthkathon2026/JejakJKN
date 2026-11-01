#!/usr/bin/env bash
# One command to start the whole demo: secrets, containers, schemas, and seed data.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

trap 'echo "Startup gagal. Lihat pesan di atas; konfigurasi dan data tetap disimpan. Ulangi: bash scripts.sh" >&2' ERR

echo "[1/6] Menyiapkan konfigurasi otomatis..."
bash scripts/bootstrap-dev.sh
echo "[2/6] Membangun aplikasi (build pertama memerlukan internet)..."
docker compose build
echo "[3/6] Menjalankan database dan login..."
docker compose up -d --wait postgres redis rabbitmq keycloak

echo "[4/6] Menerapkan migrasi database..."
for service in encounter-api evidence-api verification-api review-api simrs-a-api simrs-b-api; do
  docker compose run --rm --no-deps "$service" alembic upgrade head
done
echo "[5/6] Mengisi data demo..."
docker compose run --rm --no-deps encounter-api python -m app.seed

docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U encounter_app -d encounter_db < scripts/generated/seed_encounter_1000.sql > /dev/null
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U evidence_app -d evidence_db < scripts/generated/seed_evidence_1000.sql > /dev/null

echo "[6/6] Menjalankan dan memeriksa seluruh aplikasi..."
docker compose up -d --wait
docker compose exec -T encounter-api python - < scripts/check-demo-ready.py

echo "JejakJKN siap dipakai."
echo "Pasien      http://localhost:5173  (patient01 / synthetic-patient-01)"
echo "SIMRS A     http://localhost:5174"
echo "Verifikator http://localhost:5175"
echo "SIMRS B     http://localhost:5176"
