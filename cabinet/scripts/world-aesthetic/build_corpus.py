#!/usr/bin/env python3.12
"""Calibration corpus builder for the Cabinet World aesthetic judge.

The corpus lives in cabinet/scripts/world-aesthetic/corpus/{positive,negative}/
and is GITIGNORED (LimeZu-derived images are licensed; Captain-rejected build
screenshots are instance data). Only this script and corpus/manifest.json are
tracked. The manifest carries sha256 + provenance per image so any checkout can
verify (or re-assemble) the exact corpus without committing licensed pixels.

Usage (python3.12; `synthetic` needs Pillow — e.g. a venv with `pip install pillow`):
    build_corpus.py synthetic   # regenerate the 2 synthetic scatter negatives
    build_corpus.py manifest    # hash corpus images + write corpus/manifest.json
    build_corpus.py verify      # check corpus files against the tracked manifest

POSITIVE class: official LimeZu showcase/promo scenes (finished composed maps —
grounded terrain, paths, fences, shadows, purposeful prop placement).
NEGATIVE class: Captain-rejected Cabinet World build screenshots (2026-07-08)
plus synthetic random-prop-scatter-on-flat-green images reproducing the exact
rejected failure mode at two densities.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
MANIFEST = CORPUS / "manifest.json"
REPO_ROOT = HERE.parents[2]
WORLD_ASSETS = REPO_ROOT / "cabinet" / "dashboard" / "public" / "world-assets"

# Props sampled for the synthetic scatter negatives (repo-relative, all singles
# from the licensed world-assets tree, which is itself gitignored).
SCATTER_PROPS = [
    "exteriors/street/ME_Singles_City_Props_16x16_Bench_1.png",
    "exteriors/street/ME_Singles_City_Props_16x16_Street_Lamp_1.png",
    "exteriors/street/ME_Singles_City_Props_16x16_Tree_1.png",
    "exteriors/street/ME_Singles_City_Props_16x16_Tree_2.png",
    "exteriors/street/ME_Singles_City_Props_16x16_Hydrant_1.png",
    "exteriors/street/ME_Singles_City_Props_16x16_Black_Closed_Trash_Can.png",
    "exteriors/ME_Singles_City_Props_16x16_Mailbox_1.png",
]

FLAT_GREEN = (139, 195, 116)  # the exact rejected flat-green void backdrop
CANVAS = (768, 640)

# id -> (class, filename, provenance, why-it-belongs)
REGISTRY: dict[str, tuple[str, str, str, str]] = {
    "pos-village-island": (
        "positive", "pos-village-island.png",
        "LimeZu Serene Village showcase (itch.io limezu/serenevillagerevamped, "
        "image 803179/4541802, first GIF frame)",
        "Finished island village scene: shore transitions, fenced yard, path to door, "
        "grounded props — the composition bar Z0/Z1 exteriors must clear.",
    ),
    "pos-village-house": (
        "positive", "pos-village-house.png",
        "LimeZu Serene Village showcase (itch.io limezu/serenevillagerevamped, "
        "image 803179/4498755)",
        "Close-up composed house: fence lines, dirt path edge, mailbox placement, "
        "layered tree canopy — texture-level (Z1) composition reference.",
    ),
    "pos-farm-homestead": (
        "positive", "pos-farm-homestead.png",
        "LimeZu Modern Farm showcase (itch.io limezu/modernfarm, "
        "image 3354014/20024293, first GIF frame)",
        "Dense farm homestead: forest border, dirt clearing, fenced crop plots, "
        "characters mid-task — no empty voids anywhere in frame.",
    ),
    "pos-farm-barn-silo": (
        "positive", "pos-farm-barn-silo.png",
        "LimeZu Modern Farm showcase (itch.io limezu/modernfarm, "
        "image 3354014/20024294, first GIF frame)",
        "Barn + silo + animal pens scene: large structures grounded by paths, "
        "fences and animals — how big buildings sit in terrain.",
    ),
    "pos-city-street": (
        "positive", "pos-city-street.png",
        "LimeZu Modern Exteriors showcase (itch.io limezu/modernexteriors, "
        "image 1329426/8444670, first GIF frame)",
        "Composed city street: full paving coverage, road markings, crosswalk, "
        "streetlights and inhabitants — the standard the rejected street shot missed.",
    ),
    "pos-city-market-square": (
        "positive", "pos-city-market-square.png",
        "LimeZu Modern Exteriors showcase (itch.io limezu/modernexteriors, "
        "image 1329426/7805364, first GIF frame)",
        "Market square with stalls, fountain, benches, lamp posts: dense purposeful "
        "prop placement on continuous paving.",
    ),
    "pos-interior-hotel": (
        "positive", "pos-interior-hotel.png",
        "LimeZu Modern Interiors showcase (itch.io limezu/moderninteriors, "
        "image 671751/7034264, first GIF frame)",
        "Hotel hallway + lobby interior: complete walls, floor coverage, carpets on "
        "stairs, plants at doors — interior composition reference.",
    ),
    "pos-interior-restaurant": (
        "positive", "pos-interior-restaurant.png",
        "LimeZu Modern Interiors showcase (itch.io limezu/moderninteriors, "
        "image 671751/4589297, first GIF frame)",
        "Restaurant kitchen + dining interior: wall-hugging appliances, set tables, "
        "patterned floor, characters seated — furnished-interior bar for Z2.",
    ),
    "pos-office-floor": (
        "positive", "pos-office-floor.png",
        "LimeZu Modern Office Revamped showcase (itch.io limezu/modernoffice, "
        "img 6975002, first GIF frame)",
        "Office floor with cubicle rows, meeting nook, side rooms: desks face "
        "consistently, walkways read clearly — the wardroom target look.",
    ),
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
    "neg-scatter-sparse": (
        "negative", "neg-scatter-sparse.png",
        "Synthetic (build_corpus.py synthetic, seed 42, 18 props): random LimeZu "
        "singles scattered on flat green",
        "Reproduces the rejected failure mode at low density: unrelated props dropped "
        "on an untextured green field with no grounding.",
    ),
    "neg-scatter-dense": (
        "negative", "neg-scatter-dense.png",
        "Synthetic (build_corpus.py synthetic, seed 1337, 90 props): random LimeZu "
        "singles scattered on flat green",
        "Same failure mode at high density: clutter without composition still fails — "
        "density alone must not fool the judge.",
    ),
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _corpus_path(cls: str, filename: str) -> Path:
    p = (CORPUS / cls / filename).resolve()
    if not p.is_relative_to(CORPUS):  # path-containment guard
        raise ValueError(f"path escapes corpus dir: {p}")
    return p


def make_synthetic() -> None:
    from PIL import Image

    props = []
    for rel in SCATTER_PROPS:
        p = (WORLD_ASSETS / rel).resolve()
        if not p.is_relative_to(WORLD_ASSETS):
            raise ValueError(f"prop path escapes world-assets: {p}")
        if p.exists():
            props.append(Image.open(p).convert("RGBA"))
    if not props:
        sys.exit("no scatter props found under world-assets — cannot build synthetics")

    for name, seed, count in (("neg-scatter-sparse.png", 42, 18),
                              ("neg-scatter-dense.png", 1337, 90)):
        rng = random.Random(seed)
        canvas = Image.new("RGB", CANVAS, FLAT_GREEN)
        for _ in range(count):
            spr = props[rng.randrange(len(props))]
            scale = rng.choice((2, 3))  # chunky pixel scale, like the real renderer
            s = spr.resize((spr.width * scale, spr.height * scale), Image.NEAREST)
            x = rng.randint(-s.width // 2, CANVAS[0] - s.width // 2)
            y = rng.randint(-s.height // 2, CANVAS[1] - s.height // 2)
            canvas.paste(s, (x, y), s)
        out = _corpus_path("negative", name)
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out)
        print(f"wrote {out.relative_to(HERE)}")


def build_manifest() -> None:
    images, missing = [], []
    for entry_id, (cls, filename, provenance, why) in sorted(REGISTRY.items()):
        p = _corpus_path(cls, filename)
        if not p.exists():
            missing.append(entry_id)
            continue
        images.append({
            "id": entry_id,
            "class": cls,
            "file": f"corpus/{cls}/{filename}",
            "sha256": sha256_of(p),
            "provenance": provenance,
            "why": why,
        })
    if missing:
        sys.exit(f"missing corpus files for: {', '.join(missing)} "
                 f"(run `build_corpus.py synthetic` / re-fetch per provenance)")
    manifest = {
        "purpose": "Calibration corpus for the Cabinet World aesthetic judge "
                   "(positive = LimeZu showcase scenes; negative = Captain-rejected "
                   "builds + synthetic prop-scatter).",
        "note": "Image files are gitignored (LimeZu license); this manifest is the "
                "tracked record. Verify with `build_corpus.py verify`.",
        "counts": {
            "positive": sum(1 for i in images if i["class"] == "positive"),
            "negative": sum(1 for i in images if i["class"] == "negative"),
        },
        "images": images,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {MANIFEST.relative_to(HERE)} "
          f"({manifest['counts']['positive']} positive, "
          f"{manifest['counts']['negative']} negative)")


def verify() -> None:
    data = json.loads(MANIFEST.read_text())
    bad = 0
    for img in data["images"]:
        rel = Path(img["file"])
        p = (HERE / rel).resolve()
        if not p.is_relative_to(CORPUS):
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
    print(f"{total - bad}/{total} corpus images verified OK")
    if bad:
        sys.exit(1)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "synthetic":
        make_synthetic()
    elif cmd == "manifest":
        build_manifest()
    elif cmd == "verify":
        verify()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
