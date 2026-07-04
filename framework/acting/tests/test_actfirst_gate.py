"""TI-3 act-first gate — the eligibility chain rule + fail-closed runtime gates.

Fully fixtured: no Telegram, no live Redis/Monday, no LLM. Tests the pure gate
helpers directly (the main() I/O loop is exercised elsewhere); the flag defaults
OFF so the whole branch is dark until a Captain flip.
"""
from __future__ import annotations

from framework.acting import run_action_lane as r
from framework.acting.action_lane import ActionProposal, ActionStep
from framework.frontdoor import actfirst_canary, veto_registry, action_undo


def _card(kinds=("monday_task_create",), *, suspect=False, board="5091706356"):
    steps = tuple(
        ActionStep(kind=k, title=f"do {k}",
                   payload=({"board_id": board, "title": "t"} if k.startswith("monday") else {}))
        for k in kinds)
    return ActionProposal(subject="s", situation="why", steps=steps, lane="polads",
                          evidence=("6-Commitments/x.md",), confidence=0.9,
                          urgency="batch", injection_suspect=suspect)


# --- flag -------------------------------------------------------------------

def test_flag_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("CABINET_ACT_FIRST", raising=False)
    monkeypatch.setattr(r, "ACT_FIRST_FLAG_FILE", tmp_path / "nope-not-here")
    assert r._act_first_on() is False


def test_flag_on_via_env(monkeypatch):
    monkeypatch.setenv("CABINET_ACT_FIRST", "1")
    assert r._act_first_on() is True


def test_flag_on_via_file(monkeypatch, tmp_path):
    monkeypatch.delenv("CABINET_ACT_FIRST", raising=False)
    f = tmp_path / "act-first-enabled"; f.write_text("")
    monkeypatch.setattr(r, "ACT_FIRST_FLAG_FILE", f)
    assert r._act_first_on() is True


# --- backend mapping --------------------------------------------------------

def test_backend_for_step(monkeypatch):
    monkeypatch.delenv("ACTION_LANE_REMINDER_BACKEND", raising=False)
    assert r._backend_for_step(ActionStep("monday_task_create", "t")) == "monday"
    assert r._backend_for_step(ActionStep("monday_task_update", "t")) == "monday"
    assert r._backend_for_step(ActionStep("reminder_create", "t")) == "calendar"
    assert r._backend_for_step(ActionStep("delegate_work", "t")) == "delegate_work"


# --- eligibility chain rule -------------------------------------------------

def test_eligible_single_create_when_stamped():
    ok, why = r._card_act_first_eligible(_card(("monday_task_create",)), "task_create")
    # eligibility depends on action_undo.act_first_eligible(create, monday) having
    # a registered inverse (it does — archive_item); so ok iff task_create maps.
    assert action_undo.act_first_eligible("monday_task_create", "monday") is True
    assert ok is True and why == ""


def test_injection_suspect_never_eligible():
    ok, why = r._card_act_first_eligible(_card(suspect=True), "task_create")
    assert ok is False and why == "injection_suspect"


def test_unstamped_never_eligible():
    ok, why = r._card_act_first_eligible(_card(), None)
    assert ok is False and "unstamped" in why


def test_too_many_steps_never_eligible():
    card = _card(("monday_task_create", "monday_task_update", "reminder_create"))
    ok, why = r._card_act_first_eligible(card, "task_create")
    assert ok is False and "steps" in why


def test_ineligible_step_blocks_whole_chain():
    # delegate_work has op "none" (no inverse) → the whole card is propose-only
    card = _card(("monday_task_create", "delegate_work"))
    ok, why = r._card_act_first_eligible(card, "task_create")
    assert ok is False and "delegate_work" in why


# --- fail-closed runtime gates ----------------------------------------------

def test_gate_blocks_on_veto(monkeypatch):
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: True)
    ok, why = r._act_first_gates_ok("task_create", "5091706356", "task_create")
    assert ok is False and "veto" in why


def test_gate_blocks_on_frozen(monkeypatch):
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: True)
    ok, why = r._act_first_gates_ok("task_create", "5091706356", "task_create")
    assert ok is False and "frozen" in why


