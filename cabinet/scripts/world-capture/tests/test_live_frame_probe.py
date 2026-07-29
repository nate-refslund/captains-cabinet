#!/usr/bin/env python3
"""The live-frame probe's own arms — including the ones that catch IT lying.

live-frame-probe.py is the only sensor in this repo that judges the COMPOSITED
browser frame; the twelve invariants judge raster.py's re-draw of the layout and
have no day bucket, no veil and no compositor at all. A sensor with that much
territory to itself has to be shown failing, and shown refusing to answer, or it
is decoration.

THREE OF THESE ARMS EXIST BECAUSE AN ADVERSARIAL REVIEW BROKE THE FIRST VERSION
of the probe before it ever ran in CI, and each one pins the fix:

  * `open_water` maximised the SEA count. Unlawful pixels are by definition not
    sea, so that rule preferred the window with the LEAST defect — a frame with
    the veil over half its ocean came back OK. It now reports the WORST window.
  * a frame of one flat colour passed as lawful water. It is now UNJUDGED.
  * the "is this water" qualifier counted DISTINCT non-sea tones, so a cobbled
    quay (few tones, large area) judged as water — and the dusk veil hues are
    themselves cobble-adjacent, so that confusion was guaranteed. It now asks
    two questions instead: is each non-water tone SCATTERED (a dither) rather
    than contiguous, and is the non-water mass spread EVENLY across the window
    (a veil covers every quadrant equally; a coastline does not). Scatter alone
    was not enough — a real quay is finely interleaved cobble, so every one of
    its tones is individually scattered. Together they also stopped a sand
    beach and the onboarding card from false-REDding.

Plus the invariants: the sea ramp and the veil tables are parsed out of the
TypeScript rather than retyped, the probe is shown red on the exact defect that
shipped and on the chroma near-miss, and a blank frame is UNJUDGED rather than
OK — a probe that reports success on an empty image is the disabled sensor this
file exists to prevent.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent / "live-frame-probe.py"
REPO = HERE.parents[3]
WORLD_LIB = REPO / "cabinet" / "dashboard" / "src" / "lib" / "world"
ISO_TERRAIN = WORLD_LIB / "iso-terrain.ts"
TERRAIN_PATTERN = WORLD_LIB / "terrain-pattern.ts"


def _load():
    spec = importlib.util.spec_from_file_location("live_frame_probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


probe = _load()


def _hexes(text: str) -> list[tuple[int, int, int]]:
    return [(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            for h in re.findall(r"0x([0-9a-fA-F]{6})", text)]


def _ramp_from_ts(name: str) -> list[tuple[int, int, int]]:
    """The shipped ramp, read out of the renderer's own source."""
    m = re.search(rf"^\s*{name}:\s*\[([^\]]*)\]", ISO_TERRAIN.read_text(), re.M)
    assert m, f"{name} ramp not found in iso-terrain.ts — regrep this test"
    out = _hexes(m.group(1))
    assert out, f"{name} ramp parsed empty"
    return out


def _veil_from_ts(bucket: str) -> list[tuple[int, int, int]]:
    """The shipped veil hues, read out of the renderer's own source."""
    m = re.search(rf"^export const {bucket.upper()}_VEIL_HUES = \[([^\]]*)\]",
                  TERRAIN_PATTERN.read_text(), re.M)
    assert m, f"{bucket} veil hues not found in terrain-pattern.ts"
    out = _hexes(m.group(1))
    assert out, f"{bucket} veil hues parsed empty"
    return out


