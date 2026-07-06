"""TI-3 act-first gate — the eligibility chain rule + fail-closed runtime gates.

Fully fixtured: no Telegram, no live Redis/Monday, no LLM. Tests the pure gate
helpers directly (the main() I/O loop is exercised elsewhere); the flag defaults
OFF so the whole branch is dark until a Captain flip.
"""
from __future__ import annotations

import datetime as dt
import json

from framework.acting import run_action_lane as r
from framework.acting.action_lane import ActionProposal, ActionStep
from framework.fidelity import graduation
from framework.fidelity.consequence import read_ledger
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
    ok, why = r._act_first_gates_ok("task_create", "5091706356", "task_create", "cos")
    assert ok is False and "veto" in why


def test_gate_blocks_on_frozen(monkeypatch):
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: True)
    ok, why = r._act_first_gates_ok("task_create", "5091706356", "task_create", "cos")
    assert ok is False and "frozen" in why


def test_gate_blocks_on_silenced(monkeypatch):
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_silenced", lambda *a, **k: True)
    ok, why = r._act_first_gates_ok("task_create", None, "task_create", "cos")
    assert ok is False and "silenced" in why


def test_gate_blocks_on_cap(monkeypatch):
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_silenced", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "cap_check", lambda *a, **k: {"ok": False})
    ok, why = r._act_first_gates_ok("task_create", None, "task_create", "cos")
    assert ok is False and "cap" in why


def test_gate_veto_error_fails_closed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("registry unreadable")
    monkeypatch.setattr(veto_registry, "is_vetoed", boom)
    ok, why = r._act_first_gates_ok("task_create", None, "task_create", "cos")
    assert ok is False and "fail-closed" in why


def test_gate_all_pass(monkeypatch):
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_silenced", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "cap_check", lambda *a, **k: {"ok": True})
    ok, why = r._act_first_gates_ok("task_create", "5091706356", "task_create", "cos")
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
    """Patch main()'s I/O seams; return captured (emits, delivers, tgs, stores,
    rc). ``stores`` records every _store_action(pid, proposal, cid) call — the
    lane-normalization tests read the stored proposal's lane (the record the
    executor journals + emits acted rows from)."""
    emits, delivers, tgs, receipts, stores = [], [], [], [], []

    monkeypatch.setattr(r.sys, "argv", ["run_action_lane"])
    monkeypatch.setattr(r, "_acquire_lock", lambda: True)
    monkeypatch.setattr(r, "_load_env", lambda: None)
    monkeypatch.setattr(r, "gather_signals", lambda *a, **k: "a fresh signal line")
    monkeypatch.setattr(r.ld, "decided_subjects", lambda: {})
    monkeypatch.setattr(r, "pending_proposals", lambda: [])
    monkeypatch.setattr(r, "covered_evidence_refs", lambda: frozenset())
    monkeypatch.setattr(r, "load_directions", lambda: None)
    monkeypatch.setattr(r.action_lane, "propose_actions",
                        lambda *a, **k: list(proposals))
    monkeypatch.setattr(r, "_prior_acted_types", lambda: frozenset())
    monkeypatch.setattr(r, "_store_action",
                        lambda pid, p, cid="": stores.append((pid, p, cid)))
    monkeypatch.setattr(r, "_tg", lambda text: tgs.append(text))
    monkeypatch.setattr(r, "_emit_receipt", lambda *a, **k: receipts.append(a))
    # ask-budget seam (germline 2026-07-04): hermetic per-run counter. Without
    # this stub, _ask_budget_ok's `_redis("INCR", ...)` reaches the REAL local
    # Redis and increments the LIVE day-budget key from a unit test — both
    # polluting the running org's ≤5/day ask contract and (once the live count
    # passes 5) withholding every presented card in these fixtures. Fresh
    # counter per _drive_main call, so every test starts inside budget.
    _ask_counter = {"n": 0}

    def _fake_redis(*a):
        if a and a[0] == "INCR":
            _ask_counter["n"] += 1
            return str(_ask_counter["n"])
        return ""
    monkeypatch.setattr(r, "_redis", _fake_redis)

    # flag
    monkeypatch.setattr(r, "_act_first_on", lambda: act_first)
    # confidence floor — pinned to the shipped default so main() never reads the
    # real instance yml from a unit test (hermetic fixtures)
    monkeypatch.setattr(r, "_confidence_floor", lambda: r.CONFIDENCE_FLOOR_DEFAULT)
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
            "receipts": receipts, "stores": stores, "rc": rc}


def test_act_path_emits_nothing_lane_side_executor_owns_acted_row(monkeypatch):
    # ACTED-EVENT IDENTITY FIX (germline batch 2026-07-05): the lane's old
    # card-level acted emit (dict(prop_ev) under 'action-card') is GONE — it
    # never matched the identity binder/reconcile recompute, leaving a permanent
    # outcome:unknown orphan + a double-mint per verdict. The executor now owns
    # the per-step acted row (emitted INSIDE deliver_action off the enriched
    # journal row — pinned in test_action_exec.py::
    # test_act_first_emits_acted_row_on_canonical_identity). Lane-side the act
    # path keeps ONLY the caps counter + receipt: zero ledger emits here.
    out = _drive_main(monkeypatch, proposals=[_update_card()],
                      deliver_result={"ok": True})
    # executor invoked in act-first mode
    assert len(out["delivers"]) == 1
    assert out["delivers"][0]["act_first"] is True
    # NO card was presented to the Captain (acted, not proposed)
    assert out["tgs"] == []
    # and NO lane-side ledger row — the acted row is the executor's
    assert out["emits"] == []
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


