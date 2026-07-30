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
    The overlays get their own arm instead, and the honest statement is that
    ambience-under-weather has a sensor for the OVERLAY and none for their
    COMPOSITION.
  * The nine layout invariants (roads, stacking, art, traceability, era, terrain,
    depth order, shadows) still run on the blueprint. Six of them need artifacts
    only the renderer can emit — the sprites-free ground layer and the two id
    buffers — and the engine has no capture door. See README.frame.md for the
    per-check table and what building that door costs.
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
# The twelve live in the mirror, which is what CI runs (sync-checks.py --check
# guards it against the private source). Importing check_light rather than
# re-deriving a grade rule is the point: this file adds a capture, not a second
# opinion about exposure.
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
    results += arm_grade(frames, root)
    results += arm_water(frames)
    results += arm_killswitch(frames)

    print()
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:26s} {detail}")
    buckets = sorted({f["bucket"] for f in frames})
    zooms = sorted({f["zoom"] for f in frames})
    print(f"\njudged {len(frames)} real composited frames · buckets {buckets} · zooms {zooms}")
    print("NOT CHECKED HERE — the blueprint path owns these, and six of them need a "
          "renderer capture door that does not exist: roads, stacking, art (opacity, "
          "cut-off, palette), state traceability, era, terrain, depth order, shadows. "
          "See README.frame.md.")

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
