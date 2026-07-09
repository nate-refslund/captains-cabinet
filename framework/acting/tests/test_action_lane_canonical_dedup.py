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


def test_same_batch_duplicate_dropped():
    """One LLM response carrying two proposals for the same commitment must
    yield ONE card — accepted refs cover the rest of the batch (gauntlet
    finding: within-run dedup only checked prior-run refs)."""
    log = []
    second = dict(REWORDED_PROPOSAL,
                  subject_hint="a-completely-different-slug",
                  evidence=["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — third wording"])
    out = _run([], [REWORDED_PROPOSAL, second, UNRELATED_PROPOSAL], log)
    assert [p.subject for p in out] == ["will-signing-kolding-fresh-wording",
                                        "chase-ec-connection-details"]
    assert any("evidence-overlap-canonical" in line for line in log)


def test_path_only_overlap_gets_distinct_drop_reason():
    """Rolling digest-file paths (commits.md) are the audit-worthy suppression
    class — the drop reason must say so (P4 surfaces these)."""
    log = []
    prior = "9-Codebases/Toolbox/commits.md — commits cc49aa2920 flagged"
    prop = dict(UNRELATED_PROPOSAL,
                subject_hint="new-commits-md-situation",
                evidence=["9-Codebases/Toolbox/commits.md — commit ffffffffff broke prod"])
    out = _run([prior], [prop], log)
    assert out == []
    assert any("evidence-overlap-canonical-path" in line for line in log)


def test_same_batch_shared_source_note_yields_distinct_cards():
    """The other half of the batch split (review cp1 Medium): two DISTINCT
    situations grounded in ONE meeting note must BOTH present — path-grade
    refs deliberately do not accumulate within a batch."""
    log = []
    a = dict(UNRELATED_PROPOSAL, subject_hint="situation-one",
             evidence=["2-Meetings/2026-07-02-scrum.md — VIES autofill decision"])
    b = dict(UNRELATED_PROPOSAL, subject_hint="situation-two",
             evidence=["2-Meetings/2026-07-02-scrum.md — billing question raised"])
    out = _run([], [a, b], log)
    assert [p.subject for p in out] == ["situation-one", "situation-two"]
    assert not any("evidence-overlap-canonical" in line for line in log)


def test_id_grade_drop_reason_is_the_exact_string():
    """Pins the reason strings exactly (substring asserts let an inverted
    path_grade classification pass — review cp1 Medium)."""
    log = []
    out = _run([PRIOR_RUN_EVIDENCE], [REWORDED_PROPOSAL], log)
    assert out == []
    assert any(line.endswith("reason=evidence-overlap-canonical") for line in log)
    log2 = []
    prior = "9-Codebases/Toolbox/commits.md — commits cc49aa2920 flagged"
    prop = dict(UNRELATED_PROPOSAL, subject_hint="fresh-commits-situation",
                evidence=["9-Codebases/Toolbox/commits.md — new commit broke prod"])
    assert _run([prior], [prop], log2) == []
    assert any(line.endswith("reason=evidence-overlap-canonical-path")
               for line in log2)


def test_ninth_evidence_item_is_outside_identity():
    """Documents the [:8] evidence boundary at the propose seam: a covered ref
    appearing only as the 9th item carries no identity — the card presents."""
    log = []
    prop = dict(UNRELATED_PROPOSAL,
                subject_hint="nine-item-evidence-card",
                evidence=[f"filler note {i}" for i in range(8)]
                + ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md"])
    out = _run([PRIOR_RUN_EVIDENCE], [prop], log)
    assert len(out) == 1


def test_covered_window_env_parse_is_fail_safe(monkeypatch):
    """A bad CABINET_COVERED_EVIDENCE_WINDOW_D must fall back to the default,
    never crash the lane at import or silently disarm dedup via inf/nan
    (review cp1 Low-1)."""
    from framework.acting import run_action_lane as ral
    for bad in ("abc", "inf", "-inf", "nan", ""):
        monkeypatch.setenv("CABINET_COVERED_EVIDENCE_WINDOW_D", bad)
        assert ral._covered_window_days() == 14.0, bad
    monkeypatch.setenv("CABINET_COVERED_EVIDENCE_WINDOW_D", "0")
    assert ral._covered_window_days() == 0.0
    monkeypatch.setenv("CABINET_COVERED_EVIDENCE_WINDOW_D", "30")
    assert ral._covered_window_days() == 30.0