def test_create_card_acts_post_germline(monkeypatch):
    # [GERM-2] a pure create stamps task_create (pm_write / act_with_undo) and
    # ACTS through the journaled lane — the second genuine end-to-end act path.
    # (2026-07-05 acted-identity fix: the acted ledger row is the EXECUTOR's now
    # — lane-side the act path emits nothing; see the emits==[] pin above.)
    step = ActionStep(kind="monday_task_create", title="new",
                      payload={"board_id": "5091706356", "title": "t"})
    card = ActionProposal(subject="new task", situation="w", steps=(step,),
                          lane="polads", evidence=("x.md",), confidence=0.9,
                          urgency="batch")
    out = _drive_main(monkeypatch, proposals=[card],
                      deliver_result={"ok": True})
    assert len(out["delivers"]) == 1 and out["delivers"][0]["act_first"] is True
    assert out["tgs"] == []                    # acted, not proposed
    assert out["emits"] == []                  # executor owns the acted row
    # the record the executor acts from was stored before delivery
    assert [s[1].subject for s in out["stores"]] == ["new task"]


def test_ineligible_dispatch_proposes_even_with_flag_on(monkeypatch):
    # delegate_work stamps officer_dispatch (internal_comms) but has NO
    # registered inverse → never act-first; falls through to propose.
    step = ActionStep(kind="delegate_work", title="dispatch",
                      payload={"officer": "cto", "brief": "b"})
    card = ActionProposal(subject="dispatch work", situation="w", steps=(step,),
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
    # A raising lane-side emit seam cannot disturb an acted card: the lane must
    # NOT re-present it (no double-action) and the Captain still gets the
    # receipt. (Since the 2026-07-05 acted-identity fix the act path emits
    # nothing lane-side at all — the executor owns the acted row, best-effort,
    # pinned in test_action_exec.py::test_acted_emit_failure_is_best_effort_*;
    # this stays as the lane-level no-re-propose pin with the emit seam armed.)
    out = _drive_main(monkeypatch, proposals=[_update_card()],
                      deliver_result={"ok": True}, emit_raises=True)
    assert len(out["delivers"]) == 1           # acted
    assert out["tgs"] == []                     # NOT re-proposed despite emit loss
    assert len(out["receipts"]) == 1           # Captain still gets the receipt


# ============================================================================
# L2-gate (flip-conditions burn-down, checkpoint 2026-07-04): confidence floor
# enforcement + steps_sha256 TOCTOU stamp + flag-off byte-identity pins.
# ============================================================================

def _conf_card(conf):
    """A single stampable create with an arbitrary confidence value."""
    step = ActionStep(kind="monday_task_create", title="new",
                      payload={"board_id": "5091706356", "title": "t"})
    return ActionProposal(subject="s", situation="w", steps=(step,),
                          lane="polads", evidence=("x.md",), confidence=conf,
                          urgency="batch")


# --- confidence floor (the ex-phantom knob) ----------------------------------

def test_confidence_below_floor_blocks():
    ok, why = r._card_act_first_eligible(_conf_card(0.5), "task_create")
    assert ok is False and why == "confidence below floor"


def test_confidence_above_floor_passes():
    ok, why = r._card_act_first_eligible(_conf_card(0.9), "task_create")
    assert ok is True and why == ""


def test_confidence_exactly_at_floor_passes():
    ok, _ = r._card_act_first_eligible(_conf_card(r.CONFIDENCE_FLOOR_DEFAULT),
                                       "task_create")
    assert ok is True


def test_explicit_floor_param_is_honored():
    ok, why = r._card_act_first_eligible(_conf_card(0.9), "task_create", floor=0.95)
    assert ok is False and why == "confidence below floor"


def test_unparseable_confidence_never_clears_floor():
    # fail-safe: a confidence we cannot verify is treated as 0.0, never waved on
    ok, why = r._card_act_first_eligible(_conf_card("very sure"), "task_create")
    assert ok is False and why == "confidence below floor"


def test_nan_confidence_never_clears_floor():
    ok, why = r._card_act_first_eligible(_conf_card(float("nan")), "task_create")
    assert ok is False and why == "confidence below floor"


def _floor_yml(tmp_path, body):
    p = tmp_path / "act-first-surfaces.yml"
    p.write_text(body)
    return p


def test_floor_reader_reads_declared_value(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "_surfaces_path",
                        lambda: _floor_yml(tmp_path, "confidence_floor: 0.8\n"))
    assert r._confidence_floor() == 0.8


def test_floor_reader_absent_file_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "_surfaces_path", lambda: tmp_path / "missing.yml")
    assert r._confidence_floor() == r.CONFIDENCE_FLOOR_DEFAULT


def test_floor_reader_corrupt_yaml_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "_surfaces_path", lambda: _floor_yml(tmp_path, "{"))
    assert r._confidence_floor() == r.CONFIDENCE_FLOOR_DEFAULT


