#!/usr/bin/env python3.12
"""The Python ambience twin IS the renderer's, or CI is red.

WHAT THIS REPLACED, and why the shape changed. Until 2026-07-30 both Python
consumers — world-growth-backtest.py, which paints Pillow timelapse strips, and
live-frame-probe.py, which judges live PNGs — carried a hand-copied per-bucket
veil HUE TABLE, and the contract between them and the renderer was a comment
saying "change one, change both". The predecessor of this file parsed the
TypeScript for those tables and pinned the copies equal, which was right as far as
it went: a prose contract is not a sensor.

THE AMBIENCE STRUCTURE LAW deleted the dither those tables described (ambience is
a colour REMAP now, not an overlay), so there is no hue table left to mirror. What
the Python side needs instead is a FUNCTION, and a function cannot be pinned by a
regex over the source that declares it. So the authority emits its own answers:
`cabinet/dashboard/src/lib/world/ambience-derived.json` is produced by
lib/world/ambience.ts and pinned to it by an arm in ambience.test.ts, and the arms
below check the Python port against that output rather than against a re-reading
of the TypeScript.

Three things are pinned, and the third is the one that matters:

  1. the artifact is real and covers every lit bucket (vacuity guard — an empty
     or truncated artifact would satisfy every arm below);
  2. its per-bucket split-tone ends and shaded ramps are what ambience_py serves;
  3. ambience_py.remap, which is the ONE piece of ported LOGIC on this side,
     reproduces the renderer's own answer for all fifty-two shipped ramp colours
     in all three buckets. That is 156 independent comparisons against the
     authority's output; a snap that used a different metric, a different bit
     depth or a different candidate set cannot survive it.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DERIVED = REPO / "cabinet" / "dashboard" / "src" / "lib" / "world" / "ambience-derived.json"
ISO_TERRAIN = REPO / "cabinet" / "dashboard" / "src" / "lib" / "world" / "iso-terrain.ts"
BUCKETS = ("dawn", "dusk", "night")


def _load():
    spec = importlib.util.spec_from_file_location(
        "ambience_py", HERE.parent / "ambience_py.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


amb = _load()


def _ts_ramp_names() -> set[str]:
    """The shipped ramp names, read out of the renderer's own RAMPS block."""
    src = ISO_TERRAIN.read_text()
    block = src[src.index("export const RAMPS = {"):]
    block = block[:block.index("} as const")]
    names = set(re.findall(r"^\s*([A-Za-z][A-Za-z0-9]*):\s*\[", block, re.M))
    assert names, "no ramp names parsed out of iso-terrain.ts — regrep this test"
    return names


def test_the_artifact_is_real_and_total():
    """Vacuity guard: an empty parse would make every arm below pass."""
    assert DERIVED.exists(), f"{DERIVED} missing — regenerate via ambience.test.ts"
    raw = json.loads(DERIVED.read_text())["buckets"]
    assert set(raw) == set(BUCKETS), sorted(raw)
    names = _ts_ramp_names()
    assert isinstance(json.loads(DERIVED.read_text())["curve"], (int, float))
    for b in BUCKETS:
        for end in ("shadow", "highlight"):
            assert len(raw[b][end]) == 3, raw[b][end]
            # a light may only REMOVE light — ambience.ts `solveStrength`
            assert all(0 < v <= 1 for v in raw[b][end]), (b, end, raw[b][end])
        assert 0 < raw[b]["depth"] <= 1, raw[b]["depth"]
        assert 0 < raw[b]["strength"] <= 1, raw[b]["strength"]
        assert len(raw[b]["sea"]) >= 5, raw[b]["sea"]
        # every ramp the renderer ships is covered — a shrunk artifact is caught
        assert set(raw[b]["ramps"]) == names, sorted(set(names) ^ set(raw[b]["ramps"]))
        for tones in raw[b]["ramps"].values():
            assert tones and all(len(c) == 3 for c in tones), tones


