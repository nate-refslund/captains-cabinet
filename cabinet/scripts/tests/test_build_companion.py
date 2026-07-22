"""Contract tests for the menu-bar companion (Wave D / D1 — DESIGN-companion-2026-07-10 §11).

Always-runnable half (no build, no network, no Redis writes):

  * test_source_doctrine_greps — doctrine pins over cabinet/companion/main.swift:
    orchestrate-never-reimplement (no direct killswitch SET/DEL in either the
    single-string or the house argv-array form — "SET"/"DEL" string literals
    are forbidden outright and every redisArgv( call must open with a literal
    PING/GET, occurrence-counted so no call shape can evade; no launchctl),
    loopback-only (every http(s):// literal is 127.0.0.1; no all-interfaces
    address), docker-residue neutralized (loopback REDIS_URL pinned adjacent
    to the kill-switch.sh call site; no docker-era redis URL), typed-confirm
    literals present, Launch-Services-only Terminal launches (no AppleScript
    bridges), and — F1 — the companion is BIND-AGNOSTIC: none of the three
    dashboard bind variable names may appear in main.swift. Those names are
    assembled by concatenation below so they appear in no repo file at all.
  * test_info_plist_contract — LSUIElement + stable bundle identifier.
  * test_egg_manifest_rows — the three §3 expect-present rows exist in
    cabinet/scripts/egg-export-manifest.txt (fail-loud packaging pin).

Build half (skips honestly when swiftc is absent — e.g. CI):

  * test_build_produces_bundle — build-companion.sh assembles the bundle.
  * test_adhoc_signature_no_quarantine — codesign verifies, adhoc, and the
    locally built bundle carries no quarantine xattr (no Gatekeeper dance).
  * test_smoke_mode — the built binary's --smoke one-shot prints
    ^STATE=(GREEN|AMBER|RED|PAUSED|OFF) reason= and exits 0 (any HONEST
    state passes, so the gate works on un-hatched Macs too).

Run shape mirrors the sibling script tests: subprocess against the real
script with real bash; Redis is only ever READ (PING/GET) by --smoke.
"""
from __future__ import annotations

import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
COMPANION_DIR = REPO / "cabinet" / "companion"
MAIN = COMPANION_DIR / "main.swift"
PLIST = COMPANION_DIR / "Info.plist"
BUILD = REPO / "cabinet" / "scripts" / "build-companion.sh"
MANIFEST = REPO / "cabinet" / "scripts" / "egg-export-manifest.txt"
APP = REPO / "bin" / "Cabinet Companion.app"
BIN = APP / "Contents" / "MacOS" / "cabinet-companion"

# The egg-export manifest is PRIVATE-SIDE export tooling: it drives the export
# (which packages the tree) and is itself stripped from the packaged egg. On a
# clean/public checkout it is absent, so the packaging-pin rows it carries
# cannot be asserted; skip loud + named. Present on the source instance ⇒ the
# row check runs with full teeth (no skip fires there).
requires_egg_manifest = pytest.mark.skipif(
    not MANIFEST.is_file(),
    reason="egg-export-manifest.txt absent — private-side export tooling, not "
           "shipped in the egg; packaging-pin rows arm on the source instance",
)

# F1: the three dashboard bind variable names are DEAD on this surface. They
# are assembled here by concatenation so the names appear in NO repo file —
# not even this test.
_BIND_VAR_NAMES = tuple("CABINET_DASHBOARD_" + suffix for suffix in ("BIND", "HOSTNAME", "HOST"))

_FORBIDDEN = (
    # orchestrate-never-reimplement: killswitch writes belong to kill-switch.sh.
    # Two forms pinned: the single-string form…
    "SET cabinet:killswitch",
    "DEL cabinet:killswitch",
    # …and the house argv-array form (redisArgv(cli, ["SET", …])) — the app
    # has no legitimate use for a "SET"/"DEL" Swift string literal at all.
    '"SET"',
    '"DEL"',
    # docker-era Redis URL residue (the locked script's default) must never
    # be re-encoded here — the app pins loopback instead
    "redis://redis:",
    # loopback-only: the all-interfaces address has no business in this app
    "0.0.0.0",
    # Terminal launches are Launch Services only — no AppleScript bridges
    # (they would add an Apple-events TCC prompt)
    "osascript",
    "NSAppleScript",
    # the companion observes; it never touches launchd (§6 budget: 0)
    "launchctl",
    # never surfaced, ships dark (§2)
    "generate-plists",
    "gate-apply",
)

