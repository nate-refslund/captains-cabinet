"""Tests for the role eval runner + pattern detector + evolution proposals."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.measurement.role_eval_runner import (
    RoleEval,
    register,
    resolve_role_slug,
    run_eval,
    run_all,
    run_all_for_role,
    list_evals,
    _EVALS,
)
from framework.measurement.eval_pattern_detector import detect_patterns
from framework.roles.evolution import (
    draft_amendment,
    propose_one,
    propose_from_patterns,
)
from framework.events.emitter import emit, replay


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Each test gets a fresh event log and instance dir."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    (tmp_path / "instance" / "roles" / "active").mkdir(parents=True)


@pytest.fixture
def synthetic_evals():
    """Three test evals with known outcomes: pass / fail-missing-skill / fail-quality."""
    passing = RoleEval(
        name="t_pass",
        role_slug="t_role",
        category="capability",
        description="always passes",
        setup=lambda: {},
        execute=lambda ctx: {"ok": True},
        verify=lambda ctx, res: [("works", True, "n/a")],
    )
    fail_skill = RoleEval(
        name="t_fail_skill",
        role_slug="t_role",
        category="capability",
        description="always fails (missing_skill)",
        setup=lambda: {},
        execute=lambda ctx: {},
        verify=lambda ctx, res: [("missing", False, "missing_skill")],
    )
    fail_quality = RoleEval(
        name="t_fail_quality",
        role_slug="t_role",
        category="quality",
        description="always fails (quality_gap)",
        setup=lambda: {},
        execute=lambda ctx: {},
        verify=lambda ctx, res: [("quality", False, "quality_gap")],
    )
    err_eval = RoleEval(
        name="t_runtime_error",
        role_slug="t_role",
        category="capability",
        description="raises",
        setup=lambda: {},
        execute=lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")),
        verify=lambda ctx, res: [],
    )
    for ev in (passing, fail_skill, fail_quality, err_eval):
        register(ev)
    yield
    for name in ("t_pass", "t_fail_skill", "t_fail_quality", "t_runtime_error"):
        _EVALS.pop(name, None)


# ---------------------------------------------------------------------------
# role_eval_runner
# ---------------------------------------------------------------------------


class TestRunner:
    def test_run_eval_pass_emits_eval_passed(self, synthetic_evals):
        result = run_eval("t_pass")
        assert result.passed is True
        passed = replay(event_types=["eval_passed"])
        assert any((e.get("payload") or {}).get("eval_name") == "t_pass" for e in passed)

    def test_run_eval_fail_emits_eval_failed(self, synthetic_evals):
        result = run_eval("t_fail_skill")
        assert result.passed is False
        assert "missing_skill" in result.failure_types
        failed = replay(event_types=["eval_failed"])
        assert any((e.get("payload") or {}).get("eval_name") == "t_fail_skill" for e in failed)

    def test_run_eval_exception_treated_as_runtime_error(self, synthetic_evals):
        result = run_eval("t_runtime_error")
        assert result.passed is False
        assert result.error == "boom"
        assert "runtime_error" in result.failure_types

    def test_run_all_for_role_runs_only_that_role(self, synthetic_evals):
        results = run_all_for_role("t_role")
        assert {r.name for r in results} == {
            "t_pass", "t_fail_skill", "t_fail_quality", "t_runtime_error",
        }

    def test_run_eval_unknown_returns_error(self):
        result = run_eval("does-not-exist")
        assert result.passed is False
        assert "Unknown eval" in (result.error or "")


# ---------------------------------------------------------------------------
# roster-driven role resolution (R8 retarget, 2026-07-04)
# ---------------------------------------------------------------------------
# Shipped evals declare the retired work-preset roster (cto/cpo/cro/coo);
# the registry resolves those against cabinet/officer-capabilities.conf so
# eval attribution targets a role the evolution loop can load_role().


def _write_capabilities_conf(root: Path, lines: list[str]) -> None:
    conf_dir = root / "cabinet"
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "officer-capabilities.conf").write_text(
        "# test conf\n" + "\n".join(lines) + "\n"
    )


class TestRosterResolution:
    def test_non_extinct_slugs_pass_through(self, tmp_path):
        # Synthetic/test slugs and live slugs are NEVER remapped — only the
        # known-extinct work-preset roster is (surgical rule 1).
        _write_capabilities_conf(tmp_path, ["cos:telegram_bot"])
        assert resolve_role_slug("t_role") == "t_role"
        assert resolve_role_slug("cos") == "cos"
        assert resolve_role_slug("bakery-ceo") == "bakery-ceo"

    def test_extinct_slug_resolves_to_cos_from_conf(self, tmp_path):
        # The live portfolio-roster shape: Chair (cos) + lane CEOs + comms.
        _write_capabilities_conf(tmp_path, [
            "cos:captain_rules_retrieval",
            "cos:validates_deployments",
            "bakery-ceo:deploys_code",
            "newsletter-ceo:deploys_code",
            "comms-officer:logs_captain_decisions",
        ])
        for extinct in ("cto", "cpo", "cro", "coo"):
            assert resolve_role_slug(extinct) == "cos"

    def test_extinct_slug_kept_when_deployment_runs_it(self, tmp_path):
        # A deployment that genuinely still runs a cto keeps cto attribution
        # (rule 2) — resolution must not steal evals from a living role.
        _write_capabilities_conf(tmp_path, [
            "cto:deploys_code",
            "cos:validates_deployments",
        ])
        assert resolve_role_slug("cto") == "cto"
        assert resolve_role_slug("cpo") == "cos"  # still-extinct one remaps

    def test_successor_by_capability_when_no_cos(self, tmp_path):
        # Exotic roster with a renamed coordinator: the validates_deployments
        # holder (platform-quality owner) inherits the subsystem evals.
        _write_capabilities_conf(tmp_path, [
            "lane-a:deploys_code",
            "chair-x:validates_deployments",
        ])
        assert resolve_role_slug("coo") == "chair-x"

    def test_conf_inline_comments_stripped(self, tmp_path):
        # A trailing `# comment` on a conf line must not poison the exact
        # capability match in successor rule 3 (checkpoint-review cp1 #7).
        _write_capabilities_conf(tmp_path, [
            "lane-a:deploys_code",
            "chair-x:validates_deployments  # coordinator note",
        ])
        assert resolve_role_slug("cro") == "chair-x"

    def test_missing_conf_falls_back_to_static_cos(self, tmp_path):
        # tmp CABINET_ROOT has no conf at all (unit-test / bare-framework
        # context) → deterministic static successor.
        assert resolve_role_slug("cro") == "cos"

    def test_register_rebinds_and_preserves_declared(self, tmp_path):
        _write_capabilities_conf(tmp_path, ["cos:validates_deployments"])
        ev = RoleEval(
            name="t_extinct_bound",
            role_slug="coo",
            category="quality",
            description="declared for a retired role",
            setup=lambda: {},
            execute=lambda ctx: {"ok": True},
            verify=lambda ctx, res: [("works", True, "n/a")],
        )
        try:
            register(ev)
            assert _EVALS["t_extinct_bound"].role_slug == "cos"
            assert _EVALS["t_extinct_bound"].declared_role_slug == "coo"
            # ...and the runner's role filter sees it under the LIVE role,
            # so its eval_failed events reach a loadable amendment target.
            names = {e.name for e in run_all_for_role("cos")}
            assert "t_extinct_bound" in names
        finally:
            _EVALS.pop("t_extinct_bound", None)

    def test_register_leaves_live_binding_unmarked(self, tmp_path):
        _write_capabilities_conf(tmp_path, ["cos:validates_deployments"])
        ev = RoleEval(
            name="t_live_bound",
            role_slug="cos",
            category="quality",
            description="already live",
            setup=lambda: {},
            execute=lambda ctx: {"ok": True},
            verify=lambda ctx, res: [("works", True, "n/a")],
        )
        try:
            register(ev)
            assert _EVALS["t_live_bound"].role_slug == "cos"
            assert _EVALS["t_live_bound"].declared_role_slug == ""
        finally:
            _EVALS.pop("t_live_bound", None)


# ---------------------------------------------------------------------------
# eval_pattern_detector
# ---------------------------------------------------------------------------


class TestPatternDetector:
    def test_no_failures_no_patterns(self):
        patterns = detect_patterns()
        assert patterns == []

    def test_below_threshold_not_flagged(self):
        # emit just 2 failures (threshold default = 3)
        for _ in range(2):
            emit("eval_failed", actor="runner", payload={
                "eval_name": "e1",
                "role_slug": "cto",
                "failure_types": ["missing_skill"],
                "failed_assertions": ["a"],
            })
        assert detect_patterns() == []

    def test_threshold_met_flags(self):
        for i in range(3):
            emit("eval_failed", actor="runner", payload={
                "eval_name": f"e{i}",
                "role_slug": "cto",
                "failure_types": ["missing_skill"],
                "failed_assertions": [f"a{i}"],
            })
        patterns = detect_patterns()
        assert len(patterns) == 1
        p = patterns[0]
        assert p["role_slug"] == "cto"
        assert p["failure_type"] == "missing_skill"
        assert p["count"] == 3
        assert sorted(p["eval_names"]) == ["e0", "e1", "e2"]

    def test_multiple_failure_types_per_event_explode_to_buckets(self):
        # One eval failing for two reasons contributes to both buckets
        for i in range(3):
            emit("eval_failed", actor="runner", payload={
                "eval_name": f"e{i}",
                "role_slug": "cpo",
                "failure_types": ["missing_skill", "quality_gap"],
            })
        patterns = detect_patterns()
        types = {p["failure_type"] for p in patterns}
        assert types == {"missing_skill", "quality_gap"}

    def test_patterns_sorted_by_count_desc(self):
        for _ in range(5):
            emit("eval_failed", actor="runner", payload={
                "eval_name": "e",
                "role_slug": "cto",
                "failure_types": ["missing_skill"],
            })
        for _ in range(3):
            emit("eval_failed", actor="runner", payload={
                "eval_name": "e",
                "role_slug": "cpo",
                "failure_types": ["quality_gap"],
            })
        patterns = detect_patterns()
        assert patterns[0]["count"] == 5
        assert patterns[1]["count"] == 3


# ---------------------------------------------------------------------------
# evolution proposals
# ---------------------------------------------------------------------------


class TestEvolution:
    def _make_pattern(self, role_slug="cto", failure_type="missing_skill", count=3):
        return {
            "role_slug": role_slug,
            "failure_type": failure_type,
            "count": count,
            "eval_names": ["e1", "e2", "e3"],
            "first_seen": "2026-05-20T00:00:00Z",
            "last_seen": "2026-05-25T00:00:00Z",
            "sample_failed_assertions": ["assertion_a", "assertion_b"],
        }

    def test_draft_amendment_shape(self, tmp_path):
        amendment = draft_amendment(self._make_pattern(), cabinet_root=str(tmp_path))
        assert amendment["proposal_id"] == "cto-missing-skill"
        assert amendment["role_slug"] == "cto"
        assert amendment["status"] == "pending_captain_approval"
        assert "trigger" in amendment
        assert amendment["trigger"]["count"] == 3
        assert "current_charter" in amendment
        assert "suggested_change" in amendment
        # Heuristic: missing_skill → add_hat
        assert amendment["suggested_change"]["kind"] == "add_hat"

    def test_propose_one_writes_yaml_and_emits_event(self, tmp_path):
        path = propose_one(self._make_pattern(), cabinet_root=str(tmp_path))
        assert path.exists()
        content = path.read_text()
        assert "cto" in content
        assert "missing_skill" in content or "missing-skill" in content

        # role_charter_changed event was emitted
        events = replay(event_types=["role_charter_changed"])
        assert any(
            (e.get("payload") or {}).get("proposal_id") == "cto-missing-skill"
            for e in events
        )

    def test_propose_one_overwrites_existing_proposal(self, tmp_path):
        # First write
        first = propose_one(self._make_pattern(count=3), cabinet_root=str(tmp_path))
        first_content = first.read_text()

        # Re-propose with higher count — should overwrite, not duplicate
        second = propose_one(self._make_pattern(count=7), cabinet_root=str(tmp_path))
        assert first == second
        assert second.read_text() != first_content
        # Only one file in the proposals dir for this id
        files = list((tmp_path / "instance" / "roles" / "proposals").glob("cto-*.yml"))
        assert len(files) == 1

    def test_propose_from_patterns_creates_one_per_pattern(self, tmp_path):
        # Seed 3 patterns
        for slug, ftype, count in [
            ("cto", "missing_skill", 5),
            ("cpo", "quality_gap", 4),
            ("cos", "wrong_authority", 3),
        ]:
            for _ in range(count):
                emit("eval_failed", actor="runner", payload={
                    "eval_name": "e",
                    "role_slug": slug,
                    "failure_types": [ftype],
                })

        proposed = propose_from_patterns(cabinet_root=str(tmp_path))
        assert len(proposed) == 3
        proposal_dir = tmp_path / "instance" / "roles" / "proposals"
        assert len(list(proposal_dir.glob("*.yml"))) == 3

    def test_heuristic_mapping_failure_type_to_suggestion(self, tmp_path):
        for ftype, expected_kind in [
            ("missing_skill", "add_hat"),
            ("wrong_authority", "expand_authority"),
            ("scope_confusion", "captain_decision_split_or_refocus"),
            ("quality_gap", "add_quality_hat"),
            ("runtime_error", "engineering_investigation"),
            ("unspecified", "annotate_evals"),
        ]:
            amend = draft_amendment(
                self._make_pattern(failure_type=ftype),
                cabinet_root=str(tmp_path),
            )
            assert amend["suggested_change"]["kind"] == expected_kind, ftype
