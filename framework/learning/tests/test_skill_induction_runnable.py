"""§4.2 — runnable skill induction (2026-07-09 upgrade).

A draft used to ship an empty "(Filled in by the CoS...)" Procedure
skeleton — procedural memory that wasn't executable. Pins: deterministic
imperative-step distillation (replayable, deduped, capped), the
quote-the-lesson fallback floor, the auto-derived first validation
scenario, frontmatter distillation record, and — the safety spine —
governance UNCHANGED: drafts stay status: draft, and only the existing
promote_draft gate flips them (induction never self-promotes).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from framework.learning import skill_induction as si


def _cluster(bodies):
    return {"lesson_type": "pattern", "trigger_signal": "test signal here",
            "size": len(bodies), "actors": ["cos"],
            "applicability_scopes": ["this_role"],
            "sample_bodies": bodies,
            "first_seen": "2026-07-01T00:00:00Z",
            "last_seen": "2026-07-08T00:00:00Z"}


DIRECTIVE = ("Always gather context before replying to the Captain. "
             "The stale self-view nudge failed twice.")


class TestDistill:
    def test_extracts_directive_sentences_only(self):
        steps = si.distill_procedure([DIRECTIVE])
        assert steps == ["Always gather context before replying to the Captain"]

    def test_deterministic_and_deduped(self):
        bodies = [DIRECTIVE, DIRECTIVE.lower(), DIRECTIVE]
        assert si.distill_procedure(bodies) == si.distill_procedure(bodies)
        assert len(si.distill_procedure(bodies)) == 1

    def test_capped_at_max_steps(self):
        bodies = [f"Always do the number {i} thing before acting."
                  for i in range(20)]
        assert len(si.distill_procedure(bodies)) == si._MAX_STEPS

    def test_no_directives_yields_empty(self):
        assert si.distill_procedure(["a fact", "another plain fact here ok"]) == []


class TestRunnableDraft:
    def test_distilled_procedure_lands_numbered(self):
        _, body = si._draft_skill_yaml(_cluster([DIRECTIVE]))
        assert "1. Always gather context before replying to the Captain." in body
        assert "procedure_distilled: true" in body
        assert "(Filled in by the CoS" not in body    # the dead skeleton is gone

    def test_fallback_quotes_lessons_as_runnable_floor(self):
        _, body = si._draft_skill_yaml(_cluster(
            ["plain observation without directives whatsoever in this text"]))
        assert "1. Apply the recorded lesson: plain observation" in body
        assert "procedure_distilled: false" in body

    def test_auto_derived_scenario_present(self):
        _, body = si._draft_skill_yaml(_cluster([DIRECTIVE]))
        assert "Scenario 1 (auto-derived)" in body
        assert 'the signal "test signal here" appears again' in body

    def test_draft_status_and_promotion_bar_unchanged(self):
        _, body = si._draft_skill_yaml(_cluster([DIRECTIVE]))
        assert "status: draft" in body
        assert "must pass golden eval before promotion" in body


class TestGovernanceUnchanged:
    def test_only_promote_draft_flips_status(self, tmp_path):
        _, body = si._draft_skill_yaml(_cluster([DIRECTIVE]))
        p = tmp_path / "induced-pattern-test-signal-here.md"
        p.write_text(body)
        assert si.draft_status(p) == "draft"
        assert si.promote_draft(p) is True
        assert si.draft_status(p) == "validated"
        # a validated skill is never re-stamped
        assert si.promote_draft(p) is False

    def test_induction_source_never_calls_promote(self):
        src = Path(si.__file__).read_text()
        induce_body = src.split("def induce_drafts", 1)[1].split("\ndef ", 1)[0]
        assert "promote_draft" not in induce_body
        assert "status: validated" not in induce_body

    def test_reinduction_never_demotes_promoted_skill(self, tmp_path, monkeypatch):
        """memory-learning-2: the recurring induce_drafts pass must never
        overwrite a promoted (status: validated) skill back to draft — only
        still-draft (or absent) files are (re)written."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        monkeypatch.setattr(si, "list_records", lambda: [])
        monkeypatch.setattr(si, "_cluster_records",
                            lambda *a, **k: [_cluster([DIRECTIVE])])
        monkeypatch.setattr(si, "emit", lambda *a, **k: None)
        first = si.induce_drafts()
        assert len(first) == 1
        path = first[0]
        assert si.draft_status(path) == "draft"
        # a still-draft skill IS refreshed on re-run (idempotent overwrite)
        assert si.induce_drafts() == [path]
        # promote, then re-run: the promoted skill is skipped, byte-identical
        assert si.promote_draft(path) is True
        validated_body = path.read_text()
        assert si.induce_drafts() == []
        assert path.read_text() == validated_body
        assert si.draft_status(path) == "validated"
