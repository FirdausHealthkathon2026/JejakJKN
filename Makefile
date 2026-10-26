.PHONY: bootstrap install up migrate seed test-unit test-contract test-integration test-e2e test-security test-concurrency lint backup-local restore-local down reset-dev-data

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

seed:
	docker compose run --rm encounter-api python -m app.seed

test-unit:
	PYTHONPATH=.deps python3 -m pytest services/encounter-service/tests/unit tests/security/test_redaction_unit.py
	PYTHONPATH=.deps python3 -m pytest services/evidence-service/tests/unit services/evidence-service/tests/contract
	PYTHONPATH=.deps:services/verification-service:libs/python-auth:libs/canonical-data python3 -m pytest services/verification-service/tests/unit services/verification-service/tests/contract
	PYTHONPATH=.deps:services/review-service:libs/python-auth:libs/canonical-data python3 -m pytest services/review-service/tests/unit services/review-service/tests/contract
	PYTHONPATH=.deps:services/narrative-worker python3 -m pytest services/narrative-worker/tests/unit
	PYTHONPATH=.deps:adapters/simrs-b python3 -m pytest adapters/simrs-b/tests

test-contract:
	bash scripts/run-contract-tests.sh

test-integration:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest services/encounter-service/tests/integration/test_db_and_outbox.py tests/integration/test_db_isolation.py'
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest services/evidence-service/tests/integration/test_db_and_outbox.py'
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest services/verification-service/tests/integration/test_db_and_outbox.py'
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest services/review-service/tests/integration/test_db_and_outbox.py'

test-e2e:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest tests/e2e/test_gate7_simrs_b.py'

test-security:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest tests/security'

test-concurrency:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest tests/concurrency'

lint:
	PYTHONPATH=.deps python3 -m ruff check services/encounter-service services/evidence-service services/verification-service services/review-service services/narrative-worker simulators/simrs-a-backend simulators/simrs-b-backend adapters/simrs-b libs scripts tests

backup-local:
	bash scripts/backup-local.sh

restore-local:
	bash scripts/restore-local.sh "$(BACKUP)"

down:
	docker compose down

reset-dev-data:
	@test "$${APP_ENV:-local}" = local
	docker compose down -v
	$(MAKE) up migrate seed
