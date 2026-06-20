"""F4 T3 tests — run_case wires clone identity into the F4 (gather) arm.

Design §1.6, §2.4, §4; ground retrodiction-clone-draft-reference / brain-
identity-sources / cabinet-officer-prompt.

The clone arm (gather set) must drive the officer to draft AS NATE'S CLONE:
run_case gathers the current-state identity priors leak-safe —
  - voice_profile()            (accepted current-state prior)
  - nate_model_patterns()      (accepted current-state prior, PRIVATE-fenced)
  - drafting_lessons(before_ts=case.cutoff_ts)  (STRICTLY pre-cutoff)
  - person_static              (already in the gathered ctx, atemporal frontmatter)
— and builds the officer system via build_clone_eval_system, so the officer
drafts in Nate's identity. The lessons date-filter is the only HARD cutoff:
voice + nate_model are accepted current-state priors (like retrodiction).

PRIVACY FENCE (paramount): the identity goes into the SYSTEM prompt ONLY. It
must NEVER echo into the captured decision/output — the post-output
scan_for_leaks must still run and catch any leak. These tests inject a fake
BrainAdapter (the `brain` seam) so they touch NO live screenpipe / vault /
network.

The gather=None (F1) arm stays BYTE-FOR-BYTE unchanged: no identity, generic
build_eval_system, payload == format_situation(case).
"""

from __future__ import annotations

import pytest

from framework.fidelity import officer_runner, leakguard
from framework.fidelity.officer_prompt import (
    build_clone_eval_system, build_eval_system, format_situation)
from framework.fidelity.types import Case

CUTOFF = "2026-06-10T12:00:00+00:00"

# Distinctive sentinels per identity prior — the tests assert they reach the
# SYSTEM prompt (inform the draft) and NEVER the captured decision/output.
_VOICE = "VOICE-SENTINEL: korte saetninger, ingen tankestreger."
_PATTERNS = "[PRIVATE NATE-MODEL] PATTERNS-SENTINEL: beslutter hurtigt."
_PERSON = "PERSON-SENTINEL: Ulrik, VP Product & Publishers."

# Lessons file: two blocks strictly before the 2026-06-10 cutoff (must survive)
# and one ON the cutoff date (must be dropped entirely by the date-filter).
_LESSONS_RAW = """---
title: Drafting-Lessons
---

### 2026-05-01 — keep replies short
LESSON-BEFORE-SENTINEL: two sentences max on Teams.

### 2026-06-10 — SAME-DAY-LEAK do not surface
LESSON-SAMEDAY-SENTINEL: this block postdates the reply and must drop.
"""


class _FakeBrain:
    """A fake BrainAdapter honoring the methods run_case calls in the clone arm.
    Records which methods were called (so a test can assert the clone-identity
    gather actually ran) and with what before_ts (so the lessons date-filter is
    provably driven by the case cutoff)."""

    def __init__(self):
        self.calls = []
        self.lessons_before_ts = None

    def voice_profile(self) -> str:
        self.calls.append("voice_profile")
        return _VOICE

    def nate_model_patterns(self) -> str:
        self.calls.append("nate_model_patterns")
        return _PATTERNS

    def drafting_lessons(self, before_ts: str) -> str:
        # Mirror the real adapter: ALWAYS date-filter strictly before before_ts.
        from framework.fidelity import retro
        self.calls.append("drafting_lessons")
        self.lessons_before_ts = before_ts
        return retro.lessons_before(before_ts, text=_LESSONS_RAW)

    def person_intel(self, slug: str) -> str:  # only reached if ctx lacks it
        self.calls.append("person_intel")
        return _PERSON


