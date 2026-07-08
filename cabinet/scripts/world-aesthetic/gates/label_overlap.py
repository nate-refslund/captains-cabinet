"""Gate 4 — label overlap (IMAGE): renderer-emitted label boxes, per zoom.

LABELS SCHEMA — cabinet.world.labels/v1 (renderer will emit alongside a render):
{
  "schema": "cabinet.world.labels/v1",
  "render": {"width": 1280, "height": 960},        # px of the render
  "labels": [
    {"id": "bld-hq", "text": "HQ", "zoom": 1,      # zoom level of visibility
     "rect": [x, y, w, h],                          # px box incl. padding
     "chrome": false}                               # true = sanctioned UI hud
  ]
}
A bare list of label objects is also accepted.

Checks (the label-spam class):
  * LABEL_OVERLAP  (error) — two non-chrome boxes at the same zoom intersect;
  * LABEL_SPAM     (error) — non-chrome label area / render area > spam_ratio
                    at one zoom (default 0.15);
  * LABEL_OUT_OF_BOUNDS (warn) — box exceeds the render;
  * LABEL_RENDER_MISMATCH (warn) — labels' declared dims != render PNG dims.
"""

from __future__ import annotations

from pathlib import Path

from . import _common as C
from . import _png

GATE = "label_overlap"
SPAM_RATIO = 0.15


def _norm(labels) -> tuple[dict | None, list[dict]]:
    if isinstance(labels, (str, Path)):
        labels = C.load_json(labels)
    if isinstance(labels, list):
        return None, labels
    if isinstance(labels, dict):
        return labels.get("render"), list(labels.get("labels", []))
    raise ValueError("labels must be a list or a labels/v1 object")


def _rect(entry) -> tuple[int, int, int, int] | None:
    r = entry.get("rect")
    if (isinstance(r, (list, tuple)) and len(r) == 4
            and all(isinstance(v, (int, float)) for v in r) and r[2] > 0 and r[3] > 0):
        return tuple(r)
    return None


def check(labels, image_path: str | Path | None = None,
          config: dict | None = None) -> list[dict]:
    cfg = config or {}
    spam_ratio = cfg.get("spam_ratio", SPAM_RATIO)
    findings: list[dict] = []
    render_meta, entries = _norm(labels)

    img_dims = None
    if image_path is not None:
        img_dims = _png.read_size(image_path)
    meta_dims = None
    if isinstance(render_meta, dict):
        w, h = render_meta.get("width"), render_meta.get("height")
        if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
            meta_dims = (w, h)
    if img_dims and meta_dims and img_dims != meta_dims:
        findings.append(C.finding(
            GATE, "LABEL_RENDER_MISMATCH", C.SEV_WARN,
            f"labels declare render {meta_dims[0]}x{meta_dims[1]} but PNG is "
            f"{img_dims[0]}x{img_dims[1]} — using PNG dims",
            data={"labels_dims": list(meta_dims), "png_dims": list(img_dims)}))
    dims = img_dims or meta_dims
    if dims is None:
        findings.append(C.finding(
            GATE, "LABEL_NO_DIMS", C.SEV_WARN,
            "no render dims available (no --render and labels carry none) — "
            "spam/bounds checks skipped"))

    by_zoom: dict[int, list[tuple[int, dict, tuple]]] = {}
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        r = _rect(e)
        if r is None:
            findings.append(C.finding(
                GATE, "LABEL_BAD_RECT", C.SEV_WARN,
                f"label #{i} ({e.get('id', e.get('text', '?'))}) has no valid "
                "rect [x,y,w,h]", data={"index": i}))
            continue
        if e.get("chrome"):
            continue  # sanctioned UI chrome is exempt
        zoom = e.get("zoom", 0)
        by_zoom.setdefault(int(zoom), []).append((i, e, r))
        if dims is not None:
            x, y, w, h = r
            if x < 0 or y < 0 or x + w > dims[0] or y + h > dims[1]:
                findings.append(C.finding(
                    GATE, "LABEL_OUT_OF_BOUNDS", C.SEV_WARN,
                    f"label '{e.get('id', e.get('text', i))}' rect {list(r)} "
                    f"exceeds render {dims[0]}x{dims[1]}",
                    where={"rect": list(r)}, data={"zoom": zoom}))

    for zoom, items in sorted(by_zoom.items()):
        for ai in range(len(items)):
            ia, ea, (ax, ay, aw, ah) = items[ai]
            for bi in range(ai + 1, len(items)):
                ib, eb, (bx, by, bw, bh) = items[bi]
                ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
                iy = max(0, min(ay + ah, by + bh) - max(ay, by))
                inter = ix * iy
                if inter > 0:
                    union = aw * ah + bw * bh - inter
                    findings.append(C.finding(
                        GATE, "LABEL_OVERLAP", C.SEV_ERROR,
                        f"labels '{ea.get('id', ea.get('text', ia))}' and "
                        f"'{eb.get('id', eb.get('text', ib))}' overlap at "
                        f"zoom {zoom} (IoU {inter / union:.2f})",
                        where={"rects": [[ax, ay, aw, ah], [bx, by, bw, bh]]},
                        data={"zoom": zoom, "intersection_px": inter,
                              "iou": round(inter / union, 4)}))
        if dims is not None:
            area = sum(w * h for (_, _, (_, _, w, h)) in items)
            ratio = area / float(dims[0] * dims[1])
            if ratio > spam_ratio:
                findings.append(C.finding(
                    GATE, "LABEL_SPAM", C.SEV_ERROR,
                    f"labels cover {ratio:.1%} of the render at zoom {zoom} "
                    f"(limit {spam_ratio:.0%}) — the label-spam class",
                    data={"zoom": zoom, "ratio": round(ratio, 4),
                          "limit": spam_ratio, "labels": len(items)}))
    return C.cap_findings(findings, GATE)
