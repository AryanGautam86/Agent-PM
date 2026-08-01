# Agent 1: Project Management Agent (Delivery Steward)

> This is the source functional specification for the system. It was authored
> against Microsoft Copilot Studio. The platform sections are retained verbatim
> for traceability; see [`ARCHITECTURE.md`](ARCHITECTURE.md) for how each
> Copilot Studio construct is realised in this codebase, and
> [`adr/0001-replatform-from-copilot-studio.md`](adr/0001-replatform-from-copilot-studio.md)
> for why.

## Agent brief

**Mission.** Be the delivery steward attached to each project's pod Teams
channel. Every working day, deliver a morning sprint plan and an end-of-day
summary with committed / delivered / pending stories per person and current
blockers. Maintain the RAID log: read it for context, identify items missing
from it, and — with human-in-the-loop confirmation — propose updates extracted
from meeting outcomes delegated from the Meeting Agent. Surface action items,
ask the PO to approve before pushing them to Jira and the RAID log.

**Reasoning model.** Default to a fast structured model for structured tasks
(morning post, EOD post, RAID gap scan). For high-stakes synthesis (weekly
client status narrative), route to a stronger model.

**Agent identity.** `agent-pm-{engagement-id}`. One agent instance per project.
Each instance has its own channel binding, its own knowledge sources, and its
own audit trail.

**Persona.** A senior delivery manager with 10+ years in agile services
delivery. Calm, proactive, never lets a follow-up slip. Writes status updates
the way a good EM does: clear, ranked by impact, with crisp "so what"
commentary. Defaults to *show evidence* over *opinion*. Always cites the Jira
ticket, commit, message, or transcript timestamp that grounds a claim. Never
auto-updates a system without explicit PO confirmation.

**Augments role.** Technical Product Owner / Engagement Manager / Delivery Lead.

## Autonomy levels

| Level | Meaning                                                            |
| ----- | ------------------------------------------------------------------ |
| L1    | Suggests only; no artefact produced without a human asking          |
| L2    | Drafts, human approves before any external write                    |
| L3    | Autonomous action, human reviews after the fact                     |
| L4    | Fully autonomous within policy; only exceptions surface to a human  |

## Detailed task catalog

Each row is one agent task (`backend/src/agent_pm/agents/tasks/`).

| Task | Trigger | Autonomy | Inputs | Outputs | HITL checkpoint |
| --- | --- | --- | --- | --- | --- |
| **Morning sprint plan** — post the sprint plan, committed/delivered/pending counts by person, and current blockers. | Scheduled, 08:00 daily | L3 | Jira, RAID log, prior EOD summary | Standup card in pod channel | Auto-post; PO reacts for feedback |
| **End-of-day summary** — post what shipped, what's pending, what's blocked. | Scheduled, 17:30 daily | L3 | Jira deltas since morning, GitHub commits, Meeting Agent outcomes | Standup card; emits `pm_eod_summary` | Auto-post; PO can flag for re-summary |
| **RAID log read & gap detection** — scan the RAID log against current Jira blockers; flag blockers not present in RAID. | Scheduled, after morning Jira pull | L3 | RAID workbook, Jira blockers | Approval card per gap: *Add to RAID* / *Already there* | PO approves before any write |
| **Meeting-driven update flow** — consume `meeting_outcome` from the Meeting Agent; propose Jira and RAID updates. | Event: `meeting_outcome` | L2 | Meeting outcome payload (decisions, actions, risks) | Two approval batches: Jira updates, RAID updates | PO approves before flows execute |
| **Action-item tracking** — track every action item; nudge owners 24h before due; escalate overdue to PO. | Scheduled hourly + event-driven | L4 nudges / L3 escalations | Action item store, calendar | Owner nudges; weekly aging card; PO escalation | Escalations visible to PO before client comms |
| **Blocker → risk promotion** — blocker older than 2 days becomes a proposed risk with mitigation. | Scheduled daily | L2 | Jira blocker aging, RAID state | Approval card: *Promote to risk?* with proposed mitigation | PO confirms |
| **Weekly client status** — aggregate sprint progress, velocity, scope delta, risks, decisions. | Scheduled weekly | L2 | Jira, RAID, prior weekly report, meeting outcomes | Status document + email draft; narrative routed to the stronger model | Engagement Lead reviews and sends |
| **Sprint planning prep** — 24h before planning, post velocity, carryover, capacity, proposed backlog slice. | Scheduled per sprint | L2 | Jira velocity, capacity, refined backlog | Planning pack + draft sprint | PO and Tech Lead validate |

