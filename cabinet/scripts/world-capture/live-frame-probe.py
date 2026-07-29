#!/usr/bin/env python3.12
"""live-frame-probe.py — judge a frame the twelve invariants CANNOT see.

    python3.12 cabinet/scripts/world-capture/live-frame-probe.py shot.png [...]

WHY THIS EXISTS. capture.py draws the frame it judges with raster.py, from
composeLayout's blueprint. That pipeline has no clock, no day bucket and no
PIXI stage, so every SCREEN-SPACE pass the browser composites on top of the
world — the ambience veil, weather, the killswitch wash, the glow layer — is
outside all twelve invariants at every zoom. On 2026-07-29 the dusk veil
replaced 15.6% of open water with a bright apricot at every zoom and nothing
went red; the Captain found it. This probe takes a PNG captured from the LIVE
/world and asks the one question that would have caught it: is every pixel of
open water still lawful water?

THE LAWS, and they are the renderer's, not this file's. A veil hue may darken
water but may never be brighter than the brightest sea tone, and may never be
more colourful than the water it shades. Both bounds are derived here from the
same sea ramp iso-terrain.ts declares (kept in sync by test_live_frame_probe).

CAPTURING THE INPUT (no browser dependency is added to this repo — the capture
is a two-minute local recipe, the judging is what had to be committed):

    1. pin the clock:  instance/config/platform.yml -> captain_timezone, chosen
       so the Captain-local hour lands in the bucket you want to judge
       (dawn 6-8, day 8-18, dusk 18-21, night otherwise). The render path takes
       the hour as DATA from the snapshot, so this is the only lever.
    2. run the dashboard:  cd cabinet/dashboard && npx next dev --port 3111
    3. drive a headless browser to  /world?z=<zoom>  — z is read straight off
       the query string by engine-client's parseUrlState, so any zoom is exact
       and reproducible — log in, wait for the canvas, screenshot the canvas.
    4. run this probe over the PNGs.

JUDGE AT MORE THAN ONE ZOOM. The defect above was identical at 0.35 / 0.50 /
0.60 / 1.00, but that was luck: the veil is screen-space. A pass that lives in
world space fails differently per zoom, and one capture cannot tell you which
kind you have.

Exit code 0 = every frame lawful, 1 = at least one frame is not, 2 = unusable
invocation. No frame is ever SKIPPED for being hard to judge: a frame with no
open water in it says so and is reported as unjudged, because a probe that
quietly judges nothing is the disabled sensor this whole file exists to be.
"""
from __future__ import annotations

import collections
import math
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover - the message IS the behaviour
    print("live-frame-probe: needs Pillow (python3.12 -m pip install Pillow)",
          file=sys.stderr)
    raise SystemExit(2)

# iso-terrain.ts RAMPS.sea, dark -> light. The ONE place these five tones are
# duplicated outside the renderer; test_live_frame_probe.py pins them equal.
SEA = [(0x3E, 0x6E, 0x6B), (0x48, 0x80, 0x7C), (0x54, 0x91, 0x8C),
       (0x61, 0xA0, 0x99), (0x6F, 0xAE, 0xA6)]

# terrain-pattern.ts DAWN/DUSK/NIGHT_VEIL_HUES, mirrored so a green can name
# the veil it judged. test_live_frame_probe.py parses the TypeScript and pins
# these equal — the same trick that pins SEA.
VEILS = {
    "dawn": [(0x8C, 0x8C, 0x94), (0xA7, 0x9C, 0x8F)],
    "dusk": [(0x7C, 0x7C, 0x84), (0x6C, 0x6C, 0x74), (0x4C, 0x7C, 0x6C)],
    "night": [(0x24, 0x34, 0x4C), (0x34, 0x34, 0x4C), (0x2C, 0x34, 0x4C)],
}

