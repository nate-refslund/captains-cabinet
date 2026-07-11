#!/usr/bin/env python3
"""One-time pivot hygiene (2026-07-03): expire the orphaned draft-lane proposals.

The Captain pivoted the Cabinet AWAY from draft-replies (the Captain handles replying)
toward proactive action proposals; the draft-lane presenter is parked. That
leaves draft proposals that were presented but will now NEVER receive a decision
dangling 'pending' forever. Post M-2 (ledger-liveness reads unwindowed) the
evidence-starvation dead-man correctly sees them (oldest ~270h) and would page
indefinitely — turning a real alarm into ignorable noise.

The honest terminal state for an abandoned, never-sent draft is 'expired'
(loop.expire_event: verdict unknown, NO outcome — the ladder neither climbs nor
records a lesson; nothing shipped). This appends one superseding 'expired' event
per open draft proposal on its identity tuple. Append-only; history preserved.

SAFETY: only proposals whose action == 'draft-reply' are touched. Any other
pending (e.g. a future action-proposal) is left untouched. Run with no args for
a dry run; pass --apply to write.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from framework.acting import loop  # noqa: E402
from framework.fidelity.consequence import emit_consequence  # noqa: E402

APPLY = "--apply" in sys.argv


def main() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pending = loop.pending_proposals()  # unwindowed
    drafts = [p for p in pending if str(p.get("action")) == "draft-reply"]
    other = [p for p in pending if str(p.get("action")) != "draft-reply"]

    print(f"pending total={len(pending)}  draft-reply={len(drafts)}  "
          f"other(preserved)={len(other)}")
    if other:
        for p in other:
            print(f"  PRESERVE lane={p.get('lane')!r} action={p.get('action')!r} "
                  f"subj={str(p.get('subject'))[:50]!r}")

    for p in drafts:
        pid = loop.proposal_id(p)
        # decided_at = the proposal's OWN ts (expire_event contract); reviewed_at
        # = the real audit moment of this hygiene sweep.
        ev = loop.expire_event(p, reviewed_at=now, decided_at=p.get("ts"))
        print(f"  {'EXPIRE' if APPLY else 'would-expire'} {pid}")
        if APPLY:
            emit_consequence(
                ts=ev["ts"],
                actor=ev["actor"],
                lane=ev.get("lane"),
                action=ev["action"],
                subject=ev["subject"],
                action_type=ev.get("action_type"),
                refs=ev.get("refs"),
                proposal=ev["proposal"],
                review=ev.get("review"),
            )

    if not APPLY:
        print("\nDRY RUN — re-run with --apply to write the expiry events.")
        return 0

    remaining = [p for p in loop.pending_proposals()
                 if str(p.get("action")) == "draft-reply"]
    print(f"\nAPPLIED. draft-reply pending now: {len(remaining)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
