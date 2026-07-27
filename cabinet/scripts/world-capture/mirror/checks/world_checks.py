#!/usr/bin/env python3
"""world_checks.py — invariants for a rendered Cabinet World frame.

THE RULE THAT MAKES THIS WORTH ANYTHING: nothing in this file may import the
compositor, the cutout pipeline or any of their helpers. Every assertion is made
against the RENDERED PIXELS and the emitted blueprint, derived independently.

That rule exists because it was paid for. The on-road audit used to call the same
footprint helper the placement rule called, so when that helper's model of "where a
sprite stands" was wrong, the rule and its own check were wrong in exactly the same
way — and the world was reported clean three times while props sat in the road.
A check that imports what it tests certifies its own blind spot.

Each check returns (name, ok, detail, surfaces_covered).
"""
from __future__ import annotations
import json, math, os, glob
from collections import Counter
from PIL import Image

# ---------------------------------------------------------------- independent geometry
# Re-derived here on purpose. If the compositor's notion of a ground footprint drifts,
# these two disagree and the check fails — which is the entire point.
def ground_box(x, y, w, h):
    """An isometric sprite stands on a DIAMOND, not on its base line or its rect."""
    hw = w*0.42
    depth = max(6.0, min(h*0.55, w*0.55))
    return (x-hw, y-depth, x+hw, y)


def overlap_frac(a, b):
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0: return 0.0
    aa = max(1.0, (a[2]-a[0])*(a[3]-a[1]))
    ab = max(1.0, (b[2]-b[0])*(b[3]-b[1]))
    return ix*iy/min(aa, ab)


# ---------------------------------------------------------------- road, from PIXELS
ROAD_RGB = [(138, 106, 66), (156, 122, 78), (173, 138, 92), (188, 154, 108),
            (201, 168, 122), (139, 129, 117), (153, 143, 128), (167, 156, 140),
            (180, 169, 151), (193, 182, 163)]


def _is_roadish(p):
    r, g, b = p[:3]
    if g > r or b > r: return False              # road is never greener/bluer than red
    return any(abs(r-c[0]) < 17 and abs(g-c[1]) < 17 and abs(b-c[2]) < 17 for c in ROAD_RGB)


