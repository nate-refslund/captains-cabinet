"""Tests for Phase 7 self-improvement modules."""

from __future__ import annotations

import json
import os
import subprocess
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
# Store unification (2026-07-04, lane/learn-0705)
# ---------------------------------------------------------------------------
# The canonical store is memory/tier3/experience-records/ and list_records()
# must read BOTH formats living there: records-*.jsonl (record()) and the
# markdown files record-experience.sh writes. These tests pin the md→
# structured adapter contract and the legacy-store one-shot migration.


def _write_md_record(
    root: Path,
    *,
    name: str = "2026-06-24-polads-ceo-1782277573-20176",
    officer: str = "polads-ceo",
    outcome: str = "success",
    task: str = "First Mac-native polads-ceo boot",
    what: str = "Gathered-then-decided per courses-of-action.",
    lessons: str = "Verify session identity at boot.",
    counterfactual: str | None = "Check env first",
    date: str = "2026-06-24T05:06:13Z",
    tags: str = "activation,launchd",
) -> Path:
    """Compose a file byte-compatible with record-experience.sh block 1."""
    rec_dir = root / "memory" / "tier3" / "experience-records"
    rec_dir.mkdir(parents=True, exist_ok=True)
    body = (
        "# Experience Record\n\n"
        f"- **Officer:** {officer}\n"
        f"- **Date:** {date}\n"
        f"- **Outcome:** {outcome}\n"
        f"- **Tags:** {tags}\n\n"
        f"## Task\n{task}\n\n"
        f"## What Happened\n{what}\n\n"
        f"## Lessons Learned\n{lessons}\n"
    )
    # Records written before the counterfactual feature (pre 2026-06-25)
    # have NO such section — the parser must tolerate both shapes.
    if counterfactual is not None:
        body += f"\n## Counterfactual (one change → 10x)\n{counterfactual}\n"
    path = rec_dir / f"{name}.md"
    path.write_text(body)
    return path


