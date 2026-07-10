"""framework.comms.surface.pacing — hold, don't dump (master prompt §4).

The triage/pacing engine between the ranked census
(``framework.attention.queue.build_queue`` — germline, CALLED never edited)
and the Captain's channel. Decisions accumulate in the queue; the Captain
sees at most ``cap`` (3–5) active single-decision cards; the next advances
only as he clears the current ones.

Shape: a PURE transition function ``plan(census, state, now, cfg) →
(ops, state')`` — no I/O, fully unit-testable — plus a thin executor
``step()`` that delivers every op through ``framework.comms.tools``
(``send_card`` / ``edit_card``), so the attention gate's charter, standing-
card dedup and quiet hours govern this engine like any officer. The engine
never touches an adapter or the front door directly.

Invariants (tested in tests/test_pacing_invariants.py):
  * pacing never holds more than ``cap`` active cards — presentation stops
    at the cap and resumes only on clears (advance-on-clear);
  * ask-first is the default: with no Captain opt-in the engine sends ONE
    standing nudge card, never the batch;
  * quiet hours pass through: a present op the gate routes to the briefing
    does NOT become an active card (the engine reads the gate's decision —
    it cannot out-shout the charter);
  * urgent jumps are budgeted per rolling window; the budget burns only on
    an ACTUAL direct send (a gate-demoted jump costs nothing).

Durable state: ``$CABINET_ATTENTION_DIR/pacing-state.json`` — atomic replace
under an flock (the standing-card map's own pattern). The state holds ids,
handles and timestamps only — never message bodies.
"""
from __future__ import annotations

import copy
import fcntl
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from framework.comms.surface import config as _cfg
from framework.comms.surface import decision_card as _dc

STATE_FILE = "pacing-state.json"

# The one standing nudge/pacing card — constant identity, edited in place
# forever (never a second nudge message; the count just changes).
# NEUTRAL subject: the same card carries the pending count AND the all-clear
# face, so the identity line must contradict neither ("Decisions waiting /
# All clear" read as nonsense at a glance). One-time re-mint 2026-07-10.
NUDGE_SUBJECT = "Your decisions"
NUDGE_EVIDENCE = ["thread:comms-surface-nudge"]
NUDGE_KIND = "triage-nudge"

_OPEN_STATES = frozenset({"open", "pending"})
_URGENT_KINDS = frozenset({"deadline-critical", "infra-page", "security-alert"})


# ---------------------------------------------------------------------------
# Durable state
# ---------------------------------------------------------------------------

def _fresh_state() -> dict:
    return {"v": 1, "mode": None, "cap_override": None,
            "active": {}, "handles": {}, "nudge": None,
            "snooze_until": None, "ride_briefing_until": None,
            "triage_open": False, "batch_offered": False,
            "presented_in_batch": 0, "urgent_sends": [], "deferred": {},
            "holds": {}, "updated_at": None}


def _state_path():
    return _cfg.attention_dir() / STATE_FILE


def load_state() -> dict:
    p = _state_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("active"), dict):
            base = _fresh_state()
            base.update(data)
            return base
    except (OSError, json.JSONDecodeError):
        pass
    return _fresh_state()


def save_state(state: dict) -> None:
    d = _cfg.attention_dir()
    d.mkdir(parents=True, exist_ok=True)
    lock = d / ".pacing.lock"
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
# Small time helpers
# ---------------------------------------------------------------------------

def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _past(iso_s, now: datetime) -> bool:
    t = _parse_iso(iso_s)
    return t is None or t <= now


# ---------------------------------------------------------------------------
# Census helpers
# ---------------------------------------------------------------------------

def _census_index(census: dict) -> dict:
    idx = {}
    for shelf in ("decisions", "overflow_cards", "directions"):
        for c in census.get(shelf) or []:
            if isinstance(c, dict) and c.get("id"):
                idx[str(c["id"])] = c
    return idx


def _pending_pool(census: dict, active: dict,
                  holds: "dict | None" = None) -> list:
    """Ranked decision cards not yet on the surface (census order = rank).
    ``holds`` = per-item "Later" parks (item_id → until-iso) — a held item
    waits out its hold instead of re-presenting."""
    pool = []
    holds = holds or {}
    for shelf in ("decisions", "overflow_cards"):
        for c in census.get(shelf) or []:
            if not isinstance(c, dict) or not c.get("id"):
                continue
            cid = str(c["id"])
            if cid in active or cid in holds:
                continue
            if _dc.is_decision(c):
                pool.append(c)
    return pool


