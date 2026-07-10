"""framework.comms.surface.pin_lifecycle — the pin is the ONE thing to act on
now (master prompt §5, Captain-approved design).

The pin = the single highest-value open item — auto-maintained, never a
stack. Auto-unpin / replace when: (1) the Captain ENGAGES it (reply/tap →
resolved → unpin + advance — the concrete gap this module fixes); (2)
something strictly more urgent arrives (replace); (3) it passes its
wrong-by-tomorrow horizon (unpin — the item itself still rides the census
into the briefing); (4) the underlying situation closes.

Shape: pure ``sync(census, state, now, engaged) → (plan, state')`` + a thin
executor that pins/unpins ONLY via ``framework.comms.tools`` (and adopts the
item's existing standing card when the census knows its message id, instead
of minting a duplicate).

Replace is deliberately conservative: the pin follows rank #1 only when the
newcomer is STRICTLY more urgent (worse cost-of-delay class, or a real
before-next-briefing deadline the incumbent lacks) — rank jitter must not
thrash the Captain's pin.

Durable state: ``$CABINET_ATTENTION_DIR/pin-state.json`` (ids + timestamps
only).
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import datetime, timezone

from framework.comms.surface import config as _cfg
from framework.comms.surface import decision_card as _dc

STATE_FILE = "pin-state.json"

_SEVERITY = {"blocking": 3, "high": 2, "medium": 1, "": 0}
_OPEN_STATES = frozenset({"open", "pending"})


# ---------------------------------------------------------------------------
# Durable state
# ---------------------------------------------------------------------------

def _fresh_state() -> dict:
    return {"v": 1, "item_id": None, "h": None, "message_id": None,
            "own_card": False, "set_at": None, "deadline_iso": None,
            "severity": 0, "updated_at": None}


def _state_path():
    return _cfg.attention_dir() / STATE_FILE


def load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            base = _fresh_state()
            base.update(data)
            return base
    except (OSError, json.JSONDecodeError):
        pass
    return _fresh_state()


def save_state(state: dict) -> None:
    d = _cfg.attention_dir()
    d.mkdir(parents=True, exist_ok=True)
    lock = d / ".pin.lock"
    lf = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lf, fcntl.LOCK_EX)
        state["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tmp = _state_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _state_path())
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
        os.close(lf)


# ---------------------------------------------------------------------------
# Pure lifecycle decision
# ---------------------------------------------------------------------------

def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _severity_of(card: dict, now: datetime) -> int:
    why = card.get("why_now") or {}
    sev = _SEVERITY.get(str(why.get("cost_of_delay") or "").lower(), 0)
    dl = _parse_iso(why.get("deadline_iso"))
    if dl is not None and dl < _cfg.next_briefing(now):
        sev = max(sev, 3)          # a real before-next-briefing deadline
    return sev


def _find(census: dict, item_id: str) -> "dict | None":
    for shelf in ("decisions", "overflow_cards", "directions"):
        for c in census.get(shelf) or []:
            if isinstance(c, dict) and str(c.get("id") or "") == item_id:
                return c
    return None


def sync(census: dict, state: dict, now: datetime,
         *, engaged: "set | frozenset" = frozenset()) -> "tuple[list, dict]":
    """(plan, state'). Plan ops, in execution order:
      ("unpin", message_id|None, reason)   reason ∈ engaged|closed|expired|replaced
      ("pin",   card)                      make this item the pin
    An empty plan = keep the current pin (or keep having none)."""
    st = dict(_fresh_state(), **{k: v for k, v in (state or {}).items()})
    ops: list = []
    avoid: set = set()      # never re-pin what this very pass just retired
    decisions = [c for c in census.get("decisions") or []
                 if isinstance(c, dict) and _dc.is_decision(c)]
    top = decisions[0] if decisions else None

    current_id = st.get("item_id")
    if current_id:
        card = _find(census, str(current_id))
        clear_reason = None
        if str(current_id) in {str(e) for e in engaged}:
            clear_reason = "engaged"        # (1) the Captain acted → advance
        elif card is None or str(card.get("state") or "open").lower() \
                not in _OPEN_STATES:
            clear_reason = "closed"         # (4) situation closed
        else:
            dl = _parse_iso(st.get("deadline_iso")
                            or (card.get("why_now") or {}).get("deadline_iso"))
            if dl is not None and dl <= now:
                clear_reason = "expired"    # (3) horizon passed → briefing owns it
        if clear_reason:
            ops.append(("unpin", st.get("message_id"), clear_reason))
            if clear_reason == "expired":
                avoid.add(str(current_id))
            st = _fresh_state()
        elif top is not None and str(top.get("id") or "") != str(current_id):
            # (2) replace only for a STRICT urgency upgrade
            if _severity_of(top, now) > max(
                    int(st.get("severity") or 0), _severity_of(card, now)):
                ops.append(("unpin", st.get("message_id"), "replaced"))
                st = _fresh_state()

    if st.get("item_id") is None and top is not None:
        skip = {str(e) for e in engaged} | avoid
        pick = next((c for c in decisions if str(c.get("id")) not in skip), None)
        if pick is not None:
            ops.append(("pin", pick))
            st.update({"item_id": str(pick.get("id") or ""),
                       "h": _dc.handle_of(str(pick.get("id") or "")),
                       "severity": _severity_of(pick, now),
                       "deadline_iso": (pick.get("why_now") or {}).get("deadline_iso"),
                       "set_at": now.astimezone(timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ")})
    return ops, st


# ---------------------------------------------------------------------------
# Executor — comms tools only
# ---------------------------------------------------------------------------

def step(*, census: "dict | None" = None, now: "datetime | None" = None,
         state: "dict | None" = None, engaged: "set | frozenset" = frozenset(),
         cfg: "dict | None" = None, adapter=None, ch=None) -> dict:
    """One pin tick. Adopts the item's existing standing card
    (``standing_message_id``) when the census carries one; otherwise sends
    the single-decision card first (through the gate) and pins that. A
    quiet-hours-routed send simply leaves the pin empty this tick — the pin
    never out-shouts the charter."""
    from framework.comms import tools
    now = now or datetime.now(timezone.utc)
    cfg = cfg or _cfg.load()
    persist = state is None
    if state is None:
        state = load_state()
    if census is None:
        from framework.attention.queue import build_queue
        census = build_queue(now=now)

    ops, st = sync(census, state, now, engaged=engaged)
    report = {"ops": []}
    for op in ops:
        try:
            if op[0] == "unpin":
                res = tools.unpin(message_id=op[1], adapter=adapter)
                report["ops"].append(("unpin", op[2], (res or {}).get("status")))
            elif op[0] == "pin":
                card = op[1]
                mid = card.get("standing_message_id")
                own_card = False
                if not mid:
                    kwargs = _dc.render(card, state="open", now=now, cfg=cfg)
                    res = tools.send_card(
                        subject=kwargs["subject"], situation=kwargs["situation"],
                        kind=kwargs["kind"], lane=kwargs["lane"],
                        evidence=kwargs["evidence"], state="open",
                        deadline_iso=kwargs["deadline_iso"],
                        pid_marker=kwargs["pid_marker"],
                        buttons=kwargs["buttons"],
                        escalation=kwargs.get("escalation"),
                        adapter=adapter, ch=ch, now=now)
                    decision = (res or {}).get("decision") or {}
                    if decision.get("action") == "send":
                        mids = ((res or {}).get("result") or {}).get("message_ids") or []
                        mid = mids[0] if mids else None
                    elif decision.get("action") in ("edit", "suppress"):
                        mid = decision.get("message_id")
                        if mid is None and decision.get("situation_key"):
                            # suppress carries no id — the standing map does
                            from framework.attention import gate as _gate
                            mid = ((_gate.load_standing().get(
                                decision["situation_key"]) or {}).get("message_id"))
                    own_card = mid is not None
                if mid:
                    pres = tools.pin(message_id=int(mid), adapter=adapter)
                    st["message_id"] = int(mid)
                    st["own_card"] = own_card
                    report["ops"].append(("pin", st["item_id"],
                                          (pres or {}).get("status")))
                else:
                    # nothing rendered (e.g. quiet hours) — no pin this tick
                    st = _fresh_state()
                    report["ops"].append(("pin", None, "deferred"))
        except Exception as e:  # noqa: BLE001
            print(f"[surface.pin] op {op[0]} failed: {e}", file=sys.stderr)
            report["ops"].append((op[0], "error", str(e)[:120]))

    if persist:
        save_state(st)
    else:
        state.clear()
        state.update(st)
    report["pinned"] = st.get("item_id")
    return report
