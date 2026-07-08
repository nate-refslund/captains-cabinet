"""Shared plumbing for the aesthetic gates: findings, map schema v1, occupancy.

MAP SCHEMA — cabinet.world.map/v1 (the tilemap JSON the renderer will emit;
defined HERE first, per the build kickoff — the renderer conforms to this):

{
  "schema": "cabinet.world.map/v1",
  "tile_size": 16,                       # px per map cell (world is 16px-grid)
  "width": 48, "height": 32,             # map size in cells
  "anchor": [24, 16],                    # spawn/reference cell (connectivity root)
  "sheets": {                            # source-sheet metadata
    "<sheet-name>": {
      "grid": 16,                        # native px grid of the SOURCE sheet
      "autotile": [                      # optional autotile blocks in the sheet
        {"origin": [0, 0],               # block origin, in sheet TILE units
         "size": [3, 3],                 # block size, in tiles
         "convention": "blob3x3",        # key into gates/data/autotile_conventions.json
         "primary": "grass",             # terrain the block paints
         "secondary": "dirt"}            # terrain it transitions into
      ]
    }
  },
  "layers": [
    {"name": "ground", "kind": "terrain", "walkable": true,
     "tiles": [
       {"sheet": "outdoor", "region": [16, 0, 16, 16],  # src rect, PX [x,y,w,h]
        "x": 0, "y": 0}                                 # dest cell (tile units)
     ]},
    ...
  ]
}

Layer "kind" vocabulary + walkability defaults (tile.walkable / layer.walkable
override; explicit beats default):
  terrain, path, door  -> walk-positive
  building, prop, collision -> blocking (footprint = ceil(region/tile_size))
  entity, decor, label, other -> neutral (no contribution)
Door cells (kind=="door" or tile.door==true) punch through blocking — a door
must be enterable. Explicit tile.walkable==true punches through likewise.

FINDINGS: every gate returns a list of dicts
  {"gate", "code", "severity": error|warn|info, "message", "where", "data"}
error → runner exit 1; warn → exit 0 unless --strict; info → never fails.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SEV_ERROR = "error"
SEV_WARN = "warn"
SEV_INFO = "info"

MAP_SCHEMA_PREFIX = "cabinet.world.map/"
LABELS_SCHEMA_PREFIX = "cabinet.world.labels/"

KIND_WALK = {"terrain", "path", "door"}
KIND_BLOCK = {"building", "prop", "collision"}

# Cap identical-class findings per gate so a broken map can't emit megabytes.
FINDING_CAP = 200


def finding(gate: str, code: str, severity: str, message: str,
            where=None, data=None) -> dict:
    f = {"gate": gate, "code": code, "severity": severity, "message": message}
    if where is not None:
        f["where"] = where
    if data is not None:
        f["data"] = data
    return f


def cap_findings(findings: list[dict], gate: str) -> list[dict]:
    if len(findings) <= FINDING_CAP:
        return findings
    kept = findings[:FINDING_CAP]
    kept.append(finding(
        gate, "FINDINGS_TRUNCATED", SEV_INFO,
        f"{len(findings) - FINDING_CAP} further findings truncated "
        f"(cap {FINDING_CAP})", data={"total": len(findings)}))
    return kept


def load_json(path: str | Path):
    return json.loads(Path(path).read_text())


def sha256_path(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


class MapError(ValueError):
    pass


def _is_cell_pair(v) -> bool:
    return (isinstance(v, (list, tuple)) and len(v) == 2
            and all(isinstance(c, int) for c in v))


def validate_map(m) -> list[str]:
    """Structural validation. Returns list of fatal problems (empty = usable)."""
    probs: list[str] = []
    if not isinstance(m, dict):
        return ["map is not a JSON object"]
    if not str(m.get("schema", "")).startswith(MAP_SCHEMA_PREFIX):
        probs.append(f'schema must start with "{MAP_SCHEMA_PREFIX}"')
    for k in ("width", "height"):
        if not isinstance(m.get(k), int) or m.get(k, 0) <= 0:
            probs.append(f"{k} must be a positive int")
    ts = m.get("tile_size", 16)
    if not isinstance(ts, int) or ts <= 0:
        probs.append("tile_size must be a positive int")
    if "anchor" in m and not _is_cell_pair(m["anchor"]):
        probs.append("anchor must be [x, y] ints")
    layers = m.get("layers")
    if not isinstance(layers, list):
        probs.append("layers must be a list")
        return probs
    for li, layer in enumerate(layers):
        if not isinstance(layer, dict):
            probs.append(f"layers[{li}] not an object")
            continue
        if not isinstance(layer.get("name"), str):
            probs.append(f"layers[{li}].name missing")
        if not isinstance(layer.get("kind"), str):
            probs.append(f"layers[{li}].kind missing")
        tiles = layer.get("tiles")
        if not isinstance(tiles, list):
            probs.append(f"layers[{li}].tiles must be a list")
            continue
        for ti, t in enumerate(tiles):
            if not isinstance(t, dict):
                probs.append(f"layers[{li}].tiles[{ti}] not an object")
                continue
            r = t.get("region")
            if (not isinstance(r, (list, tuple)) or len(r) != 4
                    or not all(isinstance(v, int) and v >= 0 for v in r)
                    or r[2] <= 0 or r[3] <= 0):
                probs.append(f"layers[{li}].tiles[{ti}].region must be "
                             "[x,y,w,h] non-negative ints, w/h > 0")
            if not isinstance(t.get("sheet"), str):
                probs.append(f"layers[{li}].tiles[{ti}].sheet missing")
            if not isinstance(t.get("x"), int) or not isinstance(t.get("y"), int):
                probs.append(f"layers[{li}].tiles[{ti}].x/y must be ints")
            if len(probs) > 40:  # enough to diagnose; don't flood
                probs.append("... (further problems suppressed)")
                return probs
    return probs


def load_map(path: str | Path) -> dict:
    m = load_json(path)
    probs = validate_map(m)
    if probs:
        raise MapError("invalid map: " + "; ".join(probs))
    return m


def footprint(tile: dict, tile_size: int) -> list[tuple[int, int]]:
    """Cells covered by a placed region (buildings span multiple cells)."""
    _, _, w, h = tile["region"]
    cw = max(1, math.ceil(w / tile_size))
    ch = max(1, math.ceil(h / tile_size))
    x0, y0 = tile["x"], tile["y"]
    return [(x0 + dx, y0 + dy) for dy in range(ch) for dx in range(cw)]


def build_occupancy(m: dict) -> dict:
    """Resolve per-cell walkability + door cells from all layers.

    Returns {"walkable": set, "doors": set, "walk_pos": set, "blocked": set}.
    walkable = (walk_pos | force) - (blocked - force); doors/explicit
    walkable==true force-punch through blocking footprints.
    """
    ts = m.get("tile_size", 16)
    W, H = m["width"], m["height"]
    walk_pos: set = set()
    blocked: set = set()
    force: set = set()
    doors: set = set()

    def in_bounds(c):
        return 0 <= c[0] < W and 0 <= c[1] < H

    for layer in m.get("layers", []):
        kind = layer.get("kind", "")
        lw = layer.get("walkable")
        for t in layer.get("tiles", []):
            cells = [c for c in footprint(t, ts) if in_bounds(c)]
            if not cells:
                continue
            tw = t.get("walkable")
            is_door = bool(t.get("door")) or kind == "door"
            if is_door:
                # Doors are single-cell entry points at the tile's dest cell.
                dc = (t["x"], t["y"])
                if in_bounds(dc):
                    doors.add(dc)
                    if tw is not False:
                        force.add(dc)
            if tw is True:
                force.update(cells)
            elif tw is False:
                blocked.update(cells)
            elif lw is True:
                walk_pos.update(cells)
            elif lw is False:
                blocked.update(cells)
            elif kind in KIND_WALK:
                walk_pos.update(cells)
            elif kind in KIND_BLOCK:
                blocked.update(cells)
            # neutral kinds: no contribution
    walkable = (walk_pos | force) - (blocked - force)
    return {"walkable": walkable, "doors": doors,
            "walk_pos": walk_pos, "blocked": blocked}