## Required integrations

| Integration | Purpose |
| --- | --- |
| Teams | Post cards to the channel, read messages and reactions for HITL |
| Document storage | Read and write the RAID workbook, read PRDs, write status reports |
| Jira | Read stories / sprints / blockers; write comments and labels after approval |
| GitHub | Read commits and PR status for the EOD summary's engineering signal |
| Calendar / mail | Read schedules, send email drafts |
| Persistent store | Agent state (action items, prior summaries) for cross-session continuity |
| Meeting Agent (A2A) | Subscribe to `meeting_outcome`; emit `pm_summary` for downstream consumers |
| Anthropic | Narrative-quality tasks (weekly status and similar) |

## KPIs / success metrics

| KPI | Baseline | Target (90-day) |
| --- | --- | --- |
| PM coordination hrs / pod / week | 8–12 hrs | ≤ 3 hrs |
| Morning standup post on-time | n/a (manual, often skipped) | ≥ 95% |
| EOD summary post on-time | n/a | ≥ 95% |
| RAID freshness (blockers reflected within 24h) | often > 1 week stale | ≤ 24 hrs |
| Action items closed on time | ~70% | ≥ 95% |
| Jira/RAID updates approved on first draft | n/a | ≥ 80% with minor/no edits |
| Hallucination rate (audit sample) | n/a | < 1% |
| Risks caught before client escalation | reactive | ≥ 80% proactive |
| PO satisfaction (5-pt) | n/a | ≥ 4.2 |

## Phased rollout

| Phase | Duration | Scope | Exit criteria |
| --- | --- | --- | --- |
| **0 — Scaffold** | Weeks 1–2 | Stand up environments, connect Jira / storage / Teams, configure knowledge sources for the pilot pod | Agent reachable from the pilot channel; all integrations authenticated; first task responds |
| **1 — Read-only morning/EOD** | Weeks 3–5 | Morning and EOD tasks on schedule; initial 30-case eval set | PO accepts ≥ 80% of posts; on-time ≥ 95%; eval pass ≥ 90% |
| **2 — RAID gap + meeting-driven flow** | Weeks 6–9 | RAID gap scan with approval cards; Meeting Agent subscription | RAID gap precision ≥ 85%; ≥ 80% approved; zero unapproved writes in the audit log |
| **3 — Action tracking & risk promotion** | Weeks 10–12 | Action follow-up and risk promotion; expand to 3 pilot pods | On-time closure ≥ 90%; first promoted risks accepted |
| **4 — Productize** | Weeks 13–24 | Hardening, CI/CD, client-branded delivery; package as an offering | First external client pilot signed |

## Key risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Hallucinated status (claiming work done that isn't) | Grounding rule in every task prompt: each claim cites a Jira ticket, commit or message id. Eval gate blocks release if grounding rate < 90%. Enforced in code by `GroundingError`. |
| Unapproved writes to Jira / RAID | Every external write goes through the approval service; auto-deny on expiry; every decision is audited. |
| Provider rate limits | Backoff and caching in the integration layer; usage recorded per agent run. |
| PM Agent + Meeting Agent drift | Versioned `meeting_outcome` event contract. The PM Agent processes only that event, never raw transcripts. |
| Notification fatigue | Per-engineer nudge frequency config; hard cap on direct messages per person per day. |
| Meeting data ingested without consent | The Meeting Agent's consent flow is the upstream gate; events with `consented=false` are rejected at intake. |
| Per-engagement scaling pain | One row per engagement rather than one deployment per engagement; all engagement-specific behaviour is configuration. |
