"""tap_wire — mechanical inline-tap semantics (tap-pipeline fix 2026-07-11).

Pins the contract the poller depends on:
  * classify is pure and yields the instant-ack toast (defer = the ⏸ line);
  * a per-card "Later" parks the item until the next briefing AND flips the
    card's face in place — no LLM, no relay;
  * a batch defer (tri|brief) quiets the surface and stamps the tapped
    card's keyboard receipt;
  * Approve/No route the SAME server-side verdict door the dashboard uses
    (canonical grammar, verify-at-fire, feed-journaled) and flip ✅/✗;
  * ritual-print kinds REFUSE tap-approve (denial journaled, canonical
    typed-sign-off face repainted, nothing fired);
  * every failure path fail-opens to relay=True (the poller's bracket line).

Hermetic via conftest: tmp CABINET_ATTENTION_DIR, UTC captain clock,
briefings 07:30/19:30, FakeAdapter, real charter. Census is ALWAYS injected
so no test folds the live estate.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from framework.comms.surface import decision_card as dc
from framework.comms.surface import pacing
from framework.comms.surface import tap_wire

NOW = datetime(2026, 7, 11, 10, 0, tzinfo=timezone.utc)
NOW_ISO = "2026-07-11T10:00:00Z"
NEXT_BRIEFING_ISO = "2026-07-11T19:30:00Z"   # conftest clock: UTC, 07:30/19:30


def _card(item_id="sit-1", pid="lane|action-card|fix-the-mast", *,
          kind="action-proposal", one_tap=None, what="Fix the mast"):
    return {"id": item_id, "pid": pid, "kind": kind, "state": "open",
            "what": what, "created_ts": NOW_ISO,
            "one_tap": one_tap or {"approve": "direct", "veto": "direct",
                                   "defer": "direct"}}


def _census(*cards, shelf="decisions"):
    return {"generated_at": NOW_ISO, "decisions": list(cards) if shelf == "decisions" else [],
            "directions": list(cards) if shelf == "directions" else []}


def _seed_active(item_id="sit-1", subject="Fix the mast", message_id=501):
    h = dc.handle_of(item_id)
    st = pacing.load_state()
    st["active"][item_id] = {"h": h, "subject": subject,
                             "evidence": [f"thread:{item_id}"],
                             "message_id": message_id, "urgent": False,
                             "reversible": True, "presented_at": NOW_ISO}
    st["handles"][h] = item_id
    pacing.save_state(st)
    return h


def _bodies(adapter):
    return [e["body"] for e in adapter.edits] + [s["body"] for s in adapter.sends]


# ---------------------------------------------------------------------------
# classify — pure toast selection
# ---------------------------------------------------------------------------

def test_classify_defer_toasts_and_purity():
    assert tap_wire.classify("cv2|later|abc123abc123") == \
        ("later", "abc123abc123", tap_wire.DEFER_TOAST)
    assert tap_wire.classify("cv2|tri|brief") == ("tri", "brief", tap_wire.DEFER_TOAST)
    verb, arg, toast = tap_wire.classify("cv2|ok|abc123abc123")
    assert (verb, arg) == ("ok", "abc123abc123") and "✓" in toast


def test_classify_foreign_data_is_inert():
    assert tap_wire.classify("gwtest:ok") == (None, "", "")
    assert tap_wire.classify("") == (None, "", "")
    assert tap_wire.classify("cv2|nosuchverb|x") == (None, "", "")


def test_foreign_data_applies_nothing_and_relays():
    res = tap_wire.apply_tap("gwtest:ok", message_id=9)
    assert res == {"handled": False, "relay": True, "mode": "foreign",
                   "summary": ""}


# ---------------------------------------------------------------------------
# Later — the per-card defer is fully mechanical
# ---------------------------------------------------------------------------

def test_later_parks_until_next_briefing_and_flips_card(adapter, charter):
    h = _seed_active("sit-1")
    res = tap_wire.apply_tap(f"cv2|later|{h}", message_id=501, now=NOW,
                             census=_census(_card("sit-1")),
                             adapter=adapter, ch=charter)
    assert res["handled"] is True and res["relay"] is False
    assert res["outcome"] == "deferred" and res["item_id"] == "sit-1"
    st = pacing.load_state()
    assert st["holds"] == {"sit-1": NEXT_BRIEFING_ISO}   # demote-to-briefing
    assert "sit-1" not in st["active"]                   # pacing advanced
    faces = _bodies(adapter)
    assert any("⏸" in b and "next briefing" in b for b in faces), faces


def test_later_unknown_handle_relays_to_chair(adapter, charter):
    res = tap_wire.apply_tap("cv2|later|" + "0" * 12, now=NOW,
                             census=_census(), adapter=adapter, ch=charter)
    assert res["handled"] is False and res["relay"] is True


# ---------------------------------------------------------------------------
# tri|brief — the batch defer quiets the surface + stamps the tapped card
# ---------------------------------------------------------------------------

def test_tri_brief_sets_ride_and_stamps_keyboard(adapter, charter):
    marks = []
    res = tap_wire.apply_tap(
        "cv2|tri|brief", message_id=77, now=NOW, census=_census(),
        adapter=adapter, ch=charter,
        edit_markup=lambda mid, kb: marks.append((mid, kb)))
    assert res["handled"] is True and res["relay"] is False
    assert res["marked"] is True
    assert pacing.load_state()["ride_briefing_until"] == NEXT_BRIEFING_ISO
    assert marks == [(77, [[{"text": tap_wire.DEFER_TOAST,
                             "callback_data": "cv2|tri|brief"}]])]


def test_tri_brief_markup_failure_never_unhandles(adapter, charter):
    def _boom(_mid, _kb):
        raise RuntimeError("edit failed")
    res = tap_wire.apply_tap("cv2|tri|brief", message_id=77, now=NOW,
                             census=_census(), adapter=adapter, ch=charter,
                             edit_markup=_boom)
    assert res["handled"] is True and res["marked"] is False
    assert pacing.load_state()["ride_briefing_until"] == NEXT_BRIEFING_ISO


# ---------------------------------------------------------------------------
# Approve / No — the dashboard door's exact chain, fired from a tap
# ---------------------------------------------------------------------------

def test_ok_routes_through_door_with_canonical_grammar(adapter, charter):
    h = _seed_active("sit-9", subject="Fix thing")
    card = _card("sit-9", pid="lane|action-card|fix-thing", what="Fix thing")
    wired, journal = [], []

    def _wire(text, quoted):
        wired.append((text, quoted))
        return {"handled": True, "status": "decided", "verdict": "confirmed",
                "delivery": {"ok": True}}

    res = tap_wire.apply_tap(
        f"cv2|ok|{h}", message_id=502, now=NOW, census=_census(card),
        adapter=adapter, ch=charter, wire=_wire,
        journal=lambda row: journal.append(row) or {"seq": len(journal)})

    assert wired == [("approve", "·lane|action-card|fix-thing·")]
    assert res["handled"] is True and res["outcome"] == "approved"
    assert res["relay"] is True          # the Chair still harvests lessons
    assert "sit-9" not in pacing.load_state()["active"]   # resolved + advanced
    assert any(r.get("phase") == "fire" and r.get("verb") == "approve"
               for r in journal)
    assert any("Approved" in b for b in _bodies(adapter))  # ✅ edit-in-place


def test_skip_maps_to_no_with_tap_provenance(adapter, charter):
    h = _seed_active("sit-9", subject="Fix thing")
    card = _card("sit-9", pid="lane|action-card|fix-thing", what="Fix thing")
    wired = []

    def _wire(text, quoted):
        wired.append((text, quoted))
        return {"handled": True, "status": "decided", "verdict": "wrong"}

    res = tap_wire.apply_tap(
        f"cv2|skip|{h}", message_id=502, now=NOW, census=_census(card),
        adapter=adapter, ch=charter, wire=_wire,
        journal=lambda row: {"seq": 1})
    assert len(wired) == 1
    text, quoted = wired[0]
    assert text.startswith("skip:") and "card tap" in text   # honest provenance
    assert "dashboard" not in text
    assert quoted == "·lane|action-card|fix-thing·"
    assert res["outcome"] == "skipped"


def test_ritual_refuses_tap_approve_and_repaints(adapter, charter):
    h = _seed_active("sit-r", subject="Ratify the outcome")
    card = _card("sit-r", pid="chair|ratify|outcome-1",
                 kind="outcome-ratification", what="Ratify the outcome",
                 one_tap={"approve": "ritual-print", "veto": "direct",
                          "defer": "direct"})
    wired, journal = [], []
    res = tap_wire.apply_tap(
        f"cv2|ok|{h}", message_id=503, now=NOW,
        census=_census(card, shelf="directions"),
        adapter=adapter, ch=charter,
        wire=lambda t, q: wired.append((t, q)) or {"handled": True},
        journal=lambda row: journal.append(row) or {"seq": len(journal)})

    assert wired == []                                   # the wire never fires
    assert res["outcome"] == "denied:ritual"
    assert res["handled"] is True and res["relay"] is False
    assert res.get("repainted") is True
    assert any(r.get("phase") == "deny" and r.get("code") == "ritual"
               for r in journal)
    assert any("typed sign-off" in b for b in _bodies(adapter))


def test_decision_without_census_relays(adapter):
    h = _seed_active("sit-9")
    res = tap_wire.apply_tap(f"cv2|ok|{h}", now=NOW, census=None,
                             adapter=adapter)   # hermetic dir: no queue.json
    assert res["handled"] is False and res["relay"] is True
    assert "census" in res["summary"]


def test_decision_unknown_handle_relays(adapter):
    res = tap_wire.apply_tap("cv2|ok|ffffffffffff", now=NOW,
                             census=_census(), adapter=adapter)
    assert res["handled"] is False and res["relay"] is True


def test_edit_and_undo_stay_with_the_chair():
    for verb in ("edit", "undo"):
        res = tap_wire.apply_tap(f"cv2|{verb}|abcabcabcabc", now=NOW)
        assert res["handled"] is False and res["relay"] is True
        assert res["mode"] == f"chair:{verb}"


def test_tap_journal_stamps_telegram_tap_provenance(monkeypatch):
    seen = {}

    def _capture(row):
        seen.update(row)
        return {"seq": 7, **row}

    from framework.attention import feed
    monkeypatch.setattr(feed, "append_event", _capture)
    tap_wire._tap_journal({"direction": "in", "kind": "verdict",
                           "source": "dashboard", "phase": "fire"})
    assert seen["source"] == "telegram-tap"


# ---------------------------------------------------------------------------
# ndg / ndl / ndd — the captain-reminder card's one-tap needs verbs
# (equal-authority door: the tap composes the CANONICAL typed binder line)
# ---------------------------------------------------------------------------

HEX = "a1b2c3d4"


def _need_wire_ok(calls, need="approved_pending_apply"):
    def _wire(text, quoted):
        calls.append((text, quoted))
        return {"handled": True, "need": need, "need_id": f"NEED-{HEX}",
                "summary": f"need NEED-{HEX} → {need}"}
    return _wire


def test_classify_need_verb_toasts():
    assert tap_wire.classify(f"cv2|ndg|{HEX}")[0] == "ndg"
    assert "✓" in tap_wire.classify(f"cv2|ndg|{HEX}")[2]
    assert "⏰" in tap_wire.classify(f"cv2|ndl|{HEX}")[2]
    assert "✗" in tap_wire.classify(f"cv2|ndd|{HEX}")[2]


def test_done_tap_composes_canonical_grant_line():
    calls, marks = [], []
    res = tap_wire.apply_tap(f"cv2|ndg|{HEX}", message_id=88, now=NOW,
                             wire=_need_wire_ok(calls),
                             edit_markup=lambda mid, kb: marks.append((mid, kb)))
    assert calls == [(f"grant NEED-{HEX}", "")]      # the typed verb, exactly
    assert res["handled"] is True and res["relay"] is False
    assert res["mode"] == "need:ndg"
    assert res["item_id"] == f"NEED-{HEX}"
    assert res["outcome"] == "approved_pending_apply"
    # the tapped card's keyboard swapped for ONE inert receipt row
    assert marks == [(88, [[{"text": "✓ Done",
                             "callback_data": f"cv2|ndg|{HEX}"}]])]
    assert res["marked"] is True


def test_later_tap_composes_canonical_later_line():
    calls = []
    res = tap_wire.apply_tap(f"cv2|ndl|{HEX}", message_id=89, now=NOW,
                             wire=_need_wire_ok(calls, need="snoozed"))
    assert calls == [(f"later NEED-{HEX}", "")]
    assert res["outcome"] == "snoozed"
    assert res["handled"] is True and res["relay"] is False


def test_drop_tap_composes_canonical_deny_line_with_provenance():
    calls = []
    res = tap_wire.apply_tap(f"cv2|ndd|{HEX}", message_id=90, now=NOW,
                             wire=_need_wire_ok(calls, need="denied"))
    assert len(calls) == 1
    text, quoted = calls[0]
    assert text.startswith(f"deny NEED-{HEX}:")
    assert "card tap" in text                        # honest provenance
    assert quoted == ""
    assert res["outcome"] == "denied"


def test_need_tap_malformed_args_fail_closed_wire_never_fires():
    """The 8-hex fullmatch is the injection gate: anything else NEVER reaches
    the binder text composer — a hostile callback payload cannot splice
    grammar (deny NEED-x: <smuggled>) or bind a wider id."""
    calls = []
    wire = _need_wire_ok(calls)
    for bad in ("A1B2C3D4",            # uppercase — not ledger form
                "a1b2c3d4e5f6",        # 12 hex — wrong width
                "a1b2c3",              # short
                "..bbccdd",            # path chars
                "aabbccd:",            # grammar splice attempt
                ""):                   # empty
        res = tap_wire.apply_tap(f"cv2|ndg|{bad}", message_id=1, now=NOW,
                                 wire=wire)
        assert res["handled"] is False and res["relay"] is True, bad
    assert calls == []                               # gate held every time


def test_need_tap_door_refusal_relays_to_chair():
    """Stale/unknown id or a dark needs plane: the door refuses (its own
    fail-closed law) and the tap relays to the Chair instead of pretending."""
    res = tap_wire.apply_tap(
        f"cv2|ndg|{HEX}", message_id=2, now=NOW,
        wire=lambda t, q: {"handled": False,
                           "reason": f"unknown-need-id (NEED-{HEX})"})
    assert res["handled"] is False and res["relay"] is True
    assert "unknown-need-id" in res["summary"]


def test_need_tap_markup_failure_never_unhandles():
    def _boom(_mid, _kb):
        raise RuntimeError("edit failed")
    res = tap_wire.apply_tap(f"cv2|ndl|{HEX}", message_id=3, now=NOW,
                             wire=_need_wire_ok([], need="snoozed"),
                             edit_markup=_boom)
    assert res["handled"] is True and res["marked"] is False


def test_need_tap_wire_exception_fails_open_to_relay():
    def _explode(_t, _q):
        raise RuntimeError("binder down")
    res = tap_wire.apply_tap(f"cv2|ndg|{HEX}", message_id=4, now=NOW,
                             wire=_explode)
    assert res["handled"] is False and res["relay"] is True
    assert res["mode"].startswith("error:")


def test_apply_tap_never_raises(monkeypatch, adapter):
    """A broken sibling import must degrade to relay, never to an exception
    reaching the poller's receive loop."""
    import framework.comms.surface.engine as eng
    monkeypatch.setattr(eng, "on_callback",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    res = tap_wire.apply_tap("cv2|tri|brief", message_id=1, now=NOW,
                             census=_census(), adapter=adapter)
    assert res["handled"] is False and res["relay"] is True
    assert res["mode"].startswith("error:")
