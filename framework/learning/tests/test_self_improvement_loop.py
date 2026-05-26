"""Tests for the self-improvement loop (R8).

Covers:
  * CLI flag wiring — both ``--dry-run`` and ``--skip-evals`` parse correctly
    and are documented in ``--help`` output.
  * Dry-run contract — a full loop run with ``dry_run=True`` writes NO events
    to ``$CABINET_EVENT_LOG_DIR``, NO proposal YAMLs to
    ``instance/roles/proposals/``, and NO draft skills to
    ``memory/skills/evolved/``.
  * Proposal validation gate — concrete proposals are auto-applied when the
    gate passes; held back when it fails (status=blocked_by_validation).
  * Hat graduation — ``role_hat_assigned`` events meeting the threshold
    produce graduation candidates that auto-apply with
    ``captain_auto_ratified=true`` in the emitted ``role_hat_promoted``
    event payload.
  * Skill induction — clustered experience records produce draft skill
    files; the loop emits ``skill_promoted`` only for well-formed drafts.
  * Loop bracketing events — every non-dry-run invocation produces a paired
    ``self_improvement_loop_started`` / ``self_improvement_loop_completed``
    event sharing the same ``loop_id``.

Design notes:
  - Tests use the autouse ``isolated_env`` fixture to pin
    ``CABINET_ROOT`` + ``CABINET_EVENT_LOG_DIR`` to a per-test tmp_path so
    nothing touches the real ledger.
  - The validation gate is expensive (scenario evals + golden eval shells)
    so most tests monkeypatch ``_validation_gate`` to return a deterministic
    verdict. The validation tests exercise the pass + fail branches.
  - The framework store mirror is auto-disabled in pytest (the emitter
    checks ``PYTEST_CURRENT_TEST``) so JSONL is the only sink we measure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.events.emitter import emit, replay
from framework.learning import self_improvement_loop as sil
from framework.learning.experience import record as record_experience
from framework.roles.lifecycle import create_role


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Pin every filesystem + ledger path to tmp_path so tests are hermetic."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Make the validation gate trivially pass by default — individual tests
    # override this when they want to exercise the fail branch.
    monkeypatch.setattr(
        sil,
        "_validation_gate",
        lambda: (True, {"scenario_passed": True, "golden_passed": True}),
    )
    yield


@pytest.fixture
def event_log_dir(tmp_path) -> Path:
    return tmp_path / "events"


def _seed_eval_failures(
    role_slug: str,
    failure_type: str,
    n: int,
    eval_name: str = "test_eval",
) -> None:
    """Emit N synthetic eval_failed events tagged with the same failure_type.

    The pattern detector groups these by (role_slug, failure_type); N >= the
    min_occurrences threshold turns the cluster into a pattern, which the
    evolution generator then drafts a proposal for.
    """
    for i in range(n):
        emit("eval_failed", actor="role_eval_runner", payload={
            "role_slug": role_slug,
            "eval_name": f"{eval_name}-{i}",
            "failure_types": [failure_type],
            "failed_assertions": [f"assertion-{i}"],
        })


def _seed_role_on_disk(tmp_path: Path, slug: str) -> None:
    """Materialize a minimal role YAML so adapt_role can mutate it."""
    create_role(
        slug=slug,
        title=slug.upper(),
        charter=f"Test role {slug}",
        capabilities=["base_capability"],
        authority_level="standard",
        approved_by="test_setup",
    )


# ---------------------------------------------------------------------------
# 1. CLI flag wiring
# ---------------------------------------------------------------------------


class TestCLIFlags:
    """argparse must accept --skip-evals + --dry-run, and --help must list them."""

    def _run_help(self) -> str:
        cp = subprocess.run(
            [sys.executable, "-m", "framework.learning.self_improvement_loop", "--help"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert cp.returncode == 0, f"--help exited non-zero: {cp.stderr}"
        return cp.stdout

    def test_help_lists_skip_evals(self):
        out = self._run_help()
        assert "--skip-evals" in out, "--skip-evals missing from --help"

    def test_help_lists_dry_run(self):
        out = self._run_help()
        assert "--dry-run" in out, "--dry-run missing from --help"

    def test_help_documents_dry_run_no_writes(self):
        """The --dry-run blurb must promise no writes (key user contract)."""
        out = self._run_help()
        # Look for explicit language so this test breaks if the contract
        # gets watered down without intent.
        assert "NO events" in out or "NO writes" in out.lower() or \
               "NO proposal" in out, (
            "--dry-run --help should explicitly state it writes NO events / "
            f"NO proposals / NO draft files. Got: {out!r}"
        )

    def test_skip_evals_parses_without_error(self, monkeypatch):
        """Calling main() with --skip-evals must not raise on argparse."""
        monkeypatch.setattr(sil, "run_loop", lambda **kw: {
            "loop_id": "x", "dry_run": False, "skip_evals": kw.get("skip_evals", False),
            "validation_gate": {"skipped": "skip_evals"},
            "proposals": {"generated": 0, "auto_applied": 0,
                          "pending_captain": 0, "blocked_by_validation": 0,
                          "detail": []},
            "hat_graduations": {"candidates": 0, "applied": 0, "detail": []},
            "skill_induction": {"drafted": 0, "promoted": 0, "detail": []},
        })
        rc = sil.main(["--skip-evals"])
        assert rc == 0

    def test_dry_run_parses_without_error(self, monkeypatch):
        """Calling main() with --dry-run must not raise on argparse."""
        monkeypatch.setattr(sil, "run_loop", lambda **kw: {
            "loop_id": "x", "dry_run": kw.get("dry_run", False), "skip_evals": False,
            "validation_gate": {"skipped": "dry_run"},
            "proposals": {"generated": 0, "auto_applied": 0,
                          "pending_captain": 0, "blocked_by_validation": 0,
                          "detail": []},
            "hat_graduations": {"candidates": 0, "applied": 0, "detail": []},
            "skill_induction": {"drafted": 0, "promoted": 0, "detail": []},
        })
        rc = sil.main(["--dry-run"])
        assert rc == 0

    def test_both_flags_parse_together(self, monkeypatch):
        seen: dict[str, Any] = {}
        def fake_run_loop(**kw):
            seen.update(kw)
            return {
                "loop_id": "x", "dry_run": kw["dry_run"],
                "skip_evals": kw["skip_evals"],
                "validation_gate": {},
                "proposals": {"generated": 0, "auto_applied": 0,
                              "pending_captain": 0, "blocked_by_validation": 0,
                              "detail": []},
                "hat_graduations": {"candidates": 0, "applied": 0, "detail": []},
                "skill_induction": {"drafted": 0, "promoted": 0, "detail": []},
            }
        monkeypatch.setattr(sil, "run_loop", fake_run_loop)
        rc = sil.main(["--dry-run", "--skip-evals"])
        assert rc == 0
        assert seen["dry_run"] is True
        assert seen["skip_evals"] is True


# ---------------------------------------------------------------------------
# 2. Dry-run is a complete no-writes contract
# ---------------------------------------------------------------------------


class TestDryRunNoWrites:
    """Dry-run must touch nothing — ledger, proposals dir, skills dir all clean."""

    def test_no_events_emitted_in_dry_run(self, tmp_path, event_log_dir):
        # Trigger every stage: seed eval failures (proposals),
        # hat events (graduations), experience records (induction).
        _seed_eval_failures("test_role", "missing_skill", 4)
        for i in range(6):
            emit("role_hat_assigned", actor="cos", payload={
                "role_slug": "test_role",
                "hat_slug": "test-hat",
                "mission_id": f"m-{i}",
                "capabilities": ["foo"],
            })
        for i in range(3):
            record_experience(
                actor=f"officer-{i}",
                lesson_type="pattern",
                trigger_signal="Shared trigger signal",
                body=f"Lesson body {i}",
                applicability_scope="cabinet_wide",
            )

        # Snapshot the JSONL files before dry-run so we can diff after
        files_before = sorted(event_log_dir.glob("events-*.jsonl"))
        sizes_before = {f.name: f.stat().st_size for f in files_before}

        # Run the loop in dry-run
        summary = sil.run_loop(window_days=28, min_occurrences=3, dry_run=True)

        # Verify: no NEW events appended to the JSONL log
        files_after = sorted(event_log_dir.glob("events-*.jsonl"))
        sizes_after = {f.name: f.stat().st_size for f in files_after}
        assert files_after == files_before, \
            "dry-run created new JSONL log files (should be zero)"
        assert sizes_after == sizes_before, \
            "dry-run wrote new content to existing JSONL log files"

        # Verify: no loop_started / loop_completed in the ledger
        loop_events = replay(event_types=[
            "self_improvement_loop_started",
            "self_improvement_loop_completed",
        ])
        assert loop_events == [], \
            f"dry-run emitted loop bracket events: {loop_events!r}"

        # Verify: the summary still describes what was planned
        assert summary["dry_run"] is True
        assert summary["validation_gate"] == {"skipped": "dry_run"}

    def test_no_proposal_yaml_written_in_dry_run(self, tmp_path):
        _seed_eval_failures("test_role", "missing_skill", 4)
        proposals_dir = tmp_path / "instance" / "roles" / "proposals"

        sil.run_loop(dry_run=True)

        if proposals_dir.exists():
            yamls = list(proposals_dir.glob("*.yml"))
            assert yamls == [], f"dry-run wrote proposal YAMLs: {yamls!r}"

    def test_no_draft_skill_written_in_dry_run(self, tmp_path):
        for i in range(3):
            record_experience(
                actor=f"officer-{i}",
                lesson_type="pattern",
                trigger_signal="Dry-run should not write",
                body=f"body-{i}",
                applicability_scope="cabinet_wide",
            )
        skills_dir = tmp_path / "memory" / "skills" / "evolved"

        sil.run_loop(dry_run=True)

        if skills_dir.exists():
            md_files = list(skills_dir.glob("*.md"))
            assert md_files == [], f"dry-run wrote draft skills: {md_files!r}"

    def test_no_role_mutation_in_dry_run(self, tmp_path):
        _seed_role_on_disk(tmp_path, "test_role")
        _seed_eval_failures("test_role", "missing_skill", 4)

        role_file = tmp_path / "instance" / "roles" / "active" / "test_role.yml"
        mtime_before = role_file.stat().st_mtime
        content_before = role_file.read_bytes()

        sil.run_loop(dry_run=True)

        # The role file must not be touched in dry-run
        assert role_file.stat().st_mtime == mtime_before
        assert role_file.read_bytes() == content_before


# ---------------------------------------------------------------------------
# 3. Proposal gate — pass + fail paths
# ---------------------------------------------------------------------------


class TestProposalGate:
    """Concrete proposals must auto-apply when gate passes, hold when it fails."""

    def _patch_evolution_to_concrete(self, monkeypatch, role_slug: str):
        """Force propose_from_patterns to return a concrete (no-TODO) proposal."""
        proposals_dir = sil._cabinet_root() / "instance" / "roles" / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        proposal = {
            "proposal_id": f"{role_slug}-missing-skill",
            "role_slug": role_slug,
            "status": "pending_captain_approval",
            "trigger": {"failure_type": "missing_skill", "count": 4},
            "suggested_change": {
                "kind": "add_hat",
                "rationale": "Concrete test hat",
                "hat_template": {
                    "name": "concrete-hat",
                    "description": "Concrete test capability",
                    "capabilities": ["concrete_capability"],
                    "expires_at": None,
                },
            },
        }
        from yaml import safe_dump
        path = proposals_dir / f"{proposal['proposal_id']}.yml"
        path.write_text(safe_dump(proposal, sort_keys=False))
        monkeypatch.setattr(
            sil,
            "propose_from_patterns",
            lambda **kw: [(path, {"role_slug": role_slug,
                                  "failure_type": "missing_skill", "count": 4})],
        )

    def test_concrete_proposal_auto_applied_when_gate_passes(self, tmp_path, monkeypatch):
        _seed_role_on_disk(tmp_path, "gate_test_role")
        self._patch_evolution_to_concrete(monkeypatch, "gate_test_role")
        monkeypatch.setattr(
            sil, "_validation_gate",
            lambda: (True, {"scenario_passed": True, "golden_passed": True}),
        )

        summary = sil.run_loop()

        assert summary["proposals"]["generated"] == 1
        assert summary["proposals"]["auto_applied"] == 1
        # role_evolved event emitted with captain_auto_ratified=true
        ev = replay(event_types=["role_evolved"])
        assert len(ev) == 1
        payload = ev[0]["payload"]
        assert payload["captain_auto_ratified"] is True
        assert payload["validation_skipped"] is False
        # Capability actually added to the role
        role_yaml = (tmp_path / "instance" / "roles" / "active" / "gate_test_role.yml").read_text()
        assert "concrete_capability" in role_yaml

    def test_proposal_blocked_when_gate_fails(self, tmp_path, monkeypatch):
        _seed_role_on_disk(tmp_path, "blocked_role")
        self._patch_evolution_to_concrete(monkeypatch, "blocked_role")
        monkeypatch.setattr(
            sil, "_validation_gate",
            lambda: (False, {"scenario_passed": False, "golden_passed": True}),
        )

        summary = sil.run_loop()

        assert summary["proposals"]["generated"] == 1
        assert summary["proposals"]["auto_applied"] == 0
        assert summary["proposals"]["blocked_by_validation"] == 1
        # No role_evolved event
        assert replay(event_types=["role_evolved"]) == []

    def test_skeleton_proposal_held_for_captain(self, tmp_path, monkeypatch):
        """A proposal with <TODO:> placeholders must NOT auto-apply, gate or no gate."""
        _seed_eval_failures("skeleton_role", "missing_skill", 4)

        summary = sil.run_loop()

        # The pattern detector found the cluster; evolution drafted a skeleton.
        assert summary["proposals"]["generated"] >= 1
        # Skeletons stay pending_captain regardless of gate verdict.
        assert summary["proposals"]["auto_applied"] == 0
        assert summary["proposals"]["pending_captain"] >= 1

    def test_skip_evals_bypasses_gate(self, tmp_path, monkeypatch):
        """--skip-evals applies even when the gate would fail."""
        _seed_role_on_disk(tmp_path, "skip_role")
        self._patch_evolution_to_concrete(monkeypatch, "skip_role")
        # Gate would fail — but skip_evals should prevent it from running.
        sentinel = {"called": False}
        def gate_should_not_run():
            sentinel["called"] = True
            return (False, {"scenario_passed": False, "golden_passed": False})
        monkeypatch.setattr(sil, "_validation_gate", gate_should_not_run)

        summary = sil.run_loop(skip_evals=True)

        assert sentinel["called"] is False, \
            "validation_gate ran despite --skip-evals"
        assert summary["proposals"]["auto_applied"] == 1
        assert summary["validation_gate"] == {"skipped": "skip_evals"}
        ev = replay(event_types=["role_evolved"])
        assert len(ev) == 1
        assert ev[0]["payload"]["validation_skipped"] is True


# ---------------------------------------------------------------------------
# 4. Hat graduation
# ---------------------------------------------------------------------------


class TestHatGraduation:
    """role_hat_assigned events meeting threshold → auto-applied promotion."""

    def _emit_hat_uses(self, role: str, hat: str, n: int, capability: str):
        for i in range(n):
            emit("role_hat_assigned", actor="cos", payload={
                "role_slug": role,
                "hat_slug": hat,
                "mission_id": f"mission-{i:03d}",
                "capabilities": [capability],
            })

    def test_graduation_auto_applied_when_threshold_met(self, tmp_path, monkeypatch):
        _seed_role_on_disk(tmp_path, "hat_role")
        self._emit_hat_uses("hat_role", "promotable-hat", 6, "promoted_capability")

        summary = sil.run_loop()

        assert summary["hat_graduations"]["candidates"] == 1
        assert summary["hat_graduations"]["applied"] == 1

        # Verify the role_hat_promoted event carries auto-ratification
        promoted = [
            e for e in replay(event_types=["role_hat_promoted"])
            if (e.get("payload") or {}).get("status") == "auto_applied"
        ]
        assert len(promoted) == 1, \
            f"expected 1 auto_applied promotion event, got {len(promoted)}"
        payload = promoted[0]["payload"]
        assert payload["captain_auto_ratified"] is True
        assert payload["validation_skipped"] is False
        assert "promoted_capability" in payload["capabilities_promoted"]

        # The role on disk must now carry the promoted capability
        role_yaml = (tmp_path / "instance" / "roles" / "active" / "hat_role.yml").read_text()
        assert "promoted_capability" in role_yaml

    def test_below_threshold_no_graduation(self, tmp_path):
        _seed_role_on_disk(tmp_path, "shy_role")
        # 4 uses — below the default min_uses=5
        self._emit_hat_uses("shy_role", "shy-hat", 4, "unpromoted_capability")

        summary = sil.run_loop()

        assert summary["hat_graduations"]["candidates"] == 0
        assert summary["hat_graduations"]["applied"] == 0

    def test_graduation_blocked_when_gate_fails(self, tmp_path, monkeypatch):
        _seed_role_on_disk(tmp_path, "blocked_hat_role")
        self._emit_hat_uses("blocked_hat_role", "blocked-hat", 6, "blocked_cap")
        monkeypatch.setattr(
            sil, "_validation_gate",
            lambda: (False, {"scenario_passed": False, "golden_passed": False}),
        )

        summary = sil.run_loop()

        # Candidate detected but not applied
        assert summary["hat_graduations"]["candidates"] == 1
        assert summary["hat_graduations"]["applied"] == 0


# ---------------------------------------------------------------------------
# 5. Skill induction
# ---------------------------------------------------------------------------


class TestSkillInduction:
    """Experience clusters → draft skills → promoted only when well-formed."""

    def _seed_cluster(self, signal: str, n: int = 3,
                      scope: str = "cabinet_wide"):
        for i in range(n):
            record_experience(
                actor=f"officer-{i}",
                lesson_type="pattern",
                trigger_signal=signal,
                body=f"Cluster body {i} — must be non-empty",
                applicability_scope=scope,
            )

    def test_cluster_produces_promoted_draft(self, tmp_path):
        self._seed_cluster("Repeated lesson signal")

        summary = sil.run_loop()

        assert summary["skill_induction"]["drafted"] >= 1
        assert summary["skill_induction"]["promoted"] >= 1
        # A skill_promoted event for the draft
        promoted = replay(event_types=["skill_promoted"])
        assert len(promoted) >= 1
        payload = promoted[0]["payload"]
        assert payload["status"] == "draft_promoted"
        assert payload["captain_auto_ratified"] is True
        # File actually exists on disk
        skill_path = Path(payload["skill_path"])
        assert skill_path.exists()

    def test_invalid_draft_not_promoted(self, tmp_path, monkeypatch):
        """If induce_drafts returns a path to a bad file, no promotion event."""
        bad_path = tmp_path / "memory" / "skills" / "evolved" / "broken.md"
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        bad_path.write_text("")  # empty body → fails _validate_skill_draft

        monkeypatch.setattr(sil, "induce_drafts", lambda **kw: [bad_path])

        summary = sil.run_loop()

        assert summary["skill_induction"]["drafted"] == 1
        assert summary["skill_induction"]["promoted"] == 0
        assert replay(event_types=["skill_promoted"]) == []

    def test_no_records_no_drafts(self, tmp_path):
        summary = sil.run_loop()
        assert summary["skill_induction"]["drafted"] == 0
        assert summary["skill_induction"]["promoted"] == 0


# ---------------------------------------------------------------------------
# 6. Loop bracket events (started + completed)
# ---------------------------------------------------------------------------


class TestLoopEventsEmitted:
    """Non-dry-run runs always emit the started + completed pair."""

    def test_started_and_completed_emitted_paired(self, tmp_path):
        summary = sil.run_loop()

        started = replay(event_types=["self_improvement_loop_started"])
        completed = replay(event_types=["self_improvement_loop_completed"])
        assert len(started) == 1, f"expected 1 started event, got {len(started)}"
        assert len(completed) == 1, f"expected 1 completed event, got {len(completed)}"

        # The started event becomes the parent of the completed event
        assert completed[0]["parent_id"] == started[0]["id"]

        # Both reference the same loop_id
        assert (started[0]["payload"] or {}).get("loop_id") == summary["loop_id"]
        assert (completed[0]["payload"] or {}).get("loop_id") == summary["loop_id"]

    def test_completed_payload_contains_summary(self, tmp_path):
        sil.run_loop()
        completed = replay(event_types=["self_improvement_loop_completed"])
        assert len(completed) == 1
        payload = completed[0]["payload"] or {}
        # All four top-level summary sections present
        assert "proposals" in payload
        assert "hat_graduations" in payload
        assert "skill_induction" in payload
        assert "validation_gate" in payload

    def test_skip_evals_stamped_in_loop_events(self, tmp_path):
        sil.run_loop(skip_evals=True)

        started = replay(event_types=["self_improvement_loop_started"])
        completed = replay(event_types=["self_improvement_loop_completed"])
        assert started[0]["payload"]["skip_evals"] is True
        assert completed[0]["payload"]["skip_evals"] is True
        assert completed[0]["payload"]["validation_gate"] == {"skipped": "skip_evals"}
