"""Tests for the trust ladder — the OPT-IN earn_up surface (AX-2).

Non-negotiable properties under test (the historical set + the axes-build
modernizations, spec 2026-07-05 §1 L1):
  1. Fail-closed load: a missing/broken ladder file -> single would-like-to rung.
  2. Only the grand-plan rung vocabulary is valid; junk rungs are dropped.
  3. A rung is EARNED only when EVERY granted cell is `graduated`.
  4. A ceiling rung (granted cell maps to a hard-ceiling risk_class) is
     classified blocked_by_ceiling — NEVER 'earned' (no auto-advance path).
  5. propose_next_rung SURFACES, never grants. grant_rung is the only path
     that emits trust_rung_granted, rejects an unknown rung — and the event
     is AUDIT ONLY: authority derives EXCLUSIVELY from `granted:` rows of the
     ATTESTED (Captain-locked) ladder file. A forged trust_rung_granted event
     mints nothing (the AX-8 no-self-grant fix); unattested granted rows are
     ignored; malformed rows are line-dropped.
  6. POSTURE GATE: the surfacing path is inert unless resolve_posture()==
     earn_up (guardian/sovereign/broken kernel -> None, zero side effects).
  7. GATE OVERLAY INPUT: rung_verdict_lift maps the effective granted rung
     (from the attested file) through the FROZEN rung->verdict table, capped
     by the ladder FILE, and fail-closes to None (the earn_up floor) on
     missing/corrupt/unattested file, base rung, wrong posture, or any
     failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.learning import trust_ladder as T  # noqa: E402


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    monkeypatch.setenv("CABINET_PRODUCT_SLUG", "testprod")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CABINET_POSTURE", raising=False)


def _write_ladder(tmp_path, body: str) -> Path:
    # Path assembled from the module's own constant — no literal layer token,
    # so the layer-separation baseline's ratcheted-out entry needn't regrow.
    root = tmp_path / "cab"
    cfg = root / T._LADDER_REL
    cfg.parent.mkdir(parents=True)
    cfg.write_text(body)
    return root


_EARN_UP = lambda lane=None: "earn_up"  # noqa: E731 — injectable posture_fn
_LOCKED = lambda p: True    # noqa: E731 — injectable attestation (tests own tmp roots)


# --------------------------------------------------------------------------
# 1. Fail-closed load.
# --------------------------------------------------------------------------

def test_missing_file_defaults_to_base_rung(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    ladder = T.load_ladder(cabinet_root=root)
    assert len(ladder) == 1
    assert ladder[0].name == T.BASE_RUNG
    assert ladder[0].grants == []


def test_broken_yaml_defaults_to_base_rung(tmp_path):
    root = _write_ladder(tmp_path, "rungs: [ this is : not : valid yaml ][")
    ladder = T.load_ladder(cabinet_root=root)
    assert [r.name for r in ladder] == [T.BASE_RUNG]


def test_empty_rungs_defaults_to_base(tmp_path):
    root = _write_ladder(tmp_path, "rungs: []\n")
    ladder = T.load_ladder(cabinet_root=root)
    assert [r.name for r in ladder] == [T.BASE_RUNG]


# --------------------------------------------------------------------------
# 2. Only the valid vocabulary survives.
# --------------------------------------------------------------------------

def test_junk_rung_names_dropped(tmp_path):
    root = _write_ladder(tmp_path, """
rungs:
  - name: super-autonomous
    lane: bakery
    grants:
      - { action_type: task_status_move }
  - name: ive-done
    lane: bakery
    grants:
      - { action_type: task_status_move }