def test_gate_blocks_on_silenced(monkeypatch):
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_silenced", lambda *a, **k: True)
    ok, why = r._act_first_gates_ok("task_create", None, "task_create")
    assert ok is False and "silenced" in why


def test_gate_blocks_on_cap(monkeypatch):
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_silenced", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "cap_check", lambda *a, **k: {"ok": False})
    ok, why = r._act_first_gates_ok("task_create", None, "task_create")
    assert ok is False and "cap" in why


def test_gate_veto_error_fails_closed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("registry unreadable")
    monkeypatch.setattr(veto_registry, "is_vetoed", boom)
    ok, why = r._act_first_gates_ok("task_create", None, "task_create")
    assert ok is False and "fail-closed" in why


def test_gate_all_pass(monkeypatch):
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_silenced", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "cap_check", lambda *a, **k: {"ok": True})
    ok, why = r._act_first_gates_ok("task_create", "5091706356", "task_create")
    assert ok is True and why == ""


# --- board extraction -------------------------------------------------------

def test_card_board_from_first_monday_step():
    assert r._card_board(_card(("monday_task_create",), board="9999")) == "9999"
    assert r._card_board(_card(("reminder_create",))) is None


# ============================================================================
# main() integration — act-vs-propose branching. Only I/O seams are stubbed
# (Telegram, ledger, executor, gather, veto/canary); the real eligibility +
# stamping + gate logic runs. The write-ahead-journal-before-mutation ordering
# is pinned in test_action_exec.py::test_write_ahead_journal_exists_before_mutation
# (deliver_action's own contract) — not duplicated here.
# ============================================================================

def _update_card(board="5091706356"):
    """The genuine end-to-end act-first path: update → stamped 'board_status'."""
    step = ActionStep(kind="monday_task_update", title="move to Done",
                      payload={"board_id": board, "item_id": "42", "status": "Done"})
    return ActionProposal(subject="close cmt", situation="done", steps=(step,),
                          lane="polads", evidence=("6-Commitments/x.md",),
                          confidence=0.95, urgency="batch")


