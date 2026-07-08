"""Gate 1 — edge continuity (MAP): adjacent terrain tiles must be edge-compatible.

Mechanics: each terrain tile resolves, via its sheet's autotile blocks and the
conventions data (gates/data/autotile_conventions.json), to four side
signatures — tuples of terrain names along N/E/S/W. For every horizontally /
vertically adjacent pair in the same terrain layer, my E must equal their W
and my S their N. A grass-blob edge tile sitting next to plain grass interior
the wrong way round, a dirt path chopped mid-transition, the classic LimeZu
seam bugs — all reduce to a side-signature mismatch here.

Tiles whose region maps to no known autotile block are UNKNOWN: they match
anything (wildcard) and surface as capped info findings, so an uncalibrated
sheet degrades to observability, never false errors.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import _common as C

GATE = "edge_continuity"
DATA = Path(__file__).resolve().parent / "data" / "autotile_conventions.json"


def load_conventions(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or DATA).read_text())


def _sides_from_subgrid(rows: list[str], primary: str, secondary: str | None):
    def resolve(chars: str):
        out = []
        for ch in chars:
            if ch == "A":
                out.append(primary)
            else:
                if secondary is None:
                    raise ValueError(
                        "convention cell uses 'B' but block has no secondary")
                out.append(secondary)
        return tuple(out)

    n = resolve(rows[0])
    s = resolve(rows[2])
    w = resolve(rows[0][0] + rows[1][0] + rows[2][0])
    e = resolve(rows[0][2] + rows[1][2] + rows[2][2])
    return {"N": n, "E": e, "S": s, "W": w}


def _tile_sides(tile: dict, sheets: dict, conventions: dict, tile_size: int):
    """Resolve a placed tile to side signatures, or None if unknown."""
    sheet = sheets.get(tile["sheet"])
    if not sheet:
        return None
    grid = sheet.get("grid", tile_size)
    px, py, pw, ph = tile["region"]
    if pw != grid or ph != grid or px % grid or py % grid:
        return None  # not a single autotile cell of this sheet
    tx, ty = px // grid, py // grid
    for block in sheet.get("autotile", []):
        conv = conventions["conventions"].get(block.get("convention", ""))
        if not conv:
            continue
        ox, oy = block.get("origin", [0, 0])
        size = block.get("size") or conv.get("size")
        cx, cy = tx - ox, ty - oy
        if size is not None:
            sw, sh = size
            if not (0 <= cx < sw and 0 <= cy < sh):
                continue
        elif (cx, cy) != (0, 0) and conv["cells"].get("*") is None:
            continue
        cells = conv["cells"]
        rows = cells.get(f"{cx},{cy}") or cells.get("*")
        if rows is None:
            continue
        return _sides_from_subgrid(rows, block.get("primary", "?"),
                                   block.get("secondary"))
    return None


def check(map_data: dict, config: dict | None = None) -> list[dict]:
    cfg = config or {}
    conventions = cfg.get("conventions") or load_conventions(
        cfg.get("conventions_path"))
    sheets = map_data.get("sheets", {})
    ts = map_data.get("tile_size", 16)
    findings: list[dict] = []
    unknown_seen: set = set()

    for layer in map_data.get("layers", []):
        if layer.get("kind") != "terrain":
            continue
        lname = layer.get("name", "?")
        cellmap: dict[tuple[int, int], dict] = {}
        for t in layer.get("tiles", []):
            cell = (t["x"], t["y"])
            sides = _tile_sides(t, sheets, conventions, ts)
            if sides is None:
                key = (t["sheet"], tuple(t["region"]))
                if key not in unknown_seen:
                    unknown_seen.add(key)
                    findings.append(C.finding(
                        GATE, "EDGE_UNKNOWN_TILE", C.SEV_INFO,
                        f"terrain tile from sheet '{t['sheet']}' region "
                        f"{t['region']} matches no autotile block — treated "
                        "as wildcard",
                        where={"layer": lname, "cell": list(cell)},
                        data={"sheet": t["sheet"], "region": list(t["region"])}))
                cellmap[cell] = {"sides": None, "tile": t}
            else:
                cellmap[cell] = {"sides": sides, "tile": t}

        for (x, y), info in cellmap.items():
            a = info["sides"]
            if a is None:
                continue
            for (dx, dy, my_side, their_side) in ((1, 0, "E", "W"),
                                                  (0, 1, "S", "N")):
                nb = cellmap.get((x + dx, y + dy))
                if nb is None or nb["sides"] is None:
                    continue
                mine = a[my_side]
                theirs = nb["sides"][their_side]
                if mine != theirs:
                    findings.append(C.finding(
                        GATE, "EDGE_MISMATCH", C.SEV_ERROR,
                        f"terrain seam break in layer '{lname}': "
                        f"({x},{y}).{my_side}={'/'.join(mine)} vs "
                        f"({x + dx},{y + dy}).{their_side}={'/'.join(theirs)}",
                        where={"layer": lname,
                               "cells": [[x, y], [x + dx, y + dy]]},
                        data={"a_side": list(mine), "b_side": list(theirs),
                              "a_region": list(info["tile"]["region"]),
                              "b_region": list(nb["tile"]["region"])}))
    return C.cap_findings(findings, GATE)
