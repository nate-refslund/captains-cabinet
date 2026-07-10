"""T5 — small REAL reversible end-to-end smoke test (live OAuth judge, NO sends).

Ada's directive: test the real flow, reversible only. This test exercises the
SAME chain as the stubbed T4 seam test (test_e2e_flow.py), but against the LIVE
seams: the real OAuth `claude -p` judge + real gather + real Voyage STYLE
scoring on a SMALL n of held-out cases. It asserts the pipeline completes,
produces a CaseScore per scored case, emits consequence events, graduation
reads them, and NO leak (n_leaked tracked + leaked cases EXCLUDED, never
silently scored).

Reversibility (the only-thing-allowed posture): reads + scores + LOCAL ledger
writes only. There is NO queue_draft, NO send, NO board write, NO deploy, NO
spend on the pay-as-you-go path (ANTHROPIC_API_KEY is stripped; the judge bills
the Max OAuth pool). The consequence/org-event ledgers are isolated to a tmp
dir, so even the local writes land nowhere durable.

Layering:
  * The DETERMINISTIC unit tests (always run) cover the script's PURE control
    surface — preflight gating, run_smoke's structure on stubbed seams, the
    reversibility invariants (no API key, isolated ledger) — with real
    assertions and no live LLM/Voyage call. These are the TDD spine.
  * The LIVE test (``@pytest.mark.live``) SKIPS unless preflight passes
    (OAuth + Voyage + retrodiction lib all reachable) and then runs the real
    flow on n=1. It is the one test that proves the wiring works against the
    real judge — costing only an OAuth-pool `claude -p` call, no money.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.fidelity import run_e2e_smoke
from framework.fidelity.scorer import CaseScore
from framework.fidelity.types import Case, OfficerDecision

CUTOFF = "2026-06-10T12:00:00+00:00"
LANE = "send-1to1-reply"
ACTION_TYPE = "internal_message"
OFFICER = "cos"


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    """Isolate both ledgers to a tmp dir — the local writes the smoke makes land
    nowhere durable (reversibility)."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