def test_floor_reader_invalid_values_default_never_zero(monkeypatch, tmp_path):
    # a broken knob must TIGHTEN the gate (0.65), never widen it (0 would let
    # every card through the confidence check)
    for body in ("confidence_floor: 0\n",       # zero is not a floor
                 "confidence_floor: -0.3\n",    # negative
                 "confidence_floor: 1.5\n",     # out of range
                 "confidence_floor: high\n",    # non-numeric
                 "confidence_floor: .nan\n",    # NaN
                 "version: 1\n"):               # key missing entirely
        monkeypatch.setattr(r, "_surfaces_path",
                            lambda b=body: _floor_yml(tmp_path, b))
        assert r._confidence_floor() == r.CONFIDENCE_FLOOR_DEFAULT, body


def test_floor_reader_consumes_shipped_instance_yml():
    # the real Captain-owned file, no monkeypatch: whatever the yml declares is
    # what the gate enforces — the knob is READ, no longer phantom (checkpoint
    # flip condition). Stays green if the Captain retunes (or deletes) the value.
    import yaml
    data = yaml.safe_load(r._surfaces_path().read_text()) or {}
    declared = data.get("confidence_floor")
    if declared:
        assert r._confidence_floor() == float(declared)
    else:
        assert r._confidence_floor() == r.CONFIDENCE_FLOOR_DEFAULT


def test_low_confidence_card_proposes_instead_of_acting(monkeypatch):
    # main() wiring: a 0.5-confidence create clears every mechanical gate EXCEPT
    # the floor → falls through to propose (card presented, executor untouched)
    out = _drive_main(monkeypatch, proposals=[_conf_card(0.5)],
                      deliver_result={"ok": True})
    assert out["delivers"] == []               # never reached the executor
    assert len(out["tgs"]) == 1                # proposed to the Captain instead
    assert "outcome" not in out["emits"][0]    # propose-shaped ledger row


# --- steps_sha256 TOCTOU stamp at store ---------------------------------------

def _capture_store(monkeypatch):
    stored = {}
    monkeypatch.setattr(r, "_redis", lambda *a: stored.update(args=a) or "")
    return stored


def _exec_valid_update_card():
    """An update card whose payload matches the executor's CLOSED schema
    (_PAYLOAD_KEYS/_SET_KEYS) — required for the end-to-end store→deliver
    round-trips below, which run the real deliver_action."""
    step = ActionStep(kind="monday_task_update", title="move to Done",
                      payload={"board_id": "5091706356", "monday_id": "42",
                               "set": {"status": "Done"}})
    return ActionProposal(subject="close cmt", situation="done", steps=(step,),
                          lane="polads", evidence=("6-Commitments/x.md",),
                          confidence=0.95, urgency="batch")


def test_store_action_stamps_steps_sha256(monkeypatch):
    from framework.frontdoor.action_exec import _canonical_sha
    stored = _capture_store(monkeypatch)
    r._store_action("pid-1", _update_card(), cid="cid-1")
    assert stored["args"][:2] == ("SET", "cabinet:action:pid-1")
    rec = json.loads(stored["args"][2])
    # shape agreement end-to-end: the executor's TOCTOU re-check recomputes
    # _canonical_sha over rec["steps"] AS READ BACK from the record — the
    # store-time stamp must equal that round-tripped hash exactly.
    assert rec["steps_sha256"] == _canonical_sha(rec["steps"])
    assert rec["steps"][0]["kind"] == "monday_task_update"


def test_executor_toctou_refuses_swapped_record(monkeypatch):
    # end-to-end against the REAL executor: a record stamped by _store_action
    # then swapped in Redis is refused before anything runs (dry_run keeps the
    # probe pure; the TOCTOU check fires ahead of it either way).
    from framework.frontdoor import action_exec
    monkeypatch.setattr(action_exec, "_load_shared_env", lambda: None)  # hermetic
    stored = _capture_store(monkeypatch)
    r._store_action("pid-2", _exec_valid_update_card(), cid="c")
    rec = json.loads(stored["args"][2])
    rec["steps"][0]["payload"]["monday_id"] = "666"        # the swap
    out = action_exec.deliver_action("pid-2", redis_get=lambda k: json.dumps(rec),
                                     dry_run=True)
    assert out["ok"] is False and out.get("toctou") is True
    assert out["executed"] == []


def test_executor_accepts_unswapped_stored_record(monkeypatch):
    # the positive half: the untouched stored record passes the executor's
    # TOCTOU re-check (no false refusals from the store-time stamp)
    from framework.frontdoor import action_exec
    monkeypatch.setattr(action_exec, "_load_shared_env", lambda: None)  # hermetic
    stored = _capture_store(monkeypatch)
    r._store_action("pid-3", _exec_valid_update_card(), cid="c")
    blob = stored["args"][2]
    out = action_exec.deliver_action("pid-3", redis_get=lambda k: blob,
                                     dry_run=True)
    assert out.get("toctou") is not True
    assert out["ok"] is True


# --- flag-off byte-identity (refuter KILLED #1 pinned closed) -----------------

