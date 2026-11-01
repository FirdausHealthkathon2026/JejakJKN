-- Strict per-service database & credential isolation (§5, §9, §49)
CREATE USER encounter_app WITH PASSWORD 'dev_encounter_pass';
CREATE DATABASE encounter_db OWNER encounter_app;
REVOKE ALL ON DATABASE encounter_db FROM PUBLIC;

CREATE USER evidence_app WITH PASSWORD 'dev_evidence_pass';
CREATE DATABASE evidence_db OWNER evidence_app;
REVOKE ALL ON DATABASE evidence_db FROM PUBLIC;

CREATE USER verification_app WITH PASSWORD 'dev_verification_pass';
CREATE DATABASE verification_db OWNER verification_app;
REVOKE ALL ON DATABASE verification_db FROM PUBLIC;

CREATE USER review_app WITH PASSWORD 'dev_review_pass';
CREATE DATABASE review_db OWNER review_app;
REVOKE ALL ON DATABASE review_db FROM PUBLIC;

CREATE USER simrs_a_app WITH PASSWORD 'dev_simrs_a_pass';
CREATE DATABASE simrs_a_db OWNER simrs_a_app;
REVOKE ALL ON DATABASE simrs_a_db FROM PUBLIC;

CREATE USER simrs_b_app WITH PASSWORD 'dev_simrs_b_pass';
CREATE DATABASE simrs_b_db OWNER simrs_b_app;
REVOKE ALL ON DATABASE simrs_b_db FROM PUBLIC;

CREATE USER kc_user WITH PASSWORD 'dev_kc_pass';
CREATE DATABASE keycloak_db OWNER kc_user;
REVOKE ALL ON DATABASE keycloak_db FROM PUBLIC;
