"""SOV-4 lane posture routing (D10/D13) — matrix wire, dormant ceilings, needs.

Fully fixtured: no Telegram, no live Redis/Monday, no LLM. The matrix wire is
driven through a fake posture ctx (pure callables over the REAL shipped floor
policy) so routing semantics are pinned against the germline data; the P3
sentinel poisons the new kernel modules to prove the absent-posture path never
touches them; P4 sweeps guardian routing against the legacy chain per
stampable action_type × confidence state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from framework.acting import run_action_lane as r
from framework.acting.action_lane import ActionProposal, ActionStep

_REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """No test touches the real repo's ledgers/config: needs ledger + posture
    config resolve under a tmp CABINET_ROOT (no posture.yml ⇒ absent), events
    to a tmp dir, needs dark unless a test arms them."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    monkeypatch.delenv("CABINET_POSTURE", raising=False)
    # RECONCILE 2026-07-05: kept both — main's DEMOTE-WIRE (_graduation_demoted)
    # does a REAL fail-closed graduation read whose bars load resolves the
    # matrix under CABINET_ROOT. A bare tmp root starves that load → every
    # act blocks "graduation state unreadable (fail-closed)" (correct runtime
    # behavior, wrong hermetic premise). Ship the floor into the tmp root
    # (posture.yml still ABSENT ⇒ the posture axis stays un-configured) so the
    # routing semantics under test are posture routing, not a broken plane.
    pol_dir = tmp_path / "root" / "framework" / "policies"
    pol_dir.mkdir(parents=True)
    (pol_dir / "authority-matrix.yml").write_text(
        (_REPO / "framework" / "policies" / "authority-matrix.yml").read_text())
    yield


def _policy():
    from framework.authority.matrix import load_matrix, matrix_policy
    return matrix_policy(load_matrix(str(
        _REPO / "framework" / "policies" / "authority-matrix.yml")))


def _pctx(state="unmeasured", posture="guardian", **over):
    """A fake D10 ctx: REAL floor policy + REAL risk_of/resolve_verdict from
    the ONE gate implementation, injectable cell state + posture."""
    from framework.authority import policy_engine
    ctx = {
        "policy": _policy(),
        "resolve_posture": lambda lane=None: posture,
        "risk_of": policy_engine.risk_of,
        "resolve_verdict": policy_engine.resolve_verdict,
        "read_cell_state": lambda officer, lane, at: state,
    }
    ctx.update(over)
    return ctx


# kind -> (payload, stamped action_type). The five stampable lane kinds.
_KINDS = {
    "monday_task_create": ({"board_id": "42424242", "title": "t"}, "task_create"),
    "monday_task_update": ({"board_id": "42424242", "monday_id": "42",
                            "set": {"status": "Done"}}, "board_status"),
    "reminder_create": ({"title": "t", "due_iso": "2026-07-06"}, "calendar_event_create"),
    "delegate_work": ({"officer": "cos", "brief": "b"}, "officer_dispatch"),
    "investigation_run": ({"officer": "cos", "question": "q"}, "investigation_run"),
}


def _card(kind, *, evidence=("6-Commitments/x.md",), conf=0.95):
    payload, _ = _KINDS[kind]
    step = ActionStep(kind=kind, title=f"do {kind}", payload=dict(payload))
    return ActionProposal(subject=f"s-{kind}", situation="w", steps=(step,),
                          lane="bakery", evidence=tuple(evidence),
                          confidence=conf, urgency="batch")


