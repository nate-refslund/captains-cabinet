"""framework.comms.surface.tap_wire — mechanical inline-tap semantics (no LLM).

WHY (found live 2026-07-11): the Captain's inline-button taps were relayed as
bracket lines into the Chair's tmux session — an LLM turn (minutes, or never)
between a tap and its effect, and no visible feedback beyond a silent spinner
clear. The 07:35:04Z "At next briefing" tap on the standing briefing card
applied at 07:38:45Z (3m41s), with its horizon computed in the wrong timezone;
a 2026-07-09 tap's ack 400'd entirely after a long-poll timeout storm. A tap
is MECHANICAL input on engine-minted ids — nothing about it needs judgment:

* PACING / DEFER verbs (``later``, ``tri|now/brief/snz``, ``more``, ``stop``,
  ``all``, ``top1``) apply through ``engine.on_callback``: durable pacing
  state (flock + atomic), the parked card's edit-in-place face, and the
  post-control re-tick — that IS the demote-to-briefing routing plus the
  pacing advance. Defer is narrowing-only; no authority question. For the
  batch controls (``tri|…``) the TAPPED card additionally gets a receipt: its
  keyboard is swapped for one inert state row via the injected
  ``edit_markup`` (content-preserving — never a re-send).
* DECISION verbs (``ok`` / ``skip``) route through the SAME server-side
  authority door the dashboard uses — ``framework.attention.verdicts.fire``:
  verify-at-fire freshness (live census; pid present; state undecided),
  verb legality (ritual-print kinds REFUSE tap-approve), then the canonical
  reply grammar through ``binder_wire.handle_captain_update`` (the
  equal-authority-door law — the Captain-authenticated chat is a binder
  surface; ``callback_data`` carries ids only, never free text). Receipts
  and denials journal to the append-only feed inside the door (tagged
  ``source:"telegram-tap"``). On success ``engine.report_outcome`` flips the
  card ✅/✗ in place; on a RITUAL/STALE denial the card re-renders its
  canonical open face from census truth (self-heals a stale button face).
* NEEDS verbs (``ndg``/``ndl``/``ndd`` — the captain-reminder one-tap card's
  ✓ Done / ⏰ Later / ✗ Drop buttons) compose the CANONICAL typed binder line
  (``grant/later/deny NEED-<hex8>``) and route it through the SAME door the
  Captain's typed replies use — ``binder_wire.handle_captain_update`` with
  its own gates (CABINET_NEEDS_WIRED, captain_verified, stale-id
  fail-closed). The arg is re-validated as exactly the 8-hex fingerprint
  tail BEFORE composing, so a hostile callback payload can never splice
  grammar; the tapped card's keyboard swaps to one inert receipt row. The
  due-at tick's reconcile pass finishes the loop (grant → close, later →
  due_at +7d bump via the guarded 041 path).
* ``edit`` / ``undo`` verbs still relay to the Chair — an edit needs typed
  text; an undo rides the acted-registry reply grammar.

VISIBLE TRUTH vs CENSUS FOLD: the edit-in-place faces here are the INTERIM
visible truth. The census FOLD (situation removal) still rides the locked
queue/situations estate and may lag until the window-4 ceremony re-points it
(docs/proposals/germline-window-4-deferral-2026-07-10.md — §"Tap receipts").

Foundation module: launcher-neutral, no axis branches, stdlib-only at import.
Framework siblings import lazily inside functions so a broken sibling can
never break the caller's receive path (the inbound poller fail-opens to its
bracket-line relay on ANY exception from here).
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone

#: Instant-ack toasts by (verb, arg); (verb, None) is the verb-wide default.
#: The DEFER toast is the contract line — the tap's whole point is that the
#: Captain SEES the defer land the moment he taps.
DEFER_TOAST = "⏸ Deferred to next briefing"
_TOASTS: dict = {
    ("later", None): DEFER_TOAST,
    ("tri", "brief"): DEFER_TOAST,
    ("tri", "now"): "▶ Triage open — next cards coming",
    ("tri", "snz"): "😴 Snoozed",
    ("ok", None): "✓ Recording your approval…",
    ("skip", None): "✗ Recording the no…",
    ("edit", None): "✎ Reply to this card with the change",
    ("undo", None): "↩ Sending the undo to the Chair",
    ("more", None): "▶ Next cards coming",
    ("stop", None): "✅ Done for now",
    ("all", None): "Showing everything waiting",
    ("top1", None): "Top one only",
    ("ndg", None): "✓ Done — recording…",
    ("ndl", None): "⏰ Snoozed 7d",
    ("ndd", None): "✗ Dropping…",
}

#: Batch-control receipt labels for the tapped card's swapped keyboard.
_MARK_LABELS = {"brief": DEFER_TOAST, "snz": "😴 Snoozed", "now": "▶ Triage open"}

#: Needs-verb receipt labels (the reminder card's swapped keyboard).
_NEED_MARK_LABELS = {"ndg": "✓ Done", "ndl": "⏰ Snoozed 7d", "ndd": "✗ Dropped"}

#: Door-denial codes that CONCLUDE the tap mechanically (no Chair relay):
#: ritual → the card re-renders its typed-sign-off face; decided → the next
#: pacing tick's reconcile pass flips the final face (≤ one tick of lag).
_CONCLUDED_DENIALS = frozenset({"ritual", "decided"})

_DOOR_VERB = {"ok": "approve", "skip": "no"}


def classify(data: str) -> "tuple[str | None, str, str]":
    """(verb, arg, toast) for one raw ``callback_data`` — PURE (no I/O), so
    the poller can pick the ack toast before anything else runs. Foreign /
    malformed data → ``(None, "", "")`` (ack clears the spinner silently and
    the status-quo bracket relay carries the tap)."""
    try:
        from framework.comms.surface import engine as _engine
        parsed = _engine.parse_callback(data)
    except Exception:
        parsed = None
    if parsed is None:
        return None, "", ""
    verb, arg = parsed
    toast = _TOASTS.get((verb, arg)) or _TOASTS.get((verb, None)) or ""
    return verb, arg, toast


def _census_row(census: dict, item_id: str) -> "dict | None":
    """The census card for ``item_id`` on the door's shelves (decisions +
    directions — the same freshness surface ``verdicts.fire`` verifies, so a
    tap can never fire what the dashboard door could not)."""
    for shelf in ("decisions", "directions"):
        rows = census.get(shelf)
        if not isinstance(rows, list):
            continue
        for r in rows:
            if isinstance(r, dict) and str(r.get("id") or "") == str(item_id):
                return r
    return None


def _tap_journal(row: dict) -> dict:
    """The door's journal seam with honest provenance: verdict receipts fired
    from a Telegram tap are ``source:"telegram-tap"``, never ``dashboard``."""
    from framework.attention import feed
    stamped = dict(row)
    stamped["source"] = "telegram-tap"
    return feed.append_event(stamped)


def _repaint_open_face(card: dict, *, now: datetime,
                       adapter=None, ch=None) -> bool:
    """Re-render a card's CANONICAL open face from census truth (edit-in-place
    through the gate). Self-heals a stale button face — e.g. a ritual card
    somehow showing an ✓ Approve button repaints to its typed-sign-off face."""
    from framework.comms import tools
    from framework.comms.surface import config as _cfg
    from framework.comms.surface import decision_card as _dc
    kwargs = _dc.render(card, state="open", now=now, cfg=_cfg.load())
    res = tools.edit_card(subject=kwargs["subject"],
                          evidence=list(kwargs["evidence"] or []),
                          situation=kwargs["situation"], state="open",
                          lane=kwargs["lane"], buttons=kwargs["buttons"],
                          adapter=adapter, ch=ch, now=now)
    action = str(((res or {}).get("decision") or {}).get("action") or "")
    return action in ("send", "edit", "suppress")


def _apply_pacing(verb: str, arg: str, data: str, *, message_id, now,
                  census, adapter, ch, edit_markup) -> dict:
    """later / tri|… / more / stop / all / top1 → engine.on_callback (state +
    card flip + re-tick), plus the tapped-card keyboard receipt for tri|…."""
    from framework.comms.surface import engine as _engine
    res = _engine.on_callback(data, now=now, census=census,
                              adapter=adapter, ch=ch)
    routing = (res or {}).get("routing") or {}
    handled = bool(routing.get("handled"))
    mode = f"pacing:{verb}" + (f"|{arg}" if arg else "")
    if not handled:
        return {"handled": False, "relay": True, "mode": mode,
                "summary": str(routing.get("why") or "control not applied")}
    out: dict = {"handled": True, "relay": False, "mode": mode}
    if verb == "later":
        out["item_id"] = str(routing.get("item_id") or "")
        out["outcome"] = "deferred"
        out["summary"] = "deferred to next briefing (card parked + flipped)"
    else:
        out["summary"] = f"pacing control {verb}|{arg} applied" if arg \
            else f"pacing control {verb} applied"
    if verb == "tri" and edit_markup is not None and message_id:
        # Receipt on the TAPPED card: swap the buttons for one inert state
        # row. Content-preserving (a briefing card keeps its briefing); a
        # re-tap of the inert row re-applies the same control (idempotent).
        label = _MARK_LABELS.get(arg, "✓")
        try:
            edit_markup(int(message_id),
                        [[{"text": label, "callback_data": str(data)[:64]}]])
            out["marked"] = True
        except Exception:
            out["marked"] = False   # receipt UX only — never un-handle the tap
    return out


def _apply_decision(verb: str, arg: str, *, now, census, adapter, ch,
                    wire, journal) -> dict:
    """ok / skip → the dashboard door's exact chain, fired from a tap."""
    from framework.attention import verdicts as _verdicts
    from framework.comms.surface import engine as _engine
    from framework.comms.surface import pacing as _pacing

    mode = f"decision:{verb}"
    state = _pacing.load_state()
    item_id = (state.get("handles") or {}).get(arg)
    if not item_id:
        return {"handled": False, "relay": True, "mode": mode,
                "summary": "unknown card handle — relayed to the Chair"}

    doc = census if census is not None else _verdicts.read_census(now=now)
    if doc is None:
        return {"handled": False, "relay": True, "mode": mode,
                "item_id": str(item_id),
                "summary": "census stale/absent — relayed to the Chair"}
    row = _census_row(doc, str(item_id))
    if row is None or not str(row.get("pid") or ""):
        return {"handled": False, "relay": True, "mode": mode,
                "item_id": str(item_id),
                "summary": "card gone from census / no pid — relayed"}

    pid = str(row.get("pid"))
    res = _verdicts.fire(pid, _DOOR_VERB[verb], _verdicts.revision_of(row),
                         census=doc, wire=wire,
                         journal=journal or _tap_journal, now=now,
                         skip_text="skip: declined from a card tap (✗ No)")

    if res.get("ok"):
        outcome = "approved" if verb == "ok" else "skipped"
        try:
            _engine.report_outcome(str(item_id), outcome, now=now,
                                   census=doc, adapter=adapter, ch=ch)
        except Exception:
            pass   # face repaint is UX; the verdict is already recorded
        return {"handled": True, "relay": True, "mode": mode,
                "item_id": str(item_id), "outcome": outcome,
                "summary": f"{outcome} via the verdict door pid={pid[:44]} "
                           f"(wire={res.get('wire_status') or 'n/a'})"}

    code = str(res.get("code") or "denied")
    out = {"handled": code in _CONCLUDED_DENIALS,
           "relay": code not in _CONCLUDED_DENIALS,
           "mode": mode, "item_id": str(item_id),
           "outcome": f"denied:{code}",
           "summary": f"door denied ({code}): "
                      f"{str(res.get('message') or '')[:100]}"}
    if code == "ritual":
        # The canonical open face carries "needs your typed sign-off" and NO
        # approve button — repainting it is the honest mechanical answer.
        try:
            out["repainted"] = _repaint_open_face(row, now=now,
                                                  adapter=adapter, ch=ch)
        except Exception:
            out["repainted"] = False
    return out


