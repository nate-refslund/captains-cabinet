"""Verdict-supply runner (run_verifier) — fixtured, no live ledger/systems.

What must never break (lane-supply 2026-07-05):
  1. claims come ONLY from executed act-first action cards (proposal.required
     == False on an action-card row) — pending/approved/expired cards and
     non-card rows are skipped with visible reasons;
  2. a landed HUMAN verdict is never machine-overwritten (flavor-A seniority);
  3. an acted row still outcome=unknown yields NO verdict (RT#4 pass-through);
  4. a ttl_ok-settled acted row (outcome ok, review absent — exactly what the
     undo-sweep leaves, binder_wire.acted_verdict_event:216) becomes review
     confirmed / verdict_judge ON THE SAME (actor, lane, action_type) cell;
  5. a probe-failed acted row becomes review wrong / verdict_judge (demotion
     evidence);
  6. verdict_judge idempotence: unchanged classification re-emits nothing;
     a CHANGED machine outcome re-claims (machine corrects machine);
  7. dry-run writes nothing (collector emit) yet validates every event.
"""
from __future__ import annotations

from framework.fidelity.consequence import validate_consequence
from framework.probes import correlation as c
from framework.probes import run_verifier as rv


def _acted(cid, *, subject="cvr-task", lane="cos", action_type="task_create",
           outcome=None, review=None, ts="2026-07-05T01:00:00Z"):
    """An acted act-first action-card row exactly as run_action_lane.py:931-936
    emits it (+ optional supersede state the sweep/probes/binder would add)."""
    ev = {"ts": ts, "actor": {"kind": "officer", "id": "cos"}, "lane": lane,
          "action": "action-card", "subject": subject,
          "action_type": action_type, "refs": [c.ref_for(cid)],
          "proposal": {"required": False, "decision": None},
          "outcome": outcome or {"status": "unknown"}}
    if review:
        ev["review"] = review
    validate_consequence(ev)   # fixtures must be ledger-legal or the test lies
    return ev


def _pending(cid, subject="pending-card"):
    ev = {"ts": "2026-07-05T01:00:00Z", "actor": {"kind": "officer", "id": "cos"},
          "lane": "cos", "action": "action-card", "subject": subject,
          "refs": [c.ref_for(cid)],
          "proposal": {"required": True, "decision": None}}
    validate_consequence(ev)
    return ev


# --- derive_claims: selection + seniority -------------------------------------

def test_pending_and_no_cid_cards_are_skipped_visibly():
    cid = c.mint()
    no_cid = {"ts": "2026-07-03T17:42:12Z", "actor": {"kind": "officer", "id": "cos"},
              "lane": "Commitments", "action": "action-card",
              "subject": "first-night-card", "refs": [],
              "proposal": {"required": True, "decision": None}}
    d = rv.derive_claims([_pending(cid), no_cid])
    assert d["claims"] == []
    reasons = {s["reason"] for s in d["skipped"]}
    assert any(r.startswith("not-acted") for r in reasons)
    assert "no-cid" in reasons


def test_approved_card_is_not_claimed():
    # An approved card carries review verdict_human from the decision emit
    # (loop.outcome_event:214) — but even review-less approved shapes must not
    # be claimed: required=True means propose-first, not act-first-executed.
    cid = c.mint()
    ev = _pending(cid)
    ev["proposal"] = {"required": True, "decision": "approved",
                      "decided_at": "2026-07-05T02:00:00Z"}
    d = rv.derive_claims([ev])
    assert d["claims"] == [] and "not-acted" in d["skipped"][0]["reason"]


def test_human_review_is_senior_never_reclaimed():
    cid = c.mint()
    row = _acted(cid, outcome={"status": "ok", "evidence": "ttl-48h survived"},
                 review={"verdict": "confirmed", "source": "verdict_human"})
    d = rv.derive_claims([row])
    assert d["claims"] == []
    assert "human-reviewed" in d["skipped"][0]["reason"]


def test_unattributed_review_is_skipped_fail_safe():
    cid = c.mint()
    row = _acted(cid, outcome={"status": "ok", "evidence": "x"},
                 review={"verdict": "confirmed"})   # legacy: no source
    d = rv.derive_claims([row])
    assert d["claims"] == [] and "unattributed-review" in d["skipped"][0]["reason"]


