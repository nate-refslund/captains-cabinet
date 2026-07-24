"""COG-4 W6 e2 — the REAL organ-runner + real-compose bindings (§9.2/§9.5).

NEW test file (corpus law §13: purely additive — no existing test edited).
Two jobs:

1. PRE-PROVE the armed corpus arms this unit flips, out-of-band of the arms
   themselves, so the landing integrator's surgery is a verified drop-in:
     * `test_cog4_organ_runner.py::TestRealRunnerCliArms` (both absence
       tripwires RED on the CLI landing) — the retirement condition asks the
       §9.5 battery to bind to the real CLI as a subprocess: DONE HERE via
       `real_cli_runner`, reusing the corpus checkers (`_check_invariance`,
       `_check_cache_untouched`, `_check_declared_list`) imported from the
       corpus file, never re-implemented (the W5-x3 single-source precedent).
     * `test_cog4_floor_conservation.py::TestRealParseOrganManifestsArm`
       (hasattr tripwire RED on `_parse_organ_manifests` landing) — the
       retirement condition asks the REAL derivation to be cross-checked
       against `lib_cog4_floors.derive_organ_expectations` on the same
       fixtures: DONE HERE over BOTH the serialized corpus fixture dicts and
       the five REAL organ manifests.

2. BIND the real compose forward-tree invariants (the §9.2 COUNT+TUPLE laws
   over the LIVE cabinet/services.yml + cabinet/config/organs/): association
   1:1, runner cadence <= every absorbed period, thresholds <= the absorbed
   rows' derived floors (`_floor_for_entry` semantics — the absorbed rows were
   daily-calendar, floor 93600s), per-organ distinct non-runner-log probes,
   disjoint state_ownership, and the runner's --plan smoke over the REAL row
   (nothing executed, nothing written).

S0: python3.12, no DB, no network; the ONLY subprocesses are the runner CLI
under test (fixture manifests + --plan — it executes no organ entrypoints
here). Provenance: authored per the 2026-07-07 full-autonomy grant + the
2026-07-20 cognitive-masterplan continuous grant (COG-4 W6 unit e2,
Fable-for-execution per the 2026-07-23 calibration).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog4_floors as FL                                   # noqa: E402
from framework.watchdog import registry as wreg                # noqa: E402
from test_cog4_organ_runner import (                           # noqa: E402
    _check_cache_untouched,
    _check_declared_list,
    _check_invariance,
)

RUNNER_CLI = _REPO / "cabinet" / "scripts" / "cog4-organ-runner.py"
SERVICES_YML = _REPO / "cabinet" / "services.yml"
ORGANS_DIR = _REPO / "cabinet" / "config" / "organs"
RUNNER_ROW = "cog4-organ-runner"
COMPOSED = ["charter-shadow", "judge-calibration", "prediction-calibration",
            "preference-pairs", "world-census"]
# the absorbed rows' pre-compose reality (services.yml at fc51fd59): all five
# were daily-calendar rows — effective period 86400s, derived floor 26h
# (registry._floor_for_entry calendar law). Pinned so a loosening edit to the
# manifests or the runner row REDs here even after the rows are gone.
ABSORBED_PERIOD_S = 86400
ABSORBED_FLOOR_S = 26 * 3600


# ===========================================================================
# 1a. the real CLI under the §9.5 corpus battery (subprocess adapter)
# ===========================================================================

def real_cli_runner(row, manifest_dir: Path, run_root: Path, cache_dir: Path):
    """The corpus-battery adapter: run the REAL CLI as a subprocess over the
    same row fixture. `cache_dir` is deliberately NOT passed — the runner has
    no cache parameter at all (scheduler-blind by construction); the injected
    artifact sits where a reader-mutant WOULD find it, and the battery proves
    behavior is identical either way."""
    row_path = Path(manifest_dir).parent / "row.json"
    row_path.write_text(json.dumps(row, sort_keys=True), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(RUNNER_CLI), "--row-json", str(row_path),
         "--manifest-dir", str(manifest_dir), "--run-root", str(run_root)],
        capture_output=True, text=True, check=False)
    assert proc.stdout.strip(), f"no behavior JSON on stdout: {proc.stderr}"
    behavior = json.loads(proc.stdout)
    assert behavior["exit_status"] == proc.returncode, (
        "behavior exit_status must equal the process exit code")
    return behavior


class TestRealRunnerCliBattery:
    """The retirement-condition binding for BOTH TestRealRunnerCliArms
    tripwires (§9.5/§12) — run twice as a subprocess, with and without a
    schedule artifact injected, byte-identical behavior."""

    def test_real_cli_invariance(self, tmp_path):
        _check_invariance(real_cli_runner, tmp_path)

    def test_real_cli_leaves_schedule_cache_untouched(self, tmp_path):
        _check_cache_untouched(real_cli_runner, tmp_path)

    def test_real_cli_declared_list_never_discovery(self, tmp_path):
        _check_declared_list(real_cli_runner, tmp_path)

    def test_real_cli_deterministic_across_runs(self, tmp_path):
        from test_cog4_organ_runner import _arm
        b1, bytes1, _x, _y = _arm(real_cli_runner, tmp_path, "r1", inject=False)
        b2, bytes2, _z, _w = _arm(real_cli_runner, tmp_path, "r2", inject=False)
        assert b1 == b2
        assert bytes1 == bytes2

    def test_real_cli_source_is_statically_scheduler_blind(self):
        """Belt to the boundary rows' braces: the runner file IMPORTS no
        framework.scheduler (AST, alias-safe) and carries no schedule-store
        path token in code (the §8.3 deliberate-absence rows fence this at
        the import gate; this is the same assertion nearer the file)."""
        import ast
        tree = ast.parse(RUNNER_CLI.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("framework.scheduler")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("framework.scheduler")
                if mod == "framework":
                    assert all(a.name != "scheduler" for a in node.names)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # string literals in CODE positions may not spell the store
                # token; the module docstring documents the LAW and names the
                # boundary rows, so it is exempt (first statement).
                pass
        token = "cabinet/cache/" + "scheduler"
        body = RUNNER_CLI.read_text(encoding="utf-8")
        docstring = ast.get_docstring(tree, clean=False) or ""
        assert token not in body.replace(docstring, "")


# ===========================================================================
# 1b. the real _parse_organ_manifests vs the reference twin (cross-checks)
# ===========================================================================

def _manifest_text_from_fixture(man: dict) -> str:
    """Serialize a corpus fixture dict (the lib_cog4_floors._organ shape) into
    the manifest text shape the registry's narrow parser documents."""
    fn = man.get("freshness_needs", {})
    lines = [f"name: {man['name']}", "kind: organ", "freshness_needs:"]
    if "max_staleness_seconds" in fn:
        lines.append(f"  max_staleness_seconds: {fn['max_staleness_seconds']}")
    if "expected_output" in fn:
        lines.append(f"  expected_output: {fn['expected_output']}")
    return "\n".join(lines) + "\n"


