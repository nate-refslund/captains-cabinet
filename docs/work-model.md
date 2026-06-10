# Cabinet Work Model — Stream / Missions / Intake

> Captain-agreed 2026-06-10. The contract for how the Cabinet's hq instance
> classifies and moves work. Referenced by `instance/config/outcomes.yml`
> (header) and the clone-convergence plan (P2/P3). Products are **lanes**,
> not outcomes — a product never "finishes"; only outcomes do.

## The three work classes

Every piece of work in a lane (polads, stephie-stepnetwork, system-self) is
exactly one of:

| Class | What it is | Where it lives | Lifecycle |
|---|---|---|---|
| **STREAM** | Continuous product work: bugs, tasks, small features | Monday Tasks board **5091706356** (per-product filter via the dev-tasks plugin) | claim → execute → close back to Monday; never ends |
| **MISSIONS** | Bounded, Captain-ratified state changes | `instance/config/outcomes.yml` (rolling window, 1–2 active per lane) | draft → active → achieved → retired |
| **INTAKE** | Classification machinery feeding the other two | Scheduled CoS routine (cron trigger, P3) | runs forever; never an outcome |

Never collapse these. Stream wrapped in outcomes produces zombie missions;
intake wrapped in an outcome produces a mission that can never achieve.

## STREAM — continuous product work

- The Monday Tasks board (5091706356) is the **canonical backlog** per
  product. Officers claim items via the dev-tasks plugin, execute, and close
  back to Monday.
- **Close-back rule** (mirrors the existing "Linear/board state must always
  reflect reality" rule): the moment an officer learns a tracked item is
  done, its Monday status moves — same turn, no "please close it" prompt.
  A drifting board poisons briefings, retros, and priority math.
- **Autonomy**: propose-first per the autonomy manifest (vault
  `6-Areas/autonomy-manifest.md`) until a lane graduates — status writes and
  claims are proposed to the Captain, then applied. Graduation lifts
  propose-first for stream writes only; the P4 hard ceiling
  (external_comms / production deploys / spend) never lifts.
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

**Renewal loop** — slots refill, products never finish:
1. An outcome's criteria all carry verified evidence → **CoS proposes
   `achieved`** to the Captain; Captain confirms.
2. The freed slot triggers succession: **CPO's existing 12h backlog-refine
   routine drafts a successor** from the Monday epic queue + stream pressure
   (what the lane's stream is straining against).
3. CPO **proposes the successor to the Captain (Telegram)**; **Captain
   ratifies**; the successor goes active in the freed slot.

Roles in one line: CPO proposes successors, CoS proposes `achieved` on
verified evidence, the Captain ratifies both. At AI speed these are
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

A scheduled CoS routine (cron trigger; implemented in P3 of the
clone-convergence plan — `docs/clone-convergence-plan-2026-06-09.md`):

1. **Sweep** sources: Monday Nate's-Todos board **5098236573** + any
   unclassified stream items on the Tasks board.
2. **Classify** each item to a lane (or decline with reason).
3. **Gather-then-decide**: pull the evidence (brain search, Monday context,
   recent activity) *before* proposing — never propose from a stale view.
4. **Propose-only** via the brain MCP `ask_nate` human gate. Approved items
   become **stream tasks** (routed to the lane's Monday backlog) or
   **outcome proposals** (handed to CPO for the renewal loop). No
   auto-claiming, no execution, no Monday writes without per-item approval.

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
