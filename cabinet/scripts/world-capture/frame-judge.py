#!/usr/bin/env python3.12
"""frame-judge.py — judge REAL composited browser frames, across the clock and the zoom.

    python3.12 cabinet/scripts/world-capture/frame-judge.py /tmp/world-frames
    python3.12 .../frame-judge.py DIR --json report.json

INPUT is a directory written by `cabinet/dashboard/frame-harness/shoot.mjs`: PNGs
plus `frames.json`, which names each frame's state, HOUR, bucket, zoom, weather
and killswitch. Every lit frame is paired there with a DAY twin at the identical
state, zoom, weather and canvas size — the pairing is what most of the arms below
rest on.

────────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS

`capture.py` runs the twelve invariants over a frame `raster.py` DRAWS from
`composeLayout`'s blueprint. That pipeline has no clock, no day bucket and no
PIXI stage — `grep -r 'veil\\|clockHour\\|bucket'` across it returns nothing — so
the ambience remap, the weather layer, the killswitch wash and the glow sit
outside all twelve checks at every zoom. On 2026-07-29 a dusk veil replaced 15.6%
of every pixel in the frame, three hours a day, and every arm stayed green; the
Captain found it by looking at a picture. **A check that judges a re-derivation
of the render is testing the model, not the product.**

This is ADDITIVE. The blueprint path is fast, deterministic and catches layout
defects a frame cannot (a sprite declared and not drawn needs the declaration).
It keeps every check it has. What is here is the half it structurally cannot see.

────────────────────────────────────────────────────────────────────────────────
THE ARMS, and what each would have caught

  determinism   Two captures of one URL must be identical. Not a world law — the
                PRECONDITION for every day-vs-bucket arm below. Measured 0
                differing pixels of 960000 on the shipped renderer, so a red here
                means the pairs are comparing noise and no other verdict stands.

  ambience      The shipped frame's grade must be the grade the ambience module
                PREDICTS: remap the day twin's colours through ambience_py (the
                port pinned to `ambience-derived.json`, which lib/world/
                ambience.ts emits and ambience.test.ts pins to itself) and
                compare the two histograms. Measured on the shipped renderer over
                3 zooms x 3 lit buckets: mean within 0.1 of 255, saturation within
                0.001, sd within 0.6, span within 3. This is the arm that answers
                the question live-frame-probe's docstring names and cannot reach —
                whether the GPU indexes that table correctly, at every zoom, over
                a real composed frame. It goes red on: the filter not applied at
                all, the wrong bucket for the hour, any wash or veil with mass,
                any hue shift.

  grain         Mean |ΔL| between horizontally adjacent pixels must not EXCEED the
                day twin's. This is THE AMBIENCE STRUCTURE LAW (lib/world/
                ambience.ts) measured on the product: ambience is a function of
                the PIXEL, never of its POSITION, and a per-colour map cannot
                create an edge where none existed. There is no tuned constant —
                the bound is the day frame's own grain. Measured: the shipped
                remap runs 0.30-0.68x, and the dither it replaced ran 4.0x
                (sea 5.5 -> 31.8). The two arms are complementary and neither
                subsumes the other: `ambience` reads the histogram (WHICH colours,
                in what proportion) and `grain` reads the structure (WHERE they
                sit), and a pass that swapped two pixels would move only the
                second.

  grade         world_checks.check_light's grade arm, verbatim, through the
                mirror, on every DAY frame — the first time a real browser frame
                has been put in front of any of the twelve. Day is its calibration
                domain: its bounds were fitted on daylight stills and a night
                frame legitimately measures mean 64 against its floor of 95. The
                lit buckets are covered by `ambience` instead, which is strictly
                tighter than a bound would be.

  surface       THE NEIGHBOUR LAW, and the one arm here that asks whether a hue
                is plausible IN THE PLACE IT LANDED. Every screen-space pass in
                this renderer — ambience, weather, the killswitch wash — is a
                decision per COLOUR, so over any patch of the frame it may MERGE
                a surface's tones and may never ADD one. Measured per 16x16 tile
                against the twin that differs only in the pass under test.
                This is what a membership test structurally cannot do:
                PALETTE_FOREIGN_MASS asks whether a pixel is a corpus colour and
                never whether it is a plausible neighbour of the surface it sits
                on, so the 2026-07-29 dusk veil satisfied it BY CONSTRUCTION —
                every apricot pixel was a legitimate corpus sand tone, sprayed
                across open water. Measured on the shipped renderer: 0.4-5.5% of
                tiles gain a colour legitimately (the GPU's LUT and ambience_py's
                nearest-native snap disagree on ~14% of pixels), against 77.6%
                for that veil. ITS FIRING FLOOR, measured rather than asserted
                (2026-07-30, on this file's own chroma-veil fixture): the arm
                reads 12.3% and goes RED at 0.20% coverage and reads 11.3% and
                PASSES at 0.18%, so the floor is ~0.19% and NOT the 0.05% an
                earlier version of this paragraph implied — that sentence quoted
                a reading "over 10%" as if it were a detection, and 10% is under
                the 12% limit. It is still ~1/25th of the mass
                PALETTE_FOREIGN_MASS needs. It also catches what `ambience` and
                `grain` provably cannot: a LUMINANCE-MATCHED chroma veil moves no
                edge energy and almost no histogram, so at 0.4% coverage both of
                those arms pass it and this one reads 0.512. And it is the only
                arm that judges weather and the killswitch COMPOSED WITH
                ambience rather than as a layer.

  soil          THE CONTENT LAW, and the only arm here that compares nothing.
                Every arm above reads a lit frame against its DAY TWIN, and a
                twin carries a CONTENT defect exactly as the frame does —
                measured 2026-07-30 by injecting the 2026-07-29 dither into
                `terrainField` itself and re-capturing: corpus sand over land,
                and determinism/ambience/grain/surface/grade/water/killswitch
                ALL STAYED GREEN. `soil` reads the sprites-free GROUND layer
                (the renderer's own `groundOnly` pass) and asks whether the
                ground steps further between two adjacent pixels than its own
                shipped ladder ever does. It went red on that build at 59.7-90.0%
                of ground tiles against a 45% limit. Its two measured holes are
                in its docstring and in README.frame.md.

  water         live-frame-probe's veil laws, run over EVERY frame in the sweep
                rather than over one PNG someone captured by hand. Ambience may
                darken water; it may never make it brighter or more colourful
                than any water this world draws.

  killswitch    The red wash is the third pass outside the twelve. When the sweep
                carries a killswitch pair, the killswitch frame must be
                measurably DESATURATED against its twin, and the twin must not be.
                Measured: saturation 0.417 -> 0.270 at day, 0.403 -> 0.264 at
                night. Absent a pair this reports UNJUDGED and does not claim the
                surface — it is never silently green.

────────────────────────────────────────────────────────────────────────────────
WHAT THIS DOES NOT COVER, said here rather than discovered later

  * The `ambience` and `grain` arms judge the sweep with weather=sun and the
    killswitch OFF. Both overlays draw ABOVE the ambience filter and are
    therefore not remapped, so under rain the prediction drifts +0.8 mean / +0.07
    saturation and under fog +3.9 — measured, not feared. Judging them together
    would mean loosening the tolerance that makes the ambience arm worth having.
    `surface` closes exactly that composition gap, because its law survives an
    unremapped overlay: measured 0.4% of tiles gain a colour for night-under-fog
    against its own fogged day twin, identical to the sun figure, and 0.0% for
    the killswitch wash. What is still uncovered is the overlay judged against a
    frame WITHOUT it — fog is not a per-colour map of the sun frame (it reads
    13.2%), so the twin must carry the same weather.
  * `soil` has two holes of its own, both measured in the run that built it.
    NIGHT: the shipped night grass ladder steps 40 per channel by itself, so the
    derived bound has no purchase and the injected defect reads 0.3-0.4% there.
    ZOOM 0.5: the injection reached 0.27% of that frame's pixels against 19.9%
    at z2, so the widest shot proves nothing in either direction.
  * The nine layout invariants (roads, stacking, art, traceability, era, terrain,
    depth order, shadows) still run on the blueprint. The sprites-free ground
    layer now HAS a capture door (`groundOnly`), which `soil` uses and which
    unblocks the pixel halves of check_terrain / check_on_road /
    check_paint_fidelity — none of them wired here. The two id buffers are still
    missing, so check_depth_order and check_shadows stay blocked. See
    README.frame.md.
  * The DOM half of /world (chips, cards, the HUD) is not on this canvas at all.

EXIT 0 = every arm green, 1 = at least one red or unjudgeable, 2 = unusable
invocation. NOTHING IS EVER SKIPPED for being hard: a missing twin, a frame with
no judgeable water, a sweep with no lit frame in it — each is a non-zero exit
with the reason. A capture that quietly judged nothing is the disabled sensor
this whole programme keeps finding in its own tests.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageStat
except ImportError:  # pragma: no cover - the message IS the behaviour
    print("frame-judge: needs Pillow (python3.12 -m pip install Pillow)", file=sys.stderr)
    raise SystemExit(2)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ambience_py                                    # noqa: E402
# The twelve live in the mirror, which is what CI runs. Importing check_light
# rather than re-deriving a grade rule is the point: this file adds a capture,
# not a second opinion about exposure.
#
# WHAT GUARDS THE MIRROR, stated exactly rather than optimistically: an earlier
# version of this comment said `sync-checks.py --check` guards it against the
# private source. It does — ON A LAPTOP THAT HAS THAT SOURCE. In CI
# `~/cabinet-meta` is absent, `--check` prints SKIPPED-NO-SOURCE and exits 0
# without diffing anything, which is its own documented behaviour and honest on
# its own terms. So in the environment this file actually runs in, the mirror is
# guarded by git history and by the mirrored checks being EXERCISED here against
# a real capture — not by that diff. (Backlog: nothing pins the mirror's
# content in CI.)
sys.path.insert(0, str(HERE / "mirror" / "checks"))
import world_checks                                   # noqa: E402

# live-frame-probe.py carries a hyphen, so it is loaded by path rather than
# imported. Reused rather than re-implemented: its veil laws are already pinned
# by nine self-arms in tests/test_live_frame_probe.py, and a second opinion about
# what lawful water is would be one more thing to get wrong.
import importlib.util                                 # noqa: E402
_spec = importlib.util.spec_from_file_location("live_frame_probe", HERE / "live-frame-probe.py")
_probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_probe)


# ── tolerances, and where each number comes from ────────────────────────────
# MEASURED on the shipped renderer, 2026-07-30, over hamlet x {dawn,dusk,night} x
# zoom {0.5, 1.0, 2.0} — the worst cell of the nine in each column:
#
#     mean |Δ| 0.1/255   sd |Δ| 0.6   saturation |Δ| 0.001   span |Δ| 3
#
# The bounds below sit ~4-15x above the worst observed agreement and far under
# any defect this arm exists for: the 2026-07-29 dusk veil moved saturation by
# more than 0.05 and mean by several units at 16% coverage, and a filter that
# fails to apply at all moves mean by 50. They are a NOISE FLOOR for the
# nearest-native snap disagreeing with the GPU on a tie, not a quality dial —
# there is nothing here to relax when a frame goes red.
AMB_MEAN = 1.5
AMB_SD = 2.5
AMB_SAT = 0.015
AMB_SPAN = 8
# The killswitch wash measured a 0.147 absolute saturation drop at day and 0.139
# at night. A third of the smaller of those is comfortably below the effect and
# far above the 0.001 the ambience pair agrees to, so a wash that stopped drawing
# is caught and a wash that merely changed shade is not accused.
KS_SAT_DROP = 0.045

# ── the surface arm's two numbers, and why neither is a dial ────────────────
# SURFACE_TILE is the tile the law is stated over. 16 is the world's own
# tile_size (world.map/v1), so a tile is one authored surface cell rather than an
# arbitrary window — which is the whole point of asking the question per SURFACE.
SURFACE_TILE = 16
# SURFACE_EXCESS is a NOISE FLOOR for one measured fact: the shipped GLSL filter
# and ambience_py's nearest-native snap disagree on ~14% of pixels (measured
# 2026-07-30 — 85.9% of a night z2 frame is EXACTLY remap(day), and where they
# differ the difference is small and spread evenly rather than clustered on any
# object). That disagreement lets a tile gain a tone with nothing wrong. Measured
# over 30 legitimate cells — 3 zooms x 3 lit buckets x {sun,rain,fog,storm} x
# {killswitch on, off} — the worst was 5.5% of tiles (dawn z2) and the best 0.4%.
# The defect this exists for reads 77.6% at its historical strength and stays
# over 10% at 0.05% coverage, so the gap between the floor and the failure is a
# factor of 14 at the very worst and a factor of 200 in the case that was
# actually shipped. There is nothing here to relax when a frame goes red.
SURFACE_EXCESS = 0.12

# ── the soil arm's three numbers, and the one that is DERIVED ───────────────
# SOIL_TILE is SURFACE_TILE's reason: the world's own tile_size, so a window is
# an authored cell.
SOIL_TILE = 16
# A tile counts as DITHERED when more than this share of its adjacent pixel
# pairs step further than the ground's own ladder ever does. A sprite edge
# crossing a 16px tile contributes ~16-32 of its 480 pairs (3-7%); a pass drawn
# per POSITION crosses on every one of its pixels, and the 2026-07-29 dither's
# own geometry puts a third of a tile's pairs over the bound. Measured below.
SOIL_PAIR = 0.15
# ...and the frame is red when more than this share of judged tiles is dithered.
# MEASURED over all twelve ground cells of the shipped renderer — 4 buckets x 3
# zooms — the worst was 23.9% (day z0.5, where the island is small and almost
# every judged tile holds a coastline or a dressing sprite) and the best 0.0%.
# The 2026-07-29 defect class re-run through the REAL ground layer — corpus sand
# (212,156,84) on land, below the ambience filter, where every twin-comparing
# arm is blind because the twin carries it too — reads 81.3-100% at every zoom
# and at both mod-6 and mod-12 spacing. So the floor sits 1.9x over the worst
# lawful frame and 1.8x under the weakest catch. NOT A DIAL: a red here is a
# ground layer taking steps its own ladder does not take.
SOIL_EXCESS = 0.45
# A sweep whose ground frame yields fewer judged tiles than this has not looked
# at the ground. Measured minimum on the shipped renderer: 248 tiles (night
# z0.5). Never a silent pass — below the floor the arm reports UNJUDGED.
SOIL_MIN_TILES = 100


def _luma(c) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def label(f: dict) -> str:
    """One frame, named by every axis that makes it a different frame.

    Every axis, because two arms that collide on a name are one arm in the
    report — and the run that found this had a killswitch frame and its twin
    both printing `grade[z0.5]`, one PASS and one FAIL, which reads as a flake.
    """
    return (f"{f['bucket']}@z{f['zoom']}"
            + ("" if f["weather"] == "sun" else f"/{f['weather']}")
            + ("/ks" if f.get("killswitch") else ""))


def _hist(path: Path) -> collections.Counter:
    """Every colour in the frame with its count. Exact — no striding.

    A stride aliases against a periodic dither, which is precisely the defect
    class these arms exist for: the 2026-07-29 veil ran on a mod-6 diagonal and a
    2px walk read it as 100% of some rows and 0% of others.

    `getcolors` counts in C. `maxcolors` is the full 24-bit space so it can never
    return None and fall through to a partial count — a frame with more distinct
    tones than expected is a fact about the frame, not a reason to measure less
    of it.
    """
    im = Image.open(path).convert("RGB")
    counts = im.getcolors(maxcolors=1 << 24)
    if counts is None:  # pragma: no cover - unreachable at 24-bit maxcolors
        return collections.Counter(im.getdata())
    return collections.Counter({col: n for n, col in counts})


def _grade(hist: collections.Counter) -> tuple[float, float, float, int]:
    """mean luminance, contrast, saturation, tonal span — from the histogram.

    The same four quantities check_light's grade arm reads, computed here off the
    exact histogram so the prediction and the frame are measured identically.
    """
    n = 0
    sl = sl2 = ss = 0.0
    bins = [0] * 256
    for (r, g, b), k in hist.items():
        n += k
        lum = (r + g + b) / 3.0
        sl += lum * k
        sl2 += lum * lum * k
        bins[int(lum)] += k
        mx, mn = max(r, g, b), min(r, g, b)
        ss += (0.0 if mx == 0 else (mx - mn) / mx) * k
    if n == 0:
        return 0.0, 0.0, 0.0, 0
    mean = sl / n
    sd = math.sqrt(max(0.0, sl2 / n - mean * mean))
    c = p01 = p99 = 0
    for i, v in enumerate(bins):
        c += v
        if not p01 and c >= n * 0.01:
            p01 = i
        if c >= n * 0.99:
            p99 = i
            break
    return mean, sd, ss / n, p99 - p01


def _grain(path: Path) -> float:
    """Mean |ΔL| between horizontally adjacent pixels — the art's own dither
    energy, and the quantity THE AMBIENCE STRUCTURE LAW is stated in.

    EVERY adjacent pair in the frame, with no stride at all: a stride is what
    aliases against a periodic dither, and a periodic dither is the defect. The
    whole thing is one PIL difference of the luminance plane against itself
    shifted one pixel, so exhaustive costs less here than a sampled Python walk.
    """
    im = Image.open(path).convert("RGB")
    # The Rec.709 matrix is spelled out because PIL's bare convert('L') uses the
    # ITU-R 601 weights, and this file, _luma and ambience_py have to agree on
    # what luminance means or the arms are measuring three different things.
    lum = im.convert("L", (0.2126, 0.7152, 0.0722, 0))
    w, h = lum.size
    if w < 2:
        return 0.0
    return ImageStat.Stat(ImageChops.difference(
        lum.crop((0, 0, w - 1, h)), lum.crop((1, 0, w, h)))).mean[0]


_QUANT_BITS = ambience_py._quant_bits()
_QUANT_CENTRE = 1 << (8 - _QUANT_BITS - 1)
_remap_cache: dict = {}


def _remap(col: tuple, bucket: str) -> tuple:
    """ambience_py.remap, memoized on the QUANTIZED source.

    The GPU's LUT is indexed by the palette's own bit depth, and `remap`
    quantizes before it does anything else — so every colour in a 5-bit bin has
    the same answer, and caching on the bin rather than on the colour collapses a
    frame's few thousand distinct tones onto a few hundred nearest-native
    searches. Measured: 0.8ms per uncached search against 2952 native colours,
    which is 36s of the judge's runtime without this and ~4s with it.
    """
    q = tuple((((c >> (8 - _QUANT_BITS)) << (8 - _QUANT_BITS)) | _QUANT_CENTRE) for c in col)
    key = (q, bucket)
    hit = _remap_cache.get(key)
    if hit is None:
        hit = _remap_cache[key] = ambience_py.remap(q, bucket)
    return hit


def _predict(day_hist: collections.Counter, bucket: str) -> collections.Counter:
    """The day frame's histogram, put through the renderer's own ambience table.

    Per DISTINCT COLOUR rather than per pixel — a 1200x800 frame carries a few
    thousand distinct tones, so the whole prediction is a few thousand snaps
    instead of a million.
    """
    out: collections.Counter = collections.Counter()
    for col, k in day_hist.items():
        out[_remap(col, bucket)] += k
    return out


# ── result plumbing ─────────────────────────────────────────────────────────
def _ok(name, detail):
    return (name, True, detail)


def _red(name, detail):
    return (name, False, detail)


def _unjudged(name, why):
    """NOT a pass. Nothing was measured, so nothing may be claimed.

    Every absence in this file goes through here and every one of them is a
    non-zero exit, because the alternative — a green that means "there was
    nothing to look at" — is the exact shape of every disabled sensor this
    programme has found in its own tests.
    """
    return (name, False, f"UNJUDGED — {why}; nothing was measured, so nothing is claimed")


# ── the arms ────────────────────────────────────────────────────────────────
def arm_determinism(man: dict, root: Path) -> list:
    d = man.get("determinism")
    if not d or not d.get("a") or not d.get("b"):
        return [_unjudged("determinism", "the manifest carries no re-shot twin")]
    a, b = Path(d["a"]), Path(d["b"])
    if not a.exists() or not b.exists():
        return [_unjudged("determinism", f"twin missing on disk ({a.name} / {b.name})")]
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return [_red("determinism", f"the two captures are {ia.size} and {ib.size}")]
    # Per-channel MAX of the difference, not its luminance. `convert('L')` would
    # weight the channels (ITU-601), and a pure one-unit red difference rounds to
    # zero there — a determinism arm that reads two different frames as identical
    # is the fail-open every other arm here is standing on.
    dr, dg, db = ImageChops.difference(ia, ib).split()
    worst = ImageChops.lighter(ImageChops.lighter(dr, dg), db)
    diff = sum(n for n, v in (worst.getcolors(maxcolors=256) or []) if v != 0)
    tot = ia.size[0] * ia.size[1]
    if diff:
        return [_red("determinism",
                     f"{diff} of {tot} pixels differ between two captures of {a.name} — "
                     "every day-vs-bucket arm below is comparing noise")]
    return [_ok("determinism", f"two captures of {a.name} are identical ({tot} px)")]


def arm_ambience(pairs: list) -> list:
    """The shipped frame's grade must be the grade the ambience module predicts."""
    out = []
    for lit, day in pairs:
        dh = _hist(Path(day["file"]))
        bh = _hist(Path(lit["file"]))
        pm, psd, psat, pspan = _grade(_predict(dh, lit["bucket"]))
        am, asd, asat, aspan = _grade(bh)
        bad = []
        if abs(am - pm) > AMB_MEAN:
            bad.append(f"mean {am:.1f} vs predicted {pm:.1f}")
        if abs(asd - psd) > AMB_SD:
            bad.append(f"contrast {asd:.1f} vs predicted {psd:.1f}")
        if abs(asat - psat) > AMB_SAT:
            bad.append(f"saturation {asat:.3f} vs predicted {psat:.3f}")
        if abs(aspan - pspan) > AMB_SPAN:
            bad.append(f"span {aspan} vs predicted {pspan}")
        name = f"ambience[{label(lit)}]"
        detail = (f"h{lit['hour']:02d} -> {lit['bucket']}: mean {am:.1f}/{pm:.1f} "
                  f"sd {asd:.1f}/{psd:.1f} sat {asat:.3f}/{psat:.3f} span {aspan}/{pspan}")
        out.append(_red(name, detail + f"; FAIL {bad}") if bad else _ok(name, detail))
    return out


