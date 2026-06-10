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

## Scope

Universal: every officer, every preset, every Cabinet deployment. The
coordinating officer (Chair/CoS) audits adherence in retros; violations are
reflection material, not silent drift.
