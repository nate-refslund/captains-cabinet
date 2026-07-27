#!/usr/bin/env python3
"""Procedural ground for the headless capture — the ramps and the dither of
designs/world-mockup-v2/terrain.py, with no third-party dependency.

WHY A PORT AND NOT AN IMPORT. terrain.py needs `opensimplex` (and through it
numpy). Neither is installed on this machine or on the CI runner, and a capture
harness whose whole job is to make CI go red must not itself depend on a wheel
nobody has. What terrain.py's OUTPUT actually is — and what every colour
predicate in world_checks.py keys off — is: a value field quantised onto a small
hex ramp with a 4x4 Bayer dither, optionally furrowed or rippled. The ramps, the
dither matrix, the furrow/ripple forms and the flagstone cell rule are copied
EXACTLY. Only the noise source differs: a bicubic-upsampled lattice instead of
open simplex, summed over octaves at the same lacunarity and gain.

That substitution is stated rather than hidden because it is the one place this
file is not the reference. It changes WHERE a shade lands, never WHICH shades
exist — and which shades exist is the whole of what the terrain checks measure
(_is_water, _is_sand, _is_stone, _is_cultivated are all closed-form predicates
over the ramp colours). tests/test_ground.py asserts every emitted pixel of
every surface is one of that surface's ramp colours, so a drift in the noise can
never smuggle in a colour the palette does not have.

SPEED IS A CORRECTNESS PROPERTY HERE, not a nicety: the CI arm captures a real
frame, and a per-pixel Python field over 2400x1760 would put it out of reach and
straight into "skipped", which is a disabled sensor. Everything below is PIL
image ops (C) except the two small furrowed plots and the flagstone square.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageChops

# ---------------------------------------------------------------- the palette
# designs/world-mockup-v2/palette.py RAMPS, verbatim. Copied rather than
# imported for the same reason as above (palette.py itself is dependency-free,
# but it lives in a tree the repo does not ship); tests/test_ground.py pins this
# copy byte-for-byte against the mirrored original.
RAMPS = {
    "foliage":   ["#3A5230", "#4E6B3C", "#6A8252", "#7D9B5F", "#8CBF88", "#B9D19A", "#C7CD90"],
    "terracotta": ["#6E3A2A", "#8A4B36", "#B5674A", "#D08A63", "#E3BBA1", "#CBA46A", "#A87C4A"],
    "cream":     ["#C9B79A", "#E1D3B4", "#E9EEDA", "#F1DAB6", "#FFF5F1", "#FBEBD2", "#EFE0C4"],
    "timber":    ["#402A1E", "#5C3D28", "#7A5335", "#9A6E45", "#B98D5C", "#D2AD7C", "#6B4A30"],
    "water":     ["#2E5350", "#3E6E6B", "#5C9A93", "#79B6AC", "#A9D3C8", "#A3C5E0", "#CFE6DE"],
    "stone":     ["#4B4A52", "#6B6A72", "#8B8A90", "#A9A8AC", "#C6C4C2", "#DEDBD4", "#7C7A80"],
    "accent":    ["#E3C16F", "#E8A03C", "#C6553F", "#8E4B6B", "#E39BB0", "#5E7FA8", "#F2E3A0"],
}
ORDER = ["foliage", "terracotta", "cream", "timber", "water", "stone", "accent"]


def hx(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def flat_colors():
    out = []
    for k in ORDER:
        out += [hx(c) for c in RAMPS[k]]
    return out


# terrain.py's 4x4 Bayer matrix — the dither that keeps banding from reading as
# a gradient. Same matrix, same (BAYER+0.5)/16 threshold, expressed as integers.
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]

# terrain.py's ramps, one per surface. Dark -> light, exactly as written there.
RAMP_GRASS = ["#4E6B3C", "#5E7A46", "#6A8252", "#7A945C", "#8AA468"]
RAMP_GRASS_DARK = ["#415C33", "#4E6B3C", "#5A7745", "#67854E"]
RAMP_DIRT = ["#8A6A42", "#9C7A4E", "#AD8A5C", "#BC9A6C", "#C9A87A"]
RAMP_SAND = ["#CDB98C", "#D8C69C", "#E2D2AC", "#EBDCBB"]
RAMP_SEA = ["#3E6E6B", "#48807C", "#54918C", "#61A099", "#6FAEA6"]
RAMP_COBBLE_CELL = ["#8B8175", "#998F80", "#A79C8C", "#B4A997", "#C1B6A3", "#CEC3AF"]
RAMP_COBBLE_BASE = ["#9A9084", "#A79C8F", "#B4A99A"]
RAMP_PLOUGHED = ["#5C3D28", "#6B4A30", "#7A5335", "#8A5F3D", "#996B45"]
RAMP_CROP = ["#6A8252", "#79924F", "#8AA255", "#9DB25E", "#B4C06A"]

# compose.py:385 / iso-layout paint.ts MOTTLE_TONES — the three value-mottle
# colours with the reference's own alphas. The layout picks one per region and
# ships the index; a renderer that invented them would invent a different ground
# every time the file was read.
MOTTLE_TONES = [(152, 178, 120, 22), (98, 132, 80, 22), (178, 192, 132, 18)]


def _lattice(gw: int, gh: int, seed: int) -> Image.Image:
    rnd = random.Random(seed & 0x7FFFFFFF)
    return Image.frombytes("L", (gw, gh), bytes(rnd.getrandbits(8) for _ in range(gw * gh)))


def _fbm(w: int, h: int, seed: int, scale: float, octaves: int) -> Image.Image:
    """Fractal value noise as an L image, lacunarity 2 and gain 0.5 (terrain.py).

    `scale` is terrain.py's own: the noise is sampled at (px*scale), so an
    octave's feature size is 1/scale px. Each octave is a random lattice at that
    spacing upsampled bicubically, which is what makes it smooth rather than
    blocky; the running blend keeps the amplitude-weighted mean.
    """
    acc = None
    total = 0.0
    amp = 1.0
    for o in range(max(1, octaves)):
        cell = max(2.0, 1.0 / max(1e-6, scale * (2 ** o)))
        gw = max(2, int(w / cell) + 2)
        gh = max(2, int(h / cell) + 2)
        img = _lattice(gw, gh, seed * 1000003 + o * 7919).resize((w, h), Image.BICUBIC)
        acc = img if acc is None else Image.blend(acc, img, amp / (total + amp))
        total += amp
        amp *= 0.5
    return acc


def _bayer_image(w: int, h: int) -> Image.Image:
    """(15 - BAYER) tiled — the integer form of terrain.py's (1-d)*16 term."""
    tile = Image.new("L", (4, 4))
    tile.putdata([15 - BAYER[y][x] for y in range(4) for x in range(4)])
    out = Image.new("L", (w, h))
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            out.paste(tile, (x, y))
    return out


