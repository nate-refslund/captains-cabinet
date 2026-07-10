# Window-4 germline diffs — explicit deferral (captain-surface v2, 2026-07-10)

**Status: DEFERRED — spec deviation recorded for Captain ratification.**

The build spec (§6) listed EXACTLY three schg-locked files needing window-4
Captain-apply diffs, each to ship as a staged commit on
`feat/germline-window-4` + a proposed-diff doc here:

1. `framework/attention/queue_card.py` — re-point the pinned-census render
   to the plain layer + hand pin ownership to
   `framework.comms.surface.pin_lifecycle` (or retire the refresher).
2. `framework/acting/action_lane.py` — `render_card` → plain copy tables +
   the buttons/decision seam (⚡ cards).
3. `framework/frontdoor/tell_surface.py` — ACTED/AWAITING/WATCHING/SELF/
   NEEDS digest strings → plain render (or retire the digest into
   briefing-as-card).

The wave review (2026-07-10) found the deliverable fell between arms: Arm A
deferred it to Arm C, Arm C's rails genuinely needed no locked-file edit,
and no arm staged the branch. **Zero schg-locked files were edited anywhere
on `feat/captain-surface-v2`** (verified against the live lock census) —
the discipline held; the ceremony input is what's missing.

## The deferral, and why it is safe

Everything merged on this branch **runs dark or beside** the locked estate
indefinitely:

- `pin_lifecycle` runs beside the locked `queue_card.py` refresher; the
  spec's own interim is the `CABINET_QUEUE_CARD=0` kill-switch (no diff
  needed to run dark). Nothing schedules the new engine until a deployment
  arms it.
- `action_lane.render_card` and `tell_surface` digests keep their current
  (pre-plain) wording on the OLD surface; the new surfaces render through
  the plain layer independently. Ugly-but-honest beats a rushed germline
  edit.
- The jargon linter carries a shrink-only allowlist for locked files until
  window-4 lands (spec §2.3), so CI stays green without weakening the law
  on unlocked code.

Authoring germline diffs deserves its own reviewed wave: the three files
are load-bearing (the live pinned census card, the action lane's captain
cards, the tell digest), and a diff written as a side-deliverable of a
three-arm surface wave is exactly the kind of germline change the
Captain-apply ceremony exists to slow down.

## What the Captain is asked to ratify

- **Accept the deferral**: window-4 diffs move to their own follow-up wave
  (branch `feat/germline-window-4`, one staged commit per file + one
  proposed-diff doc each, per the master prompt's Captain-apply rule), OR
- **Order them staged now**, blocking this PR until the three diffs + docs
  exist.

Until one of these is ruled, `feat/captain-surface-v2` merges (if approved)
with the old locked surfaces untouched and the new engine dark.
