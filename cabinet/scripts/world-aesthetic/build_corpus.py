#!/usr/bin/env python3.12
"""Calibration corpus builder for the Cabinet World aesthetic judge.

The corpus lives in cabinet/scripts/world-aesthetic/corpus/{positive,negative,
palette}/ and is GITIGNORED (renders and licensed art are instance data). Only
this script and corpus/manifest.json are tracked. The manifest carries sha256 +
provenance per image so any checkout can verify (or re-assemble) the exact
corpus without committing the pixels.

Usage (python3.12; `synthetic` needs Pillow — e.g. a venv with `pip install pillow`):
    build_corpus.py synthetic            # regenerate the 3 synthetic negatives
    build_corpus.py manifest             # hash corpus images + write manifest
    build_corpus.py verify [--corpus D]  # check files against a tracked manifest

CLASSES
  positive  finished OWNED-ART isometric scenes the Captain has seen and
            accepted. Fits both the palette and the clustering image bounds,
            and is the vision judge's positive pool.
  negative  Captain-rejected build screenshots (accumulated taste — never
            dropped) plus synthetic owned-art scatter/void scenes reproducing
            the rejected failure mode INSIDE the owned art family.
  palette   palette-source art that is NOT a scene: the owned isometric atlas.
            Read by the palette fit only — never by the clustering fit and
            never by the vision judge, which would otherwise be comparing a
            candidate scene against a sprite sheet. It exists because a frame
            built only from sprites the wide renders happen not to exercise
            otherwise reads as foreign colour: measured 6.52% foreign without
            it against 1.23% with it, on neg-owned-scatter-dense (2026-07-28).

RE-FIT PROVENANCE (2026-07-28). The corpus was LimeZu showcase scenes until the
Captain's "ALL OUT of LimeZu" direction made every world pixel owned generated
art. A palette fitted to LimeZu measured owned frames at 57-90% foreign against
a 5% limit — the gate was pointed at the art family we are deliberately leaving,
not at a defect. The previous corpus is preserved VERBATIM and still runnable at
corpus-limezu-2026-07-08/ (manifest tracked), and the calibration it produced is
preserved at calibration/archive/limezu-2026-07-08/ so every claim made against
it is still reproducible from a plain checkout. The argument, the before/after
numbers and the bite proof are in cabinet-meta
designs/world-aesthetic-corpus-refit-2026-07-28.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
REPO_ROOT = HERE.parents[2]
ISO_PACK = (REPO_ROOT / "cabinet" / "dashboard" / "public" / "world-assets"
            / "originals" / "iso")

CLASSES = ("positive", "negative", "palette")

# The owned world's own ground colour — the dominant exact RGB of a live
# isometric capture. Scattering owned props on THIS is the honest reproduction
# of the rejected failure mode: palette-lawful, composition-broken.
OWNED_GROUND = (127, 197, 175)
CANVAS = (1200, 880)  # half the 2400x1760 live capture, same aspect

# Owned atlas frames sampled for the synthetic negatives. Every one is in the
# repo's own TRACKED pack, so these synthetics are reproducible from a plain
# checkout + Pillow — the LimeZu-prop synthetics they replace were not.
SCATTER_PROPS = ["barrel_single", "anchor", "well", "bench", "flagpole",
                 "firepit", "chart_table", "signpost", "tree_oak", "crop_rows"]
VOID_BUILDINGS = ["great_house", "officer_house_a", "officer_house_b",
                  "library", "workshop"]

# id -> (class, filename, provenance, why-it-belongs)
REGISTRY: dict[str, tuple[str, str, str, str]] = {
    # ── POSITIVES: owned isometric art, Captain-seen. Chosen to span the
    #    renderer's whole colour production, not just its prettiest frame:
    #    two wide island states (two terrain eras), one close zoom (paving and
    #    plaza colours the wide frames never show) and one roof-off interior.
    #    A fit missing the close zoom measured that zoom at 12.94% foreign —
    #    the corpus has to cover the zoom tiers or the gate reds a good frame.
    "pos-owned-island-hamlet": (
        "positive", "pos-owned-island-hamlet.png",
        "Owned isometric live capture (cabinet-meta "
        "designs/world-iso-hamlet-island-2026-07-28.png, 2400x1760)",
        "Wide island at today's org state: computed fbm+dither ground, worn "
        "lanes, districts, quay. The default frame every renderer change is "
        "judged on.",
    ),
    "pos-owned-island-camp": (
        "positive", "pos-owned-island-camp.png",
        "Owned isometric live capture (cabinet-meta "
        "designs/world-camp-overgrown-2026-07-27.png, 2400x1760)",
        "Wide island in the wilderness/camp era — the Captain's subtractive-"
        "clearing inversion. Different terrain mix from the hamlet, so the "
        "palette covers overgrowth and not only cleared ground.",
    ),
    "pos-owned-square-close": (
        "positive", "pos-owned-square-close.png",
        "Owned isometric live capture, close zoom (cabinet-meta "
        "designs/cabinet-world-iso-v24-zoom-square-2026-07-25.png, 1200x800)",
        "Close-zoom village square: paving, benches, lamp posts at texture "
        "level. Carries the plaza colours no wide frame exercises.",
    ),
    "pos-owned-interior-cutaway": (
        "positive", "pos-owned-interior-cutaway.png",
        "Owned isometric roof-off capture, post alpha-hole fix (cabinet-meta "
        "designs/world-iso-roof-off-great-house-close-FIXED-2026-07-28.png, "
        "1440x960)",
        "Roof-off interior: floors, walls, furniture. The frame whose alpha "
        "holes the Captain diagnosed, AFTER the cutout fix — so the corpus "
        "records the corrected interior, never the bug.",
    ),

    # ── PALETTE SOURCE: the art itself, not a render of it. ─────────────────
    "pal-owned-atlas": (
        "palette", "pal-owned-atlas.png",
        "Copy of the repo's own TRACKED owned isometric atlas "
        "(cabinet/dashboard/public/world-assets/originals/iso/atlas-0.png, "
        "2048x2048, 182 frames) — the one corpus member reconstructible from "
        "a plain checkout with a single cp",
        "Defines every colour the owned sprites may draw, independently of "
        "which sprites a chosen render happens to contain. Without it an "
        "all-owned-sprite frame reads foreign (6.52% vs 1.23% measured).",
    ),

    # ── NEGATIVES: Captain rulings on our OWN builds. Kept across the re-fit
    #    because accumulated taste is never dropped (see _carried_entries).
    "neg-island-void": (
        "negative", "neg-island-void.png",
        "Captain-rejected Cabinet World build screenshot 2026-07-08 "
        "(~/.claude/image-cache/e55f9b5f-b7cf-469f-af48-89a202a8cc4a/5.png, Island Z0)",
        "Ground-truth rejection: sparse props floating on flat green void — no terrain "
        "variation, no paths, no shore, buildings unanchored.",
    ),
    "neg-city-street-void": (
        "negative", "neg-city-street-void.png",
        "Captain-rejected Cabinet World build screenshot 2026-07-08 "
        "(~/.claude/image-cache/e55f9b5f-b7cf-469f-af48-89a202a8cc4a/6.png, Street Z1)",
        "Ground-truth rejection: buildings against black void, garbled road-marking "
        "tiling, near-empty street — incomplete scene assembly.",
    ),
    "neg-grey-wardroom": (
        "negative", "neg-grey-wardroom.png",
        "Captain-rejected Cabinet World build screenshot 2026-07-08 "
        "(~/.claude/image-cache/e55f9b5f-b7cf-469f-af48-89a202a8cc4a/7.png, Wardroom Z2)",
        "Ground-truth rejection: vast grey floor, one desk strip, scattered orphan "
        "chairs/props — an unfurnished room, not a composed interior.",
    ),

    # ── NEGATIVES: the same failure mode rebuilt in the OWNED art family, so
    #    the composition bounds have ground truth that cannot be passed on
    #    art-family grounds. These trip clustering and PASS palette BY DESIGN
    #    — that separation is the point, and calibrate.py prove asserts it in
    #    both directions rather than leaving it to be assumed.
    "neg-owned-scatter-sparse": (
        "negative", "neg-owned-scatter-sparse.png",
        "Synthetic (build_corpus.py synthetic, seed 42, 18 props): owned atlas "
        "frames scattered on the world's own ground colour",
        "Reproduces the rejected failure mode at low density in owned art: "
        "unrelated props dropped on an untextured field with no grounding.",
    ),
    "neg-owned-scatter-dense": (
        "negative", "neg-owned-scatter-dense.png",
        "Synthetic (build_corpus.py synthetic, seed 1337, 90 props): owned "
        "atlas frames scattered on the world's own ground colour",
        "Same failure mode at high density: clutter without composition still "
        "fails — density alone must not fool the judge.",
    ),
    "neg-owned-void": (
        "negative", "neg-owned-void.png",
        "Synthetic (build_corpus.py synthetic, seed 5150): owned atlas "
        "buildings on the world's own flat ground colour, no terrain",
        "The island-void rejection rebuilt in owned art: real buildings, real "
        "palette, no terrain variation, no paths, nothing anchored.",
    ),
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _corpus_path(corpus: Path, cls: str, filename: str) -> Path:
    p = (corpus / cls / filename).resolve()
    if not p.is_relative_to(corpus.resolve()):  # path-containment guard
        raise ValueError(f"path escapes corpus dir: {p}")
    return p


# ------------------------------------------------------------- synthetics

def _atlas_cutter():
    """(cut(name), frames) over the repo's OWN tracked owned iso pack."""
    from PIL import Image

    pack_json = ISO_PACK / "world-pack.json"
    atlas_png = ISO_PACK / "atlas-0.png"
    if not pack_json.is_file() or not atlas_png.is_file():
        sys.exit(f"owned iso pack not found under {ISO_PACK} — cannot build "
                 f"the synthetic negatives from owned art")
    pack = json.loads(pack_json.read_text())
    atlas = Image.open(atlas_png).convert("RGBA")

    def cut(name: str):
        f = pack["frames"][name]
        im = atlas.crop((f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"]))
        if f["scale"] != 1:
            im = im.resize((f["dw"], f["dh"]), Image.NEAREST)
        return im

    return cut, pack["frames"]


def make_synthetic(corpus: Path) -> None:
    from PIL import Image

    cut, frames = _atlas_cutter()
    props = [p for p in SCATTER_PROPS if p in frames]
    builds = [b for b in VOID_BUILDINGS if b in frames]
    if len(props) < 5 or len(builds) < 3:
        sys.exit(f"owned pack is missing scatter/void frames (props "
                 f"{len(props)}, buildings {len(builds)}) — refusing to build "
                 f"a synthetic negative from a different set than the "
                 f"manifest records")

    for name, seed, count in (("neg-owned-scatter-sparse.png", 42, 18),
                              ("neg-owned-scatter-dense.png", 1337, 90)):
        rng = random.Random(seed)
        canvas = Image.new("RGB", CANVAS, OWNED_GROUND)
        for _ in range(count):
            s = cut(props[rng.randrange(len(props))])
            x = rng.randint(-s.width // 2, CANVAS[0] - s.width // 2)
            y = rng.randint(-s.height // 2, CANVAS[1] - s.height // 2)
            canvas.paste(s, (x, y), s)
        out = _corpus_path(corpus, "negative", name)
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out)
        print(f"wrote {out.relative_to(HERE)}")

    rng = random.Random(5150)
    canvas = Image.new("RGB", CANVAS, OWNED_GROUND)
    for i, name in enumerate(builds[:5]):
        s = cut(name)
        x = 90 + (i % 3) * 380 + rng.randint(-20, 20)
        y = 120 + (i // 3) * 380 + rng.randint(-20, 20)
        canvas.paste(s, (x, y), s)
    out = _corpus_path(corpus, "negative", "neg-owned-void.png")
    canvas.save(out)
    print(f"wrote {out.relative_to(HERE)}")


# --------------------------------------------------------------- manifest

def _carried_entries(corpus: Path, manifest: Path) -> list[dict]:
    """Preserve non-REGISTRY manifest entries (Captain-recorded verdicts).

    judge/goldens.py `record` appends Captain approve/reject frames to the
    manifest (taste accumulation). Rebuilding from REGISTRY alone would
    silently DROP that accumulated taste — so carried entries survive a
    rebuild, and a carried file that is missing or has drifted bytes is a
    hard stop, never a silent drop.
    """
    if not manifest.exists():
        return []
    carried = []
    for img in json.loads(manifest.read_text()).get("images", []):
        if img.get("id") in REGISTRY:
            continue  # rebuilt from REGISTRY
        p = (corpus.parent / Path(img["file"])).resolve()
        if not p.is_relative_to(corpus.resolve()):
            sys.exit(f"carried manifest entry escapes corpus dir: "
                     f"{img['file']}")
        if not p.exists():
            sys.exit(f"carried (Captain-recorded) corpus file missing: "
                     f"{img['file']} — restore it or consciously remove "
                     f"the manifest entry")
        if sha256_of(p) != img["sha256"]:
            sys.exit(f"carried corpus file changed on disk: {img['file']} "
                     f"— re-record the Captain verdict instead of mutating "
                     f"corpus bytes")
        carried.append(img)
    return carried


def build_manifest(corpus: Path) -> None:
    manifest = corpus / "manifest.json"
    rel = corpus.name
    images, missing = [], []
    for entry_id, (cls, filename, provenance, why) in sorted(REGISTRY.items()):
        p = _corpus_path(corpus, cls, filename)
        if not p.exists():
            missing.append(entry_id)
            continue
        images.append({
            "id": entry_id,
            "class": cls,
            "file": f"{rel}/{cls}/{filename}",
            "sha256": sha256_of(p),
            "provenance": provenance,
            "why": why,
        })
    if missing:
        sys.exit(f"missing corpus files for: {', '.join(missing)} "
                 f"(run `build_corpus.py synthetic` / re-assemble per provenance)")
    images = sorted(images + _carried_entries(corpus, manifest),
                    key=lambda i: i["id"])
    counts = {c: sum(1 for i in images if i["class"] == c) for c in CLASSES}
    payload = {
        "purpose": "Calibration corpus for the Cabinet World aesthetic judge. "
                   "positive = OWNED isometric scenes the Captain has seen; "
                   "negative = Captain-rejected builds + synthetic owned-art "
                   "scatter/void; palette = owned atlas (palette fit only, "
                   "never the judge).",
        "note": "Image files are gitignored (instance renders); this manifest "
                "is the tracked record. Verify with `build_corpus.py verify`. "
                "The pre-2026-07-28 LimeZu corpus is preserved verbatim at "
                "corpus-limezu-2026-07-08/ and the calibration it produced at "
                "calibration/archive/limezu-2026-07-08/.",
        "refit": {
            "date": "2026-07-28",
            "reason": "Captain direction: every world pixel becomes owned "
                      "generated art. A palette fitted to LimeZu measured "
                      "owned frames at 57-90% foreign against a 5% limit — "
                      "the gate was pointed at the art family we are leaving.",
            "supersedes": "corpus-limezu-2026-07-08/manifest.json",
            "argument": "cabinet-meta designs/"
                        "world-aesthetic-corpus-refit-2026-07-28.md",
        },
        "counts": counts,
        "images": images,
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {manifest.relative_to(HERE)} — "
          + ", ".join(f"{v} {k}" for k, v in counts.items()))


def verify(corpus: Path) -> None:
    manifest = corpus / "manifest.json"
    if not manifest.is_file():
        sys.exit(f"no manifest at {manifest}")
    data = json.loads(manifest.read_text())
    bad = 0
    for img in data["images"]:
        rel = Path(img["file"])
        p = (corpus.parent / rel).resolve()
        if not p.is_relative_to(corpus.resolve()):
            print(f"SKIP (escapes corpus): {rel}")
            bad += 1
            continue
        if not p.exists():
            print(f"MISSING: {rel}")
            bad += 1
        elif sha256_of(p) != img["sha256"]:
            print(f"HASH MISMATCH: {rel}")
            bad += 1
    total = len(data["images"])
    print(f"{total - bad}/{total} corpus images verified OK ({corpus.name})")
    if bad:
        sys.exit(1)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        prog="build_corpus.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["synthetic", "manifest", "verify"])
    ap.add_argument("--corpus", default=str(CORPUS),
                    help="corpus dir (default corpus/; pass "
                         "corpus-limezu-2026-07-08 to verify the archive)")
    args = ap.parse_args(argv)
    corpus = Path(args.corpus).resolve()
    if args.cmd == "synthetic":
        make_synthetic(corpus)
    elif args.cmd == "manifest":
        build_manifest(corpus)
    else:
        verify(corpus)


if __name__ == "__main__":
    main()
