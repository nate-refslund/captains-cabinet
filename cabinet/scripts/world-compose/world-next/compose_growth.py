#!/usr/bin/env python3.12
"""
TRIPTYCH — THE GROWTH STORY (unified-spec-v2.md §3 eras), three renders on the
PROVEN compose_unified.py lineage (world-unified, ratified 7.5):

  stage-egg.png    1200x900   EGG era (§3.1): forested islet, one cottage,
                              bare flagpole, mailbox (flag down), dirt path,
                              rowboat jetty, dark lantern-cairn, mist beyond.
  stage-today.png  1600x1100  VILLAGE + WORKING QUAY (≈ today): the ratified
                              island compressed to frame, ONE product isle in
                              haze offshore, one VISIBLE-WORK construction
                              site (scaffold + crew clearing trees, §3.3/D4).
  stage-grown.png  1920x1280  PORT TOWN → ARCHIPELAGO zoom-out (LOD, D1):
                              expanded village, busy multi-berth quay, LIT
                              lighthouse, 3 product isles w/ size variance,
                              sea lanes + ships, counting-house, infirmary,
                              telegraph poles.

Palette law: every sprite pixel from LimeZu sheets; drawn accents reuse ONLY
hues proven in compose_unified.py or sampled at runtime from the sheets
themselves. Deterministic (fnv1a LCG only). Scratchpad-only outputs.
Gate: world-aesthetic-gate.py --mechanical --render <png> must pass all three.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
"""
import sys

# In-repo landing (WORLD-V1A T1): the compositor lineage lives at
# cabinet/scripts/world-compose/{world-unified,world-next}.
from pathlib import Path as _Path
_BASE = str(_Path(__file__).resolve().parents[1])
sys.path.insert(0, _BASE + "/world-unified")

import compose_unified as U                      # noqa: E402  proven lineage
from PIL import Image, ImageDraw                 # noqa: E402

T   = U.T
OUT = _BASE + "/world-next"

# proven drawn-accent hues (all appear in the ratified compose_unified.py)
CREAM   = (242, 236, 222)
WOODMID = (96, 66, 42)
WOODDK  = (64, 46, 30)
WOODDKR = (44, 30, 20)
PIEREDG = (58, 40, 26)
FOAM_A  = (232, 240, 248)
FOAM_B  = (226, 236, 246)
FOAM_C  = (222, 232, 244)
CHALK   = (226, 230, 238)
LAMP_Y  = (250, 208, 120)      # noticeboard pin yellow (proven)
ASH_L   = (120, 116, 124)      # firepit ash greys (proven)
ASH_M   = (88, 84, 92)
ASH_D   = (64, 60, 70)
DKLAMP  = (38, 40, 54)         # dark lantern head hues (proven)
DKLAMP2 = (30, 36, 52)
DKLAMP3 = (20, 22, 32)
RED_BY  = (198, 50, 40)        # buoy red (proven)