""")
    ladder = T.load_ladder(cabinet_root=root)
    names = [r.name for r in ladder]
    assert "super-autonomous" not in names
    assert "ive-done" in names
    # base rung is injected + first.
    assert names[0] == T.BASE_RUNG


# --------------------------------------------------------------------------
# 3. Earned requires ALL granted cells graduated.
# --------------------------------------------------------------------------

def _eval_factory(states: dict):
    """states maps action_type -> (state, sample_count)."""
    def fn(cell):
        _actor, _lane, at = cell
        st, n = states.get(at, ("unmeasured", None))
        return {"state": st, "evidence": {"sample_count": n}}
    return fn


def test_rung_earned_when_all_cells_graduated(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery",
               [("bakery", "task_status_move"), ("bakery", "label")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    ev = _eval_factory({"task_status_move": ("graduated", 30),
                        "label": ("graduated", 25)})
    res = T.evaluate_ladder("officer:cos", "bakery", evaluate_fn=ev)
    assert [e["rung"]["name"] for e in res["earned"]] == ["ive-done"]
    assert res["pending"] == []


def test_rung_pending_when_one_cell_not_graduated(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery",
               [("bakery", "task_status_move"), ("bakery", "label")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    ev = _eval_factory({"task_status_move": ("graduated", 30),
                        "label": ("eligible", 18)})
    res = T.evaluate_ladder("officer:cos", "bakery", evaluate_fn=ev)
    assert res["earned"] == []
    assert [e["rung"]["name"] for e in res["pending"]] == ["ive-done"]


def test_min_samples_override_blocks_earn(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery", [("bakery", "task_status_move")], 50, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    # graduated but only 30 samples < the rung's 50 override -> pending.
    ev = _eval_factory({"task_status_move": ("graduated", 30)})
    res = T.evaluate_ladder("officer:cos", "bakery", evaluate_fn=ev)
    assert res["earned"] == []
    assert [e["rung"]["name"] for e in res["pending"]] == ["ive-done"]


def test_rung_with_no_grants_never_earned(tmp_path, monkeypatch):
    rungs = [T.Rung("would-like-to", None, [], None, []),
             T.Rung("ive-done", "bakery", [], None, [])]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    res = T.evaluate_ladder("officer:cos", "bakery", evaluate_fn=_eval_factory({}))
    assert res["earned"] == []


def test_none_evaluate_result_reads_unmeasured(tmp_path, monkeypatch):
    # graduation.evaluate returns None for a cell with no rows — must read as
    # unmeasured (never earned, never raise).
    rungs = [T.Rung("would-like-to", None, [], None, []),
             T.Rung("ive-done", "bakery", [("bakery", "task_status_move")], None, [])]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    res = T.evaluate_ladder("officer:cos", "bakery", evaluate_fn=lambda cell: None)
    assert res["earned"] == []
    assert [e["rung"]["name"] for e in res["pending"]] == ["ive-done"]


# --------------------------------------------------------------------------
# 4. Ceiling rung never earns — blocked_by_ceiling.
# --------------------------------------------------------------------------

def test_ceiling_rung_is_blocked_not_earned(tmp_path, monkeypatch):
    # external_message maps to external_comms (hard ceiling) via the real matrix.
    ceiling = T._grants_touch_ceiling([("bakery", "external_message")])
    assert ceiling == ["external_comms"]  # sanity: matrix mapping holds

    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery", [("bakery", "external_message")], None, ceiling),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    # even if the cell is fully graduated, it must NOT be 'earned'.
    ev = _eval_factory({"external_message": ("graduated", 100)})
    res = T.evaluate_ladder("officer:cos", "bakery", evaluate_fn=ev)
    assert res["earned"] == []
    assert [e["rung"]["name"] for e in res["blocked_by_ceiling"]] == ["ive-done"]
    assert res["blocked_by_ceiling"][0]["ceiling"] == ["external_comms"]


# --------------------------------------------------------------------------
# 5. propose_next_rung surfaces; grant_rung is the only grant path.
# --------------------------------------------------------------------------

def test_propose_surfaces_lowest_earned_non_ceiling(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery", [("bakery", "task_status_move")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    ev = _eval_factory({"task_status_move": ("graduated", 30)})

    enq = []
    emitted = []
    prop = T.propose_next_rung(
        "officer:cos", "bakery", evaluate_fn=ev,
        enqueue_fn=lambda item: enq.append(item) or "sid",
        emit_fn=lambda et, actor, payload: emitted.append((et, payload)),
        posture_fn=_EARN_UP,
    )
    assert prop is not None
    assert prop["rung"] == "ive-done"
    assert prop["ceiling"] is False
    assert prop["enqueued_id"] == "sid"
    assert enq[0]["source"] == "trust-ladder"
    assert ("trust_rung_proposed", {"actor_id": "officer:cos", "lane": "bakery",
            "rung": "ive-done", "ceiling": False, "urgency_tier": "batch"}) in emitted


def test_propose_returns_none_when_nothing_earned(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery", [("bakery", "task_status_move")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    ev = _eval_factory({"task_status_move": ("eligible", 10)})
    prop = T.propose_next_rung("officer:cos", "bakery", evaluate_fn=ev,
                               enqueue_fn=lambda i: "x", emit_fn=lambda *a, **k: None,
                               posture_fn=_EARN_UP)
    assert prop is None


def test_propose_ceiling_rung_flagged_captain_only(tmp_path, monkeypatch):
    ceiling = T._grants_touch_ceiling([("bakery", "external_message")])
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery", [("bakery", "external_message")], None, ceiling),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    ev = _eval_factory({"external_message": ("graduated", 100)})
    prop = T.propose_next_rung("officer:cos", "bakery", evaluate_fn=ev,
                               enqueue_fn=lambda i: "x", emit_fn=lambda *a, **k: None,
                               posture_fn=_EARN_UP)
    assert prop is not None
    assert prop["ceiling"] is True
    assert "Captain-only" in prop["summary"]


def test_propose_does_not_emit_granted_event(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery", [("bakery", "task_status_move")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    ev = _eval_factory({"task_status_move": ("graduated", 30)})
    emitted = []
    T.propose_next_rung("officer:cos", "bakery", evaluate_fn=ev,
                        enqueue_fn=lambda i: "x",
                        emit_fn=lambda et, actor, payload: emitted.append(et),
                        posture_fn=_EARN_UP)
    # propose emits trust_rung_proposed but NEVER trust_rung_granted.
    assert "trust_rung_proposed" in emitted
    assert "trust_rung_granted" not in emitted


def test_propose_real_emitter_type_is_registered(tmp_path, monkeypatch):
    """trust_rung_proposed rides the REAL emitter (re-registered in
    VALID_EVENT_TYPES by the axes build) — a raise here means the type was
    dropped again."""
    from framework.events.emitter import replay
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery", [("bakery", "task_status_move")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    ev = _eval_factory({"task_status_move": ("graduated", 30)})
    prop = T.propose_next_rung("officer:cos", "bakery", evaluate_fn=ev,
                               enqueue_fn=lambda i: "x", posture_fn=_EARN_UP)
    assert prop is not None
    events = replay(event_types=["trust_rung_proposed"])
    assert len(events) == 1
    assert events[0]["payload"]["rung"] == "ive-done"


def test_grant_rung_emits_granted_event():
    emitted = {}
    T.grant_rung("ive-done", lane="bakery",
                 emit_fn=lambda et, actor, payload: emitted.update(
                     {"et": et, "actor": actor, "payload": payload}))
    assert emitted["et"] == "trust_rung_granted"
    assert emitted["payload"]["rung"] == "ive-done"
    assert emitted["payload"]["lane"] == "bakery"


def test_grant_rung_rejects_unknown_rung():
    with pytest.raises(ValueError):
        T.grant_rung("god-mode", emit_fn=lambda *a, **k: None)


# --------------------------------------------------------------------------
# 5b. current_rung — authority derives ONLY from the ATTESTED ladder file
#     (the AX-8 no-self-grant fix; standing-grants polarity).
# --------------------------------------------------------------------------

def test_current_rung_derives_from_attested_granted_rows(tmp_path):
    root = _write_ladder(tmp_path, """
