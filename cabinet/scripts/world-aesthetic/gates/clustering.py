"""Gate 6 — clustering (IMAGE+MAP): the scattered-props detector.

The Captain-rejected failure mode (corpus negatives, 5.png class): unrelated
props uniformly scattered over an untextured field. Two mechanical views:

MAP side (prop placements from kind=="prop" layers):
  * Clark-Evans R = mean nearest-neighbor distance / (0.5 * sqrt(area/n)).
    Uniform random scatter → R ≈ 1; designed clumping (benches by tables,
    tree groups, cleared plazas) → R well below 1. Fails when R > r_max.
  * open-space ratio: fraction of cells with Manhattan distance > open_radius
    from every prop. Scatter blankets the map (no clearings) → low ratio.
    Fails when ratio < open_min.
  * NN-distance CV as a secondary signal (uniform scatter ≈ 0.52) → warn only.

IMAGE side (render pixels):
  * flat-block mass: fraction of opaque block_px² blocks whose per-channel
    range <= flat_eps — untextured void (flat green / grey floor / black).
  * dominant share: mass of the single most common exact RGB.
  * busy CV: dispersion of per-block mean-abs-luma-deviation → warn band.
  Fails when flat_mass > flat_max OR dominant_share > dominant_max.

All bounds are FITTED from the positive corpus by calibrate.py (margins over
the worst positive), and calibrate --prove asserts corpus negatives fail /
positives pass — the prove-it contract for this gate.

BOUNDS SCHEMA — cabinet.world.clustering-bounds/v1:
{"schema": ..., "map": {"r_max", "open_min", "cv_min", "params", "fitted_from"},
 "image": {"flat_max", "dominant_max", "busy_cv_min", "params", "fitted_from"},
 "generated": iso}
"""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path

from . import _common as C
from . import _png

GATE = "clustering"
MIN_PROPS = 8
OPEN_RADIUS = 4
BLOCK_PX = 8
FLAT_EPS = 8


# ---------------------------------------------------------------- map side

def prop_centers(map_data: dict) -> list[tuple[float, float]]:
    ts = map_data.get("tile_size", 16)
    out = []
    for layer in map_data.get("layers", []):
        if layer.get("kind") != "prop":
            continue
        for t in layer.get("tiles", []):
            _, _, w, h = t["region"]
            fw = max(1, math.ceil(w / ts))
            fh = max(1, math.ceil(h / ts))
            out.append((t["x"] + fw / 2.0, t["y"] + fh / 2.0))
    return out


def map_stats(map_data: dict, min_props: int = MIN_PROPS,
              open_radius: int = OPEN_RADIUS) -> dict:
    W, H = map_data["width"], map_data["height"]
    pts = prop_centers(map_data)
    n = len(pts)
    stats: dict = {"n_props": n, "area": W * H,
                   "params": {"min_props": min_props,
                              "open_radius": open_radius}}
    if n < min_props:
        stats.update({"r": None, "mean_nn": None, "cv_nn": None,
                      "open_ratio": None})
        return stats

    nn = []
    for i, (x, y) in enumerate(pts):
        best = None
        for j, (u, v) in enumerate(pts):
            if i == j:
                continue
            d = math.hypot(x - u, y - v)
            if best is None or d < best:
                best = d
        nn.append(best)
    mean_nn = sum(nn) / n
    var = sum((d - mean_nn) ** 2 for d in nn) / n
    cv = (math.sqrt(var) / mean_nn) if mean_nn > 0 else 0.0
    expected = 0.5 * math.sqrt((W * H) / n)
    r = mean_nn / expected if expected > 0 else 0.0

    # Multi-source BFS (Manhattan) from prop cells; open = farther than radius.
    INF = -1
    dist = [INF] * (W * H)
    q: deque = deque()
    for (fx, fy) in pts:
        cx = min(W - 1, max(0, int(fx)))
        cy = min(H - 1, max(0, int(fy)))
        idx = cy * W + cx
        if dist[idx] == INF:
            dist[idx] = 0
            q.append((cx, cy))
    while q:
        x, y = q.popleft()
        d = dist[y * W + x]
        if d >= open_radius:
            continue
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < W and 0 <= ny < H and dist[ny * W + nx] == INF:
                dist[ny * W + nx] = d + 1
                q.append((nx, ny))
    open_cells = sum(1 for d in dist if d == INF)
    stats.update({"r": round(r, 4), "mean_nn": round(mean_nn, 4),
                  "cv_nn": round(cv, 4),
                  "open_ratio": round(open_cells / (W * H), 4)})
    return stats


