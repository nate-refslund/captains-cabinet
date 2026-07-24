"""COG-4 N6 — the §10 measurement surface, pre-proven OUT-OF-BAND (W6 e3).

Contract: docs/plans/cognitive-core-phase-4-contract-2026-07-23.md §10 + §1 N6.

Mirrors `test_cog4_parity_record.py`'s role. The W2 corpus battery
`test_cog4_measurement.py` carries TWO vacuity-guarded arms whose companion
assertions go RED the moment THIS unit's artifacts land — the DESIGNED tripwire
that the integrator retire those skips (corpus surgery §13; builders never edit
the corpus — the retirement routes via this unit's contradictions[]). Because a
builder cannot edit that corpus file, THIS NEW file proves — right now, GREEN —
exactly what the two retired arms will assert:

  A. VERIFY-TWIN ARM (retires test_verify_twin_arm): the twin
     `verify-cognitive-phase4.sh` consumes COG4_ENFORCE_BOUND *and* now ARMS it
     LIVE (e1's file-existence deferral discharged) — the §10.3 same-commit
     armed-consumer law / MR2. The retired arm keeps exactly "the twin consumes
     COG4_ENFORCE_BOUND"; this file proves that AND the live-arm flip.

  B. REAL-PILOT ARM (retires test_real_pilot_measurement_arm): `cog4-measure.py`
     + the dated S0 baseline artifact land; the baseline's proxies reproduce
     EXACT from the CLI over the committed composed manifests (deterministic
     across PYTHONHASHSEED), each pilot organ's FRESH measured p95 stays <=
     `wall_clock_bound(baseline p95)`, the CLI's SELF-CONTAINED bound helper is
     byte-equal to the corpus `lib_cog4_floors.wall_clock_bound` (the drift-pin
     — a CLI in the egg must not import a tests/ lib), the CLI proxy fold equals
     the corpus `test_cog4_measurement.proxies_from_schedule_rows`, and the
     §10.4 seeded-regression mutants RED (inflated cost + over-activation
     always-on; inflated p95 when armed).

Everything here is GREEN now; the two corpus arms stay RED-by-design until the
integrator's §13 surgery (recorded in this unit's contradictions[]). The corpus
reference (fold + bound) is IMPORTED, never re-defined — the gate law stays
single-sourced.

S0: python3.12, no DB, no network, file-seeded, deterministic in every
assertion (wall-clock rows are compared to a generous floor-aware bound, never
to each other). Provenance: authored per the 2026-07-07 full-autonomy grant +
the 2026-07-20 cognitive-masterplan continuous grant (COG-4 W6 e3, §10).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# corpus reference — IMPORTED verbatim, never re-defined (single-sourced law)
import lib_cog4_floors as FL  # noqa: E402
import test_cog4_measurement as CM  # noqa: E402

_MEASURE_CLI = _REPO / "cabinet" / "scripts" / "cog4-measure.py"
_TWIN = _REPO / "cabinet" / "scripts" / "verify-cognitive-phase4.sh"
_ORGANS_DIR = _REPO / "cabinet" / "config" / "organs"
_BASELINE = (_REPO / "cabinet" / "scripts" / "tests" / "fixtures" / "cog4"
             / "cog4-measure-baseline-2026-07-24.json")
_FLAG = "COG4_ENFORCE_BOUND"
_PILOT = ("charter-shadow", "judge-calibration", "prediction-calibration",
          "preference-pairs", "world-census")


def _load_cli():
    """Load the hyphenated CLI as a module (the record-test idiom)."""
    spec = importlib.util.spec_from_file_location("cog4_measure_cli",
                                                  str(_MEASURE_CLI))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_cli(args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(_MEASURE_CLI), *args],
                          capture_output=True, text=True, env=env)


CLI = _load_cli()


# ---------------------------------------------------------------------------
# A) the verify-twin arm — retires test_verify_twin_arm
# ---------------------------------------------------------------------------
class TestVerifyTwinArm:
    def test_twin_consumes_the_flag(self):
        """The retired arm's kept assertion (§10.3): the twin consumes
        COG4_ENFORCE_BOUND — the same-commit armed-consumer law."""
        assert _TWIN.exists(), f"the verify twin must exist at {_TWIN}"
        text = _TWIN.read_text(encoding="utf-8")
        assert _FLAG in text, (
            f"{_TWIN.name} landed WITHOUT consuming {_FLAG} — the §10.3 "
            f"same-commit armed-consumer law (the phantom-M6 class)")

    def test_twin_arms_the_flag_live(self):
        """W6-e3 flip: the deferral is discharged — the twin EXPORTS the flag
        unconditionally (no more `if [ -f cog4-measure.py ]` gate) and runs the
        real measure check against the S0 baseline."""
        text = _TWIN.read_text(encoding="utf-8")
        assert f"export {_FLAG}=1" in text, (
            "the twin must ARM the flag live (export COG4_ENFORCE_BOUND=1) — "
            "e1's file-existence deferral is discharged in W6-e3")
        assert "cog4-measure.py --check" in text, (
            "the armed leg must run the REAL measurement check "
            "(cog4-measure.py --check) against the S0 baseline")
        assert 'if [ -f "cabinet/scripts/cog4-measure.py" ]' not in text, (
            "the file-existence deferral gate must be gone — the CLI has landed")

    def test_corpus_arm_is_red_by_design_until_surgery(self):
        """Document the DESIGNED state: the corpus arm test_verify_twin_arm goes
        RED (pytest.fail 'retire this vacuity skip') because the twin exists and
        carries the flag — that RED is the integrator's retire signal, recorded
        in this unit's contradictions[]. Prove the trigger condition holds."""
        assert _TWIN.exists() and _FLAG in _TWIN.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# B) the real-pilot arm — retires test_real_pilot_measurement_arm