def test_flag_off_row_carries_no_action_type(monkeypatch):
    # KILLED #1(b): with the flag off, the ledger row must be the pre-TI-3
    # propose-only bytes — NO action_type, no dark graduation-cell accumulation
    out = _drive_main(monkeypatch, proposals=[_update_card()],
                      deliver_result={"ok": True}, act_first=False)
    assert len(out["emits"]) == 1
    assert "action_type" not in out["emits"][0]
    assert "outcome" not in out["emits"][0]


def test_flag_on_propose_fallthrough_keeps_stamp(monkeypatch):
    # the counterpart: once armed, a downgraded card's propose row DOES stamp —
    # graduation earns from live verdicts only while the posture is on
    out = _drive_main(monkeypatch, proposals=[_update_card()],
                      deliver_result={"ok": False, "gate": "board_not_allowed"})
    assert len(out["emits"]) == 1
    assert out["emits"][0].get("action_type") == "board_status"


def test_flag_off_prints_pre_ti3_baseline_summary(monkeypatch, capsys):
    # KILLED #1(a): the flag-off run summary is the exact pre-TI-3 line, and the
    # TI-3 "acted" format never leaks into a dark run's output
    _drive_main(monkeypatch, proposals=[_update_card()],
                deliver_result={"ok": True}, act_first=False)
    stdout = capsys.readouterr().out
    assert "done: presented 1 action card(s)" in stdout
    assert "acted" not in stdout


def test_flag_on_prints_acted_summary(monkeypatch, capsys):
    _drive_main(monkeypatch, proposals=[_update_card()],
                deliver_result={"ok": True})
    stdout = capsys.readouterr().out
    assert "done: presented 0 card(s), acted 1 card(s)" in stdout


# ============================================================================
# MF-2 regression batch (checkpoint review lane-germline-0705-cp1, 2026-07-05):
# the germline batch's PRIMARY safety brake (_graduation_demoted — evidence-
# driven demotion), the ask-budget throttle, and the card-expiry sweep shipped
# with zero coverage. Pin them so they cannot silently break — a computed-but-
# never-enforced brake is exactly how the "officer:officer:cos" actor-key
# severing bug shipped.
# ============================================================================

# --- _graduation_demoted (DEMOTE-WIRE, germline 2026-07-04) -------------------

def test_demote_state_blocks_and_cell_key_is_single_prefixed(monkeypatch):
    # The demote brake blocks — AND the cell it reads composes the CANONICAL
    # "officer:cos" (bare-role _ACTOR, ONE prefix). The old inline actor
    # literal flattened to "officer:officer:cos", making every demotion row
    # invisible to this exact query; pin the join key so the gate and the
    # emitters can never drift on identity again.
    seen = {}

    def fake_eval(cell, **kw):
        seen["cell"] = cell
        return {"state": "demote"}

    monkeypatch.setattr(graduation, "evaluate", fake_eval)
    demoted, why = r._graduation_demoted("task_create", "polads")
    assert demoted is True and "demot" in why
    assert seen["cell"] == ("officer:cos", "polads", "task_create")


def test_non_demote_states_never_block(monkeypatch):
    # Trust-inversion posture: unmeasured / eligible / graduated / propose_only
    # — and a missing cell (None) — all pass. ONLY state=='demote' brakes
    # (trust is lost on evidence, never pre-earned).
    for state in ({"state": "unmeasured"}, {"state": "eligible"},
                  {"state": "graduated"}, {"state": "propose_only"}, None):
        monkeypatch.setattr(graduation, "evaluate",
                            lambda cell, _s=state, **kw: _s)
        assert r._graduation_demoted("task_create", "polads") == (False, ""), state


def test_lane_none_fails_closed_without_reading_graduation(monkeypatch):
    # N3 fix (checkpoint review 2026-07-05): a None lane cannot key the real
    # per-lane cell — reading the None-lane cell would MISS a demotion living
    # on the actual lane (fail-open). Must fail closed BEFORE consulting the
    # graduation plane at all; the raising stub distinguishes (a consult would
    # surface the "unreadable" reason instead).
    def boom(cell, **kw):
        raise AssertionError("graduation must not be consulted for lane=None")

    monkeypatch.setattr(graduation, "evaluate", boom)
    demoted, why = r._graduation_demoted("task_create", None)
    assert demoted is True and "lane unspecified" in why


def test_graduation_error_fails_closed(monkeypatch):
    # An unverifiable brake must never widen action: an unreadable ledger /
    # matrix (evaluate raising) blocks instead of waving the card through.
    def boom(cell, **kw):
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(graduation, "evaluate", boom)
    demoted, why = r._graduation_demoted("task_create", "polads")
    assert demoted is True and "unreadable" in why


# --- _act_first_gates_ok: the demote branch -----------------------------------

def _canary_all_clear(monkeypatch):
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_silenced", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "cap_check", lambda *a, **k: {"ok": True})


def test_gate_blocks_on_demoted_cell(monkeypatch):
    # Veto passes but the demote brake blocks — proving the gate actually
    # CONSULTS graduation state (before this batch, demotion was computed by
    # the engine but never read anywhere in the acting path).
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    _canary_all_clear(monkeypatch)
    monkeypatch.setattr(graduation, "evaluate",
                        lambda cell, **kw: {"state": "demote"})
    ok, why = r._act_first_gates_ok("task_create", "5091706356", "task_create",
                                    lane="polads")
    assert ok is False and "demot" in why