def _frame(path: Path, base, dots=None, coverage=0.16, size=(600, 400),
           band=None, band_tones=None):
    """An open-water frame: a sea-tone field, optionally dithered, optionally
    with a contiguous second surface (a beach, a quay) filling a band."""
    im = Image.new("RGB", size, base[0])
    px = im.load()
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = base[(x * 7 + y * 13) % len(base)]
    if dots:
        step = max(2, int(1 / coverage))
        for y in range(size[1]):
            for x in range(size[0]):
                if (x * 3 + y * 5) % step == 0:
                    px[x, y] = dots[(x + y) % len(dots)]
    if band and band_tones:
        y0, y1 = band
        for y in range(y0, y1):
            for x in range(size[0]):
                px[x, y] = band_tones[(x * 7 + y * 13) % len(band_tones)]
    im.save(path)
    return path


def _run(*paths) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(PROBE), *map(str, paths)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


# ── the duplicated constants are pinned to their source ─────────────────────

def test_sea_ramp_is_the_shipped_one_byte_for_byte():
    assert probe.SEA == _ramp_from_ts("sea"), (
        "live-frame-probe.py's SEA has drifted from iso-terrain.ts RAMPS.sea — "
        "the probe would be judging water the renderer no longer draws"
    )


@pytest.mark.parametrize("bucket", ["dawn", "dusk", "night"])
def test_veil_tables_are_the_shipped_ones(bucket):
    assert probe.VEILS[bucket] == _veil_from_ts(bucket), (
        f"live-frame-probe.py's {bucket} veil has drifted from terrain-pattern.ts"
    )


def test_caps_are_derived_from_that_ramp_not_typed_in():
    assert probe.LUMA_CAP == max(probe.luma(c) for c in probe.SEA)
    assert probe.CHROMA_CAP == max(probe.chroma(c) for c in probe.SEA)
    assert 155 < probe.LUMA_CAP < 165
    assert 20 < probe.CHROMA_CAP < 25


# ── it goes red on the real defect, both laws ───────────────────────────────

def test_red_on_the_defect_that_shipped(tmp_path):
    """0xffc890 at 16% over open water — the frame the Captain was shown."""
    f = _frame(tmp_path / "shipped.png", _ramp_from_ts("sea"), dots=[(255, 200, 144)])
    code, out = _run(f)
    assert code == 1, out
    assert "UNLAWFUL" in out
    assert "(255, 200, 144)" in out


def test_red_on_a_hue_that_is_dark_enough_but_too_colourful(tmp_path):
    """The near-miss: luminance-lawful, chroma-foreign. Law 1 alone passed it."""
    f = _frame(tmp_path / "brown.png", _ramp_from_ts("sea"), dots=[(0x96, 0x6C, 0x3E)])
    code, out = _run(f)
    assert code == 1, out
    assert "UNLAWFUL" in out


def test_red_when_only_PART_of_the_ocean_is_defective(tmp_path):
    """THE SELECTION BUG. The first version maximised the sea count, which
    prefers the cleanest window; a half-defective ocean came back OK."""
    sea = _ramp_from_ts("sea")
    f = _frame(tmp_path / "half.png", sea, size=(900, 500))
    im = Image.open(f)
    px = im.load()
    for y in range(500):                       # defect on the LEFT half only
        for x in range(450):
            if (x * 3 + y * 5) % 6 == 0:
                px[x, y] = (255, 200, 144)
    im.save(f)
    code, out = _run(f)
    assert code == 1, out
    assert "UNLAWFUL" in out and "worst" in out


# ── it goes green on the real fix, and says WHAT it judged ──────────────────

def test_green_on_the_shipped_dusk_veil(tmp_path):
    f = _frame(tmp_path / "dusk.png", _ramp_from_ts("sea"), dots=_veil_from_ts("dusk"))
    code, out = _run(f)
    assert code == 0, out
    assert "OK" in out and "veil=dusk" in out


def test_green_on_the_shipped_night_veil_at_its_real_coverage(tmp_path):
    """42% coverage. The FIRST qualifier rejected every night frame as 'not
    water', so the densest veil in the world was never judged at all."""
    f = _frame(tmp_path / "night.png", _ramp_from_ts("sea"),
               dots=_veil_from_ts("night"), coverage=0.42)
    code, out = _run(f)
    assert code == 0, out
    assert "veil=night" in out


