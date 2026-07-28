#!/usr/bin/env python3
"""verify.py — run every registered check, and report WHAT WAS NOT CHECKED.

The Captain's framing: "check what you haven't checked." The valuable half of this
tool is not the pass/fail — it is the COVERAGE line. Self-attestation cannot catch a
blind spot (asking "did you check?" re-runs the judgment that already failed), but
enumerating the surfaces a turn touched and subtracting the surfaces a check actually
covers is mechanical, and the remainder is exactly the thing worth looking at.

Registry is APPEND-ONLY. Every defect the Captain finds becomes a permanent row here,
so a fix can never quietly replace the previous concern.

    python3.12 checks/verify.py --render <frame.png> [--assets DIR] [--json OUT]
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import world_checks as C

# Every surface the world has. A check claims one or more; anything unclaimed is
# reported as UNCHECKED rather than silently assumed fine.
# Refined 2026-07-26 after adjudication. The coarse "depth" and "light" surfaces each
# bundled several distinct claims, which let a check claim the whole bundle while
# verifying one part of it — the proposed depth check would have claimed "draw order and
# occlusion" while its order arm was dead code. Split so a claim is provable.
# Split again 2026-07-27 for the same reason: `terrain` bundled the ground/coast/water
# sweeps with the plaza and field masks, so a frame that declared NO square and NO plots
# still bought the whole bundle — the camp capture was reporting zero unchecked surfaces
# on the strength of two arms that never ran.
SURFACES = {
    "art":         "sprite quality — opacity, cut-offs, palette, residual ground slab",
    "placement":   "where things stand — roads, stacking, floating, clearance",
    "roads":       "the lane network itself",
    "state":       "every drawn thing traceable to a real measurement",
    "terrain":     "ground, coastline and water — the island's own shape",
    "plaza":       "the paved square: declared where it is drawn, and drawn where declared",
    "fields":      "declared plots really are cultivated ground",
    "grade":       "exposure, contrast, saturation — the frame not washed out",
    "lamp":        "the lighthouse lamp lit iff a cell has graduated",
    "era":         "vocabulary matches the era; nothing from a future rung",
    "depth_order": "which of two overlapping sprites won the contested pixel",
    "occlusion":   "a sprite correctly hidden behind the thing in front of it",
    "shadows":     "the cast shadow under every sprite",
}

# Defects the Captain found, each now a permanent row. Never delete a row.
REGISTRY = [
    ("on_road",          "2026-07-25", "props standing in the road (reported clean 3x)"),
    ("stacking",         "2026-07-26", "two houses fused; props piled on each other"),
    ("sprite_opacity",   "2026-07-26", "the barn rendered semi-transparent"),
    ("sprite_cutoff",    "2026-07-25", "tree trunks, firepit ring, building corners sliced"),
    ("palette",          "2026-07-26", "pines flipped to a yellow variant on a re-pick"),
    ("state_traceable",  "2026-07-26", "hatch frame drew a village's worth of unjustified dressing"),
    ("paint_fidelity",   "2026-07-26", "a declared sprite that left no mark, or paint with nothing declared"),
    ("era",              "2026-07-26", "camp frame drawing village vocabulary"),
    ("light",            "2026-07-26", "over-graded washed-out frames; the lamp lit without a graduation"),
    ("terrain",          "2026-07-26", "plaza/field regions declared but not painted; lanes running into water"),
    ("depth_order",      "2026-07-26", "a farther sprite painted over a nearer one"),
    ("shadows",          "2026-07-26", "sprites floating without a cast shadow"),
]


def load_palette():
    import importlib.util
    p = HERE.parent / "designs" / "world-mockup-v2" / "palette.py"
    spec = importlib.util.spec_from_file_location("pal", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.flat_colors()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", required=True)
    # THE DEFAULT USED TO BE A FIXED PATH (/tmp/isoframe/assets), and that was a
    # fail-open with a wide blast radius: a capture whose art lived anywhere else had
    # three of the twelve arms sweeping a stranger's directory — or, when it did not
    # exist at all, sweeping nothing and reporting "0 problems" three times. The art of
    # a capture sits beside its frame, so that is what this resolves to; the arms
    # themselves now go RED on a directory that does not hold this frame's sprites.
    ap.add_argument("--assets", default=None,
                    help="art directory (default: <render dir>/assets)")
    ap.add_argument("--blueprint", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--allow-ambient", default=None,
                    help="file of sprite names allowed without a ladder (one per line)")
    a = ap.parse_args()

    bp_path = a.blueprint or os.path.splitext(a.render)[0] + ".blueprint.json"
    if not os.path.exists(bp_path):
        print(f"NO BLUEPRINT at {bp_path} — a render without its layout data cannot be checked")
        return 2
    bp = json.loads(Path(bp_path).read_text())
    assets = a.assets or str(Path(a.render).resolve().parent / "assets")
    # Comment lines were being loaded as allowed sprite names. Harmless while nobody
    # counted them — no sprite is called "# One name per line" — but check_state_traceable
    # now prints the size of this set, and a printed number has to be true.
    allowed = set()
    if a.allow_ambient and os.path.exists(a.allow_ambient):
        allowed = {l.strip() for l in open(a.allow_ambient)
                   if l.strip() and not l.lstrip().startswith("#")}

    # The three asset arms take the blueprint too: they resolve the art of the sprites
    # THIS frame declares rather than globbing whatever is in the directory, which is
    # what makes an absent or wrong directory red instead of an empty loop.
    results = []
    results.append(C.check_on_road(a.render, bp))
    results.append(C.check_stacking(a.render, bp))
    results.append(C.check_sprite_opacity(assets, bp))
    results.append(C.check_sprite_cutoff(assets, bp))
    results.append(C.check_palette(assets, bp, load_palette()))
    results.append(C.check_state_traceable(bp, bp.get("state", {}), allowed))
    results.append(C.check_paint_fidelity(a.render, bp, assets))
    results.append(C.check_era(bp, bp.get("state", {})))
    results.append(C.check_light(a.render, bp, bp.get("state", {})))
    results.append(C.check_terrain(a.render, bp, bp.get("state", {})))
    results.append(C.check_depth_order(a.render, bp))
    results.append(C.check_shadows(a.render, bp))

    covered = set()
    for name, ok, detail, surfaces in results: covered |= surfaces
    unchecked = sorted(set(SURFACES) - covered)

    red = [r for r in results if not r[1]]
    for name, ok, detail, _ in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:18s} {detail}")
    print()
    if unchecked:
        print("NOT CHECKED — no check claims these surfaces:")
        for s in unchecked: print(f"   {s:10s} {SURFACES[s]}")
    else:
        print("every registered surface has a check")

    out = {"render": a.render, "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "results": [{"check": n, "ok": ok, "detail": d} for n, ok, d, _ in results],
           "unchecked": unchecked, "red": [r[0] for r in red]}
    dest = a.json or os.path.splitext(a.render)[0] + ".verify.json"
    Path(dest).write_text(json.dumps(out, indent=1))
    print(f"\n{'GREEN' if not red else 'RED'} · {len(results)-len(red)}/{len(results)} checks pass"
          f" · {len(unchecked)} surfaces unchecked · report {dest}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
