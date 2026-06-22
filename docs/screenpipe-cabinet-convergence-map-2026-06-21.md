# Screenpipe ↔ Cabinet — The Convergence Map (what's where)

_2026-06-21. The definitive division of labour + the migration order. Read before
going live._

> **Superseded (2026-06-22):** the committed architecture is now
> `docs/cabinet-architecture-cohesive-2026-06-22.md` — one brain (System 2) in
> front, screenpipe (System 1) behind, one channel, a front-door + one trigger
> bus. The planes/disposition below still inform it; the "acting-lane as the
> cabinet's product" framing here is replaced by the front-door + orchestration.

## The principle (the dividing line)

- **SCREENPIPE = the autonomic nervous system + memory.** CAPTURE (sensors:
  screen/audio/Teams/email/meetings/code/deploys), STORE (vault, embeddings, db),
  and BUILD the *baseline* self-model (voice, nate-model, self-knowledge, people).
  Coupled to the sensors; always-on; **no acting, no orchestration, no governance.**
- **CABINET = the brain.** THINK + ACT + SURFACE + GOVERN. Reads screenpipe via the
  brain MCP; the **one surface** the captain talks to; every action gated by the
  authority matrix + the ladder; proof recorded in the consequence ledger.

**Rule of thumb:** if a pipe *captures* or *builds baseline memory* → screenpipe.
If it *thinks, acts, surfaces, or governs* → cabinet.

## The complete ideal — four planes + the clone

Beyond the pipe layers, the ideal pins down four cross-cutting planes and one identity.

### 1. Memory
- **Vault** (Obsidian) = the captain's *life truth*, screenpipe-built. Stays.
- **Cabinet memory** (tier2 / ledger / shared interfaces) = the *org's operational
  state*. Cabinet-owned.
- **Self-model** (nate-model / voice) = screenpipe builds the baseline from
  observation; the cabinet reads it and feeds corrections back via
  `append_agent_inbox` (the one vault write path). Co-owned, never duplicated.

### 2. Work surfaces — captain's decision (2026-06-21)
One owner per surface; the work-tracker is a **plugin-able adapter** (captain picks,
via `instance/config/adapters.yml`):
- **Comms** → Telegram, the one Cabinet bot.
- **Work-work** → **Monday** (the captain's real board; the cabinet creates items
  there). Plugin-able — other captains select their own tracker.
- **Linear → REMOVED** for this deployment (redundant with Monday; already a
  read-only archive). Drop it from the officer MCP scope + the docs; keep it only as
  an *inactive* adapter option for captains who'd choose it.
- **Internal cabinet work** → **`/tasks`** (the officer work-graph) — *optional,
  visualization-only.* **Retire for now if it's overhead**; re-enable when
  officer-work visibility is wanted.
- **Personal-work** → **Apple Reminders** (the captain's personal to-dos; the cabinet
  feeds them).

### 3. Proof — ONE store
Two proof systems exist today: screenpipe's `record_shadow` + `retrodiction` scores,
and the cabinet's **consequence ledger**. The ideal is **one** — the cabinet ledger.
Screenpipe's shadow/retrodiction **retire into it** as lanes migrate. (A real
migration, beyond Telegram.)

### 4. Governance
Cabinet owns it; the meta-pipes (`architect` / `reasoning-review` / `retrodiction` /
`autonomy` / `pipe-health`) subsume into the cabinet's evolution / reflection /
authority-matrix / ladder / monitoring loops (see Layer 5).

### The clone — identity (confirmed 2026-06-21)
The clone is **the Nate-shaped coordinating mind** — not an officer, not the whole
org. It does the captain's direct work **and** directs the specialist officers
(CTO/CPO/CRO/COO), and it **climbs from worker → org-runner via the ladder**.
Real-Nate stays the ultimate owner/override; the ladder is the path by which the
clone earns the captain's seat. *Start:* it runs the apprenticeship lanes under
oversight. *End:* it runs the org autonomously.

## The five layers