def test_a_green_says_when_there_was_no_veil_to_judge(tmp_path):
    """Otherwise a pass cannot distinguish 'the veil is lawful' from 'you
    captured the day bucket', which is the wrong-frame failure."""
    f = _frame(tmp_path / "clean.png", _ramp_from_ts("sea"))
    code, out = _run(f)
    assert code == 0, out
    assert "veil=none" in out


# ── it refuses to answer rather than answering wrongly ──────────────────────

def test_land_is_not_judged_as_water(tmp_path):
    """A grass frame has no open water — the probe must decline, not pass."""
    f = _frame(tmp_path / "grass.png", _ramp_from_ts("grass"))
    code, out = _run(f)
    assert code == 1, out
    assert "UNJUDGED" in out


def test_a_cobbled_quay_is_never_reported_as_an_unlawful_veil(tmp_path):
    """THE QUALIFIER BUG, and the sharpest form of it: the dusk veil hues ARE
    cobble tones, and a real quay is itself finely interleaved, so neither a
    tone COUNT nor per-tone scatter can tell a paved quay from a dithered sea.
    Uniformity can: a veil covers every quadrant equally, a quay does not."""
    f = _frame(tmp_path / "quay.png", _ramp_from_ts("sea"),
               band=(140, 400), band_tones=_ramp_from_ts("cobbleBase"))
    code, out = _run(f)
    assert "UNLAWFUL" not in out, out
    assert code == 0, out


def test_a_quay_does_not_HIDE_a_defective_sea(tmp_path):
    """The other half of the same qualifier: excluding the quay must not
    exclude the water beside it. A frame with both comes back red."""
    sea = _ramp_from_ts("sea")
    f = _frame(tmp_path / "quay-bad.png", sea, dots=[(255, 200, 144)],
               band=(140, 400), band_tones=_ramp_from_ts("cobbleBase"))
    code, out = _run(f)
    assert code == 1, out
    assert "UNLAWFUL" in out and "(255, 200, 144)" in out


def test_a_sand_beach_is_not_a_violation(tmp_path):
    """The other direction: sand is legitimately brighter than water. A
    tone-count qualifier called the beach an unlawful veil."""
    f = _frame(tmp_path / "beach.png", _ramp_from_ts("sea"),
               band=(260, 400), band_tones=_ramp_from_ts("sand"))
    code, out = _run(f)
    assert code == 0, out
    assert "UNLAWFUL" not in out


def test_a_flat_frame_is_unjudged_not_ok(tmp_path):
    """One tone across the whole window is what a frame that failed to render
    looks like. It must never come back green."""
    Image.new("RGB", (600, 400), (0x54, 0x91, 0x8C)).save(tmp_path / "flat.png")
    code, out = _run(tmp_path / "flat.png")
    assert code == 1, out
    assert "UNJUDGED" in out


def test_a_blank_frame_is_unjudged_not_ok(tmp_path):
    """The degenerate end. An empty image must never come back green."""
    Image.new("RGB", (300, 300), (0, 0, 0)).save(tmp_path / "blank.png")
    code, out = _run(tmp_path / "blank.png")
    assert code == 1, out
    assert "UNJUDGED" in out
    assert "OK " not in out


def test_no_arguments_is_a_usage_error_not_a_pass():
    code, _ = _run()
    assert code == 2


def test_every_frame_is_judged_not_just_the_first(tmp_path):
    """One red must not mask the next — the whole reason this loop is a sum."""
    bad = _frame(tmp_path / "bad.png", _ramp_from_ts("sea"), dots=[(255, 200, 144)])
    good = _frame(tmp_path / "good.png", _ramp_from_ts("sea"), dots=_veil_from_ts("dusk"))
    code, out = _run(bad, good)
    assert code == 1
    assert "UNLAWFUL" in out and "OK" in out
    assert out.count("bad.png") >= 1 and out.count("good.png") >= 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
