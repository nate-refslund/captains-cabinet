"""Static tests for the dashboard PWA/install surfaces (Wave D app-feel).

Pins, without node or a server: every install artifact exists; PNG
dimensions via a pure-python IHDR read (NEVER byte-equality — sharp version
drift re-renders bytes); the maskable icon's corner pixel is the OPAQUE
brand background (a transparent corner means the safe-zone extension was
lost and launchers would mask onto garbage); the icon source is original
pure-geometry SVG (no embedded/traced assets — the licensing-safe bar);
the middleware matcher carries exactly the five auth exclusions; the
api/health namespace is pinned closed (the matcher excludes by PREFIX, so
the tripwire is what keeps the unauthenticated surface at one liveness
route); manifest.ts carries the field literals; the egg packaging manifest
expect-present rows sit inside the expect-present block.

Run: python3.12 -m pytest cabinet/scripts/tests/test_dashboard_pwa_static.py -q
"""

from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DASH = _REPO_ROOT / "cabinet" / "dashboard"
_APP = _DASH / "src" / "app"
_EGG_MANIFEST = _REPO_ROOT / "cabinet" / "scripts" / "egg-export-manifest.txt"

# The egg-export manifest is PRIVATE-SIDE export tooling — it drives the export
# and is itself stripped from the packaged egg. Absent on a clean/public
# checkout, so the expect-present packaging rows cannot be asserted there; skip
# loud + named. Present on the source instance ⇒ the check runs with full teeth.
requires_egg_manifest = pytest.mark.skipif(
    not _EGG_MANIFEST.is_file(),
    reason="egg-export-manifest.txt absent — private-side export tooling, not "
           "shipped in the egg; packaging-pin rows arm on the source instance",
)

_PNG_SIG = b"\x89PNG\r\n\x1a\n"

_MATCHER = (
    "matcher: ['/((?!_next/static|_next/image|favicon.ico"
    "|manifest.webmanifest|icon.svg|apple-icon.png|icons/|api/health).*)']"
)

_EGG_ROWS = (
    "expect-present cabinet/dashboard/src/app/manifest.ts",
    "expect-present cabinet/dashboard/src/app/icon.svg",
    "expect-present cabinet/dashboard/public/icons/icon-512.png",
    "expect-present cabinet/dashboard/src/app/api/health/route.ts",
)


def _png_header(path: Path) -> tuple[int, int, int, int]:
    """(width, height, bit_depth, color_type) from the IHDR chunk."""
    data = path.read_bytes()
    assert data[:8] == _PNG_SIG, f"{path} is not a PNG"
    assert data[12:16] == b"IHDR", f"{path}: first chunk is not IHDR"
    width, height = struct.unpack(">II", data[16:24])
    bit_depth, color_type = data[24], data[25]
    return width, height, bit_depth, color_type


def _png_first_pixel(path: Path) -> tuple[int, ...]:
    """First pixel of the first scanline, pure python. For pixel (0,0) every
    PNG filter type degenerates to the raw byte values (left/up/upper-left
    neighbors are all zero), so no unfiltering pass is needed."""
    data = path.read_bytes()
    width, height, bit_depth, color_type = _png_header(path)
    assert bit_depth == 8, f"{path}: expected 8-bit channels"
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    idat = b""
    off = 8
    while off < len(data):
        (length,) = struct.unpack(">I", data[off:off + 4])
        ctype = data[off + 4:off + 8]
        if ctype == b"IDAT":
            idat += data[off + 8:off + 8 + length]
        if ctype == b"IEND":
            break
        off += 12 + length
    raw = zlib.decompressobj().decompress(idat, 1 + channels)
    assert len(raw) >= 1 + channels, f"{path}: truncated IDAT"
    # raw[0] is the scanline filter byte; the next bytes are pixel (0,0)
    return tuple(raw[1:1 + channels])


# ---------------------------------------------------------------------------
# Existence + dimensions
# ---------------------------------------------------------------------------

def test_install_surfaces_exist():
    for rel in (
        "src/app/manifest.ts",
        "src/app/icon.svg",
        "src/app/apple-icon.png",
        "src/app/api/health/route.ts",
        "src/app/pwa.test.ts",
        "scripts/gen-icons.mjs",
        "public/icons/icon-192.png",
        "public/icons/icon-512.png",
        "public/icons/icon-512-maskable.png",
    ):
        assert (_DASH / rel).is_file(), f"missing install surface: {rel}"


def test_png_dimensions():
    for rel, size in (
        ("public/icons/icon-192.png", 192),
        ("public/icons/icon-512.png", 512),
        ("public/icons/icon-512-maskable.png", 512),
        ("src/app/apple-icon.png", 180),
    ):
        width, height, _depth, _ctype = _png_header(_DASH / rel)
        assert (width, height) == (size, size), (
            f"{rel}: {width}x{height}, expected {size}x{size}"
        )


