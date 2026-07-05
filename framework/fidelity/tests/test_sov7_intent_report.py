"""SOV-7 / D17 — intent_report: AGB headline, decision-match diagnostic,
per-identity segmentation.

Pure-reader tests (no scoring stack, no LLM) — they run on lib-less installs.
Rates follow no-silent-caps: unmeasured is a visible None, never 0.0/1.0.
"""

from __future__ import annotations

import json

from framework.fidelity import intent_report


def _rec(outcome=None, decision=None, intent=None, identity=None,
         leaked=False, error=None, case_id="c1"):
    rec = {"case_id": case_id, "channel": "msgraph", "leaked": leaked,
           "error": error, "decision_verdict": decision,
           "intent_verdict": intent, "outcome_verdict": outcome,
           "grounded_fact": None}
    if identity is not None:
        rec["identity_mode"] = identity
    return rec


class TestSummarizeAGBHeadline:
    def test_agb_rate_excludes_incomparable_and_error(self):
        recs = [
            _rec(outcome="as_good_or_better", decision="match"),
            _rec(outcome="as_good_or_better", decision="divergent"),
            _rec(outcome="as_good_or_better", decision="partial"),
            _rec(outcome="worse", decision="match"),
            _rec(outcome="incomparable", decision="match"),
            _rec(outcome="error", decision="match"),
        ]
        s = intent_report.summarize(recs)["overall"]
        assert s["agb_rate"] == 0.75  # 3 / (3 + 1); incomparable+error out
        assert s["outcome_counts"]["as_good_or_better"] == 3
        assert s["outcome_counts"]["worse"] == 1
        assert s["outcome_counts"]["incomparable"] == 1
        assert s["outcome_counts"]["error"] == 1

    def test_unmeasured_agb_is_visible_none(self):
        recs = [_rec(outcome="", decision="match"),
                _rec(outcome=None, decision="partial"),
                _rec(outcome="incomparable", decision="match")]
        s = intent_report.summarize(recs)["overall"]
        assert s["agb_rate"] is None  # no judged AGB/worse rows → unmeasured

    def test_decision_match_diagnostic(self):
        recs = [_rec(decision="match"), _rec(decision="match"),
                _rec(decision="partial"), _rec(decision="divergent")]
        s = intent_report.summarize(recs)["overall"]
        assert s["decision_match_rate"] == 0.5  # 2 / 4
        assert s["decision_counts"] == {"match": 2, "partial": 1,
                                        "divergent": 1}

    def test_intent_aligned_diagnostic_excludes_partial(self):
        recs = [_rec(intent="intent-aligned"), _rec(intent="intent-aligned"),
                _rec(intent="intent-partial"), _rec(intent="intent-divergent")]
        s = intent_report.summarize(recs)["overall"]
        assert s["intent_aligned_rate"] == 2 / 3
        assert s["intent_counts"]["intent-partial"] == 1

    def test_leaked_and_error_rows_counted_but_not_scored(self):
        recs = [_rec(outcome="as_good_or_better", decision="match"),
                _rec(leaked=True, outcome="as_good_or_better"),
                _rec(error="RuntimeError('x')", outcome="worse")]
        s = intent_report.summarize(recs)["overall"]
        assert s["n_recs"] == 3
        assert s["leaked"] == 1
        assert s["errors"] == 1
        # the leaked/error rows contribute NO verdict counts
        assert s["outcome_counts"]["as_good_or_better"] == 1
        assert s["outcome_counts"]["worse"] == 0


class TestIdentitySegmentation:
    def test_segments_by_identity_mode(self):
        recs = [
            _rec(outcome="as_good_or_better", identity="clone"),
            _rec(outcome="worse", identity="clone"),
            _rec(outcome="as_good_or_better", identity="agent"),
        ]
        s = intent_report.summarize(recs)
        assert set(s["identities"]) == {"clone", "agent"}
        assert s["identities"]["clone"]["agb_rate"] == 0.5
        assert s["identities"]["agent"]["agb_rate"] == 1.0

    def test_unstamped_rec_defaults_to_clone(self):
        """A pre-D17 rec (no identity_mode key) was measured under the clone
        default — it belongs to the clone baseline segment."""
        recs = [_rec(outcome="as_good_or_better"),  # unstamped
                _rec(outcome="worse", identity="agent")]
        s = intent_report.summarize(recs)
        assert s["identities"]["clone"]["n_recs"] == 1
        assert s["identities"]["agent"]["n_recs"] == 1


class TestRenderAndCLI:
    def test_render_headlines_agb(self):
        recs = [_rec(outcome="as_good_or_better", decision="match",
                     identity="clone")]
        text = intent_report.render(intent_report.summarize(recs))
        lines = text.splitlines()
        assert "AGB" in lines[1]           # headline right under the title
        assert "HEADLINE" in lines[1]
        assert "100%" in lines[1]
        assert "identity: clone" in text
        assert "diagnostic decision-match" in text

    def test_render_unmeasured_reads_unmeasured(self):
        text = intent_report.render(intent_report.summarize([_rec()]))
        assert "unmeasured" in text

    def test_load_recs_skips_malformed_lines(self, tmp_path):
        shard = tmp_path / "s.jsonl"
        shard.write_text(
            json.dumps(_rec(outcome="worse")) + "\n"
            + "NOT JSON AT ALL\n"
            + json.dumps(["not", "a", "dict"]) + "\n"
            + "\n"
            + json.dumps(_rec(outcome="as_good_or_better")) + "\n")
        recs = intent_report.load_recs([str(shard)])
        assert len(recs) == 2

    def test_cli_json_smoke(self, tmp_path, capsys):
        shard = tmp_path / "s.jsonl"
        shard.write_text(json.dumps(_rec(outcome="as_good_or_better",
                                         identity="agent")) + "\n")
        intent_report.main([str(shard), "--json"])
        out = json.loads(capsys.readouterr().out)
        assert out["overall"]["agb_rate"] == 1.0
        assert out["identities"]["agent"]["n_recs"] == 1

    def test_cli_text_smoke(self, tmp_path, capsys):
        shard = tmp_path / "s.jsonl"
        shard.write_text(json.dumps(_rec(outcome="worse")) + "\n")
        intent_report.main([str(shard)])
        assert "HEADLINE" in capsys.readouterr().out