def test_gate_demote_checked_before_mechanical_breakers(monkeypatch):
    # Ordering pin (the gate's documented contract): demotion is checked right
    # after the Captain's word (veto) and BEFORE freeze/silence/caps — with the
    # kind frozen AND the cell demoted, the reason must be the demote one.
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(actfirst_canary, "is_frozen", lambda *a, **k: True)
    monkeypatch.setattr(graduation, "evaluate",
                        lambda cell, **kw: {"state": "demote"})
    ok, why = r._act_first_gates_ok("task_create", None, "task_create",
                                    lane="polads")
    assert ok is False and "demot" in why and "frozen" not in why


def test_gate_lane_none_fails_closed(monkeypatch):
    # lane is REQUIRED at the gate (N3): veto clear but no lane must block via
    # _graduation_demoted's fail-closed leg, never read a wrong (None) cell.
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    _canary_all_clear(monkeypatch)
    ok, why = r._act_first_gates_ok("task_create", None, "task_create",
                                    lane=None)
    assert ok is False and "lane unspecified" in why


def test_gate_passes_on_unmeasured_cell(monkeypatch):
    # The complement: a fresh (unmeasured) cell does NOT brake — only demote
    # does. Every other gate clear ⇒ (True, "").
    monkeypatch.setattr(veto_registry, "is_vetoed", lambda *a, **k: False)
    _canary_all_clear(monkeypatch)
    monkeypatch.setattr(graduation, "evaluate",
                        lambda cell, **kw: {"state": "unmeasured"})
    ok, why = r._act_first_gates_ok("task_create", "5091706356", "task_create",
                                    lane="polads")
    assert ok is True and why == ""


# --- _ask_budget_ok (FIELD-TEST caps, 2026-07-05 override) --------------------

def test_field_test_caps_read_from_module():
    # FIELD-TEST OVERRIDE (feedback_field_test_disturb_max, 2026-07-05): the
    # caps are lifted to non-binding — per-run equals the generation bound (so
    # generation is the only bound) and the day budget sits far above it. Pin
    # the RELATION, not the numbers: the numbers are a phase choice and will
    # re-tighten once acceptance/undo rates are known.
    assert r.MAX_PRESENT_PER_RUN == r.MAX_PER_RUN
    assert r.DAY_ASK_BUDGET > r.MAX_PRESENT_PER_RUN


def test_ask_budget_ok_under_caps(monkeypatch):
    calls = []

    def fake_redis(*a):
        calls.append(a)
        return "1" if a and a[0] == "INCR" else ""

    monkeypatch.setattr(r, "_redis", fake_redis)
    for presented in (0, r.MAX_PRESENT_PER_RUN - 1):
        assert r._ask_budget_ok(presented) == (True, "")
    # the counter still runs (ask-volume/day is the field-test telemetry)
    assert any(a[0] == "INCR" and a[1].startswith("cabinet:action:asks:")
               for a in calls)


def test_ask_budget_per_run_cap_blocks_before_redis(monkeypatch):
    # Leg-order pin: the per-run leg is checked FIRST, so a run-capped card
    # never burns day budget (no INCR fires).
    calls = []
    monkeypatch.setattr(r, "_redis", lambda *a: calls.append(a) or "")
    ok, why = r._ask_budget_ok(r.MAX_PRESENT_PER_RUN)
    assert ok is False and "per-run" in why
    assert calls == []


def test_ask_budget_day_budget_exhausted(monkeypatch):
    # INCR-then-compare: a counter past DAY_ASK_BUDGET withholds — the
    # berserk-loop backstop (a wedged LLM still can't fire thousands).
    monkeypatch.setattr(
        r, "_redis",
        lambda *a: str(r.DAY_ASK_BUDGET + 1) if a[0] == "INCR" else "")
    ok, why = r._ask_budget_ok(0)
    assert ok is False and "day ask budget" in why


def test_ask_budget_redis_error_fails_closed(monkeypatch):
    # FAIL-CLOSED: an unreachable counter withholds. Safe because a withheld
    # card writes NOTHING (no ledger row / Redis record / Telegram) and
    # re-proposes naturally while its evidence window stays fresh.
    def boom(*a):
        raise RuntimeError("redis down")

    monkeypatch.setattr(r, "_redis", boom)
    ok, why = r._ask_budget_ok(0)
    assert ok is False and "fail-closed" in why


# --- _expire_stale_cards (CARD-EXPIRY, germline 2026-07-04) -------------------
# Real ledger + real loop.expire_event/emit/pending_proposals round-trip,
# fenced to a tmp dir via CABINET_EVENT_LOG_DIR — the same discipline as
# test_auto_expire.py uses for the draft lane's sweep. Only Redis is faked.

def _fence_ledger(monkeypatch, tmp_path):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(r, "CARD_MAX_AGE_H", 36.0)   # pin against env override


