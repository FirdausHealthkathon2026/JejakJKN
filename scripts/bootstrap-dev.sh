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

if [[ ! -f "$secrets_dir/release-signing-private.pem" ]]; then
  openssl genpkey -algorithm ED25519 -out "$secrets_dir/release-signing-private.pem"
  openssl pkey -in "$secrets_dir/release-signing-private.pem" -pubout -out "$secrets_dir/release-signing-public.pem"
  chmod 600 "$secrets_dir/release-signing-private.pem" "$secrets_dir/release-signing-public.pem"
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
  bpjs_claim_db_password="$(openssl rand -hex 24)"
  keycloak_admin_password="$(openssl rand -hex 24)"
  keycloak_db_password="$(openssl rand -hex 24)"
  # Must match scripts/generate-synthetic-bpjs-sample.py: the 1,000-claim seed is precomputed with these.
  participant_key="0d70fe6c79ac335cbf6894b35f18c20a470000094d55f8a85ee7b937359baa8c"
  field_key="76e615c41c9303747950656b727151dc65aced28b91aa891429beca78a695b7c"
  simrs_a_secret="$(openssl rand -hex 24)"
  simrs_b_secret="$(openssl rand -hex 24)"
  test_patient_secret="$(openssl rand -hex 24)"
  test_patient_2_secret="$(openssl rand -hex 24)"
  verification_service_secret="$(openssl rand -hex 24)"
  test_verifier_secret="$(openssl rand -hex 24)"
  review_service_secret="$(openssl rand -hex 24)"
  sed -i \
    -e "s/POSTGRES_SUPERUSER_PASSWORD=change-me-local-only/POSTGRES_SUPERUSER_PASSWORD=$postgres_password/" \
    -e "s/ENCOUNTER_DB_PASSWORD=change-me-local-only/ENCOUNTER_DB_PASSWORD=$encounter_db_password/" \
    -e "s/EVIDENCE_DB_PASSWORD=change-me-local-only/EVIDENCE_DB_PASSWORD=$evidence_db_password/" \
    -e "s/VERIFICATION_DB_PASSWORD=change-me-local-only/VERIFICATION_DB_PASSWORD=$verification_db_password/" \
    -e "s/REVIEW_DB_PASSWORD=change-me-local-only/REVIEW_DB_PASSWORD=$review_db_password/" \
    -e "s/SIMRS_A_DB_PASSWORD=change-me-local-only/SIMRS_A_DB_PASSWORD=$simrs_a_db_password/" \
    -e "s/SIMRS_B_DB_PASSWORD=change-me-local-only/SIMRS_B_DB_PASSWORD=$simrs_b_db_password/" \
    -e "s/BPJS_CLAIM_DB_PASSWORD=change-me-local-only/BPJS_CLAIM_DB_PASSWORD=$bpjs_claim_db_password/" \
    -e "s/KEYCLOAK_ADMIN_PASSWORD=change-me-local-only/KEYCLOAK_ADMIN_PASSWORD=$keycloak_admin_password/" \
    -e "s/KEYCLOAK_DB_PASSWORD=change-me-local-only/KEYCLOAK_DB_PASSWORD=$keycloak_db_password/" \
    -e "s/SIMRS_A_CLIENT_SECRET=change-me-local-only/SIMRS_A_CLIENT_SECRET=$simrs_a_secret/" \
    -e "s/SIMRS_B_CLIENT_SECRET=change-me-local-only/SIMRS_B_CLIENT_SECRET=$simrs_b_secret/" \
    -e "s/TEST_PATIENT_CLIENT_SECRET=change-me-local-only/TEST_PATIENT_CLIENT_SECRET=$test_patient_secret/" \
    -e "s/TEST_PATIENT_2_CLIENT_SECRET=change-me-local-only/TEST_PATIENT_2_CLIENT_SECRET=$test_patient_2_secret/" \
    -e "s/VERIFICATION_SERVICE_CLIENT_SECRET=change-me-local-only/VERIFICATION_SERVICE_CLIENT_SECRET=$verification_service_secret/" \
    -e "s/TEST_VERIFIER_CLIENT_SECRET=change-me-local-only/TEST_VERIFIER_CLIENT_SECRET=$test_verifier_secret/" \
    -e "s/REVIEW_SERVICE_CLIENT_SECRET=change-me-local-only/REVIEW_SERVICE_CLIENT_SECRET=$review_service_secret/" \
    -e "s#ENCOUNTER_DATABASE_URL=postgresql+asyncpg://encounter_app:change-me-local-only@postgres:5432/encounter_db#ENCOUNTER_DATABASE_URL=postgresql+asyncpg://encounter_app:$encounter_db_password@postgres:5432/encounter_db#" \
    -e "s#EVIDENCE_DATABASE_URL=postgresql+asyncpg://evidence_app:change-me-local-only@postgres:5432/evidence_db#EVIDENCE_DATABASE_URL=postgresql+asyncpg://evidence_app:$evidence_db_password@postgres:5432/evidence_db#" \
    -e "s#VERIFICATION_DATABASE_URL=postgresql+asyncpg://verification_app:change-me-local-only@postgres:5432/verification_db#VERIFICATION_DATABASE_URL=postgresql+asyncpg://verification_app:$verification_db_password@postgres:5432/verification_db#" \
    -e "s#REVIEW_DATABASE_URL=postgresql+asyncpg://review_app:change-me-local-only@postgres:5432/review_db#REVIEW_DATABASE_URL=postgresql+asyncpg://review_app:$review_db_password@postgres:5432/review_db#" \
    -e "s#SIMRS_B_DATABASE_URL=postgresql+asyncpg://simrs_b_app:change-me-local-only@postgres:5432/simrs_b_db#SIMRS_B_DATABASE_URL=postgresql+asyncpg://simrs_b_app:$simrs_b_db_password@postgres:5432/simrs_b_db#" \
    -e "s#SIMRS_A_DATABASE_URL=postgresql+asyncpg://simrs_a_app:change-me-local-only@postgres:5432/simrs_a_db#SIMRS_A_DATABASE_URL=postgresql+asyncpg://simrs_a_app:$simrs_a_db_password@postgres:5432/simrs_a_db#" \
    -e "s/PARTICIPANT_LOOKUP_HMAC_KEY=replace-with-64-hex-characters/PARTICIPANT_LOOKUP_HMAC_KEY=$participant_key/" \
    -e "s/FIELD_ENCRYPTION_MASTER_KEY=replace-with-64-hex-characters/FIELD_ENCRYPTION_MASTER_KEY=$field_key/" \
    "$env_file"
  chmod 600 "$env_file"
fi

echo "[bootstrap-dev] Local-only secrets are ready in .secrets/ and .env"