@pytest.mark.parametrize("bucket", BUCKETS)
def test_the_reader_serves_the_artifact_unchanged(bucket):
    raw = json.loads(DERIVED.read_text())["buckets"][bucket]
    assert amb.is_lit(bucket)
    # the split's two ends ARE the light, at the two ends of the art's tonal
    # range — read straight off the artifact, no re-derivation on this side
    assert list(amb.light(bucket, (0, 0, 0))) == pytest.approx(raw["shadow"], abs=1e-6)
    assert list(amb.light(bucket, (255, 255, 255))) == pytest.approx(
        raw["highlight"], abs=1e-6)
    assert amb.sea(bucket) == [tuple(c) for c in raw["sea"]]
    for name, tones in raw["ramps"].items():
        assert amb.ramp(bucket, name) == [tuple(c) for c in tones], name


def test_day_is_a_no_op_on_both_sides():
    """`day` carries no ambience at all, and the reader must say so rather than
    inventing one — an ambience applied under the wrong label is a worse defect
    than an ambience that is too strong."""
    assert not amb.is_lit("day")
    assert amb.light("day", (0x6F, 0xAE, 0xA6)) is None
    assert amb.remap((0x6F, 0xAE, 0xA6), "day") == (0x6F, 0xAE, 0xA6)
    assert amb.sea("day") == [
        (0x3E, 0x6E, 0x6B), (0x48, 0x80, 0x7C), (0x54, 0x91, 0x8C),
        (0x61, 0xA0, 0x99), (0x6F, 0xAE, 0xA6)]


@pytest.mark.parametrize("bucket", BUCKETS)
def test_the_ported_remap_reproduces_the_renderer(bucket):
    """THE ARM THAT MATTERS. 52 shipped ramp colours per bucket, each shaded by
    the Python port and compared with the renderer's own answer for the same
    colour. A different metric, bit depth or candidate set dies here."""
    raw = json.loads(DERIVED.read_text())["buckets"][bucket]
    checked = 0
    for name, tones in raw["ramps"].items():
        src = _ts_ramp(name)
        assert len(src) == len(tones), name
        for before, after in zip(src, tones):
            assert amb.remap(before, bucket) == tuple(after), (
                f"{bucket}/{name}: the Python port shaded "
                f"#{before[0]:02x}{before[1]:02x}{before[2]:02x} to "
                f"{amb.remap(before, bucket)}, the renderer to {tuple(after)}")
            checked += 1
    assert checked >= 50, checked


def _ts_ramp(name: str) -> list[tuple[int, int, int]]:
    """One shipped ramp, read out of the renderer's own source — the INPUTS to the
    comparison above have to come from the authority too, or the arm is only
    checking the artifact against itself."""
    m = re.search(rf"^\s*{name}:\s*\[([^\]]*)\]", ISO_TERRAIN.read_text(), re.M)
    assert m, f"{name} ramp not found in iso-terrain.ts — regrep this test"
    hexes = re.findall(r"0x([0-9a-fA-F]{6})", m.group(1))
    assert hexes, f"{name} ramp parsed empty — the regex, not the source, is wrong"
    return [(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) for h in hexes]


def test_bucket_ranges_match_the_renderer_defaults():
    """lighting.ts DEFAULT_BUCKETS, parsed rather than retyped. The renderer can
    have these overridden by the grammar; a Python preview cannot, so the least it
    must do is agree with the defaults."""
    src = (REPO / "cabinet" / "dashboard" / "src" / "lib" / "world" / "lighting.ts").read_text()
    block = src[src.index("export const DEFAULT_BUCKETS"):]
    block = block[:block.index("}")]
    want = {m[0]: (int(m[1]), int(m[2]))
            for m in re.findall(r"(\w+):\s*\[(\d+),\s*(\d+)\]", block)}
    assert set(want) == {"dawn", "day", "dusk", "night"}, want
    for name, (a, z) in want.items():
        if name == "night":
            continue                      # the wrap-around remainder
        assert amb.bucket_of(a) == name, (name, a)
        assert amb.bucket_of(z - 1) == name, (name, z - 1)
        assert amb.bucket_of(a - 1) != name, (name, a - 1)
    assert amb.bucket_of(None) == "day"
    assert amb.bucket_of(23) == "night"
    assert amb.bucket_of(2) == "night"
