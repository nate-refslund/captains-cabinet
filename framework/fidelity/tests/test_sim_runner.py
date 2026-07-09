"""SIE-9 — the sim RUNNER over the SIE-7 quarantine (W3, 2026-07-09).

The sim-harness foundation shipped the fences (SIE-7 chokepoint, A8 as-of
fence, fence_lib readers) but never the runner that uses them. These tests pin
the runner's fail-closed spine:

  * pre-flight refuses to spend a single officer drive unless BOTH halves of
    the quarantine agree (CABINET_SIM_MODE=1 AND a '-sim' ledger dir);
  * a quarantined batch produces sim-marked rows only, forces emit_scored=True
    (sim rows ARE the product) and writes an atomic summary INSIDE the
    quarantine dir;
  * post-run verification hard-fails on a contaminated dir (any live-shaped
    row) — a sim summary can never be produced over a dirty ledger.

All offline: injected fake runner/scorer/baseline, monkeypatched case builder
(same convention as test_run_f1.py).
"""
from __future__ import annotations

import json

import pytest

from framework.fidelity import run_f1, sim_runner
from framework.fidelity.sim_runner import (
    SimHarnessError,
    assert_sim_quarantine,
    run_sim_batch,
)
from framework.fidelity.types import Case, OfficerDecision
from framework.fidelity.scorer import CaseScore

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


def _arm_sim(monkeypatch, tmp_path):
    d = tmp_path / "events-sim"
    monkeypatch.setenv("CABINET_SIM_MODE", "1")
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return d


def _fake_pipeline(monkeypatch, n=2):
    cases = [_case(f"c{i}") for i in range(n)]
    monkeypatch.setattr(run_f1, "build_cases",
                        lambda lane="send-1to1-reply", decision_type="reply",
                        n=24, window=None, people_dir=None: cases)
    monkeypatch.setattr(run_f1, "author_centroid",
                        lambda exclude_keys=None: {"msgraph": [1.0]})
    runner = lambda case, role, emit_events=True, gather=None: \
        OfficerDecision("Ja.", "", [])
    scorer_fn = lambda case, dec, baseline_draft, centroids, embedder=None, \
        judge=None, intent_ctx=None: \
        CaseScore(case.case_id, True, "match", [], False, 1.0, {},
                  intent_verdict="intent-aligned")
    baseline_llm = lambda *a, **k: "Generic."
    return runner, scorer_fn, baseline_llm


class TestPreflight:
    def test_refuses_without_sim_mode(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events-sim"))
        with pytest.raises(SimHarnessError, match="CABINET_SIM_MODE"):
            assert_sim_quarantine()

    def test_refuses_without_ledger_dir(self, monkeypatch):
        monkeypatch.setenv("CABINET_SIM_MODE", "1")
        monkeypatch.delenv("CABINET_EVENT_LOG_DIR", raising=False)
        with pytest.raises(SimHarnessError, match="CABINET_EVENT_LOG_DIR unset"):
            assert_sim_quarantine()

    def test_refuses_non_sim_suffix_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CABINET_SIM_MODE", "1")
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
        with pytest.raises(SimHarnessError, match="-sim"):
            assert_sim_quarantine()

    def test_accepts_armed_quarantine(self, monkeypatch, tmp_path):
        d = _arm_sim(monkeypatch, tmp_path)
        assert assert_sim_quarantine() == d

    def test_run_sim_batch_spends_no_drives_when_unarmed(self, monkeypatch,
                                                         tmp_path):
        # The refusal must fire BEFORE any officer drive.
        monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
        calls = []
        monkeypatch.setattr(run_f1, "run_batch",
                            lambda *a, **k: calls.append(1) or {})
        with pytest.raises(SimHarnessError):
            run_sim_batch()
        assert calls == []


class TestQuarantinedBatch:
    def test_batch_lands_only_sim_rows_and_writes_summary(self, monkeypatch,
                                                          tmp_path):
        qdir = _arm_sim(monkeypatch, tmp_path)
        runner, scorer_fn, baseline_llm = _fake_pipeline(monkeypatch, n=2)

        s = run_sim_batch(officer_role="cos", n_cases=2, runner=runner,
                          scorer_fn=scorer_fn, baseline_llm=baseline_llm)

        assert s["sim"] is True
        assert s["quarantine_dir"] == str(qdir)
        assert s["n_scored"] == 2
        assert s["n_sim_rows"] >= 1  # emit_scored is FORCED on — rows landed
        # every row on disk is sim-stamped (the SIE-7 chokepoint held)
        rows = []
        for f in sorted(qdir.glob("consequence-events-*.jsonl")):
            rows += [json.loads(l) for l in f.read_text().splitlines() if l]
        assert rows and all(r.get("sim") is True for r in rows)
        # atomic summary artifact INSIDE the quarantine dir, no tmp residue
        out = list(qdir.glob("sim-batch-summary-*.json"))
        assert len(out) == 1 and s["summary_path"] == str(out[0])
        assert not list(qdir.glob("*.json.tmp"))
        assert json.loads(out[0].read_text())["sim"] is True

    def test_emit_scored_is_forced_on(self, monkeypatch, tmp_path):
        _arm_sim(monkeypatch, tmp_path)
        seen = {}
        monkeypatch.setattr(
            run_f1, "run_batch",
            lambda **k: seen.update(k) or
            {"n_scored": 0, "n_leaked": 0, "scores": []})
        run_sim_batch(n_cases=1, write_summary=False)
        assert seen["emit_scored"] is True
        assert seen["emit_events"] is True

    def test_contaminated_quarantine_dir_refuses_summary(self, monkeypatch,
                                                         tmp_path):
        qdir = _arm_sim(monkeypatch, tmp_path)
        qdir.mkdir(parents=True)
        # a live-shaped (unmarked) row somehow present inside the -sim dir
        (qdir / "consequence-events-2026-07-09.jsonl").write_text(json.dumps({
            "ts": "2026-07-09T08:00:00+00:00",
            "actor": {"kind": "officer", "id": "cos"},
            "lane": "polads", "action": "auto-closed-commitment",
            "subject": "thread-abc", "refs": ["msg-1"],
        }) + "\n")
        runner, scorer_fn, baseline_llm = _fake_pipeline(monkeypatch, n=1)
        with pytest.raises(SimHarnessError, match="live-shaped"):
            run_sim_batch(n_cases=1, runner=runner, scorer_fn=scorer_fn,
                          baseline_llm=baseline_llm)
        # and no summary artifact was produced over the dirty dir
        assert not list(qdir.glob("sim-batch-summary-*.json"))


class TestRunF1EnvKnobs:
    """W3 also made the D1 knobs reachable from the scheduled entry
    (run_f1.__main__ reads F1_WITH_INTENT / F1_EMIT_SCORED / F1_GATHER)."""

    @pytest.mark.parametrize("val,expected", [
        ("1", True), ("true", True), ("YES", True), ("on", True),
        ("", False), ("0", False), ("no", False), ("off", False),
    ])
    def test_env_flag_truthiness(self, monkeypatch, val, expected):
        monkeypatch.setenv("F1_X_PROBE", val)
        assert run_f1._env_flag("F1_X_PROBE") is expected

    def test_env_flag_unset_is_false(self, monkeypatch):
        monkeypatch.delenv("F1_X_PROBE", raising=False)
        assert run_f1._env_flag("F1_X_PROBE") is False