#: The canonical typed binder line each needs-verb tap composes. The tap IS
#: the typed verb (equal-authority-door law): it rides binder_wire's own
#: NEED grammar, gates (CABINET_NEEDS_WIRED + captain_verified) and ledger
#: mark — a tap can never do more than the Captain typing the same words.
_NEED_VERB_TEXT = {
    "ndg": "grant {nid}",
    "ndl": "later {nid}",
    "ndd": "deny {nid}: dropped from a card tap (✗ Drop)",
}

_NEED_ARG_RE = re.compile(r"[0-9a-f]{8}\Z")


def _default_need_wire(text: str, quoted: str) -> dict:
    from framework.frontdoor import binder_wire
    return binder_wire.handle_captain_update(
        text, quoted, log=lambda m: print(f"[tap-wire] {m}", file=sys.stderr))


def _apply_need(verb: str, arg: str, data: str, *, message_id, wire,
                edit_markup) -> dict:
    """ndg / ndl / ndd → the SAME binder door the Captain's typed
    grant/later/deny NEED-<hex> replies use (captain-reminder one-tap cards).

    The arg is re-validated as EXACTLY the 8-hex fingerprint tail before any
    text is composed — a malformed/oversized/uppercase arg fails closed to
    the Chair relay, so hostile callback payloads can never splice binder
    grammar. On a marked need the tapped card's keyboard swaps to one inert
    receipt row; the due-at tick's reconcile pass then closes (grant) or
    due_at-bumps (later) the reminder row — no new state machine here."""
    mode = f"need:{verb}"
    if not _NEED_ARG_RE.fullmatch(arg or ""):
        return {"handled": False, "relay": True, "mode": mode,
                "summary": "malformed need id — relayed to the Chair"}
    nid = f"NEED-{arg}"
    text = _NEED_VERB_TEXT[verb].format(nid=nid)
    res = (wire or _default_need_wire)(text, "") or {}
    if not (res.get("handled") and res.get("need")):
        # needs plane dark / unknown-stale id / door refusal — the typed-verb
        # door already fail-closes; surface the same refusal to the Chair.
        return {"handled": False, "relay": True, "mode": mode,
                "item_id": nid,
                "summary": f"needs door refused: "
                           f"{str(res.get('reason') or res.get('summary') or 'not handled')[:120]}"}
    out = {"handled": True, "relay": False, "mode": mode, "item_id": nid,
           "outcome": str(res.get("need")),
           "summary": str(res.get("summary") or f"{nid} → {res.get('need')}")[:200]}
    if edit_markup is not None and message_id:
        # Receipt on the TAPPED card: swap the buttons for one inert state
        # row (idempotent re-tap re-fires the same verb — the ledger mark is
        # last-write-wins on the same status, a no-op).
        try:
            edit_markup(int(message_id),
                        [[{"text": _NEED_MARK_LABELS[verb],
                           "callback_data": str(data)[:64]}]])
            out["marked"] = True
        except Exception:
            out["marked"] = False   # receipt UX only — never un-handle the tap
    return out


