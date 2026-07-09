#!/usr/bin/env python3.12
"""world-asset-install.py — T4 asset installer for Cabinet World (WORLD-V1A).

Installs licensed LimeZu pack assets from local pack directories into the
gitignored asset root `cabinet/dashboard/public/world-assets/` and appends
content-addressed rows to the tracked `manifest.json`, following the same
doctrine as the existing rows (world-asset-gate.py: PNG magic only, 16px
grid, sha256, realpath containment; binaries NEVER committed).

Sections (all idempotent; `--only ui,portraits,regions,forge` to subset):

  ui         Modern User Interface pack (Captain addendum 3 2026-07-09:
             ON-DISK, purchase-handback VOID) — three scales 16/32/48 into
             ui/{scale}/, animated GIFs converted to horizontal PNG
             spritesheets (deterministic frame order, `_sheetN.png` suffix,
             N = frame count). Plus the OWNED Modern Interiors
             4_User_Interface_Elements sheets (speech/emote bubbles,
             thinking dots, mail, timers) into ui/interiors-elements/
             (bubbles/emotes region of the v1a audit).
  portraits  Portrait Generator 1.5.0 raw Portrait Pieces (the Linux app is
             NEVER executed — pieces compose directly with PIL, addendum 3)
             into portrait-pieces/{16x16,32x32,48x48}/{category}/.
  regions    v1a region audit extractions (curated Modern Exteriors 16x16
             singles + staged-future farm singles promotions):
             construction scaffolds (Worksite), buoys (Camping/harbor),
             torch/lantern/streetlight era variants, bucket→tank ladder,
             tent→cottage ladder, lighthouse raw pieces (Beach), and the
             farm 6_Trees sheet (corpus tree canon — the palette positives'
             own oaks, promoted for the live engine's forest border).
  forge      Derived sprites, deterministic PIL composition (no RNG, no
             timestamps), provenance in the `pack` field:
               * lighthouse_unlit / lighthouse_lit — Captain ruling
                 2026-07-09: the lamp must fit the tower; composed from the
                 pack's REAL lighthouse tiles (21_Beach), not the silo/
                 water-tank body. Lit variant = lamp-room glass remapped to
                 the proven warm lamp hue + gallery under-glow.
               * torch_post_unlit / torch_post_lit — camp-era lantern_posts
                 vocab rung; post drawn in proven wood hues, flame cropped
                 from Campfire_3.
               * weather rain strip + splash (16-grid, own pixels in proven
                 accent hues) — no pack ships weather particles (audited:
                 Exteriors/Interiors/Farm/Serene Village 2026-07-09); fog &
                 storm tints remain renderer overlay passes (T1).

Gate: run `python3.12 cabinet/scripts/world-asset-gate.py` after any
install; QA renders for the lighthouse ride `--qa` (composed on manifested
water/terrain tiles only) and must pass
`world-aesthetic-gate.py --mechanical --render <png>`.

Usage:
  python3.12 cabinet/scripts/world-asset-install.py [--only ui,portraits,...]
      [--dry-run] [--qa-out DIR]

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageSequence

REPO = Path(os.environ.get("CABINET_ROOT")
            or Path(__file__).resolve().parents[2])
ASSET_ROOT = REPO / "cabinet" / "dashboard" / "public" / "world-assets"
MANIFEST = ASSET_ROOT / "manifest.json"

HOME = Path.home()
UI_PACK = HOME / "Downloads" / "modernuserinterface-win"
PP_ROOT = (HOME / "Downloads" / "Portrait Generator 1.5.0 Linux Build"
           / "Portrait Pieces")
MI_UI = HOME / "Downloads" / "moderninteriors-win" / "4_User_Interface_Elements"
ME16 = (HOME / "Downloads" / "modernexteriors-win" / "Modern_Exteriors_16x16"
        / "Modern_Exteriors_Complete_Singles_16x16")
FARM_SG = ASSET_ROOT / "staged-future" / "farm" / "Single_Files_16x16"

LICENSE = "LimeZu commercial — do not redistribute"
PACK_UI = "LimeZu Modern User Interface (modernuserinterface-win)"
PACK_PP = "LimeZu Portrait Generator 1.5.0 (raw Portrait Pieces; app never run)"
PACK_MI_UI = "LimeZu Modern Interiors (moderninteriors-win, UI elements)"
PACK_ME = "LimeZu Modern Exteriors (modernexteriors-win, 16x16 singles)"
PACK_FARM = "LimeZu Modern Farm (16x16)"

GRID = 16
_SAFE = re.compile(r"[^A-Za-z0-9._/-]+")

# proven drawn-accent hues (compose_unified.py ratified lineage)
LAMP_Y = (250, 208, 120)
WOODMID = (96, 66, 42)
WOODDK = (64, 46, 30)
WOODDKR = (44, 30, 20)
CHALK = (226, 230, 238)
FOAM_A = (232, 240, 248)
DKLAMP = (38, 40, 54)
DKLAMP3 = (20, 22, 32)


def sanitize(rel: str) -> str:
    """Normalize a relative asset path to the manifest's safe charset."""
    rel = rel.replace(" - ", "-").replace(" ", "_")
    rel = _SAFE.sub("_", rel)
    while "__" in rel:
        rel = rel.replace("__", "_")
    return rel