# ---------------------------------------------------------------------------
class TestBaselineArtifact:
    def test_baseline_exists_and_is_well_shaped(self):
        assert _MEASURE_CLI.exists(), "cog4-measure.py must have landed"
        assert _BASELINE.exists(), (
            f"the dated S0 baseline artifact must be tracked at {_BASELINE}")
        b = json.loads(_BASELINE.read_text(encoding="utf-8"))
        assert b.get("schema") == "cog4-measure-baseline/v1"
        assert sorted(b["pilot_organs"]) == sorted(_PILOT)
        for cap_key in ("activations", "activations_by_capability",
                        "budget_units_total"):
            assert cap_key in b["proxies"], cap_key
        assert set(b["wall_clock_p95_s"]) == set(_PILOT), (
            "the baseline must carry a per-organ p95 for EVERY pilot organ "
            "(no borrowed numbers — §10.1)")
        for name, p95 in b["wall_clock_p95_s"].items():
            assert isinstance(p95, (int, float)) and p95 >= 0, (name, p95)

    def test_baseline_is_the_sole_tracked_baseline(self):
        """The retired arm loads THE baseline (singular) — prove exactly one
        dated cog4-measure baseline is tracked, and it is ours."""
        fx = _REPO / "cabinet" / "scripts" / "tests" / "fixtures" / "cog4"
        found = sorted(p for p in fx.glob("cog4-measure-baseline-*.json"))
        assert found == [_BASELINE], (
            f"expected exactly one tracked baseline at {_BASELINE}, found {found}")


class TestProxiesReproduceExact:
    def test_cli_reproduces_the_baseline_proxies(self):
        """The retired arm binds the real schedule-artifact proxies to the S0
        baseline: the CLI, folding the CURRENT composed manifests, reproduces
        the baseline proxies EXACTLY (deterministic — §10.2 EXACT tolerance)."""
        proc = _run_cli(["--json"])
        assert proc.returncode == 0, proc.stderr
        record = json.loads(proc.stdout)
        baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
        assert record["proxies"] == baseline["proxies"], (
            "CLI proxies over the committed manifests != the tracked baseline "
            "proxies — a manifest changed without regenerating the baseline")

    def test_proxies_deterministic_across_hashseeds(self):
        """N1 determinism discipline on the proxy fold: byte-identical proxies
        across three PYTHONHASHSEED values (wall-clock is measured, so only the
        deterministic proxies are compared)."""
        seen = []
        for seed in ("0", "1", "2"):
            proc = _run_cli(["--json", "--samples", "1"],
                            env_extra={"PYTHONHASHSEED": seed})
            assert proc.returncode == 0, proc.stderr
            seen.append(json.dumps(json.loads(proc.stdout)["proxies"],
                                   sort_keys=True))
        assert len(set(seen)) == 1, f"non-deterministic proxies: {seen}"
        baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
        assert json.loads(seen[0]) == baseline["proxies"]

    def test_cli_fold_equals_corpus_reference(self):
        """The CLI proxy fold IS the corpus reference fold (single-sourced law):
        equal on the corpus fixture rows AND on the real measurement rows."""
        assert CLI.proxies_from_schedule_rows(CM._FIXTURE_ROWS) \
            == CM.proxies_from_schedule_rows(CM._FIXTURE_ROWS) \
            == CM._FIXTURE_BASELINE
        manifests = CLI.load_organ_manifests(_ORGANS_DIR)
        rows = CLI.build_measurement_schedule(manifests)
        assert CLI.proxies_from_schedule_rows(rows) \
            == CM.proxies_from_schedule_rows(rows)


