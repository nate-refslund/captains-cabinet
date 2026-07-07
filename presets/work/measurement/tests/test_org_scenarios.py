"""Concrete org-scenario seed tests (five-officer work-preset archetype).

Relocated from framework/measurement/tests/test_scenario_runner.py by egg
row R006 (R050 pair): framework/measurement keeps the runner/registry
MACHINERY tests; these tests exercise the CONCRETE scenario seed content
that ships with the work preset (../scenarios/).

The seed is written for its INSTALL location — a work-preset deployment
copies it into framework/measurement/{scenarios,role_evals}/, and the
modules resolve the repo root / cabinet lib / policy layers positionally
from `__file__` there. So instead of loading the seed in place (which would
mis-resolve those paths to presets/), the session fixture performs a
MINIATURE INSTALL into a temp root — seed files copied byte-verbatim to
`<root>/framework/measurement/…`, repo layers symlinked read-only — exactly
the README's install semantics. Each installed module's import-time
`register(...)` populates the ONE shared registry in `_scenario_registry`,
the same mechanism the runner's directory discovery uses post-install. That
also makes `test_all_seed_scenarios_register` the relocated successor of
the old `test_dash_m_entrypoint_sees_all_scenarios` content guard (the
module-identity machinery half stays in framework:
`TestDashMEntrypoint.test_registry_is_shared_across_import_paths`).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# Repo root: presets/work/measurement/tests/<this file> -> up 4 dirs.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.measurement.scenario_runner import _SCENARIOS, run_scenario  # noqa: E402

_SEED_DIR = Path(__file__).resolve().parents[1]  # presets/work/measurement

# Every scenario shipped in this seed. Add here when adding a seed module so
# the register guard fails loudly on an unloadable/unregistered addition.
_EXPECTED_SCENARIOS = (
    "outcome_to_mission",
    "outcome_to_verified",
    "policy_enforcement",
    "role_adaptation",
    "role_retirement",
)

_seed_loaded = False


def _install_and_load(install_root: Path) -> None:
    """Copy the seed into a framework-shaped temp root and import it (once).

    - Seed content lands at <root>/framework/measurement/{scenarios,role_evals}
      byte-verbatim, so each module's positional `__file__` math (4 parents up
      = repo root; `<root>/cabinet/scripts/lib`; `load_policies(<root>)`)
      resolves exactly as at a real install.
    - The layers the seed READS are symlinked to this repo: framework/policies
      plus the cabinet/instance/presets/shared trees (policy layering mirrors
      the live root; everything is read-only for these scenarios — writes go
      to the temp roots the scenarios mkdtemp for themselves).
    - Distinct module-name namespace on purpose: the canonical
      `framework.measurement.scenarios.*` names belong to a real installed
      tree; claiming them here would mask install-path import bugs.
    """
    global _seed_loaded
    if _seed_loaded:
        return

    measurement = install_root / "framework" / "measurement"
    for content_dir in ("scenarios", "role_evals"):
        dst = measurement / content_dir
        dst.mkdir(parents=True)
        for f in sorted((_SEED_DIR / content_dir).glob("*.py")):
            (dst / f.name).write_bytes(f.read_bytes())
    (install_root / "framework" / "policies").symlink_to(
        _REPO_ROOT / "framework" / "policies", target_is_directory=True
    )
    for top in ("cabinet", "instance", "presets", "shared"):
        (install_root / top).symlink_to(_REPO_ROOT / top, target_is_directory=True)

    for f in sorted((measurement / "scenarios").glob("*.py")):
        if f.name.startswith("_"):
            continue
        module_name = f"work_preset_seed_scenarios.{f.stem}"
        if module_name in sys.modules:
            continue
        spec = importlib.util.spec_from_file_location(module_name, f)
        assert spec and spec.loader, f"unloadable seed module: {f}"
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)

    # The seed modules insert the install root into sys.path at import time
    # (their repo-root bootstrap). The real repo root is already importable
    # here; scrub the install-root entries so the temp tree never shadows it.
    sys.path[:] = [p for p in sys.path if not p.startswith(str(install_root))]
    _seed_loaded = True


@pytest.fixture(scope="session")
def seed_install(tmp_path_factory):
    root = tmp_path_factory.mktemp("seed-install")
    _install_and_load(root)
    return root


@pytest.fixture(autouse=True)
def clean_env(tmp_path, seed_install):
    """Same isolation the framework suite used for these tests.

    The scenarios' own setup() bodies re-point CABINET_ROOT at fresh temp
    dirs; the repo-root conftest fence restores the env after each test.
    """
    os.environ["CABINET_ROOT"] = str(tmp_path)
    os.environ["CABINET_EVENT_LOG_DIR"] = str(tmp_path / "events")
    os.environ.pop("DATABASE_URL", None)
    (tmp_path / "instance" / "roles" / "active").mkdir(parents=True)
    yield


class TestSeedRegistration:
    def test_all_seed_scenarios_register(self):
        """Every seed scenario must land in the shared runner registry."""
        missing = set(_EXPECTED_SCENARIOS) - set(_SCENARIOS)
        assert not missing, f"seed scenarios failed to register: {sorted(missing)}"


class TestOrgScenarios:
    """Run the actual org scenarios to verify they work."""

    def test_role_adaptation_scenario(self):
        result = run_scenario("role_adaptation")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"

    def test_role_retirement_scenario(self):
        result = run_scenario("role_retirement")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"

    def test_policy_enforcement_scenario(self):
        result = run_scenario("policy_enforcement")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"

    def test_outcome_to_mission_scenario(self):
        """Phase 1 baseline: outcome compiles into a valid mission."""
        result = run_scenario("outcome_to_mission")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"

    def test_outcome_to_verified_scenario(self):
        """Phase 1 closure: outcome → completed → verified → OVI reflects activity."""
        result = run_scenario("outcome_to_verified")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"