def _drive_main(monkeypatch, *, proposals, deliver_result=None, act_first=True,
                pctx="absent"):
    """The test_actfirst_gate driver + a pctx seam: "absent" pins the legacy
    path (ctx forced None), "real" leaves the genuine _load_posture_ctx (or a
    caller's pre-installed patch) in place, a dict installs that routing ctx."""
    emits, delivers, tgs, receipts = [], [], [], []

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
    monkeypatch.setattr(r, "_store_action", lambda *a, **k: None)
    monkeypatch.setattr(r, "_tg", lambda text: tgs.append(text))
    monkeypatch.setattr(r, "_emit_receipt", lambda *a, **k: receipts.append(a))
    monkeypatch.setattr(r, "_act_first_on", lambda: act_first)
    monkeypatch.setattr(r, "_confidence_floor", lambda: r.CONFIDENCE_FLOOR_DEFAULT)
    # RECONCILE 2026-07-05: kept both — main's ASK-BUDGET seam landed after the
    # sovereign fork; without this hermetic stub (same as test_actfirst_gate's
    # driver) _ask_budget_ok's `_redis("INCR", ...)` reaches the REAL local
    # Redis: it pollutes the LIVE day-budget key from a unit test AND, once the
    # live count passes the budget, withholds every presented card in these
    # fixtures (order-dependent full-suite failures). Fresh counter per
    # _drive_main call, so every test starts inside budget.
    _ask_counter = {"n": 0}

    def _fake_redis(*a):
        if a and a[0] == "INCR":
            _ask_counter["n"] += 1
            return str(_ask_counter["n"])
        return ""
    monkeypatch.setattr(r, "_redis", _fake_redis)
    if pctx == "absent":
        monkeypatch.setattr(r, "_load_posture_ctx", lambda: None)
    elif pctx != "real":
        monkeypatch.setattr(r, "_load_posture_ctx", lambda: pctx)
    monkeypatch.setattr(r.veto_registry, "rebuild_cache", lambda *a, **k: None)
    monkeypatch.setattr(r.veto_registry, "veto_cache_ready", lambda *a, **k: True)
    monkeypatch.setattr(r.veto_registry, "is_vetoed", lambda *a, **k: False)
    monkeypatch.setattr(r.actfirst_canary, "own_acted_cids", lambda *a, **k: frozenset())
    monkeypatch.setattr(r.actfirst_canary, "is_frozen", lambda *a, **k: False)
    monkeypatch.setattr(r.actfirst_canary, "is_silenced", lambda *a, **k: False)
    monkeypatch.setattr(r.actfirst_canary, "cap_check", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(r.actfirst_canary, "incr_and_check", lambda *a, **k: None)
    monkeypatch.setattr(r, "emit_consequence", lambda **ev: emits.append(ev))

    def fake_deliver(pid, **kw):
        delivers.append({"pid": pid, **kw})
        return dict(deliver_result or {"ok": True})
    monkeypatch.setattr(r, "deliver_action", fake_deliver)

    rc = r.main()
    return {"emits": emits, "delivers": delivers, "tgs": tgs,
            "receipts": receipts, "rc": rc}


# ============================================================================
# P3 sentinel — absent posture ⇒ the new kernel modules are untouched and the
# lane's behavior + summary bytes are unchanged even when they raise on import.
# ============================================================================

def _poison_new_modules(monkeypatch):
    """None in sys.modules ⇒ importing that module raises ImportError; the
    cached package attribute is removed so `from framework.authority import x`
    cannot short-circuit around it.

    RECONCILE 2026-07-05: kept both — `matrix` REMOVED from the poison list.
    Post-merge it is NOT a sovereign-new module: main's DEMOTE-WIRE
    (_graduation_demoted → graduation.evaluate → matrix bars) legitimately
    imports it on the absent-posture path, and poisoning it correctly trips
    the fail-closed brake ("graduation state unreadable") — main's invariant,
    not a posture leak. The sentinel still poisons everything the posture
    axis actually added (posture/grants/needs kernels + the policy_engine
    routing import)."""
    import framework.authority as fa
    for name in ("posture", "grants", "needs"):
        monkeypatch.setitem(sys.modules, f"framework.authority.{name}", None)
        monkeypatch.delattr(fa, name, raising=False)
    monkeypatch.setitem(sys.modules, "policy_engine", None)


def test_p3_absent_posture_flag_on_acts_with_poisoned_modules(monkeypatch, capsys):
    _poison_new_modules(monkeypatch)
    # the REAL _load_posture_ctx runs ("real" leaves the seam alone): the
    # posture import raises ⇒ silent None ⇒ legacy chain acts exactly as before
    out = _drive_main(monkeypatch, proposals=[_card("monday_task_update")],
                      pctx="real")
    assert len(out["delivers"]) == 1 and out["tgs"] == []
    stdout = capsys.readouterr().out
    assert "done: presented 0 card(s), acted 1 card(s)" in stdout
    assert "posture" not in stdout            # the absent path is SILENT


def test_p3_absent_posture_flag_off_summary_bytes(monkeypatch, capsys):
    _poison_new_modules(monkeypatch)
    out = _drive_main(monkeypatch, proposals=[_card("monday_task_update")],
                      act_first=False, pctx="real")
    assert out["delivers"] == [] and len(out["tgs"]) == 1
    stdout = capsys.readouterr().out
    assert "done: presented 1 action card(s)" in stdout
    assert "acted" not in stdout and "posture" not in stdout


def test_p3_flag_off_never_loads_the_ctx(monkeypatch):
    called = []
    monkeypatch.setattr(r, "_load_posture_ctx",
                        lambda: called.append(1) or None)
    _drive_main(monkeypatch, proposals=[_card("monday_task_update")],
                act_first=False, pctx="real")
    # "real" leaves the tracking patch above in place — the point: a flag-off
    # run never even evaluates the ctx loader.
    assert called == []


# ============================================================================
# _load_posture_ctx — presence gating + fail-safe polarity
# ============================================================================

def test_ctx_none_when_no_posture_yml(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))   # empty root
    assert r._load_posture_ctx() is None
    assert capsys.readouterr().out == ""                # silent (P3)


