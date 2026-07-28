#!/usr/bin/env python3
"""The Cabinet World master palette — one swatch image fed to EVERY pixflux call as color_image.
Deterministic cohesion lever (beats prompt-suffix luck). Ramps from the Ghibli brief."""
from PIL import Image
import os

RAMPS = {
    "foliage":   ["#3A5230", "#4E6B3C", "#6A8252", "#7D9B5F", "#8CBF88", "#B9D19A", "#C7CD90"],
    "terracotta":["#6E3A2A", "#8A4B36", "#B5674A", "#D08A63", "#E3BBA1", "#CBA46A", "#A87C4A"],
    "cream":     ["#C9B79A", "#E1D3B4", "#E9EEDA", "#F1DAB6", "#FFF5F1", "#FBEBD2", "#EFE0C4"],
    "timber":    ["#402A1E", "#5C3D28", "#7A5335", "#9A6E45", "#B98D5C", "#D2AD7C", "#6B4A30"],
    "water":     ["#2E5350", "#3E6E6B", "#5C9A93", "#79B6AC", "#A9D3C8", "#A3C5E0", "#CFE6DE"],
    "stone":     ["#4B4A52", "#6B6A72", "#8B8A90", "#A9A8AC", "#C6C4C2", "#DEDBD4", "#7C7A80"],
    "accent":    ["#E3C16F", "#E8A03C", "#C6553F", "#8E4B6B", "#E39BB0", "#5E7FA8", "#F2E3A0"],
}
ORDER = ["foliage", "terracotta", "cream", "timber", "water", "stone", "accent"]

def hx(h): return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))

def build(path, cell=16):
    cols = max(len(v) for v in RAMPS.values()); rows = len(ORDER)
    im = Image.new("RGB", (cols*cell, rows*cell))
    px = im.load()
    for r, k in enumerate(ORDER):
        ramp = RAMPS[k]
        for c in range(cols):
            col = hx(ramp[min(c, len(ramp)-1)])
            for y in range(r*cell, (r+1)*cell):
                for x in range(c*cell, (c+1)*cell): px[x, y] = col
    im.save(path)
    return im

def flat_colors():
    out = []
    for k in ORDER: out += [hx(c) for c in RAMPS[k]]
    return out

if __name__ == "__main__":
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "master_palette.png")
    build(p); print("wrote", p, len(flat_colors()), "colors")
