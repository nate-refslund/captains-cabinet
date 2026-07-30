"""Pytest bootstrap for the world-aesthetic gates.

Loads the gates package + runner + calibrate via importlib under UNIQUE
module names (world_aesthetic_*) — never as top-level "gates", which is the
pre-existing cabinet/scripts/gates package. No sys.path mutation.

THE CORPUS IS VERIFIED HERE, and that is not housekeeping. Until 2026-07-30 the
corpus arms gated on `has_corpus` — "are there any PNGs in corpus/positive?" —
which is a different question from "is this the corpus the tracked manifest
declares". Measured on ONE commit: the manifest's corpus gives 96 passed; the
ARCHIVED pre-re-fit corpus dropped into the same directory gives 4 failed; a
fresh CI checkout gives 5 skipped. Three verdicts from one tree, and nothing in
the suite could tell them apart — so the reds were unattributable and the greens
were unearned. Now every member present on disk is sha256-checked against the
manifest and a MISMATCH IS A HARD FAILURE naming the ids, never a skip and never
a quiet pass; every member the repo can rebuild is materialised first, so the
arms actually run in CI instead of skipping; and the members that genuinely
cannot be reconstructed are declared, pinned, and reported by name rather than
relabelled as covered.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

WA_DIR = Path(__file__).resolve().parents[1]
CORPUS_DIR = WA_DIR / "corpus"
CALIB_DIR = WA_DIR / "calibration"


def _corpus_state(builder) -> tuple[dict, list[str], list[str]]:
    """(verified paths by class, held ids, mismatching ids).

    `builder` is the loaded build_corpus module — the ONE place that knows how a
    member is rebuilt, so this file never carries a second copy of that list.
    """
    manifest = CORPUS_DIR / "manifest.json"
    if not manifest.is_file():
        return {}, [], []
    try:
        held = builder.materialise(CORPUS_DIR)
    except SystemExit as e:                       # a recipe that cannot run
        pytest.fail(f"corpus materialise refused: {e}")
    except ImportError as e:
        # Pillow builds the synthetic negatives. The gates themselves are
        # stdlib-only, so a missing Pillow is only fatal when it actually costs
        # coverage — and then it IS fatal, never a quiet reversion to the skip
        # this whole change removed. (`cabinet-ci.yml` pins pillow in this job
        # for the same stated reason.)
        held = [i["id"] for i in json.loads(manifest.read_text())["images"]]
        absent = [e_id for e_id, row in builder.REGISTRY.items()
                  if row[4] is not None
                  and not (WA_DIR / "corpus" / row[0] / row[1]).is_file()]
        if absent:
            pytest.fail(
                f"Pillow is missing ({e}), so these REBUILDABLE corpus members "
                f"could not be materialised: {', '.join(sorted(absent))}. Every "
                "arm that reads them would skip — which is the disabled sensor "
                "this fixture exists to prevent. `pip install pillow`.")
    data = json.loads(manifest.read_text())
    rebuildable = {e for e, row in builder.REGISTRY.items() if row[4] is not None}
    verified: dict[str, list[Path]] = {}
    mismatch, missing = [], []
    for img in data["images"]:
        p = WA_DIR / img["file"]
        if not p.is_file():
            missing.append(img["id"])
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != img["sha256"]:
            # BYTES first because it is free; PIXELS only when the bytes differ
            # AND the member is one this checkout rebuilt.
            #
            # A rebuilt PNG is re-encoded by the local zlib, so a macOS laptop
            # and an ubuntu runner write the same picture as different files —
            # measured, CI run 30566688025, after three byte-identical
            # regenerations on one machine had made it look settled. The file
            # digest is the right invariant for a member that is TRANSPORTED
            # and the wrong one for a member that is GENERATED, and conflating
            # them turns a portable corpus into a machine-specific one.
            same_pixels = (
                img["id"] in rebuildable
                and img.get("pixels_sha256")
                and builder.pixels_sha256_of(p) == img["pixels_sha256"])
            if not same_pixels:
                mismatch.append(img["id"])
                continue
        verified.setdefault(img["class"], []).append(p)
    for cls in verified:
        verified[cls].sort()
    return verified, sorted(set(held) | set(missing)), sorted(mismatch)


def _load(name: str, path: Path):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


@pytest.fixture(scope="session")
def wa():
    loader = _load("world_aesthetic_loader", WA_DIR / "_loader.py")
    gates = loader.load_gates()
    runner = _load("world_aesthetic_runner", WA_DIR / "aesthetic_gates.py")
    calibrate = _load("world_aesthetic_calibrate", WA_DIR / "calibrate.py")
    builder = _load("world_aesthetic_build_corpus", WA_DIR / "build_corpus.py")

    verified, held, mismatch = _corpus_state(builder)
    if mismatch:
        # NOT a skip. A corpus that is present but is not the one the manifest
        # records makes every verdict below meaningless in an unattributable
        # direction — it is how the same commit produced 96 green on one machine
        # and 4 red on another, with no line anywhere saying why.
        pytest.fail("corpus members on disk do NOT match the tracked manifest: "
                    + ", ".join(mismatch)
                    + " — re-assemble per provenance or re-record the manifest; "
                      "a corpus the suite cannot identify proves nothing either way")

    def corpus(cls: str) -> list[Path]:
        """Only members verified against the manifest. Never a bare glob.

        A glob is a set that cannot detect removal from itself: drop a positive
        and the loop simply runs one fewer time, green. The manifest is the
        declared set, so a member that goes missing is reported as held rather
        than silently unchecked.
        """
        return list(verified.get(cls, []))

    def require(cls: str):
        """Skip ONLY for members the repo genuinely cannot reconstruct, and say
        which ones. Any other absence is a failure."""
        if corpus(cls):
            return
        if held:
            pytest.skip(f"no verified {cls} member: the whole {cls} class is HELD "
                        f"(cannot be rebuilt from a checkout) — {', '.join(held)}")
        pytest.fail(f"no verified {cls} member and nothing is declared held — "
                    "the corpus is neither present nor honestly absent")

    def base_map(w=8, h=8):
        return {
            "schema": "cabinet.world.map/v1",
            "tile_size": 16,
            "width": w, "height": h,
            "anchor": [1, 1],
            "sheets": {
                "outdoor": {
                    "grid": 16,
                    "autotile": [
                        {"origin": [0, 0], "size": [3, 3],
                         "convention": "blob3x3",
                         "primary": "grass", "secondary": "dirt"},
                        {"origin": [3, 0], "size": [1, 1],
                         "convention": "solid", "primary": "dirt"},
                        {"origin": [4, 0], "size": [1, 1],
                         "convention": "solid", "primary": "grass"},
                    ],
                },
                "props": {"grid": 16},
                "charset": {"grid": 16},
                "b48": {"grid": 48},
            },
            "layers": [],
        }

    def blob(cx, cy):  # region of blob3x3 cell (cx,cy) in the outdoor sheet
        return [cx * 16, cy * 16, 16, 16]

    SOLID_DIRT = [48, 0, 16, 16]
    SOLID_GRASS = [64, 0, 16, 16]

    def errors(findings):
        return [f for f in findings if f["severity"] == "error"]

    def codes(findings):
        return [f["code"] for f in findings]

    def write_json(path, obj):
        Path(path).write_text(json.dumps(obj))
        return str(path)

    return SimpleNamespace(
        dir=WA_DIR, gates=gates, runner=runner, calibrate=calibrate,
        builder=builder,
        png=gates._png, common=gates._common, synth=gates._synth,
        base_map=base_map, blob=blob,
        SOLID_DIRT=SOLID_DIRT, SOLID_GRASS=SOLID_GRASS,
        errors=errors, codes=codes, write_json=write_json,
        corpus_dir=CORPUS_DIR, calib_dir=CALIB_DIR,
        corpus=corpus, require=require, held=held,
        has_corpus=bool(verified.get("positive")),
    )