def arm_grain(pairs: list) -> list:
    """THE AMBIENCE STRUCTURE LAW, measured. The bound is the day frame's own."""
    out = []
    for lit, day in pairs:
        gd = _grain(Path(day["file"]))
        gb = _grain(Path(lit["file"]))
        name = f"grain[{label(lit)}]"
        # The degenerate end FIRST. Building the ratio before testing the
        # denominator raised ZeroDivisionError on a flat day frame — caught by
        # this file's own flat-twin arm, which is the whole reason that arm asks
        # for zero rather than for something merely small.
        if gd <= 0:
            out.append(_unjudged(name, "the day twin has no adjacent-pixel energy at all — "
                                       "it is a flat fill, and a ratio against zero proves nothing"))
            continue
        detail = f"adjacent |dL| {gb:.2f} against the day frame's own {gd:.2f} ({gb / gd:.2f}x)"
        if gb > gd:
            out.append(_red(name, detail + " — ambience ADDED structure the art did not draw, "
                                           "which is a decision per POSITION and not per colour"))
        else:
            out.append(_ok(name, detail))
    return out


def _tile_tones(path: Path, tile: int = SURFACE_TILE) -> dict:
    """Distinct EXACT colours per tile, keyed by the tile's top-left corner.

    EXACT rather than quantized, and that is what makes the law tight rather
    than approximate: every screen-space pass here maps a colour to a colour, so
    |pass(S)| <= |S| holds for any pixel set S with no tolerance at all. Quantize
    first and the claim weakens — two colours in one bin may leave it on
    different sides, which would be a bin artefact reported as a defect.

    Partial tiles at the right and bottom edge are DROPPED rather than measured
    short: a 40px-wide strip holds fewer pixels and therefore fewer tones, which
    would make an edge tile systematically look better than a full one.
    """
    im = Image.open(path).convert("RGB")
    px = im.load()
    w, h = im.size
    out: dict = {}
    for ty in range(0, h - tile + 1, tile):
        for tx in range(0, w - tile + 1, tile):
            s = set()
            for y in range(ty, ty + tile):
                for x in range(tx, tx + tile):
                    s.add(px[x, y])
            out[(tx, ty)] = len(s)
    return out


