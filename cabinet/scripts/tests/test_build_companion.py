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
PET = COMPANION_DIR / "pet.swift"
SPRITES_TS = REPO / "cabinet" / "dashboard" / "src" / "lib" / "world" / "sprites.ts"
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
    assert info["CFBundleShortVersionString"] == "0.7.0"


@requires_egg_manifest
def test_egg_manifest_rows():
    text = MANIFEST.read_text(encoding="utf-8")
    for row in (
        "expect-present cabinet/companion/main.swift",
        "expect-present cabinet/companion/pet.swift",
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


# ==========================================================================
# Desk pet (pet.swift) — the floating officer beside the Dock.
#
# WHY THESE ARMS EXIST, in the order they were paid for:
#
#  * The doctrine greps above read main.swift ONLY. Adding a second source to
#    the same binary would have walked every read-only pin straight past the
#    sensor, so the pin now reads the whole target (test_pet_*_union).
#  * A sprite geometry copied into Swift can silently drift from the World's
#    own sheet layout. It is pinned AGAINST the TypeScript, not restated.
#  * The state→look mapping is asserted on the BINARY's output, and the
#    distinctness arm is the direct test of the failure the Captain named: a
#    pet that shows the same thing regardless of state is the defect.
#  * The colour arms read the RENDERED PIXELS. "desaturated" as a label is
#    worth nothing; r == g == b on every body pixel is worth something.
# ==========================================================================

COMPANION_SWIFT_SOURCES = ("main.swift", "pet.swift")


@pytest.fixture(scope="module")
def all_src() -> str:
    parts = []
    for name in COMPANION_SWIFT_SOURCES:
        f = COMPANION_DIR / name
        assert f.is_file(), f"cabinet/companion/{name} must exist"
        parts.append(f.read_text(encoding="utf-8"))
    # Every .swift in the directory compiles into the ONE binary, so the pins
    # must cover every .swift in the directory — not a hand-listed subset.
    on_disk = sorted(p.name for p in COMPANION_DIR.glob("*.swift"))
    assert on_disk == sorted(COMPANION_SWIFT_SOURCES), (
        "a Swift source appeared in cabinet/companion/ that these doctrine pins "
        f"do not read: on disk {on_disk}, pinned {sorted(COMPANION_SWIFT_SOURCES)}"
    )
    return "\n".join(parts)


def test_pet_doctrine_pins_cover_every_companion_source_union(all_src: str):
    """The read-only / loopback pins, over the WHOLE compiled target."""
    for token in _FORBIDDEN:
        assert token not in all_src, f"forbidden token in a companion source: {token!r}"

    # Redis stays read-only across every file, counted the same way.
    calls = re.findall(r'redisArgv\(\s*\w+\s*,\s*\[\s*"([A-Z]+)"', all_src)
    definitions = len(re.findall(r"func\s+redisArgv\s*\(", all_src))
    occurrences = len(re.findall(r"redisArgv\s*\(", all_src))
    assert definitions == 1
    assert calls, "expected at least one redisArgv call site across the target"
    assert occurrences == definitions + len(calls)
    for cmd in calls:
        assert cmd in _ALLOWED_REDIS_COMMANDS

    for host in re.findall(r"https?://([^\s\"'\\)/]+)", all_src):
        assert host.startswith("127.0.0.1"), f"non-loopback URL literal: {host}"

    # The pet observes; it must not grow its own reader or actuator.
    assert "redisArgv" not in PET.read_text(encoding="utf-8"), (
        "pet.swift is a BODY — every reading comes from CompanionCore.poll()"
    )


def test_pet_click_through_finding_is_pinned():
    """macOS 26.6 swallows clicks on a fully transparent window (measured).

    The shipped fallback is ignoresMouseEvents = true. Flipping it back needs
    the probe re-run, so the value is pinned here rather than left to a diff.
    """
    src = PET.read_text(encoding="utf-8")
    assert "static let petWindowIgnoresMouse = true" in src, (
        "per-pixel click-through is broken on this macOS — the pet must ignore "
        "mouse events entirely, or it silently blocks clicks on whatever is under it"
    )
    assert "window.ignoresMouseEvents = Self.petWindowIgnoresMouse" in src, (
        "the window must actually READ the pin — a constant nothing consults is decoration"
    )


def test_pet_sheet_geometry_is_pinned_against_the_world():
    """The pet's sheet layout is a MIRROR of the World's, pinned to its source.

    Both draw the same owned cast. If the World's atlas moves and this copy
    does not, the pet renders the wrong 16x32 window of the sheet — a silent
    visual break no unit test of pet.swift alone could see.
    """
    assert SPRITES_TS.is_file(), "world sprite atlas missing — the mirror has no original"
    ts = SPRITES_TS.read_text(encoding="utf-8")
    swift = PET.read_text(encoding="utf-8")

    ts_dirs = dict(re.findall(r"^\s*(right|up|left|down):\s*(\d+),", ts, re.M))
    assert set(ts_dirs) == {"right", "up", "left", "down"}, f"could not read DIR_X from the atlas: {ts_dirs}"
    for facing, x in ts_dirs.items():
        assert re.search(rf"case \.{facing}: return {x}\b", swift), (
            f"pet.swift DIR_X for {facing} must be {x} to match the world atlas"
        )

    for ts_name, swift_name in (("CHAR_FRAME_W", "cellW"), ("CHAR_FRAME_H", "cellH"),
                                ("CHARACTER_COUNT", "characterCount")):
        m = re.search(rf"{ts_name}\s*=\s*(\d+)", ts)
        assert m, f"{ts_name} not found in the world atlas"
        assert re.search(rf"static let {swift_name}[^=]*=\s*{m.group(1)}\b", swift), (
            f"pet.swift {swift_name} must equal the world's {ts_name} ({m.group(1)})"
        )

    m = re.search(r"CHARACTER_DIR\s*=\s*'([^']+)'", ts)
    assert m, "CHARACTER_DIR not found in the world atlas"
    assert m.group(1) in swift, (
        f"pet.swift must read the same character directory as the world ({m.group(1)})"
    )
    # The strip rows: idle at y=32, walk at y=64 (atlas header comment).
    assert re.search(r"y:\s*32,", ts) and re.search(r"y:\s*64,", ts), "atlas strip rows moved"
    assert "static let idleY = 32" in swift and "static let walkY = 64" in swift


@needs_swiftc
def test_pet_selftest_mapping_is_honest_and_distinct(built_bundle: Path):
    """Every state through the shipped binary's own pure look function.

    Arms, each pointed at a specific way the pet could lie:
      1. all five ladder states are reported
      2. their looks are PAIRWISE DISTINCT — "shows the same thing regardless
         of state" is the defect this exists to catch
      3. only GREEN walks (motion means the fleet is working)
      4. only GREEN is chipless and only PAUSED is full-colour-and-still
      5. every non-GREEN look carries a machine-built reason
      6. a GREEN fleet whose officer is missing or absent does NOT read GREEN
    """
    env = {**os.environ, "CABINET_ROOT": str(REPO)}
    proc = subprocess.run([str(BIN), "--pet-selftest"], env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"--pet-selftest failed:\n{proc.stdout}\n{proc.stderr}"

    looks = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"^PETLOOK in=(\S+) state=(\S+) anim=(\S+) body=(\S+) chip=(\S+) why=(.*)$", line)
        if m:
            looks[m.group(1)] = dict(state=m.group(2), anim=m.group(3),
                                     body=m.group(4), chip=m.group(5), why=m.group(6))
    ladder = ["OFF", "PAUSED", "RED", "AMBER", "GREEN"]
    assert set(ladder).issubset(looks), f"missing ladder states: {sorted(set(ladder) - set(looks))}"

    triples = {s: (looks[s]["anim"], looks[s]["body"], looks[s]["chip"]) for s in ladder}
    assert len(set(triples.values())) == len(ladder), (
        f"two states render identically — the pet cannot be read: {triples}"
    )

    for s in ladder:
        walks = looks[s]["anim"] == "walk"
        assert walks == (s == "GREEN"), f"{s} anim={looks[s]['anim']} — only GREEN may walk"
        chipless = looks[s]["chip"] == "none"
        assert chipless == (s == "GREEN"), f"{s} chip={looks[s]['chip']} — only GREEN may be chipless"
        if s != "GREEN":
            assert looks[s]["why"].strip(), f"{s} carries no reason"
    assert looks["PAUSED"]["anim"] == "frozen", "PAUSED must be frozen mid-stride, not idling"
    assert looks["OFF"]["body"] == "hollow", "OFF must be a shell — never a contented body"
    assert looks["AMBER"]["body"] == "grey" and looks["RED"]["body"] == "grey", (
        "absence must not look like calm — unknown and bad both render grey"
    )

    for degraded in ("GREEN_NO_ROW", "GREEN_ABSENT"):
        assert degraded in looks, f"{degraded} case missing from the selftest"
        assert looks[degraded]["state"] != "GREEN", (
            f"{degraded} rendered GREEN — the pet portrays an officer, and it must "
            "not walk contentedly while that officer is missing"
        )
        assert looks[degraded]["anim"] != "walk"


@needs_swiftc
def test_pet_sheet_resolves_to_the_same_character_as_the_world(built_bundle: Path):
    """officer → sheet must be the World's fnv1a, recomputed here independently."""
    env = {**os.environ, "CABINET_ROOT": str(REPO)}
    proc = subprocess.run([str(BIN), "--pet-selftest"], env=env,
                          capture_output=True, text=True, timeout=30)
    m = re.search(r"^PETSHEET officer=(\S+) path=(\S+) readable=(\S+)$", proc.stdout, re.M)
    assert m, f"--pet-selftest printed no PETSHEET line:\n{proc.stdout}"
    slug, path, _readable = m.group(1), m.group(2), m.group(3)

    h = 0x811C9DC5
    for ch in slug:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    expected = f"Premade_Character_{h % 20 + 1:02d}.png"
    assert path.endswith(expected), (
        f"pet picked {os.path.basename(path)} for {slug!r}; the world's hash says {expected}"
    )


# ---- pixel-level arms: what the pet actually DRAWS, not what it claims ----

def _read_png_rgba(path: Path):
    """Minimal stdlib PNG reader (8-bit RGBA, non-interlaced).

    Deliberately dependency-free: the hermetic suites pin HOME, so a
    user-site Pillow is not there when the gate runs.
    """
    import struct
    import zlib

    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(raw):
        (length,) = struct.unpack(">I", raw[pos:pos + 4])
        ctype = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            w, h, depth, color, _comp, _filt, interlace = struct.unpack(">IIBBBBB", data)
            assert (depth, color, interlace) == (8, 6, 0), (
                f"expected 8-bit RGBA non-interlaced, got depth={depth} color={color} interlace={interlace}"
            )
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
        pos += 12 + length

    stream = zlib.decompress(idat)
    stride, out, prev = w * 4, [], bytearray(w * 4)
    p = 0
    for _ in range(h):
        ftype = stream[p]
        line = bytearray(stream[p + 1:p + 1 + stride])
        p += 1 + stride
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if ftype == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ftype == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ftype == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif ftype == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
            elif ftype != 0:
                raise AssertionError(f"unknown PNG filter {ftype}")
        out.append(bytes(line))
        prev = line
    return w, h, out


def _pixel(rows, x, y):
    row = rows[y]
    return row[x * 4], row[x * 4 + 1], row[x * 4 + 2], row[x * 4 + 3]


@pytest.fixture(scope="module")
def pet_renders(built_bundle: Path, tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("petrender")
    env = {**os.environ, "CABINET_ROOT": str(REPO)}
    canvases = {}
    for state in ("GREEN", "AMBER", "RED", "PAUSED", "OFF"):
        target = out / f"{state}.png"
        proc = subprocess.run([str(BIN), "--pet-render", state, str(target)],
                              env=env, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            # Skip ONLY when the art is genuinely not in this checkout. Keying
            # the skip off the binary's error TEXT would let a broken-sheet
            # failure disable five pixel arms and report a green skip.
            sheets = REPO / "cabinet" / "dashboard" / "public" / "world-assets" / "originals" / "characters"
            if not any(sheets.glob("Premade_Character_*.png")):
                pytest.skip("owned character sheets absent from this checkout — nothing to render")
        assert proc.returncode == 0, f"--pet-render {state} failed:\n{proc.stdout}\n{proc.stderr}"
        canvases[state] = _read_png_rgba(target)
    return canvases


# The body occupies the lower part of the canvas; the chip the upper right.
# Both are read from pet.swift's own constants so the split cannot drift.
def _layout():
    src = PET.read_text(encoding="utf-8")
    def const(name):
        m = re.search(rf"static let {name} = (\d+)", src)
        assert m, f"pet.swift constant {name} not found"
        return int(m.group(1))
    return {n: const(n) for n in ("canvasW", "canvasH", "spriteX", "spriteY", "chipX", "chipY")}


@needs_swiftc
def test_pet_grey_states_are_really_grey_in_the_pixels(pet_renders):
    """AMBER and RED must be desaturated IN THE OUTPUT, r == g == b.

    The label "grey" in the look table is a claim; this is the measurement.
    """
    L = _layout()
    body_top = L["spriteY"] + 4  # below the chip band, inside the officer
    for state in ("AMBER", "RED"):
        w, h, rows = pet_renders[state]
        assert (w, h) == (L["canvasW"], L["canvasH"])
        seen = 0
        for y in range(body_top, h):
            for x in range(w):
                r, g, b, a = _pixel(rows, x, y)
                if a == 0:
                    continue
                seen += 1
                assert r == g == b, (
                    f"{state} body pixel ({x},{y}) is coloured rgb=({r},{g},{b}) — "
                    "a state that means 'I do not know' must not look alive"
                )
        assert seen > 100, f"{state} rendered almost nothing ({seen} visible body pixels)"


@needs_swiftc
def test_pet_green_and_paused_keep_their_colour(pet_renders):
    """The inverse arm: if everything were grey, the arm above would pass for
    the wrong reason. GREEN and PAUSED must carry saturated pixels."""
    L = _layout()
    for state in ("GREEN", "PAUSED"):
        w, h, rows = pet_renders[state]
        saturated = 0
        for y in range(L["spriteY"] + 4, h):
            for x in range(w):
                r, g, b, a = _pixel(rows, x, y)
                if a and max(r, g, b) - min(r, g, b) > 30:
                    saturated += 1
        assert saturated > 20, f"{state} has only {saturated} saturated pixels — it should be in colour"


@needs_swiftc
def test_pet_off_state_is_hollow(pet_renders):
    """OFF is the officer's OUTLINE with nobody in it.

    Measured relationally: pixels that are solid body in GREEN must be
    transparent in OFF. A filled grey body would pass a naive "is it drawn"
    check and would read as a calm officer, which is the exact lie forbidden.
    """
    L = _layout()
    _wg, hg, green = pet_renders["GREEN"]
    _wo, _ho, off = pet_renders["OFF"]
    interior, hollow = 0, 0
    # Column band through the torso, well inside the silhouette.
    for y in range(L["spriteY"] + 14, hg - 4):
        for x in range(L["spriteX"] + 6, L["spriteX"] + 10):
            if _pixel(green, x, y)[3] == 255:
                interior += 1
                if _pixel(off, x, y)[3] == 0:
                    hollow += 1
    assert interior > 20, f"sampling band missed the body ({interior} solid GREEN pixels)"
    # Not 100%: the shell traces the sprite's INTERNAL contours too (between the
    # legs, under an arm), which is what makes it read as a drawing rather than
    # a blob. A FILLED body scores 0 here, so the arm still fails loudly for the
    # failure it exists to catch.
    assert hollow / interior >= 0.80, (
        f"OFF is not hollow: only {hollow} of {interior} torso pixels are transparent"
    )

    def body_ink(state):
        _w, h, rows = pet_renders[state]
        return sum(1 for y in range(L["spriteY"] + 4, h) for x in range(L["canvasW"])
                   if _pixel(rows, x, y)[3])

    ratio = body_ink("OFF") / body_ink("GREEN")
    assert ratio <= 0.75, (
        f"OFF draws {ratio:.0%} of GREEN's pixels — that is a filled officer, not a shell"
    )


@needs_swiftc
def test_pet_chip_distinguishes_amber_from_red_and_green_has_none(pet_renders):
    L = _layout()
    chip_rows = range(0, L["spriteY"] + 4)
    chip_cols = range(L["chipX"] - 1, L["canvasW"])

    def chip_pixels(state):
        _w, _h, rows = pet_renders[state]
        return [_pixel(rows, x, y) for y in chip_rows for x in chip_cols]

    amber, red, green = chip_pixels("AMBER"), chip_pixels("RED"), chip_pixels("GREEN")
    assert any(p[3] for p in amber), "AMBER drew no chip"
    assert any(p[3] for p in red), "RED drew no chip"
    assert amber != red, "AMBER and RED chips are identical — the two states are indistinguishable"
    assert not any(p[3] for p in green), "GREEN must carry no chip — it has nothing to say"


@needs_swiftc
def test_pet_argv_refuses_nonsense(built_bundle: Path):
    """A pet flag that is wrong must fail loudly, never render something plausible."""
    env = {**os.environ, "CABINET_ROOT": str(REPO)}
    for args in (["--pet-demo", "NOPE"], ["--pet-scale", "0"], ["--pet-scale", "99"],
                 ["--pet-officer"], ["--pet-render", "GREEN"]):
        proc = subprocess.run([str(BIN), *args], env=env, capture_output=True, text=True, timeout=30)
        assert proc.returncode == 64, f"{args} should exit 64, got {proc.returncode}: {proc.stderr}"


# ==========================================================================
# Degenerate-art arms. Added 2026-07-30 after an adversarial review proved two
# defects that every arm above was blind to, because no test SUPPLIED a broken
# sheet — the art is tracked, so every render ran against perfect input:
#
#   * a sheet that DECODES but is the wrong size drew a pet with ten visible
#     pixels, exit 0, no log — an empty floating window, which is the one
#     thing pet.swift exists to forbid;
#   * a light semi-transparent pixel made the desaturation lift a premultiplied
#     channel above its own alpha, and the unchecked UInt8(...) in the
#     compositor SIGTRAPPED the whole app — in AMBER and RED, the two states
#     that mean "I do not know" and "it is bad".
#
# Both fixtures are synthesised here (stdlib PNG writer, no Pillow) so the arms
# run wherever the suite runs.
# ==========================================================================


def _write_rgba_png(path: Path, w: int, h: int, pixels: list[tuple[int, int, int, int]]) -> None:
    import struct
    import zlib

    assert len(pixels) == w * h
    raw = b"".join(
        b"\x00" + bytes(v for px in pixels[y * w:(y + 1) * w] for v in px)
        for y in range(h)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def _fake_root(tmp: Path, sheet: tuple[int, int, list[tuple[int, int, int, int]]]) -> Path:
    """A minimal valid CABINET_ROOT carrying ONE synthetic character sheet."""
    root = tmp / "root"
    (root / "cabinet" / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "cabinet" / "scripts" / "cabinet-doctor.sh").write_text("#!/bin/bash\nexit 0\n")
    art = root / "cabinet" / "dashboard" / "public" / "world-assets" / "originals" / "characters"
    art.mkdir(parents=True, exist_ok=True)
    w, h, px = sheet
    # cos → Premade_Character_05 by the world's hash; asserted independently by
    # test_pet_sheet_resolves_to_the_same_character_as_the_world.
    _write_rgba_png(art / "Premade_Character_05.png", w, h, px)
    return root


@pytest.fixture(scope="module")
def portable_bin(built_bundle: Path, tmp_path_factory) -> Path:
    """The bundle, copied OUT of the repo.

    Root discovery self-locates from the bundle path first, so a bundle sitting
    at <repo>/bin/ always resolves to the repo and CABINET_ROOT is ignored —
    which would make every fixture below silently test the real art.
    """
    dest = tmp_path_factory.mktemp("portable") / "Cabinet Companion.app"
    shutil.copytree(built_bundle, dest)
    return dest / "Contents" / "MacOS" / "cabinet-companion"


@needs_swiftc
def test_pet_refuses_a_sheet_that_decodes_but_is_the_wrong_size(portable_bin: Path, tmp_path):
    root = _fake_root(tmp_path, (64, 16, [(200, 60, 60, 255)] * (64 * 16)))
    env = {**os.environ, "CABINET_ROOT": str(root)}
    out = tmp_path / "wrong.png"
    proc = subprocess.run([str(portable_bin), "--pet-render", "GREEN", str(out)],
                          env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0, (
        "a 64x16 sheet must be REFUSED, not resampled into the 16x32 cell — "
        f"got exit 0 and {out.stat().st_size if out.exists() else 0} bytes of output"
    )
    assert "sprite sheet unreadable" in proc.stderr


@needs_swiftc
def test_pet_falls_back_to_the_missing_body_when_a_frame_is_empty(portable_bin: Path, tmp_path):
    """Right dimensions, no art: the pet must draw the loud box, not nothing.

    This is the degenerate end of "the sheet loaded". Rendering an empty canvas
    would put an invisible window on the Captain's screen, which cannot be told
    apart from the pet never having launched.
    """
    root = _fake_root(tmp_path, (384, 96, [(0, 0, 0, 0)] * (384 * 96)))
    env = {**os.environ, "CABINET_ROOT": str(root)}
    out = tmp_path / "empty.png"
    proc = subprocess.run([str(portable_bin), "--pet-render", "GREEN", str(out)],
                          env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    _w, h, rows = _read_png_rgba(out)
    body = [_pixel(rows, x, y) for y in range(6, h) for x in range(_layout()["canvasW"])]
    ink = [p for p in body if p[3]]
    assert len(ink) > 60, (
        f"an empty sheet produced {len(ink)} visible body pixels — that is an "
        "invisible pet, which is indistinguishable from a pet that never started"
    )
    warn = [p for p in ink if p[0] > 150 and p[1] < 110]
    assert len(warn) > 20, "the fallback must be the unmistakable MISSING box, not a faint smudge"


@needs_swiftc
def test_pet_survives_light_semi_transparent_art(portable_bin: Path, tmp_path):
    """The grey states must not TRAP on anti-aliased art.

    Premultiplied rgb <= a is a property of the source art, not of this buffer:
    the desaturation's gamma lift can push a light low-alpha pixel above its own
    alpha, and compositing that over the keyline underneath overflows. Against
    the original code this exited 133 (SIGTRAP) for AMBER and RED.

    TWO guards now prevent it — the desaturation caps at the pixel's own alpha,
    and the compositor clamps — and EITHER alone is sufficient, so this arm goes
    red only when both are gone. That is the mutation that matters (it is the
    pre-change code), but it means neither guard has an independent sensor and
    nothing here pretends otherwise: they are redundant by construction, and at
    the offending pixel they produce byte-identical output.
    """
    # Geometry matters more than colour here. The compositor only overflows
    # when a light LOW-alpha pixel lands on an ALREADY-PAINTED destination, and
    # the only thing painted underneath is the keyline — which is drawn exactly
    # where alpha < 128 next to an opaque neighbour. So: an opaque core with a
    # light anti-aliased fringe, i.e. ordinary art. A uniformly translucent
    # sheet produces no keyline at all and never reaches the defect (learned by
    # mutation: the first version of this fixture passed against the ORIGINAL
    # unfixed code, which makes it decoration, not a test).
    px = [(0, 0, 0, 0)] * (384 * 96)
    for y in range(32, 96):          # idle AND walk strips
        for x in range(384):
            cx, cy = x % 16, y % 32
            core = 4 <= cx <= 12 and 10 <= cy <= 22
            px[y * 384 + x] = (240, 240, 240, 255) if core else (255, 255, 255, 100)
    root = _fake_root(tmp_path, (384, 96, px))
    env = {**os.environ, "CABINET_ROOT": str(root)}
    for state in ("AMBER", "RED", "OFF", "GREEN", "PAUSED"):
        out = tmp_path / f"aa-{state}.png"
        proc = subprocess.run([str(portable_bin), "--pet-render", state, str(out)],
                              env=env, capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, (
            f"--pet-render {state} exited {proc.returncode} on anti-aliased art "
            f"(133 = SIGTRAP, i.e. the app would have died):\n{proc.stderr}"
        )


@needs_swiftc
def test_pet_walk_cycle_actually_advances(portable_bin: Path, tmp_path):
    """A pet that draws frame 0 forever is a still image with a timer."""
    env = {**os.environ, "CABINET_ROOT": str(REPO)}
    sheets = REPO / "cabinet" / "dashboard" / "public" / "world-assets" / "originals" / "characters"
    if not any(sheets.glob("Premade_Character_*.png")):
        pytest.skip("owned character sheets absent from this checkout")
    digests = set()
    for tick in range(6):
        out = tmp_path / f"walk-{tick}.png"
        proc = subprocess.run([str(portable_bin), "--pet-render", "GREEN", str(out),
                               "--pet-tick", str(tick)],
                              env=env, capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        digests.add(out.read_bytes())
    assert len(digests) >= 4, (
        f"six consecutive walk ticks produced only {len(digests)} distinct frames"
    )


def test_pet_demo_suppression_is_pinned():
    """Nothing else in the suite can see this, and deleting it is silent.

    --pet-demo renders a SYNTHETIC state. Its safety rests on two lines: the
    poll never runs, and the displayed snapshot is rebuilt from the forced
    state rather than from a real one. Both are single lines in main.swift that
    a later edit could drop with every other arm still green.
    """
    src = MAIN.read_text(encoding="utf-8")
    assert "guard PetOptions.demoState == nil else { return }" in src, (
        "the demo poll-suppression guard is gone — a forced state could be mixed "
        "with a real reading"
    )
    assert "if let demo = PetOptions.demoState {\n            return PetCLI.demoSnapshot(" in src, (
        "displayedSnapshot() must return the synthetic snapshot in demo mode"
    )
    assert 'DEMO (synthetic, not a reading)' in src, (
        "the menu-bar tooltip must carry the DEMO marker — the menu bar is in "
        "every screenshot --pet-demo exists to produce"
    )
    assert "let rootOK = rootInfo.valid && !demo" in src, (
        "every acting menu item must be disabled in demo mode: their labels and "
        "enablement are derived from the synthetic snapshot"
    )