# Read-only Redis pin, matched to the house call style: every redisArgv(...)
# call must open its argv tail with one of these literal commands.
_ALLOWED_REDIS_COMMANDS = {"PING", "GET"}


@pytest.fixture(scope="module")
def src() -> str:
    # Loaded inside a fixture (not at import) so a missing main.swift fails as
    # ONE clean assertion instead of a module collection error that would also
    # swallow the plist/manifest tests.
    assert MAIN.is_file(), "cabinet/companion/main.swift must exist"
    return MAIN.read_text(encoding="utf-8")


def _line_of(lines: list[str], needle: str) -> int:
    for i, line in enumerate(lines):
        if needle in line:
            return i
    raise AssertionError(f"literal not found in main.swift: {needle!r}")


def test_source_doctrine_greps(src: str):
    for token in _FORBIDDEN:
        assert token not in src, f"forbidden token in main.swift: {token!r}"

    # Orchestrate-never-reimplement, argv-shape half: every redisArgv( call
    # opens its tail with a literal read-only command. The occurrence count
    # pins completeness — a call built any other way (variable tail, non-literal
    # first element) breaks the count equation instead of slipping through.
    calls = re.findall(r'redisArgv\(\s*\w+\s*,\s*\[\s*"([A-Z]+)"', src)
    definitions = len(re.findall(r"func\s+redisArgv\s*\(", src))
    occurrences = len(re.findall(r"redisArgv\s*\(", src))
    assert definitions == 1, "expected exactly one redisArgv definition"
    assert calls, "expected at least one redisArgv call site"
    assert occurrences == definitions + len(calls), (
        "every redisArgv call must open with a string-literal command "
        f"(found {occurrences} occurrences, {definitions} definition(s), "
        f"{len(calls)} literal-opening call(s))"
    )
    for cmd in calls:
        assert cmd in _ALLOWED_REDIS_COMMANDS, (
            f"redisArgv command {cmd!r} is not read-only (allowed: PING/GET)"
        )

    src_lines = src.splitlines()

    # F1 bind-agnosticism: no dashboard bind variable name, ever
    for name in _BIND_VAR_NAMES:
        assert name not in src, f"main.swift must not mention the dashboard bind var {name!r}"
    # …but the PORT discovery contract (§8) must be present
    assert "CABINET_DASHBOARD_PORT=" in src, "anchored .env port scan (§8) missing"

    # loopback-only: every http(s):// literal is 127.0.0.1
    hosts = re.findall(r"https?://([^\s\"'\\)/]+)", src)
    assert hosts, "expected at least one loopback http:// literal"
    for host in hosts:
        assert host.startswith("127.0.0.1"), f"non-loopback URL literal: {host}"

    # docker residue neutralized ADJACENT to the kill-switch.sh call site (§4)
    literal = "REDIS_URL=redis://127.0.0.1:6379"
    assert literal in src, "loopback REDIS_URL export literal missing"
    distance = abs(_line_of(src_lines, literal) - _line_of(src_lines, "kill-switch.sh"))
    assert distance <= 40, (
        f"REDIS_URL loopback pin must sit adjacent to the kill-switch.sh call site "
        f"(distance {distance} lines)"
    )

    # typed-confirm literals (§7)
    assert '"STOP"' in src, 'typed-confirm literal "STOP" missing'
    assert '"RESUME"' in src, 'typed-confirm literal "RESUME" missing'

    # Commercial app shell routes into the shared journey. It must not grow a
    # companion-owned onboarding writer or a second source of truth.
    assert 'Continue Orientation' in src
    assert 'openLoopback(path: "/onboarding?from=companion&trace_id=' in src
    assert '&correlation_id=' in src
    assert 'UUID().uuidString.lowercased()' in src
    assert "framework.onboarding.journey" not in src


