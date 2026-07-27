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

THE SECOND RULE, paid for on 2026-07-27: A CHECK THAT COULD NOT RUN HAS NOT
PASSED. check_shadows was found green on a frame with EVERY SHADOW DELETED, and the
audit that followed found the same shape in eight more arms: three globbed an assets
directory, so pointing them at a path that does not exist made the loop never run and
each reported "0 problems" and PASSED; five more passed over an empty list, an absent
state key or zero contested pixels. A loop with nothing in it prints a zero, and a
zero reads like evidence.

So every arm here separates two cases that are NOT the same thing:

  INPUT MISSING — no ground layer, no assets directory, no id buffer, no state key.
    RED, the word UNVERIFIABLE in the detail, and the arm CLAIMS NO SURFACE. Never a
    pass: the check did not run.
  SUBJECT ABSENT — no lanes on this frame, no lamp in this state, no plaza declared.
    Green ONLY where that absence is legal for this frame (a camp has no town
    square), and then the detail says UNJUDGED and the arm CLAIMS NO SURFACE, so
    verify.py goes on reporting it unchecked. Where the absence is itself the defect
    — a built settlement with no lanes, a blueprint with no sprites — it is RED.
  AND EVERY COUNTING ARM STATES ITS DENOMINATOR and goes red under a floor, so
    "0 problems out of 0 things judged" can never read as a pass. paint_fidelity set
    that precedent; the other eleven now follow it.