def test_judge_review_unchanged_is_idempotent_skip():
    cid = c.mint()
    row = _acted(cid, outcome={"status": "ok", "evidence": "ttl-48h survived"},
                 review={"verdict": "confirmed", "source": "verdict_judge"})
    d = rv.derive_claims([row])
    assert d["claims"] == [] and "already-reconciled" in d["skipped"][0]["reason"]


def test_judge_review_reclaims_when_machine_outcome_changed():
    # Verifier confirmed while outcome=ok; a later probe superseded the row to
    # failed → the recorded confirmed now disagrees → machine corrects machine.
    cid = c.mint()
    row = _acted(cid, outcome={"status": "failed", "evidence": "probe:rolled_back"},
                 review={"verdict": "confirmed", "source": "verdict_judge"})
    d = rv.derive_claims([row])
    assert d["claims"] == [{"cid": cid, "claimed": "done"}]


# --- run(): the full reconciliation ------------------------------------------

def test_acted_unknown_outcome_yields_no_verdict():
    # RT#4 pass-through: acted but not yet TTL-swept/probed → could-not-observe.
    cid = c.mint()
    res = rv.run(rows=[_acted(cid)], dry_run=True, now="2026-07-05T03:00:00Z")
    assert res["would_write"] == 0
    assert res["verify_skipped"][0]["reason"] == "could-not-observe"


def test_ttl_ok_row_confirms_on_the_same_gate_cell():
    # The keystone path: undo-sweep left outcome=ok + review ABSENT
    # (binder_wire.acted_verdict_event:216) → verifier emits verdict_judge
    # confirmed ON the row's own (actor, lane, action_type) cell.
    cid = c.mint()
    row = _acted(cid, lane="bakery-ceo", action_type="task_create",
                 outcome={"status": "ok",
                          "evidence": "ttl-48h survived; artifact intact"})
    res = rv.run(rows=[row], dry_run=True, now="2026-07-05T03:00:00Z")
    assert res["would_write"] == 1
    em = res["emitted"][0]
    assert em["verdict"] == "confirmed" and em["demote"] is False
    assert em["cell"] == {"actor": "officer:cos", "lane": "bakery-ceo",
                          "action_type": "task_create"}
    ev = res["collected_events"][0]
    validate_consequence(ev)
    assert ev["review"] == {"verdict": "confirmed", "source": "verdict_judge",
                            "reviewed_at": "2026-07-05T03:00:00Z"}
    # cell key fields inherited unchanged — the gate reads this exact tuple
    assert (ev["actor"], ev["lane"], ev["action_type"]) == (
        {"kind": "officer", "id": "cos"}, "bakery-ceo", "task_create")


def test_probe_failed_row_becomes_wrong_verdict_judge():
    cid = c.mint()
    row = _acted(cid, outcome={"status": "failed", "evidence": "probe:deploy_error"})
    res = rv.run(rows=[row], dry_run=True, now="2026-07-05T03:00:00Z")
    em = res["emitted"][0]
    assert (em["verdict"], em["kind"], em["demote"]) == ("wrong", "contradiction", False)
    ev = res["collected_events"][0]
    assert ev["review"]["verdict"] == "wrong"
    assert ev["review"]["source"] == "verdict_judge"


def test_fabrication_unreachable_from_acted_scope():
    # Every acted emit carries outcome{status:unknown} (run_action_lane:933),
    # so machine=="none" (the fabrication precondition) cannot arise from rows
    # this runner selects — pin that the unknown shape skips, never demotes.
    cid = c.mint()
    res = rv.run(rows=[_acted(cid)], dry_run=True)
    assert res["emitted"] == []
    assert all(not e.get("demote") for e in res["emitted"])


def test_dry_run_never_calls_the_real_emitter(monkeypatch):
    # Belt-and-braces: even if the ledger env were live, dry-run must not
    # touch emit_consequence.
    import framework.fidelity.consequence as cq
    calls = []
    monkeypatch.setattr(cq, "emit_consequence",
                        lambda **ev: calls.append(ev))
    cid = c.mint()
    row = _acted(cid, outcome={"status": "ok", "evidence": "ttl"})
    res = rv.run(rows=[row], dry_run=True)
    assert res["would_write"] == 1 and calls == []


def test_live_mode_gated_on_probes_enabled(monkeypatch, capsys):
    monkeypatch.delenv("CABINET_PROBES_ENABLED", raising=False)
    assert rv.main([]) == 0
    assert "disabled" in capsys.readouterr().out
