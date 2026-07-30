#!/usr/bin/env python3.12
"""ambience_py.py — the renderer's day/night ambience, for the Python consumers.

THIS FILE OWNS NO COLOURS. Every value it returns comes from
`cabinet/dashboard/src/lib/world/ambience-derived.json`, which is emitted by the
renderer's own `lib/world/ambience.ts` and pinned to it by an arm in
ambience.test.ts. Two Python tools need to know what an hour looks like and
neither can run TypeScript:

  * live-frame-probe.py, which judges PNGs captured off the live /world
  * world-growth-backtest.py, which paints Pillow timelapse strips

Until 2026-07-30 both carried a hand-copied per-bucket veil hue table and the
contract between them was a comment saying "change one, change both" — a third
copy of a hue table, in the repo whose entire finding had been that a hue table
nothing can reach will drift. THE AMBIENCE STRUCTURE LAW (ambience.ts) replaced
the dither those tables described with a colour remap, and this module replaced
the copies with one read of one artifact.

The one piece of LOGIC here is the nearest-native snap, because a Python consumer
that wants to shade an arbitrary pixel needs it and a table of 32768 entries is
not worth committing. It is not trusted on faith: tests/test_ambience_mirror.py
runs it over all fifty-two shipped ramp colours and pins the results against the
`ramps` table the TypeScript emitted, so the port is verified against the
authority's own output rather than against a re-reading of the authority's code.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DERIVED = REPO / "cabinet" / "dashboard" / "src" / "lib" / "world" / "ambience-derived.json"
PALETTE = REPO / "cabinet" / "scripts" / "world-aesthetic" / "calibration" / "palette.json"

BUCKETS = ("dawn", "day", "dusk", "night")
LIT = ("dawn", "dusk", "night")

# Rec.709-weighted RGB distance, x3 — ambience.ts's `ambienceLut` metric, so
# LUMINANCE error dominates the snap. Verified by test_ambience_mirror.
_W = (0.6378, 2.1456, 0.2166)


@lru_cache(maxsize=1)
def derived() -> dict:
    """The renderer's emitted ambience artifact."""
    return json.loads(DERIVED.read_text())["buckets"]


def light(bucket: str) -> tuple[float, float, float] | None:
    """Per-channel light factor, or None for a bucket that changes nothing."""
    if bucket not in BUCKETS:
        raise ValueError(f"unknown bucket {bucket!r}")
    row = derived().get(bucket)
    return None if row is None else tuple(row["light"])


def sea(bucket: str) -> list[tuple[int, int, int]]:
    """The shipped sea ramp as it appears in this bucket — the tones open water
    is ALLOWED to be. `day` returns the raw ramp (ambience is a no-op there)."""
    row = derived().get(bucket)
    if row is None:
        return [tuple(c) for c in _DAY_SEA]
    return [tuple(c) for c in row["sea"]]


def ramp(bucket: str, name: str) -> list[tuple[int, int, int]]:
    """One shipped RAMPS ladder as it appears in this bucket."""
    row = derived().get(bucket)
    if row is None:
        raise ValueError(f"{bucket} has no ambience — the ramp is unchanged")
    return [tuple(c) for c in row["ramps"][name]]


# iso-terrain.ts RAMPS.sea, dark -> light. The ONE place these five tones are
# duplicated outside the renderer; test_live_frame_probe.py pins them equal.
_DAY_SEA = [(0x3E, 0x6E, 0x6B), (0x48, 0x80, 0x7C), (0x54, 0x91, 0x8C),
            (0x61, 0xA0, 0x99), (0x6F, 0xAE, 0xA6)]


@lru_cache(maxsize=1)
def _quant_bits() -> int:
    return json.loads(PALETTE.read_text())["quant_bits"]


@lru_cache(maxsize=1)
def _native() -> list[tuple[int, int, int]]:
    """Every colour the palette gate calls NATIVE: a fitted corpus bin, or one
    within its `neighbor_radius`. Same set ambience.ts snaps into."""
    pal = json.loads(PALETTE.read_text())
    bits = pal["quant_bits"]
    radius = pal["neighbor_radius"]
    levels = 1 << bits
    centre = 1 << (8 - bits - 1)
    seen: set[int] = set()
    for key in pal["bins"]:
        r0, g0, b0 = (key >> (2 * bits)) & (levels - 1), (key >> bits) & (levels - 1), key & (levels - 1)
        for dr in range(-radius, radius + 1):
            for dg in range(-radius, radius + 1):
                for db in range(-radius, radius + 1):
                    r, g, b = r0 + dr, g0 + dg, b0 + db
                    if 0 <= r < levels and 0 <= g < levels and 0 <= b < levels:
                        seen.add((r << (2 * bits)) | (g << bits) | b)
    return [((((k >> (2 * bits)) & (levels - 1)) << (8 - bits)) | centre,
             ((((k >> bits) & (levels - 1)) << (8 - bits)) | centre),
             (((k & (levels - 1)) << (8 - bits)) | centre)) for k in sorted(seen)]


def remap(rgb: tuple[int, int, int], bucket: str) -> tuple[int, int, int]:
    """One pixel under a bucket's light, snapped to the nearest native colour.

    The source is quantized to the palette's own bit depth FIRST, exactly as the
    GPU's LUT lookup does, so a Python-shaded frame and a browser-shaded frame
    agree pixel for pixel rather than nearly.
    """
    fac = light(bucket)
    if fac is None:
        return rgb
    bits = _quant_bits()
    centre = 1 << (8 - bits - 1)
    src = tuple((((c >> (8 - bits)) << (8 - bits)) | centre) for c in rgb)
    tgt = tuple(min(255.0, src[i] * fac[i]) for i in range(3))
    best, best_d = _native()[0], float("inf")
    for cand in _native():
        d = sum(_W[i] * (tgt[i] - cand[i]) ** 2 for i in range(3))
        if d < best_d:
            best_d, best = d, cand
    return best


def bucket_of(hour: int | None) -> str:
    """lighting.ts DEFAULT_BUCKETS. The grammar can override these ranges for the
    renderer (`night.buckets`); a Python preview has no grammar, so it uses the
    defaults and says so rather than pretending to be configurable."""
    if hour is None:
        return "day"
    h = int(hour) % 24
    if 6 <= h < 8:
        return "dawn"
    if 8 <= h < 18:
        return "day"
    if 18 <= h < 21:
        return "dusk"
    return "night"
