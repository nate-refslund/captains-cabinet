"""framework.comms.surface.digest — FYI → digest, never the decision stream (§3.2).

The other half of the label-soup kill: an FYI-kind item is not a decision and
must not mint a Captain card. This module folds every FYI-shaped census card
into ONE canonical intake item (the exact ``gate.briefing_item`` shape the
briefing composer consumes), so FYIs ride the next briefing as one section.

Pure fold + an injectable enqueue (live default: ``frontdoor.intake.enqueue``,
best-effort — a broken intake never blocks the surface tick).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from framework.comms.surface import decision_card as _dc

_MAX_LINES = 12


def _scrub(text) -> str:
    # marker-hygiene law: digest lines never carry the U+00B7 marker char.
    return str(text or "").replace("·", "")


def split_fyi(cards: list) -> "tuple[list, list]":
    """(decisions, fyis) — the renderer-time fork every consumer uses."""
    decisions, fyis = [], []
    for c in cards or []:
        (decisions if _dc.is_decision(c) else fyis).append(c)
    return decisions, fyis


def fold_fyi(fyi_cards: list, *, now: "datetime | None" = None) -> "dict | None":
    """N FYI cards → ONE intake item (None when there are none — silence is
    the correct render of an empty pile)."""
    rows = [c for c in fyi_cards or [] if isinstance(c, dict)]
    if not rows:
        return None
    lines = [f"For your information — {len(rows)} item(s):"]
    for c in rows[:_MAX_LINES]:
        what = _scrub(str(c.get("what") or "(no title)")).strip()[:120]
        lane = str(c.get("lane") or "").strip()
        lines.append(f"- {what}" + (f" ({lane})" if lane else ""))
    if len(rows) > _MAX_LINES:
        lines.append(f"…and {len(rows) - _MAX_LINES} more.")
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "source": "comms-surface",
        "kind": "digest",
        "ts": ts,
        "urgency_tier": "fyi",
        "payload": {"summary": "\n".join(lines), "count": len(rows)},
    }


def enqueue_fyi_digest(fyi_cards: list, *, enqueue_fn=None,
                       now: "datetime | None" = None) -> "dict | None":
    """Fold + enqueue. Returns ``{"id": <receipt>, "count": n}`` or None.
    Best-effort: an intake failure is loud on stderr, never raised — the
    FYIs re-fold on the next tick."""
    item = fold_fyi(fyi_cards, now=now)
    if item is None:
        return None
    try:
        if enqueue_fn is None:
            from framework.frontdoor import intake
            enqueue_fn = intake.enqueue
        return {"id": enqueue_fn(item), "count": item["payload"]["count"]}
    except Exception as e:  # noqa: BLE001
        print(f"[surface.digest] intake enqueue failed ({e}) — will re-fold",
              file=sys.stderr)
        return {"id": None, "count": item["payload"]["count"], "error": str(e)[:200]}
