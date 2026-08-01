# Agent-PM backend

FastAPI service implementing the Delivery Steward. Deploys to Render; uses
Supabase for Postgres and for verifying auth tokens.

## Running locally

```bash
cp .env.example .env
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head            # needs ALEMBIC_DATABASE_URL
uvicorn agent_pm.main:app --reload --port 8000
```

API docs at <http://localhost:8000/docs> (disabled in production).

### Running without credentials

Every outbound integration has a deterministic fixture implementation, selected
automatically when its credentials are absent:

| Unset variable      | Falls back to                                    |
| ------------------- | ------------------------------------------------ |
| `ANTHROPIC_API_KEY` | An offline model that echoes prompt evidence     |
| `JIRA_BASE_URL`     | A fixed 12-issue sprint with 3 blockers          |
| `GITHUB_TOKEN`      | Three commits and a merged pull request          |
| `TEAMS_WEBHOOK_URL` | An in-memory channel that logs what it would post |
| `TEAMS_TENANT_ID`   | An in-memory RAID workbook                        |

`GET /api/v1/health/ready` reports which of each is live. This is why the unit
tests need no network: a task's behaviour is exercised end to end against
fixtures.

Only `DATABASE_URL` has no fallback — the API needs Postgres.

### Running without Supabase

Authentication has no fixture equivalent, because faking it is exactly the
thing you do not want happening by accident. Instead there is one explicit
escape hatch for local development:

```bash
ENVIRONMENT=local
DEV_AUTH_BYPASS_EMAIL=you@company.com
```

Every request is then treated as that user and no token is required, so the UI
is usable before a Supabase project exists. Three guard rails keep it local:

1. The setting is only honoured when `ENVIRONMENT=local`.
2. The application **refuses to start** if it is set in any other environment —
   a misconfigured deploy crashes on boot rather than serving every request as
   one user.
3. Every bypassed request logs `auth_bypassed_dev_only` at WARNING.

Delete the line once Supabase is configured. `tests/unit/test_dev_auth_bypass.py`
covers all three guards.

## Commands

| Command                          | Purpose                                  |
| -------------------------------- | ---------------------------------------- |
| `pytest`                         | Full suite                               |
| `pytest -m "not integration"`    | Skip anything needing a live database    |
| `ruff check src tests`           | Lint                                     |
| `mypy`                           | Type check                               |
| `python -m agent_pm.evals.runner`| Agent quality gate                       |
| `python -m agent_pm.scheduler.runner` | Scheduler worker                    |
| `alembic revision --autogenerate -m "..."` | New migration               |

## Structure

```
src/agent_pm/
├── api/            HTTP surface — routing only, no business logic
│   ├── deps.py     Session, current user, pagination
│   └── v1/routes/  One module per resource
├── agents/         Agent tasks: prompts, reasoning, grounding
│   └── tasks/      One module per row of the brief's catalog
├── core/           Config, logging, security, errors, enums, clock, grounding
├── db/             Engine, session, declarative base, custom column types
├── evals/          Scored scenarios — the release gate for autonomy changes
├── integrations/   Outbound adapters, each a Protocol + real + fixture
├── models/         SQLAlchemy tables
├── repositories/   Data access — the only place queries are built
├── scheduler/      APScheduler jobs and the worker entry point
├── schemas/        Pydantic request/response DTOs
└── services/       Use cases, transactions, authorisation
```

Dependencies point one way only: `api → services → agents → repositories →
models`. `core`, `schemas` and `integrations` may be imported by anything.
See [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for the reasoning.

Two rules worth restating, because most of the design follows from them:

1. **Agent tasks never touch the database.** They receive an immutable
   `TaskContext` and return a `TaskResult`. That is what makes them testable
   with no session and no network.
2. **Only `services/approval_service.py` writes to Jira or the RAID workbook.**
   Every such call sits downstream of a recorded human decision and executes
   the exact approved payload.

## Migrations

Alembic reads its URL from application settings, not `alembic.ini`, so
credentials live in one place. Use the **direct** Supabase connection (port
5432) for `ALEMBIC_DATABASE_URL` — the transaction pooler cannot run DDL.

```bash
alembic upgrade head
alembic revision --autogenerate -m "add something"
alembic downgrade -1
```

## Tests

- `tests/unit` — agent tasks against fixtures, grounding policy, autonomy
  gating, the dev-bypass guards. No database, no network.
- `tests/integration` — the API through `TestClient`, plus migration parity.

**The migration tests drop every table.** They read
`ALEMBIC_TEST_DATABASE_URL` — never `DATABASE_URL` — so that running `pytest`
cannot destroy your seeded development data. They skip when it is unset:

```bash
createdb agent_pm_test
ALEMBIC_TEST_DATABASE_URL=postgresql+asyncpg://agent_pm:agent_pm@localhost:5432/agent_pm_test \
  pytest tests/integration/test_migrations.py
```

What they assert is worth the setup: applying every migration to an empty
database must produce exactly the schema the models describe, and `downgrade
base` must leave nothing behind. Without that, `--autogenerate` drifts from the
ORM and the first symptom is a production 500 on a missing column.
