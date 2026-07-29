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

BOX = 150          # probe window, px
STEP = 50          # window stride, px
SEA_FLOOR = 0.30   # a window is open water when this much of it is sea ramp
# ...and whatever else is in it comes from few enough distinct tones to be a
# dither rather than a coastline. A veil is 1-3 hues and the wave dashes add a
# couple; grass, sand and roofs bring hundreds. Counting DISTINCT tones instead
# of capping foreign MASS is what lets the night veil (42% coverage, three
# navies) be judged at all — a mass cap rejected every night frame as "not
# water", which is a probe that reports nothing about the densest veil there is.
NON_SEA_TONES = 8


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


def open_water(im: Image.Image):
    """The most water-dominated window, or None when the frame has no sea.

    Found mechanically rather than by a hand-picked rectangle: a hardcoded box
    silently stops being water the moment the camera or the coastline moves,
    and then the probe reports green about land.
    """
    w, h = im.size
    sea_set = set(SEA)
    best = None
    for y in range(0, max(1, h - BOX), STEP):
        for x in range(0, max(1, w - BOX), STEP):
            counts = im.crop((x, y, x + BOX, y + BOX)).getcolors(maxcolors=1 << 24)
            hist = collections.Counter({col: n for n, col in counts})
            total = BOX * BOX
            sea = sum(n for col, n in hist.items() if col in sea_set)
            if sea / total < SEA_FLOOR:
                continue
            if sum(1 for col in hist if col not in sea_set) > NON_SEA_TONES:
                continue          # a coastline or a sprite, not open water
            unlawful = sum(n for col, n in hist.items()
                           if col not in sea_set
                           and (luma(col) > LUMA_CAP or chroma(col) > CHROMA_CAP))
            if best is None or sea > best[0]:
                best = (sea, (x, y), hist, unlawful, total)
    return best


def judge(path: str) -> int:
    im = Image.open(path).convert('RGB')
    found = open_water(im)
    if found is None:
        print(f"UNJUDGED {path}: no open-water window — capture a zoom that "
              f"shows sea, this frame proves nothing")
        return 1
    _, at, hist, unlawful, total = found
    share = unlawful / total
    if unlawful == 0:
        print(f"OK       {path}: open water at {at} is all lawful "
              f"({len(hist)} distinct tones)")
        return 0
    worst = sorted(((n, col) for col, n in hist.items()
                    if col not in set(SEA)
                    and (luma(col) > LUMA_CAP or chroma(col) > CHROMA_CAP)),
                   reverse=True)[:3]
    print(f"UNLAWFUL {path}: {share:.1%} of open water at {at} breaks the veil "
          f"laws (luma <= {LUMA_CAP:.1f}, chroma <= {CHROMA_CAP:.1f})")
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
