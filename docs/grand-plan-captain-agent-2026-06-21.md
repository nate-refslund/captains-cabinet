# Grand Plan — Captain-Configurable Autonomous Agent (the Convergence)

_2026-06-21. Supersedes the "clone fidelity" framing as the primary goal._

## North Star (revised today, with Nate)

**A captain-configurable AI agent (the Cabinet) that does valuable work, serves the
captain's intent, and speaks in the captain's voice — climbing an autonomy ladder on
proven outcomes.** The "Nate clone" is *this deployment's instance*, not the product.
Voice-fidelity is a **capability**; intent-served valuable action is the **product**
(general, sellable, multi-tenant).

**Why the shift (today's evidence):** chasing exact-response *prediction* produced a
benchmark that is capped (action-coupled replies a predictor can't know) and measures
*mimicry*, not service. The honest read of the clone: **strong voice, mostly-served
intent, real gaps only on substance/knowledge an _actor_ would have.** So: stop cloning
responses; build the intent-serving, voice-capable, value-creating agent — and let it
**act** (and remember its own acting), because that is the only path to being close to
the captain.

## Architecture — the Convergence

- **CABINET = the BRAIN.** Cognition, multi-agent orchestration, acting, governance
  (ladder + authority matrix + consequence ledger). **The ONE surface the captain talks
  to** (one Telegram bot). You command the thing that thinks and acts.
- **SCREENPIPE = the SENSES + MEMORY.** Capture (Teams/email/meetings/screen), the vault,
  embeddings, reflections. **Read by the Cabinet via the brain MCP bridge.** Never the
  surface.
- **Brain MCP** = the bridge (vault search, person intel, commitments, `queue_draft`
  outbound gate, reasoning log). Already built, already scoped to officers.

## The autonomy ladder (= the authority matrix, made legible)

| Rung | Clone behavior | = matrix cell |
|---|---|---|
| ~~Tell me / I see / I think~~ | — skipped — | the clone is *capable* day one |
| **I would like to** | proposes, waits for approval | propose-first |
| **I intend to** | announces, acts unless vetoed | veto-window |
| **I've done** | acts on reversible, reports after | auto-when-proven (reversible) |
| **I've been doing** | acts, reports periodically | fully graduated |

Per-**lane**, climb one rung when N outcomes the review-loop confirmed served intent.
Capability is given; **trust is earned.** Reversible config the clone reprograms itself
from chat; safety-critical code stays captain-gated (the line = the authority matrix).

## Reconciling the previous intentions

- **Fidelity / prediction harness (F):** DEMOTE to a **regression guardrail** (catch
  voice/values drift). Keep the leak-safety + honest-measurement work — it stands. Finish
  honest-ifying it (kill the token-floor, ensemble judge, bucket action-coupled cases) at
  **lower priority** — enough to be a trustworthy drift alarm, not the headline. Stop
  chasing the %.
- **Authority matrix (A) + consequence ledger:** ELEVATE to **primary** — the real
  fitness (act → outcome → climb). This is where the energy goes now.
- **Data foundation:** DONE as substrate (Teams capture fixed, retrieval improved,
  participants backfilled). Remaining items (meeting speaker-ID) are screenpipe-side,
  as-needed.
- **Productize (P):** MORE central now (the assistant *is* a product) — but after the
  acting loop proves out.

## Screenpipe pipes disposition (Nate's Q — ~70 pipes, ~22 on Telegram today)

| Class | Examples | Disposition |
|---|---|---|
| Capture / senses | teams/msgraph/gmail-incremental, conversations-sync, meeting-intel, embeddings, teams-ocr, product-ops, commit-stream | **STAY** — substrate; Cabinet reads via brain MCP |
| Memory / reflection | nate-model, voice-profile, self-knowledge, decisions-capture, reasoning-review, retrodiction | **STAY** — memory layer |
| Proactive surfacing (briefs, relationships) | morning-brief, day-recap, pre-meeting-brief, ask-my-brain, relationship-radar, top-of-mind, idea-tracker, monday-* | **RELAY now, ABSORB later** — Cabinet CoS produces these reading screenpipe data; near-term relay through the one bot, don't rebuild day 1 |
| Reactive acting | **draft-reply**, commitment-ledger, inbox/feedback-triage, todo-list-assistant, completion-tracker | **draft-reply → FIRST cabinet acting lane** (migrate). Others read/acted via brain MCP, absorbed as lanes prove out |
| Governance / meta | architect, autonomy, reasoning-review, pipe-health | Cabinet governance absorbs; pipe-health stays (infra) |

**Principle:** capture + memory + reflection **stay** in screenpipe (substrate). Acting +
orchestration + the **surface** are the Cabinet. Briefs/relationships become Cabinet
capabilities reading screenpipe — relayed near-term, absorbed over time. **Nothing that
works gets rebuilt; it gets re-fronted through the one surface.**

## The path (sequenced by dependency, not calendar)

**Phase 1 — Wire the first acting lane (the apprenticeship foundation).**
- Cabinet officer (clone) drafts replies, reading screenpipe memory via brain MCP.
- Presents on the **one Cabinet Telegram**; captain approve / edit / skip / instruct.
- The **3-way message router**: instance-instruction (→ act + open task + register
  commitment), standing-policy (→ reply-gate + captain-patterns + digest),
  correction (→ drafting-lessons + nate-model).
- Each interaction → consequence ledger (proof) + lessons/policy. Lane =
  `send-1to1-reply`, starts at **"I would like to"** (propose; nothing sends unattended).
- Re-front the `queue_draft` approval gate to the Cabinet Telegram.

**Phase 2 — The apprenticeship week.**
- Captain routes everything through the one Telegram. Dense labeled signal
  (approve/edit/skip/policy). The lane climbs **"I would like to" → "I intend to"**
  (veto window) on proven approvals. Prediction harness runs in the background as the
  drift guardrail.

**Phase 3 — Open lanes + proactive-doing.**
- More reversible lanes open as proof accumulates.
- **Proactive-doing** switches on: the org runtime runs missions/outcomes continuously
  ("paid by the minute"). Requires `outcomes.yml` defined.
- Briefs/relationships absorbed into Cabinet proactive capabilities.

**Phase 4 — Productize.**
- Captain-configurable (preset framework), two install flavors (mac+screenpipe /
  server+docker), private-data layer.

## Safety (unchanged, load-bearing)

Ladder + authority matrix: reversible auto, veto window, **irreversible always gated,
money always gated**, kill switch. Germline protection. One approval gate. Acting starts
where the worst case is a **rejected draft**.

## Immediate next steps

1. Design the Cabinet acting lane (officer draft → Cabinet Telegram → ledger + router).
2. Build it (workflow: parallel components + adversarial verify).
3. Re-front `queue_draft` approval to the Cabinet surface.
4. Dry-run the loop end-to-end (no real sends) → then the apprenticeship week.