class TestRealDerivationCrossCheck:
    """The TestRealParseOrganManifestsArm retirement condition, discharged:
    the REAL registry derivation equals the reference twin's
    `(expected_output, max_staleness)` pairs."""

    def test_fixture_dicts_cross_check(self):
        from test_cog4_floor_conservation import _good_organs
        ref, ref_errors = FL.derive_organ_expectations(_good_organs())
        assert ref_errors == []
        for man in _good_organs():
            derived, errors = wreg._derive_organ_expectation_from_text(
                _manifest_text_from_fixture(man))
            assert errors == [], (man["name"], errors)
            name, out, stale = derived
            assert (out, stale) == ref[name], (
                f"{name}: real derivation {derived} != reference {ref[name]}")

    def test_real_manifest_files_cross_check(self):
        yaml_dicts = [yaml.safe_load((ORGANS_DIR / f"{n}.yml").read_text())
                      for n in COMPOSED]
        ref, ref_errors = FL.derive_organ_expectations(yaml_dicts)
        assert ref_errors == []
        assert set(ref) == set(COMPOSED)
        for n in COMPOSED:
            derived, errors = wreg._derive_organ_expectation_from_text(
                (ORGANS_DIR / f"{n}.yml").read_text())
            assert errors == [], (n, errors)
            name, out, stale = derived
            assert name == n
            assert (out, stale) == ref[n]

    def test_malformed_manifest_yields_errors_never_silence(self):
        derived, errors = wreg._derive_organ_expectation_from_text(
            "name: broken\nkind: organ\n")
        assert derived is None
        assert any("max_staleness_seconds" in e for e in errors)
        derived2, errors2 = wreg._derive_organ_expectation_from_text(
            "kind: organ\nfreshness_needs:\n  max_staleness_seconds: 10\n"
            "  expected_output: x\n")
        assert derived2 is None
        assert any("name" in e for e in errors2)

    def test_services_association_parses_through_the_real_registry(self):
        """The runner row's DECLARED organ list reaches the watchdog: the
        real `_parse_organ_manifests` over the LIVE services.yml derives one
        expectation per composed organ (COUNT law, live)."""
        def read_text(path):
            p = Path(path)
            return p.read_text(encoding="utf-8") if p.is_file() else ""
        entries, problems = wreg._parse_organ_manifests(
            SERVICES_YML.read_text(encoding="utf-8"), read_text)
        assert problems == []
        got = {e["organ"]: e for e in entries}
        assert set(got) == set(COMPOSED)
        for e in entries:
            assert e["runner"] == RUNNER_ROW
            assert e["max_staleness_s"] <= ABSORBED_FLOOR_S

    def test_disabled_runner_rows_derive_no_floors(self):
        """Parked runner rows are declared state, not failures — mirroring the
        per-row disabled law."""
        text = ("services:\n"
                "  - name: parked-runner\n"
                "    label: com.cabinet.parked-runner\n"
                "    kind: cron\n"
                "    disabled: true\n"
                "    schedule: { interval_s: 60 }\n"
                "    organs:\n"
                "      - cabinet/config/organs/charter-shadow.yml\n")
        entries, problems = wreg._parse_organ_manifests(
            text, lambda p: (_REPO / "cabinet/config/organs/charter-shadow.yml"
                             ).read_text(encoding="utf-8"))
        assert entries == []
        assert problems == []

    def test_unreadable_declared_manifest_is_a_loud_problem(self):
        text = ("services:\n"
                "  - name: live-runner\n"
                "    label: com.cabinet.live-runner\n"
                "    kind: cron\n"
                "    schedule: { interval_s: 60 }\n"
                "    organs:\n"
                "      - cabinet/config/organs/absent.yml\n")
        entries, problems = wreg._parse_organ_manifests(text, lambda p: "")
        assert entries == []
        assert any("CANNOT derive" in p for p in problems), problems