| Layer | Examples | Home | Why |
|---|---|---|---|
| **1. Capture (sensors)** | teams/msgraph/gmail-incremental, conversations-sync, meeting-intel, embeddings, teams-ocr, commit-stream, codebase-digest, product-ops | **screenpipe — stays** | must run where the raw data is born |
| **2. Memory / self-model** | voice-profile, nate-model, self-knowledge, decisions-capture, people-intel, obsidian-sync | **screenpipe builds → cabinet reads + refines** | baseline model from observation; cabinet refines it from interaction (the 3-way router's corrections feed nate-model/lessons) |
| **3. Reactive acting** | **draft-reply**, commitment-ledger, inbox/feedback-triage, todo-list-assistant, reminders, completion-tracker, automate-my-work | **→ cabinet** (migrate as lanes) | deciding + acting on incoming = the agent |
| **4. Proactive surfacing** | morning-brief, day-recap, session-digest, ask-my-brain, relationship-radar, pre-meeting-brief, top-of-mind, idea-tracker, monday-* | **→ cabinet** (officer capabilities) | surfacing / suggesting = cognition (the CoS/CRO) |
| **5. Governance / meta** | architect, autonomy, reasoning-review, retrodiction, pipe-health | **→ cabinet subsumes** | the cabinet *is* the grown-up governance |

## Layer 5 — the meta-pipes you flagged (the deepest convergence)

The screenpipe meta-pipes are the **first-generation, single-agent** governance.
The cabinet is the **second-generation, multi-agent, ladder-governed** version — it
already holds the grown-up of each:

| Screenpipe meta-pipe | Cabinet equivalent (already built) |
|---|---|
| **architect** (suggests architecture changes) | the evolution loop + capability-gap + CTO/CoS improvement proposals |
| **reasoning-review** (reviews reasoning vs what happened) | the reflection loop + the consequence ledger's `review` (did the action serve intent?) |
| **retrodiction** (clone fitness score) | the fidelity harness (already reuses retrodiction's lib) + the consequence ledger = the *real* fitness. **Half-migrated already.** |
| **autonomy** (graduated autonomy) | the authority matrix + the ladder |
| **pipe-health** (monitoring) | org-health-audit / supervisor monitoring |

So: **the cabinet subsumes governance.** These migrate **last** (most coupled to the
cabinet's own maturity) and *retire* once all acting has migrated and there is
nothing screenpipe-side left to govern.

## The migration order + the pre-go-live RULE

**RULE — one owner per function.** Never double-run: no function may ping the captain
from both bots, and no two systems may act on the same thing. **When a cabinet lane
is proven, DISABLE the screenpipe twin** (launchd unload). This is the single most
important go-live invariant.

**ORDER — one lane at a time, proven before the next:**
1. **draft-reply** — the apprenticeship lane (now).
2. commitment-ledger, triage, reminders.
3. briefs + radar + the surfacing layer.
4. governance / meta (last).

## Go-live — LIVE-BUT-GATED, not shadow

A lane goes **live the moment it migrates** — there is no "shadow the old pipe"
phase (that was an over-cautious mistake: it would keep the captain on the *worse*
engine while the new one spectates, and score against a flawed flow). The first
rung is safe **by construction**, not by shadowing:

- The lane is **propose-only** — nothing sends without the captain's approval. So
  going live risks no unwanted send; the worst case is a weak draft the captain
  skips (the same risk the old pipe already has). There is nothing for a shadow to
  protect against.
- Migrating a lane = the cabinet **presents its own drafts on the cabinet bot**, the
  captain approves/edits/skips **there**, and the **screenpipe twin is disabled**
  (kept intact as a one-command rollback). Verify the full path on the first real
  round (present → approve → `queue_draft` send).
- **Proof comes from this live-but-gated operation**, not a shadow. Every
  approve/edit/skip is a real ledger event; that track record is what later earns
  the lane the right to act *unattended* (the ladder climb to "I intend to" / "I've
  done"). The apprenticeship IS the gated-live phase.

Going live needs the bot token (for the live present). Each lane migrates one at a
time, real and reversible — never two engines running the same function.

## Telegram at go-live (concrete)

- The Cabinet's **one bot** is the target surface.
- Shadow phase: cabinet sends nothing; screenpipe's bot is unchanged. You keep
  getting briefs/drafts exactly as today.
- First flip (draft-reply → live): the cabinet bot presents drafts; **screenpipe's
  draft-reply is disabled.** The other screenpipe Telegram pipes stay on screenpipe's
  bot temporarily (you'll briefly have two bots — cabinet=acting, screenpipe=briefs)
  until each migrates, then it collapses to **one**.
- **Never** the same function pinging you from both.
