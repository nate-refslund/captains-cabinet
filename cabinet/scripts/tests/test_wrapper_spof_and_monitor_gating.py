"""Audit #51 + #52 — service wrapper env-SPOF + screenpipe-monitor gating.

#51: generate-plists' command wrapper chained ``cd … && … && source
cabinet/.env … && … exec {command}`` — a missing/malformed ``cabinet/.env``
made ``source`` non-zero, the ``&&`` chain short-circuited, and the service
(watchdog/doctor included) died BEFORE ``exec`` with no log. The fix decouples
the best-effort source with ``;`` (+ a ``[ -r ]`` guard); ``cd`` failure still
aborts.

#52: ``healthchecks-drill`` + ``memory-curator-health`` were hardwired to a
personal screenpipe source and shipped ENABLED, so on a box with no personal
source they alert forever. The fix marked both ``disabled: true`` — excluded
from the rendered fleet AND from the watchdog's no-silent-cron floors (so
disabling them can never manufacture a false-DEAD, the #59 class).

#52 UPDATE 2026-07-26 (Captain arm-the-cabinet ruling): ``healthchecks-drill``
was RE-POINTED off the personal sensor onto the cabinet's own hourly dead-man
and enabled, so it is no longer a member of the parked set. The #52 PROPERTY is
not relaxed — it is machine-checked on the newly-enabled row instead of assumed:
``test_drill_carries_no_personal_source_coupling`` reads the drill's default
target constants out of the AST and REDs if either one ever points back at a
personal source while the row is enabled, and
``test_drill_is_credless_safe`` proves the surviving cries-wolf path (no
healthchecks keys) exits 0 with a DRILL_SKIP line instead of paging weekly.
``memory-curator-health`` stays parked and stays in the list.

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
# Rows still hardwired to a personal source: they must ship parked.
# healthchecks-drill LEFT this set 2026-07-26 (re-pointed at the cabinet's own
# ledger-liveness dead-man) — its replacement guards are the two tests at the
# bottom of this file, which are strictly stronger than membership here.
_SCREENPIPE_MONITORS = ("memory-curator-health",)
_DRILL = Path(__file__).resolve().parents[3] / "cabinet" / "scripts" / "healthchecks-drill.py"


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


# ===========================================================================
# #52 successor guards — the RE-POINTED drill (2026-07-26 Captain ruling)
# ===========================================================================
def test_drill_carries_no_personal_source_coupling():
    """The drill may only ship ENABLED while its defaults name a CABINET-owned
    target. Re-pointing it back at a personal sensor without re-parking the row
    is exactly the #52 regression, so it REDs here."""
    import ast
    row = next(s for s in _services() if s["name"] == "healthchecks-drill")
    tree = ast.parse(_DRILL.read_text())
    defaults = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id in ("TARGET_SLUG", "WATCHDOG_LABEL"):
                # os.environ.get(NAME, "default") — the default is arg 2.
                assert isinstance(node.value, ast.Call), \
                    f"{tgt.id} must stay env-overridable with an explicit default"
                assert len(node.value.args) == 2, f"{tgt.id} needs a literal default"
                defaults[tgt.id] = ast.literal_eval(node.value.args[1])
    assert set(defaults) == {"TARGET_SLUG", "WATCHDOG_LABEL"}, defaults
    if not row.get("disabled"):
        for name, value in defaults.items():
            assert "screenpipe" not in value.lower(), (
                f"healthchecks-drill is ENABLED but {name} defaults to a personal "
                f"source ({value!r}) — #52 regression; re-park the row or re-point it")
        assert defaults["WATCHDOG_LABEL"].startswith("com.cabinet."), defaults
        target = defaults["TARGET_SLUG"]
        owner = defaults["WATCHDOG_LABEL"].split("com.cabinet.", 1)[1]
        assert any(s["name"] == owner and not s.get("disabled") for s in _services()), (
            f"drill kickstarts {owner!r}, which is not an enabled services.yml row — "
            f"the recovery leg would fail every week")
        assert target, "drill target slug must not be empty"


def test_drill_is_credless_safe(tmp_path):
    """No healthchecks keys = no external dead-man to drill. That is an honest
    absence: one DRILL_SKIP line, exit 0 — never a weekly page (#52's surviving
    cries-wolf path). Runs a COPY in a tmp tree so no live cabinet/.env is read
    and no network call can happen (main() returns before any request)."""
    dest = tmp_path / "cabinet" / "scripts" / "healthchecks-drill.py"
    dest.parent.mkdir(parents=True)
    dest.write_text(_DRILL.read_text())
    env = dict(os.environ)
    env["HOME"] = str(tmp_path / "home")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, str(dest)], capture_output=True,
                          text=True, env=env, timeout=120)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "DRILL_SKIP" in proc.stdout
