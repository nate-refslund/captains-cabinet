"""Tests for the COG-2 shadow-parity WIRING (COG-2 UNIT 5, Lane C).

Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §53 (the parity
invocation is added INSIDE task-sync-drift-falsifier.py — `services.yml` stays
BYTE-IDENTICAL, G-F7) + §8 sim 6 (doctor-probed).

Pins the wiring contract (NOT the parity math — that is test_cog2_parity.py):
  * task-sync-drift-falsifier main() invokes run_cog2_parity() on its default
    nightly path (the COG-2 parity cycle rides the EXISTING falsifier cadence)
    and a COG-2 breach propagates into main's exit code;
  * run_cog2_parity() invokes cog2-parity-falsifier.py as an EXTERNAL SUBPROCESS
    (the house interpreter + the sibling script, default mode), propagates the
    child's returncode, and is an honest no-op (exit 0) when the subprocess
    cannot be launched (sibling absent / interpreter missing / timeout) —
    exactly as run_cog1_parity no-ops when its pilot never armed;
  * task-sync-drift-falsifier.py imports NO cortex module (the import ban rides
    in the CHILD's own process; the parent stays adapter/framework-free);
  * services.yml gains NO cog2-parity row — parity runs on the task-sync-drift
    row that already exists (G-F7 byte-identical intent, encoded as content);
  * cabinet-doctor surfaces the cog2-parity health token via the falsifier's
    --probe (§8 sim 6 doctor-probed), and that --probe emits a real token.
"""
from __future__ import annotations

import importlib.util as _ilu
import subprocess
import sys
import types
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_REPO = Path(__file__).resolve().parents[3]
_TSD_SCRIPT = _SCRIPTS / "task-sync-drift-falsifier.py"
_COG2_SCRIPT = _SCRIPTS / "cog2-parity-falsifier.py"
_SERVICES_YML = _REPO / "cabinet" / "services.yml"
_DOCTOR = _SCRIPTS / "cabinet-doctor.sh"

# hyphenated filename — load via importlib (the house pattern, cf.
# test_task_sync_drift_falsifier.py).
_spec = _ilu.spec_from_file_location("task_sync_drift_falsifier", _TSD_SCRIPT)
tsd = _ilu.module_from_spec(_spec)
sys.modules["task_sync_drift_falsifier"] = tsd
_spec.loader.exec_module(tsd)


class TestMainWiring:
    def test_main_default_path_invokes_run_cog2_parity(self, monkeypatch):
        """The default nightly run calls run_cog2_parity (rides the existing
        falsifier cadence — no new services row)."""
        called = {"cog2": 0}
        monkeypatch.setattr(tsd, "run", lambda: 0)
        monkeypatch.setattr(tsd, "run_cog1_parity", lambda: 0)

        def _fake_cog2() -> int:
            called["cog2"] += 1
            return 0

        monkeypatch.setattr(tsd, "run_cog2_parity", _fake_cog2)
        assert tsd.main([]) == 0
        assert called["cog2"] == 1

    def test_cog2_breach_propagates_into_main_exit(self, monkeypatch):
        """A COG-2 parity breach (child rc=1) surfaces in main's exit code, the
        same way a COG-1 breach does (rc_drift or rc_cog1 or rc_cog2)."""
        monkeypatch.setattr(tsd, "run", lambda: 0)
        monkeypatch.setattr(tsd, "run_cog1_parity", lambda: 0)
        monkeypatch.setattr(tsd, "run_cog2_parity", lambda: 1)
        assert tsd.main([]) == 1

    def test_probe_path_does_not_run_cog2(self, monkeypatch):
        """--probe is pure file inspection: it must NOT invoke the cog2 cycle."""
        called = {"cog2": 0}
        monkeypatch.setattr(tsd, "probe", lambda: 0)
        monkeypatch.setattr(
            tsd, "run_cog2_parity",
            lambda: called.__setitem__("cog2", called["cog2"] + 1) or 0)
        assert tsd.main(["--probe"]) == 0
        assert called["cog2"] == 0

    def test_cog2_parity_flag_runs_only_cog2(self, monkeypatch):
        """--cog2-parity runs the cog2 cycle standalone (mirrors --cog1-parity):
        neither the drift run nor the cog1 read fires on that path."""
        seen = {"drift": 0, "cog1": 0, "cog2": 0}
        monkeypatch.setattr(
            tsd, "run", lambda: seen.__setitem__("drift", 1) or 0)
        monkeypatch.setattr(
            tsd, "run_cog1_parity",
            lambda: seen.__setitem__("cog1", 1) or 0)
        monkeypatch.setattr(
            tsd, "run_cog2_parity",
            lambda: seen.__setitem__("cog2", seen["cog2"] + 1) or 0)
        assert tsd.main(["--cog2-parity"]) == 0
        assert seen == {"drift": 0, "cog1": 0, "cog2": 1}


