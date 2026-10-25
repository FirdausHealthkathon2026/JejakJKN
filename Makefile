.PHONY: bootstrap install up migrate seed test-unit test-contract test-integration test-e2e test-security test-concurrency lint down reset-dev-data

bootstrap:
	bash scripts/bootstrap-dev.sh

install:
	python3 -m pip install --target .deps -r requirements/dev.txt

up:
	docker compose up --build -d --wait

migrate:
	docker compose run --rm encounter-api alembic upgrade head
	docker compose run --rm evidence-api alembic upgrade head
	docker compose run --rm simrs-a-api alembic upgrade head

seed:
	docker compose run --rm encounter-api python -m app.seed

test-unit:
	PYTHONPATH=.deps python3 -m pytest services/encounter-service/tests/unit tests/security/test_redaction_unit.py
	PYTHONPATH=.deps python3 -m pytest services/evidence-service/tests/unit services/evidence-service/tests/contract

test-contract:
	bash scripts/run-contract-tests.sh

test-integration:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest services/encounter-service/tests/integration/test_db_and_outbox.py tests/integration/test_db_isolation.py'
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest services/evidence-service/tests/integration/test_db_and_outbox.py'

test-e2e:
	pytest tests/e2e

test-security:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest tests/security'

test-concurrency:
	bash -c 'set -a; source .env; set +a; RUN_LIVE_TESTS=1 PYTHONPATH=.deps python3 -m pytest tests/concurrency'

lint:
	PYTHONPATH=.deps python3 -m ruff check services/encounter-service services/evidence-service simulators/simrs-a-backend libs scripts tests

down:
	docker compose down

reset-dev-data:
	@test "$${APP_ENV:-local}" = local
	docker compose down -v
	$(MAKE) up migrate seed
