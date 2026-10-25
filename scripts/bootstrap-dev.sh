#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
secrets_dir="$project_dir/.secrets"
env_file="$project_dir/.env"

mkdir -p "$secrets_dir"
chmod 700 "$secrets_dir"

if [[ ! -f "$secrets_dir/qr-signing-private.pem" ]]; then
  openssl genpkey -algorithm ED25519 -out "$secrets_dir/qr-signing-private.pem"
  openssl pkey -in "$secrets_dir/qr-signing-private.pem" -pubout -out "$secrets_dir/qr-signing-public.pem"
  chmod 600 "$secrets_dir/qr-signing-private.pem" "$secrets_dir/qr-signing-public.pem"
fi

if [[ ! -f "$env_file" ]]; then
  cp "$project_dir/.env.example" "$env_file"
  postgres_password="$(openssl rand -hex 24)"
  encounter_db_password="$(openssl rand -hex 24)"
  evidence_db_password="$(openssl rand -hex 24)"
  verification_db_password="$(openssl rand -hex 24)"
  review_db_password="$(openssl rand -hex 24)"
  simrs_a_db_password="$(openssl rand -hex 24)"
  simrs_b_db_password="$(openssl rand -hex 24)"
  keycloak_admin_password="$(openssl rand -hex 24)"
  keycloak_db_password="$(openssl rand -hex 24)"
  participant_key="$(openssl rand -hex 32)"
  field_key="$(openssl rand -hex 32)"
  simrs_a_secret="$(openssl rand -hex 24)"
  simrs_b_secret="$(openssl rand -hex 24)"
  test_patient_secret="$(openssl rand -hex 24)"
  test_patient_2_secret="$(openssl rand -hex 24)"
  sed -i \
    -e "s/POSTGRES_SUPERUSER_PASSWORD=change-me-local-only/POSTGRES_SUPERUSER_PASSWORD=$postgres_password/" \
    -e "s/ENCOUNTER_DB_PASSWORD=change-me-local-only/ENCOUNTER_DB_PASSWORD=$encounter_db_password/" \
    -e "s/EVIDENCE_DB_PASSWORD=change-me-local-only/EVIDENCE_DB_PASSWORD=$evidence_db_password/" \
    -e "s/VERIFICATION_DB_PASSWORD=change-me-local-only/VERIFICATION_DB_PASSWORD=$verification_db_password/" \
    -e "s/REVIEW_DB_PASSWORD=change-me-local-only/REVIEW_DB_PASSWORD=$review_db_password/" \
    -e "s/SIMRS_A_DB_PASSWORD=change-me-local-only/SIMRS_A_DB_PASSWORD=$simrs_a_db_password/" \
    -e "s/SIMRS_B_DB_PASSWORD=change-me-local-only/SIMRS_B_DB_PASSWORD=$simrs_b_db_password/" \
    -e "s/KEYCLOAK_ADMIN_PASSWORD=change-me-local-only/KEYCLOAK_ADMIN_PASSWORD=$keycloak_admin_password/" \
    -e "s/KEYCLOAK_DB_PASSWORD=change-me-local-only/KEYCLOAK_DB_PASSWORD=$keycloak_db_password/" \
    -e "s/SIMRS_A_CLIENT_SECRET=change-me-local-only/SIMRS_A_CLIENT_SECRET=$simrs_a_secret/" \
    -e "s/SIMRS_B_CLIENT_SECRET=change-me-local-only/SIMRS_B_CLIENT_SECRET=$simrs_b_secret/" \
    -e "s/TEST_PATIENT_CLIENT_SECRET=change-me-local-only/TEST_PATIENT_CLIENT_SECRET=$test_patient_secret/" \
    -e "s/TEST_PATIENT_2_CLIENT_SECRET=change-me-local-only/TEST_PATIENT_2_CLIENT_SECRET=$test_patient_2_secret/" \
    -e "s#ENCOUNTER_DATABASE_URL=postgresql+asyncpg://encounter_app:change-me-local-only@postgres:5432/encounter_db#ENCOUNTER_DATABASE_URL=postgresql+asyncpg://encounter_app:$encounter_db_password@postgres:5432/encounter_db#" \
    -e "s/PARTICIPANT_LOOKUP_HMAC_KEY=replace-with-64-hex-characters/PARTICIPANT_LOOKUP_HMAC_KEY=$participant_key/" \
    -e "s/FIELD_ENCRYPTION_MASTER_KEY=replace-with-64-hex-characters/FIELD_ENCRYPTION_MASTER_KEY=$field_key/" \
    "$env_file"
  chmod 600 "$env_file"
fi

echo "[bootstrap-dev] Local-only secrets are ready in .secrets/ and .env"