def test_info_plist_contract():
    with PLIST.open("rb") as fh:
        info = plistlib.load(fh)
    assert info["LSUIElement"] is True, "companion must be a menu-bar-only accessory"
    assert info["CFBundleIdentifier"] == "com.cabinet.companion", (
        "bundle id is the stable identity for notifications/defaults/login item"
    )
    assert info["CFBundleExecutable"] == "cabinet-companion"
    assert info["CFBundleShortVersionString"] == "0.6.0"


@requires_egg_manifest
def test_egg_manifest_rows():
    text = MANIFEST.read_text(encoding="utf-8")
    for row in (
        "expect-present cabinet/companion/main.swift",
        "expect-present cabinet/companion/Info.plist",
        "expect-present cabinet/scripts/build-companion.sh",
    ):
        assert row in text, f"egg-export-manifest.txt missing verification row: {row}"


# --------------------------------------------------------------------------
# build half — honest skip when the toolchain is absent
# --------------------------------------------------------------------------

# Dev-Mac only: main.swift imports AppKit, which compiles on darwin alone —
# a bare `swiftc` on PATH is NOT enough (GitHub's ubuntu runners ship a Linux
# Swift toolchain that fooled the PATH-only probe; master CI 2026-07-10).
_HAS_SWIFTC = sys.platform == "darwin" and shutil.which("swiftc") is not None
needs_swiftc = pytest.mark.skipif(not _HAS_SWIFTC, reason="swiftc not available or not macOS (AppKit compiles on darwin only)")


@pytest.fixture(scope="module")
def built_bundle() -> Path:
    if not _HAS_SWIFTC:
        pytest.skip("swiftc not available (CLT not installed)")
    env = {**os.environ, "CABINET_ROOT": str(REPO)}  # pin output into THIS checkout
    proc = subprocess.run(
        ["bash", str(BUILD)], env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, f"build-companion.sh failed:\n{proc.stdout}\n{proc.stderr}"
    return APP


@needs_swiftc
def test_build_produces_bundle(built_bundle: Path):
    assert built_bundle.is_dir()
    assert (built_bundle / "Contents" / "Info.plist").is_file()
    assert BIN.is_file()
    assert os.access(BIN, os.X_OK), "bundle executable must carry the executable bit"


@needs_swiftc
def test_adhoc_signature_no_quarantine(built_bundle: Path):
    verify = subprocess.run(
        ["codesign", "--verify", str(built_bundle)], capture_output=True, text=True, timeout=60,
    )
    assert verify.returncode == 0, f"codesign --verify failed: {verify.stderr}"

    detail = subprocess.run(
        ["codesign", "-dv", str(built_bundle)], capture_output=True, text=True, timeout=60,
    )
    combined = detail.stdout + detail.stderr  # codesign -dv writes to stderr
    assert "Signature=adhoc" in combined, f"expected ad-hoc signature, got:\n{combined}"
    assert "com.cabinet.companion" in combined, "stable signing identifier missing"

    xattrs = subprocess.run(
        ["xattr", str(built_bundle)], capture_output=True, text=True, timeout=60,
    )
    assert "com.apple.quarantine" not in xattrs.stdout, (
        "locally built bundle must carry no quarantine xattr (no Gatekeeper dance)"
    )


@needs_swiftc
def test_smoke_mode(built_bundle: Path):
    env = {**os.environ, "CABINET_ROOT": str(REPO)}
    proc = subprocess.run(
        [str(BIN), "--smoke"], env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (
        f"--smoke must exit 0 on ANY honest state (exit {proc.returncode}):\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert re.match(r"^STATE=(GREEN|AMBER|RED|PAUSED|OFF) reason=", proc.stdout), (
        f"--smoke output contract violated: {proc.stdout!r}"
    )
