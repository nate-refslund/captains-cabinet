"""B2.8 dual-source verifier — fixtured, no live LLM/ledger.

The verifier's authority claim is the whole point, so these tests pin: the RT#4
classification gate (upstream outage → NO verdict, never fabrication), the
deterministic reconciliation truth table, and that a dissenting advisory can
NEVER flip the deterministic verdict."""
from __future__ import annotations

from framework.acting import loop
from framework.fidelity.consequence import DIRECT_DEMOTE_REF, validate_consequence
from framework.probes import correlation as c
from framework.probes import verifier as v


def _decided(cid, subject="polads-ceo-feature"):
    p = loop.proposal_event(actor={"kind": "officer", "id": "polads-ceo"},
                            lane="feature-impl", subject=subject,
                            ts="2026-07-03T01:00:00Z", refs=[c.ref_for(cid)])
    p["proposal"]["decision"] = "approved"
    p["proposal"]["decided_at"] = "2026-07-03T01:00:00Z"
    return p


def _outcome_row(cid, status, subject="polads-ceo-feature"):
    """A probe outcome event carrying the cid (as the fleet would emit)."""
    p = _decided(cid, subject)
    p["outcome"] = ({"status": "unknown"} if status == "unknown"
                    else {"status": status, "evidence": f"probe:{status}"})
    return p


# --- pure classify: the RT#4 gate ceases evaluation --------------------------

def test_gate_unreachable_yields_no_verdict():
    r = v.classify_claim(claimed="success", outcomes=[], probes_reachable=False)
    assert r["verdict"] is None and r["kind"] == v.KIND_COULD_NOT_OBSERVE

def test_gate_all_unknown_yields_no_verdict_not_fabrication():
    # a success claim while the ONLY probe reading is could-not-observe → NO
    # verdict — must NOT be scored fabrication (the Vercel-outage case).
    r = v.classify_claim(claimed="success", outcomes=[{"status": "unknown"}],
                         probes_reachable=True)
    assert r["verdict"] is None and r["kind"] == v.KIND_COULD_NOT_OBSERVE
    assert r["demote"] is False


# --- pure classify: deterministic reconciliation truth table -----------------

def test_success_matches_ok_confirmed():
    r = v.classify_claim(claimed="deployed", outcomes=[{"status": "ok"}],
                         probes_reachable=True)
    assert (r["verdict"], r["kind"]) == ("confirmed", v.KIND_CONFIRMED)

def test_success_vs_failed_is_contradiction_wrong():
    r = v.classify_claim(claimed="success", outcomes=[{"status": "failed"}],
                         probes_reachable=True)
    assert (r["verdict"], r["kind"], r["demote"]) == ("wrong", v.KIND_CONTRADICTION, False)

def test_success_with_no_evidence_is_fabrication_demote():
    r = v.classify_claim(claimed="fixed", outcomes=[], probes_reachable=True)
    assert (r["verdict"], r["kind"], r["demote"]) == ("wrong", v.KIND_FABRICATION, True)

def test_failed_probe_beats_ok_probe_in_aggregate():
    # a clean deploy that later regressed: ANY failed dominates → success claim wrong
    r = v.classify_claim(claimed="success",
                         outcomes=[{"status": "ok"}, {"status": "failed"}],
                         probes_reachable=True)
    assert (r["verdict"], r["kind"]) == ("wrong", v.KIND_CONTRADICTION)

def test_honest_failure_report_confirmed():
    r = v.classify_claim(claimed="failed", outcomes=[{"status": "failed"}],
                         probes_reachable=True)
    assert (r["verdict"], r["kind"]) == ("confirmed", v.KIND_CONFIRMED)

def test_self_flag_uncertain_never_scored_wrong():
    r = v.classify_claim(claimed="not sure it worked", outcomes=[],
                         probes_reachable=True)
    assert (r["verdict"], r["kind"], r["demote"]) == ("unknown", v.KIND_HONEST_UNKNOWN, False)


# --- verify orchestration ----------------------------------------------------

def test_verify_emits_schema_valid_confirmed_with_markers():
    cid = c.mint()
    rows = [_outcome_row(cid, "ok")]
    emitted = []
    r = v.verify(claims=[{"cid": cid, "claimed": "deployed"}], rows=rows,
                 reviewed_at="2026-07-03T04:00:00Z",
                 emit=lambda **ev: emitted.append(ev))
    assert r["emitted"][0]["verdict"] == "confirmed"
    ev = emitted[0]
    validate_consequence(ev)
    assert ev["review"] == {"verdict": "confirmed", "reviewed_at": "2026-07-03T04:00:00Z"}
    assert "verdict-source:verdict_judge" in ev["refs"]
    assert "verdict-kind:confirmed" in ev["refs"]
    assert c.cid_from_refs(ev["refs"]) == cid          # join preserved


def test_verify_fabrication_emits_wrong_plus_direct_demote():
    cid = c.mint()
    rows = [_decided(cid)]                              # decided proposal, NO probe outcome
    emitted = []
    r = v.verify(claims=[{"cid": cid, "claimed": "deployed"}], rows=rows,
                 emit=lambda **ev: emitted.append(ev))
    ev = emitted[0]
    validate_consequence(ev)
    assert ev["review"]["verdict"] == "wrong"
    # pin the emitter↔consumer contract: the same constant graduation (B2.9) reads
    assert "verdict-kind:fabrication" in ev["refs"] and DIRECT_DEMOTE_REF in ev["refs"]
    assert r["emitted"][0]["demote"] is True


def test_advisory_dissent_never_flips_deterministic_verdict():
    cid = c.mint()
    rows = [_outcome_row(cid, "ok")]
    emitted = []
    # advisory screams "wrong"; deterministic says confirmed → confirmed WINS.
    r = v.verify(claims=[{"cid": cid, "claimed": "deployed"}], rows=rows,
                 advisory=lambda claim, outcomes: "wrong",
                 emit=lambda **ev: emitted.append(ev))
    assert r["emitted"][0]["verdict"] == "confirmed"          # not flipped
    ev = emitted[0]
    assert ev["review"]["verdict"] == "confirmed"
    assert "advisory-verdict:wrong" in ev["refs"]
    assert "advisory-agrees:false" in ev["refs"]              # dissent recorded, not obeyed


def test_advisory_exception_does_not_break_verdict():
    cid = c.mint()
    rows = [_outcome_row(cid, "ok")]
    emitted = []
    def boom(claim, outcomes):
        raise RuntimeError("haiku down")
    r = v.verify(claims=[{"cid": cid, "claimed": "deployed"}], rows=rows,
                 advisory=boom, emit=lambda **ev: emitted.append(ev))
    assert r["emitted"][0]["verdict"] == "confirmed"          # deterministic unaffected


def test_verify_could_not_observe_skips_no_emit():
    cid = c.mint()
    rows = [_outcome_row(cid, "unknown")]
    emitted = []
    r = v.verify(claims=[{"cid": cid, "claimed": "deployed"}], rows=rows,
                 probes_reachable=True, emit=lambda **ev: emitted.append(ev))
    assert emitted == [] and r["skipped"][0]["reason"] == v.KIND_COULD_NOT_OBSERVE


def test_verify_unattributable_cid_skipped():
    cid = c.mint()
    emitted = []
    r = v.verify(claims=[{"cid": cid, "claimed": "deployed"}], rows=[],  # no proposal
                 emit=lambda **ev: emitted.append(ev))
    assert emitted == [] and r["skipped"][0]["reason"] == "unattributable-cid"