def urgent_eligible(card: dict, now: datetime) -> bool:
    """Structurally wrong-by-tomorrow only (mirrors the gate's piercing law):
    a producer-attested urgent KIND, a blocking cost-of-delay, or a real
    deadline before the next briefing. Never a prose keyword."""
    if str(card.get("kind") or "").lower() in _URGENT_KINDS:
        return True
    why = card.get("why_now") or {}
    if str(why.get("cost_of_delay") or "").lower() == "blocking":
        return True
    dl = _parse_iso(why.get("deadline_iso"))
    if dl is not None:
        return dl < _cfg.next_briefing(now)
    return False


def _urgent_budget_left(state: dict, now: datetime, cfg: dict) -> int:
    window = timedelta(hours=float(cfg["urgent_window_hours"]))
    recent = [t for t in (state.get("urgent_sends") or [])
              if (_parse_iso(t) or now) > now - window]
    state["urgent_sends"] = recent
    return max(0, int(cfg["urgent_interrupts"]) - len(recent))


# ---------------------------------------------------------------------------
# The pure planner
# ---------------------------------------------------------------------------

def plan(census: dict, state: dict, now: datetime,
         cfg: "dict | None" = None) -> "tuple[list, dict]":
    """(ops, state') — pure. Ops (executor contract):
      ("clear",   item_id, reason)   — item resolved/gone: flip its card state
      ("urgent",  card)              — wrong-by-tomorrow jump (budgeted)
      ("present", card)              — next paced single-decision card
      ("nudge",   pending_count)     — upsert the ONE standing nudge card
      ("batch_offer", pending_count) — "next batch?" on the same nudge card
      ("all_clear",)                 — nudge card flips to all-clear
    """
    cfg = cfg or _cfg.load()
    st = copy.deepcopy(state if isinstance(state, dict) else _fresh_state())
    for key, default in _fresh_state().items():
        st.setdefault(key, copy.deepcopy(default))
    ops: list = []

    # 0. expire timed controls (+ per-item "Later" holds)
    if st["snooze_until"] and _past(st["snooze_until"], now):
        st["snooze_until"] = None
    if st["ride_briefing_until"] and _past(st["ride_briefing_until"], now):
        st["ride_briefing_until"] = None
    st["holds"] = {k: v for k, v in (st.get("holds") or {}).items()
                   if not _past(v, now)}

    # 1. reconcile actives against the census (advance-on-clear's first half)
    idx = _census_index(census)
    for cid in list(st["active"].keys()):
        card = idx.get(cid)
        if card is None or str(card.get("state") or "open").lower() not in _OPEN_STATES:
            ops.append(("clear", cid, "resolved"))
            entry = st["active"].pop(cid)
            st["handles"].pop(entry.get("h") or "", None)
    # deferred entries that left the census stop being tracked
    st["deferred"] = {k: v for k, v in (st.get("deferred") or {}).items()
                      if k in idx}

    # 2. urgent lane — bounded jumps, independent of triage state
    budget = _urgent_budget_left(st, now, cfg)
    if budget > 0:
        for card in _pending_pool(census, st["active"], st["holds"]):
            if budget <= 0:
                break
            if urgent_eligible(card, now):
                ops.append(("urgent", card))
                # reserve the slot now so one plan can never over-jump; the
                # executor refunds the budget when the gate demotes the send.
                st["urgent_sends"].append(_iso(now))
                st["active"][str(card["id"])] = _tentative(card, now, urgent=True)
                st["handles"][_dc.handle_of(str(card["id"]))] = str(card["id"])
                budget -= 1

    # 3. paced presentation
    mode = st["mode"] or cfg["mode"]
    cap_eff = int(st["cap_override"] or cfg["cap"])
    cap_eff = max(1, min(cap_eff, int(cfg["hard_all_cap"])))
    pending = _pending_pool(census, st["active"], st["holds"])
    presenting_allowed = (mode == "auto-push") or st["triage_open"]

    # Batch pause (ask-first only): the Captain cleared a FULL batch in one
    # go (surface drained, ≥cap presented since the session opened) and more
    # waits — pause and ask on the standing card instead of auto-continuing.
    # A PARTIALLY cleared surface never pauses: each clear advances the next
    # (advance-on-clear), holding ≤cap.
    if presenting_allowed and mode != "auto-push" and not st["batch_offered"] \
            and pending and not st["active"] \
            and st["presented_in_batch"] >= cap_eff:
        ops.append(("batch_offer", len(pending)))
        st["batch_offered"] = True
        st["presented_in_batch"] = 0
        st["nudge"] = {"count": len(pending), "state": "open",
                       "updated_at": _iso(now)}
    elif presenting_allowed and not st["batch_offered"]:
        while pending and len(st["active"]) < cap_eff:
            card = pending.pop(0)
            ops.append(("present", card))
            st["active"][str(card["id"])] = _tentative(card, now, urgent=False)
            st["handles"][_dc.handle_of(str(card["id"]))] = str(card["id"])
            if mode != "auto-push":
                st["presented_in_batch"] += 1

    # 4. ask-first nudge / batch offer / all-clear on the ONE standing card
    quietable = st["snooze_until"] or st["ride_briefing_until"]
    if not pending and not st["active"]:
        if st["triage_open"] or (st.get("nudge") or {}).get("state") == "open":
            ops.append(("all_clear",))
            st["nudge"] = {"count": 0, "state": "cleared", "updated_at": _iso(now)}
        st["triage_open"] = False
        st["batch_offered"] = False
        st["presented_in_batch"] = 0
        st["cap_override"] = None
    elif mode != "auto-push" and not st["triage_open"] and not quietable \
            and len(pending) >= int(cfg["pileup"]):
        # off-cycle pileup (ask-first): ONE standing nudge card, edited in
        # place as the count changes — never a fresh message per pileup.
        prev = st.get("nudge") or {}
        if prev.get("state") != "open" or prev.get("count") != len(pending):
            ops.append(("nudge", len(pending)))
            st["nudge"] = {"count": len(pending), "state": "open",
                           "updated_at": _iso(now)}

    return ops, st


