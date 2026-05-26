"""Tests for Phase 7 self-improvement modules."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.events.emitter import emit, replay
from framework.roles.hat_graduation import (
    graduation_candidates,
    propose_graduations,
)
from framework.learning.experience import (
    record,
    list_records,
    VALID_LESSON_TYPES,
    VALID_APPLICABILITY_SCOPES,
)
from framework.learning.skill_induction import (
    induce_drafts,
    _cluster_records,
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)


# ---------------------------------------------------------------------------
# Hat graduation
# ---------------------------------------------------------------------------


class TestHatGraduation:
    def _emit_uses(self, role: str, hat: str, n: int, capabilities: list[str] | None = None):
        for i in range(n):
            emit("role_hat_assigned", actor="cos", payload={
                "role_slug": role,
                "hat_slug": hat,
                "mission_id": f"mission-{i:03d}",
                "capabilities": capabilities or [],
            })

    def test_no_events_no_candidates(self):
        assert graduation_candidates() == []

    def test_below_threshold_not_candidate(self):
        self._emit_uses("cto", "code-review", 4, capabilities=["reviews_implementations"])
        assert graduation_candidates(min_uses=5) == []

    def test_threshold_met_becomes_candidate(self):
        self._emit_uses("cto", "code-review", 6,
                        capabilities=["reviews_implementations", "approves_pull_requests"])
        candidates = graduation_candidates()
        assert len(candidates) == 1
        c = candidates[0]
        assert c["role_slug"] == "cto"
        assert c["hat_slug"] == "code-review"
        assert c["uses"] == 6
        assert c["missions"] == 6
        assert set(c["capabilities_to_promote"]) == {
            "reviews_implementations", "approves_pull_requests"
        }

    def test_already_promoted_excluded(self):
        self._emit_uses("cto", "code-review", 6, capabilities=["x"])
        emit("role_hat_promoted", actor="cos", payload={
            "role_slug": "cto", "hat_slug": "code-review",
        })
        assert graduation_candidates() == []

    def test_propose_graduations_emits_events(self):
        self._emit_uses("cpo", "spec-writer", 6, capabilities=["writes_specs"])
        propose_graduations()
        events = replay(event_types=["role_hat_promoted"])
        proposed = [e for e in events
                    if (e.get("payload") or {}).get("status") == "pending_captain_approval"]
        assert len(proposed) == 1

    def test_ovi_regression_blocks_candidate(self):
        # Baseline snapshot (BEFORE any hat use)
        emit("ovi_snapshot_computed", actor="ovi", payload={"composite_score": 0.8})
        # First three hat uses
        self._emit_uses("coo", "process-fixer", 3, capabilities=["fixes_processes"])
        # Regression snapshot INSIDE the use window
        emit("ovi_snapshot_computed", actor="ovi", payload={"composite_score": 0.6})
        # Three more uses (now total 6, meets min_uses)
        self._emit_uses("coo", "process-fixer", 3, capabilities=["fixes_processes"])
        # 0.8 baseline - 0.6 in-window = 0.2 > 0.02 threshold → blocked
        assert graduation_candidates() == []


# ---------------------------------------------------------------------------
# Structured experience records
# ---------------------------------------------------------------------------


class TestExperienceRecords:
    def test_valid_record(self):
        rec = record(
            actor="cto",
            lesson_type="pattern",
            trigger_signal="Migration with downtime",
            body="Use multi-step migration: add nullable column, backfill, switch reads, drop old.",
            applicability_scope="this_role",
        )
        assert rec["lesson_type"] == "pattern"
        assert rec["applicability_scope"] == "this_role"

    def test_invalid_lesson_type_rejected(self):
        with pytest.raises(ValueError, match="Invalid lesson_type"):
            record(actor="cto", lesson_type="bogus",
                   trigger_signal="x", body="y")

    def test_invalid_scope_rejected(self):
        with pytest.raises(ValueError, match="Invalid applicability_scope"):
            record(actor="cto", lesson_type="pattern",
                   trigger_signal="x", body="y",
                   applicability_scope="not-a-scope")

    def test_record_emits_event(self):
        record(actor="cto", lesson_type="surprise",
               trigger_signal="OVI dropped after charter change",
               body="...", applicability_scope="cabinet_wide")
        events = replay(event_types=["experience_recorded"])
        assert len(events) == 1
        assert (events[0].get("payload") or {}).get("lesson_type") == "surprise"

    def test_list_filters_by_actor(self):
        record(actor="cto", lesson_type="pattern", trigger_signal="A", body="a")
        record(actor="cpo", lesson_type="pattern", trigger_signal="B", body="b")
        assert len(list_records()) == 2
        assert len(list_records(actor="cto")) == 1
        assert len(list_records(actor="cpo")) == 1

    def test_list_filters_by_lesson_type(self):
        record(actor="cto", lesson_type="pattern", trigger_signal="A", body="a")
        record(actor="cto", lesson_type="blocker", trigger_signal="B", body="b")
        assert len(list_records(lesson_type="pattern")) == 1


# ---------------------------------------------------------------------------
# Skill induction
# ---------------------------------------------------------------------------


class TestSkillInduction:
    def _seed_records(self, count: int, signal: str, ltype: str = "pattern",
                      scope: str = "this_role", actor_prefix: str = "officer"):
        for i in range(count):
            record(
                actor=f"{actor_prefix}-{i}",
                lesson_type=ltype,
                trigger_signal=signal,
                body=f"Lesson body for record {i}",
                applicability_scope=scope,
            )

    def test_no_records_no_clusters(self):
        clusters = _cluster_records([], min_size=3)
        assert clusters == []

    def test_below_min_cluster_size_excluded(self):
        self._seed_records(count=2, signal="Test signal")
        clusters = _cluster_records(list_records(), min_size=3)
        assert clusters == []

    def test_threshold_met_yields_cluster(self):
        self._seed_records(count=3, signal="PR rejected for missing tests")
        clusters = _cluster_records(list_records(), min_size=3)
        assert len(clusters) == 1
        assert clusters[0]["size"] == 3
        assert clusters[0]["trigger_signal"] == "PR rejected for missing tests"

    def test_scope_filter_excludes_narrow_scopes(self):
        self._seed_records(count=3, signal="X", scope="this_task")
        # default scope_filter excludes this_task
        clusters = _cluster_records(list_records(), min_size=3,
                                     scope_filter={"this_role", "cabinet_wide"})
        assert clusters == []

    def test_induce_drafts_writes_files_and_emits(self, tmp_path):
        self._seed_records(count=3, signal="Captain decisions need WHY",
                           scope="cabinet_wide")
        drafts = induce_drafts(min_cluster_size=3)
        assert len(drafts) == 1
        # File written to memory/skills/evolved/
        assert drafts[0].exists()
        assert drafts[0].parent.name == "evolved"
        content = drafts[0].read_text()
        assert "name: induced-pattern-captain-decisions-need-why" in content
        assert "status: draft" in content
        # Event emitted
        events = replay(event_types=["digest_published"])
        induction_events = [e for e in events
                            if (e.get("payload") or {}).get("kind") == "skill_induction_draft"]
        assert len(induction_events) == 1

    def test_idempotent_overwrite(self):
        self._seed_records(count=3, signal="Same signal")
        first = induce_drafts()
        assert len(first) == 1
        first_content = first[0].read_text()

        # Add more records → re-induce
        self._seed_records(count=2, signal="Same signal", actor_prefix="more")
        second = induce_drafts()
        assert len(second) == 1
        assert first[0] == second[0]  # same path
        second_content = second[0].read_text()
        assert "cluster_size: 5" in second_content  # updated

    def test_sorted_by_cluster_size_desc(self):
        self._seed_records(count=5, signal="High frequency")
        self._seed_records(count=3, signal="Medium frequency")
        clusters = _cluster_records(list_records(), min_size=3)
        assert clusters[0]["trigger_signal"] == "High frequency"
        assert clusters[1]["trigger_signal"] == "Medium frequency"