def _seed_card(now, *, subject, hours_old, action="action-card",
               action_type=None, lane="polads"):
    ts = (now - dt.timedelta(hours=hours_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ev = r.proposal_event(actor=r._ACTOR, lane=lane, subject=subject, ts=ts,
                          action=action)
    if action_type:
        ev["action_type"] = action_type          # as main() stamps it flag-on
    r.emit_consequence(**ev)                     # the REAL emitter, fenced dir
    return ev


def test_expire_stale_open_card_is_graduation_neutral(monkeypatch, tmp_path):
    _fence_ledger(monkeypatch, tmp_path)
    dels = []
    monkeypatch.setattr(r, "_redis", lambda *a: dels.append(a) or "")
    now = dt.datetime.now(dt.timezone.utc)
    stale = _seed_card(now, subject="stale ask", hours_old=40,
                       action_type="task_create")

    assert r._expire_stale_cards(now) == 1

    # The superseding closure: decision=expired, verdict=unknown/system.
    # decided_at is the card's OWN ts (the suppression clock — a genuinely-new
    # same-subject situation arriving before the sweep must not be judged
    # already-handled); reviewed_at is the real expiry moment (audit clock).
    rows = [e for e in read_ledger() if e.get("subject") == "stale ask"]
    assert len(rows) == 1                         # last-write-wins superseded
    ev = rows[0]
    assert ev["proposal"]["decision"] == "expired"
    assert ev["proposal"]["decided_at"] == stale["ts"]
    assert ev["review"]["verdict"] == "unknown"
    assert ev["review"]["source"] == "system"
    assert ev["review"]["reviewed_at"] == now.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert r.pending_proposals() == []            # no more ⚡AWAITING line

    # TTL alignment: the executable Redis record dies WITH the card.
    assert ("DEL", f"cabinet:action:{r.proposal_id(stale)}") in dels

    # Graduation-NEUTRAL by construction: the unknown verdict is excluded from
    # every scored denominator, so an expiry can NEVER register as a demotion
    # — the cell stays honestly unmeasured, not demoted.
    res = graduation.evaluate(("officer:cos", "polads", "task_create"))
    assert res["state"] == "unmeasured"


def test_expire_leaves_fresh_and_foreign_rows_alone(monkeypatch, tmp_path):
    _fence_ledger(monkeypatch, tmp_path)
    dels = []
    monkeypatch.setattr(r, "_redis", lambda *a: dels.append(a) or "")
    now = dt.datetime.now(dt.timezone.utc)
    _seed_card(now, subject="fresh ask", hours_old=1, action_type="task_create")
    _seed_card(now, subject="stale draft", hours_old=40, action="draft-reply")

    assert r._expire_stale_cards(now) == 0
    # The fresh card stays open; the stale DRAFT proposal belongs to the draft
    # lane's own sweep (only action=='action-card' rows are touched here).
    assert {p["subject"] for p in r.pending_proposals()} == {"fresh ask",
                                                             "stale draft"}
    assert dels == []


def test_expiry_sweep_disabled_at_nonpositive_age(monkeypatch):
    # CARD_MAX_AGE_H <= 0 disables the sweep BEFORE any ledger read.
    monkeypatch.setattr(r, "CARD_MAX_AGE_H", 0.0)

    def boom():
        raise AssertionError("ledger must not be read when the sweep is off")

    monkeypatch.setattr(r, "pending_proposals", boom)
    assert r._expire_stale_cards(dt.datetime.now(dt.timezone.utc)) == 0


def test_expiry_unreadable_ledger_skips_whole_sweep(monkeypatch):
    # Best-effort contract: an unreadable ledger skips (0 expired), never
    # raises out of the lane run.
    monkeypatch.setattr(r, "CARD_MAX_AGE_H", 36.0)

    def boom():
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(r, "pending_proposals", boom)
    assert r._expire_stale_cards(dt.datetime.now(dt.timezone.utc)) == 0


def test_expiry_unparseable_ts_never_expires(monkeypatch):
    # Conservative: a card whose age cannot be proven is left open — the same
    # stance as the draft lane's backstop.
    monkeypatch.setattr(r, "CARD_MAX_AGE_H", 36.0)
    prop = {"action": "action-card", "ts": "not-a-timestamp", "subject": "s"}
    monkeypatch.setattr(r, "pending_proposals", lambda: [prop])
    emitted = []
    monkeypatch.setattr(r, "emit_consequence", lambda **ev: emitted.append(ev))
    assert r._expire_stale_cards(dt.datetime.now(dt.timezone.utc)) == 0
    assert emitted == []


# ============================================================================
# LANE CELL-KEY NORMALIZATION (germline batch 2026-07-05). The graduation cell
# is (actor, lane, action_type); the lane component was LLM free-text, so ONE
# conceptual lane arrived under many spellings (the live ledger held 5 across
# 26 rows) — fragmenting verdict accumulation so the 2-wrong demotion never
# clustered and the graduation floor was unreachable. _normalize_lane collapses
# to the instance context enum at proposal INGESTION (main) and at the demote
# gate's cell composition (_graduation_demoted); these pin both seams + the
# helper's determinism.
# ============================================================================

# The 5 raw spellings observed on the live ledger (the fix's motivating data).
_LIVE_SPELLINGS = ("Commitments", "Commitments / Delivery",
                   "Commitments / Meetings", "nate", "polads-ceo")


def test_normalize_lane_idempotent():
    # normalize(normalize(x)) == normalize(x) — applying the collapse at BOTH
    # seams (emit + gate) can never disagree.
    for raw in _LIVE_SPELLINGS + ("cabinet", "PolAds delivery", "polads",
                                  "", None, "zzz totally unknown"):
        once = r._normalize_lane(raw)
        assert r._normalize_lane(once) == once, raw


def test_live_ledger_spellings_map_to_stable_slugs():
    slugs = r._context_slugs()
    assert slugs                                    # instance enum readable
    enum = set(slugs) | {r._LANE_NORM_DEFAULT}
    for raw in _LIVE_SPELLINGS:
        got = r._normalize_lane(raw)
        assert got in enum, raw                     # a real cell, never free text
        assert got != raw, raw                      # no raw spelling passes through
        assert r._normalize_lane(raw) == got        # stable across calls
    # the officer-role spelling collapses onto its context slug
    assert r._normalize_lane("polads-ceo") == "polads"
    # the three 'Commitments*' spellings of ONE conceptual lane land in ONE
    # cell — the exact de-fragmentation the demotion cluster needs
    assert len({r._normalize_lane(x) for x in _LIVE_SPELLINGS[:3]}) == 1
    # the docstring's promised fuzzy matches
    assert r._normalize_lane("cabinet") == "captains-cabinet"
    assert r._normalize_lane("PolAds delivery") == "polads"


def test_unknown_or_empty_lane_maps_to_stable_default():
    # fail-safe: unknown/empty inputs land on the FIXED 'adhoc' cell — one
    # stable catch-all, never a fresh per-call string (which would mint an
    # unclusterable cell per run).
    assert r._LANE_NORM_DEFAULT == "adhoc"          # a real context slug
    assert r._normalize_lane("") == r._LANE_NORM_DEFAULT
    assert r._normalize_lane(None) == r._LANE_NORM_DEFAULT
    a = r._normalize_lane("zzz unknown one")
    b = r._normalize_lane("qqq unknown two")
    assert a == b == r._LANE_NORM_DEFAULT           # different unknowns, ONE cell


def test_enum_unreadable_degrades_to_stable_slugify(monkeypatch, tmp_path):
    # config unreadable ⇒ deterministic per-input slugification (suffix-stripped
    # kebab) — still stable per input, never a fresh string per call.
    monkeypatch.setattr(r, "CONTEXTS_DIR", tmp_path / "no-such-contexts")
    monkeypatch.setattr(r, "_context_slugs_cache", None)   # drop the run cache
    assert r._normalize_lane("polads-ceo") == "polads"     # role suffix stripped
    assert r._normalize_lane("Commitments / Delivery") == "commitments-delivery"
    assert (r._normalize_lane("Commitments / Delivery")
            == r._normalize_lane("commitments   delivery"))   # spelling-stable
    assert r._normalize_lane("") == r._LANE_NORM_DEFAULT
    # idempotent in degraded mode too
    once = r._normalize_lane("polads-ceo")
    assert r._normalize_lane(once) == once
    monkeypatch.setattr(r, "_context_slugs_cache", None)   # don't poison later tests


def test_gate_reads_the_exact_cell_the_emitters_write(monkeypatch, tmp_path):
    # THE CRITICAL PARITY PIN: acted rows emitted under the normalized lane and
    # a gate query arriving with a RAW spelling must land on the SAME graduation
    # cell — if they diverge, demotion re-severs (the whole point of the fix).
    # Real emit_consequence into a fenced ledger + the REAL graduation.evaluate;
    # two acted rows under two DIFFERENT raw spellings of the one conceptual
    # lane, each superseded by a captain-undo (wrong) verdict → the 2-wrong
    # cluster forms in ONE cell, and the gate — queried with a THIRD spelling —
    # reads exactly that cell and demotes.
    from framework.fidelity.consequence import emit_consequence
    from framework.frontdoor import binder_wire as bw
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))

    for i, raw in enumerate(("Commitments", "Commitments / Delivery"), 1):
        lane = r._normalize_lane(raw)               # what ingestion stores/emits
        row = action_undo.new_row(
            pid=f"cellpin-{i}", cid="", step=1, kind="monday_task_create",
            backend="monday", lane=lane, subject=f"cell parity {i}",
            actor=r._ACTOR, executed_at=f"2026-07-05T0{i}:00:00Z")
        base = action_undo.acted_event(None, row)   # the executor's emit shape
        emit_consequence(**base)
        emit_consequence(**bw.acted_verdict_event(
            base, "undo", why="fenced parity test",
            reviewed_at=f"2026-07-05T0{i}:30:00Z"))

    # the gate, handed a third RAW spelling, keys the SAME cell → demoted
    demoted, why = r._graduation_demoted("task_create", "Commitments / Meetings")
    assert demoted is True and "demoted" in why
    # raw and pre-normalized queries agree (idempotent at the gate seam)
    assert r._graduation_demoted("task_create",
                                 r._normalize_lane("Commitments")) == (demoted, why)
    # a lane normalizing to a DIFFERENT cell is untouched (no over-blocking)
    assert r._graduation_demoted("task_create", "polads") == (False, "")


