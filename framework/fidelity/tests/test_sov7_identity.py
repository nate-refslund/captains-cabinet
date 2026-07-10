"""SOV-7 / D17-INT-3 — personal-agent identity_mode wiring.

run_case gains identity_mode ('clone' default — the A/A invariant holds until
the first AGB baseline is cut; 'agent' is an explicit opt-in that reframes the
system prompt via build_agent_eval_system). The clone arm stays byte-identical
as the diagnostic arm; the privacy fence + post-output leak scan hold under
BOTH identities. measure_intent stamps identity_mode into every rec and passes
it through to run_case.

Fakes throughout — no live brain / OAuth / network.
"""

from __future__ import annotations

import json
import sys

import pytest

from framework.fidelity.retro import retro_available

if not retro_available():  # flavor-A coupling — mirror the conftest guard
    pytest.skip("screenpipe retrodiction lib absent (flavor-A coupling)",
                allow_module_level=True)

from framework.fidelity import leakguard, officer_prompt, officer_runner, scorer
from framework.fidelity.officer_prompt import (
    build_agent_eval_system, build_clone_eval_system, build_eval_system,
    format_situation)
from framework.fidelity.scorer import CaseScore
from framework.fidelity.types import Case, OfficerDecision

CUTOFF = "2026-06-10T12:00:00+00:00"

_VOICE = "VOICE-SENTINEL: korte saetninger, ingen tankestreger."
_PATTERNS = "[PRIVATE ADA-MODEL] PATTERNS-SENTINEL: beslutter hurtigt."
_PERSON = "PERSON-SENTINEL: Otto, head baker & site lead."


@pytest.fixture(autouse=True)
def _synthetic_captain(monkeypatch):
    """Pin the captain identity to the synthetic fixture captain (Ada) so the
    AGENT/CLONE framing assertions are hermetic — never coupled to this
    deployment's instance/config captain_name value."""
    monkeypatch.setattr(officer_prompt, "captain_name", lambda: "Ada")


class _FakeBrain:
    def __init__(self):
        self.calls = []

    def voice_profile(self):
        self.calls.append("voice_profile")
        return _VOICE

    def model_patterns(self):
        self.calls.append("model_patterns")
        return _PATTERNS

    def drafting_lessons(self, before_ts):
        self.calls.append("drafting_lessons")
        return "LESSON-SENTINEL: two sentences max."

    def person_intel(self, slug):
        self.calls.append("person_intel")
        return _PERSON


def _case():
    return Case.from_retro_case({
        "case_id": "abc1234567", "reply_key": "k", "slug": "otto",
        "person": "Otto", "channel": "msgraph", "language": "da",
        "reply_ts": CUTOFF, "subject": "Re: lon", "n_prior": 1,
        "thread_before": [
            {"slug": "otto", "person": "Otto",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Otto <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke lon?"},
        ],
        "real_reply": "Ja, lad os tage det fredag.",
    })


def _capture_llm(draft="Ja, fredag passer fint."):
    seen = {}

    def fake(payload, system, max_tokens=1500, model="claude-sonnet-4-6"):
        seen["system"] = system
        seen["payload"] = payload
        return draft

    return fake, seen


def _fake_gather(case):
    return {
        "thread": case.thread_before,
        "commitments": [],
        "vault_hits": [],
        "person_static": _PERSON,
        "excluded": [],
    }


# ---------------------------------------------------------------------------
# run_case identity routing
# ---------------------------------------------------------------------------

class TestIdentityModeRouting:
    def test_default_is_clone_and_byte_identical(self):
        """No identity_mode == identity_mode='clone' == the pre-D17 clone-arm
        system prompt, byte for byte (the A/A invariant: adding the param
        changed nothing for existing callers)."""
        case = _case()
        fake_d, seen_d = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake_d,
                                gather=_fake_gather, brain=_FakeBrain())
        fake_e, seen_e = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake_e,
                                gather=_fake_gather, brain=_FakeBrain(),
                                identity_mode="clone")
        assert seen_d["system"] == seen_e["system"]
        assert seen_d["payload"] == seen_e["payload"]
        assert "CLONE IDENTITY" in seen_d["system"]
        assert "AGENT IDENTITY" not in seen_d["system"]

    def test_agent_mode_builds_agent_system(self):
        case = _case()
        fake, seen = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake, gather=_fake_gather,
                                brain=_FakeBrain(), identity_mode="agent")
        system = seen["system"]
        assert "AGENT IDENTITY" in system
        assert "ON ADA'S BEHALF" in system
        assert "CLONE IDENTITY" not in system
        # the same identity priors still inform the agent
        assert _VOICE in system
        assert _PATTERNS in system
        assert "LESSON-SENTINEL" in system
        assert _PERSON in system

    def test_unknown_identity_mode_raises_loudly(self):
        """A typo must never silently change what a shard measured."""
        case = _case()
        fake, _ = _capture_llm()
        brain = _FakeBrain()
        with pytest.raises(ValueError, match="identity_mode"):
            officer_runner.run_case(case, "chair", llm=fake,
                                    gather=_fake_gather, brain=brain,
                                    identity_mode="Agent")
        assert brain.calls == []  # rejected before any identity gather

    def test_identity_modes_vocabulary(self):
        assert officer_runner.IDENTITY_MODES == ("clone", "agent")

    def test_f1_arm_ignores_identity_mode(self):
        """gather=None (F1) carries no identity at all — identity_mode='agent'
        must not change the F1 system/payload bytes."""
        case = _case()
        fake, seen = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake,
                                identity_mode="agent")
        expected_system = (
            build_eval_system(case, "chair")
            + officer_runner.EVAL_MODE_RULES.format(cutoff_ts=case.cutoff_ts)
        )
        assert seen["system"] == expected_system
        assert seen["payload"] == format_situation(case)
        assert "AGENT IDENTITY" not in seen["system"]

    def test_leak_scan_still_runs_on_agent_arm(self):
        """The post-output cutoff fence holds under the agent identity — a
        draft echoing a post-cutoff timestamp hard-fails exactly as in the
        clone arm."""
        case = _case()
        fake = lambda *a, **k: "Sat for 2026-06-11T09:00:00+00:00."  # noqa: E731
        with pytest.raises(leakguard.LeakageDetectedError):
            officer_runner.run_case(case, "chair", llm=fake,
                                    gather=_fake_gather, brain=_FakeBrain(),
                                    identity_mode="agent")


