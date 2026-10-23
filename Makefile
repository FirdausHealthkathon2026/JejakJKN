.PHONY: bootstrap up migrate seed test-unit test-contract test-integration test-e2e test-security test-concurrency lint down reset-dev-data

bootstrap:
	bash scripts/bootstrap-dev.sh

up:
	docker compose up --build -d

migrate:
	@echo "Running per-service Alembic migrations..."

seed:
	python3 scripts/seed-synthetic-data.py

test-unit:
	pytest services/*/tests/unit libs/*/tests adapters/*/tests

test-contract:
	bash scripts/run-contract-tests.sh

test-integration:
	pytest tests/integration services/*/tests/integration

test-e2e:
	pytest tests/e2e

test-security:
	pytest tests/security

test-concurrency:
	pytest tests/concurrency

lint:
	@echo "Running static analysis and type checks..."

down:
	docker compose down

reset-dev-data:
	@echo "Resetting local synthetic data..."
	python3 scripts/seed-synthetic-data.py --reset