def arm_surface(pairs: list) -> list:
    """THE NEIGHBOUR LAW: a screen-space pass may merge a surface's tones, never
    add one.

    This is the arm that answers the question a membership test cannot ask. Is a
    hue plausible? — not on its own, only in the place it landed. A corpus sand
    tone is entirely legitimate on a beach and is the 2026-07-29 defect on open
    water, and `PALETTE_FOREIGN_MASS` returns the same verdict for both because
    it only ever asks whether the colour EXISTS in the art. The surface is the
    missing half of the question, and a tile is the cheapest honest stand-in for
    one: the world's own `tile_size`, so the window is an authored cell.

    The law is not a heuristic. Ambience is a LUT indexed by colour, weather is a
    blend, the killswitch is a wash — every one of them is a function of the
    pixel, so none can turn one tone into two. A veil is a function of POSITION,
    and that is exactly what shows up here.
    """
    out = []
    for lit, day in pairs:
        name = f"surface[{label(lit)}]"
        dsz = Image.open(day["file"]).size
        lsz = Image.open(lit["file"]).size
        if dsz != lsz:
            out.append(_unjudged(name, f"the twin is {dsz} and the frame is {lsz} — the tile "
                                       "grids do not line up, so no tile has a counterpart"))
            continue
        d = _tile_tones(Path(day["file"]))
        if not d:
            # Degenerate end FIRST: a frame narrower or shorter than one tile
            # yields no tiles at all, and a share over an empty set would be a
            # ZeroDivisionError at best and a silent 0.0 green at worst.
            out.append(_unjudged(name, f"the frame is {lsz}, smaller than one {SURFACE_TILE}px "
                                       "tile — there is no surface in it to judge"))
            continue
        l = _tile_tones(Path(lit["file"]))
        gained = [(k, d[k], l[k]) for k in d if l[k] > d[k]]
        share = len(gained) / len(d)
        worst = max(gained, key=lambda t: t[2] - t[1], default=None)
        detail = (f"{len(gained)}/{len(d)} tiles gained a tone ({share:.2%}"
                  + (f", worst +{worst[2] - worst[1]} at {worst[0]}" if worst else "")
                  + f"); {sum(1 for k in d if l[k] < d[k])} merged")
        if share > SURFACE_EXCESS:
            out.append(_red(name, detail + f" — a pass that ADDS a tone to a surface is a "
                                           f"decision per POSITION, not per colour "
                                           f"(limit {SURFACE_EXCESS:.0%})"))
        else:
            out.append(_ok(name, detail))
    return out


