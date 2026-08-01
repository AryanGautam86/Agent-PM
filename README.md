# Agent-PM — Delivery Steward 

An AI project-management agent that acts as a delivery steward for a services pod:
twice-daily standup posts, RAID log stewardship, action-item tracking, and
human-approved writes to Jira and the RAID log.

**What the UI currently exposes:** Dashboard, Standups, Tasks, Reports and Team.
The RAID log and the approvals queue exist in full on the backend — tables,
endpoints, and the gap-scan, risk-promotion and meeting-intake agent tasks — but
have no screens yet.

**Who can change what:** only administrators. Everyone else has read access plus
the ability to post a standup. Enforced by one dependency on every mutating
route; see `backend/src/agent_pm/api/deps.py`.

The functional specification lives in [`docs/AGENT_BRIEF.md`](docs/AGENT_BRIEF.md).
It was originally written against Microsoft Copilot Studio; this repository
implements the same behaviour as a custom application. See
[`docs/adr/0001-replatform-from-copilot-studio.md`](docs/adr/0001-replatform-from-copilot-studio.md)
for that decision and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the
capability-by-capability mapping.

## Stack

| Layer      | Technology                                   | Hosting  |
| ---------- | -------------------------------------------- | -------- |
| Frontend   | React 19 + TypeScript + Vite + TanStack Query | Vercel   |
| Backend    | Python 3.12 + FastAPI + SQLAlchemy 2 (async)  | Render   |
| Database   | Supabase Postgres (via asyncpg)               | Supabase |
| Auth       | Supabase Auth — Google OAuth + email OTP      | Supabase |
| Reasoning  | Anthropic Claude (structured + narrative)     | API      |

## Repository layout

```
Agent-PM/
├── backend/            FastAPI service — agent tasks, API, scheduler
│   ├── src/agent_pm/   Application package (src-layout)
│   ├── migrations/     Alembic migrations
│   └── tests/          Unit + integration tests
├── frontend/           React SPA — dashboard, approvals, RAID, reports
│   └── src/            Feature-sliced source
├── docs/               Brief, architecture, deployment, ADRs
└── render.yaml         Render blueprint for the backend
```

Each directory has its own README describing the contract of the layer.

## Quick start

Prerequisites: Python 3.12+, Node 20+, and Postgres (either `make db-up` for
Docker, `brew install postgresql@16`, or a Supabase project).

```bash
make install                        # venv + npm install
make db-up                          # local Postgres, or point at Supabase
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Set `DATABASE_URL` and `ALEMBIC_DATABASE_URL` in `backend/.env`, then:

```bash
make migrate
make seed owner=you@company.com     # creates a demo engagement
make dev-backend                    # :8000
make dev-frontend                   # :5173, separate shell
```

Open <http://localhost:5173>.

**No credentials are needed to see it working.** Every outbound integration
falls back to a deterministic fixture, and setting `DEV_AUTH_BYPASS_EMAIL` in
`backend/.env` skips sign-in — so the full standup → gap scan → approval loop
runs with no Supabase, Jira, GitHub, Teams or Anthropic account. The bypass is
honoured only when `ENVIRONMENT=local`, and the app refuses to start if it is
set anywhere else. See `backend/README.md`.

Add your Supabase URL and anon key to both `.env` files, delete
`DEV_AUTH_BYPASS_EMAIL`, and Google / email-OTP sign-in takes over.

`GET /api/v1/health/ready` reports which integrations are live and which are on
fixtures.

```bash
make tasks                                   # the catalog, no database needed
cd backend && .venv/bin/python -m agent_pm.cli run demo-pod morning_sprint_plan
```

| Command      | Does                                            |
| ------------ | ----------------------------------------------- |
| `make check` | Everything CI runs: lint, types, tests, evals   |
| `make test`  | Both test suites                                |
| `make evals` | Agent quality gate                              |
| `make help`  | All targets                                     |

## Documentation

- [`docs/AGENT_BRIEF.md`](docs/AGENT_BRIEF.md) — mission, task catalog, KPIs, rollout, risks
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — layering rules, data model, agent-task lifecycle
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — Supabase, Render, Vercel setup
- [`docs/adr/`](docs/adr) — architecture decision records
