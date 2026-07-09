"""framework.frontdoor.surface — drain the intake stream and surface to the Captain.

Captain directive (2026-06-24, "make sure all pipes reach you every time"): the
single-voice flag reroutes informational pipe DMs into the intake stream
(cabinet:frontdoor:intake) instead of DMing the Captain. This is the loop that drains
that stream and actually gets items to him:

  - ping-now  -> DM the Captain immediately (channel.send), then ACK.
  - batch/fyi -> left PENDING for the next briefing to compose + ACK (one voice).

It also recovers ping-now items left pending by a crash/incomplete prior run, so
a time-sensitive brief is never silently stuck. Best-effort: never raises.

Run frequently (every ~5 min) via com.cabinet.intake-surface so ping-now items
(pre-meeting briefs, prod alerts) reach the Captain promptly.

It ALSO drains lane officers' captain-attention cards into the intake first
(attention_drain.drain_attention): officers that can't DM the Captain card decisions to
cabinet:captain-attention:<project>, and this is the loop that forwards those
into the one-voice intake so the same ping-now/batch routing applies. Best-effort
and ordered first so a card raised this tick can surface this tick.
"""
from __future__ import annotations

from framework.frontdoor import intake, channel, attention_drain

_CONSUMER = "chair"


def drain_and_surface(*, consumer: str = _CONSUMER, count: int = 200) -> dict:
    """Surface ping-now intake items to the Captain; leave batch for the briefing.

    First forwards any lane captain-attention cards into the intake, then surfaces
    ping-now items. Returns a small dict of counts (for logging). Failures degrade
    — a send error leaves that item pending so the next run retries it rather than
    dropping it; an attention-drain error degrades to "forwarded nothing".
    """
    try:
        attn = attention_drain.drain_attention()
    except Exception:
        attn = {"streams": 0, "forwarded": 0, "skipped": 0, "by_project": {}}
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

    # P5 (attention-gateway §4.6): run the T2 SLA fallback each drain — a
    # past-deadline Chair-judgment request that the Chair never answered falls
    # back mechanically (floor → send with (chair-offline); else → briefing).
    # Best-effort: a sweep error must not stop the surface loop.
    t2_swept = 0
    try:
        from framework.attention import t2
        from datetime import datetime, timezone
        t2_swept = len(t2.sweep_expired(datetime.now(timezone.utc)))
    except Exception as e:  # noqa: BLE001
        print(f"[surface] T2 sweep skipped ({e})", file=__import__("sys").stderr)

    # War-room census (command-center Stage 1): each 300s drain recomputes the
    # ONE attention queue and writes both projections — the private authed
    # census (dashboard/API source) and the PII-scrubbed shared/interfaces
    # artifact — plus the H2 hygiene sweeps (zombie cabinet:action keys whose
    # proposals already closed; forwarded captain-attention stream copies).
    # All best-effort: the census must never brick the drain.
    queue_pending = None
    try:
        from framework.attention import queue as attention_queue
        census = attention_queue.build_queue()
        attention_queue.write_artifacts(census)
        queue_pending = census.get("pending_captain_items")
        # Telegram skin: the ONE pinned standing queue card, silently edited
        # in place (pins/edits never notify). Gated on allow_sends +
        # CABINET_QUEUE_CARD inside refresh(); best-effort.
        from framework.attention import queue_card
        queue_card.refresh(census)
    except Exception as e:  # noqa: BLE001
        print(f"[surface] attention census skipped ({e})",
              file=__import__("sys").stderr)
    try:
        from framework.attention import hygiene
        hygiene.sweep_zombie_cards()
        hygiene.trim_forwarded_streams()
    except Exception as e:  # noqa: BLE001
        print(f"[surface] hygiene sweeps skipped ({e})",
              file=__import__("sys").stderr)

    batch_pending = sum(1 for it in items if (it.get("urgency_tier") or "batch") != "ping-now")
    return {"seen": len(items), "ping_now_surfaced": surfaced,
            "acked": len(acked), "batch_pending": batch_pending,
            "attention_forwarded": attn.get("forwarded", 0),
            "attention_streams": attn.get("streams", 0),
            "t2_fallback_swept": t2_swept,
            "pending_captain_items": queue_pending}


if __name__ == "__main__":  # invoked by com.cabinet.intake-surface (launchd)
    import json
    print(json.dumps(drain_and_surface()))