def _ladder_step(bucket: str) -> int:
    """The largest per-channel step INSIDE a single shipped ground ladder.

    DERIVED, and the whole reason this arm has no tuned bound. `terrainField`
    quantizes a smooth noise field onto one `RAMPS` ladder, so between two
    adjacent ground pixels the renderer can only ever move along that ladder —
    and the biggest move it can make is this number. Read from the artifact
    `ambience.ts` emits, so a re-lit world moves the bound with it.
    """
    return max(max(abs(tones[i + 1][k] - tones[i][k]) for k in range(3))
               for tones in ambience_py.ramps(bucket).values()
               for i in range(len(tones) - 1))


def _crossings(im: Image.Image, bound: int) -> Image.Image:
    """255 where a pixel's right or lower neighbour is further than `bound`.

    Whole-image ops rather than a pixel walk, and EXHAUSTIVE: a stride aliases
    against a periodic dither, which is the defect this arm exists for.
    """
    w, h = im.size

    def mask(a: Image.Image, b: Image.Image) -> Image.Image:
        d = ImageChops.difference(a, b).split()
        return ImageChops.lighter(ImageChops.lighter(d[0], d[1]), d[2]).point(
            lambda v: 255 if v > bound else 0)

    acc = Image.new("L", (w, h), 0)
    for m, box in ((mask(im.crop((0, 0, w - 1, h)), im.crop((1, 0, w, h))), (0, 0)),
                   (mask(im.crop((0, 0, w, h - 1)), im.crop((0, 1, w, h))), (0, 0))):
        lay = Image.new("L", (w, h), 0)
        lay.paste(m, box)
        acc = ImageChops.lighter(acc, lay)
    return acc


