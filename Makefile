.PHONY: bootstrap install up migrate seed seed-benchmark test-benchmark test-unit test-contract test-integration test-e2e test-security test-concurrency test-fault test-load lint backup-local restore-local restore-drill release verify-release down reset-dev-data

bootstrap:
	bash scripts/bootstrap-dev.sh

install:
	python3 -m pip install --target .deps -r requirements/dev.txt

up:
	docker compose up --build -d --wait

migrate:
	docker compose run --rm encounter-api alembic upgrade head
	docker compose run --rm evidence-api alembic upgrade head
	docker compose run --rm verification-api alembic upgrade head
	docker compose run --rm review-api alembic upgrade head
	docker compose run --rm simrs-a-api alembic upgrade head
	docker compose run --rm simrs-b-api alembic upgrade head

seed:
	docker compose run --rm encounter-api python -m app.seed

seed-benchmark:
	docker compose exec -T postgres psql -U encounter_app -d encounter_db < scripts/generated/seed_encounter_1000.sql
	docker compose exec -T postgres psql -U evidence_app -d evidence_db < scripts/generated/seed_evidence_1000.sql

test-benchmark:
	python3 scripts/test-1000-claims.py --limit 1000 --workers 8

test-unit:
	PYTHONPATH=.deps:libs/python-observability python3 -m pytest services/encounter-service/tests/unit tests/security/test_redaction_unit.py
	PYTHONPATH=.deps:libs/python-observability python3 -m pytest services/evidence-service/tests/unit services/evidence-service/tests/contract
	PYTHONPATH=.deps:services/verification-service:libs/python-auth:libs/canonical-data:libs/python-observability python3 -m pytest services/verification-service/tests/unit services/verification-service/tests/contract
	PYTHONPATH=.deps:services/review-service:libs/python-auth:libs/canonical-data:libs/python-observability python3 -m pytest services/review-service/tests/unit services/review-service/tests/contract
	PYTHONPATH=.deps:services/narrative-worker python3 -m pytest services/narrative-worker/tests/unit
	PYTHONPATH=.deps:adapters/simrs-b python3 -m pytest adapters/simrs-b/tests

test-contract:
	bash scripts/run-contract-tests.sh

test-integration:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps:libs/python-observability python3 -m pytest services/encounter-service/tests/integration/test_db_and_outbox.py tests/integration/test_db_isolation.py'
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps:libs/python-observability python3 -m pytest services/evidence-service/tests/integration/test_db_and_outbox.py'
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps:libs/python-observability python3 -m pytest services/verification-service/tests/integration/test_db_and_outbox.py'
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps:libs/python-observability python3 -m pytest services/review-service/tests/integration/test_db_and_outbox.py'

test-e2e:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest tests/e2e/test_gate7_simrs_b.py'
	cd tests/e2e && npm test

test-security:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest tests/security'

test-concurrency:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest tests/concurrency'

test-fault:
	bash -c 'set -a; source .env; set +a; RUN_FAULT_TESTS=1 PYTHONPATH=.deps python3 -m pytest tests/fault'

test-load:
	docker compose --profile load run --rm load-test run /scripts/k6_verification_load.js

lint:
	PYTHONPATH=.deps python3 -m ruff check services/encounter-service services/evidence-service services/verification-service services/review-service services/narrative-worker simulators/simrs-a-backend simulators/simrs-b-backend adapters/simrs-b libs scripts tests

backup-local:
	bash scripts/backup-local.sh

restore-local:
	bash scripts/restore-local.sh "$(BACKUP)"

restore-drill:
	APP_ENV=local bash scripts/restore-drill.sh

release:
	bash scripts/build-release-artifact.sh

verify-release:
	bash scripts/verify-release-artifact.sh "$(MANIFEST)"

down:
	docker compose down

reset-dev-data:
	@test "$${APP_ENV:-local}" = local
	docker compose down -v
	$(MAKE) up migrate seed