An honest zero must stay green; a silent hole must not.
"""
from __future__ import annotations
import json, math, os, glob
from collections import Counter
from PIL import Image, ImageChops, ImageFilter

# The four eras, oldest first. Up here rather than beside the era tables because five
# arms now consult it to decide whether an absence is legal at this rung.
ERA_ORDER = ["camp", "hamlet", "town", "beyond_bay"]
BUILT_ERAS = ("hamlet", "town", "beyond_bay")


# ------------------------------------------------------------------- the two absences
# Three one-line constructors, so the distinction in the module docstring is visible at
# every call site instead of being re-argued in prose each time one is needed.
def _unverifiable(name, why):
    """INPUT MISSING: red, no surface claimed. The check did not run."""
    return (name, False, f"{why} — UNVERIFIABLE, not passed", set())


def _illegal(name, why):
    """SUBJECT ABSENT and the absence is itself the defect: red, no surface claimed."""
    return (name, False, why, set())


def _unjudged(name, why):
    """SUBJECT ABSENT and legally so: green, and no surface claimed."""
    return (name, True, f"{why} — UNJUDGED", set())


def _sprites(name, bp):
    """(sprite list, None) or (None, red tuple) for a blueprint that declares none.

    An empty sprite array is not an empty world, it is a broken emit — and eight of the
    twelve arms iterate that array, so an empty one turns each of them into a printed
    zero. Legality is decided once, here.
    """
    ss = (bp or {}).get("sprites") or []
    if not ss:
        return None, _illegal(name, "blueprint declares NO sprites — a frame that draws "
                              "nothing is a broken emit, not an empty world, and every "
                              "per-sprite arm would report a vacuous zero over it")
    return ss, None


def _era_of(bp, state=None):
    """The era from the state block, or None when it is absent or unrecognised."""
    st = state if isinstance(state, dict) else (bp or {}).get("state") or {}
    e = st.get("era")
    return e if e in ERA_ORDER else None


def _counted(name, bad, judged, total, skipped, floor, what, surfaces):
    """The shared verdict shape for a counting arm: the denominator is in the result.

    paint_fidelity's own rule, generalised — a green built on almost nothing is not a
    green. Under `floor` the arm goes red AND drops its surface claim, because at that
    point it is an input-coverage failure rather than a clean frame.
    """
    frac = judged/max(1, total)
    thin = frac < floor
    detail = (f"{len(bad)} {what}: {bad[:8]}; judged {judged}/{total} art files "
              f"({frac:.0%}, floor {floor:.0%})")
    if skipped:
        detail += f"; {len(skipped)} too small or too sparse to judge {skipped[:4]}"
    if thin:
        detail += (f"; judged only {frac:.0%} of the art this frame draws — under the floor, "
                   "so a green here would mean nothing")
    return (name, not bad and not thin, detail, set() if thin else surfaces)


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
def check_on_road(render, bp, tol=0.16, lane_visible=0.60):
    """No prop stands in a carriageway — judged on the GROUND layer's own pixels.

    THE GROUND LAYER IS NOT OPTIONAL. Sampling the composite looks THROUGH the sprite:
    a grey stone plinth reads as cobble and reports itself as standing in the road. The
    silent fallback to the render that used to sit here is now RED — an absent ground
    layer means this cannot be judged, not that it passed.

    THE ROAD DETECTOR IS ITSELF MEASURED, EVERY RUN. ROAD_RGB is a hand-held colour
    table, so if the ground palette moves the mask empties and "0 sprites stand on a
    lane" quietly becomes true of every frame forever. The declared lane centrelines
    are therefore sampled through the same mask: that fraction is printed and is part
    of the verdict. Measured on good frames — camp 100%, hamlet 93% — against a 60%
    floor.

    NO LANES AT ALL is the absent subject, and its legality depends on the rung: a camp
    has not worn any paths yet, a built settlement without a road network is a layout
    defect, and a blueprint with no era cannot decide either way.
    """
    ground = os.path.splitext(render)[0] + ".ground.png"
    if not os.path.exists(ground):
        return _unverifiable("on_road", f"no ground layer at {ground}: the composite may not "
                             "be substituted for it — sampling the finished frame looks "
                             "THROUGH the sprite, which is how a stone plinth once reported "
                             "itself standing on cobble")
    ss, err = _sprites("on_road", bp)
    if err: return err
    lanes = bp.get("lanes") or {}
    era = _era_of(bp)
    if not lanes:
        if era == "camp":
            return _unjudged("on_road", "no lanes declared, and at era camp there is no road "
                             "network yet to stand in, so nothing was judged")
        if era is None:
            return _unverifiable("on_road", "no lanes declared and the blueprint carries no "
                                 "era, so whether that absence is legal cannot be decided")
        return _illegal("on_road", f"no lanes declared at era {era} — a built settlement with "
                        "no road network is a layout defect, and it would leave this arm "
                        "vacuously green")
    im = Image.open(ground).convert("RGB")
    m, step = road_mask(im)
    W, H = im.size
    gpx = im.load()

    # ---- can the detector see the roads it is meant to police?
    seen = tot_l = 0
    for pts in lanes.values():
        for i in range(len(pts)-1):
            (x0, y0), (x1, y1) = pts[i], pts[i+1]
            n = int(math.hypot(x1-x0, y1-y0)/6) + 1
            for t in range(n+1):
                x = x0 + (x1-x0)*t/n; y = y0 + (y1-y0)*t/n
                if not (0 <= x < W and 0 <= y < H): continue
                if _is_water(gpx[int(x), int(y)]): continue   # a wharf approach is not road
                tot_l += 1
                iy, ix = int(y)//step, int(x)//step
                if 0 <= iy < len(m) and 0 <= ix < len(m[0]) and m[iy][ix]: seen += 1
    if not tot_l:
        return _unverifiable("on_road", f"{len(lanes)} lane runs declared and not one sample "
                             "of them lands on dry land inside the canvas")
    vis = seen/tot_l
    if vis < lane_visible:
        return _unverifiable("on_road", f"the road detector reads only {vis:.0%} of the "
                             f"{len(lanes)} declared lane centrelines as road (floor "
                             f"{lane_visible:.0%}) — with the lanes invisible to it, 'no sprite "
                             "stands on a lane' would be true of every frame ever rendered")
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
    bad = []; judged = exempt = 0
    for s in ss:
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        if s["n"] in ALLOW_ON_ROAD: exempt += 1; continue
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
        if not tot: continue                       # sprite is entirely off the canvas
        judged += 1
        if hit/tot > tol and not in_plaza(x, y): bad.append(f"{s['n']}@{x},{y}")
    if not judged:
        return _unverifiable("on_road", f"not one of {len(ss)} declared sprites could be "
                             f"sampled against the road mask ({exempt} are name-exempt), so "
                             "nothing was judged")
    return ("on_road", not bad,
            f"{len(bad)} of {judged} judged sprites stand on a lane: {bad[:6]}; "
            f"{exempt} name-exempt (wharf/afloat); the road detector reads {vis:.0%} of the "
            f"{len(lanes)} declared lane runs",
            {"placement", "roads"})


ALLOW_ON_ROAD = {"quay_deck", "jetty_plank", "mooring_post", "harbor_crane", "cargo_crates",
                 "cargo_barrels", "fish_barrel", "rope_coil", "crab_pots", "fish_drying_rack",
                 "fishing_net", "anchor", "barrel_single", "crate_single", "boat_rowing",
                 "boat_packet", "boat_fishing", "buoy", "duck", "bridge_plank", "gate_arch",
                 "fence_run", "camp_rowboat_jetty", "camp_bundles", "camp_tarp_cache"}


def check_stacking(render, bp, hard=0.30, built_floor=2):
    """No two structures fused — and the structure VOCABULARY proven non-blind.

    STRUCTURES is a hand-held name list, which is the only way to avoid asking the
    compositor what counts as a building; a hand-held list also goes blind silently,
    and this one did. It named 21 of 46 hamlet frames and exactly 1 of 24 town and 1 of
    24 beyond_bay, so town and bay reported ZERO stacking while unfiltered they stacked
    24 and 27. The recognised-name count therefore belongs in the VERDICT, not beside
    the green as a number nobody gates on: at a built era, fewer than `built_floor`
    distinct recognised names means the list has gone blind on that era's vocabulary,
    and a settlement that recognises no structure at all cannot have been judged.
    """
    ss, err = _sprites("stacking", bp)
    if err: return err
    era = _era_of(bp)
    inst = [s for s in ss if s["n"] in STRUCTURES]
    known = sorted({s["n"] for s in inst})
    pairs = len(inst)*(len(inst)-1)//2
    if not pairs:
        why = (f"{len(inst)} of {len(ss)} drawn sprites carry a name the structure vocabulary "
               "recognises, so no pair could be compared")
        if era in BUILT_ERAS:
            return _illegal("stacking", why + f" — at era {era} that means STRUCTURES has gone "
                            "blind on this era's vocabulary, not that the settlement has no "
                            "buildings in it")
        return _unjudged("stacking", why)
    if era in BUILT_ERAS and len(known) < built_floor:
        return _illegal("stacking", f"only {len(known)} distinct structure names recognised at "
                        f"era {era} ({known}) — under the {built_floor}-name floor, which is "
                        "exactly how this list last went blind (1 name on 24 town frames)")
    bad = []
    for i, a in enumerate(inst):
        ba = ground_box(a["x"], a["y"], a["w"], a["h"])
        for b in inst[i+1:]:
            f = overlap_frac(ba, ground_box(b["x"], b["y"], b["w"], b["h"]))
            if f > hard: bad.append(f"{a['n']}/{b['n']} {f:.2f}")
    return ("stacking", not bad,
            f"{len(bad)} structure-on-structure over {pairs} pairs compared: {bad[:6]}; "
            f"{len(known)} distinct structure names recognised in this frame",
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


def _frame_art(name, assets_dir, bp):
    """(list of (sprite_name, png_path), None), or (None, red tuple).

    THE FAIL-OPEN THIS REPLACES, found 2026-07-27. All three asset arms used to glob
    the directory: point one at a path that does not exist and the loop never ran, so
    it printed "0 problems" and PASSED — and verify.py's --assets defaulted to a fixed
    path, so a capture whose art lived anywhere else silently green-lit three of the
    twelve invariants at once.

    Resolving each name the BLUEPRINT declares makes an absent directory, a wrong
    directory and a missing cut-out all RED. It also fixes the denominator: the art
    swept is exactly the art this frame drew, not whatever happens to be lying in the
    directory, so the judged count below means something.
    """
    ss, err = _sprites(name, bp)
    if err: return None, err
    if not assets_dir or not os.path.isdir(assets_dir):
        return None, _unverifiable(name, f"no assets directory at {assets_dir!r} — with no art "
                                   "to open, this arm would sweep nothing and report zero")
    want = sorted({s["n"] for s in ss})
    have = {os.path.basename(p)[:-4]: p for p in glob.glob(f"{assets_dir}/*.png")}
    missing = [n for n in want if n not in have]
    if missing:
        return None, _unverifiable(name, f"{len(missing)} of {len(want)} sprite names this "
                                   f"frame draws have no art file in {assets_dir} "
                                   f"({missing[:6]}) — those sprites would go unswept")
    return [(n, have[n]) for n in want], None


def check_sprite_opacity(assets_dir, bp, max_semi=0.14, body_top=0.62, judged_floor=0.80):
    """A sprite whose BODY went semi-transparent reads as a ghost over the terrain.

    Measured above the base band only: a feathered ground patch at the foot of a
    sprite is deliberate (it melts into the terrain), a see-through wall is a bug.
    Measuring the whole sprite conflates the two and flags 50 healthy sprites.
    """
    art, err = _frame_art("sprite_opacity", assets_dir, bp)
    if err: return err
    bad = []; judged = 0; skipped = []
    for n, p in art:
        im = Image.open(p).convert("RGBA"); px = im.load(); W, H = im.size
        if W < 8 or H < 8: skipped.append(n); continue
        semi = op = 0
        for y in range(0, int(H*body_top)):
            for x in range(W):
                a = px[x, y][3]
                if a == 0: continue
                if a == 255: op += 1
                elif a > 10: semi += 1
        if semi + op <= 60: skipped.append(n); continue
        judged += 1
        if semi/(semi+op) > max_semi: bad.append(f"{n} {semi/(semi+op):.0%}")
    return _counted("sprite_opacity", bad, judged, len(art), skipped, judged_floor,
                    "sprite BODIES part-transparent", {"art"})


def check_sprite_cutoff(assets_dir, bp, frac=0.72, judged_floor=0.80):
    """A dead-flat bottom edge across most of a sprite is the signature of a bad cut."""
    art, err = _frame_art("sprite_cutoff", assets_dir, bp)
    if err: return err
    bad = []; judged = 0; skipped = []
    for n, p in art:
        im = Image.open(p).convert("RGBA"); px = im.load(); W, H = im.size
        if W < 12 or H < 12: skipped.append(n); continue
        bots = []
        for x in range(W):
            ys = [y for y in range(H) if px[x, y][3] > 0]
            if ys: bots.append(ys[-1])
        if len(bots) < 12: skipped.append(n); continue
        judged += 1
        top = Counter(b//2 for b in bots).most_common(1)[0][1]
        if top > len(bots)*frac: bad.append(n)
    return _counted("sprite_cutoff", bad, judged, len(art), skipped, judged_floor,
                    "sprites cut flat", {"art"})


def check_state_traceable(bp, state, allowed_ambient):
    """Anything drawn that cannot be traced to a state rule is a bug BY CONSTRUCTION.

    This is the cheapest high-yield check in the file: it caught a hatch frame that
    rendered a full village road network, driveways to empty grass, benches, lamps and
    market goods for a camp that had exactly one building.

    A BLUEPRINT WITH NO `justified` KEY IS UNVERIFIABLE, NOT CLEAN. Without it,
    "nothing in this frame is entitled" and "nothing emitted the entitlements" are the
    same empty set, and the arm would clear an entire frame on the strength of a
    missing emitter.
    """
    ss, err = _sprites("state_traceable", bp)
    if err: return err
    if not isinstance(state, dict) or "justified" not in state:
        return _unverifiable("state_traceable", "the blueprint carries no state.justified set, "
                             "so 'nothing is entitled' and 'nothing emitted the entitlements' "
                             "cannot be told apart")
    just = set(state.get("justified") or ())
    justified = just | set(allowed_ambient)
    drawn = {s["n"] for s in ss}
    orphan = sorted(drawn - justified)
    return ("state_traceable", not orphan,
            f"{len(orphan)} sprites with no state justification: {orphan[:10]}; "
            f"{len(drawn)} distinct names screened against {len(just)} justified + "
            f"{len(allowed_ambient)} ambient",
            {"state", "placement"})


def check_palette(assets_dir, bp, palette_rgb, tol=64, max_off=0.14, judged_floor=0.80):
    """Sprites must live in the world's palette; a re-pick can silently swap a variant."""
    art, err = _frame_art("palette", assets_dir, bp)
    if err: return err
    if not palette_rgb:
        return _unverifiable("palette", "the world palette resolved to zero colours, so every "
                             "sprite would be judged against nothing")
    bad = []; judged = 0; skipped = []
    for n, p in art:
        im = Image.open(p).convert("RGBA")
        px = list(im.getdata())[::7]
        vis = [q for q in px if q[3] > 128]
        if len(vis) < 40: skipped.append(n); continue
        judged += 1
        off = sum(1 for q in vis
                  if min((q[0]-c[0])**2 + (q[1]-c[1])**2 + (q[2]-c[2])**2 for c in palette_rgb) > tol*tol)
        if off/len(vis) > max_off:
            bad.append(f"{n} {off/len(vis):.0%}")
    return _counted("palette", bad, judged, len(art), skipped, judged_floor,
                    "sprites off-palette", {"art"})


