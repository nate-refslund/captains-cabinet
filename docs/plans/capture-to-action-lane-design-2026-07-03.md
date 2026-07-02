# Capture → Action Lane — design note (2026-07-03)

> **Status:** design, for the 07:30 briefing. Supersedes the draft-reply lane as the
> Cabinet's primary Captain-facing loop, per the pivot ruling in
> `shared/interfaces/captain-decisions.md` (2026-07-03). Reuses the existing binder
> gate, consequence ledger, and courses-of-action rule wholesale — this is a
> **re-aim of the payload**, not a new machine.

## 1. The pivot, precisely

**Before:** capture streams → the Cabinet drafts *replies* → Captain approves → send.
The Captain was in the send loop for every message; draft-lane was parked because
Nate handles his own comms.

**After:** capture streams → the Cabinet proposes *actions* → Captain approves →
the Cabinet **executes work**. Nate owns communication; the Cabinet owns the work
that falls out of communication — create/update a task, implement a feature, act on
a commitment, schedule a follow-up, close a decision.

One sentence: **the Cabinet stops writing what Nate should say and starts doing what
Nate's world implies needs doing.**

## 2. What is reused (do not rebuild)

| Seam | File | Role in the action lane |
|---|---|---|
| Proposal event | `framework/acting/loop.py:proposal_event(action=…)` | `action` is already parameterized (default `draft-reply`); action proposals set new `action` values (§4). |
| Binder gate | `framework/frontdoor/binder_wire.py` | `extract_pids` + pending-set cross-check + `handle_response` bind a Captain verdict to a proposal, record a superseding ledger event, then act. **Unchanged** — the payload differs, the gate does not. |
| Expiry | `loop.expire_event` | Un-acted action proposals expire honestly (verdict unknown, no outcome) — same hygiene that just cleared the 13 parked drafts. |
| Consequence ledger | `framework/fidelity/consequence.py:emit_consequence` | Proposal → decision → **outcome** lifecycle; graduation denominators read it. |
| Courses-of-action rule | `.claude/rules/courses-of-action.md` | Investigation bar (gather-then-propose) + propose **chains** not isolated actions + urgency tiers. Governs every action proposal by construction. |
| Task write | `framework/missions/` (supervisor/compiler/session_bridge) + `cabinet/scripts/task_sync_runner.py` | The canonical local work store the `task-create`/`task-update` action types write into (Monday/Jira/Linear remain optional TaskAdapter plugins per the PM-decoupling ruling). |
| Capture sources | `~/.screenpipe/pipes/{commitment-ledger,decisions-capture,meeting-intel}` (+ audio) | Already producing signals; the lane *reads* them, adds nothing upstream. |

## 3. The pipeline (gather-then-decide, one card per situation)

```
capture signal ──▶ GATHER (investigation bar) ──▶ PROPOSE action-chain ──▶ CARD ──▶ Captain verdict ──▶ EXECUTE ──▶ OUTCOME event
  (commitment,       full thread + audience +        LLM plans the whole      (·pid·,      send/edit:/skip:    task write /      (held/failed,
   meeting, decision,  person intel + open            situation as a step-      per-step     per step via the    impl kickoff /    M-1 amendment
   audio follow-up)    commitments + board +          ordered chain             gate)        binder              followup          on failure)
                       codebase pillar
```

**Trigger cadence:** the lane runs on the capture pipes' existing outputs (event-driven
where the pipe emits, else a short poll). No new capture; it consumes what the brain
already indexes.

**The investigation bar is mandatory** (courses-of-action §1): a proposal that can't
meet the bar names the gap instead of proposing. This is the recorded failure-mode fix
— never propose an action from a thin view.

**Chains, not isolated actions** (courses-of-action §2): a real situation is usually
`create task → schedule follow-up → close commitment`, not one step. ONE card per
situation, each step independently approvable.

## 4. The action-proposal object

Reuse `proposal_event`; extend `action` + `action_type` (the enum is extensible, sourced
from the shared classifier — `consequence.py` FIX-1):

| `action` | `action_type` | Executes | Hard-ceiling? |
|---|---|---|---|
| `task-create` | `task_write` | new row in the canonical work store (+ optional TaskAdapter mirror) | no |
| `task-update` | `task_write` | status/priority/field change on an existing item | no |
| `feature-impl` | `code_change` | spawns a lane-CEO build (worktree-isolated) against a spec | **deploy stays ceiling** |
| `followup-schedule` | `reminder_write` | a time-bound nudge (Reminders / brief queue) | no |
| `commitment-close` | `ledger_write` | marks an owed-by/owed-to commitment resolved with evidence | no |

