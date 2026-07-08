"""Pytest bootstrap for the world-aesthetic gates.

Loads the gates package + runner + calibrate via importlib under UNIQUE
module names (world_aesthetic_*) — never as top-level "gates", which is the
pre-existing cabinet/scripts/gates package. No sys.path mutation.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

WA_DIR = Path(__file__).resolve().parents[1]
CORPUS_DIR = WA_DIR / "corpus"
CALIB_DIR = WA_DIR / "calibration"


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
        png=gates._png, common=gates._common, synth=gates._synth,
        base_map=base_map, blob=blob,
        SOLID_DIRT=SOLID_DIRT, SOLID_GRASS=SOLID_GRASS,
        errors=errors, codes=codes, write_json=write_json,
        corpus_dir=CORPUS_DIR, calib_dir=CALIB_DIR,
        has_corpus=(CORPUS_DIR / "positive").is_dir()
        and any((CORPUS_DIR / "positive").glob("*.png")),
    )