# ============================================================ the four missing surfaces
# Same law as everything above: no compositor, no cutout pipeline, no helper of either.
# Geometry is re-derived from the published contract (sprite x,y = BASE CENTRE, w,h =
# drawn size), terrain is judged on the sprites-free ground layer, and the lamp is
# judged on the finished frame — the glow is applied AFTER the ground layer is written,
# so the ground layer cannot show it. Nothing here ever samples the ground UNDER a
# sprite.
#
# THE MISSING-INPUT / ABSENT-SUBJECT POLICY these four introduced is now the module
# docstring's second rule and binds all twelve arms (2026-07-27). Stated once, there.
# A surface is claimed only when a real assertion was actually made about THIS frame.

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
    ss, err = _sprites("paint_fidelity", bp)
    if err: return err
    ground = os.path.splitext(render)[0] + ".ground.png"
    for path, what in ((render, "render"), (ground, "ground layer"),
                       (assets_dir, "assets dir")):
        if not path or not os.path.exists(path):
            return _unverifiable("paint_fidelity", f"no {what} at {path!r}")

    FR = Image.open(render).convert("RGB"); cp = FR.load(); W, H = FR.size
    G = Image.open(ground).convert("RGB"); gp = G.load()
    if G.size != FR.size:
        return _unverifiable("paint_fidelity", f"ground layer {G.size} != render {FR.size}")

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
    ss, err = _sprites("era", bp)
    if err: return err
    drawn = {s["n"] for s in ss}
    era = (state or {}).get("era")
    ladders = (state or {}).get("ladders")

    if era not in ERA_ORDER:
        return _unverifiable("era", f"no usable era in the blueprint ({era!r}) — vocabulary")
    if not isinstance(ladders, dict) or not ladders:
        return _unverifiable("era", "the blueprint carries no state.ladders, so nothing drawn "
                             "can be compared against its own measurement and the rung arm "
                             "would report a zero over an empty dict")
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
    notes = [f"floor arm screened {len(drawn)} distinct names, {len(drawn & set(ERA_MIN))} of "
             f"them era-constrained",
             f"rung arm: {judged_ladders} of {len(ladders)} ladders judged, "
             f"{len(unmapped)} unmapped ({unmapped[:4]})"]
    if not judged_ladders:
        notes.append("rung arm UNJUDGED — no mapped ladder object has drawn art in this frame, "
                     "so its zero is an empty loop and not a clean result")
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

    LAMP: the glow must be present exactly when state says the lamp is lit. A missing
    lighthouse_lamp rung, stage=None or measured=False is never read as "the lamp is
    off" — the previous draft collapsed absent into dark and hard-failed two
    correctly-lit, visually-confirmed frames whose blueprints simply predate the state
    emitter. But nor is it a pass, and telling those two apart is what changed on
    2026-07-27: deleting the TOWER was caught and deleting its STATE was not.
      A tower is drawn and its rung is absent  -> RED. The subject is right there in
        the frame and the thing that would make its glow legal or illegal is gone;
        that is a missing input, and a missing input has not passed.
      No tower and no measured rung           -> UNJUDGED, and the `lamp` surface is
        NOT claimed. Nothing was sampled, so nothing may be claimed — including on a
        camp frame, where state says dark and there is no tower to look at.
      No tower and the rung says lit          -> RED, as before.
    The grade arm runs regardless and keeps claiming `grade` in every one of those
    cases, because it really did measure the frame.

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
        return _unverifiable("light", f"no render at {render}")
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
    if n < 500:
        return _unverifiable("light", f"the render is {W}x{H} and yielded only {n} grade "
                             "samples — no distribution can be read from that")
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
    stated = (isinstance(lamp, dict) and lamp.get("stage") is not None
              and bool(lamp.get("measured")))
    if not stated and towers:
        # The subject IS in the frame and the thing that decides its legality is gone.
        bad.append(f"a lighthouse is drawn but state carries no measured lighthouse_lamp rung "
                   f"({lamp if lamp else 'absent'}) — whether its glow is legal is "
                   "UNVERIFIABLE, not passed")
        lampstate = f"UNVERIFIABLE — tower drawn, no measured rung; frame shows: {lampdesc}"
    elif not stated:
        lampstate = ("UNJUDGED — no lighthouse drawn and no measured lighthouse_lamp rung in "
                     f"state ({lamp if lamp else 'absent'}); no pixel was sampled, so the lamp "
                     "surface is not claimed")
    elif not towers and lamp.get("stage") != "lit":
        # State says unlit and there is no tower: nothing was looked at, so nothing is
        # claimed. Consistency between two absences is not a measurement.
        lampstate = (f"UNJUDGED — state {lamp.get('stage')!r} and no lighthouse drawn, so no "
                     "pixel was sampled and the lamp surface is not claimed")
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

    THREE SURFACES, NOT ONE (2026-07-27). `terrain` used to be a single coarse claim
    covering ground, coastline, water, fields AND the square — so a frame that declared
    no square and no plots still bought the whole bundle, and the camp capture was
    reporting zero unchecked surfaces on the strength of two arms that never ran. The
    rim/island/coast arms always run and keep `terrain`; `plaza` and `fields` are now
    claimed only where something was declared and actually judged. Same split, same
    reason, as the 2026-07-26 adjudication applied to `depth` and `light`: a claim has
    to be provable to be worth making.
    """
    ground = os.path.splitext(render)[0] + ".ground.png"
    if not os.path.exists(ground):
        return _unverifiable("terrain", f"no ground layer at {ground} — the composite may not "
                             "stand in for it: a green roof would read as pasture and a stone "
                             "wall as paving")
    im = Image.open(ground).convert("RGB"); px = im.load(); W, H = im.size
    if W < 64 or H < 64:
        return _unverifiable("terrain", f"ground layer is {W}x{H} — too small for the rim, "
                             "island and coast sweeps to carry any meaning")
    bad = []; notes = []; surfaces = {"terrain"}
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
    if not coast:
        # An island with no edge cell means the land mask found nothing to trace, and a
        # beach fraction over zero coast cells is the vacuous pass this arm must not print.
        bad.append("no coastline cell found at all — the beach band could not be measured")
    else:
        hit = 0
        for x, y in coast:
            if any(sand[ry][rx]
                   for ry in range(max(0, y-3), min(gh, y+4))
                   for rx in range(max(0, x-3), min(gw, x+4))): hit += 1
        band = hit/len(coast)
        if band < coast_min: bad.append(f"coastline has no beach band ({band:.0%})")
        notes.append(f"beach {band:.0%} of {len(coast)} coast cells")

    # ---- the square is where the blueprint says, is on dry land, and is paved if the
    #      era says the settlement builds
    pz = bp.get("plaza")
    if not pz:
        notes.append("no plaza declared — the square mask is UNJUDGED and the plaza surface "
                     "is NOT claimed")
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
            return (st/max(1, t), w/max(1, t), t)
        pv, pw, pt = sweep(0.0, 1.0)
        av, _, at = sweep(1.15, 1.55)
        if pt < 50 or at < 50:
            # A square declared off-canvas or with a degenerate radius samples almost
            # nothing, and every fraction below would be computed over max(1, ~0).
            bad.append(f"declared square samples only {pt} pixels inside and {at} outside — "
                       "too few for the paving comparison to mean anything")
        elif pw > 0.05:
            bad.append(f"declared square is {pw:.0%} water")
            surfaces.add("plaza")
        elif pv >= plaza_paved:
            if pv < av*2.0:
                bad.append(f"square paving {pv:.0%} no denser than its surroundings {av:.0%}")
            notes.append(f"square paved {pv:.0%} vs {av:.0%} outside, {pt} samples")
            surfaces.add("plaza")
        elif era is None:
            notes.append(f"square draws no paving ({pv:.0%} stone) and the blueprint "
                         "carries no era — UNJUDGED, plaza surface NOT claimed")
        elif era == "camp":
            notes.append(f"square unpaved ({pv:.0%} stone) — expected at era camp")
            surfaces.add("plaza")
        else:
            bad.append(f"declared square draws no paving ({pv:.0%} stone) at era {era}")
            surfaces.add("plaza")

    # ---- every declared field really is cultivated ground
    judged_f = 0
    flds = bp.get("fields") or []
    if not flds:
        notes.append("no fields declared — the cultivated-ground mask is UNJUDGED and the "
                     "fields surface is NOT claimed")
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
        # A plot that is mostly sea used to be counted "too far offshore to judge" and
        # noted beside the green. It is not an unjudged plot, it is a plot in the water:
        # a declared field nobody can stand in is the defect, not a gap in the sensor.
        if not tot:
            bad.append(f"field {i} at {fx},{fy} lies entirely outside the canvas")
            continue
        if ln/tot < 0.25:
            bad.append(f"field {i} at {fx},{fy} is {1-ln/tot:.0%} water — a plot in the sea "
                       "cannot be cultivated ground")
            continue
        judged_f += 1
        if cult/max(1, ln) < field_min:
            bad.append(f"field {i} at {fx},{fy} is bare ground ({cult/max(1,ln):.0%} tilled)")
    if flds:
        notes.append(f"{judged_f}/{len(flds)} declared field plots judged")
        if judged_f: surfaces.add("fields")

    # ---- no lane wanders off the island
    q = bp.get("quay"); cove = bp.get("cove")
    lanes = bp.get("lanes") or {}
    if not lanes:
        notes.append("no lanes declared — the off-island lane arm is UNJUDGED (whether that "
                     "absence is legal is check_on_road's call, not this one's)")
    lane_samples = 0
    for nm, pts in lanes.items():
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
        lane_samples += tot
        if off: bad.append(f"lane {nm} runs {off}/{tot} samples into open water")
    if lanes: notes.append(f"{lane_samples} lane samples judged against the waterline")

    # A RED arm still claims what it measured: the surface was examined and found
    # defective, which is a result. Only an arm that never looked drops its claim.
    return ("terrain", not bad,
            (f"{len(bad)} defects {bad[:4]}; " if bad else "") + "; ".join(notes),
            surfaces)


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


def _layer_overlap_cells(layers, S=16):
    """How many S-pixel cells at least two declared layer rects both cover.

    The denominator for "zero contested pixels". If no two rects even share a cell then
    zero is the honest answer and there is nothing to order; if hundreds of cells are
    shared and the buffers still contest nothing, the buffers are not carrying the
    layers and that zero is a dead sensor.
    """
    cov = {}; n = 0
    for l in layers:
        x0 = int(l.get("x", 0)); y0 = int(l.get("y", 0))
        x1 = x0 + max(0, int(l.get("w", 0))); y1 = y0 + max(0, int(l.get("h", 0)))
        for gy in range(y0//S, y1//S + 1):
            for gx in range(x0//S, x1//S + 1):
                k = (gx, gy); v = cov.get(k, 0) + 1
                cov[k] = v
                if v == 2: n += 1
    return n


def check_depth_order(render, bp, step=3, tol=1.5, max_report=8, max_unmapped=0.02):
    """Who won each CONTESTED pixel, decided from two id buffers.

    Forward order gives the last layer painted at a pixel; reverse order gives the
    first. Where they differ, at least two OPAQUE layers contested it — which rect
    overlap alone can never tell you, since most of a tree's rect is air. The nearer
    layer (lower base on screen, 2:1 isometric) must be the one in front.

    TWO DEGENERATE ENDS, both of which used to print a green (2026-07-27):
      ZERO CONTESTED PIXELS read "draw order correct on all 0 contested pixels". It is
      now measured against whether the declared layers overlap AT ALL: no shared cell
      and there is genuinely no order to decide (UNJUDGED, surface not claimed); shared
      cells and still no contested pixel means the id buffers are not carrying the
      layers, which is RED.
      AN ID COLOUR NO LAYER CLAIMS was skipped silently by `by_rgb.get(...) is None`,
      so a buffer written from a stale or renumbered layer table would decay to zero
      comparisons one pixel at a time and still print a green. Those pixels are counted
      now, and past 2% of the contested set they end the run as unverifiable.
    """
    ids = _load_ids(render)
    p_rev = os.path.splitext(render)[0] + ".idsrev.png"
    layers = bp.get("layers") or []
    if ids is None:
        return _unverifiable("depth_order", "no forward id buffer emitted — draw order cannot "
                             "be recovered from a finished frame")
    if not os.path.exists(p_rev):
        return _unverifiable("depth_order", f"no reverse id buffer at {p_rev} — without it a "
                             "contested pixel cannot be told from a lone opaque one")
    if not layers:
        return _unverifiable("depth_order", "the blueprint declares no layers, so no id colour "
                             "can be resolved to a sort position")
    rev = Image.open(p_rev).convert("RGB")
    if rev.size != ids.size:
        return _unverifiable("depth_order", f"id buffers disagree on size (forward {ids.size}, "
                             f"reverse {rev.size})")
    by_rgb = {tuple(l["rgb"]): l for l in layers}
    W, H = ids.size
    a, b = ids.load(), rev.load()
    bad, contested, unmapped = [], 0, 0
    for y in range(0, H, step):
        for x in range(0, W, step):
            ca, cb = a[x, y], b[x, y]
            if ca == cb or ca == (0, 0, 0) or cb == (0, 0, 0): continue
            near, far = by_rgb.get(ca), by_rgb.get(cb)
            if near is None or far is None: unmapped += 1; continue
            contested += 1
            if far["sort_y"] > near["sort_y"] + tol:
                bad.append((x, y, near["id"], far["id"]))
    if unmapped and unmapped/(unmapped + contested) > max_unmapped:
        return _unverifiable("depth_order", f"{unmapped} of {unmapped+contested} contested "
                             f"pixels carry an id colour none of the {len(layers)} declared "
                             "layers claims — the id buffer and the blueprint are out of sync "
                             "and every such pixel is a comparison silently skipped")
    if not contested:
        shared = _layer_overlap_cells(layers)
        if shared:
            return _illegal("depth_order", f"{len(layers)} declared layers overlap on {shared} "
                            "cells and yet NO pixel was contested by two of them — the id "
                            "buffers are not carrying the layers, so a zero here is a dead "
                            "sensor and not a correct draw order")
        return _unjudged("depth_order", f"none of the {len(layers)} declared layers overlaps "
                         "another, so no pixel is contested and there is no order to decide")
    ok = not bad
    detail = (f"{len(bad)} of {contested} contested pixels won by the FARTHER layer "
              f"{bad[:max_report]}" if bad
              else f"draw order correct on all {contested} contested pixels")
    detail += f" ({len(layers)} layers, {unmapped} unmapped id pixels)"
    return ("depth_order", ok, detail, {"depth_order", "occlusion"})


def _bare_mask(ids, dil=2):
    """Ground the id buffer says no sprite BODY reaches, grown by `dil` pixels.

    The growth is not caution, it is the fringe: the id buffer only records alpha > 128,
    so a sprite's own anti-aliased skirt (alpha 1..128) darkens the frame while reading
    as bare here. Measured: without the growth a sprite's edge alone scores as a shadow
    on frames that carry none. Shadows themselves peak at alpha 86 and so never enter
    the id buffer — which is what makes the ground under one still readable as ground.
    """
    r, g, b = ids.split()
    occ = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 255 if v else 0)
    return occ.filter(ImageFilter.MaxFilter(2*dil + 1)).load()


def _foot_ellipse(s):
    """The patch of ground a sprite's shadow lies on: its base, not its body."""
    x, y, w, h = s["x"], s["y"], s["w"], s["h"]
    return x, y - 0.03*h, max(6.0, 0.42*w), max(4.0, 0.13*h)