def test_main_ingestion_normalizes_lane_for_gate_and_store(monkeypatch):
    # main() seam (act path): an LLM free-text lane ('polads-ceo') is collapsed
    # at INGESTION, so the gate's graduation cell AND the stored record (which
    # the executor journals + emits acted rows from) carry the identical slug —
    # emit seam and gate can never diverge on the cell key.
    seen = {}

    def spy_eval(cell, **kw):
        seen["cell"] = cell
        return {"state": "unmeasured"}              # does not brake

    monkeypatch.setattr(graduation, "evaluate", spy_eval)
    step = ActionStep(kind="monday_task_update", title="move to Done",
                      payload={"board_id": "5091706356", "item_id": "42",
                               "status": "Done"})
    card = ActionProposal(subject="close cmt", situation="done", steps=(step,),
                          lane="polads-ceo",        # raw LLM spelling
                          evidence=("6-Commitments/x.md",), confidence=0.95,
                          urgency="batch")
    out = _drive_main(monkeypatch, proposals=[card], deliver_result={"ok": True})
    assert len(out["delivers"]) == 1                # acted
    assert seen["cell"] == ("officer:cos", "polads", "board_status")
    assert [s[1].lane for s in out["stores"]] == ["polads"]


def test_main_propose_path_emits_normalized_lane(monkeypatch):
    # main() seam (propose fallthrough): the PENDING proposal row and the stored
    # record also carry the normalized cell key — the ledger never accumulates a
    # free-text lane again (flag OFF = the plain propose lane, same seam).
    card = _update_card()
    card = ActionProposal(subject=card.subject, situation=card.situation,
                          steps=card.steps, lane="Commitments / Delivery",
                          evidence=card.evidence, confidence=card.confidence,
                          urgency=card.urgency)
    out = _drive_main(monkeypatch, proposals=[card],
                      deliver_result={"ok": True}, act_first=False)
    assert len(out["emits"]) == 1
    assert out["emits"][0]["lane"] == "adhoc"       # the stable catch-all slug
    assert [s[1].lane for s in out["stores"]] == ["adhoc"]


