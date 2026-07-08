"""Gate 5 — palette coherence (IMAGE): foreign-color mass vs the corpus palette.

Mechanics: calibrate.py extracts a quantized palette (5 bits/channel bins) from
the POSITIVE corpus — derived numbers only, so the palette JSON is committable
while LimeZu pixels stay untracked. A bin joins the palette when its share
reaches min_bin_share in AT LEAST ONE positive image (per-image floor, not
merged-mass: a global floor lets big corpus images starve a small positive's
legitimate scene colors out of the palette, which broke the every-positive-
passes self-consistency contract on pos-village-house). At gate time every
opaque render pixel is quantized into the same bin space; a pixel is NATIVE if
its bin (or any bin within neighbor_radius in bin space) is in the palette,
else FOREIGN. Foreign mass above max_foreign fails — the wrong-hue / AI-art /
CSS-rectangle class. Sanctioned UI chrome rects are excluded before counting.

PALETTE SCHEMA — cabinet.world.palette/v1:
{"schema": ..., "quant_bits": 5, "neighbor_radius": 1, "min_bin_share": ...,
 "bins": [packed ints (r<<2q | g<<q | b)], "colors_rgb_sample": [[r,g,b]...],
 "fitted_from": [{"file", "sha256"}], "generated": iso}
"""

from __future__ import annotations

from pathlib import Path

from . import _common as C
from . import _png

GATE = "palette_coherence"
MAX_FOREIGN = 0.05
ALPHA_MIN = 8


def quantize_key(r: int, g: int, b: int, bits: int) -> int:
    shift = 8 - bits
    return ((r >> shift) << (2 * bits)) | ((g >> shift) << bits) | (b >> shift)


def histogram(rgba: bytes, width: int, height: int, bits: int,
              ui_rects: list | None = None, alpha_min: int = ALPHA_MIN) -> dict:
    """Quantized-bin histogram of opaque pixels outside ui_rects.

    Returns {"bins": {key: count}, "total": n, "exact": {rgb_packed: count}}.
    exact colors feed the clustering dominant-share metric + debug output.
    """
    rects = [tuple(r) for r in (ui_rects or [])]
    bins: dict[int, int] = {}
    exact: dict[int, int] = {}
    total = 0
    shift = 8 - bits
    row_px = width * 4
    for y in range(height):
        # merged exclusion intervals for this row
        intervals = []
        for (rx, ry, rw, rh) in rects:
            if ry <= y < ry + rh:
                intervals.append((max(0, rx), min(width, rx + rw)))
        intervals.sort()
        segs = []
        cur = 0
        for (a, b) in intervals:
            if a > cur:
                segs.append((cur, a))
            cur = max(cur, b)
        if cur < width:
            segs.append((cur, width))
        base = y * row_px
        for (x0, x1) in segs:
            i = base + x0 * 4
            for _ in range(x1 - x0):
                a = rgba[i + 3]
                if a >= alpha_min:
                    r, g, b = rgba[i], rgba[i + 1], rgba[i + 2]
                    key = ((r >> shift) << (2 * bits)) | ((g >> shift) << bits) | (b >> shift)
                    bins[key] = bins.get(key, 0) + 1
                    pk = (r << 16) | (g << 8) | b
                    exact[pk] = exact.get(pk, 0) + 1
                    total += 1
                i += 4
    return {"bins": bins, "total": total, "exact": exact}


def extract_palette(image_paths: list, bits: int = 5,
                    min_bin_share: float = 0.0005,
                    neighbor_radius: int = 1) -> dict:
    """Fit a palette from positive images (calibrate.py calls this).

    Floor semantics: a bin is kept when its share reaches min_bin_share in AT
    LEAST ONE input image (max per-image share). This keeps every positive
    self-consistent regardless of image-size imbalance while still dropping
    bins that are trace noise in every image.
    """
    merged: dict[int, int] = {}
    max_share: dict[int, float] = {}
    total = 0
    fitted = []
    for p in image_paths:
        w, h, rgba = _png.decode(p)
        hist = histogram(rgba, w, h, bits)
        img_total = hist["total"]
        for k, v in hist["bins"].items():
            merged[k] = merged.get(k, 0) + v
            if img_total:
                share = v / img_total
                if share > max_share.get(k, 0.0):
                    max_share[k] = share
        total += img_total
        fitted.append({"file": Path(p).name, "sha256": C.sha256_path(p)})
    if total == 0:
        raise ValueError("no opaque pixels in palette inputs")
    bins = sorted(k for k, s in max_share.items() if s >= min_bin_share)
    half = 1 << (8 - bits - 1)
    top = sorted(bins, key=lambda k: -merged[k])[:64]
    mask = (1 << bits) - 1
    sample = [[((k >> (2 * bits)) & mask) << (8 - bits) | half,
               ((k >> bits) & mask) << (8 - bits) | half,
               (k & mask) << (8 - bits) | half] for k in top]
    return {"schema": "cabinet.world.palette/v1", "quant_bits": bits,
            "neighbor_radius": neighbor_radius, "min_bin_share": min_bin_share,
            "bins": bins, "colors_rgb_sample": sample, "fitted_from": fitted,
            "source_pixels": total}


