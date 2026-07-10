"""framework.comms.surface.engine — the TG-engine façade.

Two entry points the rest of the org wires to:

* ``run_surface_tick()`` — one pass: census → pacing step (paced single-
  decision cards, nudge lifecycle, urgent lane) → pin step (auto-advance).
  Idempotent between changes (standing-card dedup suppresses no-ops). Nothing
  schedules this from inside the module — arming it is a deployment decision.

* ``on_callback(data)`` — the strict parser/dispatcher for the engine's
  inline-button grammar ``cv2|<verb>|<arg>``. Pacing controls apply
  immediately (durable state) and re-tick; PER-CARD DECISIONS ARE NOT
  EXECUTED HERE — the returned routing names the item and the Captain's
  chosen action, and the CALLER (the org's ordinary decision door — the same
  path a typed reply takes) executes it with full authority checks
  (equal-authority-door law). After the door reports the outcome,
  ``report_outcome`` flips the card's state in place and advances the pin.

Engagement (§5's concrete gap): any callback on the pinned item, and any
outcome report, marks it engaged — the next tick unpins + advances.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from framework.comms.surface import config as _cfg
from framework.comms.surface import decision_card as _dc
from framework.comms.surface import pacing as _pacing
from framework.comms.surface import pin_lifecycle as _pin


def run_surface_tick(*, census: "dict | None" = None,
                     now: "datetime | None" = None,
                     engaged: "set | frozenset" = frozenset(),
                     adapter=None, ch=None) -> dict:
    """One full surface pass. Injectable census/now/adapter/charter for
    tests; live census (the germline queue) otherwise."""
    now = now or datetime.now(timezone.utc)
    if census is None:
        from framework.attention.queue import build_queue
        census = build_queue(now=now)
    pace = _pacing.step(census=census, now=now, adapter=adapter, ch=ch)
    pin = _pin.step(census=census, now=now, engaged=engaged,
                    adapter=adapter, ch=ch)
    return {"pacing": pace, "pin": pin, "at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}


def parse_callback(data: str) -> "tuple[str, str] | None":
    """Strict parse of ``cv2|<verb>|<arg>`` → (verb, arg) or None. Unknown
    prefixes/verbs are ignored (another surface's buttons are not ours)."""
    parts = str(data or "").split("|")
    if len(parts) < 2 or parts[0] != _dc.CB_PREFIX:
        return None
    verb = parts[1]
    if verb not in _dc.CB_VERBS:
        return None
    arg = parts[2] if len(parts) > 2 else ""
    if len(arg) > 64 or any(c in arg for c in "\n\r\t "):
        return None
    return verb, arg


def on_callback(data: str, *, now: "datetime | None" = None,
                census: "dict | None" = None,
                adapter=None, ch=None) -> dict:
    """Handle one inline-button tap. Returns
    ``{"status": "ignored"}`` for foreign data, else
    ``{"status": "ok", "routing": {...}}`` — with ``routing["decision"]``
    set when the CALLER must run the item through the decision door."""
    parsed = parse_callback(data)
    if parsed is None:
        return {"status": "ignored"}
    verb, arg = parsed
    now = now or datetime.now(timezone.utc)
    cfg = _cfg.load()

    state = _pacing.load_state()
    new_state, routing = _pacing.on_control(state, verb, arg, now, cfg)
    _pacing.save_state(new_state)

    if routing.get("later"):
        # flip the parked card in place ("comes back at the next briefing")
        entry = routing.get("entry") or {}
        if entry.get("message_id") is not None:
            from framework.comms import tools
            try:
                tools.edit_card(subject=entry.get("subject") or "",
                                evidence=list(entry.get("evidence") or []),
                                situation=_dc.final_line("expired"),
                                state="expired", buttons=None,
                                adapter=adapter, ch=ch, now=now)
            except Exception as e:  # noqa: BLE001
                print(f"[surface.engine] later edit failed: {e}", file=sys.stderr)

    engaged: set = set()
    if routing.get("item_id"):
        pin_state = _pin.load_state()
        if str(pin_state.get("item_id") or "") == str(routing["item_id"]):
            engaged.add(str(routing["item_id"]))

    # A pacing control changes what should be on the surface — re-tick now.
    if routing.get("handled") and "decision" not in routing:
        try:
            run_surface_tick(census=census, now=now, engaged=engaged,
                             adapter=adapter, ch=ch)
        except Exception as e:  # noqa: BLE001
            print(f"[surface.engine] post-control tick failed: {e}",
                  file=sys.stderr)
    elif engaged:
        # a decision tap on the pinned item advances the pin immediately;
        # the decision itself still rides the door.
        try:
            _pin.step(census=census, now=now, engaged=engaged,
                      adapter=adapter, ch=ch)
        except Exception as e:  # noqa: BLE001
            print(f"[surface.engine] pin advance failed: {e}", file=sys.stderr)
    return {"status": "ok", "routing": routing}


def report_outcome(item_id: str, outcome: str, *,
                   now: "datetime | None" = None,
                   census: "dict | None" = None,
                   adapter=None, ch=None) -> dict:
    """The decision door's report-back: flip the item's card to its final
    state (edit-in-place — the label-soup replacement) and advance the pin.
    ``outcome`` ∈ approved | skipped | undone | closed."""
    from framework.comms import tools
    now = now or datetime.now(timezone.utc)
    state = _pacing.load_state()
    new_state, entry = _pacing.mark_resolved(state, item_id, outcome, now)
    _pacing.save_state(new_state)
    edited = False
    if entry and entry.get("message_id") is not None:
        final = "done" if outcome in ("approved", "closed") else "skipped"
        buttons = None
        if outcome == "approved" and entry.get("reversible"):
            buttons = [[{"text": "↩ Undo",
                         "data": _dc.cb("undo", entry.get("h") or "")}]]
        try:
            tools.edit_card(subject=entry.get("subject") or "",
                            evidence=list(entry.get("evidence") or []),
                            situation=_dc.final_line(final),
                            state=final, buttons=buttons,
                            adapter=adapter, ch=ch, now=now)
            edited = True
        except Exception as e:  # noqa: BLE001
            print(f"[surface.engine] outcome edit failed: {e}", file=sys.stderr)
    try:
        _pin.step(census=census, now=now, engaged={str(item_id)},
                  adapter=adapter, ch=ch)
    except Exception as e:  # noqa: BLE001
        print(f"[surface.engine] pin advance failed: {e}", file=sys.stderr)
    return {"status": "ok", "edited": edited}


def main(argv: "list | None" = None) -> int:
    import argparse
    import json as _json
    ap = argparse.ArgumentParser(description="captain-surface TG engine")
    ap.add_argument("--tick", action="store_true", help="run one surface tick")
    ap.add_argument("--callback", help="handle one cv2|… button tap")
    args = ap.parse_args(argv)
    if args.callback:
        print(_json.dumps(on_callback(args.callback)))
        return 0
    if args.tick:
        print(_json.dumps(run_surface_tick()))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