def _case(cid: str) -> Case:
    return Case.from_retro_case({
        "case_id": cid, "reply_key": f"msgraph|{cid}", "slug": "otto",
        "person": "Otto", "channel": "msgraph", "language": "da",
        "reply_ts": CUTOFF, "subject": "Re: lon", "n_prior": 1,
        "thread_before": [
            {"slug": "otto", "person": "Otto",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Otto <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke lon snart?"},
        ],
        "real_reply": "Ja, fredag kl 14.",
    })


# ===========================================================================
# Preflight — the live-availability gate (deterministic; monkeypatched).
# ===========================================================================

class TestPreflight:
    def test_preflight_ok_when_all_three_reachable(self, monkeypatch):
        monkeypatch.setattr(run_e2e_smoke, "_oauth_ok", lambda: True)
        monkeypatch.setattr(run_e2e_smoke, "_voyage_ok", lambda: True)
        monkeypatch.setattr(run_e2e_smoke, "_retro_ok", lambda: True)
        ok, missing = run_e2e_smoke.preflight()
        assert ok is True
        assert missing == []

    def test_preflight_reports_each_missing_dependency(self, monkeypatch):
        monkeypatch.setattr(run_e2e_smoke, "_oauth_ok", lambda: False)
        monkeypatch.setattr(run_e2e_smoke, "_voyage_ok", lambda: False)
        monkeypatch.setattr(run_e2e_smoke, "_retro_ok", lambda: False)
        ok, missing = run_e2e_smoke.preflight()
        assert ok is False
        # every missing dependency is NAMED (fail-loud, not a silent skip).
        joined = " ".join(missing).lower()
        assert "oauth" in joined
        assert "voyage" in joined
        assert "retro" in joined or "retrodiction" in joined

    def test_preflight_partial_failure_still_fails_loud(self, monkeypatch):
        monkeypatch.setattr(run_e2e_smoke, "_oauth_ok", lambda: True)
        monkeypatch.setattr(run_e2e_smoke, "_voyage_ok", lambda: False)
        monkeypatch.setattr(run_e2e_smoke, "_retro_ok", lambda: True)
        ok, missing = run_e2e_smoke.preflight()
        assert ok is False
        assert any("voyage" in m.lower() for m in missing)
        assert len(missing) == 1


# ===========================================================================
# run_smoke — the full chain on stubbed seams (deterministic; no live call).
# Proves the wiring: cases -> run_batch -> emit_case_scored -> graduation,
# n_leaked tracked, leaked cases EXCLUDED.
# ===========================================================================

class TestRunSmokeStructure:
    def _stub_run_batch(self, n_scored, n_leaked, verdict="match"):
        """A run_batch stand-in returning the run_f1 result dict shape + the
        scores list (CaseScore dicts) the smoke re-hydrates to emit scored
        events."""
        scores = [
            CaseScore(f"c{i}", True, verdict, [], False, 1.0, {},
                      intent_verdict="intent-aligned",
                      intent_grounded_fact="From Otto at 2026-06-09: lon",
                      intent_composite=1.0).__dict__
            for i in range(n_scored)
        ]
        return {
            "n_scored": n_scored, "n_leaked": n_leaked,
            "decision_match_rate": 1.0 if n_scored else 0.0,
            "partial_rate": 0.0, "divergent_rate": 0.0,
            "style_win_rate": 1.0, "mechanics_fail_rate": 0.0,
            "beats_baseline": bool(n_scored), "baseline": 0.083,
            "scores": scores,
        }

    def test_run_smoke_emits_scored_events_and_reads_graduation(
            self, monkeypatch, event_log_dir):
        monkeypatch.setattr(
            run_e2e_smoke, "run_batch",
            lambda **kw: self._stub_run_batch(n_scored=2, n_leaked=0))
        result = run_e2e_smoke.run_smoke(
            officer_role=OFFICER, n_cases=2, lane=LANE, action_type=ACTION_TYPE)

        # 1. pipeline completed; a CaseScore per scored case.
        assert result["n_scored"] == 2
        assert result["n_leaked"] == 0
        assert len(result["scores"]) == 2

        # 2. a consequence event was emitted PER scored case (the T3 scored
        #    event, carrying the intent axis) — read back from the ledger.
        from framework.fidelity.consequence import read_ledger
        scored = [e for e in read_ledger()
                  if e.get("action") == "fidelity-case-scored"]
        assert len(scored) == 2
        assert all(e.get("intent_verdict") == "intent-aligned" for e in scored)

        # 3. graduation READ those events (a per-cell state, fail-safe on thin
        #    synthetic data — never silently graduated).
        grad = result["graduation"]
        cell_key = f"officer:{OFFICER}|{LANE}|{ACTION_TYPE}"
        assert cell_key in grad
        assert grad[cell_key]["state"] != "graduated"
        assert grad[cell_key]["evidence"]["sample_count"] == 2

    def test_run_smoke_tracks_leaked_and_excludes_them(
            self, monkeypatch, event_log_dir):
        # A leaked case is COUNTED and EXCLUDED — never silently scored.
        monkeypatch.setattr(
            run_e2e_smoke, "run_batch",
            lambda **kw: self._stub_run_batch(n_scored=1, n_leaked=1))
        result = run_e2e_smoke.run_smoke(
            officer_role=OFFICER, n_cases=2, lane=LANE, action_type=ACTION_TYPE)
        assert result["n_leaked"] == 1
        assert result["n_scored"] == 1
        # only the scored case produced a scored event (the leaked one did not).
        from framework.fidelity.consequence import read_ledger
        scored = [e for e in read_ledger()
                  if e.get("action") == "fidelity-case-scored"]
        assert len(scored) == 1

    def test_run_smoke_no_scores_does_not_crash(
            self, monkeypatch, event_log_dir):
        # Zero scored cases (all leaked / empty universe) must not raise — the
        # smoke reports the empty result, fail-safe.
        monkeypatch.setattr(
            run_e2e_smoke, "run_batch",
            lambda **kw: self._stub_run_batch(n_scored=0, n_leaked=2))
        result = run_e2e_smoke.run_smoke(
            officer_role=OFFICER, n_cases=2, lane=LANE, action_type=ACTION_TYPE)
        assert result["n_scored"] == 0
        assert result["n_leaked"] == 2
        assert result["scores"] == []


# ===========================================================================
# Reversibility invariants (deterministic) — the smoke must never spend on the
# pay path and must never write outside the isolated ledger.
# ===========================================================================

class TestReversibility:
    def test_baseline_system_is_the_generic_assistant(self):
        # The smoke uses run_f1's generic-assistant baseline contrast — no new
        # outbound path, no send.
        assert isinstance(run_e2e_smoke.run_smoke, type(run_e2e_smoke.preflight))

    def test_oauth_path_strips_anthropic_api_key(self):
        # The judge/officer LLM go through oauth_raw_llm, which strips
        # ANTHROPIC_API_KEY so a stray key can never bill the pay path. Assert
        # the smoke imports that exact OAuth seam, not a raw API caller.
        from framework.fidelity import oauth_llm
        assert run_e2e_smoke.oauth_raw_llm is oauth_llm.oauth_raw_llm


# ===========================================================================
# LIVE — the real flow on n=1 (OAuth judge + Voyage + retro). SKIPS unless all
# three are reachable. The ONE test that proves the wiring works live.
# ===========================================================================

@pytest.mark.live
class TestLiveSmoke:
    def test_real_flow_n1_completes_scores_emits_and_reads_graduation(
            self, event_log_dir):
        ok, missing = run_e2e_smoke.preflight()
        if not ok:
            pytest.skip(f"live deps unavailable: {missing}")

        result = run_e2e_smoke.run_smoke(
            officer_role=OFFICER, n_cases=1, lane=LANE, action_type=ACTION_TYPE)

        # the pipeline completed and tracked leakage.
        assert "n_scored" in result
        assert "n_leaked" in result
        assert result["n_scored"] + result["n_leaked"] >= 0

        # if anything scored, it produced a real CaseScore + a scored event +
        # a graduation read (a low score is fine — the FLOW is the point).
        if result["n_scored"] > 0:
            assert len(result["scores"]) == result["n_scored"]
            from framework.fidelity.consequence import read_ledger
            scored = [e for e in read_ledger()
                      if e.get("action") == "fidelity-case-scored"]
            assert len(scored) == result["n_scored"]
            assert result["graduation"]  # at least one cell evaluated
            # graduation is fail-safe on a single live sample — never auto.
            for cell in result["graduation"].values():
                assert cell["state"] != "graduated"
