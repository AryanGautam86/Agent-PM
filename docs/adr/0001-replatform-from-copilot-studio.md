# ADR 0001 — Replatform from Copilot Studio to a custom Vercel/Render/Supabase stack

- **Status:** Accepted
- **Date:** 2026-08-01
- **Deciders:** Engagement owner

## Context

The agent brief (`docs/AGENT_BRIEF.md`) specifies Microsoft Copilot Studio as
the build platform: topics for tasks, Power Automate for flows, Dataverse for
state, Adaptive Cards for human-in-the-loop, native publishing to a Teams
channel, and Power Platform admin center for governance.

The delivery decision is to host the frontend on Vercel, the backend on Render,
and use Supabase for database and authentication (Google OAuth plus email OTP).
These are mutually exclusive with Copilot Studio — Copilot Studio agents run
inside the Power Platform and cannot be deployed to Render or Vercel.

## Decision

Treat the brief as the **functional** specification and build a custom
application on the chosen stack. Every Copilot Studio construct maps onto a
first-class concept in this codebase rather than being dropped:

| Copilot Studio construct | Realisation here |
| --- | --- |
| Topic | `AgentTask` subclass in `agents/tasks/` |
| Power Automate scheduled trigger | APScheduler job in `scheduler/` |
| Power Automate connector | Adapter in `integrations/`, behind a Protocol |
| Dataverse table | Postgres table on Supabase, SQLAlchemy model |
| Adaptive Card approval | `Approval` row + approval card in the React UI |
| Connected agents (A2A) | `agent_events` table + `events/bus.py` |
| Model choice per topic | `AgentTask.model_tier` → structured or narrative model |
| Purview audit | `agent_runs` + `approvals` audit rows |
| Entra ID auth | Supabase Auth (Google OAuth + email OTP) |
| Solution per engagement | `engagements` row; behaviour is configuration, not deployment |

## Consequences

**Gained**

- Full control over prompts, grounding enforcement, and evaluation.
- Deployment on the chosen hosts, with ordinary Git-based CI/CD.
- One deployment serves all engagements; a new engagement is a database row,
  not a new solution to promote through environments.
- No Power Platform premium licensing per seat.

**Lost, and how it is handled**

- *Native Teams channel publishing.* The largest single loss. Posting to Teams
  becomes an outgoing integration (`integrations/teams/`) — an incoming webhook
  for the simple case, Microsoft Graph with an app registration for the full
  case (reading messages and reactions). Until a tenant is wired up, the
  approval UI in the React app is the primary HITL surface and Teams is a
  notification mirror. **This is the part of the brief that needs a product
  decision: is the React app the operator surface, or must it be Teams?**
- *Prebuilt connectors.* Jira, GitHub and storage adapters are hand-written.
  Each is a Protocol with a real and a fixture implementation.
- *Built-in governance.* Audit, retention and PII handling are our
  responsibility. `agent_runs` and `approvals` are append-only audit records;
  see `docs/ARCHITECTURE.md`.
- *Built-in evaluation tooling.* Replaced by the `evals/` package and a CI gate.

## Alternatives considered

1. **Build on Copilot Studio as specified.** Rejected: incompatible with the
   Vercel/Render/Supabase and Google-OAuth requirements.
2. **Hybrid — Copilot Studio front, custom backend.** Rejected for the
   skeleton: it doubles the platforms to operate and splits the audit trail.
   Remains viable later if Teams-native UX proves mandatory, because the
   integration layer already isolates channel concerns.