def test_maskable_corner_is_opaque_brand_background():
    pixel = _png_first_pixel(_DASH / "public/icons/icon-512-maskable.png")
    _w, _h, _d, color_type = _png_header(
        _DASH / "public/icons/icon-512-maskable.png")
    assert color_type in (2, 6), "expected an RGB(A) maskable icon"
    assert pixel[:3] == (9, 9, 11), (
        f"maskable corner must be the #09090b brand field, got {pixel[:3]}"
    )
    if color_type == 6:
        assert pixel[3] == 255, (
            "maskable corner must be OPAQUE — launchers mask the full square"
        )


def test_apple_icon_is_opaque():
    _w, _h, _d, color_type = _png_header(_DASH / "src/app/apple-icon.png")
    if color_type == 6:
        assert _png_first_pixel(_DASH / "src/app/apple-icon.png")[3] == 255
    else:
        assert color_type == 2  # RGB — opaque by construction


def test_icon_svg_is_original_pure_geometry():
    svg = (_APP / "icon.svg").read_text(encoding="utf-8")
    for banned in ("<image", "<text", "href", "base64", "data:image"):
        assert banned not in svg, (
            f"icon.svg must stay pure authored geometry (found {banned!r}) — "
            "no embedded rasters, no fonts, no traced third-party assets"
        )
    assert "ORIGINAL artwork" in svg, "provenance comment lost"
    assert "non-LimeZu" in svg, "licensing provenance comment lost"


# ---------------------------------------------------------------------------
# Matcher + manifest literals
# ---------------------------------------------------------------------------

def test_middleware_matcher_is_exactly_the_five_exclusions():
    text = (_DASH / "src" / "middleware.ts").read_text(encoding="utf-8")
    assert _MATCHER in text, (
        "middleware matcher drifted from the spec literal — the five install "
        "surfaces (manifest, icon.svg, apple-icon.png, icons/, api/health) "
        "plus the three pre-existing exclusions, nothing more"
    )
    assert text.count("matcher:") == 1, "unexpected second matcher"


def test_manifest_ts_field_literals():
    text = (_APP / "manifest.ts").read_text(encoding="utf-8")
    for literal in (
        "name: \"Captain's Cabinet\"",
        "short_name: 'Cabinet'",
        "id: '/'",
        "start_url: '/'",
        "scope: '/'",
        "display: 'standalone'",
        "background_color: '#09090b'",
        "theme_color: '#09090b'",
        "'/icons/icon-192.png'",
        "'/icons/icon-512.png'",
        "'/icons/icon-512-maskable.png'",
        "purpose: 'maskable'",
    ):
        assert literal in text, f"manifest.ts lost the field literal {literal}"


def test_health_route_is_liveness_only():
    text = (_APP / "api" / "health" / "route.ts").read_text(encoding="utf-8")
    assert "ok: true" in text
    # scan CODE lines only — the header comment legitimately names the
    # excluded concepts (cookie, config) while the code must not touch them
    code = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("//")
    )
    for banned in ("redis", "readFile", "cookie"):
        assert banned not in code, (
            f"/api/health must stay a config-free liveness boolean ({banned!r})"
        )
    # TWO ENVIRONMENT READS, named rather than banned (update path, A5.5).
    # The health gate has to know WHICH CABINET answered and WHICH BUILD is
    # serving, or an old process that survived a failed restart passes an
    # identity probe and a bad update is recorded as a good one. Neither is
    # configuration and neither is a secret: one is a commit id fixed at build
    # time, the other a commit id fixed when this process was started. The ban
    # stays for everything else: any OTHER process.env read here is a failure.
    env_reads = re.findall(r"process\.env\.([A-Za-z0-9_]+)", code)
    assert set(env_reads) <= {"CABINET_BUILD_SOURCE_COMMIT", "CABINET_SOURCE_COMMIT"}, (
        f"/api/health must stay a config-free liveness boolean ({env_reads!r})"
    )


def _health_field_sources() -> dict[str, str]:
    """Which environment variable each /api/health field is answered from.

    Read out of the route itself so a reader of this file cannot describe a
    route that no longer exists.
    """
    text = (_APP / "api" / "health" / "route.ts").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("//"))
    return dict(re.findall(r"(\w+):\s*process\.env\.([A-Za-z0-9_]+)", code))


def _build_inlined_names() -> set[str]:
    """The variables next.config.ts bakes into the bundle at build time."""
    config = (_DASH / "next.config.ts").read_text(encoding="utf-8")
    block = re.search(r"\n  env:\s*\{(.*?)\n  \}", config, re.S)
    assert block, "next.config.ts no longer declares an `env` block"
    return set(re.findall(r"([A-Za-z0-9_]+)\s*:", block.group(1)))


