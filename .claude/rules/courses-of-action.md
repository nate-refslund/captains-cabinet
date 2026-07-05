# Courses of Action Rule (universal operating pattern)

The Captain's recorded corrections document a repeated failure mode: officers
and loops proposing a single isolated action from thin context — replying to
a thread without knowing its full audience, nudging about something already
resolved, proposing step 1 of a situation that obviously needs steps 2–4.
This rule is the standing fix. It is mandatory for **every officer, every
loop, every preset** whenever a proposal or action touches the Captain's
world (messages, commitments, tasks, calendar, boards, external comms).

The pre-tool-use hook treats this file as **germline** (read-only for
officers and loops): propose changes to the Captain; only the Captain
applies them.

## 1. Investigation bar — gather, then propose

Before ANY proposal touching the Captain's world, assemble ALL of the
following that the situation implicates:

- **The full thread** — every message in the conversation, not just the
  latest, **plus the complete To/CC audience**. A reply drafted without the
  audience is malformed by definition.
- **Person intel** for each counterparty (via the brain MCP person-intel
  surface where configured).
- **Open commitments** in both directions (owed by / owed to the Captain)
  touching the person or topic.
- **Task-board state** — the lane's backlog and any tracked item this
  situation touches or should touch.
- **The codebase pillar** when the matter is technical — indexed
  architecture / commits / deployment / schema, not memory of the code.
- **Drafting lessons and the captain model** via the brain MCP — these
  inform tone and judgment and must never be quoted into anything outbound
  (see `.claude/rules/brain-bridge.md`).

**If the bar cannot be met** — a source is unreachable, intel is missing,
the thread is truncated — **say exactly what is missing instead of
proposing.** A named gap is useful; a proposal built on a partial view is
the recorded failure mode.

## 2. Courses of action — propose chains, not isolated actions

- Real situations rarely need exactly one action. Propose a **course of
  action**: the full plan-chain the situation needs, in step order — e.g.
  *reply → create task → schedule follow-up → close commitment*.
- **ONE proposal card per situation**, carrying the whole chain with a
  **per-step gate** (the Captain can approve, edit, or skip each step
  independently). Never split one situation across multiple pings, and
  never propose step 1 while silently planning the rest.

  **Exception — reversible-with-undo steps (`pm_write` / `calendar_write`).**
  Per the EARN-DEMOTION ruling (captain-decisions.md, 2026-07-03/04), a step
  whose action_type is in an `act_with_undo` class does not wait on a
  pre-approval gate: it ACTS immediately (write-ahead journaled, executed,
  told after) and its **per-step gate BECOMES a per-step undo handle on the
  receipt** — the Captain reverses it with `undo [n]` inside the 48h window
  instead of approving it beforehand. Every gated step in the SAME chain
  (anything outbound, deploy, spend, `officer_dispatch`, or any hard-ceiling
  step) still carries its ordinary pre-approval per-step gate; a mixed chain
  keeps both — acted steps show as done-with-undo, gated steps as awaiting.
  Under the root/guardian table this is the ONLY relaxation. Under an
  ATTESTED sovereign posture (germline amendment `apply sovereign posture`,
  2026-07-05) the matrix's `postures.sovereign` table is the relaxation
  surface instead: `reversible` steps act (`auto`, journaled where inverses
  exist), `internal_comms` / `deploy_nonprod` steps act-and-tell
  (`notify_after` — the digest line IS the audit), and hard-ceiling steps
  resolve `standing_grant` — acting ONLY under a Captain-signed, schg-locked
  standing grant with its hard-scope predicate satisfied, otherwise the step
  gates, files a `NEED-<hex>`, and the chain proceeds without it. External
  recipients stay per-item Captain-approved in every posture (ACT-AND-DRAFT,
  captain-decisions.md 2026-07-04). No `instance/config/posture.yml` =
  guardian, today's rules. The investigation bar (§1) and one-card
  discipline are unchanged in every posture.
- A single-step chain is legitimate when that is honestly all the situation
  needs — but check the chain candidates first: does this also need a task
  created? a follow-up scheduled? a commitment closed? a board status
  moved? If yes, they belong in the same card.

## 3. Proposal hygiene

- **Urgency tiers** — every proposal is tagged exactly one:
  - `ping-now` — time-critical; would be wrong or worthless by tomorrow.
  - `batch-into-next-briefing` — the DEFAULT. Rides the next scheduled
    briefing's decision queue.
  - `FYI-digest` — no decision needed; folded into the digest section.
- **Never re-ask answered questions.** Check the decision trail and prior
  proposals before asking; if the Captain already answered — in any channel
  — apply the answer and cite it.
- **Stale proposals auto-expire into the briefing.** A proposal not acted
  on by the next scheduled briefing is folded into that briefing's decision
  queue as one line with a link — it is not re-pinged as a fresh message.
- **Acted steps are told, not asked.** A reversible-with-undo step that already
  acted is reported in the digest's ✅ ACTED section — one line rendering the
  EXACT written content (what a colleague will actually see), its receipt id,
  and its `undo [n]` handle. It is never phrased as a question and never
  re-pinged. A cell's acted lines quiet to a weekly rollup only after ≥3
  explicit Captain 👍 confirmations on that cell (TTL survival alone never
  quiets it). Monday's own native task notifications are harmless and internal
  (captain-decisions.md, 2026-07-04) and are not themselves an outbound step.

## Scope

Universal: every officer, every preset, every Cabinet deployment. The
coordinating officer (Chair/CoS) audits adherence in retros; violations are
reflection material, not silent drift.