def apply_tap(data: str, *, message_id: "int | None" = None,
              now: "datetime | None" = None, census: "dict | None" = None,
              adapter=None, ch=None, edit_markup=None, wire=None,
              journal=None) -> dict:
    """Mechanically apply ONE Captain tap. Returns
    ``{"handled", "relay", "mode", "summary", ...}`` — ``handled`` means the
    tap's semantics were fully applied server-side; ``relay`` means the
    caller should STILL inject the bracket line for the Chair (decision
    receipts for lesson-harvest, or anything not mechanically concluded).

    Injectable seams (tests + the poller): ``census`` (a fresh census doc),
    ``adapter``/``ch`` (comms delivery + charter), ``edit_markup(message_id,
    keyboard_rows)`` (the tapped-card keyboard receipt), ``wire`` and
    ``journal`` (the verdict door's own seams). Never raises past its
    boundary — a failure returns ``handled=False, relay=True`` so the caller
    falls back to the status-quo relay."""
    verb, arg, _toast = classify(data)
    if verb is None:
        return {"handled": False, "relay": True, "mode": "foreign",
                "summary": ""}
    now = now or datetime.now(timezone.utc)
    try:
        if verb in ("edit", "undo"):
            # Typed follow-up / acted-registry grammar — the Chair's lane.
            return {"handled": False, "relay": True, "mode": f"chair:{verb}",
                    "summary": "needs the Chair (typed follow-up)"}
        if verb in ("ndg", "ndl", "ndd"):
            # captain-reminder one-tap card → the typed NEED-verb door.
            return _apply_need(verb, arg, data, message_id=message_id,
                               wire=wire, edit_markup=edit_markup)
        if verb in ("later", "tri", "more", "stop", "all", "top1"):
            return _apply_pacing(verb, arg, data, message_id=message_id,
                                 now=now, census=census, adapter=adapter,
                                 ch=ch, edit_markup=edit_markup)
        return _apply_decision(verb, arg, now=now, census=census,
                               adapter=adapter, ch=ch, wire=wire,
                               journal=journal)
    except Exception as e:  # noqa: BLE001 — fail-open to the bracket relay
        return {"handled": False, "relay": True, "mode": f"error:{verb}",
                "summary": f"tap-wire error ({type(e).__name__}) — relayed"}