def _tentative(card: dict, now: datetime, *, urgent: bool) -> dict:
    return {"h": _dc.handle_of(str(card.get("id") or "")),
            "subject": _dc.render(card)["subject"],
            "evidence": [f"thread:{card.get('id')}"],
            "message_id": None,
            "urgent": bool(urgent),
            # ↩ Undo is only ever offered when it is TRUE: never on ceiling
            # class, never on a no-return action (money out / external send).
            "reversible": _dc.undoable(card),
            "presented_at": _iso(now)}


# ---------------------------------------------------------------------------
# Captain controls (nudge buttons / free-text throttle verbs)
# ---------------------------------------------------------------------------

def on_control(state: dict, verb: str, arg: str, now: datetime,
               cfg: "dict | None" = None) -> "tuple[dict, dict]":
    """Apply one Captain control. Returns (state', routing) where routing
    describes anything the CALLER must execute (a per-card decision routes to
    the org's ordinary decision door — this engine only re-paces)."""
    cfg = cfg or _cfg.load()
    st = copy.deepcopy(state)
    routing: dict = {"handled": True}
    if verb == "tri":
        if arg == "now":
            st.update({"triage_open": True, "batch_offered": False,
                       "presented_in_batch": 0, "snooze_until": None,
                       "ride_briefing_until": None})
            if st.get("nudge"):
                st["nudge"]["state"] = "acted"
        elif arg == "brief":
            st["ride_briefing_until"] = _iso(_cfg.next_briefing(now))
            if st.get("nudge"):
                st["nudge"]["state"] = "acted"
        elif arg == "snz":
            st["snooze_until"] = _iso(
                now + timedelta(hours=float(cfg["snooze_hours"])))
            if st.get("nudge"):
                st["nudge"]["state"] = "acted"
        else:
            routing = {"handled": False, "why": f"unknown triage arg {arg!r}"}
    elif verb == "more":
        st.update({"batch_offered": False, "presented_in_batch": 0,
                   "triage_open": True})
    elif verb == "stop":
        st.update({"triage_open": False, "batch_offered": False,
                   "cap_override": None})
    elif verb == "all":
        st.update({"cap_override": int(cfg["hard_all_cap"]), "triage_open": True,
                   "batch_offered": False, "presented_in_batch": 0})
    elif verb == "top1":
        st.update({"cap_override": 1, "triage_open": True,
                   "batch_offered": False, "presented_in_batch": 0})
    elif verb == "later":
        # a per-card "Later": park it until the next briefing (pure pacing —
        # no decision recorded; the item itself stays open in the org).
        item_id = (st.get("handles") or {}).get(arg)
        if item_id:
            entry = (st.get("active") or {}).pop(item_id, None)
            if entry:
                st["handles"].pop(entry.get("h") or "", None)
            st.setdefault("holds", {})[item_id] = _iso(_cfg.next_briefing(now))
            routing = {"handled": True, "later": True, "item_id": item_id,
                       "entry": entry}
        else:
            routing = {"handled": False, "why": "unknown card"}
    elif verb in ("ok", "edit", "skip", "undo"):
        item_id = (st.get("handles") or {}).get(arg)
        if item_id:
            routing = {"handled": True, "decision": verb, "item_id": item_id}
        else:
            routing = {"handled": False, "why": "unknown card"}
    else:
        routing = {"handled": False, "why": f"unknown verb {verb!r}"}
    return st, routing


