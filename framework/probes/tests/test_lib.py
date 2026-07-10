"""B2.2 probe framework lib — join, schema-valid emit, freshness guard."""
from __future__ import annotations

import pytest

from framework.acting import loop
from framework.fidelity.consequence import validate_consequence
from framework.probes import correlation as c
from framework.probes import lib


def _decided_proposal(cid, subject="bakery-ceo-thread", ts="2026-07-03T01:00:00Z"):
    """A proposal event that's been decided (approved) and carries the cid."""
    prop = loop.proposal_event(
        actor={"kind": "officer", "id": "bakery-ceo"}, lane="feature-impl",
        subject=subject, ts=ts, refs=[c.ref_for(cid)])
    prop["proposal"]["decision"] = "approved"
    prop["proposal"]["decided_at"] = ts
    return prop


def test_find_by_cid_hit_and_miss():
    cid = c.mint()
    rows = [_decided_proposal(cid), _decided_proposal(c.mint(), subject="other")]
    assert lib.find_proposal_by_cid(cid, rows=rows)["subject"] == "bakery-ceo-thread"
    assert lib.find_proposal_by_cid(c.mint(), rows=rows) is None
    assert lib.find_proposal_by_cid("not-a-cid", rows=rows) is None


def test_find_returns_last_write():
    cid = c.mint()
    old = _decided_proposal(cid, ts="2026-07-03T01:00:00Z")
    new = _decided_proposal(cid, ts="2026-07-03T01:00:00Z")
    new["outcome"] = {"status": "ok", "evidence": "prior"}
    rows = [old, new]
    assert "outcome" in lib.find_proposal_by_cid(cid, rows=rows)  # the later one


def test_emit_ok_is_schema_valid_and_carries_probe_meta():
    cid = c.mint()
    rows = [_decided_proposal(cid)]
    emitted = []
    r = lib.emit_outcome(cid=cid, status="ok", probe_status="ci_green",
                         source="github", confidence="high",
                         evidence="PR #42 merged, checks green",
                         rows=rows, emit=lambda **ev: emitted.append(ev))
    assert r["emitted"] is True
    ev = emitted[0]
    validate_consequence(ev)                     # schema-legal
    assert ev["outcome"] == {"status": "ok", "evidence": "PR #42 merged, checks green"}
    assert c.cid_from_refs(ev["refs"]) == cid     # join preserved
    assert "probe:github" in ev["refs"]
    assert "probe-status:ci_green" in ev["refs"]
    assert "confidence:high" in ev["refs"]


def test_emit_failed_requires_evidence():
    cid = c.mint()
    rows = [_decided_proposal(cid)]
    emitted = []
    lib.emit_outcome(cid=cid, status="failed", probe_status="deploy_error",
                     source="vercel", confidence="high", evidence="build failed",
                     rows=rows, emit=lambda **ev: emitted.append(ev))
    ev = emitted[0]
    validate_consequence(ev)
    assert ev["outcome"]["status"] == "failed" and ev["outcome"]["evidence"]


def test_emit_unknown_has_no_evidence():
    cid = c.mint()
    rows = [_decided_proposal(cid)]
    emitted = []
    lib.emit_outcome(cid=cid, status="unknown", probe_status="could_not_observe",
                     source="sentry", confidence="low",
                     evidence="ignored for unknown",
                     rows=rows, emit=lambda **ev: emitted.append(ev))
    ev = emitted[0]
    validate_consequence(ev)                     # unknown+evidence would raise
    assert ev["outcome"] == {"status": "unknown"}
    assert "evidence" not in ev["outcome"]
    assert "probe-status:could_not_observe" in ev["refs"]


def test_unattributable_cid_never_emits():
    emitted = []
    r = lib.emit_outcome(cid=c.mint(), status="ok", probe_status="merged",
                         source="github", confidence="high", evidence="x",
                         rows=[], emit=lambda **ev: emitted.append(ev))
    assert r["emitted"] is False and r["reason"] == "unattributable-cid"
    assert emitted == []                          # RT#3: no false attribution


def test_undecided_proposal_never_emits_outcome():
    cid = c.mint()
    pending = loop.proposal_event(actor={"kind": "officer", "id": "x"},
                                  lane="feature-impl", subject="s",
                                  ts="2026-07-03T01:00:00Z", refs=[c.ref_for(cid)])
    emitted = []
    r = lib.emit_outcome(cid=cid, status="ok", probe_status="merged",
                         source="github", confidence="high", evidence="x",
                         rows=[pending], emit=lambda **ev: emitted.append(ev))
    assert r["emitted"] is False and r["reason"] == "proposal-not-decided"
    assert emitted == []


def test_acted_actfirst_row_accepts_probe_outcome():
    """Guard update (lane-supply 2026-07-05): an act-first ACTED row —
    proposal {required: False, decision: None} FOREVER (binder_wire.
    acted_verdict_event:194) — IS executed, so probes must be able to land
    outcomes on it. The old decision-only guard blinded every probe to acted
    cards, starving the verifier's reconciliation loop."""
    cid = c.mint()
    acted = {"ts": "2026-07-05T01:00:00Z",
             "actor": {"kind": "officer", "id": "cos"}, "lane": "cos",
             "action": "action-card", "subject": "acted-card",
             "action_type": "task_create", "refs": [c.ref_for(cid)],
             "proposal": {"required": False, "decision": None},
             "outcome": {"status": "unknown"}}
    validate_consequence(acted)
    emitted = []
    r = lib.emit_outcome(cid=cid, status="failed", probe_status="rolled_back",
                         source="vercel", confidence="high",
                         evidence="production alias re-pointed (rollback)",
                         rows=[acted], emit=lambda **ev: emitted.append(ev))
    assert r["emitted"] is True
    ev = emitted[0]
    validate_consequence(ev)
    assert ev["outcome"]["status"] == "failed"
    # identity/cell fields inherited — the supersede lands on the acted row
    assert (ev["actor"], ev["lane"], ev["action_type"]) == (
        acted["actor"], "cos", "task_create")


def test_bad_status_or_confidence_raises():
    cid = c.mint()
    rows = [_decided_proposal(cid)]
    with pytest.raises(ValueError):
        lib.emit_outcome(cid=cid, status="green", probe_status="x", source="s",
                         confidence="high", rows=rows)
    with pytest.raises(ValueError):
        lib.emit_outcome(cid=cid, status="ok", probe_status="x", source="s",
                         confidence="certain", evidence="e", rows=rows)


def test_freshness_guard_silent_source_forces_unknown():
    r = lib.freshness_guard(observed=[], activity_expected=True, source="vercel")
    assert r["fresh"] is False and r["action"] == "emit-unknown"
    r2 = lib.freshness_guard(observed=None, activity_expected=True, source="ci")
    assert r2["fresh"] is False
    # no activity expected → empty is fine
    assert lib.freshness_guard(observed=[], activity_expected=False, source="x")["fresh"]
    # data present → fresh
    assert lib.freshness_guard(observed=[1], activity_expected=True, source="x")["fresh"]


def test_hc_ping_no_key_is_fail_open(monkeypatch):
    monkeypatch.delenv("HEALTHCHECKS_PING_KEY", raising=False)
    assert lib.hc_ping("probe-github") == "no-ping-key"