def test_ctx_loads_when_posture_yml_present(tmp_path, monkeypatch):
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "posture.yml").write_text("posture: guardian\n")   # even corrupt counts
    # the matrix floor resolves under the SAME root (deployment semantics)
    floor = tmp_path / "framework" / "policies"
    floor.mkdir(parents=True)
    (floor / "authority-matrix.yml").write_text(
        (_REPO / "framework" / "policies" / "authority-matrix.yml").read_text())
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    ctx = r._load_posture_ctx()
    assert ctx is not None
    assert callable(ctx["resolve_verdict"]) and callable(ctx["risk_of"])
    # an unattested/corrupt ruling resolves guardian through the wire
    assert ctx["resolve_posture"]("bakery") == "guardian"


def test_ctx_present_but_broken_matrix_degrades_loudly(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "posture.yml").write_text("posture: guardian\n")
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    import framework.authority.matrix as m
    monkeypatch.setattr(m, "load_matrix",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert r._load_posture_ctx() is None
    assert "routing ctx unavailable" in capsys.readouterr().out


# ============================================================================
# P4 — guardian+file-present parity: 5 stampable action_types × 5 states.
# Legacy (flag-on, no posture ctx) is graduation-BLIND; guardian routing must
# reproduce its mechanical outcome at every operative state. The ONE ruled
# divergence is demote: the matrix narrows to propose (§0 — demote always
# narrows, evidence beats posture); a narrower-only diff is asserted, never
# a widening one.
# ============================================================================

_STATES = ("unmeasured", "propose_only", "eligible", "graduated", "demote")


@pytest.mark.parametrize("kind", sorted(_KINDS))
@pytest.mark.parametrize("state", _STATES)
def test_p4_guardian_routing_parity(monkeypatch, kind, state):
    legacy = _drive_main(monkeypatch, proposals=[_card(kind)], pctx=None)
    legacy_acted = len(legacy["delivers"]) == 1
    routed = _drive_main(monkeypatch, proposals=[_card(kind)],
                         pctx=_pctx(state=state, posture="guardian"))
    routed_acted = len(routed["delivers"]) == 1
    if state == "demote":
        assert routed_acted is False          # demote narrows — never widens
    else:
        assert routed_acted == legacy_acted, (kind, state)
    # in every cell the card lands somewhere: acted or proposed, never dropped
    assert routed_acted or len(routed["tgs"]) == 1


def test_p4_guardian_routed_act_carries_guardian_posture(monkeypatch):
    out = _drive_main(monkeypatch, proposals=[_card("monday_task_update")],
                      pctx=_pctx(state="unmeasured", posture="guardian"))
    assert len(out["delivers"]) == 1
    assert out["delivers"][0]["act_first"] is True
    assert out["delivers"][0]["posture"] == "guardian"


def test_legacy_path_delivers_with_posture_none(monkeypatch):
    out = _drive_main(monkeypatch, proposals=[_card("monday_task_update")],
                      pctx=None)
    assert len(out["delivers"]) == 1
    assert out["delivers"][0]["posture"] is None


# ============================================================================
# Sovereign routing
# ============================================================================

def test_sovereign_act_with_undo_acts(monkeypatch):
    out = _drive_main(monkeypatch, proposals=[_card("monday_task_create")],
                      pctx=_pctx(posture="sovereign"))
    assert len(out["delivers"]) == 1
    assert out["delivers"][0]["posture"] == "sovereign"
    assert out["tgs"] == []


# RECONCILE 2026-07-05: kept both — sovereign's D10 auto-without-inverse ⇒
# capability-need wire, retargeted for main's fix-wave class split:
# investigation_run moved reversible → read_only_dispatch (sovereign
# notify_after, deliberately inverse-less by main's read-only contract), so no
# stampable lane kind maps to `reversible` on the REAL floor any more. The D10
# wire is driven with a risk_of override forcing the reversible row (the
# verdict still resolves through the REAL sovereign table) on the inverse-less
# delegate_work kind.
def _auto_forcing_pctx():
    return _pctx(posture="sovereign",
                 risk_of=lambda at, rcs: "reversible")


def test_sovereign_auto_without_inverse_proposes_and_files_capability_need(
        tmp_path, monkeypatch, capsys):
    # forced reversible ⇒ sovereign auto at unmeasured, but delegate_work has
    # no registered inverse ⇒ propose + kind=capability need (D10)
    root = tmp_path / "root"
    monkeypatch.setenv("CABINET_ROOT", str(root))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    out = _drive_main(monkeypatch, proposals=[_card("delegate_work")],
                      pctx=_auto_forcing_pctx())
    assert out["delivers"] == [] and len(out["tgs"]) == 1
    assert "no registered inverse" in capsys.readouterr().out
    ledger = root / "shared" / "interfaces" / "needs-ledger.jsonl"
    rows = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert any(row["kind"] == "capability"
               and row["action_type"] == "officer_dispatch" for row in rows)


def test_sovereign_capability_need_dark_without_wire(tmp_path, monkeypatch):
    root = tmp_path / "root"
    monkeypatch.setenv("CABINET_ROOT", str(root))     # needs NOT wired
    _drive_main(monkeypatch, proposals=[_card("delegate_work")],
                pctx=_auto_forcing_pctx())
    assert not (root / "shared" / "interfaces" / "needs-ledger.jsonl").exists()


def test_sovereign_demote_narrows_to_propose(monkeypatch):
    out = _drive_main(monkeypatch, proposals=[_card("monday_task_create")],
                      pctx=_pctx(state="demote", posture="sovereign"))
    assert out["delivers"] == [] and len(out["tgs"]) == 1


def test_sovereign_dispatch_stays_proposed(monkeypatch):
    # internal_comms ⇒ notify_after in sovereign, but delegate_work has no
    # inverse ⇒ the mechanical chain proposes — officer_dispatch held (D14)
    out = _drive_main(monkeypatch, proposals=[_card("delegate_work")],
                      pctx=_pctx(posture="sovereign"))
    assert out["delivers"] == [] and len(out["tgs"]) == 1


def test_routed_summary_strings_unchanged(monkeypatch, capsys):
    _drive_main(monkeypatch, proposals=[_card("monday_task_update")],
                pctx=_pctx(posture="sovereign"))
    assert "done: presented 0 card(s), acted 1 card(s)" in capsys.readouterr().out


# ============================================================================
# Ceiling rows — standing_grant is DORMANT at the lane (FI-2 v1): probe +
# need, never an act, even on a grant hit (no scope-enforcing executor).
# ============================================================================

def _ceiling_pctx():
    # force the routed verdict to the ceiling branch: a fake risk_of maps the
    # stamp to external_comms and the sovereign table answers standing_grant.
    return _pctx(posture="sovereign",
                 risk_of=lambda at, rcs: "external_comms")


def test_standing_grant_verdict_proposes_and_files_need(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    monkeypatch.setenv("CABINET_ROOT", str(root))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    out = _drive_main(monkeypatch, proposals=[_card("monday_task_update")],
                      pctx=_ceiling_pctx())
    assert out["delivers"] == [] and len(out["tgs"]) == 1
    assert "matrix verdict standing_grant" in capsys.readouterr().out
    ledger = root / "shared" / "interfaces" / "needs-ledger.jsonl"
    rows = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert any(row["kind"] == "standing_grant"
               and row["risk_class"] == "external_comms" for row in rows)


def test_standing_grant_hit_still_never_acts(monkeypatch):
    # v1 dormancy (FI-2/REDTEAM): even a granted probe must not act and must
    # not consume the rate counter — there is no scope-enforcing executor.
    from framework.authority import grants
    monkeypatch.setattr(grants, "check",
                        lambda *a, **k: {"granted": True, "grant_id": "GRANT-x",
                                         "reason": "matched"})
    monkeypatch.setattr(grants, "record_use",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("record_use must never run at the lane")))
    out = _drive_main(monkeypatch, proposals=[_card("monday_task_update")],
                      pctx=_ceiling_pctx())
    assert out["delivers"] == [] and len(out["tgs"]) == 1


# ============================================================================
# D13 — inbound provenance never acts first, any posture
# ============================================================================

def test_inbound_evidence_never_act_first_eligible():
    card = _card("monday_task_update",
                 evidence=("3-People/frederik/conversations.md",))
    ok, why = r._card_act_first_eligible(card, "board_status")
    assert ok is False and "inbound provenance" in why


def test_meeting_evidence_is_inbound():
    card = _card("monday_task_update", evidence=("2-Meetings/2026-07-02.md",))
    assert r._card_provenance(card) == "inbound"
    ok, why = r._card_act_first_eligible(card, "board_status")
    assert ok is False and "inbound provenance" in why


def test_internal_evidence_stays_eligible():
    card = _card("monday_task_update")     # 6-Commitments ref
    assert r._card_provenance(card) == "internal"
    ok, why = r._card_act_first_eligible(card, "board_status")
    assert ok is True and why == ""


def test_inbound_card_proposes_even_in_sovereign(monkeypatch, capsys):
    card = _card("monday_task_update", evidence=("3-People/x/conversations.md",))
    out = _drive_main(monkeypatch, proposals=[card],
                      pctx=_pctx(posture="sovereign"))
    assert out["delivers"] == [] and len(out["tgs"]) == 1
    assert "inbound provenance" in capsys.readouterr().out


def test_explicit_provenance_stamp_honored():
    # future-proof: a proposer-stamped provenance attribute wins outright
    card = _card("monday_task_update")
    object.__setattr__(card, "provenance", "inbound")   # frozen dataclass
    assert r._card_provenance(card) == "inbound"


# ============================================================================
# _max_auto_steps — 2 guardian (forced) / 5 sovereign (FI-1), fail-safe 2
# ============================================================================

def test_max_auto_steps_defaults():
    assert r._max_auto_steps(None) == r.MAX_AUTO_EXEC_STEPS == 2
    assert r._max_auto_steps("guardian") == 2


def test_max_auto_steps_sovereign_reads_kernel(monkeypatch):
    import framework.authority.posture as P
    monkeypatch.setattr(P, "max_auto_steps", lambda posture, *a, **k: 5)
    assert r._max_auto_steps("sovereign") == 5


def test_max_auto_steps_broken_kernel_tightens(monkeypatch):
    import framework.authority.posture as P
    monkeypatch.setattr(P, "max_auto_steps",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert r._max_auto_steps("sovereign") == 2


def test_eligibility_honors_max_steps_param():
    steps = tuple(ActionStep(kind="monday_task_update", title=f"s{i}",
                             payload={"board_id": "1", "monday_id": "2",
                                      "set": {"status": "Done"}})
                  for i in range(3))
    card = ActionProposal(subject="s", situation="w", steps=steps, lane="bakery",
                          evidence=("6-Commitments/x.md",), confidence=0.9,
                          urgency="batch")
    ok, why = r._card_act_first_eligible(card, "board_status")
    assert ok is False and ">2 steps" in why
    ok, why = r._card_act_first_eligible(card, "board_status", max_steps=5)
    assert ok is True and why == ""


# ============================================================================
# _route_verdict — verdict resolution against the REAL shipped floor
# ============================================================================

def test_route_verdict_guardian_matches_root_table():
    ctx = _pctx(state="unmeasured", posture="guardian")
    v, posture, rc = r._route_verdict(ctx, _card("monday_task_create"), "task_create")
    assert (v, posture, rc) == ("act_with_undo", "guardian", "pm_write")
    v, _, rc = r._route_verdict(ctx, _card("delegate_work"), "officer_dispatch")
    assert (v, rc) == ("propose_only", "internal_comms")


def test_route_verdict_sovereign_selects_posture_table():
    # RECONCILE 2026-07-05: kept both — main's class split moved
    # investigation_run to read_only_dispatch (notify_after in BOTH tables),
    # so posture-table SELECTION is proven on task_status_move instead:
    # guardian act_with_undo vs sovereign auto for the same reversible cell.
    ctx = _pctx(state="unmeasured", posture="sovereign")
    v, _, rc = r._route_verdict(ctx, _card("investigation_run"), "investigation_run")
    assert (v, rc) == ("notify_after", "read_only_dispatch")
    v, _, rc = r._route_verdict(ctx, _card("monday_task_create"), "task_status_move")
    assert (v, rc) == ("auto", "reversible")
    g = _pctx(state="unmeasured", posture="guardian")
    v, _, _ = r._route_verdict(g, _card("monday_task_create"), "task_status_move")
    assert v == "act_with_undo"
    v, _, _ = r._route_verdict(ctx, _card("delegate_work"), "officer_dispatch")
    assert v == "notify_after"


def test_route_verdict_unstamped_or_unmapped_is_none():
    ctx = _pctx()
    v, posture, rc = r._route_verdict(ctx, _card("monday_task_create"), None)
    assert v is None and rc is None and posture == "guardian"
    v, _, rc = r._route_verdict(ctx, _card("monday_task_create"), "not_a_type")
    assert v is None and rc is None
