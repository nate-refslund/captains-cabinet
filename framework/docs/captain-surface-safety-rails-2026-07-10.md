# Captain-surface safety rails (ARM C, 2026-07-10)

Spec of record: the Chair's master prompt "Make the Captain's Telegram surface
comms-MCP-native" (Captain-forwarded 2026-07-10; ratified as scope in
`shared/interfaces/captain-decisions.md` the same day) — §3.5 verify-at-fire,
§3.6 draft reconciliation + withdraw/supersede, §3.9 tiered escalation, under
the §6 foundation/instance split. Four rails, all foundation (`framework/`),
all launcher-neutral, personal sensing only via `framework.sources.get_source()`.

## Rail 1 — verify-at-fire gate on the send path

`framework/acting/fire_gate.py`, wired inside the single egress chokepoint
`framework/frontdoor/chair_drafts.deliver_draft` (what the binder calls on the
Captain's `send` reply; the instance autoreply wiring inherits it too).

At fire time the gate re-gathers through the sources seam:

| Evidence at fire                                      | Outcome |
|-------------------------------------------------------|---------|
| `captain_replied_since(slug, queued_ts)` is `True`     | CANCEL — the captain handled the thread himself (the worked **Alice case**) |
| `still_awaiting(slug)` is `False` (reply-lane records) | CANCEL — the thread no longer needs this reply |
| anything else (`None`, unbound source, probe error)    | FIRE — honest uncertainty never vetoes an explicit approval |

A cancel deletes the queued record, journals a `fire-cancel` row
(`draft_queue.journal_fire_cancel`, full record retained as the undo trail),
and returns `{"ok": False, "cancelled": True, "reason": <plain sentence>}` so
the Chair relays a plain-language line ("Not sent — you already replied to …
yourself"). `dry_run` reports a would-cancel verdict without removing;
`force=True` (an explicit "send anyway") skips the gate and says so.

- Default **ON** (it can only cancel on positive evidence); escape hatch
  `CABINET_VERIFY_AT_FIRE=0`.
- The `still_awaiting` cancel is scoped to reply-lane records (`lane` contains
  `reply`, or no `lane` — both current writers are reply flows) so a future
  proactive/outreach draft is never wrongly blocked.
- Both queue writers now stamp `queued_ts` (and the lane writer stamps `lane`):
  `chair_drafts.present_draft`, `run_draft_lane._store_draft`.

Regression test: `framework/frontdoor/tests/test_fire_gate_alice.py` (the
worked Alice case end-to-end at the chokepoint) +
`framework/acting/tests/test_fire_gate.py` (the decision matrix).

## Rail 2 — withdraw / supersede on the draft queue

`framework/acting/draft_queue.py` — the primitive `queue_draft`'s surface
never had (a stale draft could only be left untapped):

- `withdraw(id, reason, actor=…)` — remove a queued draft
  (`cabinet:draft:<id>`) with an honest reason; idempotent.
- `supersede(old, new, reason=…)` — withdraw in favor of a fresher draft.
- `withdrawal_of(id)` — why a draft is gone; `deliver_draft` consults it so a
  later `send` tap gets the real reason, never the generic
  "expired or already sent" miss (the root of the Alice confusion).
- `pending()` — the queued records still awaiting fire.

Every removal appends to `draft-queue-journal.jsonl`
(`$CABINET_DRAFT_QUEUE_DIR`, default `~/Library/Application
Support/cabinet/drafts`; dir 0700, file 0600, flock-serialized) carrying the
FULL record — the undo trail: a wrongly-withdrawn draft re-queues verbatim
from its row. Ids are allowlist-validated (`[A-Za-z0-9_-]{1,64}`) before any
key/journal use. Redis access is an injectable KV (argv-list `redis-cli`
default; tests run dict-backed).

Tests: `framework/acting/tests/test_draft_queue.py`.

## Rail 3 — draft reconciliation consumer (outbound capture)

`framework/acting/draft_reconcile.py` — retires stale queued drafts EARLY (the
fire gate is the last-instant backstop). Sweeps `draft_queue.pending()` and
asks the bound personal source whether the captain's ACTUAL outbound already
handled each thread:

- `source.available()` is `False` (null / clean-room) →
  `{"status": "source-unbound", "checked": 0, "withdrawn": 0}` — **honest
  empty**, touches nothing, never fabricates a closure.
- `captain_replied_since(slug, queued_ts) is True` → withdraw
  (actor `draft-reconcile`, plain reason naming the person).
- `still_awaiting is False` alone is recorded as corroboration only;
  withdraws only under `CABINET_RECONCILE_ON_RESOLVED=1` (a queued draft is
  inert at rest — the cheap error is to leave it).

Wired best-effort at the top of `run_draft_lane.main()` (5-min cadence;
`CABINET_DRAFT_RECONCILE=0` disables) and standalone:
`python3.12 -m framework.acting.draft_reconcile --json`.

Tests: `framework/acting/tests/test_draft_reconcile.py`.

## Rail 4 — tiered-escalation gate at the gateway entry

`framework/attention/escalation.py`, wired in `gate.decide` (step 2.2 — after
the standing-card identity path, so updates/closures of admitted situations
are exempt) and `gate.deliver` (the `bounce` execution). Officer entry:
`tools.send_card(..., escalation={...})`.

The law (§3.9): each tier exhausts before it rises. When armed, a NEW open
decision card (kind `action-card`; extend via `CABINET_ESCALATION_KINDS`)
must carry

```
escalation = {"lane_tried": …, "chair_tried": …, "needs_captain_because": …}
```

(all non-empty) or it **bounces back to the org**: nothing reaches the
Captain; the producing officer's tool result says `status="bounced"`, which
fields are missing, and how to fix it. Bounces are journaled
(`bounces.jsonl` in the attention dir) and best-effort org-evented
(`captain_gate_bounced`) for retro audit.

Exempt, always: floor classes (a safety page is never blocked), standing-card
edits, non-open states, non-decision kinds.

**DARK by default** — armed only by `CABINET_ESCALATION_GATE=1` (same deploy
discipline as the admission law: today's producers attach no proof yet;
arming before they do would bounce everything). Arming order: teach the
producers (lanes/Chair briefing composers) to attach proofs → flip the flag →
watch `bounces.jsonl` in the 48h retro.

Tests: `framework/attention/tests/test_escalation.py`.

## Flags (all four rails)

| Env | Default | Meaning |
|-----|---------|---------|
| `CABINET_VERIFY_AT_FIRE` | on | `0` disables the fire-time re-gather |
| `CABINET_DRAFT_RECONCILE` | on | `0` skips the lane's reconcile pass |
| `CABINET_RECONCILE_ON_RESOLVED` | off | `1` also withdraws when the thread resolved without a captain reply |
| `CABINET_ESCALATION_GATE` | off (dark) | `1` arms the exhaustion-proof requirement |
| `CABINET_ESCALATION_KINDS` | `action-card` | csv of captain-decision kinds subject to the gate |

## Foundation/instance notes

No captain name, path, board id, or estate detail lives in any of these
modules; the personal estate is reached only through
`framework.sources.get_source()` (tri-state contract, honest-empty when
unbound). No germline-locked file was modified: the wiring seams
(`gate.py`, `tools.py`, `chair_drafts.py`, `run_draft_lane.py`) are all
outside the germline census — no window-4 diff arises from these four rails
themselves. The WAVE-level window-4 deliverable (the 3 spec-listed locked-
file diffs) is explicitly deferred — see
`docs/proposals/germline-window-4-deferral-2026-07-10.md` (Captain to
ratify the deferral or order the diffs staged).
