# Pin design — Captain to ratify (captain-surface v2, 2026-07-10)

The master prompt (§5) + build spec (§3.4) called for BOTH pin designs
shipped behind an instance `pin_mode` knob plus a written recommendation.
This note is that recommendation, and records the deviation the branch
actually shipped, for the Captain to ratify or overrule.

## What shipped

ONE design: `framework/comms/surface/pin_lifecycle.py` — **adopt-standing-
card** (a hybrid of the prompt-literal `top_item` mode):

- the pin is the #1 ranked open decision's **own standing card** — the
  engine ADOPTS the item's existing message (`standing_message_id`) whenever
  the census knows one, and only sends-then-pins when none exists. Never a
  copy.
- auto-advance on engagement (reply/tap on the pinned message → unpin +
  advance — the dead-pin fix), replace only on a STRICT urgency upgrade
  (rank jitter never thrashes the pin), unpin at the wrong-by-tomorrow
  horizon (the item rides the census into the briefing), unpin on close.

No `pin_mode` knob shipped; `pin_mode: overview` (one live "⚑ N need you"
overview card, edited in place) is NOT built.

## Why adopt-standing-card over pin-as-copy

1. **Dead-pin-by-construction avoided.** Pinning a COPY of the #1 item
   creates two surfaces for one decision; answering the original leaves the
   pinned copy stale — the exact bug this wave exists to kill. Adopting the
   item's own card means the pin IS the live card: one message, one truth,
   its ✅ edit-in-place is the pin's own face.
2. **Notification churn bounded.** Telegram pin swaps emit service
   notifications. Adopt-mode swaps only on clear/urgency-upgrade — the same
   events that already page the Captain — never on wording re-renders.
3. **§5's goals met without a second renderer:** "the one thing to act on
   now" is literally the top item, engagement is observable (D12 feed rows)
   and consumed, auto-advance is real.

## Why the knob was deferred (the deviation)

`pin_mode: overview` needs the overview card renderer + a second lifecycle
(edit-in-place on every census change) — none of which any other §3 piece
consumes. Shipping a second, untested mode behind a knob in the same wave
as the first real pin lifecycle would double the surface under review while
the engine itself is still dark (nothing schedules `run_surface_tick`;
arming is a deployment decision). The knob is a small additive follow-up
once the shipped mode has real-Telegram acceptance evidence.

## Captain options

- **Ratify as-is** — adopt-standing-card is the one pin design; overview
  mode dropped (or deferred until wanted).
- **Order the knob** — `pin_mode: adopt | overview` in
  `instance/config/comms-surface.yml`; overview renderer ships as a
  follow-up commit on this branch before merge.

Recorded as a PR-#135 review item; nothing merges without this ruling.