def test_the_health_identity_field_is_not_baked_into_the_build():
    """THE UPDATE PATH'S IDENTITY LEG, pinned where it can actually be broken.

    The update health gate asks the dashboard "which Cabinet are you?" and rolls
    the whole update back when the answer is not the sha it just installed. If
    that answer is a value `next build` INLINED into the bundle, then the only
    way to change it is to rebuild — and the updater rebuilds only when the
    bundle touched `cabinet/dashboard/**`. Every framework-only update would
    then restart the same build, hear the old sha, and roll a perfectly good
    update back. That is not hypothetical: it shipped, and it was found by
    building with one commit and starting with another.

    So the two fields carry two different facts and must come from two
    different places:

      source_commit  WHICH CABINET this process was started against — read at
                     request time from the environment the process was spawned
                     with (start-dashboard.sh reads egg-manifest.json). An old
                     process that survived a failed restart still holds the OLD
                     value: its environment was fixed when it started, and
                     nothing can reach into a running process to change it.
      build_commit   WHICH BUILD is serving — inlined by `next build`, so it
                     cannot be anything but the commit the bundle was made
                     from. The gate demands this one only when the apply
                     actually rebuilt.
    """
    fields = _health_field_sources()
    inlined = _build_inlined_names()
    assert "source_commit" in fields, "the health body lost its identity field"
    assert fields["source_commit"] not in inlined, (
        "/api/health answers source_commit from %s, which next.config.ts bakes "
        "in at BUILD time — a framework-only update cannot change it, so the "
        "update health gate would roll every one of them back"
        % fields["source_commit"]
    )
    assert "build_commit" in fields, (
        "the health body lost the build stamp — without it a dashboard bundle "
        "whose build silently failed answers as the new version"
    )
    assert fields["build_commit"] in inlined, (
        "/api/health answers build_commit from %s, which is NOT baked in at "
        "build time — a stale build would be free to claim the new commit"
        % fields["build_commit"]
    )


def test_the_health_start_time_is_the_process_start_not_a_module_load():
    """`started_at` is the leg that catches a restart that did not happen.

    A module-scope `new Date()` is evaluated when the route module is first
    LOADED, which in a Next production server is the first request that reaches
    it — possibly long after the process started, and possibly after the update
    that was supposed to restart it. Derived from `process.uptime()` it is the
    process's own start time however late the module loads.
    """
    text = (_APP / "api" / "health" / "route.ts").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("//"))
    assert "process.uptime()" in code, (
        "started_at must be derived from process.uptime(), not from the moment "
        "this module happened to be loaded"
    )


def test_health_namespace_is_closed_tripwire():
    """The middleware exclusions are PREFIX matches, not exact paths: the
    `api/health` alternative un-authenticates EVERY pathname starting with
    /api/health — /api/healthz, /api/health-report, /api/health/deep would
    all silently ship cookie-less. The matcher literal is spec-pinned (test
    above), so this tripwire pins the NAMESPACE closed instead: exactly one
    route file under the excluded prefix and no health-prefixed siblings.
    If this test fails, someone widened the unauthenticated surface —
    adjudicate the auth exposure consciously (matcher comment, spec, and
    this test move together), never just add the file."""
    api = _APP / "api"
    prefixed = sorted(p.name for p in api.iterdir()
                      if p.name.startswith("health"))
    assert prefixed == ["health"], (
        f"api/health* sibling(s) {prefixed} would ride the api/health PREFIX "
        "exclusion and serve UNAUTHENTICATED — adjudicate before adding"
    )
    # dotfiles (.DS_Store noise) can never become Next routes — ignore them
    entries = sorted(p.name for p in (api / "health").iterdir()
                     if not p.name.startswith("."))
    assert entries == ["route.ts"], (
        f"api/health/ must hold exactly route.ts, found {entries} — anything "
        "nested under the excluded prefix serves UNAUTHENTICATED"
    )


# ---------------------------------------------------------------------------
# Egg packaging manifest rows
# ---------------------------------------------------------------------------

@requires_egg_manifest
def test_egg_manifest_rows_sit_in_the_expect_present_block():
    manifest = _EGG_MANIFEST.read_text(encoding="utf-8")
    lines = manifest.splitlines()
    absent_start = lines.index("expect-absent .git")
    gitleaks_row = lines.index("expect-present .gitleaks.toml")
    for row in _EGG_ROWS:
        assert row in lines, f"egg manifest lost the row: {row}"
        idx = lines.index(row)
        assert gitleaks_row < idx < absent_start, (
            f"{row} must sit at the end of the expect-present block "
            "(after the .gitleaks.toml row, before the expect-absent block)"
        )
