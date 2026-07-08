"""Gate 2 — connectivity (MAP): every building door reachable from the anchor.

Mechanics: resolve per-cell walkability from the map (see _common schema
rules), 4-connected BFS from map["anchor"], then require every door cell to
be visited. Catches the unanchored-building class: a house dropped on the
grass with no path, a door walled off by its own footprint, an anchor placed
on collision.
"""

from __future__ import annotations

from collections import deque

from . import _common as C

GATE = "connectivity"


def check(map_data: dict, config: dict | None = None) -> list[dict]:
    findings: list[dict] = []
    W, H = map_data["width"], map_data["height"]
    occ = C.build_occupancy(map_data)
    walkable, doors = occ["walkable"], occ["doors"]

    anchor = map_data.get("anchor")
    if not (isinstance(anchor, (list, tuple)) and len(anchor) == 2):
        findings.append(C.finding(
            GATE, "CONNECT_NO_ANCHOR", C.SEV_ERROR,
            "map has no anchor cell — connectivity has no root"))
        return findings
    ax, ay = anchor
    if not (0 <= ax < W and 0 <= ay < H):
        findings.append(C.finding(
            GATE, "CONNECT_NO_ANCHOR", C.SEV_ERROR,
            f"anchor {list(anchor)} outside map bounds {W}x{H}",
            where={"cell": list(anchor)}))
        return findings

    if not walkable:
        findings.append(C.finding(
            GATE, "CONNECT_NO_WALKABLE", C.SEV_ERROR,
            "map has no walkable cells at all"))
        return findings

    start = (ax, ay)
    if start not in walkable:
        findings.append(C.finding(
            GATE, "CONNECT_ANCHOR_UNWALKABLE", C.SEV_ERROR,
            f"anchor cell {list(anchor)} is not walkable",
            where={"cell": list(anchor)},
            data={"walkable_cells": len(walkable)}))
        return findings

    visited = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            c = (nx, ny)
            if 0 <= nx < W and 0 <= ny < H and c in walkable and c not in visited:
                visited.add(c)
                q.append(c)

    if not doors:
        findings.append(C.finding(
            GATE, "CONNECT_NO_DOORS", C.SEV_INFO,
            "map declares no door cells — nothing to prove reachable"))
    unreachable = sorted(d for d in doors if d not in visited)
    for d in unreachable:
        findings.append(C.finding(
            GATE, "CONNECT_DOOR_UNREACHABLE", C.SEV_ERROR,
            f"door at {list(d)} unreachable from anchor {list(anchor)} "
            "via walkable/path tiles",
            where={"cell": list(d)}))
    findings.append(C.finding(
        GATE, "CONNECT_STATS", C.SEV_INFO,
        f"reached {len(visited)}/{len(walkable)} walkable cells; "
        f"{len(doors) - len(unreachable)}/{len(doors)} doors reachable",
        data={"walkable": len(walkable), "reached": len(visited),
              "doors": len(doors), "unreachable_doors": len(unreachable)}))
    return C.cap_findings(findings, GATE)