def mark_resolved(state: dict, item_id: str, outcome: str,
                  now: datetime) -> "tuple[dict, dict | None]":
    """The integration hook: the org's decision door reports an item's
    outcome (approved / skipped / undone / closed). Returns (state', the
    active entry that was cleared or None). The caller renders the card's
    final state via the executor's clear path."""
    st = copy.deepcopy(state)
    entry = (st.get("active") or {}).pop(str(item_id), None)
    if entry:
        st["handles"].pop(entry.get("h") or "", None)
    return st, entry


# ---------------------------------------------------------------------------
# Executor — every op through framework.comms.tools (the one door)
# ---------------------------------------------------------------------------

# Nudge decision buttons: labels come from the ONE plain-language source
# (plain.BUTTON_LABELS["nudge"]) so the duration in "Snooze 2h" and any copy
# change land here without a second edit. Verbs are this engine's grammar.
# "Triage now" is master-prompt-§4 verbatim (exception recorded in
# captain-decisions 2026-07-10) — the label is data, not a literal here.
_NUDGE_VERBS = (("tri", "now"), ("tri", "brief"), ("tri", "snz"))
_BATCH_BUTTONS = [[
    {"text": "▶ Show next", "data": _dc.cb("more")},
    {"text": "✅ Done for now", "data": _dc.cb("stop")},
]]


def _nudge_buttons() -> list:
    from framework.attention import plain as plainlaw
    labels = plainlaw.BUTTON_LABELS["nudge"]
    return [[{"text": label, "data": _dc.cb(verb, arg)}
             for label, (verb, arg) in zip(labels, _NUDGE_VERBS)]]


def _nudge_kwargs(op: tuple, cfg: dict) -> dict:
    from framework.comms.surface import links as _links
    kind, situation, buttons = op[0], "", None
    if kind == "nudge":
        situation = (f"{op[1]} decision(s) are ready when you are. "
                     f"Nothing sends until you say so.")
        buttons = _nudge_buttons()
    elif kind == "batch_offer":
        situation = f"That's this round done. {op[1]} more waiting."
        buttons = [list(_BATCH_BUTTONS[0])]
    else:  # all_clear
        situation = "All clear — nothing needs you right now."
    url = _links.queue_url(cfg)
    if url and buttons:
        u = _links.url_button("🔎 See the list", url)
        if u:
            # The link rides its OWN row — a 4-across row truncates labels on
            # phones, and a truncated button is no longer unambiguous.
            buttons = buttons + [[u]]
    return {"subject": NUDGE_SUBJECT, "situation": situation,
            "kind": NUDGE_KIND, "evidence": list(NUDGE_EVIDENCE),
            "state": "open", "buttons": buttons}


def _delivered(res: dict) -> "tuple[str, int | None]":
    """(gate_action, message_id|None) from a tools.send_card result."""
    decision = (res or {}).get("decision") or {}
    action = str(decision.get("action") or "error")
    mid = None
    if action == "edit":
        mid = decision.get("message_id")
    elif action == "send":
        mids = ((res or {}).get("result") or {}).get("message_ids") or []
        mid = mids[0] if mids else None
    return action, mid