def _all_sea(im: Image.Image, bucket: str) -> Image.Image:
    """255 where the pixel is one of this bucket's sea tones.

    Five image differences rather than a million dictionary lookups. The sea is
    excluded from the soil arm's tile universe because open water is `water`'s
    subject and a tile of it holds no ground to judge.
    """
    w, h = im.size
    acc = Image.new("L", (w, h), 0)
    for c in ambience_py.sea(bucket):
        d = ImageChops.difference(im, Image.new("RGB", (w, h), c)).split()
        same = ImageChops.lighter(ImageChops.lighter(d[0], d[1]), d[2]).point(
            lambda v: 255 if v == 0 else 0)
        acc = ImageChops.lighter(acc, same)
    return acc


def arm_soil(frames: list) -> list:
    """THE CONTENT LAW, and the only arm here that needs no second frame.

    WHY IT EXISTS, measured 2026-07-30 and not deduced: `ambience`, `grain`,
    `surface` and `grade` all judge a frame against its DAY TWIN, and a twin
    carries a CONTENT defect exactly as the frame does. A corpus sand tone
    sprayed over LAND at 16.7% coverage — the 2026-07-29 defect moved from the
    screen-space filter down into the world — passed all of them, at every hour
    and every zoom, and `PALETTE_FOREIGN_MASS` returned no finding either
    because every injected pixel was a legitimate corpus tone. `water` caught
    the same defect on WATER and only because it is the one non-differential
    pixel arm in the file. This is its land counterpart.

    THE LAW. `terrainField` quantizes a smooth noise field onto ONE shipped
    `RAMPS` ladder, so between two adjacent ground pixels the renderer moves
    along that ladder and can move no further than the ladder's own largest
    step. A pass drawn per POSITION does not move along a ladder: it lands a
    tone from somewhere else next to every pixel it touches.

    IT NEEDS THE GROUND LAYER, which is why `groundOnly` exists on the shipped
    canvas. On the composite the law is false — props, figures and cards are
    art, and art has edges — and a check that judged the composite here would
    be measuring the dressing.

    WHAT IT CANNOT SEE, stated rather than discovered: at NIGHT the shipped
    grass ladder itself steps 40 per channel — (60,52,36) -> (52,60,76), the
    split-tone light and the native snap taking the mid-tones blue while the
    dark end stays brown — so the derived bound is wide enough that the same
    defect reads 0.0-0.2% and this arm has no purchase there. That is a fact
    about the world's own art measured on the artifact, not a tolerance, and it
    is not fixable by moving a number: it needs a per-ladder bound, which needs
    the ground CLASSIFIED per pixel, which needs the id buffer the engine does
    not emit. Recorded in README.frame.md as the arm's own hole.
    """
    out = []
    for f in frames:
        name = f"soil[{label(f)}]"
        g = f.get("ground")
        if f.get("killswitch"):
            # The wash repaints the ground on purpose, so its tones are
            # legitimately not the ladder's. Same shape of exclusion as `grade`
            # and `water`, said here rather than met as a flake.
            continue
        if not g:
            out.append(_unjudged(name, "the manifest carries no ground layer for this cell — "
                                       "the content law is stated over the sprites-free layer "
                                       "and the composite may not stand in for it"))
            continue
        if not Path(g).exists():
            out.append(_unjudged(name, f"the ground layer {Path(g).name} is not on disk"))
            continue
        im = Image.open(g).convert("RGB")
        w, h = im.size
        bound = _ladder_step(f["bucket"])
        cross = _crossings(im, bound)
        sea = _all_sea(im, f["bucket"])
        judged = dithered = 0
        worst = (0.0, None)
        full = SOIL_TILE * SOIL_TILE
        for ty in range(0, h - SOIL_TILE + 1, SOIL_TILE):
            for tx in range(0, w - SOIL_TILE + 1, SOIL_TILE):
                box = (tx, ty, tx + SOIL_TILE, ty + SOIL_TILE)
                if sea.crop(box).histogram()[255] == full:
                    continue                      # open water: `water`'s subject
                judged += 1
                rate = cross.crop(box).histogram()[255] / full
                if rate > SOIL_PAIR:
                    dithered += 1
                if rate > worst[0]:
                    worst = (rate, (tx, ty))
        if judged < SOIL_MIN_TILES:
            # The degenerate end FIRST. A share over three tiles is noise, and a
            # green computed on it is a green about nothing.
            out.append(_unjudged(name, f"only {judged} ground tiles in the frame (needs "
                                       f">= {SOIL_MIN_TILES}) — there is not enough ground "
                                       "here to judge"))
            continue
        share = dithered / judged
        detail = (f"{dithered}/{judged} ground tiles step past the ladder's own "
                  f"{bound}/channel on >{SOIL_PAIR:.0%} of their pairs ({share:.2%}"
                  + (f", worst {worst[0]:.0%} at {worst[1]}" if worst[1] else "") + ")")
        out.append(_red(name, detail + f" — the ground is taking steps its own ladder does "
                                       f"not take, which is a decision per POSITION "
                                       f"(limit {SOIL_EXCESS:.0%})")
                   if share > SOIL_EXCESS else _ok(name, detail))
    if not out:
        return [_unjudged("soil", "no frame in this sweep carries a ground layer — the "
                                  "content law is the only one here that does not compare "
                                  "a frame with a twin, and this run did not ask it")]
    return out