# -------------------------------------------------------------- image side

def image_stats(image_path: str | Path, block_px: int = BLOCK_PX,
                flat_eps: int = FLAT_EPS, pixel_scale: int = 1) -> dict:
    w, h, rgba = _png.decode(image_path)
    block = block_px * max(1, pixel_scale)
    flat = 0
    blocks = 0
    mads: list[float] = []
    exact: dict[int, int] = {}
    opaque = 0
    for by in range(0, h - h % block, block):
        for bx in range(0, w - w % block, block):
            rmin = gmin = bmin = 255
            rmax = gmax = bmax = 0
            lumas = []
            for y in range(by, by + block):
                i = (y * w + bx) * 4
                for _ in range(block):
                    a = rgba[i + 3]
                    if a >= 8:
                        r, g, b = rgba[i], rgba[i + 1], rgba[i + 2]
                        if r < rmin: rmin = r
                        if r > rmax: rmax = r
                        if g < gmin: gmin = g
                        if g > gmax: gmax = g
                        if b < bmin: bmin = b
                        if b > bmax: bmax = b
                        lumas.append((r * 299 + g * 587 + b * 114) // 1000)
                        pk = (r << 16) | (g << 8) | b
                        exact[pk] = exact.get(pk, 0) + 1
                        opaque += 1
                    i += 4
            if not lumas:
                continue  # fully transparent block: not part of the scene
            blocks += 1
            if (rmax - rmin) <= flat_eps and (gmax - gmin) <= flat_eps \
                    and (bmax - bmin) <= flat_eps:
                flat += 1
            mean_l = sum(lumas) / len(lumas)
            mads.append(sum(abs(v - mean_l) for v in lumas) / len(lumas))

    stats = {"blocks": blocks, "opaque_px": opaque,
             "params": {"block_px": block_px, "flat_eps": flat_eps,
                        "pixel_scale": pixel_scale}}
    if blocks == 0:
        stats.update({"flat_mass": None, "dominant_share": None,
                      "busy_cv": None})
        return stats
    mean_mad = sum(mads) / len(mads)
    if mean_mad > 0:
        var = sum((v - mean_mad) ** 2 for v in mads) / len(mads)
        busy_cv = math.sqrt(var) / mean_mad
    else:
        busy_cv = 0.0
    dom = max(exact.values()) if exact else 0
    stats.update({"flat_mass": round(flat / blocks, 4),
                  "dominant_share": round(dom / opaque, 4) if opaque else None,
                  "busy_cv": round(busy_cv, 4)})
    return stats


# ------------------------------------------------------------------- check

def check(map_data: dict | None = None, image_path: str | Path | None = None,
          bounds=None, config: dict | None = None) -> list[dict]:
    cfg = config or {}
    findings: list[dict] = []
    if isinstance(bounds, (str, Path)):
        bounds = C.load_json(bounds)
    if not bounds:
        sev = C.SEV_ERROR if cfg.get("strict_calibration") else C.SEV_WARN
        findings.append(C.finding(
            GATE, "CALIBRATION_MISSING", sev,
            "no clustering bounds provided (run calibrate.py clustering; "
            "pass --bounds)"))
        bounds = {}

    if map_data is not None:
        mb = bounds.get("map", {})
        params = mb.get("params", {})
        ms = map_stats(map_data,
                       min_props=cfg.get("min_props",
                                         params.get("min_props", MIN_PROPS)),
                       open_radius=cfg.get("open_radius",
                                           params.get("open_radius",
                                                      OPEN_RADIUS)))
        if ms["r"] is None:
            findings.append(C.finding(
                GATE, "CLUSTER_FEW_PROPS", C.SEV_INFO,
                f"only {ms['n_props']} props — below min_props, "
                "map stats skipped", data=ms))
        else:
            if mb.get("r_max") is not None and ms["r"] > mb["r_max"]:
                findings.append(C.finding(
                    GATE, "CLUSTER_SCATTER", C.SEV_ERROR,
                    f"prop spacing is random-scatter shaped: Clark-Evans "
                    f"R={ms['r']} > fitted max {mb['r_max']} "
                    "(positives cluster; 5.png scatters)",
                    data={**ms, "r_max": mb["r_max"]}))
            if mb.get("open_min") is not None \
                    and ms["open_ratio"] < mb["open_min"]:
                findings.append(C.finding(
                    GATE, "CLUSTER_NO_CLEARING", C.SEV_ERROR,
                    f"no open space: {ms['open_ratio']:.1%} of cells are "
                    f"clear of props (fitted min "
                    f"{mb['open_min']:.1%}) — blanket scatter",
                    data={**ms, "open_min": mb["open_min"]}))
            if mb.get("cv_min") is not None and ms["cv_nn"] < mb["cv_min"]:
                findings.append(C.finding(
                    GATE, "CLUSTER_UNIFORM_SPACING", C.SEV_WARN,
                    f"NN-distance CV {ms['cv_nn']} below fitted min "
                    f"{mb['cv_min']} — suspiciously even spacing",
                    data={**ms, "cv_min": mb["cv_min"]}))
            findings.append(C.finding(
                GATE, "CLUSTER_MAP_STATS", C.SEV_INFO,
                f"map: n={ms['n_props']} R={ms['r']} "
                f"open={ms['open_ratio']:.1%} cv={ms['cv_nn']}", data=ms))

    if image_path is not None:
        ib = bounds.get("image", {})
        params = ib.get("params", {})
        istats = image_stats(
            image_path,
            block_px=cfg.get("block_px", params.get("block_px", BLOCK_PX)),
            flat_eps=cfg.get("flat_eps", params.get("flat_eps", FLAT_EPS)),
            pixel_scale=cfg.get("pixel_scale", 1))
        if istats["flat_mass"] is None:
            findings.append(C.finding(
                GATE, "CLUSTER_EMPTY_IMAGE", C.SEV_WARN,
                "render has no opaque blocks", data=istats))
        else:
            tripped = []
            if ib.get("flat_max") is not None \
                    and istats["flat_mass"] > ib["flat_max"]:
                tripped.append(f"flat_mass {istats['flat_mass']} > "
                               f"{ib['flat_max']}")
            if ib.get("dominant_max") is not None \
                    and istats["dominant_share"] is not None \
                    and istats["dominant_share"] > ib["dominant_max"]:
                tripped.append(f"dominant_share {istats['dominant_share']} > "
                               f"{ib['dominant_max']}")
            if tripped:
                findings.append(C.finding(
                    GATE, "CLUSTER_FLAT_VOID", C.SEV_ERROR,
                    "untextured-void render (props scattered on flat "
                    "field): " + "; ".join(tripped),
                    data={**istats, "bounds": {k: ib.get(k) for k in
                                               ("flat_max", "dominant_max")}}))
            if ib.get("busy_cv_min") is not None \
                    and istats["busy_cv"] is not None \
                    and istats["busy_cv"] < ib["busy_cv_min"]:
                findings.append(C.finding(
                    GATE, "CLUSTER_FLAT_TEXTURE", C.SEV_WARN,
                    f"busy CV {istats['busy_cv']} below fitted min "
                    f"{ib['busy_cv_min']} — uniformly bland detail",
                    data={**istats, "busy_cv_min": ib["busy_cv_min"]}))
            findings.append(C.finding(
                GATE, "CLUSTER_IMAGE_STATS", C.SEV_INFO,
                f"image: flat={istats['flat_mass']} "
                f"dominant={istats['dominant_share']} "
                f"busy_cv={istats['busy_cv']}", data=istats))
    return C.cap_findings(findings, GATE)