**The hard ceiling is unchanged** (blueprint §hard-ceiling): `external_comms`,
`deploy_prod`, `spend`, `secrets`, `network_write`, `credentials_grant` never lift.
`feature-impl` may build and open a PR; it may **not** deploy. Comms stays Nate's — the
lane has **no** `external_comms` action at all (that is the whole point of the pivot).

## 5. M-1 baked in from day one — honest outcomes

The cp2 review's M-1 (outcome pre-emitted `ok` at decision time → `outcome_held_rate`
structurally blinded) must **not** be reintroduced. The action lane records outcomes for
real, because unlike a fire-and-forget send, an action has an observable result:

- On approve/execute: emit the superseding **outcome** event only after the executor
  returns — `held` if the task actually landed / the PR actually opened / the reminder
  actually set; **`failed`** (a superseding `outcome=failed` amendment) if the executor
  errored. The verdict ladder reads the truth, not the intention.
- This gives the graduation cells (officer × action_type) a real `outcome_held_rate`
  denominator — the machine-truth B2 phase needs exactly this to ever grant autonomy.

## 6. The card format (Chair-includes-pid, baked in)

Every action card carries the `·pid·` marker **and** the Chair echoes it whenever it
re-presents or argues about the card (the label-UX item from the first real replies).
Because the binder now cross-checks candidates against the open set (B-2 fix), a Captain
`send`/`ja`/`edit:`/`skip:` on either the card or the Chair's echo binds correctly.

```
🎯 Action for {situation} — {urgency-tier}

  situation: {one line, grounded in the gathered thread}
  chain:
    1. task-create "…"            [approve / edit / skip]
    2. followup-schedule …        [approve / edit / skip]
    3. commitment-close …         [approve / edit / skip]
  why: {the WHY — intent inference, never a leaked model quote}
  ·{pid}·
```

Per-step gate: the Captain can approve step 1, edit step 2, skip step 3 in one reply;
the binder records each as its own superseding event.

## 7. Autonomy ladder (propose-first → autonomous)

Graduation cells key on `(officer, lane, action_type)`. Every cell starts **propose-first**
(card every time). A cell graduates to **silent-act** only when its evidence clears the
Gate bar (blueprint: balanced probe, zero-regression, pass^k, READ-isolated holdout) —
and only for **low-blast action types** (`task-create`, `task-update`, `followup-schedule`).
`feature-impl` and `commitment-close` stay propose-first far longer; the hard ceiling never
graduates. Starvation (ledger-liveness) auto-demotes a cell whose evidence stops flowing.

## 8. Build order (F0 done ⇒ this is the next increment)

1. **B2.1 correlation-id standard** (already queued) — the join key threading capture
   signal → proposal → decision → outcome. The evidence plane needs it first.
2. **Action-proposal schema** — extend `proposal_event`/`action_type`; validate against
   the consequence schema; unit tests mirroring the binder suite.
3. **One capture adapter end-to-end** — start with `commitment-ledger` (highest-signal,
   already directional owed-by/owed-to): commitment → `task-create`/`followup-schedule`
   proposal → card → execute → outcome. Prove the whole spine on one source before fanning
   out to meetings/decisions/audio.
4. **Executor + outcome truth** (M-1): the `task_write` executor + the `outcome=held/failed`
   amendment. This is where honesty is won or lost.
5. **Graduation wiring** — cells start propose-first; the denominators fill from step 4.
6. Fan out the remaining capture adapters (meeting-intel, decisions-capture, audio).

## 9. What this retires / relocates

- **Draft-lane** (`run_draft_lane.py` presenter, `com.cabinet.draft-lane` plist): parked
  (plist `.disabled`). The `·pid·`/binder/expire machinery it pioneered is **inherited**
  by this lane, not discarded.
- **`queue_draft` brain-bridge outbound path**: the Cabinet no longer drafts outbound
  messages, so the only-outbound-path rule (`.claude/rules/brain-bridge.md`) is now moot
  for the Cabinet's own work — comms is Nate's. The rule stays as a guard (no officer may
  send), which the no-`external_comms`-action design enforces structurally.
- **Plan A A5** (never-lie reply-executor): re-aimed from "draft replies honestly" to
  "propose/execute actions honestly" — the never-lie discipline (§B dossier, no fabricated
  evidence) transfers directly to action outcomes.

## 10. Open questions for the Captain (07:30 queue)

1. **Task store of record:** confirm the canonical local work store (SQLite `officer_tasks`)
   is the write target and Monday board `5091706356` stays a *mirror* (PM-decoupling ruling
   already says yes — confirming it holds for action-writes specifically).
2. **feature-impl autonomy floor:** should `feature-impl` ever graduate past propose-first,
   or is "always card a code change" a permanent Captain preference? (My default: permanent
   propose-first for code; only task/followup graduate.)
3. **First capture source:** I propose `commitment-ledger` first (§8.3). Confirm, or point
   me at meeting-intel if the daily-scrum action items are higher value to you.