def island_box(path: Path, bucket: str = "day") -> tuple[int, int, int, int] | None:
    """The bounding box of everything that is not open sea.

    WHY THE GRADE ARM NEEDS THIS. check_light's bounds were fitted on frames
    `raster.py` draws, where the island fills the canvas. A browser frame is a
    CAMERA, and at z=0.5 the same island occupies a corner of a 1200x800 window
    with flat ocean around it. Measured on the shipped renderer: whole-frame
    contrast 13.1 and span 58 at z=0.5 against 19.8 / 145 at z=1.0 — the same
    world, judged as flat because most of the frame is sea. That is the check
    being asked a question outside its domain, not a defect, and widening its
    bounds to admit the wide shot would blind it to the flatten it exists for.
    Cropping to the island asks the original question of the original subject.

    Derived from the shipped sea ramp (via the renderer's own emitted ambience
    artifact), never from a hand-picked rectangle that stops being the island the
    moment the camera moves.
    """
    im = Image.open(path).convert("RGB")
    sea = set(ambience_py.sea(bucket))
    px = im.load()
    w, h = im.size
    x0, y0, x1, y1 = w, h, -1, -1
    # A 4px stride: the box only needs to be right to within a few pixels, and an
    # exact walk of a million pixels here costs more than every other arm.
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            if px[x, y] in sea:
                continue
            if x < x0: x0 = x
            if y < y0: y0 = y
            if x > x1: x1 = x
            if y > y1: y1 = y
    if x1 < 0:
        return None
    return max(0, x0 - 4), max(0, y0 - 4), min(w, x1 + 5), min(h, y1 + 5)