rungs:
  - name: ive-done
    lane: bakery
    grants: [ { action_type: task_status_move } ]
granted:
  - { rung: intend-to, lane: bakery }
  - { rung: would-like-to, lane: bakery }
""")
    # highest applicable row wins; a lower row does not lower the rung.
    assert T.current_rung("bakery", root, is_locked_fn=_LOCKED) == "intend-to"
    # a different lane is unaffected.
    assert T.current_rung("newsletter", root, is_locked_fn=_LOCKED) == T.BASE_RUNG


def test_current_rung_lane_none_grant_applies_to_all_lanes(tmp_path):
    root = _write_ladder(tmp_path, "granted:\n  - { rung: ive-done }\n")
    assert T.current_rung("bakery", root, is_locked_fn=_LOCKED) == "ive-done"
    assert T.current_rung("newsletter", root, is_locked_fn=_LOCKED) == "ive-done"


def test_current_rung_missing_file_is_base(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    assert T.current_rung("bakery", root, is_locked_fn=_LOCKED) == T.BASE_RUNG


def test_current_rung_unattested_file_grants_nothing(tmp_path):
    """SECURITY: a present-but-NOT-Captain-locked ladder file mints no rung —
    widening authority is honored only from the attested artifact."""
    root = _write_ladder(
        tmp_path, "granted:\n  - { rung: ive-been-doing, lane: bakery }\n")
    assert T.current_rung("bakery", root,
                          is_locked_fn=lambda p: False) == T.BASE_RUNG
    # the default attestation on an ordinary (never-chflags'd) tmp file must
    # also read NOT locked ⇒ base.
    assert T.current_rung("bakery", root) == T.BASE_RUNG


def test_forged_granted_event_mints_nothing(tmp_path):
    """SECURITY (the AX-8 finding): a same-uid actor emitting
    trust_rung_granted — even claiming actor='captain' — must not advance the
    rung or lift any verdict. The ledger is unauthenticated; authority never
    derives from it."""
    from framework.events.emitter import emit
    root = _write_ladder(tmp_path, _ladder_body("ive-done"))
    emit("trust_rung_granted", actor="captain",
         payload={"rung": "ive-been-doing", "lane": "bakery"})
    assert T.current_rung("bakery", root, is_locked_fn=_LOCKED) == T.BASE_RUNG
    assert T.rung_verdict_lift("bakery", posture="earn_up", cabinet_root=root,
                               is_locked_fn=_LOCKED) is None


def test_grant_rung_event_alone_does_not_advance(tmp_path):
    """grant_rung records the AUDIT event (registered emitter type); without
    the Captain's granted row in the attested file the rung stays at base."""
    root = _write_ladder(tmp_path, _ladder_body("ive-done"))
    T.grant_rung("ive-done", lane="bakery")  # real emitter, tmp event log
    assert T.current_rung("bakery", root, is_locked_fn=_LOCKED) == T.BASE_RUNG


