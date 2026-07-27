#!/usr/bin/env python3
"""The claims ground.py makes about itself, as arms.

ground.py is a dependency-free PORT of designs/world-mockup-v2/terrain.py: same
ramps, same 4x4 Bayer dither, same furrow/ripple/flagstone forms, different noise
source (terrain.py needs opensimplex+numpy, which neither this machine nor the CI
runner has). That substitution is safe only because of two properties, and a
property nobody measures is a hope:

  1. the ramps are the palette's, byte for byte;
  2. every pixel a surface emits is one of that surface's ramp colours, so the
     noise can move a shade around but can never invent one.

Property 2 is what the terrain checks actually key off — _is_water, _is_sand,
_is_stone and _is_cultivated are closed-form predicates over these colours — so
without it the substitution could silently move the ground out from under
check_terrain while every render still looked fine.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAPTURE = HERE.parent
sys.path.insert(0, str(CAPTURE))

import ground  # noqa: E402


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ramps_are_the_palettes():
    pal = _load(CAPTURE / "mirror" / "designs" / "world-mockup-v2" / "palette.py", "pal")
    assert ground.RAMPS == pal.RAMPS
    assert ground.ORDER == pal.ORDER
    assert ground.flat_colors() == pal.flat_colors()


def test_bayer_matrix_is_the_references():
    assert ground.BAYER == [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def _colours(im):
    return {p for p in im.convert("RGB").get_flattened_data()} if hasattr(
        im, "get_flattened_data") else set(im.convert("RGB").getdata())


SURFACES = [
    ("grass", ground.grass, ground.RAMP_GRASS),
    ("grass_dark", ground.grass_dark, ground.RAMP_GRASS_DARK),
    ("dirt", ground.dirt, ground.RAMP_DIRT),
    ("sand", ground.sand, ground.RAMP_SAND),
    ("sea", ground.sea, ground.RAMP_SEA),
    ("ploughed", ground.ploughed, ground.RAMP_PLOUGHED),
    ("crop_field", ground.crop_field, ground.RAMP_CROP),
]


def test_every_surface_emits_only_its_own_ramp():
    for name, fn, ramp in SURFACES:
        allowed = {ground.hx(c) for c in ramp}
        got = _colours(fn(240, 200))
        assert got <= allowed, f"{name} emitted colours outside its ramp: {sorted(got - allowed)}"
        # ...and really uses it. A field collapsed to one shade would satisfy the
        # subset test while carrying no structure at all.
        assert len(got) >= min(3, len(allowed)), f"{name} used only {len(got)} shades"


def test_surfaces_land_in_the_class_the_checks_will_read_them_as():
    """The bridge between a ramp and world_checks.py's colour predicates.

    Re-derived here from the predicates' own definitions rather than imported:
    world_checks may not import what it tests, and this file is on the tested
    side of that line.
    """
    def is_water(p):
        return p[2] - p[0] > 24 and p[2] > 80

    def is_sand(p):
        return sum(p) / 3.0 >= 172 and p[0] > p[2] and p[0] - p[2] < 95 and p[1] > p[2]

    def is_stone(p):
        if is_water(p) or is_sand(p):
            return False
        return p[0] >= p[1] >= p[2] and 100 <= sum(p) / 3.0 < 172 and (p[0] - p[2]) >= 22

    def is_cultivated(p):
        if is_water(p) or is_sand(p):
            return False
        L = sum(p) / 3.0
        if p[0] > p[1] > p[2] and p[0] - p[2] >= 40 and L < 140:
            return True
        return p[1] >= 128 and p[0] - p[2] >= 34 and p[1] - p[2] >= 45 and L < 170

    def frac(im, pred):
        px = list(im.convert("RGB").getdata())
        return sum(1 for p in px if pred(p)) / len(px)

    assert frac(ground.sea(160, 120), is_water) == 1.0
    assert frac(ground.sand(160, 120), is_sand) > 0.9
    assert frac(ground.ploughed(160, 120), is_cultivated) > 0.9
    assert frac(ground.crop_field(160, 120), is_cultivated) > 0.6
    # Grass must NOT read as tilled, or every field arm passes over open meadow.
    assert frac(ground.grass(240, 200), is_cultivated) < 0.15
    # Paving must read as stone, or a declared square can never be shown paved.
    assert frac(ground.cobble(160, 120), is_stone) > 0.5
    # ...and a dirt lane must read as road to check_on_road's own table.
    road = [(138, 106, 66), (156, 122, 78), (173, 138, 92), (188, 154, 108), (201, 168, 122)]
    px = list(ground.dirt(160, 120).convert("RGB").getdata())
    assert all(any(abs(p[i] - c[i]) < 17 for i in range(3)) for p in px for c in [
        min(road, key=lambda c: sum((p[i] - c[i]) ** 2 for i in range(3)))])


def test_the_mirror_is_identical_to_its_source():
    """sync-checks --check is a real arm here, not a formality.

    It exits 0 with SKIPPED-NO-SOURCE when the private meta workspace is absent
    (every fresh CI checkout), which is honest: with no source there is nothing
    to diff. What it must never do is pass while the two differ.
    """
    r = subprocess.run([sys.executable, str(CAPTURE / "sync-checks.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_mirrored_checks_do_not_import_the_thing_they_test():
    """world_checks.py's own first law, enforced from this side of the line."""
    src = (CAPTURE / "mirror" / "checks" / "world_checks.py").read_text()
    for forbidden in ("import raster", "import ground", "import compose", "from raster",
                      "from ground", "from compose"):
        assert forbidden not in src, f"a check must never import {forbidden!r}"