# Window sizes, tried LARGEST FIRST: a big window is better evidence, but at
# close zoom the island fills the frame and no 150px square is clean open water.
# Falling back to smaller squares is what keeps zoom 1.0 and 2.0 judgeable
# instead of permanently UNJUDGED — and "unjudged at the zoom the Captain
# actually looks at" is how a blind spot survives while the report reads green.
BOXES = (150, 100, 64)
STEP = 50          # window stride, px
SEA_FLOOR = 0.30   # a window is open water when this much of it is sea ramp
# ...and whatever else is in it is DITHER-SHAPED rather than another surface.
# Measured as the mean fraction of a non-sea pixel's four neighbours that are
# also non-sea: a seeded dither at 16% coverage scores ~0.16 and at 42% ~0.42,
# while a beach, a cobbled quay or a roof scores ~0.95 because its pixels are
# contiguous. Counting DISTINCT non-sea tones instead (the first version of this
# qualifier) let a cobbled quay through as "water" — and the dusk veil hues are
# themselves in the cobble family, so that confusion was guaranteed, not
# hypothetical. It also false-RED'd a sand beach, which is legitimately brighter
# than water. Shape is the honest discriminator; count was a proxy for it.
DITHER_MAX = 0.75
# A window of one flat colour proves nothing about a veil — it is what a frame
# that failed to render looks like. Refuse it rather than call it lawful.
MIN_TONES = 2
# ...and a tone thinner than this is a sprite pixel, a buoy, a wave-ring dash or
# an antialiased card edge, not a veil: the thinnest lawful veil puts
# coverage/len(hues) = 8%/2 = 4% of the window on each of its hues. A window
# containing such a tone is not clean open water, so it is SKIPPED rather than
# judged — the alternative is reporting the mist band as an unlawful veil, which
# the first version of this probe did the moment it started picking the worst
# window instead of the cleanest one.
MIN_TONE_SHARE = 0.005
# A VEIL IS UNIFORM. It is a screen-space dither over the whole frame, so its
# share of any quadrant of a window equals its share of the window. A beach, a
# quay or a coastline crossing the window puts its pixels on ONE side. This is
# the qualifier that per-tone clustering could not supply: a real quay is itself
# finely interleaved cobble tones, so each tone is individually scattered and
# looks exactly like a dither until you ask WHERE it is.
QUADRANT_SPREAD = 3.0

def luma(c: tuple[int, int, int]) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def chroma(c: tuple[int, int, int]) -> float:
    def lin(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in c)

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx = f((r * .4124 + g * .3576 + b * .1805) / .95047)
    fy = f(r * .2126 + g * .7152 + b * .0722)
    fz = f((r * .0193 + g * .1192 + b * .9505) / 1.08883)
    return math.hypot(500 * (fx - fy), 200 * (fy - fz))


LUMA_CAP = max(luma(c) for c in SEA)
CHROMA_CAP = max(chroma(c) for c in SEA)


def _uniform(im, x0, y0, box, sea_set) -> bool:
    """True when the non-water pixels are spread evenly across the window.

    Counted EXACTLY, per quadrant, through getcolors rather than a strided
    pixel walk: a strided walk aliases against a periodic dither (a mod-6
    diagonal sampled every 2px reads as 100% foreign on some rows and 0% on
    others) and rejects the very thing it is meant to accept.
    """
    half = box // 2
    shares = []
    for qy in (0, half):
        for qx in (0, half):
            counts = im.crop((x0 + qx, y0 + qy, x0 + qx + half, y0 + qy + half)).getcolors(
                maxcolors=1 << 24)
            if counts is None:
                return False
            total = half * half
            foreign = sum(n for n, col in counts if col not in sea_set)
            shares.append(foreign / total if total else 0.0)
    lo, hi = min(shares), max(shares)
    if hi == 0.0:
        return True            # no veil at all is uniform by definition
    return lo > 0.0 and hi / lo <= QUADRANT_SPREAD


def _clustering(px, x0, y0, box, tone) -> float:
    """How contiguous ONE tone's pixels are: ~its coverage for a scattered
    dither, ~1 for a surface. Per-tone rather than per-window, because a window
    straddling a boundary averages a solid card and a sparse dither into a
    number that looks like neither — measured on real frames, that let the
    onboarding card's cream through as 35% of an 'open water' window.
    Sampled on a stride so the probe stays instant on a 1200x878."""
    hits = 0
    neigh = 0
    for y in range(y0 + 1, y0 + box - 1, 2):
        for x in range(x0 + 1, x0 + box - 1, 2):
            if px[x, y] != tone:
                continue
            hits += 1
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if px[nx, ny] == tone:
                    neigh += 1
    return 0.0 if hits == 0 else neigh / (4 * hits)


