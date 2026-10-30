#!/usr/bin/env bash
set -euo pipefail

create_domain_database() {
  local role="$1"
  local database="$2"
  local password="$3"
  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 \
    --command "CREATE USER $role WITH PASSWORD '$password'"
  createdb --username "$POSTGRES_USER" --owner "$role" "$database"
  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 \
    --command "REVOKE ALL ON DATABASE $database FROM PUBLIC"
}

create_domain_database encounter_app encounter_db "$ENCOUNTER_DB_PASSWORD"
create_domain_database evidence_app evidence_db "$EVIDENCE_DB_PASSWORD"
create_domain_database verification_app verification_db "$VERIFICATION_DB_PASSWORD"
create_domain_database review_app review_db "$REVIEW_DB_PASSWORD"
create_domain_database simrs_a_app simrs_a_db "$SIMRS_A_DB_PASSWORD"
create_domain_database simrs_b_app simrs_b_db "$SIMRS_B_DB_PASSWORD"
create_domain_database bpjs_claim_app bpjs_claim_db "$BPJS_CLAIM_DB_PASSWORD"
create_domain_database kc_user keycloak_db "$KEYCLOAK_DB_PASSWORD"