def check(image_path: str | Path, palette=None,
          config: dict | None = None) -> list[dict]:
    cfg = config or {}
    findings: list[dict] = []
    if isinstance(palette, (str, Path)):
        palette = C.load_json(palette)
    if not palette:
        sev = C.SEV_ERROR if cfg.get("strict_calibration") else C.SEV_WARN
        findings.append(C.finding(
            GATE, "CALIBRATION_MISSING", sev,
            "no palette calibration provided (run calibrate.py palette; "
            "pass --palette)"))
        return findings

    bits = palette.get("quant_bits", 5)
    radius = cfg.get("neighbor_radius", palette.get("neighbor_radius", 1))
    max_foreign = cfg.get("max_foreign", MAX_FOREIGN)
    bins_set = set(palette["bins"])

    w, h, rgba = _png.decode(image_path)
    hist = histogram(rgba, w, h, bits, ui_rects=cfg.get("ui_rects"),
                     alpha_min=cfg.get("alpha_min", ALPHA_MIN))
    if hist["total"] == 0:
        findings.append(C.finding(
            GATE, "PALETTE_EMPTY_IMAGE", C.SEV_WARN,
            "render has no opaque pixels outside UI rects"))
        return findings

    limit = 1 << bits
    native_memo: dict[int, bool] = {}

    def is_native(key: int) -> bool:
        hit = native_memo.get(key)
        if hit is not None:
            return hit
        if key in bins_set:
            native_memo[key] = True
            return True
        if radius > 0:
            mask = limit - 1
            r0, g0, b0 = (key >> (2 * bits)) & mask, (key >> bits) & mask, key & mask
            for dr in range(-radius, radius + 1):
                r = r0 + dr
                if not 0 <= r < limit:
                    continue
                for dg in range(-radius, radius + 1):
                    g = g0 + dg
                    if not 0 <= g < limit:
                        continue
                    for db in range(-radius, radius + 1):
                        b = b0 + db
                        if 0 <= b < limit and \
                                ((r << (2 * bits)) | (g << bits) | b) in bins_set:
                            native_memo[key] = True
                            return True
        native_memo[key] = False
        return False

    foreign = 0
    foreign_bins: dict[int, int] = {}
    for key, count in hist["bins"].items():
        if not is_native(key):
            foreign += count
            foreign_bins[key] = count
    share = foreign / hist["total"]

    mask = limit - 1
    half = 1 << (8 - bits - 1)
    top = sorted(foreign_bins.items(), key=lambda kv: -kv[1])[:5]
    top_colors = [{"rgb": [((k >> (2 * bits)) & mask) << (8 - bits) | half,
                           ((k >> bits) & mask) << (8 - bits) | half,
                           (k & mask) << (8 - bits) | half],
                   "share": round(v / hist["total"], 4)} for k, v in top]

    if share > max_foreign:
        findings.append(C.finding(
            GATE, "PALETTE_FOREIGN_MASS", C.SEV_ERROR,
            f"{share:.1%} of pixels are outside the corpus palette "
            f"(limit {max_foreign:.0%}) — foreign-color mass",
            data={"foreign_share": round(share, 4), "limit": max_foreign,
                  "top_foreign": top_colors, "pixels": hist["total"]}))
    findings.append(C.finding(
        GATE, "PALETTE_STATS", C.SEV_INFO,
        f"foreign-color share {share:.2%} of {hist['total']} px",
        data={"foreign_share": round(share, 4), "pixels": hist["total"],
              "top_foreign": top_colors}))
    return C.cap_findings(findings, GATE)
