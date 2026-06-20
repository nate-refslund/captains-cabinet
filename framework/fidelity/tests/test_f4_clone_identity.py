"""F4 T1 tests — BrainAdapter clone-identity surface (voice / nate_model
patterns / date-filtered drafting lessons).

The clone draft (the officer arm scored against Nate's held-out reply) needs the
same current-state identity priors the retrodiction reply cell uses
(docs/fidelity-harness-design-2026-06-18.md; ground retrodiction-clone-draft-
reference / brain-identity-sources). These are accepted current-state leaks
(like the retrodiction reply cell): voice.md, nate_model('patterns'), and
drafting lessons — EXCEPT drafting lessons must be date-filtered STRICTLY BEFORE
the case cutoff (a lesson logged at/after the reply moment could postdate it and
leak; the whole same-day block is dropped, conservative + leak-proof).

These three methods INFORM the officer's system prompt but must NEVER be quoted
into the captured decision, a consequence event, or any artifact — that fence is
enforced elsewhere (officer_prompt assembly + scan_for_leaks); here we only
verify the adapter returns its source and that the lesson date-filter holds.

The brain libs are MOCKED via an injected fake ``server`` so these tests touch
NO live screenpipe / vault / network — exactly the injection seam the existing
person_intel / open_commitments / read_note methods already honor.
"""

from __future__ import annotations

from framework.fidelity.officer_runner import BrainAdapter


class _FakeServer:
    """A fake brain server honoring the injected-``server`` seam. Each method
    returns a distinctive source string the tests can assert on; drafting_lessons
    returns the RAW (unfiltered) lessons file so the adapter's own date-filter is
    what must drop the post-cutoff blocks."""

    def __init__(self, lessons_text: str = ""):
        self._lessons_text = lessons_text

    def voice_profile(self) -> str:
        return "VOICE-SOURCE: warm, direct, Danish for internal"

    def nate_model_patterns(self) -> str:
        return "[PRIVATE NATE-MODEL] PATTERNS-SOURCE: ships fast, hates ceremony"

    def drafting_lessons(self) -> str:
        return self._lessons_text


# A lessons file with blocks on three dates: two strictly before a 2026-06-10
# cutoff (must survive) and one ON the cutoff date (must be dropped entirely).
_LESSONS = """---
title: Drafting-Lessons
---

### 2026-05-01 — keep replies short
Nate prefers two sentences max on Teams.

### 2026-06-09 — answer the actual question
Do not punt; give the decision.

### 2026-06-10 — SAME-DAY-LEAK do not surface
This block is dated on the cutoff and must be dropped (could postdate the reply).
"""

CUTOFF = "2026-06-10T12:00:00+00:00"


class TestVoiceProfile:
    def test_returns_source(self):
        a = BrainAdapter(server=_FakeServer())
        assert a.voice_profile() == "VOICE-SOURCE: warm, direct, Danish for internal"


class TestNateModelPatterns:
    def test_returns_patterns_source(self):
        a = BrainAdapter(server=_FakeServer())
        out = a.nate_model_patterns()
        assert "PATTERNS-SOURCE" in out
        # the private fence travels with it (informs HOW, never egresses)
        assert "PRIVATE NATE-MODEL" in out


class TestDraftingLessonsDateFilter:
    def test_keeps_strictly_before_cutoff(self):
        a = BrainAdapter(server=_FakeServer(_LESSONS))
        out = a.drafting_lessons(CUTOFF)
        assert "2026-05-01" in out
        assert "keep replies short" in out
        assert "2026-06-09" in out
        assert "answer the actual question" in out

    def test_drops_same_day_and_later_blocks(self):
        a = BrainAdapter(server=_FakeServer(_LESSONS))
        out = a.drafting_lessons(CUTOFF)
        # the cutoff-date block (== reply date) is dropped ENTIRELY
        assert "2026-06-10" not in out
        assert "SAME-DAY-LEAK" not in out
        assert "must be dropped" not in out

    def test_earlier_cutoff_drops_more(self):
        # With a cutoff on 2026-06-09, only the 2026-05-01 block is strictly
        # before — the 06-09 block (same day) and the 06-10 block both drop.
        a = BrainAdapter(server=_FakeServer(_LESSONS))
        out = a.drafting_lessons("2026-06-09T08:00:00+00:00")
        assert "2026-05-01" in out
        assert "2026-06-09" not in out
        assert "2026-06-10" not in out

    def test_empty_lessons_is_empty(self):
        a = BrainAdapter(server=_FakeServer(""))
        assert a.drafting_lessons(CUTOFF) == ""
