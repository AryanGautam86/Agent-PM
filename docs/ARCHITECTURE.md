# Architecture

## 1. System shape

```
┌──────────────┐   Supabase JWT    ┌─────────────────────────────┐
│  React SPA   │ ────────────────▶ │  FastAPI backend (Render)   │
│  (Vercel)    │ ◀──────────────── │                             │
└──────┬───────┘   JSON over HTTPS └──────┬──────────────┬───────┘
       │                                  │              │
       │ signInWithOAuth / signInWithOtp  │ asyncpg      │ httpx
       ▼                                  ▼              ▼
┌──────────────┐                  ┌──────────────┐  ┌──────────────────┐
│ Supabase Auth│                  │   Supabase   │  │ Jira · GitHub ·  │
│ Google + OTP │                  │   Postgres   │  │ Teams · Anthropic│
└──────────────┘                  └──────────────┘  └──────────────────┘
```

The SPA never talks to the database directly. Supabase is used for **auth** by
the frontend and for **Postgres** by the backend; all business reads and writes
go through the API so that grounding, autonomy gating and audit cannot be
bypassed.

## 2. Backend layering

Dependencies point in one direction only. A layer may import from layers below
it, never above.

```
api/          HTTP surface: routing, status codes, request/response models
  ↓
services/     Use cases, transactions, authorisation, orchestration
  ↓
agents/       Agent tasks: prompt construction, LLM calls, grounding checks
  ↓
repositories/ Data access; the only place that builds SQL queries
  ↓
models/       SQLAlchemy ORM tables
integrations/ Outbound adapters (Jira, GitHub, Teams, storage, LLM)
core/         Config, logging, security, errors, enums — imported by anything
schemas/      Pydantic DTOs — imported by anything
```

Rules that keep this honest:

- **Routes contain no business logic.** A route resolves dependencies, calls one
  service method, and maps the result to a schema.
- **Repositories return ORM models; services return Pydantic schemas.** ORM
  objects never escape the service layer, so no lazy-load ever fires inside a
  serialiser.
- **Agents never touch the database.** An `AgentTask` receives an immutable
  `TaskContext` and returns a `TaskResult`; persistence is the service's job.
  This is what makes tasks unit-testable without a database.
- **Integrations are Protocols.** Every outbound system is defined as a
  `typing.Protocol` with a real implementation and a fixture implementation.
  `integrations/registry.py` picks one based on whether credentials are set.

## 3. Agent task lifecycle

Every task in the brief's catalog is an `AgentTask` subclass declaring its
name, autonomy level, model tier, and whether its output requires citations.

```
Trigger (scheduler | API | event)
   └─▶ AgentTaskRunner
         1. open agent_runs row  (audit starts before any work)
         2. gather()   → task pulls read-only snapshots from integrations
         3. reason()   → prompt + LLM call, returns a structured TaskResult
         4. validate() → grounding check: every claim carries a citation
         5. gate()     → autonomy level decides: write, or raise an Approval
         6. persist()  → service writes results and emits events
         7. close agent_runs row with status, model, tokens, duration
```

Failures at any step close the run with `status=failed` and the error; the
run row is never deleted. `agent_runs` plus `approvals` together answer
"why did the agent say or do that", which is the audit requirement the brief
placed on Purview.

### Grounding

`GroundingPolicy` (in `core/grounding.py`) enforces the brief's hard rule: a
status claim must cite a Jira key, commit SHA, message id, or transcript
timestamp. Tasks with `requires_citations = True` fail validation — and
therefore never post — if the citation coverage falls below the configured
threshold. The KPI target is < 1% hallucination rate; this is the mechanism.

### Autonomy gating

`AutonomyLevel` decides what step 5 does:

| Level | Behaviour |
| --- | --- |
| L1 | Result is stored as a draft only |
| L2 | Result is stored and an `Approval` row is created; no external write |
| L3 | External write happens immediately; a review record is created |
| L4 | External write happens immediately; only policy exceptions surface |

A task can never perform an external write while its level is L1 or L2 — the
runner, not the task, holds that decision.

## 4. Data model

| Table | Purpose |
| --- | --- |
| `users` | Profile mirror of `auth.users`; app role (PO, delivery lead, engineer, admin) |
| `engagements` | One row per project. Channel binding, Jira project, schedule times, timezone, default autonomy |
| `engagement_members` | Pod membership and per-pod role |
| `standups` | Morning and EOD posts. Unique on (engagement, kind, date) so a retry cannot double-post |
| `raid_items` | Risks, assumptions, issues, dependencies, with source provenance |
| `action_items` | Owner, due date, nudge count, escalation state |
| `approvals` | HITL requests: proposed payload, decision, decider, expiry |
| `agent_events` | A2A bus — `meeting_outcome` in, `pm_summary` / `pm_eod_summary` out |
| `agent_runs` | Append-only execution audit: task, status, model, tokens, duration |
| `reports` | Weekly client status and sprint planning packs |

Design notes:

- **Enums are stored as strings**, validated by Python `StrEnum` at the
  boundary, not as Postgres enum types. Adding an autonomy level or RAID status
  is then a code change, not a migration with a type rewrite.
- **`Approval.payload` is JSONB** holding the exact proposed change. Approving
  executes that payload verbatim — the agent cannot substitute a different
  write between proposal and approval.
- **Timestamps are `timestamptz`**, stored UTC. Engagements carry an IANA
  timezone used only to decide when 08:00 and 17:30 fall.

## 5. Multi-tenancy

One deployment serves all engagements. Isolation is enforced in the service
layer: every query is scoped by `engagement_id`, and access requires an
`engagement_members` row (or the `admin` role). The dependency
`require_engagement_access` in `api/deps.py` is the single choke point.

Supabase Row Level Security is **not** relied upon, because the backend
connects with a privileged role. If the SPA is ever given direct table reads,
RLS becomes mandatory first.

## 6. Events / A2A

The Meeting Agent contract is a versioned envelope:

```json
{
  "type": "meeting_outcome",
  "version": 1,
  "engagement_slug": "acme-migration",
  "consented": true,
  "payload": { "decisions": [], "actions": [], "risks": [] }
}
```

Intake rejects `consented=false` and unknown versions. The PM agent never sees
raw transcripts — only this envelope — which is what keeps the two agents from
drifting.

## 7. Testing strategy

- `tests/unit` — agent tasks against fixture integrations, grounding policy,
  autonomy gating. No database, no network.
- `tests/integration` — API routes against a real Postgres and an overridden
  auth dependency.
- `evals/` — scored scenario cases for agent output quality; the CI gate the
  brief requires before promoting a task to a higher autonomy level.