def _case():
    return Case.from_retro_case({
        "case_id": "abc1234567",
        "reply_key": "msgraph|MID1",
        "slug": "ulrik", "person": "Ulrik", "channel": "msgraph",
        "language": "da", "reply_ts": CUTOFF, "subject": "Re: lon",
        "n_prior": 3,
        "thread_before": [
            {"slug": "ulrik", "person": "Ulrik",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke lon?"},
        ],
        "real_reply": "Ja, lad os tage det fredag.",
    })


def _capture_llm(draft="Ja, fredag passer fint."):
    """Return (fake_llm, seen) — records system+payload, returns a clean draft."""
    seen = {}

    def fake(payload, system, max_tokens=1500, model="claude-sonnet-4-6"):
        seen["system"] = system
        seen["payload"] = payload
        return draft

    return fake, seen


def _fake_gather(case):
    """gather_cutoff_context stand-in: returns the structured leak-guarded dict
    (incl. person_static, which the clone identity reuses) without a live brain."""
    return {
        "thread": case.thread_before,
        "commitments": [],
        "vault_hits": [],
        "person_static": _PERSON,
        "excluded": ["search_brain (mtime != content-ts; no mtime fallback)"],
    }


class TestCloneArmInjectsIdentity:
    def test_clone_arm_builds_clone_eval_system(self):
        """When gather is set, the system prompt is the build_clone_eval_system
        prompt (identity-driven) — all four priors reach the system prompt."""
        case = _case()
        fake, seen = _capture_llm()
        brain = _FakeBrain()
        officer_runner.run_case(case, "chair", llm=fake, gather=_fake_gather,
                                brain=brain)
        system = seen["system"]
        # the identity priors that drive the clone draft reached the SYSTEM prompt
        assert _VOICE in system
        assert _PATTERNS in system
        assert "LESSON-BEFORE-SENTINEL" in system
        assert _PERSON in system
        # the clone framing is present (drafts AS Nate)
        assert "CLONE IDENTITY" in system
        assert "Nate" in system

    def test_clone_arm_gathers_identity_leak_safe(self):
        """The clone identity gather actually ran — voice, patterns and the
        date-filtered lessons were all fetched via the injected brain seam."""
        case = _case()
        fake, _ = _capture_llm()
        brain = _FakeBrain()
        officer_runner.run_case(case, "chair", llm=fake, gather=_fake_gather,
                                brain=brain)
        assert "voice_profile" in brain.calls
        assert "nate_model_patterns" in brain.calls
        assert "drafting_lessons" in brain.calls

    def test_lessons_date_filtered_strictly_before_cutoff(self):
        """The drafting lessons MUST be date-filtered strictly BEFORE the case
        cutoff: the before_ts is exactly the case cutoff and the same-day block
        is dropped entirely (a same-day lesson could postdate the reply)."""
        case = _case()
        fake, seen = _capture_llm()
        brain = _FakeBrain()
        officer_runner.run_case(case, "chair", llm=fake, gather=_fake_gather,
                                brain=brain)
        # the filter was driven by the case cutoff
        assert brain.lessons_before_ts == case.cutoff_ts
        system = seen["system"]
        # strictly-before block survives; same-day (cutoff-date) block dropped
        assert "LESSON-BEFORE-SENTINEL" in system
        assert "LESSON-SAMEDAY-SENTINEL" not in system
        assert "SAME-DAY-LEAK" not in system

    def test_clone_arm_still_appends_context_block(self):
        """The clone arm still renders + appends the leak-guarded context block
        after format_situation in the USER message — identity drives the system
        prompt, the gathered context rides the user message (unchanged §2.4)."""
        case = _case()
        fake, seen = _capture_llm()
        brain = _FakeBrain()
        officer_runner.run_case(case, "chair", llm=fake, gather=_fake_gather,
                                brain=brain)
        payload = seen["payload"]
        assert payload.startswith(format_situation(case))
        assert "CONTEXT (gathered as-of cutoff" in payload

    def test_clone_arm_drafts(self):
        """The officer actually drafts in the clone arm — the captured decision
        is the LLM draft (clean, no leak)."""
        case = _case()
        fake, _ = _capture_llm(draft="Ja, fredag klokken 14.")
        brain = _FakeBrain()
        dec = officer_runner.run_case(case, "chair", llm=fake,
                                      gather=_fake_gather, brain=brain)
        assert dec.decision == "Ja, fredag klokken 14."


class TestPrivacyFence:
    def test_identity_never_in_captured_decision(self):
        """PRIVACY FENCE: the identity priors inform the SYSTEM prompt only —
        they must NEVER appear in the captured decision/output. A clean draft
        carries none of the identity sentinels."""
        case = _case()
        fake, seen = _capture_llm(draft="Ja, fredag passer fint.")
        brain = _FakeBrain()
        dec = officer_runner.run_case(case, "chair", llm=fake,
                                      gather=_fake_gather, brain=brain)
        out = str(dec.decision)
        assert _VOICE not in out
        assert _PATTERNS not in out
        assert "PRIVATE NATE-MODEL" not in out
        assert "LESSON-BEFORE-SENTINEL" not in out
        # identity lives in the system prompt (informs), not the user payload
        assert _PATTERNS not in seen["payload"]
        assert _VOICE not in seen["payload"]

    def test_scan_for_leaks_runs_on_clone_output(self, monkeypatch):
        """The post-output scan_for_leaks guard MUST run in the clone arm — a
        draft that echoes a post-cutoff timestamp hard-fails exactly as in F1.
        (A draft echoing nate_model content carrying a post-cutoff ISO ts is
        caught by the same guard.)"""
        case = _case()
        seen_scan = {}
        orig_scan = leakguard.scan_for_leaks

        def spy(decision_text, thread_before, cutoff_ts):
            seen_scan["ran"] = True
            seen_scan["text"] = decision_text
            return orig_scan(decision_text, thread_before, cutoff_ts)

        monkeypatch.setattr(officer_runner.leakguard, "scan_for_leaks", spy)
        fake, _ = _capture_llm(draft="Ja, fredag passer fint.")
        brain = _FakeBrain()
        officer_runner.run_case(case, "chair", llm=fake, gather=_fake_gather,
                                brain=brain)
        assert seen_scan.get("ran") is True

    def test_clone_output_echoing_post_cutoff_ts_hard_fails(self):
        """A clone draft that echoes a post-cutoff timestamp (the leak-shape a
        nate_model echo would carry) is caught by scan_for_leaks and hard-fails
        — the privacy fence + cutoff fence both hold in the clone arm."""
        case = _case()
        # the officer "echoes" a post-cutoff moment into its draft
        fake = lambda *a, **k: "Sat for 2026-06-11T09:00:00+00:00 per the model."
        brain = _FakeBrain()
        with pytest.raises(leakguard.LeakageDetectedError):
            officer_runner.run_case(case, "chair", llm=fake,
                                    gather=_fake_gather, brain=brain)


class TestF1ArmUnchanged:
    def test_f1_arm_has_no_identity(self):
        """gather=None (F1) stays byte-for-byte: generic build_eval_system, NO
        clone identity, payload == format_situation(case)."""
        case = _case()
        fake, seen = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake)  # gather defaults None
        expected_system = (
            build_eval_system(case, "chair")
            + officer_runner.EVAL_MODE_RULES.format(cutoff_ts=case.cutoff_ts)
        )
        assert seen["system"] == expected_system
        assert seen["payload"] == format_situation(case)
        # none of the clone identity leaked into the F1 arm
        assert "CLONE IDENTITY" not in seen["system"]
        assert _VOICE not in seen["system"]
        assert _PATTERNS not in seen["system"]

    def test_f1_arm_does_not_touch_brain(self):
        """The F1 arm gathers no identity — a brain passed alongside gather=None
        is never called (no voice/patterns/lessons fetch)."""
        case = _case()
        fake, _ = _capture_llm()
        brain = _FakeBrain()
        officer_runner.run_case(case, "chair", llm=fake, brain=brain)
        assert brain.calls == []
