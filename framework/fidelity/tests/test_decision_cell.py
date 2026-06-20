"""Decision cell (F3-intent) tests — docs/fidelity-decision-cell-design-2026-06-20.md.

Exercises the three pieces with stubbed LLMs (no network): the extractor's
leak-scan + cache, the runner's ground-truth leak boundary, and the scorer's
verdict→composite. The load-bearing safety property is in
test_clone_never_sees_ground_truth: the clone is driven on the dilemma +
identity ONLY and must never receive Nate's actual decision/why.
"""

from __future__ import annotations

import json

import pytest

from framework.fidelity import decision_cell
from framework.fidelity.types import DecisionCase

_NOTE = """---
type: decision
date: 2026-05-28
detected_at: 2026-05-28T17:47:07Z
app: Claude Code (Terminal)
candidate_id: 20260528-1947-approve-with-db-backup
---

# Decision — 2026-05-28

## Situation (detected)
You greenlit a potentially risky DB operation that Claude had flagged, noting you'd backed up prod.

## Why / reasoning (Nate)
I prefer fast autonomous execution with a safety net over slow approval gates.
"""


class TestParseNote:
    def test_parses_frontmatter_and_sections(self):
        p = decision_cell._parse_note(_NOTE)
        assert p["detected_at"] == "2026-05-28T17:47:07Z"
        assert p["app"] == "Claude Code (Terminal)"
        assert "risky DB operation" in p["situation"]
        assert "fast autonomous execution" in p["why"]


class TestExtractor:
    def _dir(self, tmp_path, text=_NOTE):
        (tmp_path / "note.md").write_text(text, encoding="utf-8")
        return tmp_path

    def test_clean_case_admitted(self, tmp_path):
        clean = json.dumps({
            "dilemma": "Claude flagged a potentially risky DB operation and "
                       "asked whether to proceed. What should Nate do?",
            "decision": "Greenlight it and proceed",
            "why": "prefers fast autonomous execution with a safety net"})

        def stub(payload, system):
            return clean

        cases = decision_cell.extract_decision_cases(
            decisions_dir=self._dir(tmp_path), llm=stub,
            cache_path=tmp_path / "cache.json")
        assert len(cases) == 1
        c = cases[0]
        assert c.detected_at == "2026-05-28T17:47:07Z"
        assert "proceed" in c.dilemma
        assert c.decision and c.why
        # ground truth must NOT be embedded in the dilemma
        assert "greenlight" not in c.dilemma.lower()

    def test_leaking_dilemma_dropped(self, tmp_path):
        # The LLM (mis)returns a dilemma that reveals the choice -> must drop.
        leak = json.dumps({
            "dilemma": "Nate greenlit and proceeded with the risky migration "
                       "operation, approving the proceed after backup.",
            "decision": "greenlit proceeded approving migration operation backup",
            "why": "autonomy"})

        cases = decision_cell.extract_decision_cases(
            decisions_dir=self._dir(tmp_path), llm=lambda p, s: leak,
            cache_path=tmp_path / "cache.json")
        assert cases == []

    def test_cache_prevents_rellm(self, tmp_path):
        d = self._dir(tmp_path)
        cache = tmp_path / "cache.json"
        good = json.dumps({"dilemma": "Should Nate proceed with the flagged op?",
                           "decision": "yes proceed", "why": "autonomy net"})
        decision_cell.extract_decision_cases(
            decisions_dir=d, llm=lambda p, s: good, cache_path=cache)

        def explode(p, s):
            raise AssertionError("cache miss — LLM must not be called again")

        cases = decision_cell.extract_decision_cases(
            decisions_dir=d, llm=explode, cache_path=cache)
        assert len(cases) == 1


class TestRunnerLeakBoundary:
    def _case(self):
        return DecisionCase(
            case_id="c1", detected_at="2026-05-28T17:47:07Z", app="x",
            dilemma="Claude flagged a risky DB op and asked whether to proceed.",
            decision="Greenlight the migration and approve it",
            why="prefers autonomous velocity with a manual backup safety net")

    class _FakeBrain:
        def __init__(self):
            self.lessons_before_ts = None

        def voice_profile(self):
            return "terse, decisive"

        def nate_model_patterns(self):
            return "gives AI max autonomy"

        def drafting_lessons(self, before_ts):
            self.lessons_before_ts = before_ts
            return "lesson X"

    def test_clone_never_sees_ground_truth(self):
        case = self._case()
        seen = {}

        def capturing_llm(user, system):
            seen["user"] = user
            seen["system"] = system
            return json.dumps({"decision": "proceed", "why": "velocity"})

        brain = self._FakeBrain()
        out = decision_cell.run_decision_case(case, llm=capturing_llm, brain=brain)
        blob = (seen["user"] + seen["system"]).lower()
        # the held-out ground truth must NOT reach the clone
        assert "greenlight the migration" not in blob
        assert "manual backup safety net" not in blob
        # the dilemma + identity DID reach it
        assert "risky db op" in blob
        assert "max autonomy" in blob
        # lessons date-filtered at the decision cutoff
        assert brain.lessons_before_ts == "2026-05-28T17:47:07Z"
        assert out == {"decision": "proceed", "why": "velocity"}

    def test_non_json_clone_output_degrades(self):
        case = self._case()
        out = decision_cell.run_decision_case(
            case, llm=lambda u, s: "I would just proceed.",
            brain=self._FakeBrain())
        assert out["decision"] == "I would just proceed."
        assert out["why"] == ""


class TestScorer:
    def _case(self):
        return DecisionCase(
            case_id="c1", detected_at="t", app="x", dilemma="d",
            decision="proceed", why="velocity")

    def test_verdicts_and_composite(self):
        def judge(payload, system, max_tokens=300):
            return {"decision_verdict": "match",
                    "intent_verdict": "intent-aligned", "rationale": "ok"}

        r = decision_cell.score_decision_case(
            self._case(), {"decision": "proceed", "why": "velocity"}, judge=judge)
        assert r["decision_verdict"] == "match"
        assert r["intent_verdict"] == "intent-aligned"
        assert r["composite"] == 1.0

    def test_unparseable_judge_degrades_to_empty(self):
        r = decision_cell.score_decision_case(
            self._case(), {"decision": "x", "why": "y"},
            judge=lambda p, s, max_tokens=300: None)
        assert r["decision_verdict"] == ""
        assert r["intent_verdict"] == ""
        assert r["composite"] == 0.0  # composite("","") -> decision-only 0.0