def _foot_stat(cx, cy, rx, ry, W, H, bare, gp, cp, lut, lit, step=2):
    """Per-channel mean of (this frame's grade of the ground here) MINUS (the frame).

    Positive = the finished frame is darker than its own grade of that exact ground
    pixel, which is the only thing a cast shadow can be. Returns
    (mean_per_channel, n_used, n_lit, n_wet, n_total) — never a verdict.
    """
    acc = [0.0, 0.0, 0.0]
    n = nlit = nwet = tot = 0
    for y in range(int(cy - ry), int(cy + ry) + 1, step):
        if not (0 <= y < H): continue
        for x in range(int(cx - rx), int(cx + rx) + 1, step):
            if not (0 <= x < W): continue
            if ((x - cx)/rx)**2 + ((y - cy)/ry)**2 > 1.0: continue
            tot += 1
            g = gp[x, y]
            if _is_water(g): nwet += 1
            if bare[x, y]: continue                 # a sprite body or its fringe
            q = cp[x, y]
            d = []
            for c in range(3):
                e = lut.get((c, g[c] >> 3))
                if e is None: break
                d.append(e - q[c])
            if len(d) < 3: continue                 # ground tone never seen untouched
            if max(d) < lit:                        # brighter in EVERY channel
                nlit += 1
                continue
            for c in range(3): acc[c] += d[c]
            n += 1
    return ([a/n for a in acc] if n else None), n, nlit, nwet, tot