def step(*, census: "dict | None" = None, now: "datetime | None" = None,
         state: "dict | None" = None, cfg: "dict | None" = None,
         adapter=None, ch=None) -> dict:
    """One pacing tick: plan, execute through the comms tools, persist.
    Injectable census/now/state/adapter/charter for tests; live defaults
    otherwise. Returns a report of what happened (never raises)."""
    from framework.comms import tools
    cfg = cfg or _cfg.load()
    now = now or datetime.now(timezone.utc)
    persist = state is None
    if state is None:
        state = load_state()
    if census is None:
        from framework.attention.queue import build_queue
        census = build_queue(now=now)

    ops, st = plan(census, state, now, cfg)
    report = {"ops": [], "active": 0, "deferred": 0}

    for op in ops:
        kind = op[0]
        try:
            if kind in ("present", "urgent"):
                card = op[1]
                cid = str(card.get("id") or "")
                kwargs = _dc.render(card, state="open", now=now, cfg=cfg)
                res = tools.send_card(
                    subject=kwargs["subject"], situation=kwargs["situation"],
                    kind=kwargs["kind"], lane=kwargs["lane"],
                    evidence=kwargs["evidence"],
                    urgency=("ping-now" if kind == "urgent" else None),
                    state="open", deadline_iso=kwargs["deadline_iso"],
                    pid_marker=kwargs["pid_marker"], buttons=kwargs["buttons"],
                    escalation=kwargs.get("escalation"),
                    adapter=adapter, ch=ch, now=now)
                action, mid = _delivered(res)
                if action in ("send", "edit"):
                    entry = st["active"].get(cid)
                    if entry is not None:
                        entry["message_id"] = mid
                else:
                    # QUIET-HOURS / charter passthrough: not on the surface →
                    # not active; the gate already routed it (e.g. briefing).
                    entry = st["active"].pop(cid, None)
                    if entry:
                        st["handles"].pop(entry.get("h") or "", None)
                        if kind != "urgent" and st["presented_in_batch"] > 0:
                            st["presented_in_batch"] -= 1
                    if kind == "urgent" and st["urgent_sends"]:
                        st["urgent_sends"].pop()   # refund the reserved slot
                    st["deferred"][cid] = action
                report["ops"].append((kind, cid, action))
            elif kind in ("nudge", "batch_offer", "all_clear"):
                res = tools.send_card(**_nudge_kwargs(op, cfg),
                                      adapter=adapter, ch=ch, now=now)
                action, _mid = _delivered(res)
                if action not in ("send", "edit", "suppress") \
                        and (st.get("nudge") or {}).get("state") == "open":
                    # the nudge itself was quieted (e.g. quiet hours) —
                    # let the next tick retry rather than believing it landed
                    st["nudge"]["state"] = "deferred"
                report["ops"].append((kind,) + tuple(op[1:]) + (action,))
            elif kind == "clear":
                cid, reason = op[1], op[2]
                entry = (state.get("active") or {}).get(cid) or {}
                if entry.get("message_id") is not None:
                    final = "done" if reason.endswith("ok") or reason == "resolved" \
                        else "skipped"
                    buttons = None
                    if final == "done" and entry.get("reversible") \
                            and reason.endswith("ok"):
                        buttons = [[{"text": "↩ Undo",
                                     "data": _dc.cb("undo", entry.get("h") or "")}]]
                    tools.edit_card(subject=entry.get("subject") or "",
                                    evidence=list(entry.get("evidence") or []),
                                    situation=_dc.final_line(final),
                                    state=final, buttons=buttons,
                                    adapter=adapter, ch=ch, now=now)
                report["ops"].append((kind, cid, reason))
        except Exception as e:  # noqa: BLE001 — one op must never kill the tick
            print(f"[surface.pacing] op {kind} failed: {e}", file=sys.stderr)
            report["ops"].append((kind, "error", str(e)[:120]))

    report["active"] = len(st.get("active") or {})
    report["deferred"] = len(st.get("deferred") or {})
    if persist:
        save_state(st)
    else:
        state.clear()
        state.update(st)
    return report
