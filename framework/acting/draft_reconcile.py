"""framework.acting.draft_reconcile — reconcile queued drafts against the
captain's ACTUAL outbound (captain-surface master prompt §3.6, 2026-07-10).

THE CONSUMER HALF of the Sofie fix: the verify-at-fire gate
(``framework.acting.fire_gate``) catches a stale draft at the last instant;
this consumer retires it EARLY, so the captain's queue stays honest to reality
between fires. It sweeps the queued-draft store (``draft_queue.pending()``)
and asks the personal-sensing seam whether the captain already handled each
thread himself:

    src = framework.sources.get_source()          # the seam — never hardcoded
    src.captain_replied_since(slug, queued_at)    # his real outbound, captured

``True`` → the queued draft is withdrawn (``draft_queue.withdraw``, journaled
with the full record as the undo trail) with a plain reason.

HONEST-EMPTY WHEN UNBOUND: a deployment with no personal source
(``NullPersonalSource``, ``available() == False``) returns
``{"status": "source-unbound", "checked": 0, "withdrawn": 0}`` and touches
NOTHING — reconciliation never fabricates a closure it cannot observe.

CONSERVATIVE BY DEFAULT: only a positive ``captain_replied_since == True``
withdraws. A ``still_awaiting == False`` alone (thread resolved some other
way) is recorded as corroboration but does not withdraw unless
``CABINET_RECONCILE_ON_RESOLVED=1`` — at reconcile time a queued draft is
inert (the fire gate still guards the actual send), so the cheap error is to
leave it, never to over-delete.

Wiring: called best-effort at the top of ``run_draft_lane.main()`` (the 5-min
lane cadence; ``CABINET_DRAFT_RECONCILE=0`` disables) and runnable standalone
(``python3.12 -m framework.acting.draft_reconcile --json``) for cron.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Repo root on sys.path so `from framework...` resolves when this file is run
# directly (cron passes a bare path, not `-m`). Derived from THIS file —
# parents[2] = the tree containing framework/ — never a hardcoded absolute
# (matches run_draft_lane.py:39).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.acting import draft_queue, fire_gate


def reconcile_queue(*, source=None, kv=None, limit: int = 200) -> dict:
    """One reconciliation pass over the queued-draft store. Returns
    ``{"status": "ok"|"source-unbound", "checked": n, "withdrawn": k,
    "withdrawn_pids": [...], "corroborated_resolved": m}``. Never raises."""
    if source is None:
        try:
            from framework.sources import get_source
            source = get_source()
        except Exception:
            source = None
    try:
        bound = bool(source is not None and source.available())
    except Exception:
        bound = False
    if not bound:
        # Honest empty — no estate ⇒ nothing can be observed, nothing changes.
        return {"status": "source-unbound", "checked": 0, "withdrawn": 0,
                "withdrawn_pids": [], "corroborated_resolved": 0}

    withdraw_on_resolved = (
        str(os.environ.get("CABINET_RECONCILE_ON_RESOLVED", "0")).strip() == "1")

    checked = 0
    withdrawn_pids = []
    corroborated = 0
    for rec in draft_queue.pending(kv=kv, limit=limit):
        pid = rec.get("pid") or ""
        slug = str(rec.get("slug") or "").strip()
        if not pid or not slug:
            continue
        checked += 1
        person = str(rec.get("person") or slug)

        queued_at = fire_gate._parse_iso(rec.get("queued_ts"))
        replied = None
        if queued_at is not None:
            try:
                replied = source.captain_replied_since(slug, queued_at)
            except Exception:
                replied = None

        if replied is True:
            res = draft_queue.withdraw(
                pid,
                # PLAIN-LANGUAGE LAW: this reason can reach the captain later
                # (a 'send' tap on the withdrawn draft echoes it back).
                f"you already replied to {person} yourself",
                actor="draft-reconcile", kv=kv)
            if res.get("ok"):
                withdrawn_pids.append(pid)
            continue

        # Secondary signal — thread no longer awaiting (resolved/closed some
        # other way). Recorded; withdraws only when explicitly enabled.
        if fire_gate._is_reply(rec):
            awaiting = None
            try:
                awaiting = source.still_awaiting(slug)
            except Exception:
                awaiting = None
            if awaiting is False:
                corroborated += 1
                if withdraw_on_resolved:
                    res = draft_queue.withdraw(
                        pid,
                        f"the conversation with {person} was already handled "
                        f"or closed",
                        actor="draft-reconcile", kv=kv)
                    if res.get("ok"):
                        withdrawn_pids.append(pid)

    return {"status": "ok", "checked": checked,
            "withdrawn": len(withdrawn_pids),
            "withdrawn_pids": withdrawn_pids,
            "corroborated_resolved": corroborated}


def main(argv: "list | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile queued drafts against the captain's actual "
                    "outbound (withdraw what he already handled himself).")
    parser.add_argument("--json", action="store_true", help="JSON summary")
    args = parser.parse_args(argv)
    res = reconcile_queue()
    if args.json:
        print(json.dumps(res))
    else:
        print(f"draft-reconcile: status={res['status']} "
              f"checked={res['checked']} withdrawn={res['withdrawn']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