def _quantise(v: Image.Image, ramp_hex) -> Image.Image:
    """terrain.py's ramp lookup: index = floor(v*(k-1) + (1-d)), clamped."""
    k = len(ramp_hex)
    w, h = v.size
    a = v.point(lambda p: int(p * (k - 1) * 16 / 255))
    idx = ImageChops.add(a, _bayer_image(w, h)).point(lambda p: min(k - 1, p // 16))
    out = Image.frombytes("P", (w, h), idx.tobytes())
    pal = []
    for c in ramp_hex:
        pal += list(hx(c))
    out.putpalette(pal + [0] * (768 - len(pal)))
    return out.convert("RGB")


def field(W, H, ramp_hex, seed=1, scale=0.006, octaves=4, contrast=1.0, bias=0.0,
          block=2, furrow=None, ripple=None) -> Image.Image:
    """A quantised, dithered colour field — terrain.py's `field`, same signature.

    `block` is honoured the way terrain.py means it: the field is computed at
    1/block resolution and upsampled NEAREST, which is what gives the ground the
    same chunky grain as the 1:1 sprites (and, incidentally, makes it 4x cheaper).
    """
    block = max(1, int(block))
    w, h = max(1, W // block), max(1, H // block)
    v = _fbm(w, h, seed, scale * block, octaves)
    if contrast != 1.0 or bias != 0.0:
        v = v.point(lambda p: max(0, min(255, int(128 + (p - 128) * contrast + bias * 255))))
    mod = _modulation(w, h, block, furrow, ripple)
    if mod is not None:
        v = ImageChops.add(v, mod, 1.0, -128)
    out = _quantise(v, ramp_hex)
    if block > 1:
        out = out.resize((W, H), Image.NEAREST)
    return out


def _modulation(w, h, block, furrow, ripple):
    """The furrow and ripple terms, as a signed offset centred on 128.

    Per-pixel Python, deliberately: both are cheap trigonometric forms that no
    image op expresses, and both only ever run over a small surface — the tilled
    plots (a few hundred px across) and the sea, which is computed at 1/block
    resolution. Precomputing the column phase keeps the inner loop to two
    multiplies.
    """
    if not furrow and not ripple:
        return None
    img = Image.new("L", (w, h), 128)
    px = img.load()
    if furrow:
        period, depth, ang = furrow
        ca, sa = math.cos(ang) * block / period, math.sin(ang) * block / period
        amp = depth * 255.0
        for y in range(h):
            base = y * sa
            for x in range(w):
                px[x, y] = max(0, min(255, int(128 + math.sin((x * ca + base) * math.tau) * amp)))
    if ripple:
        period, depth = ripple
        amp = depth * 255.0
        colc = [math.cos(math.sin(x * block / (period * 2.4)) * 1.3) for x in range(w)]
        cols = [math.sin(math.sin(x * block / (period * 2.4)) * 1.3) for x in range(w)]
        for y in range(h):
            r = y * block / period
            sr, cr = math.sin(r), math.cos(r)
            for x in range(w):
                cur = px[x, y] - 128
                px[x, y] = max(0, min(255, int(128 + cur + (sr * colc[x] + cr * cols[x]) * amp)))
    return img


# ------------------------------------------------------------------- surfaces
def grass(W, H, seed=3):
    return field(W, H, RAMP_GRASS, seed=seed, scale=0.0045, octaves=5, contrast=1.15, block=2)


def grass_dark(W, H, seed=8):
    return field(W, H, RAMP_GRASS_DARK, seed=seed, scale=0.0075, octaves=4, contrast=1.2, block=2)


def dirt(W, H, seed=5):
    return field(W, H, RAMP_DIRT, seed=seed, scale=0.012, octaves=4, contrast=1.1, block=2)


def sand(W, H, seed=6):
    return field(W, H, RAMP_SAND, seed=seed, scale=0.010, octaves=4, contrast=0.95, block=2)


def sea(W, H, seed=7):
    return field(W, H, RAMP_SEA, seed=seed, scale=0.0035, octaves=3, contrast=0.9,
                 ripple=(26, 0.09), block=2)


def ploughed(W, H, seed=11):
    return field(W, H, RAMP_PLOUGHED, seed=seed, scale=0.012, octaves=3, contrast=0.85,
                 furrow=(17, 0.24, math.radians(26.5)), block=2)


def crop_field(W, H, seed=12):
    return field(W, H, RAMP_CROP, seed=seed, scale=0.011, octaves=3, contrast=0.8,
                 furrow=(17, 0.26, math.radians(26.5)), block=2)


def cobble(W, H, seed=9):
    """Flagstone paving — terrain.py's `cobble`, per-pixel because the cell hash is.

    Only ever run over the plaza's own bounding box, which is a few hundred px
    across; running it over the canvas would be minutes of Python for paving
    nobody can see outside the square.
    """
    ramp = [hx(c) for c in RAMP_COBBLE_CELL]
    base = field(W, H, RAMP_COBBLE_BASE, seed=seed, scale=0.03, octaves=3, contrast=0.7, block=2)
    px = base.load()
    CELL = 30
    for y in range(H):
        for x in range(W):
            u = (x * 0.5 + y) / CELL
            v = (x * 0.5 - y) / CELL
            cu, cv = int(u // 1), int(v // 1)
            hsh = (cu * 73856093 ^ cv * 19349663 ^ seed * 83492791) & 0xFFFF
            col = ramp[hsh % len(ramp)]
            fu, fv = u - cu, v - cv
            joint = min(fu, 1 - fu, fv, 1 - fv) < 0.055
            r, g, b = px[x, y]
            k = 0.72 if joint else 0.30
            f = 0.80 if joint else 1.0
            px[x, y] = (int(r * (1 - k) + col[0] * k * f),
                        int(g * (1 - k) + col[1] * k * f),
                        int(b * (1 - k) + col[2] * k * f))
    return base