def test_malformed_granted_rows_dropped(tmp_path):
    root = _write_ladder(tmp_path, """
granted:
  - { rung: god-mode, lane: bakery }                      # out-of-vocab
  - { rung: ive-been-doing, lane: bakery, extra: nope }   # unknown key
  - ive-been-doing                                        # not a mapping
  - { rung: intend-to, lane: bakery }                     # the one valid row
""")
    assert T.current_rung("bakery", root, is_locked_fn=_LOCKED) == "intend-to"


def test_granted_not_a_list_grants_nothing(tmp_path):
    root = _write_ladder(tmp_path, "granted: { rung: ive-done }\n")
    assert T.current_rung("bakery", root, is_locked_fn=_LOCKED) == T.BASE_RUNG


# --------------------------------------------------------------------------
# 6. Posture gate — the surfacing path is inert outside earn_up.
# --------------------------------------------------------------------------

def _earned_setup(monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "bakery", [("bakery", "task_status_move")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung",
                        lambda lane=None, *a, **k: "would-like-to")
    return _eval_factory({"task_status_move": ("graduated", 30)})


@pytest.mark.parametrize("posture", ["guardian", "sovereign", "weird", None])
def test_propose_inert_outside_earn_up(tmp_path, monkeypatch, posture):
    ev = _earned_setup(monkeypatch)
    enq, emitted = [], []
    prop = T.propose_next_rung(
        "officer:cos", "bakery", evaluate_fn=ev,
        enqueue_fn=lambda item: enq.append(item) or "sid",
        emit_fn=lambda et, actor, payload: emitted.append(et),
        posture_fn=lambda lane=None: posture,
    )
    assert prop is None
    assert enq == [] and emitted == []  # zero side effects


def test_propose_inert_when_posture_kernel_broken(tmp_path, monkeypatch):
    ev = _earned_setup(monkeypatch)

    def boom(lane=None):
        raise RuntimeError("kernel down")

    enq = []
    prop = T.propose_next_rung(
        "officer:cos", "bakery", evaluate_fn=ev,
        enqueue_fn=lambda item: enq.append(item) or "sid",
        emit_fn=lambda *a, **k: None, posture_fn=boom,
    )
    assert prop is None
    assert enq == []


def test_propose_default_posture_resolution_is_inert_here(tmp_path, monkeypatch):
    """No posture_fn injected: the REAL kernel resolves guardian in this test
    env (no attested earn_up ruling) ⇒ inert — the default world never
    surfaces rung cards."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # no posture.yml here
    ev = _earned_setup(monkeypatch)
    enq = []
    prop = T.propose_next_rung(
        "officer:cos", "bakery", evaluate_fn=ev,
        enqueue_fn=lambda item: enq.append(item) or "sid",
        emit_fn=lambda *a, **k: None,
    )
    assert prop is None
    assert enq == []


# --------------------------------------------------------------------------
# 7. The gate overlay input — rung_verdict_lift (frozen map, capped,
#    fail-closed).
# --------------------------------------------------------------------------

def test_rung_verdicts_is_the_frozen_map():
    assert T.RUNG_VERDICTS == {
        "would-like-to": "propose_only",
        "intend-to": "auto_with_veto_window",
        "ive-done": "notify_after",
        "ive-been-doing": "auto",
    }
    assert set(T.RUNG_VERDICTS) == set(T.RUNG_ORDER)


def _ladder_body(rung: str, lane: str = "bakery",
                 granted: str | None = None) -> str:
    """A ladder file body; `granted` adds the Captain's granted row (the
    attested-file authority source — tests inject is_locked_fn)."""
    body = f"""