class TestWallClockBoundBinding:
    def test_drift_pin_bound_equals_corpus_helper(self):
        """The CLI's SELF-CONTAINED bound is byte-equal to the corpus
        lib_cog4_floors.wall_clock_bound (the drift-tripwire idiom — one
        formula, proven identical; the egg CLI imports no tests/ lib)."""
        for x in (0.0, 0.005, 2.0, 9.99, 10.0, 40.0, 0.001, 0.5, 3.0,
                  9.999, 100.0, 12.34, 5.0):
            assert CLI.wall_clock_bound(x) == FL.wall_clock_bound(x), x
        for bad in (-1.0, True, "2.0"):
            with pytest.raises(ValueError):
                CLI.wall_clock_bound(bad)  # type: ignore[arg-type]
            with pytest.raises(ValueError):
                FL.wall_clock_bound(bad)  # type: ignore[arg-type]

    def test_measured_p95_within_bound_per_organ(self):
        """The retired arm binds each row's measured p95 to wall_clock_bound:
        a FRESH per-organ measurement stays within the frozen-baseline bound
        (the floor-aware +5s guarantee makes sub-10s rows honest tripwires)."""
        baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))["wall_clock_p95_s"]
        measured = CLI.measure_wall_clock(_ORGANS_DIR, samples=CLI.DEFAULT_SAMPLES)
        assert set(measured) == set(_PILOT)
        assert CLI.wall_clock_violations(measured, baseline) == [], (
            "a fresh pilot measurement exceeded the S0 floor-aware bound — "
            "unexpected on any reasonable host (bound >= p95 + 5s for sub-10s)")

    def test_wall_clock_missing_baseline_row_is_a_violation(self):
        """No borrowed numbers (§10.1): a measured row with no baseline REDs."""
        v = CLI.wall_clock_violations({"new-organ": 1.0}, {"charter-shadow": 2.0})
        assert v and "no S0 baseline" in v[0]


class TestArmedCheckLive:
    def test_check_armed_passes_clean_over_the_real_pilot(self):
        """Exactly what the twin runs: `cog4-measure.py --check` armed against
        the tracked baseline over the real composed manifests — exit 0."""
        proc = _run_cli(["--check", "--baseline-file", str(_BASELINE)],
                        env_extra={_FLAG: "1"})
        assert proc.returncode == 0, (
            f"armed --check failed clean\nSTDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}")

    def test_check_unarmed_runs_proxies_and_declares_the_skip(self):
        """§10.5 honesty: unarmed, proxies are checked (always-on) and the
        wall-clock tripwire is a DECLARED skip — still exit 0 clean."""
        env = dict(os.environ)
        env.pop(_FLAG, None)
        proc = subprocess.run(
            [sys.executable, str(_MEASURE_CLI), "--check",
             "--baseline-file", str(_BASELINE)],
            capture_output=True, text=True, env=env)
        assert proc.returncode == 0, proc.stderr
        assert "DECLARED skip" in proc.stderr


class TestSeededRegressionMutants:
    """§10.4 negative controls — the seeded regression fixtures RED."""

    def _mutant_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "organs"
        d.mkdir()
        for f in sorted(_ORGANS_DIR.glob("*.yml")):
            shutil.copy(f, d / f.name)
        return d

    def test_inflated_cost_model_reds_always_on(self, tmp_path):
        """An organ manifest with an inflated cost model REDs on the exact
        budget proxy — no env flag (proxies are always-on, §10.5)."""
        d = self._mutant_dir(tmp_path)
        wc = d / "world-census.yml"
        wc.write_text(wc.read_text().replace("units_per_wake: 1",
                                             "units_per_wake: 800"))
        proc = _run_cli(["--check", "--baseline-file", str(_BASELINE),
                         "--organs-dir", str(d)])
        assert proc.returncode == 1, proc.stdout
        assert "inflated cost" in proc.stderr, proc.stderr
        assert "over-activation" not in proc.stderr  # only the budget leg fires

    def test_over_activation_reds_always_on(self, tmp_path):
        """An extra composed organ (a fold admitting an over-activation plan)
        REDs on the activation proxy — always-on."""
        d = self._mutant_dir(tmp_path)
        extra = d / "extra-organ.yml"
        extra.write_text(
            (d / "charter-shadow.yml").read_text()
            .replace("name: charter-shadow", "name: extra-organ")
            .replace("charter/shadow.measure", "extra/op.measure")
            .replace("charter/series.append", "extra/op.append"))
        proc = _run_cli(["--check", "--baseline-file", str(_BASELINE),
                         "--organs-dir", str(d)])
        assert proc.returncode == 1, proc.stdout
        assert "over-activation" in proc.stderr, proc.stderr

    def test_inflated_p95_reds_when_armed(self):
        """The seeded inflated-p95 mutant REDs when armed (the wall-clock
        tripwire) and the in-bound row stays clean — the exact corpus
        TestWallClockTripwire semantic, on the CLI's own violation fn."""
        base = {"undo-sweep": 2.0, "world-census": 12.0}
        v = CLI.wall_clock_violations({"undo-sweep": 8.0, "world-census": 12.5},
                                      base)
        assert any(x.startswith("undo-sweep:") and "exceeds bound" in x
                   for x in v), v
        assert not any(x.startswith("world-census:") for x in v), v
        assert CLI.wall_clock_violations({"undo-sweep": 6.9,
                                          "world-census": 14.9}, base) == []
