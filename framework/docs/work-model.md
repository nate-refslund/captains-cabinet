# Cabinet Work Model — Stream / Missions / Intake

> Captain-agreed 2026-06-10. The contract for how the Cabinet's hq instance
> classifies and moves work. Referenced by `instance/config/outcomes.yml`
> (header) and the clone-convergence plan (R2/R3). Products are **lanes**,
> not outcomes — a product never "finishes"; only outcomes do.

> **AMENDMENT 2026-07-02 (Captain-ruled — PM decoupling).** The foundation's
> canonical work store is a LOCAL task board (SQLite; Neon optional, never
> required). External PM tools (Monday, Jira, Linear) are optional
> `TaskAdapter` plugins: local wins, the adapter mirrors. For THIS deployment,
> Monday Tasks board 5091706356 is the **STEP collaboration mirror**, not the
> canonical store — Monday's only remaining surface is PM (dev-tasks plugin,
> todos, commitment→task promotion, completion-tracker closes, briefs reading
> due tasks via the adapter). All Monday-born SYNTHESIS re-points to the vault
> per the RE-POINT-TO-VAULT ruling (plan A A3-phase, shadow-parity per pipe;
> spec: `docs/plans/EXECUTION-STATUS.md` §Captain-ratified additions).
> Until each pipe's re-point lands, existing pipes keep writing Monday — the
> CONTRACT changes now, implementation follows the plan. Statements below that
> name Monday as "canonical" are superseded by this amendment.

## The three work classes

Every piece of work in a lane (polads, stephie-stepnetwork, system-self) is
exactly one of:

| Class | What it is | Where it lives | Lifecycle |
|---|---|---|---|
| **STREAM** | Continuous product work: bugs, tasks, small features | Local task board (canonical, Amendment 2026-07-02); mirrored to Monday Tasks board **5091706356** via TaskAdapter (per-product filter via the dev-tasks plugin) | claim → execute → close locally; adapter mirrors; never ends |
| **MISSIONS** | Bounded, Captain-ratified state changes | `instance/config/outcomes.yml` (rolling window, 1–2 active per lane) | draft → active → achieved → retired |
| **INTAKE** | Classification machinery feeding the other two | Scheduled CoS routine (cron trigger, R3) | runs forever; never an outcome |

Never collapse these. Stream wrapped in outcomes produces zombie missions;
intake wrapped in an outcome produces a mission that can never achieve.

## STREAM — continuous product work

- The **local task board is the canonical backlog** per product (Amendment
  2026-07-02); the Monday Tasks board (5091706356) is its STEP collaboration
  mirror via the TaskAdapter. Officers claim items locally (today still via
  the dev-tasks plugin against Monday until the adapter cutover lands),
  execute, and close locally; the adapter mirrors the close.
