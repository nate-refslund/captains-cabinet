"""Deterministic synthetic fixtures: clustered/scatter maps + scene images.

License-safe by construction (no LimeZu pixels): used by calibrate.py to fit
the map-side clustering bounds from canonical GOOD layouts, and by the tests
to prove the negatives fail / positives pass without touching the gitignored
corpus. Everything is seeded — same seed, same bytes.
"""

from __future__ import annotations

import random

MAP_W, MAP_H = 48, 32


def _base_map(w: int = MAP_W, h: int = MAP_H) -> dict:
    return {
        "schema": "cabinet.world.map/v1",
        "tile_size": 16,
        "width": w, "height": h,
        "anchor": [w // 2, h // 2],
        "sheets": {"props": {"grid": 16}},
        "layers": [],
    }


def make_clustered_map(seed: int, w: int = MAP_W, h: int = MAP_H,
                       n_clusters: int | None = None,
                       props_per_cluster: int = 8) -> dict:
    """Designed layout: prop clumps + a guaranteed clear plaza (positive class)."""
    rng = random.Random(seed)
    m = _base_map(w, h)
    k = n_clusters or rng.randint(3, 5)
    # Plaza: prop-free rectangle around the anchor.
    px0, py0 = w // 2 - 6, h // 2 - 4
    plaza = (px0, py0, 12, 8)
    centers = []
    while len(centers) < k:
        cx = rng.randint(4, w - 5)
        cy = rng.randint(4, h - 5)
        if plaza[0] - 2 <= cx < plaza[0] + plaza[2] + 2 and \
                plaza[1] - 2 <= cy < plaza[1] + plaza[3] + 2:
            continue
        centers.append((cx, cy))
    cells: set = set()
    for (cx, cy) in centers:
        placed = 0
        attempts = 0
        while placed < props_per_cluster and attempts < 200:
            attempts += 1
            x = int(round(rng.gauss(cx, 1.8)))
            y = int(round(rng.gauss(cy, 1.8)))
            if not (0 <= x < w and 0 <= y < h):
                continue
            if plaza[0] <= x < plaza[0] + plaza[2] and \
                    plaza[1] <= y < plaza[1] + plaza[3]:
                continue
            if (x, y) in cells:
                continue
            cells.add((x, y))
            placed += 1
    m["layers"].append({
        "name": "props", "kind": "prop",
        "tiles": [{"sheet": "props", "region": [0, 0, 16, 16],
                   "x": x, "y": y} for (x, y) in sorted(cells)]})
    return m


def make_scatter_map(seed: int, n: int = 60, w: int = MAP_W,
                     h: int = MAP_H) -> dict:
    """Uniform random prop scatter — the 5.png-class negative as MAP data."""
    rng = random.Random(seed)
    m = _base_map(w, h)
    cells: set = set()
    while len(cells) < min(n, w * h - 1):
        cells.add((rng.randrange(w), rng.randrange(h)))
    m["layers"].append({
        "name": "props", "kind": "prop",
        "tiles": [{"sheet": "props", "region": [0, 0, 16, 16],
                   "x": x, "y": y} for (x, y) in sorted(cells)]})
    return m


# ------------------------------------------------------------- scene images

def make_textured_scene(seed: int, w: int = 384, h: int = 320) -> bytes:
    """Composed pixel-art-like scene (positive class): textured ground of
    3 green shades + a stone-checker plaza + clustered dark prop blobs."""
    rng = random.Random(seed)
    greens = [(96, 160, 96), (84, 148, 84), (108, 172, 104)]
    stones = [(148, 148, 152), (128, 128, 134)]
    props = [(70, 50, 30), (90, 60, 90), (40, 70, 110)]
    buf = bytearray(w * h * 4)

    def put(x, y, c):
        i = (y * w + x) * 4
        buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = c[0], c[1], c[2], 255

    for y in range(h):
        for x in range(w):
            put(x, y, greens[(x * 7 + y * 13 + ((x >> 2) * (y >> 2))) % 3])
    # plaza (checker)
    px0, py0, pw_, ph_ = w // 3, h // 3, w // 3, h // 4
    for y in range(py0, py0 + ph_):
        for x in range(px0, px0 + pw_):
            put(x, y, stones[((x >> 3) + (y >> 3)) % 2])
    # clustered prop blobs
    for _ in range(5):
        cx, cy = rng.randint(24, w - 25), rng.randint(24, h - 25)
        if px0 - 16 < cx < px0 + pw_ + 16 and py0 - 16 < cy < py0 + ph_ + 16:
            continue
        for _ in range(7):
            bx = cx + rng.randint(-14, 14)
            by = cy + rng.randint(-14, 14)
            c = props[rng.randrange(3)]
            for y in range(max(0, by), min(h, by + 10)):
                for x in range(max(0, bx), min(w, bx + 8)):
                    if (x + y) % 5:  # keep texture inside props too
                        put(x, y, c)
    return bytes(buf)


def make_css_rect_scene(seed: int = 7, w: int = 384, h: int = 320) -> bytes:
    """Flat CSS/dashboard rectangles on a dark slate field (palette-attack
    class). Deliberately built from web colours no pixel-art corpus contains,
    so palette_coherence must fail it whatever the corpus is fitted to. Pure
    stdlib, no corpus input — this arm stays runnable when the corpus does not
    exist, which is why the bite proof never depends on assembled pixels."""
    rng = random.Random(seed)
    bg = (17, 24, 39)
    pal = [(59, 130, 246), (239, 68, 68), (16, 185, 129), (245, 158, 11),
           (139, 92, 246), (236, 72, 153), (255, 255, 255)]
    buf = bytearray(w * h * 4)
    for i in range(0, len(buf), 4):
        buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = bg[0], bg[1], bg[2], 255
    for k in range(24):
        rw, rh = rng.randint(30, 90), rng.randint(18, 60)
        x0 = rng.randint(0, max(0, w - rw - 1))
        y0 = rng.randint(0, max(0, h - rh - 1))
        c = pal[k % len(pal)]
        for y in range(y0, y0 + rh):
            i = (y * w + x0) * 4
            for _ in range(rw):
                buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = c[0], c[1], c[2], 255
                i += 4
    return bytes(buf)


def make_flat_scatter_scene(seed: int, n: int = 30, w: int = 384,
                            h: int = 320,
                            bg=(139, 195, 116)) -> bytes:
    """Flat-field prop scatter (negative class): the exact rejected look —
    solid untextured green + unrelated solid rectangles dropped at random."""
    rng = random.Random(seed)
    colors = [(70, 50, 30), (90, 60, 90), (40, 70, 110), (160, 40, 40)]
    buf = bytearray(w * h * 4)
    for i in range(0, len(buf), 4):
        buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = bg[0], bg[1], bg[2], 255
    for _ in range(n):
        rw, rh = rng.randint(16, 28), rng.randint(20, 36)
        x0 = rng.randint(0, max(0, w - rw - 1))
        y0 = rng.randint(0, max(0, h - rh - 1))
        c = colors[rng.randrange(len(colors))]
        for y in range(y0, y0 + rh):
            i = (y * w + x0) * 4
            for _ in range(rw):
                buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = c[0], c[1], c[2], 255
                i += 4
    return bytes(buf)