def arm_grade(frames: list, work: Path) -> list:
    """check_light's grade arm, verbatim, on every real DAY frame.

    KILLSWITCH FRAMES ARE EXCLUDED, and that is a coverage statement rather than
    a convenience: the red wash drains saturation to 0.24 BY DESIGN (measured
    0.416 -> 0.236), which is exactly the drained-of-colour failure the grade arm
    exists to catch. Judging the wash by the grade rule would either red every
    killswitch frame forever or force the rule wide enough to miss a real drain.
    The wash has its own arm; what it does NOT have is a grade of its own.
    """
    days = [f for f in frames if f["bucket"] == "day" and not f.get("killswitch")]
    if not days:
        return [_unjudged("grade", "the sweep carries no day frame, and the grade bounds "
                                   "were fitted on daylight")]
    out = []
    for f in days:
        n = f"grade[{label(f)}]"
        box = island_box(Path(f["file"]))
        if box is None:
            out.append(_unjudged(n, "the frame is open sea end to end — there is no island "
                                    "in it to judge the grade of"))
            continue
        crop = work / (Path(f["file"]).stem + ".island.png")
        Image.open(f["file"]).convert("RGB").crop(box).save(crop)
        # bp/state empty ON PURPOSE: with no lighthouse declared, check_light's
        # lamp arm reports UNJUDGED and does not claim the `lamp` surface, and
        # the grade arm runs regardless. The lamp needs a blueprint, and a
        # blueprint is what the browser path does not have.
        _name, ok, detail, _surfaces = world_checks.check_light(str(crop), {}, {})
        out.append((n, ok, f"island {box[2] - box[0]}x{box[3] - box[1]} of "
                            f"{Image.open(f['file']).size[0]}x{Image.open(f['file']).size[1]}; "
                            + detail))
    return out


def arm_water(frames: list) -> list:
    """live-frame-probe's veil laws, over every frame rather than one by hand."""
    out = []
    if not [f for f in frames if not f.get("killswitch")]:
        # Every frame carries the wash, so the probe has nothing to judge — and
        # an empty result list would have printed NO water arm at all, which
        # reads as "not applicable" instead of "not looked at".
        return [_unjudged("water", "every frame in the sweep carries the killswitch "
                                   "wash, which repaints the sea on purpose")]
    for f in frames:
        if f.get("killswitch"):
            # Same reason as the grade arm's exclusion: the wash repaints the sea
            # on purpose, so its tones are legitimately not the sea ramp and the
            # probe reports the frame unjudgeable. Said here rather than
            # discovered as a flake.
            continue
        rc = _probe.judge(f["file"])
        out.append((f"water[{label(f)}]", rc == 0, "open water lawful" if rc == 0
                    else "see the probe line above — unlawful or unjudgeable"))
    return out


def arm_killswitch(frames: list) -> list:
    """The red wash draws, and only the killswitch frame carries it."""
    ks = [f for f in frames if f.get("killswitch")]
    if not ks:
        return [_unjudged("killswitch", "the sweep carries no killswitch frame — the red "
                                        "wash is a screen-space pass outside all twelve "
                                        "invariants and this run looked at none of it")]
    out = []
    for f in ks:
        twin = next((g for g in frames
                     if not g.get("killswitch") and g["bucket"] == f["bucket"]
                     and g["zoom"] == f["zoom"] and g["weather"] == f["weather"]), None)
        name = f"killswitch[{label(f)}]"
        if twin is None:
            out.append(_unjudged(name, "no non-killswitch twin at the same bucket and zoom"))
            continue
        _, _, ks_sat, _ = _grade(_hist(Path(f["file"])))
        _, _, tw_sat, _ = _grade(_hist(Path(twin["file"])))
        drop = tw_sat - ks_sat
        detail = f"saturation {tw_sat:.3f} -> {ks_sat:.3f} (drop {drop:.3f})"
        out.append(_ok(name, detail) if drop >= KS_SAT_DROP
                   else _red(name, detail + f" — the wash is not drawing (needs >= {KS_SAT_DROP})"))
    return out