def contained(dest: Path) -> Path:
    """Realpath-jail check mirroring world-asset-gate.py containment."""
    real = Path(os.path.realpath(dest))
    root = Path(os.path.realpath(ASSET_ROOT))
    try:
        real.relative_to(root)
    except ValueError:
        raise SystemExit(f"REFUSED: {dest} escapes the asset root")
    return real


class Installer:
    def __init__(self, dry: bool):
        self.dry = dry
        self.rows: dict[str, dict] = {}
        self.copied = 0
        self.skipped_nonpng = 0

    def _row(self, rel: str, data: bytes, pack: str) -> None:
        im = Image.open(__import__("io").BytesIO(data))
        w, h = im.size
        if w % GRID or h % GRID:
            raise SystemExit(f"REFUSED off-grid {rel}: {w}x{h}")
        self.rows[rel.rsplit(".", 1)[0]] = {
            "id": rel.rsplit(".", 1)[0],
            "path": rel,
            "w": w, "h": h, "grid": GRID,
            "sha256": hashlib.sha256(data).hexdigest(),
            "pack": pack, "license": LICENSE,
        }

    def put_bytes(self, rel: str, data: bytes, pack: str) -> None:
        rel = sanitize(rel)
        dest = ASSET_ROOT / rel
        contained(dest)
        if not self.dry:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        self._row(rel, data, pack)
        self.copied += 1

    def copy_png(self, src: Path, rel: str, pack: str) -> None:
        data = src.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise SystemExit(f"REFUSED non-PNG copy: {src}")
        self.put_bytes(rel, data, pack)

    def gif_to_sheet(self, src: Path, rel_base: str, pack: str) -> None:
        """Animated GIF → horizontal RGBA PNG spritesheet (deterministic:
        frame order as stored; per-frame canvas padded up to the 16 grid)."""
        gif = Image.open(src)
        frames = [f.convert("RGBA") for f in ImageSequence.Iterator(gif)]
        if not frames:
            return
        fw = -(-frames[0].width // GRID) * GRID
        fh = -(-frames[0].height // GRID) * GRID
        sheet = Image.new("RGBA", (fw * len(frames), fh), (0, 0, 0, 0))
        for i, f in enumerate(frames):
            sheet.alpha_composite(f, (i * fw, 0))
        rel = f"{rel_base}_sheet{len(frames)}.png"
        buf = __import__("io").BytesIO()
        sheet.save(buf, "PNG")
        self.put_bytes(rel, buf.getvalue(),
                       pack + f" — GIF→sheet, {len(frames)}f @{fw}x{fh}")

    def image_png(self, im: Image.Image, rel: str, pack: str) -> None:
        buf = __import__("io").BytesIO()
        im.save(buf, "PNG")
        self.put_bytes(rel, buf.getvalue(), pack)


# ---------------------------------------------------------------- sections
def install_ui(ins: Installer) -> None:
    for scale in ("16x16", "32x32", "48x48"):
        base = UI_PACK / scale
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = f"ui/{scale}/{p.relative_to(base)}"
            if p.suffix.lower() == ".png":
                ins.copy_png(p, rel, PACK_UI)
            elif p.suffix.lower() == ".gif":
                ins.gif_to_sheet(p, rel.rsplit(".", 1)[0], PACK_UI)
            else:
                ins.skipped_nonpng += 1
    # owned Modern Interiors UI elements (bubbles/emotes/timers/mail)
    for p in sorted(MI_UI.glob("*.png")):
        ins.copy_png(p, f"ui/interiors-elements/{p.name}", PACK_MI_UI)
    for p in sorted((MI_UI / "Animated_Spritesheets").glob("*.gif")):
        ins.gif_to_sheet(p, f"ui/interiors-elements/animated/{p.stem}",
                         PACK_MI_UI)


def install_portraits(ins: Installer) -> None:
    for scale_dir in sorted(PP_ROOT.iterdir()):
        if not scale_dir.is_dir():
            continue
        scale = scale_dir.name.rsplit(" ", 1)[-1]  # "16x16" | "32x32" | "48x48"
        for p in sorted(scale_dir.rglob("*.png")):
            rel = f"portrait-pieces/{scale}/{p.relative_to(scale_dir)}"
            ins.copy_png(p, rel, PACK_PP)


# curated v1a region extractions (Modern Exteriors 16x16 singles)
ME_REGIONS: dict[str, list[str]] = {
    # the REAL lighthouse tiles (Captain ruling: lamp fits tower)
    "exteriors/lighthouse": [
        "21_Beach_16x16_Example_Lighthouse",
        "21_Beach_16x16_Lighthouse_To_Decorate",
        "21_Beach_16x16_Lighthouse_Roof_Light",
        "21_Beach_16x16_Lighthouse_Roof_Decorated",
        "21_Beach_16x16_Lighthouse_Roof_Trapdoor",
        "21_Beach_16x16_Lighthouse_Bottom_Door_Closed",
        "21_Beach_16x16_Lighthouse_Door_Open",
    ],
    # construction scaffolds + site dressing (visible-work pipeline)
    "exteriors/worksite": [
        "ME_Singles_Worksite_16x16_Building_Skeleton_1",
        "ME_Singles_Worksite_16x16_Building_Skeleton_2",
        "ME_Singles_Worksite_16x16_Light_Tower_1",
        "ME_Singles_Worksite_16x16_Light_Tower_2",
        "ME_Singles_Worksite_16x16_Entrance_1",
        "ME_Singles_Worksite_16x16_Sign_1",
        "ME_Singles_Worksite_16x16_Sign_2",
        "ME_Singles_Worksite_16x16_Cone_1",
        "ME_Singles_Worksite_16x16_Cone_2",
        "ME_Singles_Worksite_16x16_Helmet_1",
        "ME_Singles_Worksite_16x16_Helmet_2",
    ] + [f"ME_Singles_Worksite_16x16_Props_{i}" for i in range(1, 10)]
      + [f"ME_Singles_Worksite_16x16_Fence_1_{i}" for i in range(1, 9)]
      + [f"ME_Singles_Worksite_16x16_Ground_1_{i}" for i in range(1, 7)],
    # buoys (reef-buoy = honest retired/instance-test marker) + pier props
    "exteriors/harbor": (
        [f"ME_Singles_Camping_16x16_Buoy_{i}" for i in range(1, 7)]
        + ["ME_Singles_Camping_16x16_Life_Buoy_1",
           "ME_Singles_Camping_16x16_Life_Buoy_2",
           "ME_Singles_Camping_16x16_Pier_Pole_1"]
        + [f"ME_Singles_Camping_16x16_Pier_Barrel_{i}" for i in range(1, 5)]
    ),
    # tent→cottage ladder (camp tents; cottage/hut end lives in the
    # already-manifested Serene Village sheet + these country houses)
    "exteriors/camping": (
        [f"ME_Singles_Camping_16x16_Tent_{i}" for i in range(1, 7)]
        + [f"ME_Singles_Camping_16x16_Lantern_{i}" for i in range(1, 7)]
        + [f"ME_Singles_Camping_16x16_Campfire_{i}" for i in range(1, 4)]
    ),
    "exteriors/houses": [
        "24_Additional_Houses_Country_House_16x16",
        "24_Additional_Houses_Country_House_No_Banisters_16x16",
    ],
    # bucket→tank ladder top end (tank/tank_tower) + streetlight era
    "exteriors/props": [
        f"ME_Singles_City_Props_16x16_Water_Tower_{i}" for i in range(1, 5)
    ],
    "exteriors/street": [
        f"ME_Singles_City_Props_16x16_Street_Lamp_{i}" for i in range(3, 6)
    ],
}

# corpus tree canon (v1a terrain fix): the aesthetic-gate palette was
# fitted from positives composed with the farm-pack trees (compose_unified
# TREECUTS) — promote the whole tree sheet so the live engine's forest
# border draws the SAME palette-proven trees (the Serene tree-row strips
# measure ~11% foreign per pixel and were a top offender at island zoom).
FARM_SHEET_PROMOTIONS = [
    ("6_Trees_16x16", "farm/6_Trees_16x16.png"),
]

# bucket→tank ladder bottom end: promote staged-future farm singles
FARM_REGIONS = [
    "Props_and_Buildings_16x16/Bucket_1_Single_16x16",
    "Props_and_Buildings_16x16/Bucket_2_Single_16x16",
    "Props_and_Buildings_16x16/Bucket_Load_16x16",
    "Props_and_Buildings_16x16/Well_Stone_16x16",
    "Props_and_Buildings_16x16/Well_Usable_16x16",
    "Props_and_Buildings_16x16/Well_Usable_Bucket_Empty_16x16",
    "Props_and_Buildings_16x16/Well_Usable_Bucket_Full_16x16",
]


def install_regions(ins: Installer) -> None:
    for destdir, names in sorted(ME_REGIONS.items()):
        for n in names:
            src = ME16 / f"{n}.png"
            if not src.exists():
                raise SystemExit(f"missing pack single: {src}")
            ins.copy_png(src, f"{destdir}/{n}.png", PACK_ME)
    for rel in FARM_REGIONS:
        src = FARM_SG / f"{rel}.png"
        if not src.exists():
            raise SystemExit(f"missing farm single: {src}")
        ins.copy_png(src, f"farm/props/{Path(rel).name}.png", PACK_FARM)
    for name, dest in FARM_SHEET_PROMOTIONS:
        # whole sheets live one level above the singles dir
        src = FARM_SG.parent / f"{name}.png"
        if not src.exists():
            raise SystemExit(f"missing farm sheet: {src}")
        ins.copy_png(src, dest, PACK_FARM)


# ---------------------------------------------------------------- forge
def _lamp_room_lit(base: Image.Image) -> Image.Image:
    """Remap the lamp-room glass of the pack lighthouse to the proven warm
    lamp hue. Glass = bluish light pixels in the lamp-room band (the three
    tile rows under the dome), found by fixed color predicate — no RNG."""
    im = base.copy()
    px = im.load()
    # lamp room occupies roughly y ∈ [3*GRID, 7*GRID) on the 7x16 sprite
    y0, y1 = 3 * GRID, 7 * GRID
    for y in range(y0, min(y1, im.height)):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            light = (r + g + b) / 3
            if b >= r and light > 120 and b > 100:  # cool glass pixel
                t = min(1.0, light / 235.0)
                nr = int(LAMP_Y[0] * t)
                ng = int(LAMP_Y[1] * t)
                nb = int(LAMP_Y[2] * t * 0.9)
                px[x, y] = (min(nr + 20, 255), min(ng + 14, 255), nb, a)
    return im


def forge_lighthouse(ins: Installer) -> tuple[Image.Image, Image.Image]:
    """Unlit + lit lighthouse from the pack's real tower tiles."""
    base = Image.open(ME16 / "21_Beach_16x16_Example_Lighthouse.png"
                      ).convert("RGBA")
    unlit = base.copy()
    # honest unlit: dim the glass toward dusk-glass (keep structure)
    px = unlit.load()
    for y in range(3 * GRID, 7 * GRID):
        for x in range(unlit.width):
            r, g, b, a = px[x, y]
            if a and b >= r and (r + g + b) / 3 > 120 and b > 100:
                px[x, y] = (int(r * 0.45) + DKLAMP[0] // 2,
                            int(g * 0.45) + DKLAMP[1] // 2,
                            int(b * 0.45) + DKLAMP[2] // 2, a)
    lit = _lamp_room_lit(base)
    prov = (PACK_ME + " — derived: 21_Beach lighthouse, lamp-room glass "
            "remap only (unlit=dimmed glass, lit=proven lamp hue 250,208,120)")
    ins.image_png(unlit, "derived/lighthouse/lighthouse_unlit.png", prov)
    ins.image_png(lit, "derived/lighthouse/lighthouse_lit.png", prov)
    return unlit, lit


def forge_torch(ins: Installer) -> None:
    """Camp-era torch post (lantern_posts vocab rung): drawn post in proven
    wood hues; lit = flame cropped from Campfire_3; unlit = charred tip."""
    fire = Image.open(ME16 / "ME_Singles_Camping_16x16_Campfire_3.png"
                      ).convert("RGBA")
    flame = fire.crop((0, 0, 16, 20))  # flame body above the wood base
    for lit in (False, True):
        cv = Image.new("RGBA", (GRID, 2 * GRID), (0, 0, 0, 0))
        from PIL import ImageDraw
        d = ImageDraw.Draw(cv)
        d.rectangle([7, 10, 8, 30], fill=WOODMID + (255,))
        d.rectangle([7, 10, 7, 30], fill=WOODDK + (255,))
        d.rectangle([6, 29, 9, 31], fill=WOODDKR + (255,))
        d.rectangle([6, 8, 9, 11], fill=WOODDK + (255,))
        if lit:
            cv.alpha_composite(flame, (0, -4))
        else:
            d.rectangle([6, 6, 9, 9], fill=DKLAMP + (255,))
            d.rectangle([7, 5, 8, 6], fill=DKLAMP3 + (255,))
        prov = (PACK_ME + " — derived: torch post (proven wood hues"
                + (", flame crop Campfire_3)" if lit else ", charred tip)"))
        ins.image_png(cv, "derived/props/torch_post_"
                      + ("lit" if lit else "unlit") + ".png", prov)


def forge_weather(ins: Installer) -> None:
    """Rain particle strip + splash (no pack ships weather particles —
    audited 2026-07-09). 4 frames each, 16x16, proven accent hues, fixed
    coordinates (deterministic); fog/storm remain renderer tint passes."""
    from PIL import ImageDraw
    strip = Image.new("RGBA", (4 * GRID, GRID), (0, 0, 0, 0))
    d = ImageDraw.Draw(strip)
    drops = [(2, 1), (9, 4), (5, 9), (13, 7), (7, 13), (12, 12)]
    for f in range(4):
        ox = f * GRID
        for i, (x, y) in enumerate(drops):
            yy = (y + f * 4) % GRID
            alpha = 190 if (i + f) % 2 == 0 else 140
            d.line([ox + x, yy, ox + x - 1, min(yy + 2, GRID - 1)],
                   fill=CHALK + (alpha,))
    splash = Image.new("RGBA", (4 * GRID, GRID), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(splash)
    for f in range(4):
        ox = f * GRID
        r = 1 + f
        for dx, dy in ((-r, 0), (r, 0)):
            x, y = 8 + dx, 13 + (0 if f < 3 else -1)
            if 0 <= x < GRID:
                d2.point((ox + x, y), fill=FOAM_A + (200 - f * 40,))
        d2.point((ox + 8, 13), fill=CHALK + (120,))
    prov = ("own pixels — derived: weather particles (rain/splash), proven "
            "accent hues CHALK/FOAM_A; no pack source exists (audited)")
    ins.image_png(strip, "derived/weather/rain_strip4.png", prov)
    ins.image_png(splash, "derived/weather/rain_splash4.png", prov)


def forge(ins: Installer) -> tuple[Image.Image, Image.Image]:
    unlit, lit = forge_lighthouse(ins)
    forge_torch(ins)
    forge_weather(ins)
    return unlit, lit


# ---------------------------------------------------------------- QA render
class _LCG:
    """fnv1a-seeded LCG (determinism law — no random module)."""

    def __init__(self, tag: str):
        h = 0x811C9DC5
        for ch in tag.encode():
            h ^= ch
            h = (h * 0x01000193) & 0xFFFFFFFF
        self.s = h or 1

    def ri(self, a: int, b: int) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return a + self.s % (b - a + 1)


def _fleck_hues(ter: Image.Image, base: tuple) -> tuple[list, list]:
    """Dark/light green blade hues sampled from the terrain sheet itself
    (compose_unified fleck recipe: sheet-native contrasty hues only)."""
    pool: dict[tuple, int] = {}
    px = ter.load()
    for y in range(0, ter.height, 2):
        for x in range(0, ter.width, 2):
            r, g, b, a = px[x, y]
            if a > 128 and g > r and g > b:
                pool[(r, g, b)] = pool.get((r, g, b), 0) + 1
    dk = [c for c, n in pool.items() if sum(c) <= sum(base) - 30 and n >= 4]
    lt = [c for c, n in pool.items() if sum(c) >= sum(base) + 30 and n >= 4]
    return sorted(dk), sorted(lt)


def qa_render(unlit: Image.Image, lit: Image.Image, outdir: Path) -> list[Path]:
    """T4 asset-showcase test renders (one per lighthouse variant): every
    installed region family placed on textured manifested terrain —
    deterministic tiling + fnv1a-LCG flecks, no RNG, no timestamps."""
    ter = Image.open(ASSET_ROOT / "farm" / "1_Terrains_16x16.png"
                     ).convert("RGBA")

    def tile(tx, ty):
        return ter.crop((tx * GRID, ty * GRID, (tx + 1) * GRID,
                         (ty + 1) * GRID))

    def A(rel):
        return Image.open(ASSET_ROOT / rel).convert("RGBA")

    grass = tile(3, 2)            # proven lineage GRASS
    water = tile(17, 1)           # proven lineage WATER_P
    mulch = tile(1, 13)           # proven lineage MULCH center
    tan = tile(1, 1)              # proven lineage TAN center
    # NOTE: no sand band — compose_unified deliberately kept sand out of the
    # calibrated palette ("foreign sand", line 560); grass runs to the water
    gbase = grass.load()[GRID // 2, GRID // 2][:3]
    dk, lt = _fleck_hues(ter, gbase)

    outs = []
    for name, sprite in (("unlit", unlit), ("lit", lit)):
        W, H = 34 * GRID, 22 * GRID
        cv = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        for ty in range(22):
            for tx in range(34):
                if ty >= 15:
                    t = water
                elif 8 <= ty:                    # worked meadow (mulch)
                    t = mulch
                elif 5 <= ty < 8 and 14 <= tx < 26:   # tan plaza strip
                    t = tan
                else:
                    t = grass
                cv.alpha_composite(t, (tx * GRID, ty * GRID))
        from PIL import ImageDraw
        d = ImageDraw.Draw(cv)
        rng = _LCG("t4-showcase-" + name)
        for _ in range(6500):                      # grass blade flecks
            x, y = rng.ri(0, W - 2), rng.ri(0, 15 * GRID - 2)
            hue = (dk or [WOODDK])[rng.ri(0, max(len(dk) - 1, 0))] \
                if rng.ri(0, 1) else (lt or [CHALK])[rng.ri(0, max(len(lt) - 1, 0))]
            d.point((x, y), fill=tuple(hue) + (255,))
        for _ in range(650):                       # tide foam flecks
            x, y = rng.ri(0, W - 8), rng.ri(15 * GRID, H - 2)
            d.rectangle([x, y, x + rng.ri(2, 6), y], fill=FOAM_A + (170,))
        # region families (fixed deterministic placements, measured tile
        # sizes — no overlaps; the 18x16-tile Country_House is manifested
        # but too large for this showcase canvas)
        cv.alpha_composite(sprite, (26 * GRID, 5 * GRID))   # THE lighthouse
        cv.alpha_composite(
            A("exteriors/worksite/ME_Singles_Worksite_16x16_Building_Skeleton_2.png"),
            (1 * GRID, 1 * GRID))
        cv.alpha_composite(
            A("exteriors/props/ME_Singles_City_Props_16x16_Water_Tower_2.png"),
            (9 * GRID, 1 * GRID))
        cv.alpha_composite(
            A("exteriors/worksite/ME_Singles_Worksite_16x16_Light_Tower_1.png"),
            (15 * GRID, 1 * GRID))
        cv.alpha_composite(
            A("exteriors/street/ME_Singles_City_Props_16x16_Street_Lamp_3.png"),
            (20 * GRID, 1 * GRID))
        cv.alpha_composite(A("derived/props/torch_post_lit.png"),
                           (23 * GRID, 3 * GRID))
        cv.alpha_composite(A("derived/props/torch_post_unlit.png"),
                           (24 * GRID, 3 * GRID))
        cv.alpha_composite(
            A("exteriors/camping/ME_Singles_Camping_16x16_Lantern_2.png"),
            (25 * GRID, 4 * GRID))
        cv.alpha_composite(
            A("exteriors/camping/ME_Singles_Camping_16x16_Campfire_3.png"),
            (21 * GRID, 6 * GRID))
        cv.alpha_composite(
            A("farm/props/Well_Usable_Bucket_Full_16x16.png"),
            (16 * GRID, 7 * GRID))
        cv.alpha_composite(
            A("exteriors/camping/ME_Singles_Camping_16x16_Tent_1.png"),
            (9 * GRID, 9 * GRID))
        cv.alpha_composite(
            A("exteriors/camping/ME_Singles_Camping_16x16_Tent_3.png"),
            (13 * GRID, 10 * GRID))
        for i in range(1, 5):                      # pier barrels shoreline
            cv.alpha_composite(
                A(f"exteriors/harbor/ME_Singles_Camping_16x16_Pier_Barrel_{i}.png"),
                ((17 + i * 2) * GRID, 12 * GRID))
        for i in (1, 4):                           # buoys in open water
            cv.alpha_composite(
                A(f"exteriors/harbor/ME_Singles_Camping_16x16_Buoy_{i}.png"),
                ((4 + i * 4) * GRID, 18 * GRID))
        cv.alpha_composite(
            A("exteriors/harbor/ME_Singles_Camping_16x16_Life_Buoy_1.png"),
            (22 * GRID, 17 * GRID))
        cv.alpha_composite(
            A("exteriors/harbor/ME_Singles_Camping_16x16_Pier_Pole_1.png"),
            (2 * GRID, 17 * GRID))
        cv.alpha_composite(
            A("exteriors/camping/ME_Singles_Camping_16x16_Tent_2.png"),
            (4 * GRID, 11 * GRID))
        cv.alpha_composite(
            A("exteriors/camping/ME_Singles_Camping_16x16_Campfire_1.png"),
            (12 * GRID, 8 * GRID))
        cv.alpha_composite(
            A("exteriors/worksite/ME_Singles_Worksite_16x16_Sign_1.png"),
            (0 * GRID, 12 * GRID))
        for i in range(1, 7):                      # worksite fence line
            cv.alpha_composite(
                A(f"exteriors/worksite/ME_Singles_Worksite_16x16_Fence_1_{i}.png"),
                ((17 + i) * GRID, 13 * GRID))
        cv.alpha_composite(
            A("exteriors/worksite/ME_Singles_Worksite_16x16_Props_1.png"),
            (19 * GRID, 8 * GRID))
        cv.alpha_composite(
            A("exteriors/worksite/ME_Singles_Worksite_16x16_Props_3.png"),
            (18 * GRID, 9 * GRID))
        p = outdir / f"t4-lighthouse-{name}.png"
        cv.save(p)
        outs.append(p)
    return outs


# ---------------------------------------------------------------- manifest
def update_manifest(rows: dict[str, dict], dry: bool) -> None:
    m = json.loads(MANIFEST.read_text())
    by_id = {a["id"]: a for a in m["assets"]}
    added = replaced = 0
    for aid, row in sorted(rows.items()):
        if aid in by_id:
            by_id[aid].update(row)
            replaced += 1
        else:
            m["assets"].append(row)
            added += 1
    m["version"] = 3
    if "Portrait Generator" not in m.get("_doc", ""):
        m["_doc"] += (" v3 adds: Modern User Interface pack (ui/, three "
                      "scales; GIFs converted to _sheetN.png spritesheets), "
                      "Portrait Generator raw pieces (portrait-pieces/), "
                      "v1a region extractions (worksite/harbor/camping/"
                      "lighthouse/houses/props/street + farm props), and "
                      "deterministic derived/ sprites (lighthouse unlit+lit, "
                      "torch post, weather particles) with provenance in "
                      "their pack fields.")
    if not dry:
        MANIFEST.write_text(json.dumps(m, indent=1, ensure_ascii=False)
                            + "\n")
    print(f"manifest: +{added} added, {replaced} replaced, "
          f"total {len(m['assets'])}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="ui,portraits,regions,forge")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--qa-out", default=None,
                    help="write lighthouse QA renders to this dir")
    args = ap.parse_args()
    parts = {s.strip() for s in args.only.split(",")}

    ins = Installer(args.dry_run)
    unlit = lit = None
    if "ui" in parts:
        install_ui(ins)
    if "portraits" in parts:
        install_portraits(ins)
    if "regions" in parts:
        install_regions(ins)
    if "forge" in parts:
        unlit, lit = forge(ins)
    update_manifest(ins.rows, args.dry_run)
    print(f"installed {ins.copied} assets "
          f"({ins.skipped_nonpng} non-image files skipped)")
    if args.qa_out and unlit is not None:
        outdir = Path(args.qa_out)
        outdir.mkdir(parents=True, exist_ok=True)
        for p in qa_render(unlit, lit, outdir):
            print("QA render:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
