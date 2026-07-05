"""Tests — framework/fidelity/regression_gate.py (flywheel step 2).

The gate's contract under test: PASS iff no frozen case regresses AND >=1
improves; every non-evaluable situation (empty corpus, coverage hole, type
junk, malformed corpus, IO error) is a NO-VERDICT — never a spurious pass
(Corridor fail-safe invariant). Pure-function tests + the file-driven path.
"""

from __future__ import annotations

import json

import pytest

from framework.fidelity.regression_corpus_lib import extract_corrections, write_corpus
from framework.fidelity.regression_gate import (
    OUTCOME_FAIL,
    OUTCOME_NO_VERDICT,
    OUTCOME_PASS,
    CorpusError,
    corpus_case_ids,
    evaluate_gate,
    gate_from_files,
    load_corpus,
)

IDS = ["case-a", "case-b", "case-c"]


# ---------------------------------------------------------------------------
# the predicate — decision table
# ---------------------------------------------------------------------------

def test_pass_requires_zero_regressions_and_one_improvement():
    baseline = {"case-a": True, "case-b": False, "case-c": False}
    candidate = {"case-a": True, "case-b": True, "case-c": False}
    res = evaluate_gate(IDS, baseline, candidate)
    assert res.outcome == OUTCOME_PASS
    assert res.passed is True
    assert res.improved == ["case-b"]
    assert res.regressed == []
    assert res.checked == 3


def test_any_regression_fails_even_with_improvements():
    baseline = {"case-a": True, "case-b": False, "case-c": True}
    candidate = {"case-a": True, "case-b": True, "case-c": False}
    res = evaluate_gate(IDS, baseline, candidate)
    assert res.outcome == OUTCOME_FAIL
    assert res.passed is False
    assert res.regressed == ["case-c"]
    assert res.improved == ["case-b"]  # evidence kept for diagnosis


def test_flat_candidate_fails_no_improvement():
    same = {"case-a": True, "case-b": False, "case-c": True}
    res = evaluate_gate(IDS, same, dict(same))
    assert res.outcome == OUTCOME_FAIL
    assert "no frozen case improved" in res.reasons[0]


def test_empty_corpus_is_no_verdict_never_pass():
    res = evaluate_gate([], {}, {})
    assert res.outcome == OUTCOME_NO_VERDICT
    assert res.passed is False


def test_missing_coverage_is_no_verdict():
    baseline = {"case-a": True, "case-b": False}          # case-c missing
    candidate = {"case-a": True, "case-b": True, "case-c": True}
    res = evaluate_gate(IDS, baseline, candidate)
    assert res.outcome == OUTCOME_NO_VERDICT
    assert "baseline missing 1" in res.reasons[0]

    res2 = evaluate_gate(IDS, candidate, baseline)        # other side
    assert res2.outcome == OUTCOME_NO_VERDICT
    assert "candidate missing 1" in res2.reasons[0]


def test_non_bool_result_is_no_verdict():
    baseline = {"case-a": True, "case-b": False, "case-c": 0.7}   # score junk
    candidate = {"case-a": True, "case-b": True, "case-c": True}
    res = evaluate_gate(IDS, baseline, candidate)
    assert res.outcome == OUTCOME_NO_VERDICT

    baseline2 = {"case-a": True, "case-b": False, "case-c": True}
    candidate2 = {"case-a": True, "case-b": "true", "case-c": True}  # string
    assert evaluate_gate(IDS, baseline2, candidate2).outcome == OUTCOME_NO_VERDICT


def test_extra_non_frozen_ids_are_ignored():
    baseline = {"case-a": True, "case-b": False, "case-c": True, "extra": False}
    candidate = {"case-a": True, "case-b": True, "case-c": True, "extra": False}
    res = evaluate_gate(IDS, baseline, candidate)
    assert res.outcome == OUTCOME_PASS  # 'extra' neither helps nor hurts


def test_to_dict_carries_the_full_verdict():
    res = evaluate_gate(IDS,
                        {"case-a": True, "case-b": False, "case-c": True},
                        {"case-a": True, "case-b": True, "case-c": True})
    d = res.to_dict()
    assert d["outcome"] == OUTCOME_PASS and d["passed"] is True
    assert d["improved"] == ["case-b"] and d["checked"] == 3