def check_shadows(render, bp, min_frac=0.85, dark=4.0, judged_floor=0.40,
                  lit=-2.0, lit_max=0.15, afloat=0.90, noise_max=0.15):
    """Every sprite standing on ground darkens THAT GROUND, measured against the frame's
    own grade of the SAME pixels — so the material under the sprite cannot testify.

    THE DEFECT THIS REPLACES, and why it was structural. The old arm compared the ground
    at a sprite's foot against bare ground on a ring max(70, w*1.5) out. Two different
    PLACES, so it could not tell a cast shadow from a MATERIAL CHANGE: anything standing
    on soil, planking or water beside bright grass scored as shadowed with no shadow
    drawn. Measured on this branch with every shadow deleted (raster.py --mutate
    no-shadows): camp 31/68 = 46%, hamlet 36/65 = 55% against its own 55% floor — green
    on a frame with no shadows in it at all. The signal was 14-22 points riding on a
    46-55 point noise floor, and the floor had drifted 46 -> 54 -> 55 across three
    commits as boats moved off the pier into darker water.

    WHAT IS COMPARED NOW. The sprites-free ground layer is written before the golden-hour
    pass, so ground.png and the frame cannot be subtracted directly — the grade swamps
    everything (measured elsewhere in this file: a raw difference fires on 100% of
    sprite-free pixels). _grade_lut fits THIS frame's own transform from pixels no sprite
    rect touches, and the comparison becomes: predicted-graded-ground at pixel p versus
    the frame at pixel p. Same pixel, same material, both post-grade. On open ground that
    residual is centred on -0.01 luminance (sd 1.4), so anything left is paint.

    WHAT IS PAINTED AFTER THE GRADE, and so cannot be predicted from the ground at all:
    the lighthouse glow and the chimney plumes. The glow LIFTS every channel, so foot
    pixels that are brighter than their own grade in all three are set aside as
    post-grade light, and a foot that is mostly such light is UNJUDGED rather than
    guessed at (measured: 7 sprites at hamlet, 6 at camp, all of them the ring of
    buildings round the lighthouse). A plume is the one confound left standing: it can
    darken the ground it crosses, and a sprite under one scores as shadowed with no
    shadow drawn. Measured on the shadow-deleted hamlet frame, that is 2 of 55 judged
    sprites — 4% against an 85% floor, so it cannot carry a frame, and every dense
    residual on that frame sits directly above a declared smoke anchor.

    A COLOUR CLAUSE WAS TRIED AND DROPPED, recorded because the next author will think of
    it too. Requiring the darkening to be positive in all three channels sounds like it
    separates a shadow (blends toward a dark blue-grey) from a plume (pale, lifts blue).
    Measured across all four frames it changed nothing on either shadow-deleted frame
    (0% and 4% with it and without it — the plume's darkening is all-positive too) and
    cost 5 true positives at hamlet, 100% -> 92%. A clause whose stated purpose is not
    the thing it does is the defect this file exists to catch.

    WHAT IS EXEMPT, and it is a measurement rather than a list: a foot whose ground is
    >= 90% water is afloat, and a hull on the sea casts nothing. Measured separation on
    these frames is total — the three boats sit at 1.00 wet, the next sprite in at 0.52 —
    so the exemption cannot quietly widen onto land without that gap closing first.

    THE CHECK MEASURES ITS OWN NOISE FLOOR EVERY RUN. Control patches of open ground,
    far from every sprite rect, are put through the identical statistic; the fraction of
    them that read as shadowed is the false-positive rate on this frame, it is printed in
    the detail, and it is part of the verdict. That is the specific guard against how the
    old arm died: a floor that creeps toward the threshold now goes red instead of green.
    """
    ss, err = _sprites("shadows", bp)
    if err: return err
    ids = _load_ids(render)
    ground = os.path.splitext(render)[0] + ".ground.png"
    if ids is None:
        return _unverifiable("shadows", "no id buffer — a shadow cannot be told from a sprite "
                             "body")
    if not os.path.exists(ground):
        return _unverifiable("shadows", f"no ground layer at {ground} — nothing to compare the "
                             "frame against")
    FR = Image.open(render).convert("RGB"); cp = FR.load(); W, H = FR.size
    G = Image.open(ground).convert("RGB"); gp = G.load()
    if G.size != FR.size or ids.size != FR.size:
        return _unverifiable("shadows", f"buffers disagree on size (frame {FR.size}, ground "
                             f"{G.size}, ids {ids.size})")
    want = [s for s in ss if s["w"] >= 46 and s["h"] >= 46]
    if not want:
        return _unjudged("shadows", f"none of the {len(ss)} declared sprites is large enough "
                         "(46x46) to carry a readable shadow")

    bare = _bare_mask(ids)
    cov, S = _cover_grid(ss, W, H, pad=24)   # pad clears the blurred shadow's own spill
    lut = _grade_lut(cp, gp, cov, S, W, H)

    def casts(m):
        return m is not None and (0.299*m[0] + 0.587*m[1] + 0.114*m[2]) >= dark

    cast, judged, why, misses = 0, 0, Counter(), []
    for s in want:
        cx, cy, rx, ry = _foot_ellipse(s)
        m, n, nlit, nwet, tot = _foot_stat(cx, cy, rx, ry, W, H, bare, gp, cp, lut, lit)
        if tot and nwet/tot >= afloat: why["afloat"] += 1; continue
        if n < 12: why["thin"] += 1; continue
        if nlit/(n + nlit) > lit_max: why["lit"] += 1; continue
        judged += 1
        if casts(m): cast += 1
        else: misses.append(f"{s['n']}@{s['x']},{s['y']}")

    # ---- the same statistic where nothing stands: this frame's false-positive rate
    ctrl_rx, ctrl_ry = 45.0, 12.0
    ctrl_hit = ctrl_n = 0
    for gy in range(1, 12):
        for gx in range(1, 16):
            cx, cy = W*gx/16.0, H*gy/12.0
            if cov[int(cy)//S][int(cx)//S]: continue          # too near a sprite
            m, n, nlit, nwet, tot = _foot_stat(cx, cy, ctrl_rx, ctrl_ry, W, H,
                                               bare, gp, cp, lut, lit)
            if n < 12 or (tot and nwet/tot >= afloat): continue
            ctrl_n += 1
            if casts(m): ctrl_hit += 1
    noise = ctrl_hit/ctrl_n if ctrl_n else None

    jfrac = judged/len(want)
    frac = cast/judged if judged else 0.0
    thin = jfrac < judged_floor
    noisy = noise is not None and noise > noise_max
    blind = noise is None
    ok = judged > 0 and frac >= min_frac and not thin and not noisy and not blind
    detail = (f"{cast}/{judged} judged sprites darken their own ground ({frac:.0%}, "
              f"floor {min_frac:.0%}); {len(want)-judged} unjudged "
              f"({', '.join(f'{v} {k}' for k, v in sorted(why.items())) or 'none'}); "
              f"noise floor {ctrl_hit}/{ctrl_n} control patches of open ground read as "
              f"shadowed ({'n/a' if noise is None else f'{noise:.0%}'}, ceiling "
              f"{noise_max:.0%})")
    if misses: detail += f"; no shadow: {misses[:5]}"
    if thin: detail += (f"; judged only {jfrac:.0%} of large sprites — under the "
                        f"{judged_floor:.0%} floor, so a green here would mean nothing")
    if blind: detail += "; NO control patch was measurable — noise floor UNKNOWN"
    return ("shadows", ok, detail, {"shadows"})
