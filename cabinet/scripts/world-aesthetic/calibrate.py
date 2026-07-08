#!/usr/bin/env python3.12
"""Fit the aesthetic-gate calibrations from the (gitignored) corpus.

Subcommands:
    palette     -> calibration/palette.json           (from corpus positives)
    clustering  -> calibration/clustering_bounds.json (image bounds from
                   corpus positives; map bounds from canonical synthetic
                   clustered layouts — geometry stats are asset-independent)
    prove       -> assert separation: every corpus NEGATIVE trips >=1
                   clustering-image bound, every POSITIVE trips none; and the
                   synthetic scatter maps trip the map bounds while a held-out
                   clustered map passes. Exit 1 on any violation.
    all         -> palette + clustering + prove

Only DERIVED NUMBERS + sha256 provenance are written to calibration/ (tracked);
LimeZu-licensed corpus pixels stay untracked (see corpus/manifest.json /
build_corpus.py). Corpus file access is path-contained to the corpus dir.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
CALIB = HERE / "calibration"

# Margins over the worst positive: generous enough to admit unseen good
# scenes, tight enough that every corpus negative still trips (prove checks).
FLAT_MARGIN, FLAT_FLOOR = 1.35, 0.02
DOM_MARGIN, DOM_FLOOR = 1.35, 0.02
R_MARGIN = 1.15
OPEN_MARGIN = 0.85
CV_MARGIN = 0.80
BUSY_MARGIN = 0.80

SYNTH_FIT_SEEDS = (11, 12, 13, 14, 15, 16)
SYNTH_HOLDOUT_SEED = 99
SCATTER_SEEDS = ((42, 18), (1337, 90), (7, 60))  # (seed, n) — 42/1337 mirror corpus


def _load_gates():
    spec = importlib.util.spec_from_file_location(
        "world_aesthetic_loader", HERE / "_loader.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_gates()


def _corpus_images(corpus: Path, cls: str) -> list[Path]:
    d = (corpus / cls).resolve()
    if not d.is_relative_to(corpus.resolve()):  # path-containment guard
        raise ValueError(f"class dir escapes corpus: {d}")
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.png")):
        rp = p.resolve()
        if not rp.is_relative_to(corpus.resolve()):
            raise ValueError(f"corpus file escapes corpus dir: {rp}")
        out.append(rp)
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fit_palette(gates, positives: list[Path], bits: int,
                min_share: float) -> dict:
    pal = gates.palette_coherence.extract_palette(
        positives, bits=bits, min_bin_share=min_share)
    pal["generated"] = _now()
    pal["generator"] = "calibrate.py/v1"
    return pal


def fit_image_bounds(stats_list: list[dict]) -> dict:
    """Bounds from positive image stats: margin over the worst positive."""
    flats = [s["flat_mass"] for s in stats_list if s["flat_mass"] is not None]
    doms = [s["dominant_share"] for s in stats_list
            if s["dominant_share"] is not None]
    busys = [s["busy_cv"] for s in stats_list if s["busy_cv"] is not None]
    if not flats or not doms:
        raise ValueError("no usable positive image stats")
    return {
        "flat_max": round(max(flats) * FLAT_MARGIN + FLAT_FLOOR, 4),
        "dominant_max": round(max(doms) * DOM_MARGIN + DOM_FLOOR, 4),
        "busy_cv_min": round(min(busys) * BUSY_MARGIN, 4) if busys else None,
    }


def fit_map_bounds(stats_list: list[dict]) -> dict:
    rs = [s["r"] for s in stats_list if s["r"] is not None]
    opens = [s["open_ratio"] for s in stats_list if s["open_ratio"] is not None]
    cvs = [s["cv_nn"] for s in stats_list if s["cv_nn"] is not None]
    if not rs:
        raise ValueError("no usable positive map stats")
    return {
        "r_max": round(max(rs) * R_MARGIN, 4),
        "open_min": round(min(opens) * OPEN_MARGIN, 4),
        "cv_min": round(min(cvs) * CV_MARGIN, 4) if cvs else None,
    }


def fit_clustering(gates, corpus: Path) -> dict:
    positives = _corpus_images(corpus, "positive")
    img_fitted = []
    img_stats = []
    for p in positives:
        s = gates.clustering.image_stats(p)
        img_stats.append(s)
        img_fitted.append({"file": p.name, "sha256": gates._common.sha256_path(p),
                           "stats": {k: s[k] for k in
                                     ("flat_mass", "dominant_share", "busy_cv")}})
    image_block = None
    if img_stats:
        image_block = fit_image_bounds(img_stats)
        image_block["params"] = img_stats[0]["params"]
        image_block["fitted_from"] = img_fitted

    map_stats_list = []
    map_fitted = []
    for seed in SYNTH_FIT_SEEDS:
        m = gates._synth.make_clustered_map(seed)
        s = gates.clustering.map_stats(m)
        map_stats_list.append(s)
        map_fitted.append({"synthetic": f"make_clustered_map(seed={seed})",
                           "stats": {k: s[k] for k in
                                     ("n_props", "r", "open_ratio", "cv_nn")}})
    map_block = fit_map_bounds(map_stats_list)
    map_block["params"] = map_stats_list[0]["params"]
    map_block["fitted_from"] = map_fitted

    bounds = {"schema": "cabinet.world.clustering-bounds/v1",
              "map": map_block,
              "generated": _now(), "generator": "calibrate.py/v1"}
    if image_block:
        bounds["image"] = image_block
    return bounds


def prove(gates, corpus: Path, bounds: dict) -> list[str]:
    """Mechanical separation proof. Returns list of violations (empty = OK)."""
    violations: list[str] = []
    ib = bounds.get("image", {})

    def trips_image(s: dict) -> list[str]:
        t = []
        if ib.get("flat_max") is not None and s["flat_mass"] is not None \
                and s["flat_mass"] > ib["flat_max"]:
            t.append(f"flat {s['flat_mass']}>{ib['flat_max']}")
        if ib.get("dominant_max") is not None \
                and s["dominant_share"] is not None \
                and s["dominant_share"] > ib["dominant_max"]:
            t.append(f"dom {s['dominant_share']}>{ib['dominant_max']}")
        return t

    if ib:
        print("image side (corpus):")
        for cls, want_fail in (("positive", False), ("negative", True)):
            for p in _corpus_images(corpus, cls):
                s = gates.clustering.image_stats(p)
                t = trips_image(s)
                status = "FAIL" if t else "pass"
                print(f"  {cls[:3]} {p.name:32s} flat={s['flat_mass']} "
                      f"dom={s['dominant_share']} busy={s['busy_cv']} -> "
                      f"{status} {'; '.join(t)}")
                if want_fail and not t:
                    violations.append(
                        f"negative {p.name} trips NO image bound")
                if not want_fail and t:
                    violations.append(
                        f"positive {p.name} trips image bound(s): {t}")

    mb = bounds.get("map", {})
    print("map side (synthetic):")
    for seed, n in SCATTER_SEEDS:
        s = gates.clustering.map_stats(gates._synth.make_scatter_map(seed, n=n))
        trip = (s["r"] is not None and s["r"] > mb["r_max"]) or \
               (s["open_ratio"] is not None and s["open_ratio"] < mb["open_min"])
        print(f"  neg scatter(seed={seed},n={n}): R={s['r']} "
              f"open={s['open_ratio']} -> {'FAIL' if trip else 'pass'}")
        if not trip:
            violations.append(f"scatter map seed={seed} trips no map bound")
    hold = gates.clustering.map_stats(
        gates._synth.make_clustered_map(SYNTH_HOLDOUT_SEED))
    trip = hold["r"] > mb["r_max"] or hold["open_ratio"] < mb["open_min"]
    print(f"  pos holdout(seed={SYNTH_HOLDOUT_SEED}): R={hold['r']} "
          f"open={hold['open_ratio']} -> {'FAIL' if trip else 'pass'}")
    if trip:
        violations.append("held-out clustered map trips a map bound")
    return violations


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="calibrate.py", description=__doc__)
    ap.add_argument("cmd", choices=["palette", "clustering", "prove", "all"])
    ap.add_argument("--corpus", default=str(CORPUS))
    ap.add_argument("--out-dir", default=str(CALIB))
    ap.add_argument("--quant-bits", type=int, default=5)
    ap.add_argument("--min-bin-share", type=float, default=0.0005)
    args = ap.parse_args(argv)

    gates = _load_gates()
    corpus = Path(args.corpus).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rc = 0

    if args.cmd in ("palette", "all"):
        positives = _corpus_images(corpus, "positive")
        if not positives:
            print(f"no positives under {corpus}/positive — cannot fit palette",
                  file=sys.stderr)
            return 1
        pal = fit_palette(gates, positives, args.quant_bits,
                          args.min_bin_share)
        out = out_dir / "palette.json"
        out.write_text(json.dumps(pal, indent=2) + "\n")
        print(f"wrote {out} ({len(pal['bins'])} bins from "
              f"{len(positives)} positives, {pal['source_pixels']} px)")

    bounds = None
    if args.cmd in ("clustering", "all"):
        bounds = fit_clustering(gates, corpus)
        out = out_dir / "clustering_bounds.json"
        out.write_text(json.dumps(bounds, indent=2) + "\n")
        img = bounds.get("image", {})
        print(f"wrote {out} (map r_max={bounds['map']['r_max']} "
              f"open_min={bounds['map']['open_min']}; image "
              f"flat_max={img.get('flat_max')} "
              f"dominant_max={img.get('dominant_max')})")

    if args.cmd in ("prove", "all"):
        if bounds is None:
            bpath = out_dir / "clustering_bounds.json"
            if not bpath.is_file():
                print(f"no bounds at {bpath} — run clustering first",
                      file=sys.stderr)
                return 1
            bounds = json.loads(bpath.read_text())
        violations = prove(gates, corpus, bounds)
        if violations:
            print("PROVE FAILED:")
            for v in violations:
                print(f"  - {v}")
            rc = 1
        else:
            print("PROVE OK: negatives fail, positives pass")
    return rc


if __name__ == "__main__":
    sys.exit(main())
