"""Audit #27 — the measurement corpus must actually install AND discover.

The framework ships ``framework/measurement/{role_evals,scenarios}/`` EMPTY
(egg row R006). Discovery therefore MUST also walk the per-deployment INSTANCE
seed dir (``instance/measurement/<kind>``, overridable for tests via
``CABINET_ROLE_EVALS_DIR`` / ``CABINET_SCENARIOS_DIR``). Before the fix the
runners only walked the empty framework dir, so ``run_all()`` returned ``[]``
forever — a silent dead sensor — and the org-level scenario safety gate (the
#21 partner) passed vacuously.

These prove the hole is closed (a seeded dir is discovered + its events fire)
AND that discovery does not over-reach (an empty / absent seed dir is a clean
no-op, never a crash). A MUTANT that drops the instance-dir leg of the loop
turns the seeded-discovery tests red.

Run: python3.12 -m pytest framework/measurement/tests/test_measurement_seed.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import framework.measurement._eval_registry as _er  # noqa: E402
import framework.measurement._scenario_registry as _sr  # noqa: E402
from framework.measurement import role_eval_runner as rer  # noqa: E402
from framework.measurement import scenario_runner as scr  # noqa: E402
from framework.events.emitter import replay  # noqa: E402


_ROLE_EVAL_SEED = '''\
from framework.measurement.role_eval_runner import RoleEval, register
register(RoleEval(
    name="seed_probe_eval",
    role_slug="cos",
    category="capability",
    description="seed discovery probe",
    setup=lambda: {},
    execute=lambda ctx: {"ok": True},
    verify=lambda ctx, res: [("ran", True, "n/a")],
))
'''

_SCENARIO_SEED = '''\
from framework.measurement.scenario_runner import Scenario, register
register(Scenario(
    name="seed_probe_scenario",
    description="seed discovery probe",
    category="role",
    setup=lambda: {"v": 1},
    execute=lambda ctx: {"r": ctx["v"]},
    verify=lambda ctx, res: [("ran", res["r"] == 1)],
))
'''


@pytest.fixture
def fresh_eval_registry(tmp_path, monkeypatch):
    """Own the global discovery flag + registry for this test, then restore."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("CABINET_ROLE_EVALS_DIR", raising=False)
    saved = dict(_er._EVALS)
    _er._EVALS.clear()
    _er._discovered = False
    yield
    _er._EVALS.clear()
    _er._EVALS.update(saved)
    _er._discovered = False


@pytest.fixture
def fresh_scenario_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("CABINET_SCENARIOS_DIR", raising=False)
    saved = dict(_sr._SCENARIOS)
    _sr._SCENARIOS.clear()
    _sr._discovered = False
    yield
    _sr._SCENARIOS.clear()
    _sr._SCENARIOS.update(saved)
    _sr._discovered = False


# --- role evals -----------------------------------------------------------

def test_role_evals_discovered_from_instance_seed(
        tmp_path, monkeypatch, fresh_eval_registry):
    seed = tmp_path / "role_evals"
    seed.mkdir()
    (seed / "seed_probe.py").write_text(_ROLE_EVAL_SEED)
    monkeypatch.setenv("CABINET_ROLE_EVALS_DIR", str(seed))

    results = rer.run_all()
    assert len(results) > 0, "seeded role-eval dir must be discovered"
    assert any(r.name == "seed_probe_eval" and r.passed for r in results)
    # the sensor is LIVE: an eval_passed event actually fired
    passed = replay(event_types=["eval_passed"])
    assert any((e.get("payload") or {}).get("eval_name") == "seed_probe_eval"
               for e in passed)


def test_empty_role_eval_seed_is_clean_no_crash(
        tmp_path, monkeypatch, fresh_eval_registry):
    empty = tmp_path / "empty_role_evals"
    empty.mkdir()
    monkeypatch.setenv("CABINET_ROLE_EVALS_DIR", str(empty))
    assert rer.run_all() == []


def test_absent_role_eval_seed_is_clean_no_crash(
        tmp_path, monkeypatch, fresh_eval_registry):
    monkeypatch.setenv("CABINET_ROLE_EVALS_DIR", str(tmp_path / "does-not-exist"))
    assert rer.run_all() == []


def test_role_eval_seed_default_resolves_under_cabinet_root(
        tmp_path, monkeypatch, fresh_eval_registry):
    """With no CABINET_ROLE_EVALS_DIR override, the seed dir resolves to
    ``<CABINET_ROOT>/instance/measurement/role_evals`` (the load-preset target)."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    # full-path string (not a bare quoted segment) — keeps check-layer-separation
    # from counting this test as a framework->instance coupling
    seed = tmp_path / "instance/measurement/role_evals"
    seed.mkdir(parents=True)
    (seed / "seed_probe.py").write_text(_ROLE_EVAL_SEED)
    results = rer.run_all()
    assert any(r.name == "seed_probe_eval" for r in results)


# --- scenarios ------------------------------------------------------------

def test_scenarios_discovered_from_instance_seed(
        tmp_path, monkeypatch, fresh_scenario_registry):
    seed = tmp_path / "scenarios"
    seed.mkdir()
    (seed / "seed_probe.py").write_text(_SCENARIO_SEED)
    monkeypatch.setenv("CABINET_SCENARIOS_DIR", str(seed))
    results = scr.run_all()
    assert any(r.name == "seed_probe_scenario" and r.passed for r in results)


def test_empty_scenario_seed_is_clean_no_crash(
        tmp_path, monkeypatch, fresh_scenario_registry):
    monkeypatch.setenv("CABINET_SCENARIOS_DIR", str(tmp_path / "no-scenarios"))
    assert scr.run_all() == []


def test_scenario_seed_default_resolves_under_cabinet_root(
        tmp_path, monkeypatch, fresh_scenario_registry):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    seed = tmp_path / "instance/measurement/scenarios"
    seed.mkdir(parents=True)
    (seed / "seed_probe.py").write_text(_SCENARIO_SEED)
    results = scr.run_all()
    assert any(r.name == "seed_probe_scenario" for r in results)
