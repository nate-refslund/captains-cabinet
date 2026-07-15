"""flavor_a.screenpipe_reply_wire — MECHANICAL pipe-prompt reply forwarding at
the Captain's inbound channel (CHAIR-REPLY-WIRE, one-bot migration hardening
2026-07-07). Re-homed from the former ``framework.frontdoor.sp_reply_wire``
(personal-clean wave, 2026-07-15): this glue is 100% screenpipe-specific — it
has no generic-seam identity, so it belongs in the Flavor-A adapter package
alongside ``screenpipe_source.py`` / ``screenpipe_dispatch.py``, not in
framework CORE. Function bodies are byte-identical to the original.

WHY: the one-bot migration routes screenpipe's interactive pipe prompts to the
Captain THROUGH the Chair — sp_lib's ``_tg_prompt_via_chair`` enqueues intake
text that ENDS with a ``⟦sp:<prompt_id>⟧`` marker plus a ``reply_bridge``
instruction the Chair is asked to follow by discipline: forward the Captain's
answer verbatim onto the redis stream ``screenpipe:pipe-replies``, where the
screenpipe-side consumer group ``sp-bridge`` (telegram-bot/chair_replies.py)
drains it into the existing reply machinery (label capture: draft approve/
edit/skip, commitment done/drop/snooze, decisions, self-knowledge).

Discipline is not a wire. This module makes the return leg MECHANICAL: the
inbound poller (the ONLY reader of Captain Telegram replies) detects a reply
threaded onto a Chair message carrying the marker and XADDs
``{prompt_id, text}`` in-process — the Chair LLM is out of the forwarding
path (it still receives the DM afterwards, prefixed with the outcome, so it
never double-forwards).

CONTRACT (mirrors binder_wire):
  * Captain-only by construction — the poller relays ONLY messages whose
    ``from.id == CAPTAIN_TELEGRAM_ID`` into this call.
  * The marker binds ONLY from the QUOTED text (the Chair-authored prompt the
    Captain replied to) — never from the reply free text, and the LAST marker
    wins (untrusted text embedded earlier in a card cannot mask the real one;
    the binder_wire ``extract_pids`` lesson). Unknown/forged prompt_ids are
    inert: the screenpipe consumer drops unregistered ids on the floor.
  * IDEMPOTENT on the Telegram ``update_id``: the poller advances its offset
    only AFTER delivery, so a crash re-delivers — a ``SET NX EX`` seen-key
    suppresses the second XADD (never double-dispatch a label reply).
  * Every failure mode degrades to ``handled=False`` → the poller relays the
    DM to the Chair exactly as before this wire existed (the reply_bridge
    discipline path remains the fallback). This module must never break
    Captain-DM passthrough.
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Callable, Optional

STREAM = "screenpipe:pipe-replies"

# sp_lib appends "\n⟦sp:{prompt_id}⟧" to the intake text; ids are synthetic
# ("cab-<ts>-<hex>" shaped). Bounded charset + length so arbitrary quoted
# prose can never smuggle an unbounded blob into the stream field.
_SP_MARKER_RE = re.compile(r"⟦sp:([A-Za-z0-9._:\-]{4,120})⟧")

_SEEN_PREFIX = "cabinet:sp-reply-wire:seen:"
_SEEN_TTL_S = str(7 * 24 * 3600)  # one week ≫ any crash-replay window


def wire_enabled() -> bool:
    """Default-ON (the wire hardens tonight's label capture); kill switch is
    CABINET_SP_REPLY_WIRE=0. Fail-safe either way — disabled just means the
    Chair follows the reply_bridge instruction by discipline again."""
    return os.environ.get("CABINET_SP_REPLY_WIRE", "1") != "0"


def _default_redis(args: list, timeout: int = 10):
    """redis-cli via argv list (shell=False): reply text travels as DATA only."""
    host = os.environ.get("REDIS_HOST", "localhost")
    return subprocess.run(["redis-cli", "-h", host, *args],
                          capture_output=True, text=True, timeout=timeout)


def extract_prompt_id(quoted: str) -> Optional[str]:
    """The prompt_id bound by the QUOTED message, or None. LAST marker wins —
    sp_lib renders the real marker at the END of the prompt text, after any
    untrusted embedded content (counterparty text in a draft card)."""
    ids = _SP_MARKER_RE.findall(quoted or "")
    return ids[-1] if ids else None


def handle_captain_reply(
    text: str,
    quoted: str,
    update_id: int,
    *,
    redis_cmd: Optional[Callable] = None,
    log: Callable[[str], None] = lambda m: None,
) -> dict:
    """Forward a Captain reply threaded onto a ⟦sp:…⟧-marked Chair message.

    Returns {"handled": bool, ...}. handled=True carries ``summary`` (one line
    for the tmux relay prefix, so the Chair knows forwarding ALREADY happened
    and must never re-forward) and ``prompt_id``; ``duplicate: True`` marks a
    suppressed re-delivery. handled=False ⇒ caller relays the DM unchanged
    (byte-identical passthrough; the Chair's discipline path takes over).
    Never raises."""
    try:
        if not wire_enabled():
            return {"handled": False, "reason": "wire-disabled"}
        pid = extract_prompt_id(quoted)
        if not pid:
            return {"handled": False, "reason": "no-sp-marker"}
        body = (text or "").strip()
        if not body:
            return {"handled": False, "reason": "empty-text", "prompt_id": pid}
        r = redis_cmd or _default_redis

        # Idempotency guard FIRST (SET NX → XADD): on a crash-replay the seen
        # key already exists and the second XADD is suppressed — a label reply
        # must never dispatch twice (the sp-bridge consumer dup-guards only
        # WRITE kinds). The inverse ordering would double-XADD instead.
        seen_key = _SEEN_PREFIX + str(update_id)
        res = r(["SET", seen_key, "1", "NX", "EX", _SEEN_TTL_S])
        if res is None or res.returncode != 0:
            log(f"sp-reply-wire: seen-guard unavailable — passthrough (prompt {pid})")
            return {"handled": False, "reason": "redis-unavailable", "prompt_id": pid}
        if (res.stdout or "").strip() != "OK":
            log(f"sp-reply-wire: duplicate update {update_id} suppressed (prompt {pid})")
            return {"handled": True, "prompt_id": pid, "duplicate": True,
                    "summary": f"sp-bridge: reply already forwarded → {pid} (duplicate suppressed)"}

        add = r(["XADD", STREAM, "*", "prompt_id", pid, "text", body])
        entry_id = (add.stdout or "").strip() if add is not None else ""
        if add is None or add.returncode != 0 or not entry_id:
            # Roll the guard back so a retry may re-attempt; degrade to the
            # discipline path (the DM relays with the reply_bridge instruction
            # still visible in the quoted prompt).
            try:
                r(["DEL", seen_key])
            except Exception:
                pass
            log(f"sp-reply-wire: XADD failed — passthrough (prompt {pid})")
            return {"handled": False, "reason": "xadd-failed", "prompt_id": pid}

        log(f"sp-reply-wire: forwarded reply → {STREAM} prompt_id={pid} entry={entry_id}")
        return {"handled": True, "prompt_id": pid, "entry_id": entry_id,
                "summary": f"sp-bridge: reply forwarded → {pid}"}
    except Exception as e:  # noqa: BLE001 — passthrough is the invariant
        log(f"sp-reply-wire: error (passthrough preserved): {e!r}")
        return {"handled": False, "reason": f"error:{e.__class__.__name__}"}