class TestRunCog2ParitySubprocess:
    def _fake_completed(self, rc: int):
        return types.SimpleNamespace(
            returncode=rc, stdout="cog2-parity: ok — 0 sampled\n", stderr="")

    def test_invokes_sibling_as_subprocess_default_mode(self, monkeypatch):
        """The wrapper shells out to the house interpreter + the sibling
        cog2-parity-falsifier.py in DEFAULT mode (one parity cycle) — never an
        in-process import."""
        seen = {}

        def _fake_run(argv, **kw):
            seen["argv"] = argv
            seen["kw"] = kw
            return self._fake_completed(0)

        monkeypatch.setattr(tsd.subprocess, "run", _fake_run)
        assert tsd.run_cog2_parity() == 0
        argv = seen["argv"]
        assert argv[0] == sys.executable
        assert argv[-1].endswith("cog2-parity-falsifier.py")
        # default mode: no subcommand/flag appended (a bare parity cycle)
        assert not any(a.startswith("--") for a in argv[1:])
        # the resolved sibling is the real script on disk
        assert Path(argv[-1]).resolve() == _COG2_SCRIPT.resolve()

    def test_child_returncode_propagates(self, monkeypatch):
        monkeypatch.setattr(
            tsd.subprocess, "run", lambda argv, **kw: self._fake_completed(1))
        assert tsd.run_cog2_parity() == 1

    def test_launch_failure_is_honest_no_op(self, monkeypatch):
        """Sibling absent / interpreter missing (OSError) → exit 0, never a
        false breach — mirrors run_cog1_parity's absent-pilot no-op."""
        def _boom(argv, **kw):
            raise FileNotFoundError("no such script")

        monkeypatch.setattr(tsd.subprocess, "run", _boom)
        assert tsd.run_cog2_parity() == 0

    def test_timeout_is_loud_breach(self, monkeypatch):
        """A CONFIGURED child that HANGS past the ceiling is a STUCK watchdog,
        not a launch failure — it exits 1 (loud), so a wedged reader can never
        mute the watchdog behind a momentary green. Distinct from the OSError
        launch-failure no-op above (sibling absent / interpreter missing = 0)."""
        def _slow(argv, **kw):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=1)

        monkeypatch.setattr(tsd.subprocess, "run", _slow)
        assert tsd.run_cog2_parity() == 1

    def test_no_cortex_import_in_parent_process(self, monkeypatch):
        """Invoking the wrapper must not drag framework.cortex into THIS
        process (the import ban rides in the child). Asserted as a DELTA — the
        wrapper adds NO cortex module — so a sibling suite that legitimately
        imports the engine in-process cannot make this check ordering-fragile."""
        def _cortex_mods():
            return {m for m in list(sys.modules)
                    if m == "framework.cortex" or m.startswith("framework.cortex.")}
        before = _cortex_mods()
        monkeypatch.setattr(
            tsd.subprocess, "run", lambda argv, **kw: self._fake_completed(0))
        tsd.run_cog2_parity()
        assert _cortex_mods() <= before


class TestImportBanSource:
    def test_task_sync_drift_source_has_no_cortex_import(self):
        """Grep backstop: the falsifier file never imports a cortex module (the
        cog2 projection is only ever reached as an external subprocess)."""
        src = _TSD_SCRIPT.read_text()
        assert "framework.cortex" not in src
        assert "import cortex" not in src


class TestServicesYmlByteIdentical:
    def test_no_cog2_parity_services_row(self):
        """G-F7: cog2 parity adds NO services.yml row — it rides the EXISTING
        task-sync-drift falsifier row (byte-identical intent, encoded as
        content so it survives independent of git state)."""
        yml = _SERVICES_YML.read_text()
        assert "cog2-parity-falsifier" not in yml, (
            "services.yml must stay byte-identical — cog2 parity rides the "
            "task-sync-drift row, it does NOT get its own services row (G-F7)")
        assert "task-sync-drift-falsifier.py" in yml, (
            "the existing task-sync-drift falsifier row must still be present — "
            "the cadence cog2 parity rides on")


class TestDoctorProbe:
    def test_doctor_invokes_cog2_probe(self):
        """§8 sim 6 doctor-probed: cabinet-doctor invokes the cog2 falsifier's
        --probe and labels the finding, exactly like the task-sync-drift and
        other falsifier probes."""
        doctor = _DOCTOR.read_text()
        assert "cog2-parity-falsifier.py --probe" in doctor
        assert "cog2-parity" in doctor  # the human-readable finding label

    def test_cog2_probe_emits_a_token(self, tmp_path, monkeypatch):
        """The token surface the doctor consumes actually exists: --probe on a
        box with no ledger prints exactly NOFILE (pure file inspection, exit
        0)."""
        root = tmp_path / "cabroot"
        (root / "cabinet" / "logs").mkdir(parents=True)
        env = {
            "CABINET_ROOT": str(root),
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
        }
        result = subprocess.run(
            [sys.executable, str(_COG2_SCRIPT), "--probe"],
            capture_output=True, text=True, timeout=60, env=env)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "NOFILE"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