# ---------------------------------------------------------------- samples
def _grass_fleck_colors():
    """Sheet-native contrasty blade hues (compose_unified recipe, verbatim)."""
    grass = U.tile(U.GRASS)
    gv2 = [U.tile(s) for s in U.GRASS_V]
    gbase = grass.load()[T // 2, T // 2][:3]
    pool = {}
    for v in gv2:
        vp = v.load()
        for yy in range(T):
            for xx in range(T):
                r, g, b, a = vp[xx, yy]
                if a > 128 and g > r and g > b:
                    pool[(r, g, b)] = pool.get((r, g, b), 0) + 1
    dk = [c for c, n in pool.items() if sum(c) <= sum(gbase) - 30 and n >= 4]
    lt = [c for c, n in pool.items() if sum(c) >= sum(gbase) + 30 and n >= 4]
    if not dk or not lt:
        tr = U.tree("oakM"); cnp = tr.load()
        for yy in range(0, tr.height, 2):
            for xx in range(0, tr.width, 2):
                r, g, b, a = cnp[xx, yy]
                if a > 128 and g > r and g > b:
                    c = (r, g, b)
                    if sum(c) <= sum(gbase) - 30: dk.append(c)
                    elif sum(c) >= sum(gbase) + 30: lt.append(c)
    return gbase, min(dk, key=sum), max(lt, key=sum)

# committed gate palette (read-only): drawn ACCENT hues that cover large areas
# (sea dashes, swells, mist) must sit in a palette bin — native by the same
# test the gate runs. Composition-side filter; thresholds untouched.
import json as _json
_PALJ = _json.load(open(_Path(__file__).resolve().parents[2]
                        / "world-aesthetic" / "calibration" / "palette.json"))
_PBITS = _PALJ["quant_bits"]; _PBINS = set(_PALJ["bins"])
_PNR = _PALJ.get("neighbor_radius", 1)

def in_palette(c):
    sh = 8 - _PBITS
    mx = (1 << _PBITS) - 1
    r, g, b = c[0] >> sh, c[1] >> sh, c[2] >> sh
    for dr in range(-_PNR, _PNR + 1):
        for dg in range(-_PNR, _PNR + 1):
            for db in range(-_PNR, _PNR + 1):
                rr, gg, bb = r + dr, g + dg, b + db
                if 0 <= rr <= mx and 0 <= gg <= mx and 0 <= bb <= mx:
                    if ((rr << (2 * _PBITS)) | (gg << _PBITS) | bb) in _PBINS:
                        return True
    return False

def _water_colors():
    """Pond-module sampled water hues (compose_unified recipe), palette-
    filtered: the pond rim's lightest near-white (236,244,252) is OUTSIDE the
    corpus palette (v1's #1 foreign color) — at archipelago sea scale it blows
    the 5%% budget, so light accents use the lightest IN-palette pond hues."""
    pond = U.cut(U.TER, U.POND_MOD[0], U.POND_MOD[1], 3, 3)
    ppx = pond.load()
    cols = {}
    for yy in range(3 * T):
        for xx in range(3 * T):
            r, g, b, a = ppx[xx, yy]
            if a > 128 and b > r + 20:
                cols[(r, g, b)] = cols.get((r, g, b), 0) + 1
    ranked = sorted(cols.items(), key=lambda kv: -kv[1])
    base = ranked[0][0]
    lighter = [c for c, n in ranked if sum(c) > sum(base) + 30 and n > 8
               and in_palette(c)]
    darker  = [c for c, n in ranked if sum(c) < sum(base) - 30 and n > 8
               and in_palette(c)]
    mids = [c for c, n in ranked
            if sum(base) - 90 <= sum(c) <= sum(base) - 25 and n > 8
            and in_palette(c)]
    # sheet-native + in-palette light fallbacks (probed from the owned
    # sheets: sidewalk/boat/terrain highlights — the pond rim's own lights
    # are all outside the corpus palette)
    wave_l = lighter[0] if lighter else (212, 222, 230)
    wave_l2 = lighter[1] if len(lighter) > 1 else (
        (185, 195, 213) if not lighter else wave_l)
    wave_d = darker[0] if darker else (52, 90, 172)
    mid    = mids[0] if mids else wave_d
    print("water sample:", "base", base, "L", wave_l, "L2", wave_l2,
          "D", wave_d, "mid", mid)
    return base, wave_l, wave_l2, wave_d, mid

def _stone_colors():
    swpx = U.sh(U.SW1).crop((0, 0, T, T)).load()
    dark = min(((swpx[xx, yy][0], swpx[xx, yy][1], swpx[xx, yy][2])
                for yy in range(T) for xx in range(T)), key=sum)
    swpx2 = U.sh(U.SW2).crop((0, 0, T, T)).load()
    lite = max(((swpx2[xx, yy][0], swpx2[xx, yy][1], swpx2[xx, yy][2])
                for yy in range(T) for xx in range(T)), key=sum)
    return dark, lite

def _tan_wear_colors():
    tfill = U.cut(U.TER, 5, 1)
    tpx = tfill.load()
    tcols = sorted({tpx[xx, yy][:3] for xx in range(T) for yy in range(T)},
                   key=sum)
    t_lite = tcols[-1]
    spx2 = U.tile((U.TER, 1, 9)).load()
    t_dark = min(((spx2[xx, yy][0], spx2[xx, yy][1], spx2[xx, yy][2])
                  for yy in range(T) for xx in range(T)), key=sum)
    return t_dark, t_lite

def _fence_browns():
    im = U.cut(U.FEN, 13, 7)
    px = im.load()
    cols = sorted({px[xx, yy][:3] for xx in range(T) for yy in range(T)
                   if px[xx, yy][3] > 128}, key=sum)
    return cols[0], cols[len(cols) // 2], cols[-1]

GBASE, G_DK, G_LT = _grass_fleck_colors()
WBASE, WAVE_L, WAVE_L2, WAVE_D, WMID = _water_colors()
ST_DK, ST_LT = _stone_colors()
TAN_DK, TAN_LT = _tan_wear_colors()
FBR_D, FBR_M, FBR_L = _fence_browns()
SWELL_C = (116, 170, 191)      # in-palette teal mid-light (sheet-probed)
MIST_HUES = [WAVE_L, WAVE_L2, WAVE_L, (177, 186, 200)]

# ---------------------------------------------------------------- painters
def paint_grass(sc, x0, y0, x1, y1, seed, skip=None, daub_div=12):
    """Three-pass ground painting (base + variant daubs + speckle + flecks)."""
    skip = skip or set()
    grass = U.tile(U.GRASS); gvar = U.tile(U.GVAR)
    gv2 = [U.tile(s) for s in U.GRASS_V]
    rng = U.LCG(seed)
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if (tx, ty) in skip: continue
            sc.gpaste(grass, tx, ty)
    n_daub = max(6, (x1 - x0 + 1) * (y1 - y0 + 1) // daub_div)
    for _ in range(n_daub):
        cx_, cy_ = rng.ri(x0, x1), rng.ri(y0, y1)
        v = gv2[rng.ri(0, 3)]
        for _ in range(rng.ri(2, 5)):
            tx = min(x1, max(x0, cx_ + rng.ri(-2, 2)))
            ty = min(y1, max(y0, cy_ + rng.ri(-1, 1)))
            if (tx, ty) not in skip:
                sc.gpaste(v, tx, ty)
    sp = U.LCG(seed + "-speck")
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if (tx, ty) in skip: continue
            if sp.rf() < 0.85:
                sc.gpaste(gvar, tx, ty)
    gd = ImageDraw.Draw(sc.ground)
    fl = U.LCG(seed + "-fleck")
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if (tx, ty) in skip: continue
            for _ in range(fl.ri(4, 7)):
                fx = tx * T + fl.ri(0, T - 2); fy = ty * T + fl.ri(0, T - 3)
                col = G_DK if fl.rf() < 0.62 else G_LT
                gd.rectangle([fx, fy, fx, fy + fl.ri(1, 2)], fill=col + (255,))

def paint_sea(sc, x0, y0, x1, y1, seed, two_tone=False, dash_lo=8, dash_hi=12,
              skip=None):
    """Sheet-sampled wave dashes over flat pond water; optional two-tone body
    (large-water frames: breaks the single dominant color, hues stay native)."""
    skip = skip or set()
    wp = U.tile(U.WATER_P)
    gd = ImageDraw.Draw(sc.ground)
    tt = U.LCG(seed + "-tone")
    tone_cell = {}
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if (tx, ty) in skip: continue
            sc.ground.paste(wp, (tx * T, ty * T))
            if two_tone:
                cell = (tx // 3, ty // 2)
                if cell not in tone_cell:
                    tone_cell[cell] = tt.rf() < 0.44
                if tone_cell[cell]:
                    gd.rectangle([tx * T, ty * T, tx * T + 15, ty * T + 15],
                                 fill=WMID + (255,))
    wrng = U.LCG(seed + "-waves")
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if (tx, ty) in skip: continue
            n_d = dash_lo + (wrng.n() % max(1, dash_hi - dash_lo + 1))
            for _ in range(n_d):
                wx = tx * T + wrng.ri(0, T - 7); wy = ty * T + wrng.ri(1, T - 2)
                ln = wrng.ri(3, 6)
                roll = wrng.rf()
                col = WAVE_D if roll < 0.5 else (WAVE_L if roll < 0.86
                                                 else WAVE_L2)
                gd.rectangle([wx, wy, wx + ln, wy], fill=col + (255,))
            for _ in range(3):
                wx = tx * T + wrng.ri(0, T - 2); wy = ty * T + wrng.ri(0, T - 1)
                gd.point((wx, wy), fill=WAVE_D + (255,))
                gd.point((wx + 1, wy), fill=WAVE_L + (255,))
    srng = U.LCG(seed + "-swell")
    for ty in range(y0, y1 + 1):
        y_px = ty * T + srng.ri(3, 12)
        n_seg = 5 + srng.n() % 4
        for _ in range(n_seg):
            sx = srng.ri(x0 * T, max(x0 * T + 4, (x1 + 1) * T - 20))
            sl = srng.ri(6, 16)
            y_j = y_px + srng.ri(-2, 2)
            col = SWELL_C if srng.rf() < 0.78 else WAVE_L
            gd.rectangle([sx, y_j, sx + sl, y_j], fill=col + (255,))

def shoreline_foam(gd, x0, x1, y_row, seed):
    """Foam scallops along a horizontal land->sea waterline (proven recipe)."""
    hrng = U.LCG(seed)
    for tx in range(x0, x1 + 1):
        fy0 = y_row * T + 1 + hrng.ri(0, 2)
        gd.rectangle([tx * T + hrng.ri(0, 3), fy0,
                      tx * T + 9 + hrng.ri(0, 5), fy0], fill=FOAM_A + (215,))
        if hrng.rf() < 0.5:
            gd.rectangle([tx * T + hrng.ri(2, 6), fy0 + 3,
                          tx * T + 6 + hrng.ri(2, 7), fy0 + 3],
                         fill=FOAM_B + (150,))

def mist_band(gd, x0, y0, x1, y1, seed, ramp="down", dens=(2, 9)):
    """Horizon mist = dithered OPAQUE dashes in sheet-sampled light hues
    (density gradient does the fade — no alpha wash, no flat band; ~1 in 5
    dashes may be a soft alpha accent, keeping foreign mass tiny)."""
    mr = U.LCG(seed)
    rows = max(1, y1 - y0)
    for ty in range(y0, y1 + 1):
        f = (ty - y0) / rows if ramp == "down" else 1.0 - (ty - y0) / rows
        n_row = int(dens[0] + f * (dens[1] - dens[0]))
        for tx in range(x0, x1 + 1):
            for _ in range(n_row):
                mx = tx * T + mr.ri(0, T - 8); my = ty * T + mr.ri(0, T - 1)
                ln = mr.ri(3, 8)
                col = MIST_HUES[mr.ri(0, len(MIST_HUES) - 1)]
                if mr.rf() < 0.06:
                    gd.rectangle([mx, my, mx + ln, my], fill=col + (170,))
                else:
                    gd.rectangle([mx, my, mx + ln, my], fill=col + (255,))
                if mr.rf() < 0.3:
                    gd.point((mx + mr.ri(0, ln), my + 1), fill=col + (255,))

def mist_pocket(gd, cx, cy, r_t, seed):
    """Reserved-slot mist pocket: clustered dashes densest at center."""
    mr = U.LCG(seed)
    for _ in range(int(r_t * r_t * 34)):
        dx = mr.ri(-r_t * T, r_t * T); dy = mr.ri(-r_t * T // 2, r_t * T // 2)
        d2 = (dx * dx + dy * dy * 4) / float(r_t * T * r_t * T)
        if d2 > 1.0 or mr.rf() < d2 * 0.72:
            continue
        ln = mr.ri(4, 9)
        col = MIST_HUES[mr.ri(0, len(MIST_HUES) - 1)]
        gd.rectangle([cx * T + dx, cy * T + dy, cx * T + dx + ln, cy * T + dy],
                     fill=col + (255 if mr.rf() > 0.2 else 170,))
        if mr.rf() < 0.4:
            gd.rectangle([cx * T + dx + 2, cy * T + dy + 1,
                          cx * T + dx + 2 + mr.ri(2, 5), cy * T + dy + 1],
                         fill=col + (255,))

def fence_pen(sc, x0, y0, x1, y1, ghost=False):
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            if x0 < tx < x1 and y0 < ty < y1:
                continue
            cx = 0 if tx == x0 else (2 if tx == x1 else 1)
            cy = 0 if ty == y0 else (2 if ty == y1 else 1)
            im = U.cut(U.FEN, 12 + cx, 6 + cy)
            if ghost:
                im = im.copy()
                gray = im.convert("LA").convert("RGBA")
                im = Image.blend(im, gray, 0.62)
                al = im.split()[3].point(lambda v: int(v * 0.62))
                im.putalpha(al)
            sc.ent(im, tx, ty, bias=0.02)

def tan_wear(sc, cells, seed):
    trng = U.LCG(seed)
    tand = ImageDraw.Draw(sc.ground)
    for (tx, ty) in sorted(cells):
        if trng.rf() < 0.85:
            wx = tx * T + trng.ri(1, 11); wy = ty * T + trng.ri(1, 13)
            tand.rectangle([wx, wy, wx + trng.ri(1, 4), wy],
                           fill=(TAN_DK if trng.rf() < 0.7 else TAN_LT) + (255,))
        for _ in range(trng.ri(1, 3)):
            wx = tx * T + trng.ri(2, 12); wy = ty * T + trng.ri(2, 12)
            tand.point((wx, wy), fill=TAN_LT + (255,))
            tand.point((wx + 1, wy), fill=TAN_DK + (255,))

def quay_stone(sc, gd, x0, x1, y0, y1, seed, tufts=True):
    """Working-wharf pavement + joints + flecks + lip (proven recipe)."""
    sw1 = U.sh(U.SW1).crop((0, 0, T, T))
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            sc.ground.paste(sw1, (tx * T, ty * T))
    jrng = U.LCG(seed)
    for tx in range(x0, x1 + 1):
        if jrng.rf() < 0.95:
            jx = tx * T + jrng.ri(2, 13)
            jy0 = y0 * T + jrng.ri(0, 8)
            gd.rectangle([jx, jy0, jx, min(jy0 + jrng.ri(6, 16), y1 * T + 14)],
                         fill=ST_DK + (255,))
        if jrng.rf() < 0.9:
            jy = y0 * T + jrng.ri(4, (y1 - y0 + 1) * T - 8)
            jx0 = tx * T + jrng.ri(0, 6)
            gd.rectangle([jx0, jy, jx0 + jrng.ri(5, 12), jy], fill=ST_DK + (255,))
        for ty in range(y0, y1 + 1):
            for _ in range(jrng.ri(3, 5)):
                fx = tx * T + jrng.ri(0, T - 2); fy = ty * T + jrng.ri(0, T - 2)
                if jrng.rf() < 0.6:
                    gd.point((fx, fy), fill=ST_DK + (255,))
                    gd.point((fx + 1, fy), fill=ST_DK + (255,))
                else:
                    gd.point((fx, fy), fill=ST_LT + (255,))
        if tufts and jrng.rf() < 0.25:
            sc.gpaste(U.sh(U.CS("Grass_Tufts_Flowers_16x16_%d" % jrng.ri(1, 11))),
                      tx, y0)
    gd.rectangle([x0 * T, y1 * T + 14, (x1 + 1) * T - 1, y1 * T + 15],
                 fill=ST_DK + (255,))

def tide_foam(gd, x0, x1, sea_y, seed, n=60):
    gd.rectangle([x0 * T, sea_y * T, (x1 + 1) * T - 1, sea_y * T + 2],
                 fill=(38, 52, 72, 160))
    frng = U.LCG(seed)
    for _ in range(n):
        fx = frng.ri(x0 * T, (x1 + 1) * T - 8); fl = frng.ri(2, 6)
        fy = sea_y * T + 3 + frng.ri(0, 6)
        gd.rectangle([fx, fy, fx + fl, fy],
                     fill=FOAM_A + (210,) if frng.rf() < 0.7 else FOAM_B + (150,))

def planks(sc, gd, cells):
    plank = U.tile(U.PLANK)
    for (tx, ty) in sorted(cells):
        sc.ground.paste(plank, (tx * T, ty * T))
    for (tx, ty) in sorted(cells):
        if (tx - 1, ty) not in cells:
            gd.rectangle([tx * T, ty * T, tx * T, ty * T + 15], fill=PIEREDG + (255,))
        if (tx + 1, ty) not in cells:
            gd.rectangle([tx * T + 15, ty * T, tx * T + 15, ty * T + 15],
                         fill=PIEREDG + (255,))
        if (tx, ty + 1) not in cells:
            gd.rectangle([tx * T, ty * T + 15, tx * T + 15, ty * T + 15],
                         fill=PIEREDG + (255,))

def pier_posts(gd, pts):
    for (px0, py0) in pts:
        gd.rectangle([px0, py0, px0 + 1, py0 + 5], fill=WOODDKR + (255,))
        gd.rectangle([px0 - 1, py0 + 5, px0 + 2, py0 + 6], fill=FOAM_B + (150,))

def flagpole(bare=True):
    """Drawn pole in proven wood browns; bare = pre-first-keyframe egg state."""
    im = Image.new("RGBA", (10, 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([4, 3, 5, 27], fill=WOODDK + (255,))
    d.rectangle([4, 3, 4, 27], fill=WOODMID + (255,))
    d.rectangle([3, 26, 6, 29], fill=WOODDKR + (255,))
    d.rectangle([3, 1, 6, 3], fill=WOODMID + (255,))
    d.point((4, 0), fill=CREAM + (255,))
    if not bare:
        d.polygon([(6, 4), (9, 5), (6, 7)], fill=CREAM + (255,))
    return im

def lantern_cairn():
    """Dark lantern SEATED on shore boulders — lighthouse t0 (honest-zero)."""
    rb = U.sh(U.P("Rock_Big")); rm = U.sh(U.P("Rock_Medium"))
    W_, H_ = rb.width + 12, rb.height + 16
    cv = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    cv.alpha_composite(rb, (0, H_ - rb.height))
    cv.alpha_composite(rm, (W_ - rm.width - 1, H_ - rm.height + 2))
    d = ImageDraw.Draw(cv)
    lx = rb.width // 2
    rock_top = H_ - rb.height
    ly1 = rock_top + 3                       # base plate bites into the rock
    ly0 = ly1 - 10
    d.rectangle([lx - 4, ly0, lx + 4, ly1], fill=DKLAMP + (255,),
                outline=DKLAMP3 + (255,))
    d.rectangle([lx - 2, ly0 + 2, lx + 2, ly1 - 3], fill=DKLAMP2 + (255,))
    d.point((lx - 2, ly0 + 3), fill=(58, 68, 92, 255))
    d.rectangle([lx - 5, ly1, lx + 5, ly1 + 1], fill=DKLAMP3 + (255,))
    d.rectangle([lx - 1, ly0 - 3, lx, ly0], fill=DKLAMP3 + (255,))
    return cv

def scaffold_site(w_px=56, h_px=58):
    """Great-work RAISING phase: wooden scaffold frame around a half-built
    masonry wall (GCONDO fragment). Browns sampled from the fence sheet."""
    cv = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
    wall = U.sh(U.GCONDO)
    frag = wall.crop((0, wall.height - 34, min(w_px - 10, wall.width),
                      wall.height))
    cv.alpha_composite(frag, (5, h_px - frag.height))
    d = ImageDraw.Draw(cv)
    for lx in (1, w_px // 2 - 1, w_px - 3):        # standards
        d.rectangle([lx, 3, lx + 1, h_px - 1], fill=FBR_D + (255,))
        d.rectangle([lx, 3, lx, h_px - 1], fill=FBR_M + (255,))
    for ly in (5, 20, 36):                         # ledgers + peg shadows
        d.rectangle([1, ly, w_px - 2, ly + 1], fill=FBR_M + (255,))
        for px in range(3, w_px - 3, 7):
            d.point((px, ly + 2), fill=FBR_D + (255,))
    bl = U.sh(U.P("Wood_Board"))                   # work platforms both lifts
    cv.alpha_composite(bl, (w_px // 2 - bl.width // 2, 20 - bl.height + 5))
    cv.alpha_composite(bl, (w_px - bl.width - 4, 36 - bl.height + 5))
    for i in range(0, w_px // 2 - 4, 2):           # diagonal brace
        d.point((2 + i, 18 - (i * 12) // max(1, w_px // 2 - 4)),
                fill=FBR_D + (255,))
        d.point((w_px // 2 + 1 + i, 34 - (i * 12) // max(1, w_px // 2 - 4)),
                fill=FBR_D + (255,))
    return cv

def telegraph_pole():
    im = Image.new("RGBA", (12, 26), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([5, 2, 6, 24], fill=WOODDK + (255,))
    d.rectangle([5, 2, 5, 24], fill=WOODMID + (255,))
    d.rectangle([1, 4, 10, 5], fill=WOODDK + (255,))
    for px in (1, 5, 9):
        d.point((px, 3), fill=CREAM + (255,))
    d.rectangle([4, 24, 7, 25], fill=WOODDKR + (255,))
    return im

def lantern_post(lit=False):
    im = Image.new("RGBA", (8, 22), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([3, 6, 4, 20], fill=WOODDK + (255,))
    d.rectangle([3, 6, 3, 20], fill=WOODMID + (255,))
    d.rectangle([2, 19, 5, 21], fill=WOODDKR + (255,))
    d.rectangle([1, 1, 6, 6], fill=DKLAMP + (255,), outline=DKLAMP3 + (255,))
    if lit:
        d.rectangle([2, 2, 5, 5], fill=LAMP_Y + (255,))
        d.point((3, 3), fill=CREAM + (255,))
    else:
        d.rectangle([2, 2, 5, 5], fill=DKLAMP2 + (255,))
    return im

def lighthouse_lit():
    """Proven lighthouse body, lamp LIT (first graduation earned — grown era).
    Warm hues = proven pin yellow + cream; tiny opaque sparkle halo."""
    cv = U.build_lighthouse()
    d = ImageDraw.Draw(cv)
    W_ = cv.width
    lx = W_ // 2
    by = None
    px = cv.load()
    for yy in range(cv.height):          # find the dark lamp head top
        for xx in range(cv.width):
            if px[xx, yy][3] > 0:
                by = yy; break
        if by is not None: break
    top = by if by is not None else 0
    d.rectangle([lx - 5, top + 3, lx + 4, top + 13], fill=DKLAMP + (255,),
                outline=DKLAMP3 + (255,))
    d.rectangle([lx - 3, top + 5, lx + 2, top + 11], fill=LAMP_Y + (255,))
    d.rectangle([lx - 1, top + 6, lx, top + 8], fill=CREAM + (255,))
    hal = U.LCG("halo")
    for (hx, hy) in [(-8, 6), (7, 7), (-7, 12), (6, 12), (0, -2), (-4, 0), (3, -1)]:
        d.rectangle([lx + hx, top + hy, lx + hx + hal.ri(1, 2), top + hy],
                    fill=LAMP_Y + (255,))
    return cv

def grey_buoy():
    im = Image.new("RGBA", (8, 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(1, 11), (6, 11), (5, 5), (2, 5)], fill=ASH_M + (255,))
    d.rectangle([3, 2, 4, 5], fill=ASH_D + (255,))
    d.rectangle([2, 7, 5, 8], fill=ASH_L + (255,))
    return im

def red_buoy():
    im = Image.new("RGBA", (8, 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(1, 11), (6, 11), (5, 5), (2, 5)], fill=RED_BY + (255,))
    d.rectangle([3, 2, 4, 5], fill=WOODDK + (255,))
    d.rectangle([2, 7, 5, 8], fill=CREAM + (255,))
    return im

def cargo_boat(direction="down"):
    """Packet boat with deck cargo (proven carrier trick at ship scale)."""
    b = U.sh(U.BOAT)
    if direction == "up":
        b = b.transpose(Image.FLIP_TOP_BOTTOM)
    b = b.copy()
    box = U.sh(U.P("Box_Single")).crop((2, 4, 14, 14))
    b.alpha_composite(box, (b.width // 2 - 6, b.height // 2 - 4))
    return b

def boat_wake(heading="down"):
    wake = Image.new("RGBA", (40, 26), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wake)
    rng_ = range(2, 24, 5) if heading == "down" else range(18, 2, -5)
    for i, wy in enumerate(rng_):
        a = 175 - i * 38
        wd.rectangle([14 - i * 3, wy, 17 - i * 3, wy], fill=FOAM_B + (max(a, 30),))
        wd.rectangle([22 + i * 3, wy + 1, 25 + i * 3, wy + 1],
                     fill=FOAM_B + (max(a, 30),))
    return wake

def sea_lane(gd, p0, p1, seed, dash_every=13):
    """Wake-dash shipping lane between two px points (broken, honest-light).
    Pair-dash: light crest over a dark shadow line — reads at LOD zoom."""
    lr = U.LCG(seed)
    x0, y0 = p0; x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    dist = max(abs(dx), abs(dy), 1)
    steps = dist // dash_every
    for i in range(steps + 1):
        f = i / max(steps, 1)
        px = int(x0 + dx * f) + lr.ri(-3, 3)
        py = int(y0 + dy * f) + lr.ri(-2, 2)
        ln = lr.ri(4, 7)
        col = WAVE_L if lr.rf() < 0.8 else WAVE_L2
        gd.rectangle([px, py + 1, px + ln - 1, py + 1], fill=WAVE_D + (255,))
        gd.rectangle([px, py, px + ln, py], fill=col + (255,))
        if lr.rf() < 0.5:
            gd.rectangle([px + 3, py + 2, px + 3 + lr.ri(1, 3), py + 2],
                         fill=WAVE_D + (255,))

def surveyor_stakes(gd, x_px, y_px, seed):
    sr = U.LCG(seed)
    for i in range(4):
        sx = x_px + [0, 18, 2, 20][i] + sr.ri(-1, 1)
        sy = y_px + [0, 2, 12, 13][i]
        gd.rectangle([sx, sy, sx, sy + 4], fill=WOODDK + (255,))
        gd.point((sx, sy), fill=CHALK + (255,))
    gd.rectangle([x_px + 2, y_px + 3, x_px + 17, y_px + 3], fill=CHALK + (190,))
    gd.rectangle([x_px + 3, y_px + 13, x_px + 18, y_px + 13], fill=CHALK + (190,))

def smoke_at(sc, px_, py_, alpha=0.8):
    smf = U.trim(U.sh(U.SMOK).crop((4 * 48, 0, 5 * 48, 58))).copy()
    smf.putalpha(smf.split()[3].point(lambda v: int(v * alpha)))
    sc.vfx(smf, px_, py_ - smf.height)

def pennant(sc, px_, py_):
    pn = Image.new("RGBA", (10, 12), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pn)
    pd.rectangle([0, 0, 0, 11], fill=WOODMID + (255,))
    pd.polygon([(1, 1), (8, 2), (1, 4)], fill=CREAM + (255,))
    pd.polygon([(1, 5), (8, 6), (1, 8)], fill=CREAM + (255,))
    sc.vfx(pn, px_, py_)

def ring_forest(sc, segs, seed):
    """Tree wall segments: list of (x0,x1,y,kinds,step) — staggered."""
    wr = U.LCG(seed)
    kindmap = {"mix": None, "shore": ["oakM", "oakS", "pineM"],
               "shallow": ["oakM", "oakL"], "tall": ["oakXL", "oakL", "pineM"]}
    for (x0, x1, yy, kk, step) in segs:
        x = float(x0)
        while x < x1:
            kinds = kindmap.get(kk)
            names = kinds or ["oakXL", "oakL", "oakL", "oakM", "pineM", "oakXL"]
            im = U.tree(wr.pick(names))
            px2, py2 = sc.ent(im, x + wr.ri(-1, 1) * 0.4, yy + wr.ri(0, 1),
                              bias=-0.05)
            sc.shadow_blob(px2 + im.width // 2, int((yy + 1) * T) - 5,
                           im.width - 18, 26)
            x += step

def isle_blob(sc, x0, y0, x1, y1, seed):
    cells = U.rect(x0, y0, x1, y1)
    irng = U.LCG(seed)
    for x in range(x0, x1 + 1):
        if irng.rf() < 0.5: cells.discard((x, y0))
        if irng.rf() < 0.5: cells.discard((x, y1))
    for y in range(y0, y1 + 1):
        if irng.rf() < 0.4: cells.discard((x0, y))
        if irng.rf() < 0.4: cells.discard((x1, y))
    U.paint_blob(sc.ground, cells, U.MOD_FOAM)
    grass = U.tile(U.GRASS)
    gv2 = [U.tile(s) for s in U.GRASS_V]
    heart = U.rect(x0 + 1, y0 + 1, x1 - 1, y1 - 1)
    for (hx, hy) in sorted(heart):
        if (hx, hy) in cells:
            sc.gpaste(grass, hx, hy)
    gd = ImageDraw.Draw(sc.ground)
    for (hx, hy) in sorted(heart):
        if (hx, hy) in cells:
            if irng.rf() < 0.5:
                sc.gpaste(gv2[irng.ri(0, 3)], hx, hy)
            for _ in range(irng.ri(2, 4)):
                fx = hx * T + irng.ri(0, T - 2); fy = hy * T + irng.ri(0, T - 3)
                col = G_DK if irng.rf() < 0.6 else G_LT
                gd.rectangle([fx, fy, fx, fy + 1], fill=col + (255,))
    return cells

def officer(sc, n, kind, d, tx, ty, frame=1, chipl=None):
    im = {"idle": U.c_idle, "walk": U.c_walk}[kind](n, d, frame)
    px_, py_ = sc.ent(im, tx, ty)
    sc.shadow_blob(px_ + 8, int((ty + 1) * T) - 2, 12, 34)
    if chipl:
        chip = U.thought_chip(chipl)
        sc.vfx(chip, px_ + 8 - chip.width // 2, py_ - chip.height - 2)
    return px_, py_

# ================================================================ STAGE 1: EGG
def build_egg():
    W_, H_ = 38, 29
    sc = U.Scene(W_, H_)
    SEA0 = 23
    gd = ImageDraw.Draw(sc.ground)

    paint_grass(sc, 0, 0, W_ - 1, SEA0 - 1, "egg-grass", daub_div=4)
    paint_sea(sc, 0, SEA0, W_ - 1, H_ - 1, "egg-sea", dash_lo=9, dash_hi=13)
    shoreline_foam(gd, 0, W_ - 1, SEA0, "egg-shore")
    tide_foam(gd, 0, W_ - 1, SEA0, "egg-tide", n=46)

    # dirt path: cottage door -> jetty head (the egg's ONE street)
    path = U.carve_path([(17, 10), (17, 14), (18, 18), (17, 22)])
    sc.gtiles(U.autotile(path, U.TAN, fillp=0.75))
    tan_wear(sc, path, "egg-wear")

    # clearing dressing: felled logs + boards (trees were cut ON SCREEN, §3.4)
    # fresh-cut ground at the felling sites (young clearing, worked earth)
    sc.gtiles(U.autotile(U.rect(11, 8, 12, 9), U.MULCH, fillp=0.5))
    sc.gtiles(U.autotile(U.rect(23, 13, 24, 14), U.MULCH, fillp=0.5))
    sc.gtiles(U.autotile(U.rect(20, 8, 22, 9), U.MULCH, fillp=0.5))
    sc.ent(U.sh(U.P("Trunk_Big_1")), 11.5, 8.2, prop="prop")
    sc.ent(U.sh(U.P("Trunk_Big_2")), 24.4, 13.6, prop="prop")
    sc.ent(U.sh(U.P("Wood_Board_Load")), 20.6, 9.4, prop="prop")
    sc.ent(U.sh(U.P("Rock_Small")), 13.2, 15.8, prop="prop")

    # the cottage (Great House at t0 — same identity, it GROWS)
    cot = U.sh(U.P("Chicken_Coop"))
    px_, py_ = sc.ent(cot, 15.0, 7.4, bias=-0.2)
    sc.shadow_blob(px_ + cot.width // 2, int(8.4 * T) - 4, cot.width - 10, 26)

    # water-ladder t0 (Captain addendum 1): ONE empty bucket by the cottage —
    # the memory/context reservoir at birth (bucket -> barrel -> tank -> tower)
    bk = U.sh(U.P("Bucket_1_Single"))
    px_, py_ = sc.ent(bk, 14.35, 9.6, bias=0.1, prop="prop")
    sc.shadow_blob(px_ + bk.width // 2, int(10.6 * T) - 6, bk.width - 4, 22)

    # bare flagpole (no keyframe yet) + mailbox flag DOWN (no pending items)
    fp = flagpole(bare=True)
    px_, py_ = sc.ent(fp, 19.6, 7.9)
    sc.shadow_blob(px_ + 5, int(8.9 * T) - 4, 10, 26)
    mb = U.mailbox(False)
    px_, py_ = sc.ent(mb, 18.8, 11.8, bias=0.1, prop="prop")
    sc.shadow_blob(px_ + 8, int(12.8 * T) - 6, 14, 30)

    # rowboat jetty (Lantern Quay t0)
    jt = U.rect(17, SEA0, 18, SEA0 + 2)
    planks(sc, gd, jt)
    pier_posts(gd, [(17 * T - 2, (SEA0 + 2) * T + 8), (19 * T, (SEA0 + 2) * T + 8),
                    (17 * T - 2, SEA0 * T + 6), (19 * T, SEA0 * T + 6)])
    sc.ent(U.sh(U.BOAT), 19.3, 24.3)
    gd.rectangle([int(19.5 * T), int(25.6 * T), int(19.5 * T) + 8, int(25.6 * T)],
                 fill=FOAM_B + (150,))
    gd.rectangle([int(20.4 * T), int(25.9 * T), int(20.4 * T) + 5, int(25.9 * T)],
                 fill=FOAM_A + (170,))

    # dark lantern-cairn on the shore rock (lighthouse t0 — honest zero)
    lc = lantern_cairn()
    px_, py_ = sc.ent(lc, 26.8, 21.6, bias=-0.1)
    sc.shadow_blob(px_ + lc.width // 2, int(22.6 * T) - 4, lc.width - 10, 28)
    sc.ent(U.sh(U.P("Rock_Small")), 25.5, 22.1, prop="prop")

    # meadow tufts: sparse drifts in the clearing (young ground)
    rng = U.LCG("egg-tufts")
    for _ in range(122):
        tx, ty = rng.ri(9, 28), rng.ri(5, 20)
        if (tx, ty) in path: continue
        if rng.rf() < 0.8:
            sc.gpaste(U.sh(U.CS("Grass_Tufts_Flowers_16x16_%d" % rng.ri(1, 11))),
                      tx, ty)

    # FOREST: deep ring all around the clearing (egg is R=24 forest, §3.1)
    ring_forest(sc, [
        (-2, 39, -1, "mix", 1.7), (-1, 39, 0.8, "mix", 1.8),
        (-2, 38, 2.2, "tall", 2.0),
        (-2, 9, 3.6, "mix", 1.8), (-1, 8, 5.4, "mix", 1.9),
        (-2, 7, 7.6, "mix", 2.0), (-1, 6, 9.8, "shore", 2.0),
        (-2, 6, 12.0, "mix", 2.0), (-1, 5, 14.2, "shore", 2.1),
        (-2, 4, 16.4, "mix", 2.0), (-1, 4, 18.6, "shore", 2.2),
        (-2, 3, 20.4, "shore", 2.4),
        (30, 39, 3.6, "mix", 1.8), (31, 39, 5.4, "mix", 1.9),
        (31, 40, 7.6, "mix", 2.0), (32, 40, 9.8, "shore", 2.0),
        (32, 40, 12.0, "mix", 2.0), (33, 40, 14.2, "shore", 2.1),
        (33, 40, 16.4, "mix", 2.0), (34, 40, 18.6, "shore", 2.2),
        (35, 40, 20.4, "shore", 2.4),
        (10, 30, 2.6, "shallow", 2.6),          # inner north fringe
    ], "egg-ring")
    # inner accent trees hugging the clearing
    for (tx, ty, k) in [(8, 6, "oakM"), (7, 12, "pineM"), (9, 17, "oakS"),
                        (27, 7, "oakM"), (29, 12, "oakS"), (25, 17, "pineM"),
                        (12, 4, "oakS"), (22, 4, "oakM"), (28, 17.5, "oakS")]:
        im = U.tree(k)
        px2, py2 = sc.ent(im, tx, ty, bias=-0.05)
        sc.shadow_blob(px2 + im.width // 2, int((ty + 1) * T) - 5,
                       im.width - 16, 24)

    # mist beyond: horizon band ramping south + corner pockets (grey-unmeasured
    # made geographic — nothing has been looked at yet out there)
    mist_band(gd, 0, SEA0 + 2, W_ - 1, H_ - 1, "egg-mist", ramp="down",
              dens=(1, 9))
    mist_pocket(gd, 3, H_ - 2, 4, "egg-mp1")
    mist_pocket(gd, 34, H_ - 3, 4, "egg-mp2")

    return sc

# ============================================================= STAGE 2: TODAY
def build_today():
    W_, H_ = 50, 35
    sc = U.Scene(W_, H_)
    Q0, Q1 = 22, 26            # quay stone rows
    SEA0 = 27
    gd = ImageDraw.Draw(sc.ground)

    # full-frame grass base first (quay/sea overpaint it — no unpainted voids)
    paint_grass(sc, 0, 0, W_ - 1, H_ - 1, "td-grass")
    paint_sea(sc, 0, SEA0, W_ - 1, H_ - 1, "td-sea", dash_lo=8, dash_hi=12)

    # ---- headland SW (grass runs to the water, foam scallops)
    hrng = U.LCG("td-head")
    for tx in range(0, 6):
        for ty in range(Q0, SEA0):
            if hrng.rf() < 0.7:
                sc.gpaste(U.tile(U.GVAR), tx, ty)
    shoreline_foam(gd, 0, 5, SEA0, "td-headfoam")
    shoreline_foam(gd, 48, 49, SEA0, "td-headfoam-e")

    # ---- orchard NE (mulch + apple trees)
    orch = U.rect(38, 2, 47, 6)
    org = U.LCG("td-orch")
    for x in range(38, 48):
        if org.rf() < 0.55: orch.discard((x, 6))
        if org.rf() < 0.35: orch.discard((x, 2))
    sc.gtiles(U.autotile(orch, U.MULCH))

    # ---- plaza + road + paths
    plaza = U.rect(19, 8, 26, 11)
    road = U.carve_path([(24, 11), (24, 14), (24, 17), (24, 21)])
    paths = set()
    paths |= U.carve_path([(15, 9), (19, 9)])            # great house -> plaza
    paths |= U.carve_path([(26, 9), (29, 9)])            # plaza -> library
    paths |= U.carve_path([(22, 8), (22, 6), (24, 5)])   # plaza -> cottage lane
    paths |= U.carve_path([(26, 11), (30, 12), (33, 12)])# plaza -> garden
    paths |= U.carve_path([(19, 10), (14, 12), (10, 14)])# plaza -> barn yard
    paths |= U.carve_path([(36, 9), (39, 8), (41, 8)])   # library -> workshop
    paths |= U.carve_path([(41, 9), (42, 10)])           # workshop -> site
    tan = plaza | road | paths
    sc.gtiles(U.autotile(tan, U.TAN, fillp=0.75))
    sw2 = U.sh(U.SW2).crop((0, 0, T, T))
    for (tx, ty) in sorted(road):
        if tx in (24, 25) and 11 <= ty <= 21 and (tx + ty) % 2 == 0:
            ins = sw2.crop((2, 2, 14, 14))
            sc.ground.alpha_composite(ins, (tx * T + 2, ty * T + 2))
    tan_wear(sc, tan, "td-wear")

    # ---- kitchen garden E of plaza
    bed = U.plotbed(5, 3)
    for (bx_, by_, species, stage) in [(30, 11, "Cabbage", 4),
                                       (36, 11, "Cauliflower", 5)]:
        sc.gpaste(bed, bx_, by_)
        prng = U.LCG("td-plot%d" % bx_)
        for row in range(2):
            for col in range(3):
                s = U.crop_stage(species,
                                 min(max(stage + prng.ri(-1, 0), 1), 6))
                sc.ent(s, bx_ + 1 + col, by_ + 1 + row, dx=prng.ri(-1, 2),
                       dy=-3 - row, prop="crop")
    sc.ent(U.trim(U.sh(U.P("Scarecrow"))), 35.2, 11.6, bias=0.2, prop="prop")

    # (west field cut on the 50x35 frame — kitchen garden + paddock carry
    # the crop story; pens + barn cluster own the west midland)

    # ---- east paddock (soil + turnips)
    pad = U.rect(31, 16, 36, 17)
    sc.gtiles(U.autotile(pad, U.SOIL, fillp=0.5))
    prng2 = U.LCG("td-paddock")
    for i in range(6):
        if prng2.rf() < 0.6:
            sc.ent(U.crop_stage("Turnip", 2 + (i % 3)), 31.4 + i,
                   16.5 + (i % 2) * 0.7, dy=-2, prop="crop")

    # ---- mulch bare patches + hedgerows + drifts
    for (mx0, my0, mx1, my1) in [(20, 13, 21, 14), (28, 14, 29, 15),
                                 (17, 20, 18, 21)]:
        sc.gtiles(U.autotile(U.rect(mx0, my0, mx1, my1), U.MULCH, fillp=0.5))
    dgl = U.cut(U.PROP, 25, 2, 2, 1); dsl = U.cut(U.PROP, 30, 2, 2, 2)
    hedges = [(30, 14.0), (33, 19), (36, 15), (38, 19), (28, 20), (19, 19),
              (9, 12), (40, 14), (46, 16), (8, 20)]
    hrng2 = U.LCG("td-hedge")
    for (hx, hy) in hedges:
        sc.gpaste(dgl if int(hx + hy) % 3 else dsl, int(hx + hrng2.ri(-1, 1)),
                  int(hy))
    def drift(seed, x0, y0, x1, y1, centers, per, rad, p, avoid):
        dr = U.LCG(seed)
        for _ in range(centers):
            cx_ = dr.ri(x0, x1); cy_ = dr.ri(y0, y1)
            for _ in range(per):
                tx = cx_ + dr.ri(-rad, rad); ty = cy_ + dr.ri(-rad, rad)
                if x0 <= tx <= x1 and y0 <= ty <= y1 and (tx, ty) not in avoid \
                        and dr.rf() < p:
                    sc.gpaste(U.sh(U.CS("Grass_Tufts_Flowers_16x16_%d"
                                        % dr.ri(1, 11))), tx, ty)
    avoid = tan | pad | U.rect(9, 12, 18, 20) | U.rect(0, 14, 8, 22)
    avoid |= {(int(hx) + dx, int(hy) + dy) for (hx, hy) in hedges
              for dx in (-1, 0, 1, 2) for dy in (0, 1)}
    drift("td-dr-e", 27, 13, 40, 20, 24, 9, 2, 0.75, avoid)
    drift("td-dr-w", 19, 12, 23, 21, 12, 8, 2, 0.7, avoid)
    drift("td-dr-n", 8, 12, 18, 14, 8, 7, 2, 0.6, avoid)
    drift("td-dr-s", 2, 19, 22, 21, 12, 8, 2, 0.6, avoid)
    drift("td-dr-es", 41, 15, 47, 20, 8, 8, 2, 0.55, avoid)
    verge = U.rect(20, 15, 30, 20)
    vr = U.LCG("td-verge")
    for (tx, ty) in sorted(verge):
        if (tx, ty) in tan: continue
        if vr.rf() < 0.5:
            sc.gpaste(U.sh(U.CS("Grass_Tufts_Flowers_16x16_%d" % vr.ri(1, 11))),
                      tx, ty)

    # ================================================== village buildings
    house = U.sh(U.P("Farmer_House_1"))
    px_, py_ = sc.ent(house, 9, 10, bias=-0.3)
    sc.shadow_blob(px_ + house.width // 2, 11 * T - 5, house.width - 14, 30)
    smoke_at(sc, px_ + 88 - 10, py_ + 18)
    pennant(sc, px_ + 60, py_ - 2)

    lib = U.sh(U.P("Farmer_House_2"))
    px_, py_ = sc.ent(lib, 29, 8, bias=-0.3)
    sc.shadow_blob(px_ + lib.width // 2, 9 * T - 5, lib.width - 16, 30)
    sc.ent(U.sh(U.P("Box_Single")), 30.2, 8.6, prop="prop")
    sc.ent(U.sh(U.P("Box_Single")), 31.0, 8.4, dy=-3, prop="prop")

    shop = U.sh(U.P("Chicken_Coop"))
    px_, py_ = sc.ent(shop, 40, 6.6, bias=-0.2)
    sc.shadow_blob(px_ + shop.width // 2, int(7.6 * T) - 4, shop.width - 10, 26)
    sc.ent(U.sh(U.P("Woodwork_Crafting_Table_Full")), 44.3, 6.5, prop="prop")
    sc.ent(U.sh(U.P("DIY_Crafting_Table_Full")), 44.5, 8.2, prop="prop")
    sc.ent(U.sh(U.P("Wood_Board_Load")), 39.0, 7.9, prop="prop")

    # retro firepit (cold ash, honest)
    fp_cx, fp_cy = 21.0, 12.6
    ash = Image.new("RGBA", (26, 14), (0, 0, 0, 0))
    ad = ImageDraw.Draw(ash)
    ad.ellipse([0, 0, 25, 13], fill=ASH_M + (235,))
    ad.ellipse([5, 3, 19, 10], fill=ASH_D + (255,))
    ad.point((9, 6), fill=ASH_L + (255,)); ad.point((15, 7), fill=ASH_L + (255,))
    sc.ent(ash, fp_cx, fp_cy, prop="firepit")
    for (rx, ry) in [(-1.2, -0.4), (1.3, -0.5), (-1.4, 0.7), (1.5, 0.8)]:
        sc.ent(U.sh(U.P("Rock_Small")), fp_cx + rx, fp_cy + ry + 0.4)
    sc.ent(U.sh(U.P("Trunk_Big_1")), fp_cx - 1.6, fp_cy + 1.6, prop="prop")
    px_, py_ = sc.ent(U.c_read(7, "down", 1), fp_cx + 0.1, fp_cy + 1.5)
    sc.shadow_blob(px_ + 8, int((fp_cy + 2.5) * T) - 2, 12, 40)

    # law plot NW (clear of the barn/silo cluster)
    fence_pen(sc, 1, 1, 5, 3)
    sc.ent(U.sh(U.P("Sign_1")), 2.0, 2.2, prop="prop")
    sc.ent(U.sh(U.P("Sign_2")), 3.6, 2.4, prop="prop")
    sc.ent(U.sh(U.P("Rock_Small")), 1.4, 3.6, prop="prop")

    # cottage lane (4 roles)
    coop = U.sh(U.P("Chicken_Coop"))
    for i, cx_ in enumerate([18, 23, 28, 33]):
        px_, py_ = sc.ent(coop, cx_, 4.0 + (i % 2) * 0.4, bias=-0.2)
        sc.shadow_blob(px_ + coop.width // 2, int((5.0 + (i % 2) * 0.4) * T) - 4,
                       coop.width - 12, 24)
    sc.ent(U.sh(U.P("Dog_Bowl_Red_Full")), 19.2, 5.0, prop="prop")
    sc.ent(U.sh(U.P("Hay_Dry_Pile_Small")), 29.6, 4.6, prop="prop")

    # plaza props
    well = U.sh(U.P("Well_Usable"))
    px_, py_ = sc.ent(well, 21.2, 9.1, prop="prop")
    sc.shadow_blob(px_ + well.width // 2, int(10.1 * T) - 6, 40, 30)
    sc.ent(U.sh(U.BENCH), 24.4, 8.0, prop="prop")
    sc.ent(U.sh(U.LAMP), 19.8, 7.9, dx=-6, prop="prop")

    # barn (deep W, behind) + double-silo (front) + composter — no building
    # ever stands in another's sightline (Silos_1 is a 7-tile sprite)
    barn = U.sh(U.P("Barn_Small"))
    px_, py_ = sc.ent(barn, 0, 14.2, bias=-0.3)
    sc.shadow_blob(px_ + barn.width // 2, int(15.2 * T) - 5, barn.width - 14, 30)
    silo = U.sh(U.P("Silos_1"))
    px_, py_ = sc.ent(silo, 1.6, 20.8, bias=-0.3)
    sc.shadow_blob(px_ + silo.width // 2, int(21.8 * T) - 5, silo.width - 8, 30)
    sc.gtiles(U.autotile(U.rect(10, 12, 11, 13), U.SOIL))
    sc.ent(U.sh(U.P("Sack_Jute_Load_2")), 10.1, 12.8, prop="prop")
    cart = U.sh(U.P("Trunk_Load_Big_Vertical")).copy()
    gray = cart.convert("LA").convert("RGBA")
    cart = Image.blend(cart, gray, 0.55)
    sc.ent(cart, 12.4, 12.4, prop="prop")

    # pens SW of the crossroads: cow + chicken + ghost
    fence_pen(sc, 9, 17, 13, 20)
    fence_pen(sc, 14, 17, 18, 20)
    fence_pen(sc, 10, 14, 13, 16, True)
    sc.ent(U.sh(U.FE("Wooden_Fence_Type_3_Brown_Gate_1")), 11, 20, bias=0.03)
    sc.ent(U.sh(U.P("Cow_Sign")), 8.6, 20.7, prop="prop")
    sc.ent(U.sh(U.P("Chicken_Sign")), 13.8, 20.6, prop="prop")
    sc.ent(U.sh(U.P("Drinking_Trough_Horizontal_Full")), 10, 17.9, dy=-2,
           prop="prop")
    sc.ent(U.sh(U.P("Hay_Dry_Pile")), 12.2, 17.7, dy=-2, prop="prop")
    sc.ent(U.sh(U.P("Henhouse")), 15.4, 18.0, bias=-0.05, prop="prop")
    gsign = U.sh(U.P("Sign_Blank")).copy()
    al = gsign.split()[3].point(lambda v: int(v * 0.6))
    gsign.putalpha(al)
    sc.ent(gsign, 12.8, 16.4, prop="prop")
    for (cx_, cy_, k, i, dd) in [(9.6, 19.2, "graze", 0, 0),
                                 (11.4, 18.4, "idle", 2, 0)]:
        c = U.cow_f(k, i, dd)
        px_, py_ = sc.ent(c, cx_, cy_)
        sc.shadow_blob(px_ + 24, int((cy_ + 1) * T) - 4, 30, 30)
    for (cx_, cy_, k, wh) in [(14.8, 18.4, "peck", False),
                              (16.8, 19.4, "idle", False),
                              (15.4, 19.8, "walk", True)]:
        sc.ent(U.chick(k, 0, wh), cx_, cy_, bias=0.06)

    # orchard trees
    def fruit(nm, tx, ty):
        im = U.trim(U.sh(U.FR(nm)))
        px2, py2 = sc.ent(im, tx, ty, bias=-0.1)
        sc.shadow_blob(px2 + im.width // 2, int((ty + 1) * T) - 4,
                       im.width - 20, 28)
    fruit("Fruit_Tree_Apple_Ripe_Big", 39, 3.4)
    fruit("Fruit_Tree_Apple_Ripe", 42.4, 2.2)
    fruit("Fruit_Tree_Apple_Ripe_Big", 45.6, 3.9)
    fruit("Fruit_Tree_Apple_Ripe", 41.0, 5.4)
    sc.ent(U.sh(U.FR("Basket_Apple")), 40.4, 4.8, prop="prop")

    # ============ THE CONSTRUCTION SITE (visible work, D4) ============
    # great work at the village E edge: crew cleared trees (felled trunks ON
    # SCREEN at the tree line), scaffold + masonry rising, wright crew RAISING
    lot = U.rect(42, 10, 46, 13)
    sc.gtiles(U.autotile(lot, U.MULCH, fillp=0.5))
    # felled trunks + fresh logs at the tree line (CLEARING evidence)
    sc.ent(U.sh(U.P("Trunk_Big_2")), 45.6, 13.2, prop="prop")
    sc.ent(U.sh(U.P("Trunk_Big_1")), 42.2, 13.5, prop="prop")
    sc.ent(U.sh(U.P("Trunk_Big_2")), 47.0, 11.4, prop="prop")
    sc.ent(U.sh(U.P("Wood_Board_Load")), 41.8, 11.0, prop="prop")
    sc.ent(U.sh(U.P("Sack_Jute_Load_1")), 46.4, 12.0, prop="prop")
    # scaffold + half-built wall
    scaf = scaffold_site()
    px_, py_ = sc.ent(scaf, 43.0, 10.2, bias=-0.1)
    sc.shadow_blob(px_ + scaf.width // 2, int(11.2 * T) - 4, scaf.width - 12, 26)
    # site sign (WHAT/NOW/PROOF lives on the card; sign marks the site)
    sc.ent(U.sh(U.P("Sign_1")), 41.6, 12.6, prop="prop")
    # the crew: one wright hammering at the frame, one hauling from the trees
    officer(sc, 12, "idle", "up", 43.8, 11.9)
    hauler = U.c_walk(15, "left", 2).copy()
    bl = U.sh(U.P("Wood_Board")).crop((0, 0, 14, 8))
    hauler.alpha_composite(bl, (1, 13))
    px_, py_ = sc.ent(hauler, 45.8, 12.5)
    sc.shadow_blob(px_ + 8, int(13.5 * T) - 2, 12, 34)
    # sawhorse + crate
    sc.ent(U.sh(U.P("Woodwork_Crafting_Table")), 44.8, 13.7, prop="prop")
    sc.ent(U.sh(U.P("Crate_Brown_Empty")), 46.2, 10.6, prop="prop")

    # ============ crossroads (mailbox flag UP + noticeboard + kiosk)
    mb = U.mailbox(True, pips=2)
    px_, py_ = sc.ent(mb, 23.2, 16.6, bias=0.1, prop="prop")
    sc.shadow_blob(px_ + 8, int(17.6 * T) - 6, 14, 30)
    nb = U.noticeboard()
    px_, py_ = sc.ent(nb, 20.6, 15.8, prop="prop")
    sc.shadow_blob(px_ + nb.width // 2, int(16.8 * T), 40, 28)
    kiosk = U.sh(U.P("Market_Stand_Yellow_Small"))
    px_, py_ = sc.ent(kiosk, 27.0, 18.6, prop="prop")
    sc.shadow_blob(px_ + kiosk.width // 2, int(19.6 * T) - 4, kiosk.width - 8, 26)
    sc.ent(U.sh(U.BLUE), 29.8, 18.4, prop="prop")
    sc.ent(U.sh(U.LAMP), 19.6, 18.1, dx=-6, prop="prop")
    dgs = U.dog_sleep(0)
    px_, py_ = sc.ent(dgs, 20.6, 17.9)
    sc.shadow_blob(px_ + 22, int(18.9 * T) - 6, 24, 26)
    officer(sc, 4, "walk", "down", 24.35, 15.4, chipl=["I SHOULD", "SHIP THIS"])

    # ============ quay (rows Q0..Q1)
    quay_stone(sc, gd, 6, 46, Q0, Q1, "td-quay")
    tide_foam(gd, 6, 46, SEA0, "td-tide", n=70)

    # warehouse on the wharf W
    roof_wh = U.sh(U.ROOF2).crop((0, U.sh(U.ROOF2).height - 44,
                                  U.sh(U.ROOF2).width, U.sh(U.ROOF2).height))
    ware = U.build_stack([U.crop_w(roof_wh, 6 * T), U.crop_w(U.sh(U.GCONDO), 6 * T)])
    px_, py_ = sc.ent(ware, 7.6, 24.8, bias=-0.3)
    sc.shadow_blob(px_ + ware.width // 2, int(25.8 * T) - 6, ware.width - 14, 30)
    for i, (dx0, dy0) in enumerate([(0, 0), (1.15, 0.1), (0.5, -0.75),
                                    (1.7, -0.6), (1.05, -1.4)]):
        sc.ent(U.sh(U.P("Crate_Dark_Brown_Empty" if i % 2 else "Crate_Brown_Empty")),
               5.4 + dx0, 24.4 + dy0, prop="prop")
    sc.ent(U.cut(U.PROP, 24, 6, 2, 2), 13.9, 24.2, prop="prop")
    sc.ent(U.cut(U.PROP, 24, 4, 1, 2), 14.7, 23.5, prop="prop")

    # harbormaster hut E of road mouth
    roof_eave = U.sh(U.ROOF2).crop((0, U.sh(U.ROOF2).height - 28,
                                    U.sh(U.ROOF2).width, U.sh(U.ROOF2).height))
    hut = U.build_stack([U.crop_w(roof_eave, 4 * T), U.crop_w(U.sh(U.GCONDO), 4 * T)])
    px_, py_ = sc.ent(hut, 26.5, 23.2, bias=-0.3)
    sc.shadow_blob(px_ + hut.width // 2, int(24.2 * T) - 5, hut.width - 12, 30)
    officer(sc, 1, "idle", "up", 27.6, 24.1)
    sc.ent(U.sh(U.BENCH), 30.6, 23.6, prop="prop")

    # berths: chalk + cleats + lane-grouped cargo (6 active outcomes)
    berth_xs = [(15.5, 3), (18.5, 2), (31.0, 4), (34.3, 5), (38.1, 3), (41.4, 3)]
    for i, (bx_, stg) in enumerate(berth_xs):
        by_ = 23.1 if i % 2 == 0 else 23.4
        x0, y0 = int(bx_ * T) - 3, int(by_ * T) + 6
        x1, y1 = int(bx_ * T) + 3 * T + 9, int(by_ * T) + 3 * T + 4
        for xx in range(x0, x1, 4):
            gd.rectangle([xx, y0, xx + 1, y0], fill=CHALK + (190,))
            gd.rectangle([xx, y1, xx + 1, y1], fill=CHALK + (190,))
        for yy in range(y0, y1, 4):
            gd.rectangle([x0, yy, x0, yy + 1], fill=CHALK + (190,))
            gd.rectangle([x1, yy, x1, yy + 1], fill=CHALK + (190,))
        cxp = int(bx_ * T) + 20
        gd.rectangle([cxp, Q1 * T + 10, cxp + 3, Q1 * T + 11],
                     fill=(40, 44, 58, 255))
        gd.rectangle([cxp + 1, Q1 * T + 8, cxp + 2, Q1 * T + 12],
                     fill=(58, 62, 78, 255))
        stk = U.berth_stack3(stg, "td-berth%d" % i)
        px_, py_ = sc.ent(stk, bx_, by_ + 1.6, prop="prop")
        sc.shadow_blob(px_ + stk.width // 2, int((by_ + 2.6) * T) - 6,
                       28 + 2 * stg, 26)
    sc.ent(U.sh(U.P("Crate_Brown_Empty")), 33.0, 25.7, prop="prop")
    officer(sc, 10, "idle", "up", 33.1, 26.3)

    # timber yard E (trimmed)
    wood = U.sh(U.P("Wood_Board_Load"))
    for (spx, yx, yy_) in [(wood, 43.6, 23.5), (U.cut(U.PROP, 24, 6, 2, 2), 45.2, 23.4),
                           (U.sh(U.P("Sack_Jute_Load_2")), 44.0, 24.6),
                           (U.sh(U.P("Crate_Dark_Brown_Empty")), 45.4, 24.7)]:
        sc.ent(spx, yx, yy_, prop="prop")
    sc.shadow_blob(int(44.8 * T), int(25.8 * T) - 6, 56, 22)

    # quay lamps rhythm
    for lx_ in (6.9, 14.6, 25.4, 31.9, 37.4, 42.9):
        sc.ent(U.sh(U.LAMP), lx_, Q0 - 0.6, dx=-6, prop="prop")

    # piers + dock
    piers = U.rect(21, SEA0, 22, 31) | U.rect(27, SEA0, 28, 31)
    dock = U.rect(6, SEA0, 7, 30)
    planks(sc, gd, piers | dock)
    pier_posts(gd, [(21 * T - 2, 31 * T + 8), (23 * T, 31 * T + 8),
                    (27 * T - 2, 31 * T + 8), (29 * T, 31 * T + 8),
                    (21 * T - 2, SEA0 * T + 6), (23 * T, SEA0 * T + 6),
                    (27 * T - 2, SEA0 * T + 6), (29 * T, SEA0 * T + 6),
                    (6 * T - 2, 30 * T + 8), (8 * T, 30 * T + 8)])
    boat_up_ = U.sh(U.BOAT).transpose(Image.FLIP_TOP_BOTTOM)
    px_, py_ = sc.ent(boat_up_, 8.2, 28.6)
    sc.vfx(boat_wake("down"), px_ - 4, py_ + boat_up_.height - 6)
    cour = U.c_walk(2, "up", 3).copy()
    cd_ = ImageDraw.Draw(cour)
    cd_.rectangle([2, 18, 5, 20], fill=CREAM + (255,))
    cd_.point((3, 19), fill=WOODMID + (255,))
    px_, py_ = sc.ent(cour, 24.9, 19.6)
    sc.shadow_blob(px_ + 8, int(20.6 * T) - 2, 12, 30)
    carrier = U.c_walk(3, "down", 1).copy()
    bxs = U.sh(U.P("Box_Single"))
    carrier.alpha_composite(bxs.crop((2, 4, 14, 14)), (2, 12))
    px_, py_ = sc.ent(carrier, 27.4, 28.2)
    sc.shadow_blob(px_ + 8, int(29.2 * T) - 2, 12, 30)
    sc.ent(U.sh(U.BOAT), 19.6, 28.9)
    out_b = U.sh(U.BOAT)
    px_, py_ = sc.ent(out_b, 33.0, 29.8)
    sc.vfx(boat_wake("up"), px_ - 4, py_ - 18)

    # breakwater arm + DARK lighthouse SE
    arm = ({(tx, 27) for tx in (45, 46, 47)} | {(tx, 28) for tx in (45, 46, 47)}
           | {(tx, 29) for tx in (44, 45, 46)} | {(tx, 30) for tx in (44, 45)})
    sw1 = U.sh(U.SW1).crop((0, 0, T, T))
    jr2 = U.LCG("td-arm")
    for (tx, ty) in sorted(arm):
        sc.ground.paste(sw1, (tx * T, ty * T))
        for _ in range(4):
            fx = tx * T + jr2.ri(0, T - 2); fy = ty * T + jr2.ri(0, T - 2)
            gd.point((fx, fy), fill=(ST_DK if jr2.rf() < 0.6 else ST_LT) + (255,))
    for (tx, ty) in sorted(arm):
        if (tx - 1, ty) not in arm:
            gd.rectangle([tx * T, ty * T, tx * T, ty * T + 15], fill=ST_DK + (255,))
        if (tx + 1, ty) not in arm and tx < 47:
            gd.rectangle([tx * T + 15, ty * T, tx * T + 15, ty * T + 15],
                         fill=ST_DK + (255,))
        if (tx, ty + 1) not in arm:
            gd.rectangle([tx * T, ty * T + 14, tx * T + 15, ty * T + 15],
                         fill=ST_DK + (255,))
    lh = U.build_lighthouse()
    px_, py_ = sc.ent(lh, 43.8, 29.0, bias=-0.2)
    sc.shadow_blob(px_ + lh.width // 2, int(30.0 * T) - 6, lh.width - 18, 34)
    sc.ent(U.sh(U.P("Rock_Medium")), 43.6, 29.8, prop="prop")
    sc.ent(U.sh(U.P("Rock_Small")), 44.8, 27.8, prop="prop")
    frng2 = U.LCG("td-pointfoam")
    for _ in range(10):
        fx = frng2.ri(43 * T, int(48.5 * T)); fy2 = frng2.ri(int(27.5 * T),
                                                            int(31.5 * T))
        gd.rectangle([fx, fy2, fx + frng2.ri(3, 7), fy2], fill=FOAM_C + (170,))

    # reef-buoy (retired stepnetwork anchor)
    sc.ent(red_buoy(), 23.7, 31.4)
    gd.rectangle([int(23.4 * T), int(32.5 * T), int(23.4 * T) + 10,
                  int(32.5 * T)], fill=FOAM_C + (150,))

    # ONE product isle offshore SE — IN HAZE (distance made honest)
    isle_cells = isle_blob(sc, 36, 31, 44, 34, "td-isle-polads")
    sc.ent(U.sh(U.P("Henhouse")), 38.2, 32.5)
    sc.ent(U.sh(U.P("Chicken_Coop")), 41.4, 33.0, bias=-0.1)
    sc.ent(U.tree("oakS"), 40.0, 31.7, bias=-0.05)
    sc.ent(U.sh(U.P("Box_Single")), 40.6, 33.8, prop="prop")
    plank = U.tile(U.PLANK)
    sc.ground.paste(plank, (39 * T, 34 * T))
    # haze around the isle: dense ring hugging the rim + lane ribbon (distance
    # made honest — the far isle sits in atmosphere, not crisp foreground)
    rim = {(cx2, cy2) for (cx2, cy2) in isle_cells
           if any((cx2 + dx, cy2 + dy) not in isle_cells
                  for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
    hr_ = U.LCG("td-hazering")
    for (cx2, cy2) in sorted(rim):
        for _ in range(hr_.ri(2, 4)):
            hx = cx2 * T + hr_.ri(-6, T + 2); hy = cy2 * T + hr_.ri(-4, T + 2)
            ln = hr_.ri(3, 7)
            col = MIST_HUES[hr_.ri(0, len(MIST_HUES) - 1)]
            gd.rectangle([hx, hy, hx + ln, hy],
                         fill=col + (255 if hr_.rf() > 0.25 else 170,))
    lane_h = U.LCG("td-haze")
    for _ in range(210):
        hx = lane_h.ri(30 * T, 46 * T); hy = lane_h.ri(int(30.5 * T), 35 * T - 4)
        if (hx // T, hy // T) in isle_cells and lane_h.rf() < 0.55:
            continue
        ln = lane_h.ri(3, 7)
        col = MIST_HUES[lane_h.ri(0, len(MIST_HUES) - 1)]
        gd.rectangle([hx, hy, hx + ln, hy],
                     fill=col + (255 if lane_h.rf() > 0.25 else 170,))
    sc.ent(grey_buoy(), 35.0, 32.6)

    # ducks near W pier
    for i, (tx, ty) in enumerate([(17.5, 29.0), (19, 30.0), (18, 31.0),
                                  (16.3, 29.8)]):
        df = U.duck_frame(i % 4, brown=(i == 3))
        px_, py_ = sc.ent(df, tx, ty)
        gd.rectangle([px_ + 2, int((ty + 1) * T) - 3, px_ + 13,
                      int((ty + 1) * T) - 3], fill=FOAM_B + (90,))

    # horizon mist far south
    mist_band(gd, 0, 33, W_ - 1, H_ - 1, "td-mist", ramp="down", dens=(1, 5))

    # tree ring N/W/E
    ring_forest(sc, [
        (-2, 51, -1, "mix", 2.0), (-1, 51, 0.8, "mix", 2.2),
        (-2, 5, 2.0, "mix", 2.4), (-1, 4, 4.4, "shore", 3.0),
        (-2, 3, 7.0, "mix", 2.6), (-1, 3, 10.0, "shore", 3.2),
        (-2, 2, 13.0, "mix", 2.8), (-1, 2, 16.0, "shore", 3.2),
        (-2, 2, 19.0, "shore", 3.0),
        (48, 51, 2.0, "mix", 2.2), (47.6, 51, 5.0, "shore", 2.8),
        (48, 51, 8.0, "mix", 2.6), (47.4, 51, 14.4, "shore", 3.0),
        (48, 51, 17.4, "shore", 3.0),
        (37, 48, 1.4, "shallow", 2.6),
    ], "td-ring")
    for (tx, ty, k) in [(26, 6.8, "oakS"), (7, 7, "oakS"), (37, 13, "oakS"),
                        (46, 12, "oakM"), (20, 12.6, "oakS")]:
        im = U.tree(k)
        px2, py2 = sc.ent(im, tx, ty, bias=-0.05)
        sc.shadow_blob(px2 + im.width // 2, int((ty + 1) * T) - 5,
                       im.width - 16, 24)

    return sc

# ============================================================= STAGE 3: GROWN
def coast_walk(seed, y0, y1, lo=0, hi=4, start=2):
    """Random-walk shoreline offset per row — organic coasts, deterministic."""
    rng = U.LCG(seed)
    off = {}
    cur = start
    for ty in range(y0, y1 + 1):
        cur = max(lo, min(hi, cur + rng.ri(-1, 1)))
        off[ty] = cur
    return off

def build_grown():
    W_, H_ = 120, 80
    sc = U.Scene(W_, H_)
    gd = ImageDraw.Draw(sc.ground)

    # ---- geography: main island x6..78, quay rows 37..41, open sea beyond
    LX0, LX1 = 6, 78
    Q0, Q1 = 37, 41
    QX0, QX1 = 12, 76
    SEA0 = 42

    land = U.rect(LX0, 0, LX1, Q1)
    offW = coast_walk("gr-coastW", 0, Q1, 1, 6, 4)
    offE = coast_walk("gr-coastE", 0, Q1, 1, 5, 3)
    for ty in range(0, Q1 + 1):
        for i in range(offW[ty]):
            land.discard((LX0 + i, ty))
        for i in range(offE[ty]):
            land.discard((LX1 - i, ty))
    paint_sea(sc, 0, 0, W_ - 1, H_ - 1, "gr-sea", two_tone=True,
              dash_lo=11, dash_hi=16, skip=land)
    # island grass: full 3-pass over land cells
    grass = U.tile(U.GRASS); gvar = U.tile(U.GVAR)
    gv2 = [U.tile(s) for s in U.GRASS_V]
    for (tx, ty) in sorted(land):
        sc.gpaste(grass, tx, ty)
    grng = U.LCG("gr-daub")
    for _ in range(620):
        cx_, cy_ = grng.ri(LX0, LX1), grng.ri(0, Q0 - 1)
        v = gv2[grng.ri(0, 3)]
        for _ in range(grng.ri(2, 5)):
            p = (cx_ + grng.ri(-2, 2), cy_ + grng.ri(-1, 1))
            if p in land:
                sc.gpaste(v, p[0], p[1])
    sp = U.LCG("gr-speck")
    for (tx, ty) in sorted(land):
        if sp.rf() < 0.85:
            sc.gpaste(gvar, tx, ty)
    fl = U.LCG("gr-fleck")
    for (tx, ty) in sorted(land):
        for _ in range(fl.ri(4, 7)):
            fx = tx * T + fl.ri(0, T - 2); fy = ty * T + fl.ri(0, T - 3)
            col = G_DK if fl.rf() < 0.62 else G_LT
            gd.rectangle([fx, fy, fx, fy + fl.ri(1, 2)], fill=col + (255,))
    # coast foam W/E edges
    for (tx, ty) in sorted(land):
        for (nx, side) in [(tx - 1, "w"), (tx + 1, "e")]:
            if (nx, ty) not in land and ty < Q0:
                fx = tx * T + (0 if side == "w" else 12)
                gd.rectangle([fx, ty * T + 2, fx + 3, ty * T + 2],
                             fill=FOAM_A + (200,))
                gd.rectangle([fx, ty * T + 9, fx + 3, ty * T + 9],
                             fill=FOAM_B + (160,))

    # ---- orchard NE
    orch = U.rect(64, 2, 76, 7)
    org = U.LCG("gr-orch")
    for x in range(64, 77):
        if org.rf() < 0.55: orch.discard((x, 7))
        if org.rf() < 0.35: orch.discard((x, 2))
    orch &= land
    sc.gtiles(U.autotile(orch, U.MULCH))

    # ---- plaza + road + connective paths EVERYWHERE
    plaza = U.rect(36, 10, 46, 14)
    road = U.carve_path([(46, 14), (46, 20), (46, 27), (46, 33), (46, 36)])
    paths = set()
    paths |= U.carve_path([(25, 12), (30, 11), (36, 11)])     # GH -> plaza
    paths |= U.carve_path([(46, 12), (50, 11), (52, 10)])     # plaza -> infirmary
    paths |= U.carve_path([(39, 10), (36, 7), (33, 6)])       # plaza -> lane W
    paths |= U.carve_path([(44, 10), (46, 7), (48, 6)])       # plaza -> mid E
    paths |= U.carve_path([(56, 6), (55, 9)])                 # E cottage -> infm
    paths |= U.carve_path([(55, 12), (57, 15)])               # library -> shop
    paths |= U.carve_path([(58, 17), (52, 20), (48, 20)])     # shop -> road
    paths |= U.carve_path([(36, 13), (30, 16), (24, 18), (18, 20)])  # -> barn
    paths |= U.carve_path([(13, 22), (12, 26), (12, 30)])     # barn -> fields
    paths |= U.carve_path([(46, 24), (49, 23), (51, 23)])     # road -> switchbd
    paths |= U.carve_path([(46, 31), (40, 32), (34, 33)])     # road -> W fields
    paths |= U.carve_path([(46, 30), (54, 30), (58, 30)])     # road -> E field
    paths |= U.carve_path([(21, 12), (16, 11), (13, 10)])     # GH -> law plot
    paths |= U.carve_path([(66, 7), (62, 10), (60, 13)])      # orchard -> shop
    paths |= U.carve_path([(30, 17), (30, 21)])               # green loop
    paths |= U.carve_path([(64, 18), (66, 24), (62, 29)])     # E meadow loop
    tan = plaza | road | paths
    tan &= land
    sc.gtiles(U.autotile(tan, U.TAN, fillp=0.75))
    sw2 = U.sh(U.SW2).crop((0, 0, T, T))
    for (tx, ty) in sorted(road):
        if tx in (46, 47) and 14 <= ty <= 36 and (tx + ty) % 2 == 0:
            ins = sw2.crop((2, 2, 14, 14))
            sc.ground.alpha_composite(ins, (tx * T + 2, ty * T + 2))
    tan_wear(sc, tan, "gr-wear")

    # ---- fields (three) + garden
    field_rects = []
    for (bx0, by0, cols_, rows_, species) in [(10, 32, 7, 3, "Cabbage"),
                                              (20, 32, 6, 3, "Cauliflower"),
                                              (58, 30, 6, 3, "Turnip")]:
        sc.gpaste(U.plotbed(cols_ + 1, rows_ + 1), bx0, by0)
        crng = U.LCG("gr-field%d" % bx0)
        for row in range(rows_):
            for col in range(cols_):
                if crng.rf() < 0.86:
                    st = min(6, max(2, 2 + ((col + 2 * row) % 4) + crng.ri(-1, 0)))
                    sc.ent(U.crop_stage(species, st), bx0 + 0.5 + col,
                           by0 + 0.55 + row, dx=crng.ri(-1, 2), dy=-2,
                           prop="crop")
        fence_pen(sc, bx0 - 1, by0 - 1, bx0 + cols_ + 1, by0 + rows_ + 1)
        field_rects.append(U.rect(bx0 - 1, by0 - 1, bx0 + cols_ + 1,
                                  by0 + rows_ + 1))
    # kitchen garden by the plaza
    sc.gpaste(U.plotbed(4, 3), 50, 25)
    grg = U.LCG("gr-garden")
    for row in range(2):
        for col in range(3):
            sc.ent(U.crop_stage("Cabbage", 3 + ((col + row) % 3)),
                   50.6 + col, 25.5 + row, dx=grg.ri(-1, 1), dy=-2, prop="crop")
    sc.ent(U.trim(U.sh(U.P("Scarecrow"))), 53.4, 25.4, bias=0.2, prop="prop")

    # ---- hedgerows + groves + drifts (worked, clustered midland)
    dgl = U.cut(U.PROP, 25, 2, 2, 1); dsl = U.cut(U.PROP, 30, 2, 2, 2)
    hedges = [(26, 20), (33, 22), (39, 24), (52, 17), (58, 20), (62, 24),
              (20, 25), (39, 31), (54, 33), (64, 33), (16, 17), (68, 28),
              (36, 34), (42, 28), (60, 26), (14, 13)]
    hr = U.LCG("gr-hedge")
    for (hx, hy) in hedges:
        if (hx, hy) in land:
            sc.gpaste(dgl if (hx + hy) % 3 else dsl, hx + hr.ri(-1, 1), hy)
    def drift(seed, x0, y0, x1, y1, centers, per, rad, p, avoid):
        dr = U.LCG(seed)
        for _ in range(centers):
            cx_ = dr.ri(x0, x1); cy_ = dr.ri(y0, y1)
            for _ in range(per):
                tx = cx_ + dr.ri(-rad, rad); ty = cy_ + dr.ri(-rad, rad)
                if x0 <= tx <= x1 and y0 <= ty <= y1 and (tx, ty) not in avoid \
                        and (tx, ty) in land and dr.rf() < p:
                    sc.gpaste(U.sh(U.CS("Grass_Tufts_Flowers_16x16_%d"
                                        % dr.ri(1, 11))), tx, ty)
    avoid = set(tan) | orch
    for fr_ in field_rects:
        avoid |= fr_
    avoid |= U.rect(49, 24, 54, 28) | U.rect(21, 25, 38, 30)
    avoid |= U.rect(3, 11, 19, 31)
    avoid |= {(hx + dx, hy + dy) for (hx, hy) in hedges
              for dx in (-1, 0, 1, 2) for dy in (0, 1)}
    drift("gr-dr1", 22, 15, 44, 26, 34, 9, 2, 0.75, avoid)
    drift("gr-dr2", 48, 16, 70, 28, 30, 9, 2, 0.7, avoid)
    drift("gr-dr3", 10, 16, 20, 28, 16, 8, 2, 0.65, avoid)
    drift("gr-dr4", 26, 27, 44, 35, 22, 8, 2, 0.65, avoid)
    drift("gr-dr5", 48, 29, 62, 35, 16, 8, 2, 0.6, avoid)
    drift("gr-dr6", 62, 29, 74, 35, 12, 8, 2, 0.55, avoid)
    drift("gr-dr7", 8, 29, 26, 35, 12, 8, 2, 0.55, avoid)
    drift("gr-dr8", 60, 9, 76, 14, 10, 7, 2, 0.55, avoid)
    verge = U.rect(41, 26, 52, 33)
    vr = U.LCG("gr-verge")
    for (tx, ty) in sorted(verge):
        if (tx, ty) in tan or (tx, ty) not in land: continue
        if vr.rf() < 0.5:
            sc.gpaste(U.sh(U.CS("Grass_Tufts_Flowers_16x16_%d" % vr.ri(1, 11))),
                      tx, ty)
    # inland groves (purposeful tree clusters w/ shadows)
    for gi, grove in enumerate([[(24, 16, "oakM"), (26, 17.4, "oakS"),
                                 (22.6, 17.8, "pineM")],
                                [(62, 15, "oakM"), (64, 16.2, "oakS")],
                                [(31, 32.6, "oakM"), (33, 33.8, "pineM"),
                                 (29.6, 34.2, "oakS")],
                                [(66, 30, "oakM"), (68.2, 31, "oakS")],
                                [(14, 18, "oakL"), (17, 19.2, "oakS")],
                                [(70, 20, "oakL"), (73, 21.4, "oakS")]]):
        for (tx, ty, k) in grove:
            im = U.tree(k)
            px2, py2 = sc.ent(im, tx, ty, bias=-0.05)
            sc.shadow_blob(px2 + im.width // 2, int((ty + 1) * T) - 5,
                           im.width - 16, 24)

    # ================================================== village (EXPANDED)
    house = U.sh(U.P("Farmer_House_1"))
    px_, py_ = sc.ent(house, 17, 11, bias=-0.3)
    sc.shadow_blob(px_ + house.width // 2, 12 * T - 5, house.width - 14, 30)
    smoke_at(sc, px_ + 78, py_ + 18)
    pennant(sc, px_ + 60, py_ - 2)

    lib = U.sh(U.P("Farmer_House_2"))
    px_, py_ = sc.ent(lib, 40, 10, bias=-0.3)
    sc.shadow_blob(px_ + lib.width // 2, 11 * T - 5, lib.width - 16, 30)
    sc.ent(U.sh(U.P("Box_Single")), 41.2, 10.6, prop="prop")
    sc.ent(U.sh(U.P("Box_Single")), 42.0, 10.4, dy=-3, prop="prop")
    roof_eave = U.sh(U.ROOF2).crop((0, U.sh(U.ROOF2).height - 28,
                                    U.sh(U.ROOF2).width, U.sh(U.ROOF2).height))

    # counting-house at the plaza S edge (cumulative treasury home, R1)
    roof_tall = U.sh(U.ROOF2).crop((0, U.sh(U.ROOF2).height - 44,
                                    U.sh(U.ROOF2).width, U.sh(U.ROOF2).height))
    chouse = U.build_stack([U.crop_w(roof_tall, 4 * T),
                            U.crop_w(U.sh(U.GCONDO), 4 * T)])
    px_, py_ = sc.ent(chouse, 36.5, 17.8, bias=-0.3)
    sc.shadow_blob(px_ + chouse.width // 2, int(18.8 * T) - 5,
                   chouse.width - 12, 30)
    coin = Image.new("RGBA", (9, 9), (0, 0, 0, 0))
    cd1 = ImageDraw.Draw(coin)
    cd1.ellipse([0, 0, 8, 8], outline=CREAM + (255,))
    cd1.ellipse([2, 2, 6, 6], fill=LAMP_Y + (255,))
    sc.vfx(coin, px_ + chouse.width // 2 - 4, py_ + 12)
    sc.ent(U.sh(U.BENCH), 41.0, 18.3, prop="prop")

    # skill workshop cluster E of library
    shop = U.sh(U.P("Chicken_Coop"))
    px_, py_ = sc.ent(shop, 57, 15.6, bias=-0.2)
    sc.shadow_blob(px_ + shop.width // 2, int(16.6 * T) - 4, shop.width - 10, 26)
    sc.ent(U.sh(U.P("Henhouse")), 61.4, 15.9, bias=-0.05, prop="prop")
    sc.ent(U.sh(U.P("Woodwork_Crafting_Table_Full")), 61.3, 17.6, prop="prop")
    sc.ent(U.sh(U.P("DIY_Crafting_Table_Full")), 57.4, 18.2, prop="prop")
    sc.ent(U.sh(U.P("Wood_Board_Load")), 55.8, 17.2, prop="prop")

    # infirmary + convalescent yard (empty = prominent health; cream cross)
    infirm = U.build_stack([U.crop_w(roof_tall, 5 * T),
                            U.crop_w(U.sh(U.GCONDO), 5 * T)])
    px_, py_ = sc.ent(infirm, 52, 8.8, bias=-0.3)
    sc.shadow_blob(px_ + infirm.width // 2, int(9.8 * T) - 5, infirm.width - 12, 30)
    cross = Image.new("RGBA", (9, 9), (0, 0, 0, 0))
    cd0 = ImageDraw.Draw(cross)
    cd0.rectangle([3, 0, 5, 8], fill=CREAM + (255,))
    cd0.rectangle([0, 3, 8, 5], fill=CREAM + (255,))
    cd0.rectangle([3, 3, 5, 5], fill=LAMP_Y + (255,))
    sc.vfx(cross, px_ + infirm.width // 2 - 4, py_ + 14)
    fence_pen(sc, 58, 7, 61, 9)
    sc.ent(U.sh(U.P("Hay_Fresh_Pile")), 58.6, 7.9, dy=-2, prop="prop")
    sc.ent(U.sh(U.P("Hay_Fresh_Pile")), 59.8, 8.6, dy=-2, prop="prop")

    # cottage lanes (8 cottages — the org hired)
    coop = U.sh(U.P("Chicken_Coop"))
    for i, cx_ in enumerate([26, 31, 36]):              # W lane trio
        px_, py_ = sc.ent(coop, cx_, 4.6 + (i % 2) * 0.5, bias=-0.2)
        sc.shadow_blob(px_ + coop.width // 2,
                       int((5.6 + (i % 2) * 0.5) * T) - 4, coop.width - 12, 24)
    px_, py_ = sc.ent(coop, 58, 4.8, bias=-0.2)         # E cottage by infirmary
    sc.shadow_blob(px_ + coop.width // 2, int(5.8 * T) - 4, coop.width - 12, 24)
    for i, (cx_, cy_) in enumerate([(28, 9.4), (33, 9.7)]):   # mid pair
        px_, py_ = sc.ent(coop, cx_, cy_, bias=-0.2)
        sc.shadow_blob(px_ + coop.width // 2, int((cy_ + 1) * T) - 4,
                       coop.width - 12, 24)
    sc.ent(U.sh(U.P("Dog_Bowl_Red_Full")), 27.2, 5.8, prop="prop")
    sc.ent(U.sh(U.P("Hay_Dry_Pile_Small")), 37.6, 5.4, prop="prop")
    smoke_at(sc, int(59.4 * T), int(5.2 * T), 0.55)

    # plaza props (well + benches + lamps; noticeboard lives at the crossroads)
    well = U.sh(U.P("Well_Usable"))
    px_, py_ = sc.ent(well, 39.2, 11.3, prop="prop")
    sc.shadow_blob(px_ + well.width // 2, int(12.3 * T) - 6, 40, 30)
    sc.ent(U.sh(U.BENCH), 43.0, 10.4, prop="prop")
    sc.ent(U.sh(U.BENCH), 38.0, 13.6, prop="prop")
    sc.ent(U.sh(U.LAMP), 37.0, 10.1, dx=-6, prop="prop")
    sc.ent(U.sh(U.LAMP), 45.2, 13.3, dx=-6, prop="prop")
    # market row on the plaza W edge (busy village texture)
    sc.ent(U.sh(U.P("Market_Stand_Blue_Small")), 33.0, 11.4, prop="prop")
    sc.ent(U.sh(U.P("Market_Stand_Green_Small")), 33.2, 13.2, prop="prop")

    # barn (behind) + double-silo (front-right) + water tank + composter W
    barn = U.sh(U.P("Barn_Small"))
    px_, py_ = sc.ent(barn, 4, 21, bias=-0.3)
    sc.shadow_blob(px_ + barn.width // 2, int(22.0 * T) - 5, barn.width - 14, 30)
    silo = U.sh(U.P("Silos_1"))
    px_, py_ = sc.ent(silo, 12, 27, bias=-0.3)
    sc.shadow_blob(px_ + silo.width // 2, int(28.0 * T) - 5, silo.width - 8, 30)
    tank = U.sh(U.P("Silos_2"))
    px_, py_ = sc.ent(tank, 5, 30, bias=-0.3)
    sc.shadow_blob(px_ + tank.width // 2, int(31.0 * T) - 5, tank.width - 8, 30)
    sc.gtiles(U.autotile(U.rect(20, 22, 21, 23) & land, U.SOIL))
    sc.ent(U.sh(U.P("Sack_Jute_Load_2")), 20.1, 23.0, prop="prop")

    # law plot NW
    fence_pen(sc, 9, 7, 13, 10)
    sc.ent(U.sh(U.P("Sign_1")), 9.8, 8.2, prop="prop")
    sc.ent(U.sh(U.P("Sign_2")), 11.4, 8.4, prop="prop")
    sc.ent(U.sh(U.P("Sign_2")), 12.6, 8.1, prop="prop")
    sc.ent(U.sh(U.P("Rock_Small")), 9.4, 9.6, prop="prop")
    sc.ent(U.sh(U.P("Rock_Medium")), 12.0, 9.8, prop="prop")

    # retro green mid-island (cold firepit + logs + reading officer)
    fp_cx, fp_cy = 28.0, 22.6
    ash = Image.new("RGBA", (26, 14), (0, 0, 0, 0))
    ad = ImageDraw.Draw(ash)
    ad.ellipse([0, 0, 25, 13], fill=ASH_M + (235,))
    ad.ellipse([5, 3, 19, 10], fill=ASH_D + (255,))
    ad.point((9, 6), fill=ASH_L + (255,)); ad.point((15, 7), fill=ASH_L + (255,))
    sc.ent(ash, fp_cx, fp_cy, prop="firepit")
    for (rx, ry) in [(-1.2, -0.4), (1.3, -0.5), (-1.4, 0.7), (1.5, 0.8)]:
        sc.ent(U.sh(U.P("Rock_Small")), fp_cx + rx, fp_cy + ry + 0.4)
    sc.ent(U.sh(U.P("Trunk_Big_1")), fp_cx - 1.6, fp_cy + 1.6, prop="prop")
    sc.ent(U.sh(U.P("Trunk_Big_2")), fp_cx + 1.2, fp_cy + 1.7, prop="prop")
    px_, py_ = sc.ent(U.c_read(7, "down", 1), fp_cx + 0.1, fp_cy + 1.5)
    sc.shadow_blob(px_ + 8, int((fp_cy + 2.5) * T) - 2, 12, 40)

    # pens (the herd = the fleet), E of the farm cluster
    fence_pen(sc, 22, 26, 28, 29)
    fence_pen(sc, 29, 26, 34, 29)
    fence_pen(sc, 35, 27, 38, 29, True)
    sc.ent(U.sh(U.FE("Wooden_Fence_Type_3_Brown_Gate_1")), 24, 29, bias=0.03)
    sc.ent(U.sh(U.P("Cow_Sign")), 21.6, 29.7, prop="prop")
    sc.ent(U.sh(U.P("Chicken_Sign")), 28.6, 29.6, prop="prop")
    sc.ent(U.sh(U.P("Drinking_Trough_Horizontal_Full")), 23, 26.9, dy=-2,
           prop="prop")
    sc.ent(U.sh(U.P("Hay_Dry_Pile")), 25.6, 26.7, dy=-2, prop="prop")
    sc.ent(U.sh(U.P("Henhouse")), 31.6, 27.2, bias=-0.05, prop="prop")
    for (cx_, cy_, k, i, dd) in [(23.6, 28.0, "graze", 0, 0),
                                 (25.8, 27.2, "idle", 2, 0),
                                 (27.0, 28.4, "graze", 1, 0)]:
        c = U.cow_f(k, i, dd)
        px_, py_ = sc.ent(c, cx_, cy_)
        sc.shadow_blob(px_ + 24, int((cy_ + 1) * T) - 4, 30, 30)
    for (cx_, cy_, k, wh) in [(29.8, 27.2, "peck", False),
                              (32.6, 28.2, "idle", False),
                              (30.4, 28.6, "walk", True),
                              (33.2, 27.0, "peck", True)]:
        sc.ent(U.chick(k, 0, wh), cx_, cy_, bias=0.06)

    # orchard trees NE
    def fruit(nm, tx, ty):
        im = U.trim(U.sh(U.FR(nm)))
        px2, py2 = sc.ent(im, tx, ty, bias=-0.1)
        sc.shadow_blob(px2 + im.width // 2, int((ty + 1) * T) - 4,
                       im.width - 20, 28)
    fruit("Fruit_Tree_Apple_Ripe_Big", 65, 3.4)
    fruit("Fruit_Tree_Apple_Ripe", 68.4, 2.6)
    fruit("Fruit_Tree_Apple_Ripe_Big", 71.6, 4.0)
    fruit("Fruit_Tree_Apple_Ripe", 67.0, 5.6)
    fruit("Fruit_Tree_Apple_Unripe", 74.2, 3.0)
    fruit("Fruit_Tree_Apple_Ripe", 75.4, 5.4)
    sc.ent(U.sh(U.FR("Basket_Apple")), 66.4, 5.0, prop="prop")

    # switchboard hut + telegraph line (ONE side of the road; taut-dark = OK)
    sc.ent(U.sh(U.P("Henhouse")), 50.6, 21.8, bias=-0.05, prop="prop")
    tp = telegraph_pole()
    pole_pts = []
    for py0 in range(16, 37, 5):
        px_, py_ = sc.ent(tp, 48.8, py0)
        pole_pts.append((px_ + 6, py_ + 4))
    wire_d = ImageDraw.Draw(sc.ground)
    for (p0, p1) in zip(pole_pts, pole_pts[1:]):
        mx = (p0[0] + p1[0]) // 2; my = max(p0[1], p1[1]) + 3
        wire_d.line([p0, (mx, my)], fill=WOODDKR + (230,))
        wire_d.line([(mx, my), p1], fill=WOODDKR + (230,))
    # drop-wire to the switchboard hut
    wire_d.line([pole_pts[1], (int(51.2 * T), int(22.2 * T))],
                fill=WOODDKR + (230,))

    # lantern posts, opposite verge — LIT (post-graduation era)
    lp = lantern_post(lit=True)
    for i, py0 in enumerate(range(17, 36, 6)):
        px_, py_ = sc.ent(lp, 44.9, py0)

    # crossroads (mailbox + noticeboard + kiosk + Pippin)
    mb = U.mailbox(True, pips=3)
    px_, py_ = sc.ent(mb, 44.6, 27.6, bias=0.1, prop="prop")
    sc.shadow_blob(px_ + 8, int(28.6 * T) - 6, 14, 30)
    nb2 = U.noticeboard()
    px_, py_ = sc.ent(nb2, 41.8, 26.8, prop="prop")
    sc.shadow_blob(px_ + nb2.width // 2, int(27.8 * T), 40, 28)
    kiosk = U.sh(U.P("Market_Stand_Yellow_Small"))
    px_, py_ = sc.ent(kiosk, 48.6, 29.4, prop="prop")
    sc.shadow_blob(px_ + kiosk.width // 2, int(30.4 * T) - 4, kiosk.width - 8, 26)
    sc.ent(U.sh(U.BLUE), 51.4, 29.2, prop="prop")
    sc.ent(U.sh(U.LAMP), 41.2, 29.1, dx=-6, prop="prop")
    dgs = U.dog_sleep(0)
    px_, py_ = sc.ent(dgs, 41.8, 28.7)
    sc.shadow_blob(px_ + 22, int(29.7 * T) - 6, 24, 26)

    # commuters on the arteries (event-real walks)
    officer(sc, 4, "walk", "down", 46.35, 24.6, chipl=["SHIP", "IT"])
    officer(sc, 2, "walk", "up", 46.9, 32.4)
    officer(sc, 7, "walk", "right", 52.0, 22.6)
    officer(sc, 12, "idle", "down", 40.2, 12.2)
    officer(sc, 15, "walk", "left", 28.0, 12.0)
    officer(sc, 9, "idle", "down", 12.5, 32.2)

    # ============ QUAY: busy multi-berth working wharf
    quay_stone(sc, gd, QX0, QX1, Q0, Q1, "gr-quay")
    tide_foam(gd, QX0, QX1, SEA0, "gr-tide", n=150)
    shoreline_foam(gd, LX0, QX0 - 1, SEA0, "gr-shorefoam-w")

    roof_wh = roof_tall
    ware = U.build_stack([U.crop_w(roof_wh, 6 * T), U.crop_w(U.sh(U.GCONDO), 6 * T)])
    px_, py_ = sc.ent(ware, 13.6, 39.8, bias=-0.3)
    sc.shadow_blob(px_ + ware.width // 2, int(40.8 * T) - 6, ware.width - 14, 30)
    ware2 = U.build_stack([U.crop_w(roof_wh, 5 * T), U.crop_w(U.sh(U.GCONDO), 5 * T)])
    px_, py_ = sc.ent(ware2, 20.4, 39.4, bias=-0.3)
    sc.shadow_blob(px_ + ware2.width // 2, int(40.4 * T) - 6, ware2.width - 14, 30)
    for i, (dx0, dy0) in enumerate([(0, 0), (1.15, 0.1), (0.5, -0.75),
                                    (1.7, -0.6), (1.05, -1.4)]):
        sc.ent(U.sh(U.P("Crate_Dark_Brown_Empty" if i % 2 else "Crate_Brown_Empty")),
               26.0 + dx0, 39.2 + dy0, prop="prop")
    # customs house at the road mouth (org cost aggregate home)
    cust = U.build_stack([U.crop_w(roof_wh, 4 * T), U.crop_w(U.sh(U.GCONDO), 4 * T)])
    px_, py_ = sc.ent(cust, 48.5, 39.6, bias=-0.3)
    sc.shadow_blob(px_ + cust.width // 2, int(40.6 * T) - 5, cust.width - 12, 30)
    # harbormaster hut + the Chair at the ledger window
    hut = U.build_stack([U.crop_w(roof_eave, 4 * T), U.crop_w(U.sh(U.GCONDO), 4 * T)])
    px_, py_ = sc.ent(hut, 54.5, 38.8, bias=-0.3)
    sc.shadow_blob(px_ + hut.width // 2, int(39.8 * T) - 5, hut.width - 12, 30)
    officer(sc, 1, "idle", "up", 55.6, 39.7)
    sc.ent(U.sh(U.BENCH), 58.8, 39.2, prop="prop")

    # berths: 9 working, lane-grouped + 1 waiting chalk (demand > capacity)
    berth_xs = [(30.5, 4), (34.0, 3), (37.5, 6), (41.0, 5), (44.5, 7),
                (59.0, 5), (62.5, 4), (66.0, 3), (69.5, 2)]
    for i, (bx_, stg) in enumerate(berth_xs):
        by_ = 38.1 if i % 2 == 0 else 38.4
        x0, y0 = int(bx_ * T) - 3, int(by_ * T) + 6
        x1, y1 = int(bx_ * T) + 3 * T + 9, int(by_ * T) + 3 * T + 4
        for xx in range(x0, x1, 4):
            gd.rectangle([xx, y0, xx + 1, y0], fill=CHALK + (190,))
            gd.rectangle([xx, y1, xx + 1, y1], fill=CHALK + (190,))
        for yy in range(y0, y1, 4):
            gd.rectangle([x0, yy, x0, yy + 1], fill=CHALK + (190,))
            gd.rectangle([x1, yy, x1, yy + 1], fill=CHALK + (190,))
        cxp = int(bx_ * T) + 20
        gd.rectangle([cxp, Q1 * T + 10, cxp + 3, Q1 * T + 11],
                     fill=(40, 44, 58, 255))
        gd.rectangle([cxp + 1, Q1 * T + 8, cxp + 2, Q1 * T + 12],
                     fill=(58, 62, 78, 255))
        stk = U.berth_stack3(stg, "gr-berth%d" % i)
        px_, py_ = sc.ent(stk, bx_, by_ + 1.6, prop="prop")
        sc.shadow_blob(px_ + stk.width // 2, int((by_ + 2.6) * T) - 6,
                       28 + 2 * stg, 26)
    bx_ = 72.5; by_ = 38.2       # waiting berth: chalk only
    x0, y0 = int(bx_ * T) - 3, int(by_ * T) + 6
    x1, y1 = int(bx_ * T) + 2 * T + 9, int(by_ * T) + 3 * T + 4
    for xx in range(x0, x1, 4):
        gd.rectangle([xx, y0, xx + 1, y0], fill=CHALK + (190,))
        gd.rectangle([xx, y1, xx + 1, y1], fill=CHALK + (190,))
    for yy in range(y0, y1, 4):
        gd.rectangle([x0, yy, x0, yy + 1], fill=CHALK + (190,))
        gd.rectangle([x1, yy, x1, yy + 1], fill=CHALK + (190,))
    officer(sc, 10, "idle", "up", 39.6, 40.9)
    officer(sc, 3, "walk", "left", 62.4, 40.6)

    # timber row at the wharf E end (on the deck, past the waiting berth)
    wood_l = U.sh(U.P("Wood_Board_Load"))
    for (spx, yx, yy_) in [(wood_l, 74.4, 39.3),
                           (U.cut(U.PROP, 24, 6, 2, 2), 75.6, 39.2),
                           (U.sh(U.P("Sack_Jute_Load_2")), 74.6, 40.4),
                           (U.sh(U.P("Crate_Dark_Brown_Empty")), 75.6, 40.5)]:
        sc.ent(spx, yx, yy_, prop="prop")
    sc.shadow_blob(int(75.2 * T), int(41.4 * T) - 6, 44, 22)

    # quay lamps rhythm
    for lx_ in (12.9, 22.6, 32.4, 42.1, 52.4, 61.9, 70.6):
        sc.ent(U.sh(U.LAMP), lx_, Q0 - 0.6, dx=-6, prop="prop")

    # piers + W dock
    piers = (U.rect(28, SEA0, 29, 47) | U.rect(45, SEA0, 46, 48)
             | U.rect(62, SEA0, 63, 47))
    dock = U.rect(16, SEA0, 17, 46)
    planks(sc, gd, piers | dock)
    pier_posts(gd, [(28 * T - 2, 47 * T + 8), (30 * T, 47 * T + 8),
                    (45 * T - 2, 48 * T + 8), (47 * T, 48 * T + 8),
                    (62 * T - 2, 47 * T + 8), (64 * T, 47 * T + 8),
                    (28 * T - 2, SEA0 * T + 6), (45 * T - 2, SEA0 * T + 6),
                    (62 * T - 2, SEA0 * T + 6), (16 * T - 2, 46 * T + 8),
                    (18 * T, 46 * T + 8)])
    sc.ent(U.sh(U.BOAT), 26.6, 44.6)
    sc.ent(U.sh(U.BOAT).transpose(Image.FLIP_TOP_BOTTOM), 64.4, 43.8)
    carrier = U.c_walk(3, "down", 1).copy()
    bxs = U.sh(U.P("Box_Single"))
    carrier.alpha_composite(bxs.crop((2, 4, 14, 14)), (2, 12))
    px_, py_ = sc.ent(carrier, 45.4, 44.4)
    sc.shadow_blob(px_ + 8, int(45.4 * T) - 2, 12, 30)

    # breakwater + LIT lighthouse SE (the earned light — first graduation)
    arm = ({(tx, SEA0) for tx in range(72, 79)}
           | {(tx, 43) for tx in range(73, 79)}
           | {(tx, 44) for tx in range(74, 79)}
           | {(tx, 45) for tx in (75, 76, 77)})
    sw1 = U.sh(U.SW1).crop((0, 0, T, T))
    jr2 = U.LCG("gr-arm")
    for (tx, ty) in sorted(arm):
        sc.ground.paste(sw1, (tx * T, ty * T))
        for _ in range(4):
            fx = tx * T + jr2.ri(0, T - 2); fy = ty * T + jr2.ri(0, T - 2)
            gd.point((fx, fy), fill=(ST_DK if jr2.rf() < 0.6 else ST_LT) + (255,))
    for (tx, ty) in sorted(arm):
        if (tx - 1, ty) not in arm:
            gd.rectangle([tx * T, ty * T, tx * T, ty * T + 15], fill=ST_DK + (255,))
        if (tx + 1, ty) not in arm:
            gd.rectangle([tx * T + 15, ty * T, tx * T + 15, ty * T + 15],
                         fill=ST_DK + (255,))
        if (tx, ty + 1) not in arm:
            gd.rectangle([tx * T, ty * T + 14, tx * T + 15, ty * T + 15],
                         fill=ST_DK + (255,))
    lh = lighthouse_lit()
    px_, py_ = sc.ent(lh, 74.6, 44.0, bias=-0.2)
    sc.shadow_blob(px_ + lh.width // 2, int(45.0 * T) - 6, lh.width - 18, 34)
    sc.ent(U.sh(U.P("Rock_Medium")), 74.4, 44.8, prop="prop")
    sc.ent(U.sh(U.P("Rock_Small")), 77.6, 42.6, prop="prop")
    frng2 = U.LCG("gr-pointfoam")
    for _ in range(14):
        fx = frng2.ri(72 * T, int(79.5 * T)); fy2 = frng2.ri(int(42.5 * T),
                                                            int(46.5 * T))
        gd.rectangle([fx, fy2, fx + frng2.ri(3, 7), fy2], fill=FOAM_C + (170,))

    # ============ THE ARCHIPELAGO: 3 product isles, size variance
    def texture_isle(cells, seed):
        tr = U.LCG(seed)
        for (hx, hy) in sorted(cells):
            if tr.rf() < 0.8:
                sc.gpaste(gvar, hx, hy)
            for _ in range(tr.ri(3, 6)):
                fx = hx * T + tr.ri(0, T - 2); fy = hy * T + tr.ri(0, T - 3)
                col = G_DK if tr.rf() < 0.62 else G_LT
                gd.rectangle([fx, fy, fx, fy + 1], fill=col + (255,))
        for _ in range(len(cells) // 5):
            (hx, hy) = sorted(cells)[tr.n() % len(cells)]
            sc.gpaste(U.sh(U.CS("Grass_Tufts_Flowers_16x16_%d" % tr.ri(1, 11))),
                      hx, hy)

    # polads SE — LARGEST (r2 town)
    ip = isle_blob(sc, 92, 54, 113, 68, "gr-isle-polads")
    texture_isle(ip, "gr-ptex")
    ipaths = U.carve_path([(96, 62), (101, 61), (106, 60), (109, 59)])
    for (tx, ty) in sorted(ipaths):
        if (tx, ty) in ip:
            sc.gpaste(U.cut(U.TER, 5, 1), tx, ty)
    wt = U.build_stack([U.crop_w(roof_eave, 3 * T), U.crop_w(U.sh(U.GCONDO), 3 * T)])
    for (wx, wy) in [(95, 59.4), (101, 58.6)]:
        px_, py_ = sc.ent(wt, wx, wy, bias=-0.2)
        sc.shadow_blob(px_ + wt.width // 2, int((wy + 1) * T) - 4,
                       wt.width - 10, 26)
    for (cx_, cy_) in [(99, 63.6), (104.4, 62.8), (108.0, 61.6)]:
        px_, py_ = sc.ent(coop, cx_, cy_, bias=-0.2)
        sc.shadow_blob(px_ + coop.width // 2, int((cy_ + 1) * T) - 4,
                       coop.width - 12, 22)
    smoke_at(sc, int(100.2 * T), int(63.2 * T), 0.5)
    for (tx, ty, k) in [(109.6, 57.0, "oakM"), (94.2, 56.4, "oakS"),
                        (110.4, 64.0, "oakS"), (96.0, 65.8, "pineM")]:
        im = U.tree(k)
        px2, py2 = sc.ent(im, tx, ty, bias=-0.05)
        sc.shadow_blob(px2 + im.width // 2, int((ty + 1) * T) - 5,
                       im.width - 16, 22)
    for (bx0, by0) in [(103.2, 64.6), (104.4, 64.2), (103.8, 65.4)]:
        sc.ent(U.sh(U.P("Crate_Brown_Empty")), bx0, by0, prop="prop")
    planks(sc, gd, U.rect(97, 68, 98, 70))
    sc.ent(lantern_post(lit=True), 96.2, 67.8)      # dock light LIT (verified)
    sc.ent(U.sh(U.BOAT), 99.6, 69.6)
    officer(sc, 5, "walk", "right", 101.5, 61.0)

    # stephie SW — medium (r1-r2)
    isb = isle_blob(sc, 12, 56, 28, 66, "gr-isle-stephie")
    texture_isle(isb, "gr-stex")
    px_, py_ = sc.ent(wt, 15, 59.2, bias=-0.2)
    sc.shadow_blob(px_ + wt.width // 2, int(60.2 * T) - 4, wt.width - 10, 26)
    for (cx_, cy_) in [(20.2, 60.4), (16.0, 62.6)]:
        px_, py_ = sc.ent(coop, cx_, cy_, bias=-0.2)
        sc.shadow_blob(px_ + coop.width // 2, int((cy_ + 1) * T) - 4,
                       coop.width - 12, 22)
    for (tx, ty, k) in [(24.4, 58.0, "pineM"), (13.2, 57.2, "oakS"),
                        (24.8, 62.6, "oakS")]:
        im = U.tree(k)
        px2, py2 = sc.ent(im, tx, ty, bias=-0.05)
        sc.shadow_blob(px2 + im.width // 2, int((ty + 1) * T) - 5,
                       im.width - 16, 22)
    sc.ent(U.sh(U.P("Box_Single")), 18.6, 63.4, prop="prop")
    planks(sc, gd, U.rect(19, 66, 20, 67))
    sc.ent(lantern_post(lit=False), 18.2, 65.7)     # dock light dark (unprobed)

    # new-lane isle E — smallest (r0-r1, being raised NOW)
    isn = isle_blob(sc, 98, 15, 107, 21, "gr-isle-new")
    texture_isle(isn, "gr-ntex")
    px_, py_ = sc.ent(wt, 100, 17.6, bias=-0.2)
    sc.shadow_blob(px_ + wt.width // 2, int(18.6 * T) - 4, wt.width - 10, 26)
    surveyor_stakes(gd, int(103.5 * T), int(18.5 * T), "gr-stakes")
    planks(sc, gd, U.rect(102, 21, 103, 22))
    sc.ent(U.sh(U.BOAT), 104.8, 22.0)
    sc.ent(U.tree("oakS"), 99.0, 15.6, bias=-0.05)
    officer(sc, 14, "idle", "left", 102.6, 18.4)    # rowboat crew raising r1

    # ============ sea lanes + ships (§2.4 two-signal shipping)
    sea_lane(gd, (52 * T, 43 * T), (97 * T, 60 * T), "gr-lane-polads", 9)
    sea_lane(gd, (50 * T + 8, 43 * T + 8), (96 * T, 61 * T), "gr-lane-polads2", 11)
    sea_lane(gd, (30 * T, 43 * T), (20 * T, 64 * T), "gr-lane-stephie", 9)
    sea_lane(gd, (66 * T, 43 * T), (103 * T, 23 * T), "gr-lane-new", 10)
    # cargo ships UNDER WAY to polads (milestones sailed; wakes astern)
    ship1 = cargo_boat("down")
    px_, py_ = sc.ent(ship1, 68.0, 50.2)
    sc.vfx(boat_wake("up"), px_ - 4, py_ - 16)
    ship1b = cargo_boat("down")
    px_, py_ = sc.ent(ship1b, 80.6, 54.8)
    sc.vfx(boat_wake("up"), px_ - 4, py_ - 16)
    # second ship arriving off polads roadstead
    ship3 = cargo_boat("down")
    px_, py_ = sc.ent(ship3, 90.4, 57.8)
    sc.vfx(boat_wake("up"), px_ - 4, py_ - 16)
    # packet AT ANCHOR off stephie (holding for the verdict — honest wait)
    ship2 = U.sh(U.BOAT)
    px_, py_ = sc.ent(ship2, 23.6, 52.4)
    gd.rectangle([px_ + 7, py_ + ship2.height + 2, px_ + 7,
                  py_ + ship2.height + 6], fill=WOODDKR + (255,))
    gd.rectangle([px_ + 5, py_ + ship2.height + 3, px_ + 6,
                  py_ + ship2.height + 3], fill=FOAM_B + (150,))
    # rowboat out to the new isle + outbound dinghy from the dock
    sc.ent(U.sh(U.BOAT), 96.4, 26.0)
    px_, py_ = sc.ent(U.sh(U.BOAT), 21.0, 47.6)
    sc.vfx(boat_wake("up"), px_ - 4, py_ - 16)
    # reef-buoy at the retired stepnetwork anchor (due south, honest dormant)
    sc.ent(red_buoy(), 45.7, 56.4)
    gd.rectangle([int(45.4 * T), int(57.5 * T), int(45.4 * T) + 10,
                  int(57.5 * T)], fill=FOAM_C + (150,))
    # grey buoy + haze ribbon on the UNPROBED new lane (§2.4 honest haze)
    sc.ent(grey_buoy(), 84.0, 34.6)
    hz = U.LCG("gr-hazelane")
    for _ in range(110):
        f = hz.rf()
        hx = int(66 * T + (103 * T - 66 * T) * f) + hz.ri(-14, 14)
        hy = int(43 * T + (23 * T - 43 * T) * f) + hz.ri(-8, 8)
        ln = hz.ri(3, 6)
        col = MIST_HUES[hz.ri(0, len(MIST_HUES) - 1)]
        gd.rectangle([hx, hy, hx + ln, hy],
                     fill=col + (255 if hz.rf() > 0.3 else 170,))

    # ducks in the W cove
    for i, (tx, ty) in enumerate([(10.5, 45.0), (12, 46.0), (11, 47.0)]):
        df = U.duck_frame(i % 4, brown=(i == 2))
        px_, py_ = sc.ent(df, tx, ty)
        gd.rectangle([px_ + 2, int((ty + 1) * T) - 3, px_ + 13,
                      int((ty + 1) * T) - 3], fill=FOAM_B + (90,))

    # ============ mist: reserved slots + horizons (grey-unmeasured geography)
    mist_pocket(gd, 5, 70, 5, "gr-mp1")            # reserved slot SW deep
    mist_pocket(gd, 56, 73, 7, "gr-mp2")           # reserved slot S deep
    mist_pocket(gd, 36, 68, 5, "gr-mp2b")          # southern shoal haze
    mist_pocket(gd, 115, 44, 5, "gr-mp3")          # reserved slot E
    mist_pocket(gd, 113, 8, 4, "gr-mp4")           # beyond the new isle NE
    mist_band(gd, 0, 75, W_ - 1, H_ - 1, "gr-mist", ramp="down", dens=(1, 7))
    mist_band(gd, 0, 6, 2, 34, "gr-mist-w", ramp="down", dens=(2, 3))
    mist_band(gd, 117, 24, W_ - 1, 60, "gr-mist-e", ramp="down", dens=(2, 3))

    # ============ forest rim N + coast columns (dense frame)
    ring_forest(sc, [
        (4, 80, -1, "mix", 1.7), (5, 79, 0.7, "mix", 1.8),
        (6, 62, 1.9, "tall", 2.2),
        (5, 8, 3.0, "mix", 2.2), (6, 9, 6.0, "shore", 2.6),
        (5, 8, 9.0, "mix", 2.4), (6, 9, 12.4, "shore", 2.8),
        (5, 8, 16.0, "shore", 2.8), (6, 9, 19.6, "shore", 3.0),
        (5, 8, 24.0, "shore", 3.0), (6, 9, 28.4, "shore", 3.2),
        (5, 8, 33.0, "shore", 3.2),
        (72, 76, 3.0, "mix", 2.2), (73, 77, 6.0, "shore", 2.6),
        (72, 76, 9.0, "mix", 2.4), (73, 77, 12.4, "shore", 2.8),
        (74, 78, 16.0, "shore", 2.8), (73, 77, 19.6, "shore", 3.0),
        (74, 78, 24.0, "shore", 3.0), (73, 77, 28.4, "shore", 3.2),
        (74, 78, 33.0, "shore", 3.2),
    ], "gr-ring")
    for (tx, ty, k) in [(20, 8, "oakM"), (12, 10, "oakS"), (70, 12, "oakS"),
                        (10, 24, "oakM"), (74, 8, "oakM"), (20, 24, "oakS"),
                        (36, 20, "oakS"), (54, 14, "oakS"), (12, 35, "pineM"),
                        (70, 35, "oakS"), (34, 8, "oakS"), (52, 32, "oakS")]:
        if True:
            im = U.tree(k)
            px2, py2 = sc.ent(im, tx, ty, bias=-0.05)
            sc.shadow_blob(px2 + im.width // 2, int((ty + 1) * T) - 5,
                           im.width - 16, 24)

    return sc
# ================================================================ render main
def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    if which in ("egg", "all"):
        sc = build_egg()
        base = sc.compose()
        # 608x464 -> crop base to 600x450 -> x2 = 1200x900
        base = base.crop((4, 7, 604, 457))
        U.up(base, 2).convert("RGB").save(OUT + "/stage-egg.png")
        print("stage-egg.png", (base.width * 2, base.height * 2))

    if which in ("today", "all"):
        sc = build_today()
        base = sc.compose()
        # 800x560 -> crop to 800x550 (keep rooflines; trim mist row) -> x2
        base = base.crop((0, 0, 800, 550))
        U.up(base, 2).convert("RGB").save(OUT + "/stage-today.png")
        print("stage-today.png", (base.width * 2, base.height * 2))

    if which in ("grown", "all"):
        sc = build_grown()
        base = sc.compose()
        # 1920x1280 exact at x1 (archipelago LOD zoom-out)
        img = base.convert("RGB")
        img.save(OUT + "/stage-grown.png")
        print("stage-grown.png", img.size)

if __name__ == "__main__":
    main()