rungs:
  - name: {rung}
    lane: {lane}
    grants:
      - {{ action_type: task_status_move }}
"""
    if granted:
        body += f"granted:\n  - {{ rung: {granted}, lane: {lane} }}\n"
    return body


def test_ladder_rung_cap_missing_file_is_base(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    assert T.ladder_rung_cap("bakery", cabinet_root=root) == T.BASE_RUNG


def test_ladder_rung_cap_is_highest_applicable_rung(tmp_path):
    root = _write_ladder(tmp_path, """
rungs:
  - name: intend-to
    lane: bakery
    grants: [ { action_type: internal_message } ]
  - name: ive-done
    lane: bakery
    grants: [ { action_type: task_status_move } ]
  - name: ive-been-doing
    lane: newsletter
    grants: [ { action_type: label } ]
""")
    assert T.ladder_rung_cap("bakery", cabinet_root=root) == "ive-done"
    assert T.ladder_rung_cap("newsletter", cabinet_root=root) == "ive-been-doing"
    # a lane the file defines nothing for stays at base (no lift).
    assert T.ladder_rung_cap("jobdanmark", cabinet_root=root) == T.BASE_RUNG


@pytest.mark.parametrize("rung,verdict", [
    ("intend-to", "auto_with_veto_window"),
    ("ive-done", "notify_after"),
    ("ive-been-doing", "auto"),
])
def test_lift_maps_granted_rung_per_frozen_map(tmp_path, rung, verdict):
    root = _write_ladder(tmp_path, _ladder_body(rung, granted=rung))
    got = T.rung_verdict_lift("bakery", posture="earn_up", cabinet_root=root,
                              is_locked_fn=_LOCKED)
    assert got == verdict


def test_lift_base_rung_is_no_lift(tmp_path):
    root = _write_ladder(tmp_path, _ladder_body("ive-done"))
    # nothing granted ⇒ effective rung = would-like-to ⇒ None (the floor).
    assert T.rung_verdict_lift("bakery", posture="earn_up", cabinet_root=root,
                               is_locked_fn=_LOCKED) is None


def test_lift_capped_by_ladder_file(tmp_path):
    # Captain granted ive-been-doing, but the FILE only defines intend-to for
    # the lane ⇒ the lift is capped at intend-to.
    root = _write_ladder(
        tmp_path, _ladder_body("intend-to", granted="ive-been-doing"))
    got = T.rung_verdict_lift("bakery", posture="earn_up", cabinet_root=root,
                              is_locked_fn=_LOCKED)
    assert got == "auto_with_veto_window"


def test_lift_fail_closed_on_missing_ladder_file(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    # no file ⇒ neither granted rows nor a cap ⇒ no lift (fail-closed) —
    # deleting the file is the Captain's mechanical kill handle.
    assert T.rung_verdict_lift("bakery", posture="earn_up", cabinet_root=root,
                               is_locked_fn=_LOCKED) is None


def test_lift_fail_closed_on_corrupt_ladder_file(tmp_path):
    root = _write_ladder(tmp_path, "rungs: [ not : valid : yaml ][")
    assert T.rung_verdict_lift("bakery", posture="earn_up", cabinet_root=root,
                               is_locked_fn=_LOCKED) is None


def test_lift_refuses_non_earn_up_posture(tmp_path):
    root = _write_ladder(tmp_path, _ladder_body("ive-done", granted="ive-done"))
    for posture in ("guardian", "sovereign", "", "EARN_UP"):
        assert T.rung_verdict_lift("bakery", posture=posture,
                                   cabinet_root=root,
                                   is_locked_fn=_LOCKED) is None
    # sanity: earn_up itself lifts.
    assert T.rung_verdict_lift("bakery", posture="earn_up", cabinet_root=root,
                               is_locked_fn=_LOCKED) == "notify_after"


def test_lift_is_per_lane(tmp_path):
    root = _write_ladder(
        tmp_path, _ladder_body("ive-done", lane="bakery", granted="ive-done"))
    assert T.rung_verdict_lift("bakery", posture="earn_up", cabinet_root=root,
                               is_locked_fn=_LOCKED) == "notify_after"
    # another lane: no grant for it AND no file rung for it ⇒ no lift.
    assert T.rung_verdict_lift("newsletter", posture="earn_up", cabinet_root=root,
                               is_locked_fn=_LOCKED) is None


def test_lift_fail_closed_on_broken_grant_read(tmp_path, monkeypatch):
    root = _write_ladder(tmp_path, _ladder_body("ive-done", granted="ive-done"))

    def boom(lane=None, *a, **k):
        raise RuntimeError("granted rows unreadable")

    monkeypatch.setattr(T, "current_rung", boom)
    assert T.rung_verdict_lift("bakery", posture="earn_up", cabinet_root=root,
                               is_locked_fn=_LOCKED) is None
