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

TWO pin designs, selected by the ``pin_mode`` knob (config.py — Captain-
ratified 2026-07-10): ``adopt`` (this module's original single-item design,
above) and ``overview`` — ONE live standing overview card ("⚑ N need you" +
top names when N≤5, renderer ``overview_card.py``) that is pinned once and
then edited in place forever; it never advances or swaps, so the pin can
never go dead or thrash. ``step()`` dispatches on the resolved knob.
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
    """One pin tick. In ``adopt`` mode (default): adopts the item's existing
    standing card (``standing_message_id``) when the census carries one;
    otherwise sends the single-decision card first (through the gate) and
    pins that. A quiet-hours-routed send simply leaves the pin empty this
    tick — the pin never out-shouts the charter. In ``overview`` mode the
    tick maintains the ONE standing overview card instead (edit-in-place;
    ``engaged`` is irrelevant — the card advances by re-render)."""
    from framework.comms import tools
    now = now or datetime.now(timezone.utc)
    cfg = cfg or _cfg.load()
    if str(cfg.get("pin_mode") or "adopt") == "overview":
        return overview_step(census=census, now=now, state=state, cfg=cfg,
                             adapter=adapter, ch=ch)
    persist = state is None
    if state is None:
        state = load_state()
    if census is None:
        from framework.attention.queue import build_queue
        census = build_queue(now=now)

    report = {"ops": []}
    # Knob round-trip (overview → adopt): retire the standing overview pin
    # first — the single-item design starts clean (mirror of overview_step's
    # adopt handoff), and its keys never leak into adopt state.
    if str((state or {}).get("mode") or "") == "overview" \
            and (state or {}).get("message_id"):
        try:
            res = tools.unpin(message_id=state.get("message_id"),
                              adapter=adapter)
            report["ops"].append(("unpin", "overview-retired",
                                  (res or {}).get("status")))
        except Exception as e:  # noqa: BLE001
            print(f"[surface.pin] overview handoff unpin failed: {e}",
                  file=sys.stderr)
        cleared = _fresh_state()
        if persist:
            state = cleared
        else:
            state.clear()
            state.update(cleared)

    ops, st = sync(census, state, now, engaged=engaged)
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

    st["mode"] = "adopt"          # stamp the design so a flip BACK hands off
    st.pop("pinned", None)        # overview-only key: never survives adopt
    if persist:
        save_state(st)
    else:
        state.clear()
        state.update(st)
    report["pinned"] = st.get("item_id")
    return report


# ---------------------------------------------------------------------------
# Overview mode (pin_mode: overview — Captain-ratified 2026-07-10)
# ---------------------------------------------------------------------------

def overview_step(*, census: "dict | None" = None,
                  now: "datetime | None" = None, state: "dict | None" = None,
                  cfg: "dict | None" = None, adapter=None, ch=None) -> dict:
    """One overview tick: render the standing "⚑ N need you" card, deliver
    it through the gate (send once / edit in place / suppress on no-change),
    and keep it pinned. Never unpins on all-clear — the n=0 face IS the
    quiet state. A quiet-hours-routed first send defers the pin to the next
    tick (the card never out-shouts the charter)."""
    from framework.comms import tools
    from framework.comms.surface import overview_card as _ov
    now = now or datetime.now(timezone.utc)
    cfg = cfg or _cfg.load()
    persist = state is None
    if state is None:
        state = load_state()
    if census is None:
        from framework.attention.queue import build_queue
        census = build_queue(now=now)

    st = dict(_fresh_state(), **{k: v for k, v in (state or {}).items()})
    report: dict = {"mode": "overview", "ops": []}

    # One-time handoff from adopt mode: retire the old single-item pin so the
    # overview card is the ONE pin (its own message stays, just unpinned).
    if st.get("mode") != "overview" and st.get("item_id") \
            and st.get("message_id"):
        try:
            res = tools.unpin(message_id=st.get("message_id"), adapter=adapter)
            report["ops"].append(("unpin", "adopt-retired",
                                  (res or {}).get("status")))
        except Exception as e:  # noqa: BLE001
            print(f"[surface.pin] adopt handoff unpin failed: {e}",
                  file=sys.stderr)
        st = _fresh_state()
    st["mode"] = "overview"

    try:
        kwargs = _ov.render(census, now=now, cfg=cfg)
        res = tools.send_card(subject=kwargs["subject"],
                              situation=kwargs["situation"],
                              kind=kwargs["kind"], lane=kwargs["lane"],
                              evidence=kwargs["evidence"],
                              steps=kwargs["steps"], state=kwargs["state"],
                              deadline_iso=kwargs["deadline_iso"],
                              pid_marker=kwargs["pid_marker"],
                              buttons=kwargs["buttons"],
                              adapter=adapter, ch=ch, now=now)
        decision = (res or {}).get("decision") or {}
        action = str(decision.get("action") or "error")
        mid = None
        if action == "send":
            mids = ((res or {}).get("result") or {}).get("message_ids") or []
            mid = mids[0] if mids else None
        elif action in ("edit", "suppress"):
            mid = decision.get("message_id") or st.get("message_id")
            if mid is None and decision.get("situation_key"):
                from framework.attention import gate as _gate
                mid = ((_gate.load_standing().get(
                    decision["situation_key"]) or {}).get("message_id"))
        report["ops"].append(("card", action, mid))

        if mid is not None:
            if int(mid) != int(st.get("message_id") or 0) \
                    or not st.get("pinned"):
                pres = tools.pin(message_id=int(mid), adapter=adapter)
                # live channel says "sent", the null/test adapters say "ok"
                pinned = str((pres or {}).get("status")) in ("ok", "sent")
                report["ops"].append(("pin", int(mid),
                                      (pres or {}).get("status")))
                st["pinned"] = pinned
            st["message_id"] = int(mid)
        else:
            # nothing on the surface yet (e.g. quiet hours routed the first
            # send to the briefing) — retry next tick, never force.
            report["ops"].append(("pin", None, "deferred"))
    except Exception as e:  # noqa: BLE001 — one tick must never crash the loop
        print(f"[surface.pin] overview tick failed: {e}", file=sys.stderr)
        report["ops"].append(("card", "error", str(e)[:120]))

    if persist:
        save_state(st)
    else:
        state.clear()
        state.update(st)
    report["pinned_message_id"] = st.get("message_id")
    return report