def road_mask(im, step=3):
    """Road pixels judged from the finished image, not from the compositor's mask."""
    px = im.load(); W, H = im.size
    m = [[False]*((W+step-1)//step) for _ in range((H+step-1)//step)]
    for yy in range(0, H, step):
        for xx in range(0, W, step):
            m[yy//step][xx//step] = _is_roadish(px[xx, yy])
    return m, step


# ---------------------------------------------------------------------------- checks
def check_on_road(render, bp, tol=0.16):
    # Read the GROUND layer, not the finished frame. Sampling the composite looks
    # THROUGH the sprite: a grey stone plinth reads as cobble and reports itself as
    # standing in the road. The ground pass shows what the lane actually is.
    ground = os.path.splitext(render)[0] + ".ground.png"
    im = Image.open(ground if os.path.exists(ground) else render).convert("RGB")
    m, step = road_mask(im)
    W, H = im.size
    # The paved SQUARE is somewhere to stand, not a carriageway. Its stone reads as
    # road-coloured, so without this every bench round the hearth is a false positive.
    pz = bp.get("plaza")
    def in_plaza(x, y):
        if pz:
            cx, cy, rx, ry = pz
            if ((x-cx)/rx)**2 + ((y-cy)/ry)**2 <= 1.0: return True
        # ploughed soil is the same warm brown as a dirt lane; a haystack standing in
        # its own field is not blocking anything
        for fx, fy, fw, fh in bp.get("fields", []):
            if ((x-fx)/max(1, fw))**2 + ((y-fy)/max(1, fh))**2 <= 1.0: return True
        q = bp.get("quay")
        if q and q[0] <= x <= q[2] and q[1] <= y <= q[3]: return True
        return False
    bad = []
    for s in bp["sprites"]:
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        if s["n"] in ALLOW_ON_ROAD: continue
        gx0, gy0, gx1, gy1 = ground_box(x, y, w, h)
        hit = tot = 0
        for fy in (0.0, 0.35, 0.7, 1.0):
            yy = gy1 - (gy1-gy0)*fy
            for fx in (-1, -0.5, 0, 0.5, 1):
                xx = x + (gx1-gx0)/2*fx*(1-0.45*fy)
                iy, ix = int(yy)//step, int(xx)//step
                if 0 <= iy < len(m) and 0 <= ix < len(m[0]):
                    tot += 1
                    if m[iy][ix]: hit += 1
        if tot and hit/tot > tol and not in_plaza(x, y): bad.append(f"{s['n']}@{x},{y}")
    return ("on_road", not bad, f"{len(bad)} sprites stand on a lane: {bad[:6]}", {"placement", "roads"})


ALLOW_ON_ROAD = {"quay_deck", "jetty_plank", "mooring_post", "harbor_crane", "cargo_crates",
                 "cargo_barrels", "fish_barrel", "rope_coil", "crab_pots", "fish_drying_rack",
                 "fishing_net", "anchor", "barrel_single", "crate_single", "boat_rowing",
                 "boat_packet", "boat_fishing", "buoy", "duck", "bridge_plank", "gate_arch",
                 "fence_run", "camp_rowboat_jetty", "camp_bundles", "camp_tarp_cache"}


def check_stacking(render, bp, hard=0.30):
    ss = bp["sprites"]
    boxes = [(s["n"], ground_box(s["x"], s["y"], s["w"], s["h"])) for s in ss]
    bad = []
    for i, (n1, a) in enumerate(boxes):
        for n2, b in boxes[i+1:]:
            f = overlap_frac(a, b)
            if f > hard and n1 in STRUCTURES and n2 in STRUCTURES:
                bad.append(f"{n1}/{n2} {f:.2f}")
    drawn = {s["n"] for s in ss}
    known = len(drawn & STRUCTURES)
    return ("stacking", not bad,
            f"{len(bad)} structure-on-structure: {bad[:6]}; "
            f"{known} distinct structure names recognised in this frame",
            {"placement"})


# A structure is anything a person could not walk through. Kept as an explicit list
# because the check must not ask the compositor what counts as a building — but the list
# has to cover EVERY era or the check goes quietly blind on three of them. It did: it
# named 21 of 46 hamlet frames and exactly 1 of 24 town and 1 of 24 beyond_bay, so town
# and bay reported zero stacking while unfiltered they stacked 24 and 27. Found by an
# adversarial review of the engine-port plan, not by the harness itself.
_STRUCT_HAMLET = {
    "great_house", "cottage_a", "cottage_b", "cottage_c", "officer_house_a",
    "officer_house_b", "officer_house_c", "library", "workshop", "barn", "chicken_coop",
    "windmill", "watermill_kiln", "observatory", "chart_tent", "warehouse",
    "harbormaster_hut", "lighthouse", "market_stall", "well", "well_house", "water_tank",
    "harbor_crane",
}
_STRUCT_CAMP = {
    "camp_log_cabin", "camp_tent", "camp_leanto", "camp_toolbox", "camp_book_crate",
    "camp_star_post", "camp_dark_cairn", "camp_signal_post", "camp_tarp_cache",
    "camp_stake_pen", "camp_crate_desk",
}
_STRUCT_TOWN = {
    "town_manor", "town_cottage", "town_hall", "town_workshop_hut", "town_barn",
    "town_observatory_hut", "town_warehouse", "town_harbor_office", "town_stone_well",
    "town_tank", "town_fenced_yard", "town_writing_desk", "town_cork_board",
    "town_brazier", "town_crate_stacks", "town_compost_row",
}
_STRUCT_BAY = {
    "bay_manor_estate", "bay_townhouse", "bay_wings", "bay_workshop_hall",
    "bay_great_barn", "bay_observatory_dome", "bay_warehouse_row", "bay_well_house",
    "bay_tank_tower", "bay_stable_yard", "bay_archive_bureau", "bay_post_kiosk",
    "bay_plaza_hearth", "bay_container_rows", "bay_compost_works", "bay_steam_packet",
}
STRUCTURES = _STRUCT_HAMLET | _STRUCT_CAMP | _STRUCT_TOWN | _STRUCT_BAY


def check_sprite_opacity(assets_dir, max_semi=0.14, body_top=0.62):
    """A sprite whose BODY went semi-transparent reads as a ghost over the terrain.

    Measured above the base band only: a feathered ground patch at the foot of a
    sprite is deliberate (it melts into the terrain), a see-through wall is a bug.
    Measuring the whole sprite conflates the two and flags 50 healthy sprites.
    """
    bad = []
    for p in sorted(glob.glob(f"{assets_dir}/*.png")):
        im = Image.open(p).convert("RGBA"); px = im.load(); W, H = im.size
        if W < 8 or H < 8: continue
        semi = op = 0
        for y in range(0, int(H*body_top)):
            for x in range(W):
                a = px[x, y][3]
                if a == 0: continue
                if a == 255: op += 1
                elif a > 10: semi += 1
        if semi + op > 60 and semi/(semi+op) > max_semi:
            bad.append(f"{os.path.basename(p)[:-4]} {semi/(semi+op):.0%}")
    return ("sprite_opacity", not bad, f"{len(bad)} sprite BODIES part-transparent: {bad[:8]}", {"art"})


def check_sprite_cutoff(assets_dir, frac=0.72):
    """A dead-flat bottom edge across most of a sprite is the signature of a bad cut."""
    bad = []
    for p in sorted(glob.glob(f"{assets_dir}/*.png")):
        im = Image.open(p).convert("RGBA"); px = im.load(); W, H = im.size
        if W < 12 or H < 12: continue
        bots = []
        for x in range(W):
            ys = [y for y in range(H) if px[x, y][3] > 0]
            if ys: bots.append(ys[-1])
        if len(bots) < 12: continue
        top = Counter(b//2 for b in bots).most_common(1)[0][1]
        if top > len(bots)*frac: bad.append(os.path.basename(p)[:-4])
    return ("sprite_cutoff", not bad, f"{len(bad)} sprites cut flat: {bad[:8]}", {"art"})


def check_state_traceable(bp, state, allowed_ambient):
    """Anything drawn that cannot be traced to a state rule is a bug BY CONSTRUCTION.

    This is the cheapest high-yield check in the file: it caught a hatch frame that
    rendered a full village road network, driveways to empty grass, benches, lamps and
    market goods for a camp that had exactly one building.
    """
    drawn = {s["n"] for s in bp["sprites"]}
    justified = set(state.get("justified", [])) | set(allowed_ambient)
    orphan = sorted(drawn - justified)
    return ("state_traceable", not orphan,
            f"{len(orphan)} sprites with no state justification: {orphan[:10]}",
            {"state", "placement"})


def check_palette(assets_dir, palette_rgb, tol=64, max_off=0.14):
    """Sprites must live in the world's palette; a re-pick can silently swap a variant."""
    bad = []
    for p in sorted(glob.glob(f"{assets_dir}/*.png")):
        im = Image.open(p).convert("RGBA")
        px = list(im.getdata())[::7]
        vis = [q for q in px if q[3] > 128]
        if len(vis) < 40: continue
        off = sum(1 for q in vis
                  if min((q[0]-c[0])**2 + (q[1]-c[1])**2 + (q[2]-c[2])**2 for c in palette_rgb) > tol*tol)
        if off/len(vis) > max_off:
            bad.append(f"{os.path.basename(p)[:-4]} {off/len(vis):.0%}")
    return ("palette", not bad, f"{len(bad)} sprites off-palette: {bad[:8]}", {"art"})


# ============================================================ the four missing surfaces
# Same law as everything above: no compositor, no cutout pipeline, no helper of either.
# Geometry is re-derived from the published contract (sprite x,y = BASE CENTRE, w,h =
# drawn size), terrain is judged on the sprites-free ground layer, and the lamp is
# judged on the finished frame — the glow is applied AFTER the ground layer is written,
# so the ground layer cannot show it. Nothing here ever samples the ground UNDER a
# sprite.
#
# ONE POLICY FOR "I CANNOT JUDGE THIS", applied identically by all four:
#   MISSING INPUT (no render, no ground layer, no assets dir, no era) -> ok=False and
#     NO surface claimed. A check that cannot run has not passed; check_terrain set
#     this precedent and the other three now follow it. Failing open is the defect
#     this whole file exists to prevent.
#   ABSENT SUBJECT (no lighthouse in the frame, no lamp rung in state, no plaza
#     declared) -> ok=True, the words UNJUDGED in the detail, and the affected surface
#     is NOT claimed, so verify.py keeps reporting it as unchecked.
# A surface is claimed only when a real assertion was actually made about this frame.

ERA_ORDER = ["camp", "hamlet", "town", "beyond_bay"]

# The earliest era each BUILT thing can honestly exist in. Re-derived from what the era
# words mean — a camp is people sleeping under canvas, so it has no stone tower, no
# paved market and no street lamps — NOT from the compositor's vocabulary table, which
# is the thing under test. Nature (trees, rocks, flowers, water fowl) is era-neutral and
# deliberately absent: it grows in a camp exactly as it grows in a town. Names absent
# from this table are unconstrained, which keeps the check free of invented failures.
#
# HONEST LIMIT, stated because the check reports it: every floor here is "hamlet", so
# this table can only ever fail a CAMP frame. Above camp it is vacuous, and check_era
# therefore refuses to claim the era surface there rather than printing a zero that
# reads like evidence. Populating town/beyond_bay floors is the work that would make
# the claim real; inventing them from nothing would only manufacture failures.
ERA_MIN = {n: "hamlet" for n in (
    "great_house", "cottage_a", "cottage_b", "cottage_c", "officer_house_a",
    "officer_house_b", "officer_house_c", "library", "workshop", "barn", "chicken_coop",
    "well", "well_house", "water_tank", "warehouse", "harbormaster_hut", "lighthouse",
    "observatory", "chart_tent", "windmill", "watermill_kiln", "market_stall",
    "market_goods", "harbor_crane", "quay_deck", "jetty_plank", "stone_wall",
    "stone_steps", "gate_arch", "bridge_plank", "noticeboard", "flagpole", "firepit",
    "veto_plinth", "journal_desk", "compost_bay", "crop_rows", "crop_wheat",
    "fence_corner", "hedge_run", "boat_packet", "cargo_crates", "cargo_barrels",
    "crate_single", "barrel_single", "lamp_dark", "lamp_lantern", "bench", "flowerbed",
    "potted_plant", "laundry_line", "signpost", "mailbox", "cart", "wheelbarrow",
    "haystack", "scarecrow", "beehives", "veg_garden", "water_trough", "wood_pile",
    "posture_banner", "training_dummy", "fish_drying_rack", "fishing_net", "crab_pots",
    "fish_barrel", "rope_coil", "anchor", "chicken")}

# The mirror direction: SHELTER is what a camp IS. Once the settlement has built itself
# a hamlet, nobody is still living under canvas or out of bundles, so these may not
# appear above era camp. Deliberately NOT every camp_* name: measured across the whole
# rendered timeline (tl_2026-05-25 .. tl_2026-07-26), camp_bare_pole and camp_campfire
# legitimately SURVIVE into the built era — they are unbuilt-RUNG placeholders (a
# flagpole with no pennant, a firepit not yet a gathering circle), not camp vocabulary.
# A blanket camp_* ceiling would have cried wolf on two real frames.
# Known limit: an enumerated set cannot cover a camp shelter added later; the detail
# line says so.
CAMP_SHELTER = {"camp_tent", "camp_leanto", "camp_log_cabin", "camp_tarp_cache",
                "camp_bundles"}

# Rungs that mean the thing is NOT built yet. An object sitting on one of these may not
# render its own finished sprite — that is the "drawn ahead of its measurement" defect.
# "empty_plinth" is deliberately NOT here: an empty plinth is a real object you can see.
EMPTY_RUNG = {None, "none", "bare_ground", "bare_wall", "bare_pole", "dark", "dark_cairn"}

# EXPLICIT ladder(object) -> sprite(art) map. The ladders are keyed by OBJECT
# ("officer_dwellings"), the sprite list by resolved ART NAME ("officer_house_a"), and
# the two namespaces are NOT the same: relying on names that happen to coincide gave
# 13/29 coverage on the hamlet frame and 0/29 on the camp frame, i.e. the arm quietly
# vanished on exactly the frame where "drawn before it was built" is most likely.
# Only relations that are certain from the words are listed. Resolving the rest would
# mean re-implementing the compositor's vocabulary table — the thing under test — so
# instead the coverage is REPORTED as a number and can be seen to shrink.
LADDER_SPRITES = {
    "firepit": {"firepit"}, "flagpole": {"flagpole"}, "great_house": {"great_house"},
    "harbormaster_hut": {"harbormaster_hut"}, "journal_desk": {"journal_desk"},
    "library": {"library"}, "lighthouse": {"lighthouse"}, "noticeboard": {"noticeboard"},
    "observatory": {"observatory"}, "veto_plinth": {"veto_plinth"},
    "warehouse": {"warehouse"}, "well": {"well"}, "workshop": {"workshop"},
    "composter": {"compost_bay"}, "water_store": {"water_tank"},
    "cargo_stacks": {"cargo_crates", "cargo_barrels"},
    "officer_dwellings": {"officer_house_a", "officer_house_b", "officer_house_c"},
    "lantern_posts": {"lamp_lantern", "lamp_dark"},
}


def _drawn_rect(s):
    """Pixel rect of a sprite, from the contract alone: x,y = base centre, w,h = drawn."""
    x0 = int(s["x"] - s["w"]/2.0)
    y0 = int(s["y"] - s["h"])
    return (x0, y0, x0 + int(s["w"]), y0 + int(s["h"]))


def _rect_overlap(a, b):
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    return (ix*iy, ix, iy) if (ix > 0 and iy > 0) else (0, 0, 0)


_MASK_CACHE = {}


def _sprite_mask(assets_dir, name, w, h, thr=170):
    """Opaque mask of a sprite AS DRAWN, taken from its own art file.

    Alpha is used, never colour: the compositor grades every sprite by depth and lays a
    blurred shadow under it, so raw art colours do NOT survive into the frame (measured:
    RMS 63-118 per pixel). Shape does. The mask is intersected with its own mirror so a
    horizontally flipped paste can never make the check read the wrong pixels.
    """
    key = (assets_dir, name, int(w), int(h))
    if key in _MASK_CACHE: return _MASK_CACHE[key]
    p = os.path.join(assets_dir or "", name + ".png")
    if not assets_dir or not os.path.exists(p):
        _MASK_CACHE[key] = None
        return None
    im = Image.open(p).convert("RGBA").resize((max(1, int(w)), max(1, int(h))), Image.NEAREST)
    a = list(im.getchannel("A").getdata())
    mw, mh = im.size
    m = [[(a[y*mw + x] >= thr and a[y*mw + (mw-1-x)] >= thr) for x in range(mw)]
         for y in range(mh)]
    _MASK_CACHE[key] = (m, mw, mh)
    return _MASK_CACHE[key]


def _cover_grid(sprites, W, H, S=4, pad=0):
    """How many sprite rects (optionally grown by `pad`) touch each cell.

    pad=0 finds a sprite's EXCLUSIVE pixels; a padded pass finds ground far enough from
    every sprite that nothing — not even a sprite's blurred shadow, which spills well
    outside its rect — should have painted there.
    """
    gw, gh = W//S + 2, H//S + 2
    cov = [[0]*gw for _ in range(gh)]
    for s in sprites:
        x0, y0, x1, y1 = _drawn_rect(s)
        for gy in range(max(0, (y0-pad)//S), min(gh, (y1+pad)//S + 1)):
            row = cov[gy]
            for gx in range(max(0, (x0-pad)//S), min(gw, (x1+pad)//S + 1)):
                row[gx] += 1
    return cov, S


def _grade_lut(cp, gp, cov, S, W, H, step=3):
    """Learn THIS frame's grade from pixels no sprite touches.

    The ground layer is written before the golden-hour pass, so a raw composite-vs-ground
    difference fires on 100.0% of sprite-free pixels — measured — and a check built on it
    can never fail. Fitting the frame's own transform from sprite-free ground drops the
    residual to 0.2%, which makes "this pixel differs from the ground" mean "a sprite
    painted here" again. Self-calibrating: no grade constant is imported or assumed.
    """
    acc = {}
    for y in range(0, H, step):
        gy = y//S
        for x in range(0, W, step):
            if cov[gy][x//S]: continue
            g = gp[x, y]; q = cp[x, y]
            for c in range(3):
                k = (c, g[c] >> 3)
                v = acc.get(k)
                if v is None: acc[k] = [q[c], 1]
                else:
                    v[0] += q[c]; v[1] += 1
    return {k: v[0]/v[1] for k, v in acc.items() if v[1] >= 20}


def _residual(lut, g, q):
    """|composite - graded ground| for one pixel, or None if this frame never showed the
    compositor an untouched pixel of that ground tone.

    Falling back to the RAW ground value for an unseen bin (the obvious shortcut) is
    biased in one direction only — the ungraded value is systematically darker, which
    inflates the residual and invents both "the sprite painted here" and "undeclared
    paint". It fires precisely on ground tones that exist ONLY under sprites (quay
    planks beneath crates, lane beneath a cart), so the bias lands where the check is
    least able to notice. Unseen bins are counted as unjudged instead.
    """
    d = 0
    for c in range(3):
        e = lut.get((c, g[c] >> 3))
        if e is None: return None
        d += abs(q[c] - e)
    return d


def check_paint_fidelity(render, bp, assets_dir, mark_floor=0.12, tie=2, tie_overlap=0.55,
                         stray_max=0.002, judged_floor=0.40):
    """Every declared sprite really painted, and nothing else did. NOT draw order.

    DRAW ORDER AND OCCLUSION ARE NOT VERIFIED BY THIS CHECK, and it claims neither.
    The blueprint's sprite array is PLACEMENT order, not paint order (measured: 0.54 of
    adjacent pairs ascend in base y on the hamlet frame, 0.50 on the camp frame — an
    order-reading test would report 130 and 47 "inversions" on two frames with nothing
    wrong with them). An earlier draft kept a conditional order arm that only ran at
    0.98 sortedness — it never ran on any real frame, and its detail line told the
    operator "order read from pixels instead", which nothing in the code did. A check
    that reports a surface it did not examine is worse than no check, so the arm and
    the sentence are gone and `depth` stays on verify.py's NOT-CHECKED list where it
    belongs.

    What IS checked, on the pixels:
      PAINT FIDELITY — every sprite must actually paint. Measured on the pixels only
      that sprite can reach (no other rect covers them), against the frame's own
      grade-fitted ground. A sprite in the blueprint that left no mark was dropped,
      fully overpainted, or never composited.
      UNDECLARED PAINT — ground far enough from every declared sprite to be out of
      reach of even a blurred shadow must still match the ground layer. Art in the
      frame that the layout data knows nothing about is the mirror image of the defect
      state_traceable hunts, and neither check can see the other's half. Sensitivity,
      measured: a 120x120 blob fires (0.61%), a 60x60 blob does not (0.16%).
      TIED DEPTH — two STRUCTURES that overlap heavily with the same base y have no
      defined order: a stable sort hands the decision to placement accident, so the
      occlusion flips between renders for no reason anyone can see. Restricted to
      structures for the same reason check_stacking is: a fence run enclosing a veg
      garden sits on the garden's own base row by design (measured on the good hamlet
      frame at |dy|=7, five pixels from tripping an unrestricted arm).

    COVERAGE IS PART OF THE RESULT, not a footnote: sprites whose exclusive pixels are
    too few to judge are counted and the judged fraction leads the detail. A frame
    where the arm judged almost nothing (bad assets dir, a cutout regression that
    blanked the alpha it reads) FAILS instead of reporting a green built on 0 sprites.
    """
    ss = bp.get("sprites", [])
    ground = os.path.splitext(render)[0] + ".ground.png"
    for path, what in ((render, "render"), (ground, "ground layer"),
                       (assets_dir, "assets dir")):
        if not path or not os.path.exists(path):
            return ("paint_fidelity", False,
                    f"no {what} at {path!r} — paint fidelity UNVERIFIABLE, not passed", set())
    if not ss:
        return ("paint_fidelity", True, "blueprint declares no sprites — UNJUDGED", set())

    FR = Image.open(render).convert("RGB"); cp = FR.load(); W, H = FR.size
    G = Image.open(ground).convert("RGB"); gp = G.load()
    if G.size != FR.size:
        return ("paint_fidelity", False,
                f"ground layer {G.size} != render {FR.size} — UNVERIFIABLE, not passed", set())

    notes = []
    bad_mark = []
    unjudged = 0

    # ---- tied depth (blueprint; exact data, no pixels needed)
    tied = []
    for i in range(len(ss)):
        a = ss[i]
        if a["n"] not in STRUCTURES: continue
        ra = _drawn_rect(a)
        for j in range(i+1, len(ss)):
            b = ss[j]
            if b["n"] not in STRUCTURES: continue
            if abs(a["y"] - b["y"]) > tie: continue
            rb = _drawn_rect(b)
            inter, _, _ = _rect_overlap(ra, rb)
            if not inter: continue
            aa = max(1, (ra[2]-ra[0])*(ra[3]-ra[1]))
            ab = max(1, (rb[2]-rb[0])*(rb[3]-rb[1]))
            if inter/min(aa, ab) >= tie_overlap:
                tied.append(f"{a['n']}@{a['y']}/{b['n']}@{b['y']}")

    # ---- paint fidelity (pixels)
    cov, S = _cover_grid(ss, W, H)
    lut = _grade_lut(cp, gp, cov, S, W, H)
    for s in ss:
        m = _sprite_mask(assets_dir, s["n"], s["w"], s["h"])
        if m is None: unjudged += 1; continue
        mask, mw, mh = m
        x0, y0, x1, y1 = _drawn_rect(s)
        ex = mark = 0
        for y in range(y0, y1, 2):
            if not (0 <= y < H): continue
            ly = y - y0
            if not (0 <= ly < mh): continue
            row = mask[ly]; gy = y//S
            for x in range(x0, x1, 2):
                lx = x - x0
                if not (0 <= x < W and 0 <= lx < mw) or not row[lx]: continue
                if cov[gy][x//S] != 1: continue      # someone else could paint here
                d = _residual(lut, gp[x, y], cp[x, y])
                if d is None: continue               # ground tone never seen untouched
                ex += 1
                if d > 45: mark += 1
        if ex < 30: unjudged += 1; continue
        if mark/ex < mark_floor:
            bad_mark.append(f"{s['n']}@{s['x']},{s['y']} {mark/ex:.0%}")

    judged = len(ss) - unjudged
    jfrac = judged/max(1, len(ss))

    # ---- paint where nothing was declared (measured at 0.00-0.01% on good frames)
    far, tot = 0, 0
    near, _ = _cover_grid(ss, W, H, S, pad=24)
    for y in range(0, H, 4):
        gy = y//S
        for x in range(0, W, 4):
            if near[gy][x//S]: continue
            d = _residual(lut, gp[x, y], cp[x, y])
            if d is None: continue
            tot += 1
            if d > 60: far += 1
    stray_paint = far/max(1, tot)
    # The VERDICT uses the same noise floors that gate the note. Without them a dense or
    # zoomed frame fails on a couple of dozen pixels of grade-fit residual that this
    # check's own author judged too small to describe.
    stray_bad = tot > 2000 and far > 40 and stray_paint > stray_max
    if stray_bad:
        notes.append(f"{stray_paint:.2%} of open ground carries undeclared paint")

    thin = jfrac < judged_floor
    if thin:
        notes.append(f"judged only {jfrac:.0%} of sprites — below the {judged_floor:.0%} "
                     "floor, so a green here would mean nothing")
    notes.append("draw order NOT verified (see docstring); undeclared paint blind below ~100x100px")

    ok = not bad_mark and not tied and not stray_bad and not thin
    detail = (f"judged {judged}/{len(ss)} sprites ({jfrac:.0%}); "
              f"{len(bad_mark)} left no mark {bad_mark[:5]}; "
              f"{len(tied)} tied-depth structure pairs {tied[:4]}; "
              f"undeclared paint {stray_paint:.2%}; " + "; ".join(notes))
    return ("paint_fidelity", ok, detail, {"placement"})


def check_era(bp, state):
    """Vocabulary against the era, and nothing rendered ahead of its own measurement.

    Two crossings, both independent of the compositor:
      ERA FLOOR — a built thing may not appear before the era that can hold it, re-derived
      from what the era words mean. HONEST LIMIT: every floor in ERA_MIN is "hamlet", so
      this arm can only fail a CAMP frame. On hamlet and above it is structurally
      incapable of firing, and the check REFUSES TO CLAIM the era surface there rather
      than printing "0 future-rung" — a zero that reads like evidence and carries none.
      CAMP SHELTER CEILING — canvas and bundles may not survive into a built era.
      RUNG — an object may not render its finished sprite while its own ladder says the
      thing is not built, or while nothing has been measured. Ladder keys are OBJECT
      names and sprite names are resolved ART names, so the pairing is an EXPLICIT map
      (LADDER_SPRITES) whose coverage is reported; the previous name-coincidence pairing
      silently covered 0 of 29 ladders on the camp frame.

    DELETED, deliberately: an arm that failed on `drawn - state.justified`. It is a
    tautology against real compositor output — the emitter adds a name to justified in
    the same breath as it places the sprite, measured empty on both good frames — and
    where it was not tautological it was a second, worse copy of check_state_traceable
    that ignored the ambient allowlist verify.py passes, so the two registered checks
    contradicted each other on the same frame. A check that restates the emitter cannot
    catch the emitter being wrong.
    """
    ss = bp.get("sprites", [])
    drawn = {s["n"] for s in ss}
    era = (state or {}).get("era")
    ladders = (state or {}).get("ladders") or {}

    if era not in ERA_ORDER:
        return ("era", False, f"no usable era in the blueprint ({era!r}) — vocabulary "
                "UNVERIFIABLE, not passed", set())
    ei = ERA_ORDER.index(era)
    bad = []

    future = sorted(n for n in drawn
                    if n in ERA_MIN and ERA_ORDER.index(ERA_MIN[n]) > ei)
    bad += [f"{n} (needs {ERA_MIN[n]})" for n in future]

    stale = sorted(n for n in drawn if n in CAMP_SHELTER) if ei > 0 else []
    bad += [f"{n} (camp shelter above camp)" for n in stale]

    ahead = []
    judged_ladders = 0
    for obj, arts in sorted(LADDER_SPRITES.items()):
        if obj not in ladders: continue
        hit = sorted(arts & drawn)
        if not hit: continue
        judged_ladders += 1
        e = ladders.get(obj) or {}
        if e.get("stage") in EMPTY_RUNG:
            ahead.append(f"{'/'.join(hit)} drawn at {obj} rung {e.get('stage')!r}")
        elif not e.get("measured", False):
            ahead.append(f"{'/'.join(hit)} drawn while {obj} is unmeasured")
    bad += ahead

    # Claim the era surface only where the floor table can actually catch something from
    # a future rung — which is what that surface means. Above the highest floor the arm
    # is vacuous and says so; the shelter ceiling and the rung arm still RUN and can
    # still fail, they just do not buy the era surface.
    guarded_up = any(ERA_ORDER.index(v) > ei for v in ERA_MIN.values())
    unmapped = sorted(set(ladders) - set(LADDER_SPRITES))
    notes = [f"rung arm: {judged_ladders} of {len(ladders)} ladders judged, "
             f"{len(unmapped)} unmapped ({unmapped[:4]})"]
    if not guarded_up:
        notes.append(f"NO vocabulary floor exists above {era} — future-rung vocabulary "
                     "UNVERIFIED at this era (era surface not claimed)")
    if ei > 0:
        notes.append(f"camp-shelter ceiling covers {len(CAMP_SHELTER)} enumerated names only")

    return ("era", not bad,
            f"era={era}: {len(future)} future-rung, {len(stale)} stale-camp, "
            f"{len(ahead)} ahead-of-rung {bad[:6]}; " + "; ".join(notes),
            {"era"} if guarded_up else set())


def _disc(px, W, H, ax, ay, r0, r1, step=2):
    """Mean luminance, warmth and near-white fraction of a ring, from the FINISHED frame."""
    n = 0; sl = 0.0; sw = 0.0; wht = 0
    for dy in range(-r1, r1+1, step):
        for dx in range(-r1, r1+1, step):
            d = math.hypot(dx, dy)
            if not (r0 <= d < r1): continue
            x, y = ax+dx, ay+dy
            if not (0 <= x < W and 0 <= y < H): continue
            r, g, b = px[x, y][:3]
            n += 1; L = (r+g+b)/3.0
            sl += L; sw += (r - b)
            if L >= 230 and b >= 195: wht += 1
    if not n: return None
    return (sl/n, sw/n, wht/n, n)


def check_light(render, bp, state,
                lum=(95, 180), sat=(0.20, 0.65), std_min=15.0, blowout=0.06, span_min=90,
                core_white=0.45, core_lum=222.0, halo_warm=30.0):
    """The golden-hour grade, and the lighthouse lamp. NOT shadows.

    GRADE (always run): a frame washed toward white, flattened, or drained of colour is
    the failure the golden-hour pass keeps threatening. Bounds are set from measured good
    frames (mean 151-153, std 23-27, saturation 0.41, blown 0.2%, span 167) and every one
    of them is tripped by a synthetic wash, flatten or desaturate.

    LAMP: the glow must be present exactly when state says the lamp is lit — and the
    check only says that when state actually SAYS something. A missing lighthouse_lamp
    rung, stage=None, or measured=False is UNJUDGED, never read as "the lamp is off":
    the previous draft collapsed absent into dark and hard-failed two correctly-lit,
    visually-confirmed frames whose blueprints simply predate the state emitter.

    DETECTION, re-derived across all 17 rendered frames that contain a lighthouse, after
    the single-frame calibration it replaces was falsified. Two conditions that fail
    independently, because the earlier near-white-plus-brightness rule sat 13/255 from a
    false accusation:
      A BLOWN NEAR-WHITE CORE — kills the nine unlit copper-roofed towers, which measure
      0.00-0.03 near-white against the lit lamp's 0.62.
      A WARM HALO IMMEDIATELY OUTSIDE IT — kills sunlit sand, which is the real hazard:
      on tl_2026-07-08 the brightest disc on the tower axis is BEACH, and it measures
      0.68 near-white, HIGHER than the lit lamp. Its halo measures r-b = 9 against the
      lamp's 61-64, because a lamp is a point source with an amber falloff and sand is a
      broad neutral field. Verified invariant to the exact perturbation that broke the
      old rule: lifting that frame uniformly by +10..+40 never produces a false "lit"
      (the old rule flipped at +20); warming it by +10..+30 never does either; doing both
      at once leaves the core 4 units under the bound AND blows the grade arm's
      saturation, so one of the two arms always fires. Erasing the glow from the lit
      frame is caught.
    Whether the tower itself rendered is check_paint_fidelity's question, not this one's.
    Shadows are NOT measured by anything here, which is why this returns `grade`/`lamp`
    and never the coarse `light` surface.
    """
    if not os.path.exists(render):
        return ("light", False, f"no render at {render} — UNVERIFIABLE, not passed", set())
    im = Image.open(render).convert("RGB"); px = im.load(); W, H = im.size
    n = 0; sl = 0.0; sl2 = 0.0; ss_ = 0.0; white = 0
    hist = [0]*256
    for y in range(0, H, 5):
        for x in range(0, W, 5):
            r, g, b = px[x, y]
            n += 1; L = (r+g+b)/3.0
            sl += L; sl2 += L*L; hist[int(L)] += 1
            mx, mn = max(r, g, b), min(r, g, b)
            ss_ += 0.0 if mx == 0 else (mx-mn)/mx
            if L >= 246: white += 1
    mean = sl/n; sd = math.sqrt(max(0.0, sl2/n - mean*mean)); satm = ss_/n
    c = 0; p01 = p99 = 0
    for i, v in enumerate(hist):
        c += v
        if not p01 and c >= n*0.01: p01 = i
        if c >= n*0.99: p99 = i; break
    bad = []
    if not (lum[0] <= mean <= lum[1]): bad.append(f"mean L {mean:.0f} outside {lum}")
    if sd < std_min: bad.append(f"contrast {sd:.1f} < {std_min}")
    if not (sat[0] <= satm <= sat[1]): bad.append(f"saturation {satm:.2f} outside {sat}")
    if white/n > blowout: bad.append(f"blown highlights {white/n:.1%}")
    if p99-p01 < span_min: bad.append(f"tonal span {p99-p01} < {span_min}")

    surfaces = {"grade"}
    lamp = ((state or {}).get("ladders") or {}).get("lighthouse_lamp")
    towers = [s for s in bp.get("sprites", []) if s["n"] == "lighthouse"]

    # ---- what the frame shows
    glow = None; lampdesc = "no lighthouse drawn"
    if towers:
        s = max(towers, key=lambda t: t["w"]*t["h"])
        R = max(8, int(s["w"]*0.16))
        best = None
        # Search only the tower's own axis. A wider hunt wanders onto the beach, and
        # sunlit sand scores HIGHER on near-white than the lamp does (measured 0.68).
        for ay in range(int(s["y"]-s["h"]-0.10*s["h"]), int(s["y"]-s["h"]+0.28*s["h"]), 3):
            for ax in range(int(s["x"]-0.30*s["w"]), int(s["x"]+0.30*s["w"])+1, 3):
                d = _disc(px, W, H, ax, ay, 0, R)
                if d and (best is None or d[0] > best[0][0]): best = (d, ax, ay)
        if best:
            (mL, mW, wht, _), ax, ay = best
            halo = _disc(px, W, H, ax, ay, R, int(R*1.7))
            hw = halo[1] if halo else 0.0
            glow = (wht >= core_white and mL >= core_lum and hw >= halo_warm)
            lampdesc = f"core L{mL:.0f} white {wht:.2f} warm {mW:.0f}, halo warm {hw:.0f}"
        else:
            lampdesc = "lamp region unsampleable"

    # ---- what state claims, and only then a verdict
    if not isinstance(lamp, dict) or lamp.get("stage") is None or not lamp.get("measured"):
        lampstate = ("UNJUDGED — no measured lighthouse_lamp rung in state "
                     f"({lamp if lamp else 'absent'}); frame shows: {lampdesc}")
    else:
        surfaces.add("lamp")
        lit = lamp.get("stage") == "lit"
        lampstate = f"state {lamp.get('stage')!r} — {lampdesc}"
        if lit and not towers:
            bad.append("lamp says lit but no lighthouse is drawn")
        elif lit and glow is None:
            bad.append(f"lamp says lit but the tower top could not be sampled ({lampdesc})")
        elif lit and glow is False:
            bad.append(f"lamp lit but no glow at the tower top ({lampdesc})")
        elif not lit and glow is True:
            bad.append(f"lamp glowing but state rung is {lamp.get('stage')!r} ({lampdesc})")

    return ("light", not bad,
            f"grade mean {mean:.0f} sd {sd:.0f} sat {satm:.2f} span {p99-p01}; "
            f"lamp: {lampstate}; shadows NOT checked"
            + (f"; FAIL {bad}" if bad else ""),
            surfaces)


# ---------------------------------------------------------------- terrain, from GROUND
# Classes measured off the rendered ground layer, not taken from the terrain generator.
def _is_water(p):
    r, g, b = p[:3]
    return b - r > 24 and b > 80


def _is_sand(p):
    r, g, b = p[:3]
    return (r+g+b)/3.0 >= 172 and r > b and r-b < 95 and g > b


def _is_stone(p):
    """Cobble, paving and dirt: warm-neutral, mid-toned. Brighter than this is sand."""
    r, g, b = p[:3]
    if _is_water(p) or _is_sand(p): return False
    return r >= g >= b and 100 <= (r+g+b)/3.0 < 172 and (r-b) >= 22


def _is_cultivated(p):
    """Ploughed soil or standing crop.

    MEASURED, correcting a docstring that claimed 0.00 on open grass: on the hamlet
    ground layer this fires on 5.7% of non-field dry land and on 1.1% of the camp's,
    against 66-75% inside the three declared field plots. The earlier form fired on
    15.2% because bright plaza paving (176,157,131) satisfied its standing-crop clause —
    a fake field declared on the town square measured 99.8% "tilled". Paving is now
    excluded by luminance, which is what actually separates soil (mean 92-103) from
    paving (mean 155-160).

    KNOWN CONFLATION, stated rather than hidden: wet quay planking is the same warm
    brown as tilled soil, so a field declared on the wharf still reads as cultivated.
    Separating those two needs more than a colour predicate.
    """
    r, g, b = p[:3]
    if _is_water(p) or _is_sand(p): return False
    L = (r+g+b)/3.0
    if r > g > b and r-b >= 40 and L < 140: return True          # bare tilled soil
    if g >= 128 and r-b >= 34 and g-b >= 45 and L < 170: return True  # standing crop
    return False


def check_terrain(render, bp, state=None, coast_min=0.45, plaza_paved=0.25, field_min=0.45):
    """Ground, coastline, water, field and plaza masks — judged on the SPRITES-FREE layer.

    The composite may never be used here: a green roof would read as pasture and a stone
    wall as paving, which is the same "looking through a sprite" mistake that let props
    stand in the road for three clean reports. No ground layer means the surface is
    UNVERIFIED, and this says so rather than falling back to the frame.

    field_min is 0.45: measured, the three real field plots read 66-75% cultivated and
    non-field dry land reads 5.7%, so the floor sits 21 points under the weakest real
    field and 8x above the background. The old 0.25 sat inside the noise once the plaza
    was excluded from the classifier.

    The plaza arm is ERA-AWARE, because the alternative is a threshold whose job is to
    switch the assertion off: a declared square that draws no paving used to be reported
    as a green with a footnote, so erasing every stone pixel inside it PASSED. A camp
    legitimately has no paving (measured 5% stone); a hamlet that lost its paving is a
    defect, and the blueprint's plaza is also the exemption zone check_on_road trusts,
    so a fictional square silently excuses props standing in the road.
    """
    ground = os.path.splitext(render)[0] + ".ground.png"
    if not os.path.exists(ground):
        return ("terrain", False, f"no ground layer at {ground} — terrain UNVERIFIABLE, "
                "not passed", set())
    im = Image.open(ground).convert("RGB"); px = im.load(); W, H = im.size
    bad = []; notes = []
    era = (state or {}).get("era")

    # ---- water surrounds the land: the canvas rim must be sea all the way round
    rim = []
    for x in range(0, W, 7): rim += [px[x, 2], px[x, H-3]]
    for y in range(0, H, 7): rim += [px[2, y], px[W-3, y]]
    rimw = sum(1 for p in rim if _is_water(p))/max(1, len(rim))
    if rimw < 0.98: bad.append(f"canvas rim only {rimw:.0%} water — land runs off frame")

    # ---- one island: land as a single connected mass
    S = 8; gw, gh = W//S, H//S
    land = [[not _is_water(px[x*S, y*S]) for x in range(gw)] for y in range(gh)]
    sand = [[_is_sand(px[x*S, y*S]) for x in range(gw)] for y in range(gh)]
    nland = sum(sum(1 for v in row if v) for row in land)
    seen = [[False]*gw for _ in range(gh)]
    comps = []
    for sy in range(gh):
        for sx in range(gw):
            if not land[sy][sx] or seen[sy][sx]: continue
            stack = [(sx, sy)]; seen[sy][sx] = True; cnt = 0
            while stack:
                cx, cy = stack.pop(); cnt += 1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx+dx, cy+dy
                    if 0 <= nx < gw and 0 <= ny < gh and land[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True; stack.append((nx, ny))
            comps.append(cnt)
    comps.sort(reverse=True)
    if not nland:
        bad.append("no land at all")
    else:
        if comps[0]/nland < 0.97:
            bad.append(f"land is fragmented — largest mass only {comps[0]/nland:.0%}")
        stray = [c for c in comps[1:] if c/nland > 0.015]
        if stray: bad.append(f"{len(stray)} stray land masses {stray}")

    # ---- the coast wears a beach
    coast = [(x, y) for y in range(1, gh-1) for x in range(1, gw-1)
             if land[y][x] and not all(land[y+dy][x+dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
    if coast:
        hit = 0
        for x, y in coast:
            if any(sand[ry][rx]
                   for ry in range(max(0, y-3), min(gh, y+4))
                   for rx in range(max(0, x-3), min(gw, x+4))): hit += 1
        band = hit/len(coast)
        if band < coast_min: bad.append(f"coastline has no beach band ({band:.0%})")
        notes.append(f"beach {band:.0%}")

    # ---- the square is where the blueprint says, is on dry land, and is paved if the
    #      era says the settlement builds
    pz = bp.get("plaza")
    if not pz:
        notes.append("no plaza declared — square UNJUDGED")
    else:
        cx, cy, rx, ry = pz
        def sweep(sin, sout):
            st = w = t = 0
            for y in range(int(cy-ry*sout), int(cy+ry*sout), 3):
                for x in range(int(cx-rx*sout), int(cx+rx*sout), 3):
                    if not (0 <= x < W and 0 <= y < H): continue
                    d = ((x-cx)/max(1, rx))**2 + ((y-cy)/max(1, ry))**2
                    if not (sin*sin <= d <= sout*sout): continue
                    p = px[x, y]; t += 1
                    if _is_water(p): w += 1
                    elif _is_stone(p): st += 1
            return (st/max(1, t), w/max(1, t))
        pv, pw = sweep(0.0, 1.0)
        av, _ = sweep(1.15, 1.55)
        if pw > 0.05: bad.append(f"declared square is {pw:.0%} water")
        if pv >= plaza_paved:
            if pv < av*2.0:
                bad.append(f"square paving {pv:.0%} no denser than its surroundings {av:.0%}")
            notes.append(f"square paved {pv:.0%} vs {av:.0%} outside")
        elif era is None:
            notes.append(f"square draws no paving ({pv:.0%} stone) and the blueprint "
                         "carries no era — UNJUDGED")
        elif era == "camp":
            notes.append(f"square unpaved ({pv:.0%} stone) — expected at era camp")
        else:
            bad.append(f"declared square draws no paving ({pv:.0%} stone) at era {era}")

    # ---- every declared field really is cultivated ground
    thin = 0
    flds = bp.get("fields") or []
    if not flds: notes.append("no fields declared — UNJUDGED")
    for i, fr in enumerate(flds):
        fx, fy, fw, fh = fr
        cult = ln = tot = 0
        for y in range(int(fy-fh), int(fy+fh), 3):
            for x in range(int(fx-fw), int(fx+fw), 3):
                if not (0 <= x < W and 0 <= y < H): continue
                if ((x-fx)/max(1, fw))**2 + ((y-fy)/max(1, fh))**2 > 1.0: continue
                tot += 1; p = px[x, y]
                if _is_water(p): continue
                ln += 1
                if _is_cultivated(p): cult += 1
        if not tot or ln/tot < 0.25: thin += 1; continue
        if cult/max(1, ln) < field_min:
            bad.append(f"field {i} at {fx},{fy} is bare ground ({cult/max(1,ln):.0%} tilled)")
    if thin: notes.append(f"{thin} field regions too far offshore to judge")

    # ---- no lane wanders off the island
    q = bp.get("quay"); cove = bp.get("cove")
    for nm, pts in (bp.get("lanes") or {}).items():
        off = 0; tot = 0
        for i in range(len(pts)-1):
            (x0, y0), (x1, y1) = pts[i], pts[i+1]
            steps = int(math.hypot(x1-x0, y1-y0)/6) + 1
            for t in range(steps+1):
                x = x0 + (x1-x0)*t/steps; y = y0 + (y1-y0)*t/steps
                if not (0 <= x < W and 0 <= y < H): off += 1; tot += 1; continue
                tot += 1
                if not _is_water(px[int(x), int(y)]): continue
                # the harbour approach is allowed to leave the shore: a wharf and a
                # landing beach are things you walk onto on purpose.
                if q and q[0] <= x <= q[2] and q[1] <= y <= q[3]: continue
                if cove and math.hypot(x-cove[0], y-cove[1]) <= cove[2]: continue
                off += 1
        if off: bad.append(f"lane {nm} runs {off}/{tot} samples into open water")

    return ("terrain", not bad,
            (f"{len(bad)} defects {bad[:4]}; " if bad else "") + "; ".join(notes),
            {"terrain"})


# ==================================================== depth order, from the ID buffer
# Draw order genuinely cannot be recovered from a finished frame — a proposed check that
# claimed it could was deleted for saying so while verifying nothing. It CAN be recovered
# from an id buffer: the same layers, same order, same alpha, each a unique flat colour.
# The compositor emits one; this decides independently whether the layer that WON each
# contested pixel is the layer that should have won it.
#
# The rule for a 2:1 isometric world: of two layers overlapping a pixel, the one whose
# BASE is lower on screen is nearer the camera and must be in front. Ties are legal
# (a sprite and its own shadow, two things on the same ground line).

def _load_ids(render):
    p = os.path.splitext(render)[0] + ".ids.png"
    return Image.open(p).convert("RGB") if os.path.exists(p) else None


def check_depth_order(render, bp, step=3, tol=1.5, max_report=8):
    """Who won each CONTESTED pixel, decided from two id buffers.

    Forward order gives the last layer painted at a pixel; reverse order gives the
    first. Where they differ, at least two OPAQUE layers contested it — which rect
    overlap alone can never tell you, since most of a tree's rect is air. The nearer
    layer (lower base on screen, 2:1 isometric) must be the one in front.
    """
    ids = _load_ids(render)
    p_rev = os.path.splitext(render)[0] + ".idsrev.png"
    layers = bp.get("layers")
    if ids is None or not os.path.exists(p_rev) or not layers:
        return ("depth_order", False, "no id buffers emitted — draw order UNPROVABLE", set())
    rev = Image.open(p_rev).convert("RGB")
    by_rgb = {tuple(l["rgb"]): l for l in layers}
    W, H = ids.size
    a, b = ids.load(), rev.load()
    bad, contested = [], 0
    for y in range(0, H, step):
        for x in range(0, W, step):
            ca, cb = a[x, y], b[x, y]
            if ca == cb or ca == (0, 0, 0) or cb == (0, 0, 0): continue
            near, far = by_rgb.get(ca), by_rgb.get(cb)
            if near is None or far is None: continue
            contested += 1
            if far["sort_y"] > near["sort_y"] + tol:
                bad.append((x, y, near["id"], far["id"]))
    ok = not bad
    detail = (f"{len(bad)} of {contested} contested pixels won by the FARTHER layer "
              f"{bad[:max_report]}" if bad
              else f"draw order correct on all {contested} contested pixels")
    return ("depth_order", ok, detail, {"depth_order", "occlusion"})


def check_shadows(render, bp, min_frac=0.55, drop=3.0):
    """A shadow is a LOCAL darkening, so it must be measured locally.

    Comparing the finished frame against the sprites-free ground layer measures the
    golden-hour GRADE, not the shadow — the grade is applied after the ground layer is
    written, and every sample came back brighter, not darker. Instead compare ground
    beside a sprite's foot against bare ground further out, both post-grade, using the
    id buffer to guarantee the reference really is bare.
    """
    ids = _load_ids(render)
    if ids is None:
        return ("shadows", False, "no id buffer — cannot find bare ground to compare against", set())
    f = Image.open(render).convert("RGB").load()
    idp = ids.load()
    im = Image.open(render); W, H = im.size

    def lum_(p): return 0.299*p[0] + 0.587*p[1] + 0.114*p[2]

    def bare_near(x, y, r):
        out = []
        for ang in (0.4, 1.2, 2.0, 2.8, 3.6, 4.4, 5.2, 6.0):
            xx = int(x + math.cos(ang)*r); yy = int(y + math.sin(ang)*r*0.7)
            if 0 <= xx < W and 0 <= yy < H and idp[xx, yy] == (0, 0, 0):
                out.append(lum_(f[xx, yy]))
        return out

    want = [s for s in bp["sprites"] if s["w"] >= 46 and s["h"] >= 46]
    cast, judged = 0, 0
    for s in want:
        x, y, w = s["x"], s["y"], s["w"]
        ref = bare_near(x, y, max(70, int(w*1.5)))
        if len(ref) < 3: continue
        base = sum(ref)/len(ref)
        near = []
        for fx in (-0.36, -0.14, 0.14, 0.36):
            for dy in (3, 7, 12):
                xx, yy = int(x + w*fx), int(y + dy)
                if 0 <= xx < W and 0 <= yy < H and idp[xx, yy] == (0, 0, 0):
                    near.append(lum_(f[xx, yy]))
        if len(near) < 3: continue
        judged += 1
        if sum(near)/len(near) < base - drop: cast += 1
    if not judged:
        return ("shadows", False, "no sprite had both a foot sample and a bare reference", set())
    frac = cast/judged
    return ("shadows", frac >= min_frac,
            f"{cast}/{judged} large sprites darken the ground at their foot ({frac:.0%})",
            {"shadows"})