# ---------------------------------------------------------------------------
# build_agent_eval_system (officer_prompt)
# ---------------------------------------------------------------------------

class TestBuildAgentEvalSystem:
    _IDENTITY = {"voice": _VOICE, "patterns": _PATTERNS,
                 "lessons": "LESSON-SENTINEL", "person_static": _PERSON}

    def test_privacy_fence_present(self):
        s = build_agent_eval_system(_case(), "chair", self._IDENTITY)
        assert "PRIVATE model" in s
        assert "NEVER quote, paste, or reference" in s

    def test_outcome_first_mandate_not_mimicry(self):
        s = build_agent_eval_system(_case(), "chair", self._IDENTITY)
        assert "NOT required" in s and "mimic" in s
        assert "OUTCOME" in s

    def test_missing_identity_degrades_not_crashes(self):
        s = build_agent_eval_system(_case(), "chair", {})
        assert "(unavailable)" in s
        s2 = build_agent_eval_system(_case(), "chair", None)
        assert "(unavailable)" in s2

    def test_never_includes_held_out_reply(self):
        s = build_agent_eval_system(_case(), "chair", self._IDENTITY)
        assert "Ja, lad os tage det fredag." not in s

    def test_clone_builder_unchanged_as_diagnostic_arm(self):
        """The clone arm is kept verbatim — same identity dict renders the
        CLONE framing with no agent mandate bleed-through."""
        s = build_clone_eval_system(_case(), "chair", self._IDENTITY)
        assert "CLONE IDENTITY" in s
        assert "AGENT IDENTITY" not in s
        assert "ON ADA'S BEHALF" not in s


# ---------------------------------------------------------------------------
# measure_intent — identity + outcome stamped into every rec
# ---------------------------------------------------------------------------

class TestMeasureIntentStamping:
    def _run_main(self, monkeypatch, tmp_path, argv_extra):
        from framework.fidelity import measure_intent

        case = _case()
        captured = {}

        def fake_run_case(c, role, gather=None, emit_events=True,
                          identity_mode="clone"):
            captured["identity_mode"] = identity_mode
            return OfficerDecision(decision="Ja.", rationale="", chain=[])

        def fake_score(c, decision, base, cents, intent_ctx=None):
            return CaseScore(
                case_id=c.case_id, style_win=True,
                decision_verdict="divergent", mechanics_flags=[],
                endorsement_adjusted=False, composite=0.0,
                intent_verdict="intent-aligned",
                intent_grounded_fact="From Otto at 2026-06-09: lon.",
                intent_composite=1.0,
                outcome_verdict="as_good_or_better",
                outcome_grounded_fact="From Otto at 2026-06-09: lon.")

        monkeypatch.setattr(measure_intent, "build_cases",
                            lambda n: [case])
        monkeypatch.setattr(measure_intent, "author_centroid",
                            lambda exclude_keys: {})
        monkeypatch.setattr(measure_intent, "oauth_raw_llm",
                            lambda *a, **k: "generic baseline")
        monkeypatch.setattr(measure_intent, "gather_cutoff_context",
                            lambda c: {"vault_hits": []})
        monkeypatch.setattr(officer_runner, "run_case", fake_run_case)
        monkeypatch.setattr(scorer, "score", fake_score)

        out = tmp_path / "shard.jsonl"
        monkeypatch.setattr(sys, "argv",
                            ["measure_intent.py", "--n", "1",
                             "--out", str(out)] + argv_extra)
        measure_intent.main()
        lines = [json.loads(ln) for ln in
                 out.read_text().strip().splitlines()]
        assert len(lines) == 1
        return lines[0], captured

    def test_default_identity_is_clone(self, monkeypatch, tmp_path):
        rec, captured = self._run_main(monkeypatch, tmp_path, [])
        assert rec["identity_mode"] == "clone"
        assert captured["identity_mode"] == "clone"

    def test_agent_identity_stamped_and_passed(self, monkeypatch, tmp_path):
        rec, captured = self._run_main(monkeypatch, tmp_path,
                                       ["--identity", "agent"])
        assert rec["identity_mode"] == "agent"
        assert captured["identity_mode"] == "agent"

    def test_outcome_verdict_in_rec(self, monkeypatch, tmp_path):
        rec, _ = self._run_main(monkeypatch, tmp_path, [])
        assert rec["outcome_verdict"] == "as_good_or_better"
        assert rec["decision_verdict"] == "divergent"
        assert rec["intent_verdict"] == "intent-aligned"