def open_water(im: Image.Image):
    """The WORST open-water window, or None when the frame has no judgeable sea.

    Worst, not most-watery. The first version of this maximised the sea count,
    and because unlawful pixels are by definition NOT sea, that rule actively
    preferred the window with the least defect: a frame with the veil over half
    its ocean and clean water elsewhere came back OK. A probe whose selection
    rule looks away from the thing it is looking for is worse than no probe.

    The window is found mechanically rather than from a hand-picked rectangle,
    which silently stops being water the moment the camera or coastline moves.
    """
    px = im.load()
    w, h = im.size
    sea_set = set(SEA)
    for box in BOXES:
        best = None
        for y in range(0, max(1, h - box), STEP):
            for x in range(0, max(1, w - box), STEP):
                counts = im.crop((x, y, x + box, y + box)).getcolors(maxcolors=1 << 24)
                if counts is None:      # only reachable if box**2 > 2**24
                    continue
                hist = collections.Counter({col: n for n, col in counts})
                total = box * box
                sea = sum(n for col, n in hist.items() if col in sea_set)
                if sea / total < SEA_FLOOR:
                    continue
                if len(hist) < MIN_TONES:
                    continue          # a flat fill; it proves nothing
                # Everything that is not water must be a DITHER over the water —
                # not a coastline, a quay, a card or a sprite. Judged per tone.
                foreign = [(col, n) for col, n in hist.items() if col not in sea_set]
                if any(n / total < MIN_TONE_SHARE for _, n in foreign):
                    continue          # a sprite, a dash, an antialiased edge
                if any(_clustering(px, x, y, box, col) > DITHER_MAX for col, _ in foreign):
                    continue          # a second surface, not a veil
                if not _uniform(im, x, y, box, sea_set):
                    continue          # a coastline crosses it, not a veil
                unlawful = sum(n for col, n in foreign
                               if luma(col) > LUMA_CAP or chroma(col) > CHROMA_CAP)
                if best is None or unlawful / total > best[0] / best[4]:
                    best = (unlawful, (x, y), hist, box, total)
        if best is not None:
            return best
    return None


def _which_veil(hist, sea_set) -> str:
    """Name the veil actually present, so a green says WHAT it judged.

    A green that cannot distinguish "the veil is lawful" from "there is no veil
    here" is a green about the wrong frame — captured at the wrong clock, or
    with the day bucket, where every veil is trivially lawful.
    """
    tones = frozenset(col for col in hist if col not in sea_set)
    for name, hues in VEILS.items():
        if tones and tones <= set(hues):
            return name
    return 'none/unrecognised'


def judge(path: str) -> int:
    im = Image.open(path).convert('RGB')
    found = open_water(im)
    if found is None:
        print(f"UNJUDGED {path}: no judgeable open-water window at any of "
              f"{BOXES} px (needs >= {SEA_FLOOR:.0%} sea-ramp pixels, more than "
              f"one tone, and a dither rather than a second surface) — this "
              f"frame proves nothing")
        return 1
    unlawful, at, hist, box, total = found
    sea_set = set(SEA)
    veil = _which_veil(hist, sea_set)
    if unlawful == 0:
        print(f"OK       {path}: worst {box}px open-water window at {at} is all "
              f"lawful ({len(hist)} tones, veil={veil})")
        return 0
    worst = sorted(((n, col) for col, n in hist.items()
                    if col not in sea_set
                    and (luma(col) > LUMA_CAP or chroma(col) > CHROMA_CAP)),
                   reverse=True)[:3]
    print(f"UNLAWFUL {path}: {unlawful / total:.1%} of the worst {box}px "
          f"open-water window at {at} breaks the veil laws "
          f"(luma <= {LUMA_CAP:.1f}, chroma <= {CHROMA_CAP:.1f})")
    for n, col in worst:
        print(f"           {col} luma={luma(col):.1f} chroma={chroma(col):.1f} "
              f"({n * 100 / total:.1f}% of the window)")
    return 1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    # EVERY frame is judged before the verdict. `all(judge(p) == 0 for p ...)`
    # short-circuits on the first red, so a run over five zooms would report
    # one and stay silent about four — one red masking the next.
    return 0 if sum(judge(p) for p in argv) == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
