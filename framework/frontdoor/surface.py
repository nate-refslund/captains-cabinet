"""framework.frontdoor.surface — drain the intake stream and surface to the Captain.

Captain directive (2026-06-24, "make sure all pipes reach you every time"): the
single-voice flag reroutes informational pipe DMs into the intake stream
(cabinet:frontdoor:intake) instead of DMing Nate. This is the loop that drains
that stream and actually gets items to him:

  - ping-now  -> DM Nate immediately (channel.send), then ACK.
  - batch/fyi -> left PENDING for the next briefing to compose + ACK (one voice).

It also recovers ping-now items left pending by a crash/incomplete prior run, so
a time-sensitive brief is never silently stuck. Best-effort: never raises.

Run frequently (every ~5 min) via com.cabinet.intake-surface so ping-now items
(pre-meeting briefs, prod alerts) reach Nate promptly.
"""
from __future__ import annotations

from framework.frontdoor import intake, channel

_CONSUMER = "chair"


def drain_and_surface(*, consumer: str = _CONSUMER, count: int = 200) -> dict:
    """Surface ping-now intake items to the Captain; leave batch for the briefing.

    Returns a small dict of counts (for logging). Failures degrade — a send error
    leaves that item pending so the next run retries it rather than dropping it.
    """
    try:
        pending = intake.drain_pending(consumer=consumer)   # crash recovery
    except Exception:
        pending = []
    try:
        fresh = intake.drain(consumer=consumer, count=count)  # new items
    except Exception:
        fresh = []

    seen: set[str] = set()
    items: list[dict] = []
    for it in pending + fresh:
        mid = it.get("id")
        if mid in seen:
            continue
        seen.add(mid)
        items.append(it)

    surfaced, acked = 0, []
    for it in items:
        tier = (it.get("urgency_tier") or "batch")
        if tier != "ping-now":
            continue  # batch/fyi -> stay pending for the briefing to compose
        summary = (it.get("payload") or {}).get("summary", "")
        if not summary:
            acked.append(it["id"])  # nothing to send; clear it
            continue
        try:
            r = channel.send(summary)
        except Exception:
            r = None
        if isinstance(r, dict) and r.get("status") == "sent":
            surfaced += 1
            acked.append(it["id"])
        # else: leave pending -> next run retries (never silently dropped)

    if acked:
        try:
            intake.ack(acked)
        except Exception:
            pass

    batch_pending = sum(1 for it in items if (it.get("urgency_tier") or "batch") != "ping-now")
    return {"seen": len(items), "ping_now_surfaced": surfaced,
            "acked": len(acked), "batch_pending": batch_pending}


if __name__ == "__main__":  # invoked by com.cabinet.intake-surface (launchd)
    import json
    print(json.dumps(drain_and_surface()))
