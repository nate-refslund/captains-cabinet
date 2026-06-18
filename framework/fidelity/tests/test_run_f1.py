from __future__ import annotations

import pytest

from framework.fidelity import run_f1, leakguard
from framework.fidelity.types import Case, OfficerDecision
from framework.fidelity.scorer import CaseScore


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)


CUTOFF = "2026-06-10T12:00:00+00:00"


def _case(cid):
    return Case.from_retro_case({
        "case_id": cid, "reply_key": cid, "slug": "ulrik", "person": "Ulrik",
        "channel": "msgraph", "language": "da", "reply_ts": CUTOFF,
        "subject": "s", "n_prior": 2,
        "thread_before": [{"date": "2026-06-09T00:00:00+00:00",
                           "direction": "received", "who": "Ulrik <u@x>",
                           "source": "msgraph", "text": "hej"}],
        "real_reply": "Ja.",
    })


class TestRunBatch:
    def test_clone_beats_baseline_when_mostly_match(self, monkeypatch):
        cases = [_case(f"c{i}") for i in range(5)]
        monkeypatch.setattr(run_f1, "build_cases",
                            lambda lane="send-1to1-reply", decision_type="reply",
                            n=24, window=None, people_dir=None: cases)
        runner = lambda case, role, emit_events=True: OfficerDecision("Ja.", "", [])
        baseline_llm = lambda payload, system, max_tokens=1500, model="claude-sonnet-4-6": "Generic."
        verdicts = ["match", "match", "match", "match", "divergent"]
        it = iter(verdicts)
        def scorer_fn(case, dec, baseline_draft, centroids, embedder=None, judge=None):
            v = next(it)
            return CaseScore(case.case_id, True, v, [], False,
                             {"match": 1.0, "partial": 0.5, "divergent": 0.0}[v], {})
        monkeypatch.setattr(run_f1, "author_centroid",
                            lambda exclude_keys=None: {"msgraph": [1.0]})
        res = run_f1.run_batch(runner=runner, scorer_fn=scorer_fn,
                               baseline_llm=baseline_llm)
        assert res["n_scored"] == 5
        assert res["n_leaked"] == 0
        assert res["decision_match_rate"] == pytest.approx(0.8)
        assert res["beats_baseline"] is True
        assert res["baseline"] == 0.083

    def test_leaked_cases_excluded_not_scored(self, monkeypatch):
        cases = [_case("c0"), _case("c1")]
        monkeypatch.setattr(run_f1, "build_cases",
                            lambda lane="send-1to1-reply", decision_type="reply",
                            n=24, window=None, people_dir=None: cases)
        monkeypatch.setattr(run_f1, "author_centroid",
                            lambda exclude_keys=None: {"msgraph": [1.0]})
        def runner(case, role, emit_events=True):
            if case.case_id == "c1":
                raise leakguard.LeakageDetectedError("leak")
            return OfficerDecision("Ja.", "", [])
        scorer_fn = lambda case, dec, baseline_draft, centroids, embedder=None, judge=None: \
            CaseScore(case.case_id, True, "match", [], False, 1.0, {})
        res = run_f1.run_batch(runner=runner, scorer_fn=scorer_fn,
                               baseline_llm=lambda *a, **k: "g")
        assert res["n_scored"] == 1
        assert res["n_leaked"] == 1
        assert res["decision_match_rate"] == 1.0

    def test_assert_beats_baseline_raises_when_below(self):
        with pytest.raises(AssertionError):
            run_f1.assert_beats_baseline({"decision_match_rate": 0.05})

    def test_assert_beats_baseline_passes_when_above(self):
        run_f1.assert_beats_baseline({"decision_match_rate": 0.5})  # no raise
