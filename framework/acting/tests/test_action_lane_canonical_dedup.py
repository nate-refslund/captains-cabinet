"""propose_actions must drop re-worded duplicates via canonical-ref overlap.

Drives the REAL pure core with a fixture llm; covered_evidence carries a
PRIOR run's annotated evidence string (as read back from ledger refs), the
new proposal cites the same commitment with a different annotation and a
fresh subject_hint — the exact 2026-07-07 testament pattern."""
import json

from framework.acting import action_lane


def _llm_returning(proposals):
    def llm(system, user):
        return json.dumps({"proposals": proposals})
    return llm


PRIOR_RUN_EVIDENCE = ("6-Commitments/owed_to_nate/cmt-fca6836e2844.md — "
                      "'Fredag den 10 juli klokken 14:50, Retten i Kolding'; reminder_set: false")

REWORDED_PROPOSAL = {
    "situation": "Testament signing Friday needs a calendar block.",
    "subject_hint": "will-signing-kolding-fresh-wording",   # drifted slug
    "lane": "personal",
    "urgency": "ping-now",
    "confidence": 0.9,
    "injection_suspect": False,
    "direction_fit": {"direction": "personal"},
    "evidence": ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Solveig booked Kolding courthouse"],
    "steps": [{"kind": "reminder_create", "title": "Testament signing",
               "payload": {"title": "t", "due_iso": "2026-07-10T14:50:00+02:00"}}],
}

UNRELATED_PROPOSAL = {
    "situation": "EC connection details arrive today and need a chase block.",
    "subject_hint": "chase-ec-connection-details",
    "lane": "polads",
    "urgency": "batch",
    "confidence": 0.8,
    "injection_suspect": False,
    "direction_fit": {"direction": "personal"},
    "evidence": ["6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — due 2026-07-08"],
    "steps": [{"kind": "reminder_create", "title": "Chase EC",
               "payload": {"title": "t", "due_iso": "2026-07-08T13:00:00Z"}}],
}


def _run(covered, proposals, log):
    return action_lane.propose_actions(
        "SIGNAL BUNDLE (fixture)", as_of="2026-07-08T10:00:00Z",
        llm=_llm_returning(proposals), decided_subjects=set(),
        open_subjects=set(), budget_left=8,
        covered_evidence=frozenset(covered), directions=None,
        suppress_log=log.append)


def test_reworded_duplicate_dropped_by_canonical_overlap():
    log = []
    out = _run([PRIOR_RUN_EVIDENCE], [REWORDED_PROPOSAL, UNRELATED_PROPOSAL], log)
    assert [p.subject for p in out] == ["chase-ec-connection-details"]
    assert any("evidence-overlap-canonical" in line for line in log)


def test_exact_string_check_still_fires_first():
    log = []
    dup = dict(REWORDED_PROPOSAL, evidence=[PRIOR_RUN_EVIDENCE])
    out = _run([PRIOR_RUN_EVIDENCE], [dup], log)
    assert out == []
    assert any("reason=evidence-overlap" in line and "canonical" not in line
               for line in log)


def test_refless_covered_evidence_never_suppresses():
    log = []
    out = _run(["a prose-only ledger ref with no ids"],
               [UNRELATED_PROPOSAL], log)
    assert len(out) == 1
