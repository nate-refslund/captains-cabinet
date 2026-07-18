"""setup-mac.sh Step 3 survives a PEP-668 externally-managed python (fresh-
hatch #56).

Stock Homebrew python@3.12 REFUSES a bare `pip install` (externally-managed).
Before the fix, Step 3 ran `pip install ... 2>/dev/null` and only WARNed on
failure — so the hatch continued with no deps and died later at `import yaml`,
the reason swallowed. The fix retries with --break-system-packages, verifies by
import, and on total failure fails LOUD (surfacing pip's real stderr) + records
an ISSUE.

Dynamic: we extract the real Step-3 block from setup-mac.sh, stub the ok/warn/
fail/ISSUES helpers, and PATH-shim a fake `python3.12` whose bare install is
PEP-668-refused and only succeeds with --break-system-packages. Two modes:
  * fallback  — bare refused, --break succeeds, import verifies -> "installed";
  * allfail   — every install refused, import fails -> loud fail + pip stderr
                surfaced (not swallowed) + an ISSUES entry appended.
Plus static pins on the shipped script.

Run: python3.12 -m pytest cabinet/scripts/tests/test_setup_mac_pep668_fallback.py -q
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SETUP = REPO_ROOT / "cabinet" / "scripts" / "setup-mac.sh"

_PEP668_MSG = "error: externally-managed-environment (PEP 668)"


def _step3_block() -> str:
    """The exact Step-3 body from the shipped script: from `PIP_DEPS=(` through
    the closing `fi` of the import-verify branch (excludes the Step 3.5 echo)."""
    text = SETUP.read_text(encoding="utf-8")
    i = text.index("PIP_DEPS=(pyyaml")
    j = text.index("=== Step 3.5", i)
    block = text[i:j]
    return block[: block.rindex("\nfi") + 3]


_STUB_PREFIX = (
    "set -euo pipefail\n"
    'PYBIN="python3.12"\n'
    "ISSUES=()\n"
    'ok()   { echo "STUB_OK: $1"; }\n'
    'warn() { echo "STUB_WARN: $1"; }\n'
    'fail() { echo "STUB_FAIL: $1"; }\n'
)
# bash 3.2: only expand a possibly-empty array when non-empty (set -u safe).
_STUB_SUFFIX = (
    '\nif [ "${#ISSUES[@]}" -gt 0 ]; then '
    'printf "STUB_ISSUE: %s\\n" "${ISSUES[@]}"; fi\n'
)


def _shim_python312(tmp_path: Path, mode: str) -> Path:
    """A fake `python3.12`: `-m pip install` is PEP-668-refused unless (mode
    'fallback' and) --break-system-packages is present; `-c` import verify
    passes only in 'fallback'."""
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    log = tmp_path / "shim.log"
    py = shim_dir / "python3.12"
    py.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        'case "$*" in\n'
        '  *"-m pip install"*)\n'
        f'    if [ "{mode}" = "fallback" ] && '
        'printf "%s" "$*" | grep -q -- --break-system-packages; then exit 0; fi\n'
        f'    printf "{_PEP668_MSG}\\n" >&2\n'
        "    exit 1 ;;\n"
        "  *)\n"
        f'    [ "{mode}" = "fallback" ] && exit 0 || exit 1 ;;\n'
        "esac\n",
        encoding="utf-8")
    py.chmod(0o755)
    return shim_dir


def _run_step3(tmp_path: Path, mode: str) -> subprocess.CompletedProcess:
    shim_dir = _shim_python312(tmp_path, mode)
    harness = _STUB_PREFIX + _step3_block() + _STUB_SUFFIX
    env = {"PATH": f"{shim_dir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    return subprocess.run(
        ["bash", "-c", harness],
        capture_output=True, text=True, env=env, timeout=60)


# --------------------------------------------------------------------------
# Dynamic
# --------------------------------------------------------------------------

def test_pep668_fallback_installs_via_break_system_packages(tmp_path):
    p = _run_step3(tmp_path, "fallback")
    assert p.returncode == 0, p.stderr
    out = p.stdout + p.stderr
    assert "STUB_OK: Python deps installed" in out, out
    assert "STUB_FAIL" not in out, out
    # the fallback was actually TAKEN (a --break-system-packages install ran)
    log = (tmp_path / "shim.log").read_text(encoding="utf-8")
    assert "--break-system-packages" in log, log


def test_total_failure_is_loud_not_swallowed(tmp_path):
    p = _run_step3(tmp_path, "allfail")
    out = p.stdout + p.stderr
    assert "STUB_FAIL: Python deps NOT installed" in out, out
    # pip's real reason is SURFACED (was swallowed by 2>/dev/null before)
    assert "pip stderr:" in out, out
    assert "PEP 668" in out, out
    # and an actionable ISSUE was recorded for the end-of-run summary
    assert "STUB_ISSUE: python deps missing" in out, out


# --------------------------------------------------------------------------
# Static pins on the shipped script
# --------------------------------------------------------------------------

def test_script_has_break_system_packages_fallback():
    text = SETUP.read_text(encoding="utf-8")
    assert "--break-system-packages" in text
    block = _step3_block()
    # stderr is CAPTURED for surfacing (2>&1 1>/dev/null), never discarded to
    # /dev/null the way the old swallowing install did.
    assert "2>&1 1>/dev/null" in block, block
    assert "pip stderr:" in block, block
    assert 'fail "Python deps NOT installed' in block, block
    assert "ISSUES+=(" in block, block
    # the old warn-only, reason-swallowing shape is gone
    assert 'pip install --quiet pyyaml psycopg2-binary requests pytest 2>/dev/null' not in text
