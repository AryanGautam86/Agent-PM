.DEFAULT_GOAL := help
PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup

.PHONY: install
install: install-backend install-frontend ## Install everything

.PHONY: install-backend
install-backend: ## Create the venv and install the backend
	cd backend && python3.12 -m venv .venv && .venv/bin/pip install --upgrade pip \
		&& .venv/bin/pip install -e ".[dev]"

.PHONY: install-frontend
install-frontend: ## Install frontend dependencies
	cd frontend && npm install

# ------------------------------------------------------------------ run

.PHONY: dev-backend
dev-backend: ## Run the API with reload on :8000
	cd backend && .venv/bin/uvicorn agent_pm.main:app --reload --port 8000

.PHONY: dev-frontend
dev-frontend: ## Run the SPA on :5173
	cd frontend && npm run dev

.PHONY: scheduler
scheduler: ## Run the scheduler worker
	cd backend && .venv/bin/python -m agent_pm.scheduler.runner

# ---------------------------------------------------------------- checks

.PHONY: test
test: test-backend test-frontend ## Run all tests

.PHONY: test-backend
test-backend: ## Backend test suite (never touches your dev database)
	cd backend && .venv/bin/python -m pytest

.PHONY: test-migrations
test-migrations: ## Migration parity. DESTRUCTIVE: drops every table in agent_pm_test
	createdb agent_pm_test 2>/dev/null || true
	cd backend && ALEMBIC_TEST_DATABASE_URL="postgresql+asyncpg://agent_pm:agent_pm@localhost:5432/agent_pm_test" \
		.venv/bin/python -m pytest tests/integration/test_migrations.py

.PHONY: test-frontend
test-frontend: ## Frontend test suite
	cd frontend && npm test

.PHONY: lint
lint: ## Lint both sides
	cd backend && .venv/bin/ruff check src tests
	cd frontend && npm run lint

.PHONY: typecheck
typecheck: ## Type check both sides
	cd backend && .venv/bin/mypy
	cd frontend && npm run typecheck

.PHONY: evals
evals: ## Agent quality gate — required before raising an autonomy level
	cd backend && .venv/bin/python -m agent_pm.evals.runner

.PHONY: check
check: lint typecheck test evals ## Everything CI runs

# ------------------------------------------------------------- database

.PHONY: db-up
db-up: ## Start local Postgres on :5433 (no Supabase project needed)
	docker compose up -d postgres

.PHONY: db-down
db-down: ## Stop local Postgres (keeps the volume)
	docker compose down

.PHONY: db-reset
db-reset: ## Destroy and recreate the local database
	docker compose down -v && docker compose up -d postgres

.PHONY: migrate
migrate: ## Apply migrations
	cd backend && .venv/bin/alembic upgrade head

.PHONY: revision
revision: ## Autogenerate a migration: make revision m="add x"
	cd backend && .venv/bin/alembic revision --autogenerate -m "$(m)"

# ------------------------------------------------------------------- ops

.PHONY: tasks
tasks: ## List the agent task catalog (needs no database)
	cd backend && .venv/bin/python -m agent_pm.cli tasks

.PHONY: seed
seed: ## Create a demo engagement: make seed owner=you@company.com
	cd backend && .venv/bin/python -m agent_pm.cli seed \
		--slug demo-pod --name "Demo Pod" --client "Example Client" \
		--jira-project DEMO --github-repo example/demo --owner "$(owner)"

.PHONY: engagements
engagements: ## List active engagements
	cd backend && .venv/bin/python -m agent_pm.cli engagements

# ---------------------------------------------------------------- build

.PHONY: build-frontend
build-frontend: ## Production build of the SPA
	cd frontend && npm run build