class TestStoreUnification:
    def test_md_record_visible_and_mapped(self, tmp_path):
        path = _write_md_record(tmp_path)
        recs = list_records()
        assert len(recs) == 1
        r = recs[0]
        assert r["actor"] == "polads-ceo"
        assert r["lesson_type"] == "pattern"          # success → pattern
        assert r["trigger_signal"] == "First Mac-native polads-ceo boot"
        assert r["applicability_scope"] == "this_role"  # induction-eligible
        assert r["created_at"] == "2026-06-24T05:06:13Z"
        assert r["id"] == path.stem
        assert r["evidence"].endswith(".md")
        assert "Verify session identity" in r["body"]
        assert r["tags"] == ["activation", "launchd"]

    def test_md_outcome_to_lesson_type_mapping(self, tmp_path):
        _write_md_record(tmp_path, name="r-fail", outcome="failure")
        _write_md_record(tmp_path, name="r-part", outcome="partial")
        _write_md_record(tmp_path, name="r-esc", outcome="escalated")
        by_id = {r["id"]: r["lesson_type"] for r in list_records()}
        assert by_id == {
            "r-fail": "anti_pattern",
            "r-part": "blocker",
            "r-esc": "blocker",
        }

    def test_md_without_counterfactual_section_parses(self, tmp_path):
        # Pre-2026-06-25 records on the live disk have no counterfactual
        # section; the parser must not require it.
        _write_md_record(tmp_path, name="old-record", counterfactual=None)
        assert len(list_records()) == 1

    def test_md_placeholder_lessons_dropped_from_body(self, tmp_path):
        _write_md_record(
            tmp_path, name="no-lessons",
            lessons="No specific lessons noted.",
            what="The thing that happened.",
        )
        (r,) = list_records()
        assert "No specific lessons noted." not in r["body"]
        assert "The thing that happened." in r["body"]

    def test_malformed_md_skipped_not_fatal(self, tmp_path):
        rec_dir = tmp_path / "memory" / "tier3" / "experience-records"
        rec_dir.mkdir(parents=True)
        (rec_dir / "junk.md").write_text("just some prose, no fields at all\n")
        _write_md_record(tmp_path, name="good")
        recs = list_records()
        assert [r["id"] for r in recs] == ["good"]

    def test_jsonl_and_md_merge_with_filters(self, tmp_path):
        record(actor="cos", lesson_type="pattern",
               trigger_signal="jsonl side", body="b")
        _write_md_record(tmp_path, name="md-side", officer="cos",
                         outcome="success", task="md side")
        _write_md_record(tmp_path, name="md-other", officer="stephie-ceo",
                         outcome="failure", task="other")
        assert len(list_records()) == 3
        assert len(list_records(actor="cos")) == 2
        # lesson_type filter spans formats: pattern = jsonl rec + md success
        assert len(list_records(lesson_type="pattern")) == 2

    def test_records_write_to_tier3_canonical_dir(self, tmp_path):
        record(actor="cos", lesson_type="pattern", trigger_signal="t", body="b")
        canonical = tmp_path / "memory" / "tier3" / "experience-records"
        assert list(canonical.glob("records-*.jsonl"))
        # the severed pre-unification path must NOT be (re)created
        assert not (tmp_path / "memory" / "experience_records").exists()

    def test_legacy_jsonl_store_migrates_once(self, tmp_path):
        # A pre-unification deployment left structured records at the old
        # path — first touch of the store moves them into the canonical dir.
        legacy = tmp_path / "memory" / "experience_records"
        legacy.mkdir(parents=True)
        legacy_file = legacy / "records-2026-07-01.jsonl"
        legacy_file.write_text(json.dumps({
            "id": "legacy-1", "actor": "cos", "lesson_type": "pattern",
            "trigger_signal": "legacy signal", "applicability_scope": "this_role",
            "body": "legacy body", "evidence": None,
            "created_at": "2026-07-01T00:00:00+00:00",
        }) + "\n")
        recs = list_records()
        assert [r["id"] for r in recs] == ["legacy-1"]
        assert not legacy_file.exists()
        assert not legacy.exists()  # drained dir removed
        canonical = tmp_path / "memory" / "tier3" / "experience-records"
        assert (canonical / "records-2026-07-01.jsonl").exists()

    def test_legacy_migration_appends_on_filename_collision(self, tmp_path):
        canonical = tmp_path / "memory" / "tier3" / "experience-records"
        canonical.mkdir(parents=True)
        (canonical / "records-2026-07-01.jsonl").write_text(json.dumps({
            "id": "new-1", "actor": "cos", "lesson_type": "pattern",
            "trigger_signal": "s", "applicability_scope": "this_role",
            "body": "b", "evidence": None,
            "created_at": "2026-07-01T01:00:00+00:00",
        }) + "\n")
        legacy = tmp_path / "memory" / "experience_records"
        legacy.mkdir(parents=True)
        (legacy / "records-2026-07-01.jsonl").write_text(json.dumps({
            "id": "legacy-1", "actor": "cos", "lesson_type": "pattern",
            "trigger_signal": "s", "applicability_scope": "this_role",
            "body": "b", "evidence": None,
            "created_at": "2026-07-01T00:00:00+00:00",
        }) + "\n")
        ids = {r["id"] for r in list_records()}
        assert ids == {"new-1", "legacy-1"}  # both survive the merge
        assert not legacy.exists()

    def test_record_event_carries_experience_id(self):
        rec = record(actor="cos", lesson_type="pattern",
                     trigger_signal="t", body="b")
        (ev,) = replay(event_types=["experience_recorded"])
        assert (ev.get("payload") or {}).get("experience_id") == rec["id"]

    def test_md_embedded_heading_stays_in_body(self, tmp_path):
        # Record bodies quote arbitrary text — an embedded `## Step 2` in
        # task output must NOT open a phantom section and truncate the body
        # (checkpoint-review finding, cp1 #4).
        _write_md_record(
            tmp_path, name="embed",
            what="Step dump:\n## Step 2\nmore output",
            lessons="Real lesson",
        )
        (r,) = list_records()
        assert "## Step 2" in r["body"]
        assert "more output" in r["body"]
        assert "Real lesson" in r["body"]

    def test_induction_receives_md_records(self, tmp_path):
        # THE severance proof: three shell-written records sharing a task
        # line now form an induction cluster — before unification this was
        # structurally impossible (reader looked at an empty dir).
        for i in range(3):
            _write_md_record(
                tmp_path, name=f"md-{i}", officer=f"officer-{i}",
                outcome="success", task="Recurring identity mis-wiring at boot",
            )
        drafts = induce_drafts(min_cluster_size=3)
        assert len(drafts) == 1
        text = drafts[0].read_text()
        assert "Recurring identity mis-wiring at boot" in text
        assert "cluster_size: 3" in text

    def test_shell_writer_end_to_end(self, tmp_path):
        # The fix that motivated the unification: record-experience.sh block
        # 1c must land an experience_recorded event (OVI learning_rate feed)
        # AND the md record it writes must be list_records()-visible. Runs
        # the REAL script in a fake CABINET_ROOT (framework symlinked in so
        # the heredoc import works); redis points at a dead port and
        # DATABASE_URL is absent, so only file + ledger side effects remain
        # (checkpoint-review finding, cp1 #5 — this path was untested).
        repo_root = Path(__file__).resolve().parents[3]
        script = repo_root / "cabinet" / "scripts" / "record-experience.sh"
        if not script.exists():
            pytest.skip("record-experience.sh not present in this layout")

        fake_root = tmp_path / "root"
        fake_root.mkdir()
        (fake_root / "framework").symlink_to(repo_root / "framework")

        events_dir = tmp_path / "events"
        env = dict(os.environ)
        env.update({
            "CABINET_ROOT": str(fake_root),
            "CABINET_EVENT_LOG_DIR": str(events_dir),
            "REDIS_HOST": "localhost",
            "REDIS_PORT": "1",  # dead port — redis tail is best-effort
        })
        for k in ("DATABASE_URL", "OFFICER_NAME", "COUNTERFACTUAL"):
            env.pop(k, None)

        subprocess.run(
            ["bash", str(script), "test-officer", "success",
             "Bridge the severed learning stack",
             "unified store end-to-end", "always check the dir", "learning"],
            env=env, capture_output=True, text=True, timeout=60,
            check=False,  # exit code is the pre-existing redis tail; assert artifacts
        )

        md_files = list(
            (fake_root / "memory" / "tier3" / "experience-records").glob("*.md")
        )
        assert len(md_files) == 1

        events = []
        for f in events_dir.glob("events-*.jsonl"):
            for line in f.read_text().splitlines():
                if line.strip():
                    events.append(json.loads(line))
        exp = [e for e in events if e["event_type"] == "experience_recorded"]
        assert len(exp) == 1
        assert exp[0]["actor"] == "test-officer"
        assert exp[0]["payload"]["experience_id"] == md_files[0].stem
        assert exp[0]["payload"]["lesson_type"] == "pattern"  # success →

        # ...and the reader sees the shell-written record (same fake root).
        env_root = os.environ.get("CABINET_ROOT")
        os.environ["CABINET_ROOT"] = str(fake_root)
        try:
            recs = list_records()
        finally:
            os.environ["CABINET_ROOT"] = env_root
        assert [r["actor"] for r in recs] == ["test-officer"]


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
