"""framework.attention.queue_card — the Telegram skin of the ONE census.

Two renders, same build_queue() truth (SURFACE-PARITY-LAW):

  * PINNED STANDING QUEUE CARD — one pinned message in the Captain DM,
    silently edited in place as the census changes (DM pins never notify;
    edits never notify). Renders the Decisions shelf + byClass counts.
  * "Needs you (N)" BRIEFING SECTION — one intake item folded into the
    morning/evening briefing via the pure gate.briefing_item shape.

VERDICTS STAY 100% IN THE EXISTING BINDER GRAMMAR: this card is a glance
surface. It deliberately carries NO ``·pid·`` markers — the bindable marker
lives on each situation's own standing card, and a summary card carrying
many markers would collide with the binder's last-marker heuristic. The
card names the honest actuation channel instead ("verdict on the item's own
card"), and deep-links the classic /queue page for copyable grammar.

Transport: the ONE door (frontdoor.channel send/edit_message/pin — germline
module CALLED, never edited). State (message id + render hash) lives beside
the standing-card map in $CABINET_ATTENTION_DIR/queue-card.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Render caps — the pinned card is a glance object, not a dossier.
_CARD_MAX_LINES = 10
_WHAT_CAP = 90


def _state_path() -> Path:
    from framework.attention.queue import _attention_dir
    return _attention_dir() / "queue-card.json"


def _load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, p)


def _age_str(age_h) -> str:
    if not isinstance(age_h, (int, float)):
        return ""
    if age_h < 48:
        return f"{age_h:.0f}h"
    return f"{age_h / 24:.0f}d"


def _due_str(deadline_iso) -> str:
    # separator is a plain dash — U+00B7 is the binder's bindable marker
    # char and may NEVER appear in this card (marker-hygiene law).
    return f" — due {str(deadline_iso)[:16]}" if deadline_iso else ""


def pinned_card_lines(census: dict) -> list:
    """[(card_id, rendered line)] for the Decisions shelf — the parity unit
    (the classic /queue page and the API render the same ids in the same
    order). Marker-stripped; free text capped."""
    priv_rows = census.get("decisions") or []
    lines = []
    for i, card in enumerate(priv_rows[:_CARD_MAX_LINES], 1):
        what = str(card.get("what") or "(untitled)").replace("·", "")[:_WHAT_CAP]
        age = _age_str(card.get("age_h"))
        bits = f"{i}. {what}"
        meta = ", ".join(x for x in (str(card.get("kind") or ""), age) if x)
        if meta:
            bits += f"  ({meta}{_due_str(card.get('deadline_iso'))})"
        lines.append((card.get("id"), bits))
    return lines


def render_pinned_card(census: dict) -> str:
    """The standing queue card text. Terse (charter law), no payload dumps,
    no ·markers·. Empty shelf renders the designed reward state."""
    n = int(census.get("pending_captain_items") or 0)
    total = int(census.get("pending_total") or 0)
    if n <= 0 and total <= 0:
        return ("⚑ Needs you: nothing.\n"
                "The shelf is clear — the org is deciding what it can.")
    lines = [f"⚑ Needs you ({n})"]
    id_lines = pinned_card_lines(census)
    lines.extend(line for _id, line in id_lines)
    overflow = int(census.get("overflow") or 0)
    if overflow > 0:
        lines.append(f"…+{overflow} over the cap (consolidation need filed)")
    directions = census.get("directions") or []
    if directions:
        lines.append(f"Directions (weekly): {len(directions)}")
    by_class = census.get("by_class") or {}
    if by_class:
        counts = " | ".join(f"{k}:{v}" for k, v in sorted(by_class.items()))
        lines.append(counts)
    lines.append("Verdict on each item's own card (binder grammar), "
                 "or /queue in the dashboard.")
    return "\n".join(lines)


def _render_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def update_pinned_card(census: dict, *, send_fn=None, edit_fn=None,
                       pin_fn=None, state: "dict | None" = None) -> dict:
    """Create-or-edit the ONE pinned queue card. Silent everywhere: the
    first send is ``silent=True`` + a DM pin (pins never notify); every
    subsequent change is an in-place edit (edits never notify). No-op when
    the render is unchanged. Injectable transports; the defaults are the
    one-door channel functions. Never raises — returns a status dict."""
    persist = state is None
    if state is None:
        state = _load_state()

    # census projected for render: accept either the raw build_queue() dict
    # (cards carry 'what' directly) or the private census (same keys).
    text = render_pinned_card(_as_private(census))
    rhash = _render_hash(text)
    if state.get("message_id") and state.get("render_hash") == rhash:
        return {"status": "unchanged", "message_id": state["message_id"]}

    if send_fn is None or edit_fn is None or pin_fn is None:
        try:
            from framework.frontdoor import channel
            send_fn = send_fn or (lambda t: channel.send(
                t, silent=True, feed_meta={"kind": "queue-card"}))
            edit_fn = edit_fn or (lambda mid, t: channel.edit_message(
                mid, t, feed_meta={"kind": "queue-card"}))
            pin_fn = pin_fn or (lambda mid: channel.pin(mid, silent=True))
        except Exception as e:                      # noqa: BLE001
            return {"status": "channel-unavailable", "error": str(e)[:200]}

    mid = state.get("message_id")
    if mid:
        try:
            edit_fn(mid, text)
            state["render_hash"] = rhash
            if persist:
                _save_state(state)
            return {"status": "edited", "message_id": mid}
        except Exception as e:                      # noqa: BLE001
            print(f"[queue-card] edit of {mid} failed ({e}) — re-sending",
                  file=sys.stderr)
            # mutate IN PLACE — the caller's state dict must observe the
            # re-send (rebinding the local name would silently fork it)
            for dead in ("message_id", "render_hash", "pinned"):
                state.pop(dead, None)

    try:
        res = send_fn(text)
        mids = (res or {}).get("message_ids") or []
        if not mids:
            return {"status": "send-failed", "error": "no message id"}
        mid = mids[0]
        state.update({"message_id": mid, "render_hash": rhash})
        try:
            pin_fn(mid)
            state["pinned"] = True
        except Exception as e:                      # noqa: BLE001
            # An unpinned standing card still works — loud, not fatal.
            print(f"[queue-card] pin failed ({e}) — card standing unpinned",
                  file=sys.stderr)
            state["pinned"] = False
        if persist:
            _save_state(state)
        return {"status": "sent", "message_id": mid,
                "pinned": state.get("pinned", False)}
    except Exception as e:                          # noqa: BLE001
        return {"status": "send-failed", "error": str(e)[:200]}


def _as_private(census: dict) -> dict:
    """Accept either build_queue() output or the private-census projection —
    both carry decisions/directions/by_class; build_queue cards use 'what'
    (same key the projection keeps), so rendering is uniform. age_h exists
    only on the projection; build_queue cards render age-less (honest)."""
    if census.get("decisions") and isinstance(census["decisions"][0], dict) \
            and "why_now" in census["decisions"][0] \
            and "age_h" not in census["decisions"][0]:
        from framework.attention.queue import to_private_census
        try:
            return to_private_census(census)
        except Exception:                           # noqa: BLE001
            return census
    return census


def briefing_needs_you_item(census: dict, *,
                            now: "datetime | None" = None) -> "dict | None":
    """The 'Needs you (N)' briefing section as ONE canonical intake item
    (the pure gate.briefing_item shape — composer.render_item renders the
    multi-line summary as a titled section). None when nothing pends —
    silence is the correct render of an empty shelf."""
    priv = _as_private(census)
    n = int(priv.get("pending_captain_items") or 0)
    if n <= 0:
        return None
    lines = [f"⚑ Needs you ({n})"]
    lines.extend(line for _id, line in pinned_card_lines(priv))
    overflow = int(priv.get("overflow") or 0)
    if overflow > 0:
        lines.append(f"…+{overflow} over the cap")
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "source": "attention-queue",
        "kind": "needs-you",
        "ts": ts,
        "urgency_tier": "batch",
        "payload": {"summary": "\n".join(lines),
                    "pending_captain_items": n},
        "context": {"why": "the war-room census — decisions blocked on you",
                    "sources": ["attention-queue"], "audience": None,
                    "thread_ref": None},
    }


def refresh(census: "dict | None" = None) -> dict:
    """The surface-drain entrypoint: census → pinned card upsert. Gated on
    allow_sends (a dev/test box computes but never sends) and the
    CABINET_QUEUE_CARD kill-switch (default on). Best-effort."""
    if str(os.environ.get("CABINET_QUEUE_CARD", "1")).strip().lower() in (
            "0", "false", "off", "no"):
        return {"status": "disabled"}
    try:
        from framework.env import allow_sends
        if not allow_sends():
            return {"status": "sends-disabled"}
    except Exception:
        return {"status": "sends-unknown"}
    if census is None:
        from framework.attention.queue import build_queue
        census = build_queue()
    return update_pinned_card(census)