# ---------------------------------------------------------------------------
# corpus loading strictness
# ---------------------------------------------------------------------------

def _seed_corpus(tmp_path):
    """A real 2-case corpus via the actual harvest+write path."""
    rows = [
        {"ts": "2026-07-03T20:43:15Z",
         "actor": {"kind": "officer", "id": "officer:cos"},
         "lane": "nate", "action": "action-card", "subject": f"s-{i}",
         "refs": [],
         "proposal": {"required": True, "decision": "edited",
                      "decided_at": "2026-07-03T21:07:40Z"},
         "outcome": {"status": "ok", "evidence": "captain edited the draft"},
         "review": {"verdict": "wrong", "source": "verdict_human"}}
        for i in range(2)
    ]
    write_corpus(extract_corrections(ledger=rows), corpus_dir=tmp_path)
    return corpus_case_ids(tmp_path)


def test_load_corpus_roundtrip(tmp_path):
    ids = _seed_corpus(tmp_path)
    cases = load_corpus(tmp_path)
    assert [c["case_id"] for c in cases] == ids == sorted(ids)
    assert len(cases) == 2


def test_load_corpus_missing_dir_is_honest_empty(tmp_path):
    assert load_corpus(tmp_path / "nope") == []


def test_load_corpus_refuses_id_filename_drift(tmp_path):
    ids = _seed_corpus(tmp_path)
    victim = tmp_path / "cases" / f"{ids[0]}.json"
    body = json.loads(victim.read_text())
    body["case_id"] = "case-deadbeefdeadbeef"
    victim.write_text(json.dumps(body))
    with pytest.raises(CorpusError):
        load_corpus(tmp_path)


def test_load_corpus_refuses_bad_format_and_junk(tmp_path):
    ids = _seed_corpus(tmp_path)
    victim = tmp_path / "cases" / f"{ids[0]}.json"
    body = json.loads(victim.read_text())
    body["case_format"] = 99
    victim.write_text(json.dumps(body))
    with pytest.raises(CorpusError):
        load_corpus(tmp_path)
    victim.write_text("{ not json")
    with pytest.raises(CorpusError):
        load_corpus(tmp_path)


# ---------------------------------------------------------------------------
# file-driven path — never raises, errors are no_verdict
# ---------------------------------------------------------------------------

def test_gate_from_files_happy_path(tmp_path):
    ids = _seed_corpus(tmp_path)
    base = tmp_path / "base.json"
    cand = tmp_path / "cand.json"
    base.write_text(json.dumps({ids[0]: False, ids[1]: True}))
    cand.write_text(json.dumps({ids[0]: True, ids[1]: True}))
    res = gate_from_files(base, cand, corpus_dir=tmp_path)
    assert res.outcome == OUTCOME_PASS
    assert res.improved == [ids[0]]


def test_gate_from_files_missing_file_is_no_verdict(tmp_path):
    _seed_corpus(tmp_path)
    res = gate_from_files(tmp_path / "absent.json", tmp_path / "absent2.json",
                          corpus_dir=tmp_path)
    assert res.outcome == OUTCOME_NO_VERDICT
    assert res.passed is False
    assert "gate error" in res.reasons[0]


def test_gate_from_files_malformed_corpus_is_no_verdict(tmp_path):
    ids = _seed_corpus(tmp_path)
    (tmp_path / "cases" / f"{ids[0]}.json").write_text("{ nope")
    base = tmp_path / "base.json"
    cand = tmp_path / "cand.json"
    base.write_text(json.dumps({i: True for i in ids}))
    cand.write_text(json.dumps({i: True for i in ids}))
    res = gate_from_files(base, cand, corpus_dir=tmp_path)
    assert res.outcome == OUTCOME_NO_VERDICT


def test_gate_from_files_non_object_results_are_no_verdict(tmp_path):
    _seed_corpus(tmp_path)
    base = tmp_path / "base.json"
    cand = tmp_path / "cand.json"
    base.write_text(json.dumps([1, 2, 3]))   # a list, not {case_id: bool}
    cand.write_text(json.dumps({}))
    res = gate_from_files(base, cand, corpus_dir=tmp_path)
    assert res.outcome == OUTCOME_NO_VERDICT
    assert "flat JSON objects" in res.reasons[0]
