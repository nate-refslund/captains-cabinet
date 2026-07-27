#!/usr/bin/env python3
"""raster.py — draw a composeLayout frame, and emit the four artifacts the
twelve invariants in checks/world_checks.py need.

    python3.12 raster.py --draw draw.json --blueprint blueprint.json \
        --pack world-pack.json --atlas <dir> --assets <dir> \
        --out /tmp/frame.png [--scale 1.0]

Writes, beside --out:
    frame.png            the finished frame
    frame.ground.png     the SPRITES-FREE ground layer, written before any
                         sprite and before the grade (check_terrain refuses to
                         fall back to the composite, and check_paint_fidelity
                         fits this frame's own grade from it)
    frame.ids.png        every painted layer as a unique flat colour, in paint
                         order
    frame.idsrev.png     the same buffer painted in REVERSE order
    frame.blueprint.json the emitted blueprint with `layers` filled in

WHY THE ID BUFFERS ARE TWO. Draw order cannot be recovered from a finished
frame; it can be recovered from a pair. Forward gives the LAST layer that
painted a pixel, reverse gives the FIRST — where they disagree, at least two
opaque layers genuinely contested it, which rect overlap can never tell you
because most of a tree's rect is air.

THIS FILE IS NOT A CHECK AND MUST NEVER BE IMPORTED BY ONE. It is the thing
under test. The separation is the whole reason the checks are trustworthy: the
on-road audit once called the same footprint helper the placement rule called,
so the rule and its own check were wrong in exactly the same way and the world
was reported clean three times while props stood in the road.

DEPTH IS THE SPRITE'S BASE Y — the same key the engine's sortableChildren
container sorts on and the same key compose.py sorts `placed` on. A shadow sorts
two px in front of its own sprite's base so it lands under the neighbour behind,
never over its owner.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

import ground

HERE = Path(__file__).resolve().parent
# quay.py is a BYTE-IDENTICAL mirror of the offline compositor's own wharf
# drawing (see mirror/ and sync-checks.py). Imported rather than re-derived: the
# wharf the live layout draws must be the wharf the approved stills draw, and a
# second implementation of a deck is a second thing to get wrong.
sys.path.insert(0, str(HERE / "mirror" / "designs" / "world-mockup-v2"))
import quay  # noqa: E402


# ---------------------------------------------------------------- scaling
def scale_frame(bp: dict, draw: dict, s: float) -> None:
    """Scale every coordinate in BOTH halves, in place.

    ONE pass over both, up front, so nothing downstream carries two notions of
    a pixel. The blueprint that is WRITTEN OUT is the scaled one: the checks
    measure the emitted image against the emitted blueprint, so a blueprint in
    layout px beside a render in output px would be judging a different world.
    """
    if s == 1.0:
        return
    r = lambda v: int(round(v * s))  # noqa: E731

    bp["canvas"] = [r(bp["canvas"][0]), r(bp["canvas"][1])]
    bp["island_centre"] = [r(v) for v in bp["island_centre"]]
    for key in ("cove", "plaza", "quay"):
        if bp.get(key):
            bp[key] = [r(v) for v in bp[key]]
    bp["fields"] = [[r(v) for v in f] for f in bp.get("fields") or []]
    bp["lanes"] = {k: [[r(a), r(b)] for a, b in v] for k, v in (bp.get("lanes") or {}).items()}
    bp["driveways"] = [[[r(p[0]), r(p[1])] for p in d] for d in bp.get("driveways") or []]
    bp["districts"] = [[r(a), r(b), r(rr)] for a, b, rr in bp.get("districts") or []]
    for group in (bp.get("lots") or {}).values():
        for lot in group:
            lot["c"] = [r(v) for v in lot["c"]]
            lot["road"] = [r(v) for v in lot["road"]]
    for sp in bp["sprites"]:
        sp["x"], sp["y"] = r(sp["x"]), r(sp["y"])
        sp["w"], sp["h"] = max(1, r(sp["w"])), max(1, r(sp["h"]))

    draw["canvas"] = bp["canvas"]
    draw["island_centre"] = bp["island_centre"]
    draw["coast"]["step"] = draw["coast"]["step"] * s
    for reg in draw["paint"]:
        for b in reg["blobs"]:
            b["x"], b["y"] = b["x"] * s, b["y"] * s
            b["rx"], b["ry"] = b["rx"] * s, b["ry"] * s
    for lane in draw["lanes"]:
        lane["width"] = max(1, lane["width"] * s)
        lane["runs"] = [[[p[0] * s, p[1] * s] for p in run] for run in lane["runs"]]
    if draw.get("wharf"):
        draw["wharf"]["shore"] = [[p[0] * s, p[1] * s] for p in draw["wharf"]["shore"]]
        draw["wharf"]["depth"] = max(2, draw["wharf"]["depth"] * s)
    if draw.get("jetty"):
        j = draw["jetty"]
        j["at"] = [j["at"][0] * s, j["at"][1] * s]
        j["end"] = [j["end"][0] * s, j["end"][1] * s]
        j["width"] = max(4, j["width"] * s)
    if draw.get("lamp_at"):
        draw["lamp_at"] = [r(v) for v in draw["lamp_at"]]
    draw["smokes"] = [[v[0] * s, v[1] * s, v[2], v[3] * s] for v in draw.get("smokes") or []]
    for sp, bsp in zip(draw["sprites"], bp["sprites"]):
        sp["x"], sp["y"], sp["w"], sp["h"] = bsp["x"], bsp["y"], bsp["w"], bsp["h"]


# ------------------------------------------------------- deliberate breakage
# EVERY ARM MUST BE PROVEN TO FAIL, or it is decoration. These are the
# mutations: each one disables exactly one rule the world relies on, and
# tests/ asserts the named check goes RED for it. A check that has never been
# seen to fail is an assumption with a green light on it.
#
# They live here rather than in the test because the mutation has to happen
# INSIDE the render — a check cannot be fooled by a doctored JSON alone, which
# is the point: the pixels have to really carry the defect.
def _mutate(name: str, bp: dict, draw: dict) -> str:
    W, H = bp["canvas"]
    if name == "orphan-sprite":
        # A banner nobody measured: not entitled by any rung, count or era, and
        # not on the ambient list. check_state_traceable must name it.
        #
        # IT USED TO BE A BENCH, and the day the dressing stage landed a bench
        # at hamlet became a REAL entitlement (village life, era >= hamlet) — so
        # this arm would have gone quietly green while still claiming to prove
        # that orphans are caught. A mutation whose defect stops being a defect
        # is a disabled sensor that still prints a pass. `posture_banner` is a
        # frame the pack ships and NOTHING in blueprint.ts justifies at any era.
        at = bp.get("plaza") or [W // 2, H // 2, 10, 10]
        s = {"n": "posture_banner", "x": at[0], "y": at[1], "w": 60, "h": 60,
             "flip": False, "shadow": True}
        draw["sprites"].append(s)
        bp["sprites"].append({k: s[k] for k in ("n", "x", "y", "w", "h")})
        return "state_traceable"
    if name == "camp-bench":
        # THE ERA GATE ON VILLAGE LIFE, from the other side. iso-layout/dressing
        # draws benches, lamps, stalls and fowl only at hamlet and above
        # (compose.py:523 "a camp is a camp"), and blueprint.ts justifies that
        # whole class only at hamlet and above. A gate nobody has tried to
        # defeat is an assumption: this stands a bench on a CAMP frame, where
        # the class is empty, and check_state_traceable must name it. Run
        # against the camp fixture — on hamlet a bench is entitled and this
        # mutation is correctly not a defect at all.
        #
        # IT STANDS WHERE A TREE ALREADY STANDS (the frontmost nature sprite,
        # offset clear of it), not at the canvas centre. The centre of this
        # canvas is the main carriageway, so a bench dropped there fires
        # `on_road` as well — and a mutation that trips a SECOND arm cannot show
        # that the arm it names is the one doing the work. Nature is on land, off
        # every lane and off the plough by construction, and the frontmost one is
        # painted last so the bench also leaves a mark (no false paint_fidelity).
        host = max(draw["sprites"], key=lambda q: q["y"])
        s = {"n": "bench", "x": int(host["x"]) + 30, "y": int(host["y"]) + 24,
             "w": 38, "h": 32, "flip": False, "shadow": True}
        draw["sprites"].append(s)
        bp["sprites"].append({k: s[k] for k in ("n", "x", "y", "w", "h")})
        return "state_traceable"
    if name == "sprite-on-lane":
        # Stand the biggest structure in the middle of the widest lane.
        lane = max(draw["lanes"], key=lambda ln: ln["width"])
        run = max(lane["runs"], key=len)
        p = run[len(run) // 2]
        i = max(range(len(draw["sprites"])), key=lambda k: draw["sprites"][k]["w"])
        for arr in (draw["sprites"], bp["sprites"]):
            arr[i]["x"], arr[i]["y"] = int(p[0]), int(p[1])
        return "on_road"
    if name == "no-shadows":
        for s in draw["sprites"]:
            s["shadow"] = False
        return "shadows"
    if name == "reverse-depth":
        return "depth_order"          # handled in build_layers, needs the sort
    if name == "unpaved-square":
        # The square is DECLARED in the blueprint and never painted — which also
        # silently widens check_on_road's exemption over ground nobody paved.
        draw["paint"] = [r for r in draw["paint"] if r["kind"] != "plaza"]
        return "terrain"
    if name == "ghost-sprite":
        # Declared in the blueprint, never composited: the "left no mark" defect.
        big = max(range(len(draw["sprites"])), key=lambda k: draw["sprites"][k]["w"])
        draw["sprites"][big]["skip_paint"] = True
        return "paint_fidelity"
    raise SystemExit(f"raster.py: unknown --mutate {name!r}")


MUTATIONS = ["orphan-sprite", "sprite-on-lane", "no-shadows", "reverse-depth",
             "unpaved-square", "ghost-sprite", "camp-bench"]


# ---------------------------------------------------------------- the atlas
class Pack:
    """The shipped pack, and the frames cut out of its atlas.

    Every sprite is cut ONCE at its native size and cached; the drawn size is
    applied at paste time with NEAREST so the pixel grid survives, which is the
    same rule the pack's own note states and the engine's setSize() follows.
    """

    def __init__(self, pack_path: str, atlas_dir: str):
        self.data = json.loads(Path(pack_path).read_text())
        self.frames = self.data["frames"]
        self.atlas_dir = atlas_dir
        self._atlases: dict[int, Image.Image] = {}
        self._cut: dict[str, Image.Image] = {}

    def _atlas(self, k: int) -> Image.Image:
        if k not in self._atlases:
            name = self.data["atlases"][k]
            self._atlases[k] = Image.open(os.path.join(self.atlas_dir, name)).convert("RGBA")
        return self._atlases[k]

    def cut(self, name: str) -> Image.Image | None:
        """The sprite at NATIVE size, or None when the pack has no such frame."""
        if name in self._cut:
            return self._cut[name]
        f = self.frames.get(name)
        if f is None:
            return None
        im = self._atlas(f["atlas"]).crop((f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"]))
        # A hard alpha floor, as compose.py does: PixelLab cut-outs leave a
        # halo of alpha 1..11 that reads as a grey fringe once graded.
        im.putalpha(im.getchannel("A").point(lambda v: 0 if v < 12 else v))
        self._cut[name] = im
        return im


def write_assets(pack: Pack, names, assets_dir: str) -> list[str]:
    """Cut every USED frame to its own PNG — the `--assets DIR` three checks read.

    Only the frames this capture drew: check_sprite_opacity, check_sprite_cutoff
    and check_palette sweep the whole directory, and filling it with 163 frames
    the frame never used would report art defects in art nobody looked at.
    """
    os.makedirs(assets_dir, exist_ok=True)
    written = []
    for n in sorted(set(names)):
        im = pack.cut(n)
        if im is None:
            continue
        im.save(os.path.join(assets_dir, n + ".png"))
        written.append(n)
    return written


# ---------------------------------------------------------------- the ground
def _mask_from_coast(coast: dict, W: int, H: int) -> tuple[Image.Image, Image.Image]:
    """The land and beach masks, upsampled from the coastline the LAYOUT built.

    SHIPPED, NEVER RE-DERIVED. Rebuilding the island here from the same formula
    would be a second definition of where the land is, and the placement rules
    already ran against the first one.
    """
    raw = base64.b64decode(coast["mask"])
    mw, mh, step = coast["mw"], coast["mh"], coast["step"]
    land = Image.frombytes("L", (mw, mh), bytes(255 if b & 1 else 0 for b in raw))
    beach = Image.frombytes("L", (mw, mh), bytes(255 if b & 2 else 0 for b in raw))
    tw, th = max(1, int(round(mw * step))), max(1, int(round(mh * step)))
    out = []
    for m in (land, beach):
        m = m.resize((tw, th), Image.NEAREST)
        if (tw, th) != (W, H):
            c = Image.new("L", (W, H), 0)
            c.paste(m, (0, 0))
            m = c
        out.append(m)
    return out[0], out[1]


def _blob_mask(W: int, H: int, blobs, solid_floor=0.0) -> Image.Image:
    """A region's blobs unioned into one soft mask.

    `w` on a blob is the reference's per-blob fill VALUE, not an alpha ramp, so
    blobs are drawn at their own strength and the brightest wins — a max, not a
    sum, which is what keeps overlapping meadow patches from stacking to white.
    """
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    for b in blobs:
        v = int(round(255 * max(solid_floor, b.get("w", 1.0))))
        cur = Image.new("L", (W, H), 0)
        ImageDraw.Draw(cur).ellipse(
            [b["x"] - b["rx"], b["y"] - b["ry"], b["x"] + b["rx"], b["y"] + b["ry"]], fill=v
        )
        m = ImageChops.lighter(m, cur)
    del d
    return m


def _lane_mask(W: int, H: int, lanes, squash: float) -> Image.Image:
    """Every carriageway and drive as ONE surface — THE SURFACE THE RULES RESERVED.

    Painted as the union of the same squashed discs buildLaneField is built from
    (half-width w/2 across, w/2*squash down), resampled at the same spacing, and
    never as a round stroke. A circle on the ground projects flattened on a 2:1
    screen, so a round stroke is 39% too tall: the first frame ever rendered from
    this layout put the harbourmaster's hut on a lane, because the placement
    rules had cleared it against the ellipse while the renderer painted the
    circle. check_on_road caught it on first contact — the painted road and the
    reserved road must be one surface or that class returns forever.

    ONE mask rather than one per lane, because that is what they are: the layout
    hands the clearance rules a single occupancy field, and painting them
    separately would let two overlapping widths double-darken a junction.
    """
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    for lane in lanes:
        half = max(0.5, lane["width"] / 2.0)
        ry = half * squash
        spacing = max(2.0, min(half, 16.0))
        for run in lane["runs"]:
            for i, a in enumerate(run):
                pts = [a]
                b = run[i + 1] if i + 1 < len(run) else None
                if b is not None:
                    n = int(math.hypot(b[0] - a[0], b[1] - a[1]) / spacing)
                    pts += [(a[0] + (b[0] - a[0]) * s / n, a[1] + (b[1] - a[1]) * s / n)
                            for s in range(1, n)]
                for p in pts:
                    d.ellipse([p[0] - half, p[1] - ry, p[0] + half, p[1] + ry], fill=255)
    return m


def build_ground(draw: dict, W: int, H: int, seed: int) -> Image.Image:
    """The sprites-free ground layer, back to front."""
    canvas = ground.sea(W, H, seed=seed + 7)
    land, beach = _mask_from_coast(draw["coast"], W, H)

    canvas.paste(ground.sand(W, H, seed=seed + 6), (0, 0), beach)
    canvas.paste(ground.grass(W, H, seed=seed + 3), (0, 0), land)

    by_kind: dict[str, list[dict]] = {}
    for reg in draw["paint"]:
        by_kind.setdefault(reg["kind"], []).append(reg)

    # shading first — it is what the ground LOOKS like, under everything built
    for reg in by_kind.get("meadow_dark", []):
        m = ImageChops.multiply(_blob_mask(W, H, reg["blobs"]), land)
        canvas.paste(ground.grass_dark(W, H, seed=seed + 8), (0, 0), m)
    for reg in by_kind.get("mottle", []):
        tone = ground.MOTTLE_TONES[(reg.get("tone") or 0) % len(ground.MOTTLE_TONES)]
        m = ImageChops.multiply(_blob_mask(W, H, reg["blobs"]), land)
        m = m.point(lambda v, a=tone[3]: v * a // 255)
        canvas.paste(Image.new("RGB", (W, H), tone[:3]), (0, 0), m)

    # the pond's sand ring, then the water itself over it
    for reg in by_kind.get("pond_bank", []):
        canvas.paste(ground.sand(W, H, seed=seed + 61), (0, 0),
                     ImageChops.multiply(_blob_mask(W, H, reg["blobs"], 1.0), land))
    water = None
    for kind in ("pond", "stream"):
        for reg in by_kind.get(kind, []):
            if water is None:
                water = ground.sea(W, H, seed=seed + 71)
            canvas.paste(water, (0, 0),
                         ImageChops.multiply(_blob_mask(W, H, reg["blobs"], 1.0), land))

    # lanes: dirt, clipped to land so a wobble can never paint a road on the sea
    lanes = ImageChops.multiply(
        _lane_mask(W, H, draw["lanes"], float(draw["lane_squash"])), land)
    canvas.paste(ground.dirt(W, H, seed=seed + 5), (0, 0), lanes)

    # the square, painted only over its own extent (flagstone is per-pixel)
    for reg in by_kind.get("plaza", []):
        m = ImageChops.multiply(_blob_mask(W, H, reg["blobs"], 1.0), land)
        bb = m.getbbox()
        if not bb:
            continue
        tile = ground.cobble(bb[2] - bb[0], bb[3] - bb[1], seed=seed + 9)
        full = Image.new("RGB", (W, H))
        full.paste(tile, (bb[0], bb[1]))
        canvas.paste(full, (0, 0), m)

    # the tilled plots, each drawn over its own bounding box
    for kind, tex in (("ploughed", ground.ploughed), ("crop", ground.crop_field)):
        for i, reg in enumerate(by_kind.get(kind, [])):
            m = ImageChops.multiply(_blob_mask(W, H, reg["blobs"], 1.0), land)
            bb = m.getbbox()
            if not bb:
                continue
            tile = tex(bb[2] - bb[0], bb[3] - bb[1], seed=seed + 11 + i)
            full = Image.new("RGB", (W, H))
            full.paste(tile, (bb[0], bb[1]))
            canvas.paste(full, (0, 0), m)

    # the wharf and the finger pier — drawn, not stamped (see quay.py)
    wharf = draw.get("wharf")
    if wharf and len(wharf["shore"]) > 1:
        pts = [(p[0], p[1]) for p in wharf["shore"]]
        quay.deck_strip(canvas, pts, int(round(wharf["depth"])), seed=seed + 3)
        quay.posts(canvas, pts, int(round(wharf["depth"])), seed=seed + 5)
    j = draw.get("jetty")
    if j:
        length = int(round(math.hypot(j["end"][0] - j["at"][0], j["end"][1] - j["at"][1])))
        if length > 2:
            ang = math.atan2(j["end"][0] - j["at"][0], max(1e-6, j["end"][1] - j["at"][1]))
            quay.jetty(canvas, j["at"][0], j["at"][1], length,
                       width=int(round(j["width"])), angle=ang, seed=seed + 11)
    return canvas


# ---------------------------------------------------------------- the sprites
def _shadow(im: Image.Image) -> tuple[Image.Image, int, int]:
    """compose.py's object-shaped soft shadow, verbatim in behaviour.

    The blur MUST happen on a PADDED canvas: blurring inside a layer the exact
    size of the sprite clamps at the edge and leaves a squarely cut-off shadow.
    Its peak alpha is 86, which is under the id buffer's 128 threshold on
    purpose — a shadow is not a layer that can win a contested pixel, and
    check_shadows needs the ground under it to still read as bare.
    """
    a = im.getchannel("A")
    sh = max(6, int(im.height * 0.24))
    blur = max(6, im.width // 6)
    pad = blur * 2
    sil = a.resize((im.width, sh), Image.LANCZOS)
    big = Image.new("L", (im.width + pad * 2, sh + pad * 2), 0)
    big.paste(sil, (pad, pad))
    big = big.filter(ImageFilter.GaussianBlur(blur))
    bw, bh = big.size
    fall = Image.new("L", (bw, bh), 0)
    fd = ImageDraw.Draw(fall)
    steps = 14
    for i in range(steps):
        f = 1 - i / steps
        rx = bw * 0.5 * (0.42 + 0.58 * f)
        ry = bh * 0.5 * (0.42 + 0.58 * f)
        fd.ellipse([bw / 2 - rx, bh / 2 - ry, bw / 2 + rx, bh / 2 + ry], fill=int(255 * (1 - f * 0.85)))
    fall = fall.filter(ImageFilter.GaussianBlur(blur * 0.7))
    big = ImageChops.multiply(big, fall).point(lambda v: int(v * 0.34))
    sl = Image.new("RGBA", (bw, bh), (26, 24, 36, 0))
    sl.putalpha(big)
    return sl, sh, pad


def _depth_grade(im: Image.Image, ty: float) -> Image.Image:
    """compose.py grade(): far sprites recede cool and pale, near ones stay warm."""
    if ty < 0.38:
        k = (0.38 - ty) / 0.38
        im = ImageEnhance.Color(im).enhance(1 - 0.22 * k)
        im = ImageEnhance.Brightness(im).enhance(1 + 0.07 * k)
    elif ty > 0.72:
        k = (ty - 0.72) / 0.28
        im = ImageEnhance.Color(im).enhance(1 + 0.05 * k)
        im = ImageEnhance.Brightness(im).enhance(1 - 0.05 * k)
    return im


def build_layers(pack: Pack, sprites, H: int, reverse_depth: bool = False) -> tuple[list, list[str]]:
    """Every layer to paint, sorted by base y — the renderer's own depth key.

    A sprite whose frame the pack does not carry is REPORTED, never silently
    dropped: a missing asset that draws nothing is exactly the "declared sprite
    that left no mark" defect check_paint_fidelity hunts, and swallowing it here
    would hide it from the arm built to catch it.
    """
    placed = []
    missing = []
    for sp in sprites:
        if sp.get("skip_paint"):
            continue                  # --mutate ghost-sprite: declared, never drawn
        native = pack.cut(sp["n"])
        if native is None:
            missing.append(sp["n"])
            continue
        im = native.resize((max(1, sp["w"]), max(1, sp["h"])), Image.NEAREST)
        if sp.get("flip"):
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        im = _depth_grade(im, sp["y"] / max(1, H))
        by = sp["y"]
        if sp.get("shadow", True):
            sl, sh, pad = _shadow(im)
            placed.append((by - 2, sl, int(sp["x"] - sl.width / 2 + im.width * 0.04),
                           int(by - sh * 0.55 - pad), sp["n"] + ":shadow"))
        placed.append((by, im, int(sp["x"] - im.width / 2), int(by - im.height), sp["n"]))
    # DEPTH IS THE BASE Y. Reversing it paints far sprites last, which is the
    # defect check_depth_order exists for (--mutate reverse-depth).
    placed.sort(key=lambda t: t[0], reverse=reverse_depth)
    return placed, missing


def paint_ids(placed, W: int, H: int, reverse: bool) -> tuple[Image.Image, list]:
    """The id buffer: same layers, same order, same alpha, unique flat colours."""
    ids = Image.new("RGB", (W, H), (0, 0, 0))
    rows = []
    order = range(len(placed) - 1, -1, -1) if reverse else range(len(placed))
    for i in order:
        sy, im, x, y, name = placed[i]
        n = i + 1
        col = (n & 255, (n >> 8) & 255, 40 + ((n * 37) % 200))
        flat = Image.new("RGB", im.size, col)
        ids.paste(flat, (x, y), im.getchannel("A").point(lambda v: 255 if v > 128 else 0))
        if not reverse:
            rows.append({"id": n, "rgb": list(col), "sort_y": round(sy, 1),
                         "x": x, "y": y, "w": im.width, "h": im.height, "n": name})
    return ids, rows


def apply_grade(canvas: Image.Image, W: int, H: int) -> Image.Image:
    """One gentle golden-hour pass — compose.py's, unchanged.

    A heavier grade fogged the reference into pale yellow, and check_light's
    bounds are fitted to THIS transform: mean 95..180, contrast >= 15,
    saturation 0.20..0.65, blown highlights < 6%, tonal span >= 90.
    """
    canvas = ImageChops.soft_light(canvas, Image.new("RGB", (W, H), (242, 228, 200)))
    haze = Image.new("L", (1, H))
    hp = haze.load()
    for y in range(H):
        ty = y / H
        hp[0, y] = int(52 * max(0.0, (0.20 - ty) / 0.20) ** 1.5)
    canvas = Image.composite(
        Image.blend(canvas, Image.new("RGB", (W, H), (226, 232, 226)), 0.5),
        canvas, haze.resize((W, H)))
    canvas = ImageEnhance.Color(canvas).enhance(1.10)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.07)
    return canvas


def draw_smoke(W, H, cx, cy, n, scale) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(n):
        t = i / max(1, n - 1)
        r = (7 + t * 17) * scale
        x = cx + t * 54 * scale + math.sin(t * 3.4) * 9
        y = cy - t * 104 * scale
        d.ellipse([x - r, y - r * 0.82, x + r, y + r * 0.82],
                  fill=(202, 200, 193, int(146 * (1 - t) ** 0.68)))
    return layer.filter(ImageFilter.GaussianBlur(6))


def draw_lamp(canvas: Image.Image, W, H, gx, gy) -> None:
    """The lighthouse glow — painted AFTER the grade, as compose.py does.

    That ordering is load-bearing for the check, not cosmetic: the ground layer
    is written before the glow, so the glow can only be judged on the finished
    frame, and check_light samples the tower's own axis for a blown near-white
    core with a warm halo. Grading the glow would wash it toward the sand it has
    to be distinguishable from.
    """
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(22, 0, -1):
        r = i * 13
        gd.ellipse([gx - r, gy - r * 0.94, gx + r, gy + r * 0.94],
                   fill=(255, 220, 138, int(4 + 120 * (1 - i / 22) ** 2.2)))
    glow = glow.filter(ImageFilter.GaussianBlur(13))
    canvas.paste(glow, (0, 0), glow)
    beam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(beam)
    bd.ellipse([gx - 30, gy - 26, gx + 30, gy + 26], fill=(255, 236, 176, 200))
    bd.ellipse([gx - 16, gy - 14, gx + 16, gy + 14], fill=(255, 250, 224, 255))
    canvas.paste(beam, (0, 0), beam.filter(ImageFilter.GaussianBlur(3)))


# ---------------------------------------------------------------------- main
def render(draw: dict, bp: dict, pack: Pack, out: str, assets_dir: str, seed: int,
           mutate: str = "") -> dict:
    W, H = bp["canvas"]
    stem = os.path.splitext(out)[0]

    canvas = build_ground(draw, W, H, seed)
    canvas.save(stem + ".ground.png")

    placed, missing = build_layers(pack, draw["sprites"], H,
                                   reverse_depth=(mutate == "reverse-depth"))
    ids, rows = paint_ids(placed, W, H, reverse=False)
    ids.save(stem + ".ids.png")
    paint_ids(placed, W, H, reverse=True)[0].save(stem + ".idsrev.png")

    for _, im, x, y, _ in placed:
        canvas.paste(im, (x, y), im)
    canvas = apply_grade(canvas, W, H)

    for cx, cy, n, sc in draw.get("smokes") or []:
        layer = draw_smoke(W, H, cx, cy, int(n), sc)
        canvas.paste(layer, (0, 0), layer)
    if draw.get("lamp_at"):
        draw_lamp(canvas, W, H, draw["lamp_at"][0], draw["lamp_at"][1])
    canvas.save(out)

    bp["layers"] = rows
    Path(stem + ".blueprint.json").write_text(json.dumps(bp, indent=1))
    written = write_assets(pack, [s["n"] for s in draw["sprites"]], assets_dir)
    return {"layers": len(rows), "sprites": len(draw["sprites"]), "assets": len(written),
            "missing_frames": sorted(set(missing))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draw", required=True)
    ap.add_argument("--blueprint", required=True)
    ap.add_argument("--pack", required=True)
    ap.add_argument("--atlas", required=True, help="directory holding the pack's atlas PNGs")
    ap.add_argument("--assets", required=True, help="where the per-frame PNGs are cut to")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=1.0,
                    help="scale the whole frame. FOR EYEBALLING ONLY, NEVER FOR JUDGING: world_checks.py carries absolute-pixel constants (road_mask steps 3px, check_shadows samples 3/7/12px below a base and takes its bare reference at max(70, w*1.5)), so a shrunk frame is measured at a different relative resolution. Measured at --scale 0.45 on a frame that is GREEN at 1.0: on_road invents one sprite and shadows drops to 46-54%%, under its 55%% floor. Capture at 1.0 to judge.")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mutate", default="", choices=[""] + MUTATIONS,
                    help="break ONE rule on purpose, to prove the arm that guards "
                         "it can fail (see _mutate)")
    a = ap.parse_args()

    bp = json.loads(Path(a.blueprint).read_text())
    draw = json.loads(Path(a.draw).read_text())
    if not 0.05 <= a.scale <= 4.0:
        raise SystemExit(f"raster.py: --scale {a.scale} out of range")
    scale_frame(bp, draw, a.scale)
    expects = _mutate(a.mutate, bp, draw) if a.mutate else ""
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)

    info = render(draw, bp, Pack(a.pack, a.atlas), a.out, a.assets, a.seed, a.mutate)
    if expects:
        print(f"MUTATED {a.mutate} — expect check {expects} to go RED")
    print(f"raster {a.out} {bp['canvas'][0]}x{bp['canvas'][1]} "
          f"{info['sprites']} sprites, {info['layers']} painted layers, "
          f"{info['assets']} assets cut")
    if info["missing_frames"]:
        print(f"MISSING FRAMES (declared, not in the pack): {info['missing_frames']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