# ===========================================================================
# 2. the real compose — §9.2 tuple laws bound to the live tree
# ===========================================================================

class TestRealComposeForwardTree:
    def _runner_entry(self):
        rows = {e["name"]: e for e in wreg._parse_services_manifest(
            SERVICES_YML.read_text(encoding="utf-8"))}
        assert RUNNER_ROW in rows, "the composed runner row is missing"
        return rows[RUNNER_ROW]

    def test_runner_row_is_an_enabled_fixed_interval_cron(self):
        e = self._runner_entry()
        assert not e["disabled"]
        assert e["schedule_kind"] == "interval"
        assert int(e["interval_s"]) <= ABSORBED_PERIOD_S, (
            "§9.2 cadence law: the runner must wake at least as often as "
            "every absorbed daily row")

    def test_thresholds_do_not_loosen_the_absorbed_floors(self):
        yaml_dicts = [yaml.safe_load((ORGANS_DIR / f"{n}.yml").read_text())
                      for n in COMPOSED]
        exp, errors = FL.derive_organ_expectations(yaml_dicts)
        assert errors == []
        runner_interval = int(self._runner_entry()["interval_s"])
        for name, (out, stale) in exp.items():
            assert stale <= ABSORBED_FLOOR_S, (
                f"{name}: threshold LOOSENED past the absorbed 26h floor (SF5)")
            assert stale > runner_interval, (
                f"{name}: threshold tighter than one wake period would "
                "false-page on the very first healthy cycle")

    def test_probes_are_per_organ_artifacts_never_the_runner_log(self):
        import os
        yaml_dicts = [yaml.safe_load((ORGANS_DIR / f"{n}.yml").read_text())
                      for n in COMPOSED]
        exp, _ = FL.derive_organ_expectations(yaml_dicts)
        runner_paths = {os.path.expanduser(p)
                        for p in wreg._service_log_candidates(RUNNER_ROW)}
        seen = set()
        for name, (out, _stale) in exp.items():
            norm = os.path.expanduser(out)
            assert norm not in runner_paths, f"{name}: probe is the runner log"
            assert os.path.basename(norm) not in {
                f"{RUNNER_ROW}.log", f"{RUNNER_ROW}.err",
                f"{RUNNER_ROW}.out.log", f"{RUNNER_ROW}.err.log"}
            assert out not in seen, f"{name}: duplicate probe artifact"
            seen.add(out)

    def test_state_ownership_disjoint_across_the_composed_set(self):
        from framework.organs.registry import state_ownership_collisions
        yaml_dicts = [yaml.safe_load((ORGANS_DIR / f"{n}.yml").read_text())
                      for n in COMPOSED]
        assert state_ownership_collisions(yaml_dicts) == []

    def test_entrypoints_carry_the_absorbed_commands(self):
        expected = {
            "charter-shadow": "cabinet/scripts/charter-shadow.py",
            "judge-calibration": "cabinet/scripts/judge-calibration.py",
            "prediction-calibration": "framework.fidelity.prediction_scorer",
            "preference-pairs": "framework.learning.preference_pairs",
            "world-census": "cabinet/scripts/world-census.py",
        }
        for name, needle in expected.items():
            man = yaml.safe_load((ORGANS_DIR / f"{name}.yml").read_text())
            assert needle in man["entrypoints"]["run"], (
                f"{name}: entrypoint lost the absorbed row's command")

    def test_judge_calibration_honest_failure_is_encoded(self):
        """The absorbed row's exit contract (exit 1 = bar honestly NOT met =
        the fail-closed floor WORKING) rides the manifest — §9.2's
        honest-failing health_proof."""
        man = yaml.safe_load((ORGANS_DIR / "judge-calibration.yml").read_text())
        codes = man["health_proof"]["exit_codes"]
        assert codes["ok"] == [0]
        assert codes["honest_failure"] == [1]

    def test_runner_plan_smoke_over_the_real_row(self, tmp_path):
        """--plan loads + validates the LIVE row and manifests, executes
        nothing, writes nothing (run-root = tmp proves the no-write claim)."""
        proc = subprocess.run(
            [sys.executable, str(RUNNER_CLI), "--plan",
             "--services-yml", str(SERVICES_YML),
             "--run-root", str(tmp_path)],
            capture_output=True, text=True, check=False, cwd=str(tmp_path))
        assert proc.returncode == 0, proc.stderr
        behavior = json.loads(proc.stdout)
        assert behavior["organs_selected"] == COMPOSED
        assert all(r["status"] == "planned"
                   for r in behavior["results"].values())
        assert list(tmp_path.iterdir()) == [], "--plan wrote into the run root"

    def test_manifest_paths_resolve_repo_relative(self, tmp_path):
        """The declared refs resolve under the CLI's run root — but --plan
        above already proved the LIVE resolution; here a missing declared
        manifest REFUSES (exit 2), never a partial wake."""
        bad = tmp_path / "services.yml"
        bad.write_text("services:\n  - name: cog4-organ-runner\n"
                       "    label: com.cabinet.cog4-organ-runner\n"
                       "    kind: cron\n"
                       "    schedule: { interval_s: 43200 }\n"
                       "    organs:\n"
                       "      - cabinet/config/organs/nope.yml\n",
                       encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(RUNNER_CLI), "--plan",
             "--services-yml", str(bad), "--run-root", str(tmp_path)],
            capture_output=True, text=True, check=False, cwd=str(tmp_path))
        assert proc.returncode == 2
        assert "REFUSED" in proc.stderr
