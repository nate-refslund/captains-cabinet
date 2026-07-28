#!/usr/bin/env python3
"""The meadow shading has a FEATHER, and this is what measures it.

THE DEFECT (Captain, 2026-07-27): "the meadow patches read as HARD DARK ELLIPSES
rather than as subtle variation". They did. compose.py:149 draws its 70 patches
into one mask and then blurs the WHOLE mask — `patch.filter(GaussianBlur(26))` —
before pasting the dark grass through it, and this port had replaced that blur
with an irregular OUTLINE (a lobed rim instead of an oval one). A lobed edge is
still an edge: the frame went on reading as blobs, and no check could see it,
because all twelve invariants judge sprites, paint coverage and depth — none of
them ever asks how sharp a shading boundary is.

WHAT THE ARM ACTUALLY MEASURES, and why it is not a tautology on the constant:
it rebuilds the meadow mask from a REAL draw list the same way raster.py does,
once with the feather the draw list ships and once with it disabled, and reports
the largest one-pixel step in each. Disabled, the union of hard ellipses steps by
most of full scale in a single pixel — that IS the razor edge, in numbers. With
the shipped feather no step exceeds a handful of levels. If the feather were ever
dropped from the draw list, or set to 0, or applied per blob instead of to the
union, this goes red rather than quietly repainting hard ovals.

It renders NO sprites and needs no browser: the mask is the thing under test.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAPTURE = HERE.parent
REPO = CAPTURE.parents[2]
sys.path.insert(0, str(CAPTURE))

PIL = pytest.importorskip("PIL", reason="Pillow is required — a skipped world arm is a dead sensor")
from PIL import Image, ImageChops, ImageDraw, ImageFilter  # noqa: E402

import raster  # noqa: E402

PACK = REPO / "cabinet/dashboard/public/world-assets/originals/iso"
STATE = CAPTURE / "states/hamlet.json"


def _draw_list(tmp_path: Path) -> dict:
    """A real draw list, from the real composeLayout — never a fixture."""
    out = tmp_path / "emit"
    out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [
            "node",
            "--import",
            str(CAPTURE / "resolve-ts.mjs"),
            str(CAPTURE / "emit.ts"),
            "--pack",
            str(PACK / "world-pack.json"),
            "--state",
            str(STATE),
            "--out",
            str(out),
        ],
        cwd=str(CAPTURE),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"emit.ts failed: {r.stderr[-2000:]}"
    return json.loads((out / "draw.json").read_text())


def _max_step(mask: Image.Image, stride: int = 2) -> int:
    """The largest one-pixel change anywhere in the mask, 0..255."""
    px = mask.load()
    w, h = mask.size
    worst = 0
    for y in range(0, h, stride):
        for x in range(0, w - 1, stride):
            d = abs(px[x, y] - px[x + 1, y])
            if d > worst:
                worst = d
    return worst


def test_the_draw_list_ships_a_meadow_feather(tmp_path):
    """One authority for how soft the ground is — the same contract lane_squash has."""
    draw = _draw_list(tmp_path)
    feather = draw.get("paint_feather") or {}
    assert feather.get("meadow_dark", 0) > 0, (
        "the draw list carries no meadow feather; both renderers would invent their own"
    )


def test_the_feather_removes_the_razor_edge_and_its_absence_restores_it(tmp_path):
    """The arm and its own negative twin, in one run.

    Without the twin this would pass against a mask that was smooth for some
    entirely different reason — the degenerate end of "no hard steps" is an
    empty mask, which has none.
    """
    draw = _draw_list(tmp_path)
    W, H = draw["canvas"]
    regions = [r for r in draw["paint"] if r["kind"] == "meadow_dark"]
    assert regions and sum(len(r["blobs"]) for r in regions) > 50, "no meadow to measure"
    shipped = float((draw.get("paint_feather") or {}).get("meadow_dark", 0))

    def mask(feather: float) -> Image.Image:
        out = Image.new("L", (W, H), 0)
        for reg in regions:
            out = ImageChops.lighter(out, raster._blob_mask(W, H, reg["blobs"], feather=feather))
        return out

    hard = mask(0.0)
    soft = mask(shipped)
    hard_step = _max_step(hard)
    soft_step = _max_step(soft)
    # the mask still COVERS the same ground — a feather that erased the shading
    # would also have no hard steps, and would be a different defect
    assert hard.getextrema()[1] > 100 and soft.getextrema()[1] > 100
    assert hard_step >= 100, f"expected a razor edge without the feather, saw {hard_step}"
    assert soft_step <= 16, f"the meadow still steps {soft_step}/255 in one pixel"


def test_the_blur_is_applied_to_the_union_not_to_each_blob(tmp_path):
    """Blurring the pieces and unioning after leaves a crease where rims cross.

    Two overlapping patches at the same strength: feathered-then-unioned keeps a
    visible ridge in the overlap, union-then-feathered does not. This is the one
    ordering mistake that reproduces the original defect while still calling
    itself a feather.
    """
    W = H = 400
    blobs = [
        {"x": 160, "y": 200, "rx": 90, "ry": 56, "w": 0.6},
        {"x": 240, "y": 200, "rx": 90, "ry": 56, "w": 0.6},
    ]
    union_then_blur = raster._blob_mask(W, H, blobs, feather=26.0)

    def blur_then_union() -> Image.Image:
        out = Image.new("L", (W, H), 0)
        for b in blobs:
            one = raster._blob_mask(W, H, [b], feather=26.0)
            out = ImageChops.lighter(out, one)
        return out

    wrong = blur_then_union()
    # sample the seam between the two centres: the correct order is monotone
    # across it, the wrong one dips and recovers
    row = 200
    a, b = 160, 240
    right = union_then_blur.load()
    bad = wrong.load()
    right_dip = max(right[a, row], right[b, row]) - min(
        right[x, row] for x in range(a, b + 1)
    )
    bad_dip = max(bad[a, row], bad[b, row]) - min(bad[x, row] for x in range(a, b + 1))
    assert right_dip <= 2, f"union-then-blur should be flat across the seam, dipped {right_dip}"
    assert bad_dip > right_dip, "the wrong order was expected to crease and did not"


def test_raster_blurs_by_the_shipped_number_and_defaults_to_none():
    """raster.py READS the draw list; a literal of its own would be a second ground.

    Asserted as WIRING rather than as the absence of a string: the first version
    of this arm grepped for `GaussianBlur(26` and went red on the comment that
    cites compose.py, which is the guarded-token-in-a-doc trap. The two things
    that actually matter are that the blur radius comes from the parameter, and
    that a draw list WITHOUT the key falls back to a hard edge rather than to a
    default nobody declared.
    """
    src = (CAPTURE / "raster.py").read_text()
    assert 'draw.get("paint_feather")' in src, "raster.py no longer reads the shipped feather"
    assert "ImageFilter.GaussianBlur(feather)" in src, "raster.py blurs by something else"
    assert "def _blob_mask(W: int, H: int, blobs, solid_floor=0.0, feather=0.0)" in src, (
        "a non-zero default here would hide a missing draw-list key"
    )
    W = H = 200
    blobs = [{"x": 100, "y": 100, "rx": 60, "ry": 37, "w": 1.0}]
    assert _max_step(raster._blob_mask(W, H, blobs), stride=1) >= 100, (
        "the default is meant to be the HARD edge, so an older draw list renders unchanged"
    )


def test_the_ground_raster_actually_obeys_the_shipped_number(tmp_path):
    """THE CALL SITE, not the helper — the arm the first mutation round exposed.

    `raster-ignores-feather` (replace the meadow paste's
    `feather=float(feather.get("meadow_dark", 0))` with `feather=0.0`) came back
    GREEN against every arm above, because they all rebuild the mask by calling
    `_blob_mask` themselves. A check wired to the helper cannot see the caller
    drop its argument. This one draws the REAL ground layer twice — once with
    the draw list's paint_feather, once with the key removed — and requires the
    two to differ. If build_ground stops reading the shipped number the outputs
    become identical and this goes red.
    """
    draw = _draw_list(tmp_path)
    W, H = draw["canvas"]
    seed = 12345
    with_feather = raster.build_ground(json.loads(json.dumps(draw)), W, H, seed)
    stripped = json.loads(json.dumps(draw))
    stripped.pop("paint_feather", None)
    without = raster.build_ground(stripped, W, H, seed)
    diff = ImageChops.difference(with_feather.convert("RGB"), without.convert("RGB"))
    assert diff.getbbox() is not None, (
        "the shipped feather changed nothing in the rendered ground — the paste "
        "is not reading it"
    )


def test_the_engine_renderer_reads_the_same_constant():
    """The other renderer, held to the same one-authority rule.

    `PAINT_FEATHER` alone was not enough: the `canvas-drops-constant` mutation
    (swap the lookup for a literal 26) left the import in place and the arm
    green. The lookup itself is what is asserted.
    """
    src = (REPO / "cabinet/dashboard/src/components/world/engine-canvas.tsx").read_text()
    assert "PAINT_FEATHER.meadow_dark" in src, (
        "engine-canvas.tsx no longer reads the shared feather at the meadow pass"
    )
    paint = (REPO / "cabinet/dashboard/src/lib/world/iso-layout/paint.ts").read_text()
    assert "export const PAINT_FEATHER" in paint, "the paint stage no longer owns the feather"


def test_the_shipped_feather_matches_the_paint_stage(tmp_path):
    """The bridge may not re-type what the paint stage decided."""
    draw = _draw_list(tmp_path)
    shipped = float((draw.get("paint_feather") or {}).get("meadow_dark", 0))
    src = (REPO / "cabinet/dashboard/src/lib/world/iso-layout/paint.ts").read_text()
    block = src.split("export const PAINT_FEATHER", 1)[1].split("}", 1)[0]
    declared = float(block.split("meadow_dark:", 1)[1].split(",", 1)[0].strip())
    assert shipped == declared, f"draw list ships {shipped}, paint.ts declares {declared}"
