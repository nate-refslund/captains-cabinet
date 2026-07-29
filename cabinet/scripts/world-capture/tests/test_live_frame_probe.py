#!/usr/bin/env python3
"""The live-frame probe's own arms — including the ones that catch IT lying.

live-frame-probe.py is the only sensor in this repo that judges the COMPOSITED
browser frame; the twelve invariants judge raster.py's re-draw of the layout and
have no day bucket, no veil and no compositor at all. A sensor with that much
territory to itself has to be shown failing, and shown refusing to answer, or it
is decoration.

Four things are pinned here:

  1. its copy of the sea ramp IS iso-terrain.ts's, parsed out of the TypeScript
     rather than retyped — the one duplication the probe needs, kept honest;
  2. it goes RED on the exact defect that shipped (a bright apricot dither over
     open water) and GREEN on lawful water, both directions;
  3. it does not judge LAND as water — a frame with no sea is UNJUDGED and
     non-zero, never a quiet pass;
  4. the degenerate end: a blank frame returns UNJUDGED, not OK. A probe that
     reports success on an empty image is the disabled sensor this file exists
     to prevent.
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
ISO_TERRAIN = REPO / "cabinet" / "dashboard" / "src" / "lib" / "world" / "iso-terrain.ts"


def _load():
    spec = importlib.util.spec_from_file_location("live_frame_probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


probe = _load()


def _ramp_from_ts(name: str) -> list[tuple[int, int, int]]:
    """The shipped ramp, read out of the renderer's own source."""
    src = ISO_TERRAIN.read_text()
    m = re.search(rf"^\s*{name}:\s*\[([^\]]*)\]", src, re.M)
    assert m, f"{name} ramp not found in iso-terrain.ts — regrep this test"
    hexes = re.findall(r"0x([0-9a-fA-F]{6})", m.group(1))
    assert hexes, f"{name} ramp parsed empty"
    return [(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) for h in hexes]


def _frame(path: Path, base, dots=None, coverage=0.16, size=(300, 300)):
    """An open-water frame: a sea-tone field, optionally dithered with `dots`."""
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
    im.save(path)
    return path


def _run(*paths) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(PROBE), *map(str, paths)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_sea_ramp_is_the_shipped_one_byte_for_byte():
    assert probe.SEA == _ramp_from_ts("sea"), (
        "live-frame-probe.py's SEA has drifted from iso-terrain.ts RAMPS.sea — "
        "the probe would be judging water the renderer no longer draws"
    )


def test_caps_are_derived_from_that_ramp_not_typed_in():
    assert probe.LUMA_CAP == max(probe.luma(c) for c in probe.SEA)
    assert probe.CHROMA_CAP == max(probe.chroma(c) for c in probe.SEA)
    # and they are the values the renderer's own veil test derives
    assert 155 < probe.LUMA_CAP < 165
    assert 20 < probe.CHROMA_CAP < 25


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


def test_green_on_the_shipped_dusk_veil(tmp_path):
    """The hues actually shipped after the fix, at their real coverage."""
    f = _frame(tmp_path / "dusk.png", _ramp_from_ts("sea"),
               dots=[(0x9A, 0x90, 0x84), (0x99, 0x8F, 0x80), (0xA7, 0x9C, 0x8C)])
    code, out = _run(f)
    assert code == 0, out
    assert "OK" in out


def test_land_is_not_judged_as_water(tmp_path):
    """A grass frame has no open water — the probe must decline, not pass."""
    f = _frame(tmp_path / "grass.png", _ramp_from_ts("grass"))
    code, out = _run(f)
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
    good = _frame(tmp_path / "good.png", _ramp_from_ts("sea"),
                  dots=[(0x9A, 0x90, 0x84)])
    code, out = _run(bad, good)
    assert code == 1
    assert "UNLAWFUL" in out and "OK" in out
    assert out.count("bad.png") >= 1 and out.count("good.png") >= 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
