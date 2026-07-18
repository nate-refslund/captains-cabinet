"""TZ-unification hardening (fix pass, 2026-07-18).

Two teeth this pins:

  * The launchd wrappers' one-line ``captain_timezone`` extract MUST quote-strip
    the YAML value. A quoted ``captain_timezone: "Europe/Berlin"`` (the deploy
    runbook's own shape) otherwise leaks the quotes into ``CABINET_CAPTAIN_TZ``,
    ``ZoneInfo('"Europe/Berlin"')`` raises, and the gate silently falls back to
    UTC — the exact two-clocks split the TZ-unification lane set out to kill.
    The extraction line is read FROM each script on disk and executed against a
    tmp fixture, so a reverted ``tr -d`` reddens this test.
  * ``generate-plists.py`` warns loudly (never fails) when the MACHINE timezone
    differs from the Captain timezone — launchd fires ``StartCalendarInterval``
    machine-local, so a clean-room hatch on a UTC clock with a Berlin Captain
    would otherwise fire briefings 2h off, silently.

Hermetic: fixture bodies are written to files (never interpolated into the
shell), the wrappers' own lines run via ``bash -c`` with fixture-root vars set,
and generate-plists is imported by path (its ``__main__`` guard keeps ``main``
from running on import).
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Every launchd wrapper (and the manual org-health-audit) that reads
# captain_timezone out of platform.yml with a one-line grep|awk. Each roots the
# read on a different shell var, so the harness sets them all.
TZ_SCRIPTS = (
    "cabinet/scripts/run-frontdoor-briefing.sh",
    "cabinet/scripts/run-outcome-watchdog.sh",
    "cabinet/scripts/start-inbound-poller.sh",
    "cabinet/cron/surface-pin-tick.sh",
    "cabinet/scripts/org-health-audit.sh",
)

_EXTRACT_RE = re.compile(r"^CAPTAIN_TZ_LINE=.*$", re.MULTILINE)


def _extract_line(rel: str) -> str:
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    m = _EXTRACT_RE.search(text)
    assert m, f"{rel}: no CAPTAIN_TZ_LINE= extraction line found"
    return m.group(0)


def _run_extract(rel: str, root: Path) -> str:
    """Run the REAL extraction line from ``rel`` against a fixture root and echo
    the value the wrapper would export into CABINET_CAPTAIN_TZ."""
    line = _extract_line(rel)
    snippet = (
        f'ROOT="{root}"\nREPO_ROOT="{root}"\nCABINET_ROOT="{root}"\n'
        f'{line}\nprintf %s "$CAPTAIN_TZ_LINE"\n'
    )
    proc = subprocess.run(["bash", "-c", snippet],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _write_platform(root: Path, body: str) -> None:
    (root / "instance" / "config").mkdir(parents=True, exist_ok=True)
    (root / "instance" / "config" / "platform.yml").write_text(
        body, encoding="utf-8")


@pytest.mark.parametrize("rel", TZ_SCRIPTS)
@pytest.mark.parametrize("body,expected", [
    ('captain_timezone: "Europe/Berlin"\n', "Europe/Berlin"),   # runbook shape
    ("captain_timezone: 'Europe/Berlin'\n", "Europe/Berlin"),   # single-quoted
    ("captain_timezone: Europe/Berlin\n", "Europe/Berlin"),     # bare
    ("captain_timezone: America/New_York   # inline\n", "America/New_York"),
])
def test_wrapper_extract_strips_quotes_and_loads(rel, body, expected, tmp_path):
    root = tmp_path / rel.replace("/", "_")
    root.mkdir()
    _write_platform(root, body)
    got = _run_extract(rel, root)
    assert got == expected, f"{rel}: extracted {got!r}, expected {expected!r}"
    ZoneInfo(got)   # must be a loadable IANA zone — no leaked quotes


def _load_generate_plists():
    spec = importlib.util.spec_from_file_location(
        "generate_plists_mod", REPO_ROOT / "cabinet/scripts/generate-plists.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMachineTzGuard:
    def test_real_offset_mismatch_warns_naming_both_zones(self):
        """A genuine wall-clock divergence (UTC machine vs Berlin Captain — the
        clean-room-hatch case) warns and names both zones."""
        gp = _load_generate_plists()
        msg = gp._machine_tz_mismatch_warn("Europe/Berlin", "UTC")
        assert "Europe/Berlin" in msg and "UTC" in msg
        assert "machine" in msg.lower()

    def test_same_name_is_silent(self):
        gp = _load_generate_plists()
        assert gp._machine_tz_mismatch_warn("Europe/Berlin", "Europe/Berlin") == ""

    def test_same_offset_different_name_is_silent(self):
        """The live box's real pairing: machine Europe/Copenhagen, Captain
        Europe/Berlin — distinct IANA names, identical CET/CEST offset, so the
        briefings fire at the right wall clock. Must NOT false-alarm."""
        gp = _load_generate_plists()
        assert gp._machine_tz_mismatch_warn("Europe/Berlin", "Europe/Copenhagen") == ""

    def test_unknown_host_or_captain_is_silent(self):
        gp = _load_generate_plists()
        assert gp._machine_tz_mismatch_warn("Europe/Berlin", None) == ""
        assert gp._machine_tz_mismatch_warn(None, "UTC") == ""

    def test_host_iana_tz_is_str_or_none(self):
        gp = _load_generate_plists()
        val = gp._host_iana_tz()
        assert val is None or isinstance(val, str)
