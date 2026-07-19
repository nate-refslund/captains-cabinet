"""Audit #51 + #52 — service wrapper env-SPOF + screenpipe-monitor gating.

#51: generate-plists' command wrapper chained ``cd … && … && source
cabinet/.env … && … exec {command}`` — a missing/malformed ``cabinet/.env``
made ``source`` non-zero, the ``&&`` chain short-circuited, and the service
(watchdog/doctor included) died BEFORE ``exec`` with no log. The fix decouples
the best-effort source with ``;`` (+ a ``[ -r ]`` guard); ``cd`` failure still
aborts.

#52: ``healthchecks-drill`` + ``memory-curator-health`` are hardwired to a
personal screenpipe source and shipped ENABLED, so on a box with no personal
source they alert forever. The fix marks both ``disabled: true`` — excluded
from the rendered fleet AND from the watchdog's no-silent-cron floors (so
disabling them can never manufacture a false-DEAD, the #59 class).

Run: python3.12 -m pytest cabinet/scripts/tests/test_wrapper_spof_and_monitor_gating.py -q
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "cabinet" / "scripts" / "generate-plists.py"
_SERVICES = _REPO / "cabinet" / "services.yml"
_SCREENPIPE_MONITORS = ("healthchecks-drill", "memory-curator-health")


def _load_gp():
    spec = importlib.util.spec_from_file_location("generate_plists_spof", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ===========================================================================
# #51 — a missing/malformed cabinet/.env must NOT abort the service
# ===========================================================================
def _wrapper_for(gp, root: Path, command: str) -> str:
    svc = {"name": "spoftest", "label": "com.cabinet.spoftest",
           "kind": "daemon", "command": command,
           "schedule": {"interval_s": 300}}
    return gp.render(svc, root, Path("/home/x"))["ProgramArguments"][2]


def _run(wrapper: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/bin/bash", "-lc", wrapper],
                          capture_output=True, text=True, timeout=30)


def test_absent_env_still_execs_the_service(tmp_path):
    gp = _load_gp()
    root = tmp_path / "root"
    root.mkdir()  # NO cabinet/.env at all
    out = _run(_wrapper_for(gp, root, "/bin/echo SENTINEL-EXEC-RAN"))
    assert out.returncode == 0, out.stderr
    assert "SENTINEL-EXEC-RAN" in out.stdout


def test_malformed_env_still_execs_the_service(tmp_path):
    gp = _load_gp()
    root = tmp_path / "root"
    (root / "cabinet").mkdir(parents=True)
    (root / "cabinet" / ".env").write_text('FOO="bar\nBAR=ok\n')  # unmatched quote
    out = _run(_wrapper_for(gp, root, "/bin/echo SENTINEL-EXEC-RAN"))
    assert out.returncode == 0, out.stderr
    assert "SENTINEL-EXEC-RAN" in out.stdout


def test_cd_failure_still_aborts(tmp_path):
    gp = _load_gp()
    missing = tmp_path / "does-not-exist"  # never created
    out = _run(_wrapper_for(gp, missing, "/bin/echo SENTINEL-EXEC-RAN"))
    assert out.returncode != 0
    assert "SENTINEL-EXEC-RAN" not in out.stdout


def test_wrapper_decouples_source_from_exec(tmp_path):
    """MUTANT teeth: the source must be `;`-decoupled from exec. The old SPOF
    was `… && source cabinet/.env … && … exec`; the ONLY `&&` allowed now is
    the `[ -r cabinet/.env ]` readable-guard (which short-circuits the source,
    not the whole chain). exec still ends the line."""
    gp = _load_gp()
    root = tmp_path / "root"
    root.mkdir()
    w = _wrapper_for(gp, root, "/bin/echo X")
    # the SPOF signature was source &&-CHAINED to what FOLLOWS (a failed source
    # aborted the chain before exec). The new form ;-terminates the source.
    assert "source cabinet/.env 2>/dev/null; set +a" in w
    assert "&& set +a" not in w, "old SPOF && chain still aborts before exec"
    assert "&& export" not in w and "&& REDIS_HOST=localhost exec" not in w
    assert "; REDIS_HOST=localhost exec /bin/echo X" in w
    assert w.rstrip().endswith("exec /bin/echo X")
    # the ONLY && is the readable-guard `[ -r … ] && source`, which merely
    # short-circuits the source itself, not the whole chain.
    assert w.count("&&") == 1 and "[ -r cabinet/.env ] && source" in w


# ===========================================================================
# #52 — screenpipe-hardwired monitors ship disabled + gated everywhere
# ===========================================================================
def _services():
    return yaml.safe_load(_SERVICES.read_text())["services"]


@pytest.mark.parametrize("name", _SCREENPIPE_MONITORS)
def test_screenpipe_monitor_row_is_disabled_with_reason(name):
    row = next(s for s in _services() if s["name"] == name)
    assert row.get("disabled") is True, f"{name} must ship disabled (#52)"
    assert "#52" in (row.get("disabled_reason") or ""), \
        f"{name} needs a #52 disabled_reason (parking must be documented)"


def test_screenpipe_monitors_not_rendered():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env["CABINET_ROOT"] = str(_REPO)
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), "--output-dir", td],
            capture_output=True, text=True, env=env, timeout=120)
        assert proc.returncode == 0, proc.stderr
        rendered = {p.name for p in Path(td).glob("*.plist")}
    for name in _SCREENPIPE_MONITORS:
        assert f"com.cabinet.{name}.plist" not in rendered, \
            f"{name} was rendered despite disabled: true"


def test_screenpipe_monitors_excluded_from_watchdog_floors():
    """Disabling must not manufacture a false-DEAD: the no-silent-cron floors
    must NOT expect these parked rows loaded (registry excludes `disabled`)."""
    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    from framework.watchdog import registry
    entries = registry._parse_services_manifest(_SERVICES.read_text())
    floored = {e["name"] for e in entries
               if e.get("kind") != "officer" and not e.get("disabled")}
    for name in _SCREENPIPE_MONITORS:
        row = next(e for e in entries if e["name"] == name)
        assert row["disabled"] is True          # parses as disabled...
        assert name not in floored              # ...so excluded from floors