# ============================================================================
# ACTED-EVENT IDENTITY FIX — the lane's ledger READERS (germline 2026-07-05):
# acted rows moved from 'action-card' onto 'acted:<kind>', so the cross-run
# dedup (covered_evidence_refs) and the first-ever-cell receipt rule
# (_prior_acted_types) must read BOTH the canonical and the legacy identity —
# else every acted situation would re-propose and every post-fix first act
# would spuriously instant-tell.
# ============================================================================

def _fence(monkeypatch, tmp_path):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))


def test_covered_evidence_refs_reads_acted_rows(monkeypatch, tmp_path):
    _fence(monkeypatch, tmp_path)
    now = dt.datetime.now(dt.timezone.utc)
    # a presented card (legacy 'action-card' identity) carrying evidence refs
    _seed_card(now, subject="asked", hours_old=1, action_type="task_create")
    prop = r.proposal_event(actor=r._ACTOR, lane="polads", subject="asked2",
                            ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            action="action-card", refs=["6-Commitments/a.md"])
    r.emit_consequence(**prop)
    # an ACTED row on the canonical identity, evidence ref appended exactly as
    # action_exec._emit_acted_consequence does
    row = action_undo.new_row(pid="cov-1", cid="", step=1,
                              kind="monday_task_create", backend="monday",
                              lane="polads", subject="acted situation",
                              actor=r._ACTOR, executed_at="2026-07-05T01:00:00Z")
    ev = action_undo.acted_event(None, row)
    ev["refs"] = list(ev.get("refs") or []) + ["6-Commitments/b.md"]
    r.emit_consequence(**ev)

    refs = r.covered_evidence_refs()
    assert "6-Commitments/a.md" in refs             # presented card still covers
    assert "6-Commitments/b.md" in refs             # ACTED card now covers too —
    #                                    an acted situation must not re-propose


def test_prior_acted_types_reads_canonical_and_legacy(monkeypatch, tmp_path):
    _fence(monkeypatch, tmp_path)
    # canonical acted:<kind> row (post-fix executor emit), outcome present
    row = action_undo.new_row(pid="pat-1", cid="", step=1,
                              kind="monday_task_create", backend="monday",
                              lane="polads", subject="new acted",
                              actor=r._ACTOR, executed_at="2026-07-05T01:00:00Z")
    r.emit_consequence(**action_undo.acted_event(None, row))
    # legacy pre-fix acted row: 'action-card' + outcome (what the lane used to
    # emit) — history from before the fix must still count
    legacy = r.proposal_event(actor=r._ACTOR, lane="polads", subject="old acted",
                              ts="2026-07-01T00:00:00Z", action="action-card")
    legacy["action_type"] = "board_status"
    legacy["proposal"] = {"required": False, "decision": None}
    legacy["outcome"] = {"status": "unknown"}
    r.emit_consequence(**legacy)
    # a plain PENDING proposal (no outcome) must NOT count as acted
    r.emit_consequence(**r.proposal_event(
        actor=r._ACTOR, lane="polads", subject="only asked",
        ts="2026-07-02T00:00:00Z", action="action-card"))

    types = r._prior_acted_types()
    assert "task_create" in types                   # canonical identity read
    assert "board_status" in types                  # legacy identity still read
    assert len(types) == 2
