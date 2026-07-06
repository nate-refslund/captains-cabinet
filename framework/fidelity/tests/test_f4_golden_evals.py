"""F4 T8 — golden evals (design §9).

The four F4 golden evals are markdown behavioral specs under
``memory/golden-evals/`` (same scenario/expected/failure format as the shipped
``eval-NNN-*.md`` files — they are docs the CoS runs in the reflection/evolution
loop, NOT executable code). This test is the TDD gate that keeps each spec
present AND honest against the actual code seams it describes:

  (a) eval-007 — no Tier-2 source is reachable from ``gather_cutoff_context``
      (sources=["vault"]; ``search_brain`` excluded with NO mtime fallback;
      ``brief`` dropped; ``person_intel`` -> static frontmatter).
  (b) eval-008 — a hollow surface-match (match × intent-divergent) -> 0.0.
  (c) eval-009 — an on-intent divergence (divergent × intent-aligned) -> 1.0.
  (d) eval-010 — a ``research_dependent`` case is excluded-and-surfaced,
      never zeroed.

Beyond "the file exists with the right words", the test pins the two numeric
claims (b)/(c) to ``scorer.composite`` so a spec can never assert a payoff the
code does not produce, and pins (a) to the real ``gather_cutoff_context``
behavior (Tier-2 unreachable). This is a pure file/lib check — no network, no
shell, no eval of file content.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from framework.fidelity import officer_runner, scorer

# repo root: framework/fidelity/tests/<this> -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_GOLDEN = _REPO_ROOT / "memory" / "golden-evals"

EVAL_TIER2 = _GOLDEN / "eval-007-fidelity-no-tier2-leak.md"
EVAL_HOLLOW = _GOLDEN / "eval-008-fidelity-hollow-surface-match-zero.md"
EVAL_ONINTENT = _GOLDEN / "eval-009-fidelity-on-intent-divergence-one.md"
EVAL_RESEARCH = _GOLDEN / "eval-010-fidelity-research-dependent-excluded.md"

ALL_EVALS = [EVAL_TIER2, EVAL_HOLLOW, EVAL_ONINTENT, EVAL_RESEARCH]


def _read(p: Path) -> str:
    assert p.exists(), f"missing golden eval: {p.relative_to(_REPO_ROOT)}"
    return p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Format: every F4 golden eval matches the shipped eval-NNN format (README).
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", ALL_EVALS, ids=lambda p: p.stem)
def test_format_matches_shipped_evals(path: Path):
    text = _read(path)
    assert text.lstrip().startswith("# Eval:"), "must start with '# Eval:' title"
    # category line — F4 evals are fidelity-harness quality/safety specs.
    cat = re.search(r"^Category:\s*(\w[\w| -]*)$", text, re.MULTILINE)
    assert cat, "missing 'Category:' line"
    assert "Tests:" in text, "missing 'Tests:' line"
    for section in ("## Scenario", "## Expected Behavior", "## Failure Condition"):
        assert section in text, f"missing section {section!r} in {path.name}"


# --------------------------------------------------------------------------
# (a) eval-007 — no Tier-2 source reachable from gather_cutoff_context.
# --------------------------------------------------------------------------
def test_eval_tier2_encodes_exclusion_claims():
    text = _read(EVAL_TIER2)
    assert "gather_cutoff_context" in text
    # Tier-1 only via the exact sources kwarg.
    assert 'sources=["vault"]' in text
    # search_brain excluded with NO mtime fallback ever.
    assert "search_brain" in text
    assert re.search(r"no\s+mtime\s+fallback", text, re.IGNORECASE), \
        "must state search_brain has no mtime fallback"
    # brief dropped; person_intel -> static frontmatter (dated sections stripped).
    assert "brief" in text
    assert "person_intel" in text
    assert "Notes from replies" in text
    # the audit 'excluded' list must be named (surfaced, not silently dropped).
    assert "excluded" in text


def test_eval_tier2_matches_real_gather_behavior():
    """Pin the spec to the code: gather_cutoff_context surfaces an ``excluded``
    audit list naming Tier-2 / search_brain / brief, and never reaches a Tier-2
    fetcher. A fake brain whose Tier-2 entry points raise proves unreachability;
    if the BrainAdapter ever grew a Tier-2 method, the spec (and this test) would
    be lying — so we assert no such surface exists."""

    class _Fake:
        def search(self, handle, topic=None):
            return {"hits": [], "brief": "POSTCUTOFF PROSE — must never appear"}

        def person_intel(self, slug):
            return "role: peer\n## Notes from replies\n- 2026-06-18 leaked\n"

        def open_commitments(self, direction):
            return []

        # No sent/screen/monday/search_brain method exists — calling one is a
        # hard AttributeError, the structural proof Tier-2 is unreachable.

    case = officer_runner.Case(
        case_id="c1", lane="send-1to1-reply", decision_type="reply",
        situation_ref="c1", ground_truth={}, endorsement="unknown",
        cutoff_ts="2026-05-12T00:00:00+00:00", source="t", held_out=True,
        slug="peer", person="Peer", thread_before=[], real_reply="HELD OUT",
    )
    out = officer_runner.gather_cutoff_context(case, brain=_Fake())
    excluded = " ".join(out.get("excluded", []))
    assert "search_brain" in excluded
    assert "brief" in excluded
    assert "Tier-2" in excluded
    # brief prose never makes it into the structured output.
    assert "POSTCUTOFF PROSE" not in str(out)
    # the PersonalSource interface framework depends on has no Tier-2 /
    # search_brain retrieval method at all (the source adapter can only reach the
    # four leak-eligible tools; there is deliberately NO path to "now").
    from framework.sources.base import PersonalSource
    for forbidden in ("search_brain", "fetch_sent", "gather_context",
                      "fetch_screen", "fetch_monday"):
        assert not hasattr(PersonalSource, forbidden), \
            f"PersonalSource must not expose a Tier-2 method: {forbidden}"


# --------------------------------------------------------------------------
# (b) eval-008 — hollow surface-match (match × intent-divergent) -> 0.0.
# --------------------------------------------------------------------------
def test_eval_hollow_encodes_zero_claim():
    text = _read(EVAL_HOLLOW)
    assert "match" in text and "intent-divergent" in text
    assert "0.0" in text
    assert "composite" in text


def test_eval_hollow_matches_real_composite():
    # the spec asserts match × intent-divergent == 0.0 — the code must agree.
    assert scorer.composite("match", "intent-divergent") == 0.0


# --------------------------------------------------------------------------
# (c) eval-009 — on-intent divergence (divergent × intent-aligned) -> 1.0.
# --------------------------------------------------------------------------
def test_eval_onintent_encodes_one_claim():
    text = _read(EVAL_ONINTENT)
    assert "divergent" in text and "intent-aligned" in text
    assert "1.0" in text
    assert "composite" in text
    # the credit path must reference the deterministic anti-rubber-stamp guard
    # (grounding + topic floor) so the spec records WHY this isn't a rubber-stamp.
    assert re.search(r"grounding", text, re.IGNORECASE)
    assert re.search(r"topic", text, re.IGNORECASE)


def test_eval_onintent_matches_real_composite():
    # the spec asserts divergent × intent-aligned == 1.0 — the code must agree.
    assert scorer.composite("divergent", "intent-aligned") == 1.0


# --------------------------------------------------------------------------
# (d) eval-010 — research_dependent excluded-and-surfaced, never zeroed.
# --------------------------------------------------------------------------
def test_eval_research_encodes_exclude_and_surface_claim():
    text = _read(EVAL_RESEARCH)
    assert "research_dependent" in text
    assert "excluded" in text
    # the load-bearing distinction: surfaced, NOT silently zeroed.
    assert re.search(r"never\s+(silently\s+)?zero", text, re.IGNORECASE), \
        "must state research_dependent cases are never zeroed"
    assert re.search(r"surfac", text, re.IGNORECASE), \
        "must state research_dependent cases are surfaced"
    # no live web at eval time — the reason the case can't be scored.
    assert re.search(r"web", text, re.IGNORECASE)