def _drive_main(monkeypatch, *, proposals, deliver_result, act_first=True,
                emit_raises=False):
    """Patch main()'s I/O seams; return captured (emits, delivers, tgs, rc)."""
    emits, delivers, tgs, receipts = [], [], [], []

    monkeypatch.setattr(r.sys, "argv", ["run_action_lane"])
    monkeypatch.setattr(r, "_acquire_lock", lambda: True)
    monkeypatch.setattr(r, "_load_env", lambda: None)
    monkeypatch.setattr(r, "gather_signals", lambda *a, **k: "a fresh signal line")
    monkeypatch.setattr(r.sa, "decided_subjects", lambda: {})
    monkeypatch.setattr(r, "pending_proposals", lambda: [])
    monkeypatch.setattr(r, "covered_evidence_refs", lambda: frozenset())
    monkeypatch.setattr(r, "load_directions", lambda: None)
    monkeypatch.setattr(r.action_lane, "propose_actions",
                        lambda *a, **k: list(proposals))
    monkeypatch.setattr(r, "_prior_acted_types", lambda: frozenset())
    monkeypatch.setattr(r, "_store_action", lambda *a, **k: None)
    monkeypatch.setattr(r, "_tg", lambda text: tgs.append(text))
    monkeypatch.setattr(r, "_emit_receipt", lambda *a, **k: receipts.append(a))

    # flag
    monkeypatch.setattr(r, "_act_first_on", lambda: act_first)
    # veto/canary — all clear so the real gate helper passes
    monkeypatch.setattr(r.veto_registry, "rebuild_cache", lambda *a, **k: None)
    monkeypatch.setattr(r.veto_registry, "veto_cache_ready", lambda *a, **k: True)
    monkeypatch.setattr(r.veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(r.actfirst_canary, "own_acted_cids", lambda *a, **k: frozenset())
    monkeypatch.setattr(r.actfirst_canary, "is_frozen", lambda *a, **k: False)
    monkeypatch.setattr(r.actfirst_canary, "is_silenced", lambda *a, **k: False)
    monkeypatch.setattr(r.actfirst_canary, "cap_check", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(r.actfirst_canary, "incr_and_check", lambda *a, **k: None)

    def fake_emit(**ev):
        emits.append(ev)
        if emit_raises:
            raise RuntimeError("ledger write failed")
    monkeypatch.setattr(r, "emit_consequence", fake_emit)

    def fake_deliver(pid, **kw):
        delivers.append({"pid": pid, **kw})
        return dict(deliver_result)
    monkeypatch.setattr(r, "deliver_action", fake_deliver)

    rc = r.main()
    return {"emits": emits, "delivers": delivers, "tgs": tgs,
            "receipts": receipts, "rc": rc}


def test_act_path_journals_and_marks_ledger_acted(monkeypatch):
    out = _drive_main(monkeypatch, proposals=[_update_card()],
                      deliver_result={"ok": True})
    # executor invoked in act-first mode
    assert len(out["delivers"]) == 1
    assert out["delivers"][0]["act_first"] is True
    # NO card was presented to the Captain (acted, not proposed)
    assert out["tgs"] == []
    # the acted ledger row is shaped act-not-propose
    assert len(out["emits"]) == 1
    ev = out["emits"][0]
    assert ev["proposal"] == {"required": False, "decision": None}
    assert ev["outcome"] == {"status": "unknown"}
    assert ev.get("action_type") == "board_status"
    assert len(out["receipts"]) == 1


def test_downgrade_falls_through_to_propose(monkeypatch):
    # executor's perimeter declines (e.g. board not allow-listed) → propose
    out = _drive_main(monkeypatch, proposals=[_update_card()],
                      deliver_result={"ok": False, "gate": "board_not_allowed"})
    assert len(out["delivers"]) == 1           # we tried to act
    assert out["tgs"] and "close cmt" not in out["tgs"][0][:0]  # a card was presented
    assert len(out["tgs"]) == 1
    # the ledger row is the plain proposal event — NOT act-shaped
    assert len(out["emits"]) == 1
    ev = out["emits"][0]
    assert "outcome" not in ev
    assert ev.get("proposal") in (None, {}) or ev.get("proposal", {}).get("required") is not False
    assert out["receipts"] == []


def test_ineligible_create_proposes_even_with_flag_on(monkeypatch):
    # a create is unstamped (task_create ∉ classifier enum) → never acts
    step = ActionStep(kind="monday_task_create", title="new",
                      payload={"board_id": "5091706356", "title": "t"})
    card = ActionProposal(subject="new task", situation="w", steps=(step,),
                          lane="polads", evidence=("x.md",), confidence=0.9,
                          urgency="batch")
    out = _drive_main(monkeypatch, proposals=[card],
                      deliver_result={"ok": True})
    assert out["delivers"] == []               # executor never called
    assert len(out["tgs"]) == 1                # proposed instead
    assert len(out["emits"]) == 1 and "outcome" not in out["emits"][0]


def test_flag_off_never_acts(monkeypatch):
    out = _drive_main(monkeypatch, proposals=[_update_card()],
                      deliver_result={"ok": True}, act_first=False)
    assert out["delivers"] == []               # deliver_action never called
    assert len(out["tgs"]) == 1                # pure propose path
    assert len(out["emits"]) == 1 and "outcome" not in out["emits"][0]
    assert out["receipts"] == []


def test_crash_between_act_and_emit_leaves_act_standing(monkeypatch):
    # emit_consequence raises AFTER the journaled+executed act. The lane must NOT
    # re-present the card (no double-action); the journaled act stands alone and
    # stays undoable (journal is deliver_action's durable record).
    out = _drive_main(monkeypatch, proposals=[_update_card()],
                      deliver_result={"ok": True}, emit_raises=True)
    assert len(out["delivers"]) == 1           # acted
    assert out["tgs"] == []                     # NOT re-proposed despite emit loss
    assert len(out["receipts"]) == 1           # Captain still gets the receipt
