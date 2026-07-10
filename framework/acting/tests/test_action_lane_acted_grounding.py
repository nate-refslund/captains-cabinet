"""P2 acceptance at the propose seam (spec §8 P2): acted situations do not
re-propose; Captain-reversed acts stop suppressing; unknown world state still
proposes. Drives the REAL pure core with a fixture llm."""
import json

from framework.acting import action_lane
from framework.attention.acted_overlay import load_acted


def _llm_returning(proposals):
    def llm(system, user):
        return json.dumps({"proposals": proposals})
    return llm


DEED_PROPOSAL = {
    "situation": "Deed signing Friday needs a calendar block.",
    "subject_hint": "deed-signing-yet-another-wording",
    "lane": "personal",
    "urgency": "ping-now",
    "confidence": 0.9,
    "injection_suspect": False,
    "direction_fit": {"direction": "personal"},
    "evidence": ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — reminder_set: false"],
    "steps": [{"kind": "reminder_create", "title": "Deed signing",
               "payload": {"title": "t", "due_iso": "2026-07-10T14:50:00+02:00"}}],
}


def _run(proposals, log, *, covered=(), acted_refs=frozenset(),
         reversed_refs=frozenset()):
    return action_lane.propose_actions(
        "SIGNAL BUNDLE (fixture)", as_of="2026-07-08T10:00:00Z",
        llm=_llm_returning(proposals), decided_subjects=set(),
        open_subjects=set(), budget_left=8,
        covered_evidence=frozenset(covered),
        acted_refs=acted_refs, reversed_refs=reversed_refs,
        directions=None, suppress_log=log.append)


def _acted_view(reversed_=False):
    ledger = [{
        "action": "acted:reminder_create", "subject": "deed-signing",
        "ts": "2026-07-07T16:09:28Z",
        "refs": ["cabinet-proposal-id:aaaa1111",
                 "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — booked"]}]
    journal = [{"jid": "j1", "cid": "aaaa1111", "ts": "2026-07-07T16:09:28Z",
                "status": "reversed" if reversed_ else "executed",
                "reversed_at": "2026-07-07T18:00:00Z" if reversed_ else None}]
    return load_acted(ledger_rows=ledger, journal_rows=journal)


def test_acted_situation_does_not_repropose():
    """Spec P2 acceptance: acted deed situation → proposes nothing,
    with the distinct already-acted reason (end-to-end overlay → core)."""
    v = _acted_view()
    log = []
    out = _run([DEED_PROPOSAL], log,
               acted_refs=v["live_canonical"], reversed_refs=v["reversed_canonical"])
    assert out == []
    assert any(line.endswith("reason=already-acted") for line in log)


def test_captain_reversed_act_stops_suppressing():
    """Undo semantics: the SAME situation presents again after the Captain
    reverses the act — even though the acted ledger row still sits inside
    the covered window (reversed refs subtract from covered too)."""
    v = _acted_view(reversed_=True)
    log = []
    out = _run([DEED_PROPOSAL], log,
               covered=["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — booked"],
               acted_refs=v["live_canonical"], reversed_refs=v["reversed_canonical"])
    assert len(out) == 1
    assert out[0].subject == "deed-signing-yet-another-wording"


def test_reversed_situation_survives_verbatim_covered_match():
    """cp2 M1: the Captain-undone situation must re-present even when the
    LLM cites the covered evidence string BYTE-IDENTICALLY (the verbatim
    check fires before the canonical one)."""
    v = _acted_view(reversed_=True)
    verbatim = "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — booked"
    prop = dict(DEED_PROPOSAL, evidence=[verbatim])
    log = []
    out = _run([prop], log, covered=[verbatim],
               acted_refs=v["live_canonical"], reversed_refs=v["reversed_canonical"])
    assert len(out) == 1


def test_verbatim_drop_still_fires_without_reversal():
    verbatim = "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — booked"
    prop = dict(DEED_PROPOSAL, evidence=[verbatim])
    log = []
    out = _run([prop], log, covered=[verbatim])
    assert out == []
    assert any(line.endswith("reason=evidence-overlap") for line in log)


def test_unknown_world_state_still_proposes():
    """Probe-outage leg: no acted view at all (caller passes empties) —
    the card presents; nothing crashes."""
    log = []
    out = _run([DEED_PROPOSAL], log)
    assert len(out) == 1


def test_acted_check_wins_over_generic_covered_reason():
    """When a situation is both covered (prior card) and acted, the more
    specific already-acted reason is logged, not evidence-overlap-canonical."""
    v = _acted_view()
    log = []
    out = _run([DEED_PROPOSAL], log,
               covered=["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — prior card"],
               acted_refs=v["live_canonical"], reversed_refs=v["reversed_canonical"])
    assert out == []
    assert any(line.endswith("reason=already-acted") for line in log)
    assert not any("evidence-overlap-canonical" in line for line in log)