- **Close-back rule** (mirrors the existing "Linear/board state must always
  reflect reality" rule): the moment an officer learns a tracked item is
  done, its Monday status moves — same turn, no "please close it" prompt.
  A drifting board poisons briefings, retros, and priority math.
- **Autonomy**: propose-first per the autonomy manifest (vault
  `6-Areas/autonomy-manifest.md`) until a lane graduates — status writes and
  claims are proposed to the Captain, then applied. Graduation lifts
  propose-first for stream writes only; the hard ceiling (R4:
  external_comms / production deploys / spend) never lifts.
- Stream items are **never wrapped in outcomes**. If a cluster of stream
  items amounts to a verifiable state change *and* needs orchestration
  structure (see the campaign test under MISSIONS), that's a candidate for
  a mission slot via the renewal loop — the items move under the outcome,
  not the other way around.
- **Stream SLOs** (control loops, not missions): standing quality bars —
  e.g. "Critical items triaged within 24h", "Needs-Refinement queue ≤ N" —
  are invariants to keep true, not state changes to achieve. They are
  monitored by the CoS briefing + intake routines and flagged on breach;
  they never appear in `outcomes.yml`.

## MISSIONS — the rolling window

`outcomes.yml` holds a **rolling window of 1–2 active bounded outcomes per
lane**. It is not a roadmap, not a backlog mirror, not a wish list.
**The window is a cap, not a quota** — a lane with zero active outcomes is
healthy (officers work the stream); the renewal loop proposes a successor
only when something campaign-shaped exists. Silence is a valid state.

**Inclusion test** (prong 1): the outcome describes a **verifiable state
change**, never an activity. Ask: "can a verifier look at evidence and say
*the world changed from X to Y*?" If the honest phrasing is "keep doing X",
it fails.

**Campaign test** (prong 2 — both must pass, Captain-refined 2026-06-10):
the work needs **orchestration structure the stream cannot give** —
ordering between steps, verification gates, risk-tiered approvals,
cross-role handoffs. A batch of stream items with a bow on it is NOT a
mission: Critical bugs get pulled from the stream because they are
Critical, not because an outcome wraps them. Expected density: a handful
of genuine campaigns per product per year (launches, migrations,
compliance pushes, big features) — proposed *to* the Captain, never
authored *by* him.

Good examples:
- *"PolAds v1.0 staging closeout and production release"* — the world
  changes from "CI red, UAT bugs open, no prod" to "CI green, bugs closed,
  v1.0 live". Verifiable, then done.
- *"Typed policy engine promoted from shadow to enforcing"* — a one-way
  state flip with parity proof and a soak. Verifiable, then done.

Bad examples:
- *"Standing intake: CoS triages Captain-dropped tasks into proposals"* —
  an activity that never completes; it can never reach `achieved`. That is
  intake machinery (see below), not a mission.
- *"Keep PolAds healthy / maintain the backlog"* — stewardship of a lane.
  That is the stream itself; wrapping it in an outcome creates a permanent
  zombie slot.

**Lifecycle**: `draft → active (Captain-ratified) → achieved → retired`.

**Renewal loop** — slots refill, products never finish. The loop is
defined by role *functions*, not roster titles (the coordinating role is
CoS in the functional preset, the Chair in the portfolio preset; the
lane's product-owner role is the CPO in the functional preset, the
lane-CEO in the portfolio preset):
1. An outcome's criteria all carry verified evidence → **the coordinating
   role proposes `achieved`** to the Captain; Captain confirms.
2. The freed slot triggers succession: **the lane's product-owner role
   drafts a successor** from its lane's epic queue + stream pressure
   (what the lane's stream is straining against).
3. **The coordinating role consolidates the proposal into its briefing's
   decision queue**; **the Captain ratifies**; the successor goes active
   in the freed slot.

Roles in one line: the lane's product-owner role proposes successors, the
coordinating role proposes `achieved` on verified evidence and carries
both to the Captain, the Captain ratifies. At AI speed these are
**gates, not calendars** — succession happens minutes after confirmation,
not at sprint boundaries.

**Recurring waves are stream, not monthly missions.** UAT/feedback waves
recur; authoring "June wave", "July wave", … outcomes forever would be
pure ceremony (Captain-attention waste). `outcome-polads-003` runs **once
as a bootstrap mission** — maximally legible work while the fleet earns
trust — and its retirement is the handover: subsequent wave items flow
through the stream, and the recurring quality bar lives as **stream SLOs**
(see STREAM), never as new outcomes. The outcome layer is also the
**autonomy ramp**: early on, more work is mission-shaped because missions
are verifiable and legible; as lanes graduate, proportionally more flows
as plain stream.

## INTAKE — machinery, never a mission

A scheduled CoS routine (cron trigger; implemented in R3 of the
clone-convergence plan — `docs/clone-convergence-plan-2026-06-09.md`):

1. **Sweep** sources: Monday Nate's-Todos board **5098236573** + any
   unclassified stream items on the Tasks board.
2. **Classify** each item to a lane (or decline with reason).
3. **Gather-then-decide**: pull the evidence (brain search, Monday context,
   recent activity) *before* proposing — never propose from a stale view.
4. **Propose-only** via the brain MCP `ask_nate` human gate. Approved items
   become **stream tasks** (routed to the lane's Monday backlog) or
   **outcome proposals** (handed to the lane's product-owner role for the
   renewal loop). No auto-claiming, no execution, no Monday writes without
   per-item approval.

Intake is **removed from `outcomes.yml`** (formerly `outcome-adhoc-001`)
and is never re-added as an outcome.

## Why not standing outcomes (decision rationale, 2026-06-10)

- **Lifecycle semantics**: the outcome lifecycle is
  `draft → active → achieved → retired`. A standing outcome is deliberately
  non-terminating — it can never reach `achieved`, so it sits as a permanent
  exception every consumer of the file must special-case.
- **OVI integrity**: a never-achievable outcome pollutes outcome-velocity
  metrics — it is permanent denominator with no possible numerator, and it
  masks real mission throughput per lane.
- **Captain's product-vs-project insight** (2026-06-10): products are lanes,
  not outcomes. Continuous work (stream, intake) belongs to the lane's
  standing machinery; `outcomes.yml` is reserved for bounded state changes
  the Captain can ratify, verify, and retire. One file, one semantics.

## Pipe disposition — the perception estate

> Convergence contract for deployments that pair the Cabinet with a
> perception estate (scheduled pipes feeding a personal knowledge vault).
> Role wording is by FUNCTION: *the coordinating role* is CoS in the
> functional preset and the Chair in the portfolio preset; *the lane's
> product-owner role* is the CPO in the functional preset and the
> lane-CEO in the portfolio preset.

Every perception pipe gets exactly one disposition:

**KEEP-CAPTURE** — the senses. Pipes whose job is getting reality into
the vault and keeping the machinery observable: message/email/calendar
sync, OCR/transcript capture, embeddings indexing, identity/speaker
resolution, pipe-health monitoring — **including the Telegram bot as
approval-gate infrastructure** (the human gate every proposal rides
through is capture-side plumbing, not judgment). The Cabinet never
replaces capture; it consumes it.

**KEEP-REFLEX** — deterministic bookkeeping that acts on *state, never on
people*: commitment extraction + evidence-gated auto-close, completion
tracking (marking done things done in their source systems), routing
time-bound items onto the reminder/task surfaces, the task ledger, and
feedback/correction detection. Reflexes are cheap, legible, and have no
judgment to migrate. They adopt the consequence-event shape
(`framework/docs/consequence-ledger.md`) but stay where they are.

**MIGRATE-TO-CABINET** — judgment and human-facing composition. These
move to officers, because they need the investigation bar and
course-of-action discipline (`.claude/rules/courses-of-action.md`) that
one-shot pipes structurally cannot meet:

- Reply drafting → **retired as a Cabinet function (2026-07-03 pivot: the
  Captain owns communication).** The same capture signals now feed the
  capture→action lane — proactive *action* proposals (create/update a task,
  implement, follow up, close a commitment) through the binder gate, not
  outbound message drafts. The brain bridge's `queue_draft` gate stays a
  guard (no officer may send), enforced structurally by the lane having no
  external-comms action at all. See
  `docs/plans/capture-to-action-lane-design-2026-07-03.md`.
- Commitment nudges → the coordinating role's founder-accountability
  protocol (single owner, no pile-on).
- "What needs you now" digests → the coordinating role.
- The morning/evening brief family → the coordinating role's scheduled
  briefings.
- Pre-meeting briefs → the coordinating role's calendar routine.
- Relationship radar → a coordinating-role routine (decision-aware, as
  today).
- Inbox-triage *proposals* and decision dialogues → the coordinating
  role; the deterministic detection halves stay perception-side as
  reflexes.
- Research/idea pipes → lane research crews (spawned subagents under the
  lane's owner role).

**Retirement rule** — per-pipe shadow parity, never big-bang: a migrating
pipe keeps running while its Cabinet replacement shadows it; only when
the replacement demonstrates parity on real traffic does the perception
side's architect loop retire the pipe. One pipe at a time, each
retirement reversible by re-enabling the pipe.

## Proposal hygiene

> Applies to every proposal-emitting surface — officers and surviving
> pipes alike. The operating pattern is
> `.claude/rules/courses-of-action.md`; this section is its work-model
> contract. Rationale: under one-card-per-*action*, the measured result
> was a **51% unanswered proposal backlog** — attention died of
> fragmentation, not volume.

- **Urgency tiers** — every proposal carries exactly one:
  - `ping-now`: time-critical; would be wrong or worthless by tomorrow.
  - `batch-into-next-briefing`: the DEFAULT. Rides the next scheduled
    briefing's decision queue.
  - `FYI-digest`: no decision needed; folded into the digest section.
- **ONE card per situation, showing the full course of action** — the
  whole plan-chain the situation needs (reply → task → follow-up →
  close commitment), with a per-step gate so the Captain can approve,
  edit, or skip each step. Never split one situation across multiple
  pings; never propose step 1 while silently planning the rest.
- **Stale proposals auto-expire into the briefing** — a proposal not
  acted on by the next scheduled briefing folds into that briefing's
  decision queue as one line with a link (and its consequence event
  records `proposal.decision: expired`). It is not re-pinged as a fresh
  message.
- **Never re-ask answered items** — check the decision trail and prior
  proposals first; if the Captain already answered in any channel, apply
  the answer and cite it.