# ── the run ─────────────────────────────────────────────────────────────────
def pair_up(frames: list) -> tuple[list, list]:
    """Every lit ambience frame with its day twin, and the ones with none.

    The domain is deliberately weather=sun and killswitch off — both overlays
    draw ABOVE the ambience filter, so they are not remapped and the prediction
    drifts by their own mass (measured: +0.8 mean under rain, +3.9 under fog).
    Their coverage is `arm_killswitch` and the honest gap in the header.
    """
    pairs, orphans = [], []
    days = {(f["zoom"], f["weather"]): f for f in frames
            if f["bucket"] == "day" and not f.get("killswitch")}
    for f in frames:
        if f["bucket"] == "day" or f.get("killswitch") or f["weather"] != "sun":
            continue
        d = days.get((f["zoom"], f["weather"]))
        (pairs if d else orphans).append((f, d) if d else f)
    return pairs, orphans


def pair_up_surface(frames: list) -> tuple[list, list]:
    """Every lit frame with the day twin carrying its OWN weather and killswitch.

    A WIDER domain than `pair_up`, and deliberately so. `ambience` and `grain`
    have to hold the overlays out because both draw above the filter and drift
    the histogram by their own mass. The surface law does not care: an overlay is
    a per-colour pass too, so as long as the twin carries the same overlay the
    claim still holds — measured 0.4% for night-under-fog against a fogged day
    twin and 0.0% for the killswitch wash, against 13.2% when the twin is dropped
    to weather=sun, which is the number that says the twin must match.

    So this is the only pairing in the file under which the weather layer and the
    killswitch wash are judged COMPOSED WITH ambience rather than as a layer.
    """
    pairs, orphans = [], []
    days = {(f["zoom"], f["weather"], bool(f.get("killswitch"))): f
            for f in frames if f["bucket"] == "day"}
    for f in frames:
        if f["bucket"] == "day":
            continue
        d = days.get((f["zoom"], f["weather"], bool(f.get("killswitch"))))
        (pairs if d else orphans).append((f, d) if d else f)
    return pairs, orphans


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="a directory written by frame-harness/shoot.mjs")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)

    root = Path(a.dir)
    man_path = root / "frames.json"
    if not man_path.exists():
        print(f"frame-judge: no frames.json under {root} — a directory of PNGs with no "
              "manifest cannot say which hour or zoom any of them is", file=sys.stderr)
        return 2
    man = json.loads(man_path.read_text())
    frames = man.get("frames") or []
    if not frames:
        print("frame-judge: the manifest lists no frames", file=sys.stderr)
        return 2
    missing = [f["file"] for f in frames if not Path(f["file"]).exists()]
    if missing:
        print(f"frame-judge: {len(missing)} frames named in the manifest are not on disk: "
              f"{missing[:3]}", file=sys.stderr)
        return 2

    pairs, orphans = pair_up(frames)
    results = []
    results += arm_determinism(man, root)
    if not pairs:
        results.append(_unjudged(
            "ambience", "no lit frame in this sweep has a day twin at its own zoom — "
                        "the clock axis is exactly what the blueprint path cannot see, and "
                        "a sweep that captured only daylight has not looked at it"))
    else:
        results += arm_ambience(pairs)
        results += arm_grain(pairs)
    for f in orphans:
        results.append(_unjudged(f"ambience[{label(f)}]",
                                 "no day twin at this zoom and weather"))

    spairs, sorphans = pair_up_surface(frames)
    if not spairs:
        results.append(_unjudged(
            "surface", "no frame in this sweep has a day twin carrying its own weather and "
                       "killswitch state — the neighbour law is stated against that twin, and "
                       "a sweep that captured only daylight has not asked it"))
    else:
        results += arm_surface(spairs)
    for f in sorphans:
        results.append(_unjudged(f"surface[{label(f)}]",
                                 "no day twin at this zoom, weather and killswitch state"))

    results += arm_grade(frames, root)
    results += arm_water(frames)
    results += arm_killswitch(frames)
    results += arm_soil(frames)

    print()
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:26s} {detail}")
    buckets = sorted({f["bucket"] for f in frames})
    zooms = sorted({f["zoom"] for f in frames})
    print(f"\njudged {len(frames)} real composited frames · buckets {buckets} · zooms {zooms}")
    print("NOT CHECKED HERE — the blueprint path owns these: roads, stacking, art "
          "(opacity, cut-off, palette), state traceability, era, terrain, depth order, "
          "shadows. Four of them could now read the ground layer this run captured "
          "(check_terrain, and the pixel halves of check_on_road / check_paint_fidelity) "
          "and none is wired to it yet; check_depth_order and check_shadows still need "
          "the two id buffers, which the engine does not emit. See README.frame.md.")

    red = [r for r in results if not r[1]]
    if a.json:
        Path(a.json).write_text(json.dumps(
            {"dir": str(root), "frames": len(frames), "buckets": buckets, "zooms": zooms,
             "results": [{"arm": n, "ok": ok, "detail": d} for n, ok, d in results],
             "red": [n for n, ok, _ in results if not ok]}, indent=1))
    print(f"{'GREEN' if not red else 'RED'} · {len(results) - len(red)}/{len(results)} arms pass")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
