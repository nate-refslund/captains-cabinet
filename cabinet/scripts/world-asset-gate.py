#!/usr/bin/env python3.12
"""world-asset-gate.py — asset conformance gate (Cabinet World E1).

Chassis Part 5 asset-forge gate + kickoff doctrine line: "asset conformance
gate (palette/grid/alpha) before any sprite enters the manifest; realpath
containment for world assets."

Every asset referenced by cabinet/dashboard/public/world-assets/manifest.json
must pass, or the gate fails (and the renderer must not load it):

  * PNG magic bytes ONLY (\\x89PNG\\r\\n\\x1a\\n) — never SVG/JS/HTML (an
    asset manifest must never become a script-injection or arbitrary-read
    vector);
  * realpath containment inside the world-assets dir (a manifest entry can
    never point at cabinet/.env or anywhere else outside the asset root);
  * declared w/h match the actual IHDR dimensions;
  * dimensions sit on the 16px art grid (16/32/48/64...);
  * sha256 matches when declared (content-addressed manifest discipline).

LimeZu packs are a Captain purchase (kickoff to-do 1; WORLD-E1-ASSETS
ledger row) and are NEVER committed (commercial license) — the asset dir is
gitignored, the manifest is tracked, and this gate runs wherever assets
land. Exit 0 = all conformant (or manifest honestly empty), 1 = violation.

Usage: python3.12 cabinet/scripts/world-asset-gate.py [manifest.json]
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from typing import Any, List

_REPO_ROOT = Path(os.environ.get("CABINET_ROOT")
                  or Path(__file__).resolve().parents[2])
DEFAULT_MANIFEST = (_REPO_ROOT / "cabinet" / "dashboard" / "public"
                    / "world-assets" / "manifest.json")

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
GRID = 16


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    """Width/height from the IHDR chunk (first chunk after the signature)."""
    if len(data) < 33 or data[:8] != PNG_MAGIC:
        return None
    if data[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", data[16:24])
    return int(w), int(h)


def check_asset(entry: Any, asset_root: Path, problems: List[str]) -> None:
    if not isinstance(entry, dict):
        problems.append("manifest entry is not a mapping")
        return
    aid = str(entry.get("id", "?"))
    rel = entry.get("path")
    if not isinstance(rel, str) or not rel:
        problems.append(f"{aid}: path missing")
        return
    candidate = asset_root / rel
    real = Path(os.path.realpath(candidate))
    root_real = Path(os.path.realpath(asset_root))
    try:
        real.relative_to(root_real)
    except ValueError:
        problems.append(f"{aid}: path escapes the asset root "
                        f"({rel} -> {real}) — realpath containment")
        return
    if not real.exists():
        problems.append(f"{aid}: file missing ({rel}) — a manifest must "
                        f"never cite an absent asset")
        return
    data = real.read_bytes()
    if data[:8] != PNG_MAGIC:
        problems.append(f"{aid}: not a PNG (magic bytes) — SVG/JS/HTML "
                        f"refused by doctrine")
        return
    dims = png_dimensions(data)
    if dims is None:
        problems.append(f"{aid}: unreadable IHDR")
        return
    w, h = dims
    dw, dh = entry.get("w"), entry.get("h")
    if isinstance(dw, int) and isinstance(dh, int) and (dw, dh) != (w, h):
        problems.append(f"{aid}: declared {dw}x{dh} but file is {w}x{h}")
    if w % GRID or h % GRID:
        problems.append(f"{aid}: {w}x{h} off the {GRID}px art grid")
    sha = entry.get("sha256")
    if isinstance(sha, str) and sha:
        actual = hashlib.sha256(data).hexdigest()
        if actual != sha:
            problems.append(f"{aid}: sha256 mismatch (content-addressed "
                            f"manifest — declared {sha[:12]}…, actual "
                            f"{actual[:12]}…)")


def main(argv: List[str]) -> int:
    manifest_path = Path(argv[0]) if argv else DEFAULT_MANIFEST
    if not manifest_path.exists():
        print(f"WORLD_ASSETS ABSENT — no manifest at {manifest_path} "
              f"(placeholder-graphics mode; LimeZu drop-in pending, "
              f"WORLD-E1-ASSETS)")
        return 0
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"WORLD_ASSETS FAIL — manifest unreadable: {e}")
        return 1
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        print("WORLD_ASSETS FAIL — manifest.assets must be a list")
        return 1
    problems: List[str] = []
    asset_root = manifest_path.parent
    for entry in assets:
        check_asset(entry, asset_root, problems)
    for p in problems:
        print(f"FAIL {p}")
    if problems:
        print(f"WORLD_ASSETS FAIL (assets={len(assets)}, "
              f"violations={len(problems)})")
        return 1
    print(f"WORLD_ASSETS GREEN (assets={len(assets)} — all conformant"
          f"{'; manifest empty, placeholder mode' if not assets else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
