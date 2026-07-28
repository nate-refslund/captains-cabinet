#!/usr/bin/env python3.12
"""Fit the aesthetic-gate calibrations from the (gitignored) corpus.

Subcommands:
    palette     -> calibration/palette.json           (from corpus positives
                   PLUS the corpus `palette` class — see PALETTE CLASS below)
    clustering  -> calibration/clustering_bounds.json (image bounds from
                   corpus positives; map bounds from canonical synthetic
                   clustered layouts — geometry stats are asset-independent)
    prove       -> assert separation on BOTH gates. Exit 1 on any violation.
    all         -> palette + clustering + prove

PALETTE CLASS. corpus/palette/ holds palette-source art that is not a scene
(today: the owned isometric atlas). It feeds the palette fit ONLY — never the
clustering image bounds (a sprite sheet is not a composed scene) and never the
vision judge. Without it a frame drawing sprites the corpus renders happen not
to contain reads as foreign colour; measured 6.52% vs 1.23% (2026-07-28).

THE PROVE CONTRACT, and what each half actually discriminates — this was
measured, not assumed, and the split is the reason both gates exist:

  CLUSTERING is the composition gate. Every corpus negative must trip >=1
  clustering-image bound and every positive must trip none; the synthetic
  scatter maps must trip the map bounds while a held-out clustered map passes.

  PALETTE is the ART-FAMILY gate, not a composition gate. Measured against the
  pre-2026-07-28 LimeZu corpus, palette_coherence passed 3 of its own 5
  negatives (0.04%, 0.15%, 1.38% foreign) — it never separated good scenes from
  bad ones and was never able to. What it does separate is "drawn from the
  sanctioned art family" from "not", which is exactly the sensor the
  all-owned-art direction needs. So its arms are:
    P1 SELF      every positive under max_foreign (the fit admits its inputs)
    P2 OWNED-NEG every owned-art negative ALSO under max_foreign — an owned
                 frame must never be failed by the palette gate for a
                 COMPOSITION defect; that is clustering's job and P2 pins the
                 division of labour instead of leaving it to be assumed
    P3 BITE      a channel-rotated positive (r,g,b)->(g,b,r) must EXCEED
                 max_foreign. Composition-identical by construction: flat_mass
                 and dominant_share are byte-identical to the source, so no
                 other gate can see it. If P3 ever passes, palette_coherence
                 has no independent discriminative power and is a dead gate
    P4 BITE      a synthetic flat CSS-rectangle scene must EXCEED max_foreign
                 (the AI-art / dashboard-mock class named in the gate docstring)
    P5 CROSS     when an archived corpus dir is present, EVERY image in it must
                 EXCEED max_foreign — the direct "did we actually leave that art
                 family" sensor. P3/P4 need no external art, so the bite proof
                 never depends on P5 being runnable; when the archive is absent
                 P5 prints NOT RUN and is listed in the summary, never silently
                 counted as a pass.

Only DERIVED NUMBERS + sha256 provenance are written to calibration/ (tracked);
corpus pixels stay untracked (see corpus/manifest.json / build_corpus.py).
Corpus file access is path-contained to the corpus dir.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
CALIB = HERE / "calibration"
# Superseded corpora kept verbatim for reproduction AND used as the P5
# cross-family bite arm. Picked up by name, so archiving another corpus later
# extends the proof rather than needing a code edit.
#
# They live INSIDE corpus/, not beside it, and that is not cosmetic:
# cognitive-architecture-census.py derives `durable_store_units` from
# .gitignore's wildcard-free prefixes, so a sibling corpus-*/ needs its own
# ignore rule and reads as a NEW organ of memory against a zero-headroom
# budget. An archived corpus is not a new organ — it is this organ's own
# history — so it nests under the rule that already covers corpus/*.
ARCHIVE_GLOB = "archive-*"

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


def palette_inputs(corpus: Path) -> list[Path]:
    """Positives + the palette class. Sorted, deduped, deterministic."""
    seen, out = set(), []
    for cls in ("positive", "palette"):
        for p in _corpus_images(corpus, cls):
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


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


OWNED_NEG_PREFIX = "neg-owned-"


def _foreign_share(gates, palette: dict, path) -> float:
    """Foreign mass THROUGH THE REAL GATE FUNCTION.

    Deliberately calls palette_coherence.check rather than re-deriving the
    arithmetic: a proof that reimplements the thing it proves drifts from it
    silently, which is the defect class this whole harness exists to catch.
    """
    for f in gates.palette_coherence.check(str(path), palette=palette):
        if f.get("code") == "PALETTE_STATS":
            return float(f["data"]["foreign_share"])
    raise ValueError(f"palette gate returned no PALETTE_STATS for {path}")


def _channel_rotated(gates, src: Path, dst: Path) -> None:
    """(r,g,b) -> (g,b,r), alpha untouched. Every pixel keeps its exact
    luminance-neighbourhood structure, so flat_mass and dominant_share come out
    byte-identical — the arm is invisible to every gate except this one."""
    w, h, rgba = gates._png.decode(str(src))
    out = bytearray(rgba)
    out[0::4], out[1::4], out[2::4] = rgba[1::4], rgba[2::4], rgba[0::4]
    gates._png.encode(str(dst), w, h, bytes(out))


def prove_palette(gates, corpus: Path, palette: dict) -> tuple[list[str], list[str]]:
    """Palette separation proof. Returns (violations, not_run)."""
    violations: list[str] = []
    not_run: list[str] = []
    limit = gates.palette_coherence.MAX_FOREIGN  # the gate's own constant
    print(f"palette side (limit {limit:.0%} foreign mass):")

    positives = _corpus_images(corpus, "positive")
    if not positives:
        return ["no positives — palette proof cannot run"], not_run

    # P1 — the fit admits its own inputs.
    for p in positives:
        s = _foreign_share(gates, palette, p)
        ok = s <= limit
        print(f"  P1 self     {p.name:34s} {s:7.2%} -> {'pass' if ok else 'FAIL'}")
        if not ok:
            violations.append(f"P1 positive {p.name} exceeds max_foreign "
                              f"({s:.2%} > {limit:.0%})")

    # P2 — owned-art negatives must NOT be failed by the palette gate. Their
    # defect is composition; attributing it to colour would be a false reading.
    for p in _corpus_images(corpus, "negative"):
        if not p.name.startswith(OWNED_NEG_PREFIX):
            continue
        s = _foreign_share(gates, palette, p)
        ok = s <= limit
        print(f"  P2 owned-neg {p.name:33s} {s:7.2%} -> {'pass' if ok else 'FAIL'}")
        if not ok:
            violations.append(
                f"P2 owned-art negative {p.name} FAILS the palette gate "
                f"({s:.2%} > {limit:.0%}) — a composition defect is being "
                f"reported as foreign colour; the palette is under-fitted")

    # P3/P4 — the bite arms. No external art: they are synthesised here, so the
    # proof that the gate still fires never depends on assembled pixels.
    with tempfile.TemporaryDirectory(prefix="wa-prove-") as td:
        rot = Path(td) / "bite-channel-rotated.png"
        _channel_rotated(gates, positives[0], rot)
        s = _foreign_share(gates, palette, rot)
        base_stats = gates.clustering.image_stats(positives[0])
        rot_stats = gates.clustering.image_stats(rot)
        invisible = (base_stats["flat_mass"] == rot_stats["flat_mass"]
                     and base_stats["dominant_share"] == rot_stats["dominant_share"])
        print(f"  P3 bite     channel-rot({positives[0].name[:22]}) "
              f"{s:7.2%} -> {'FAIL(good)' if s > limit else 'PASSES(bad)'}"
              f"  clustering-blind={invisible}")
        if s <= limit:
            violations.append(
                f"P3 channel-rotated positive PASSES the palette gate "
                f"({s:.2%} <= {limit:.0%}) — the gate cannot distinguish the "
                f"art family from a hue-permuted impostor and is DEAD")
        if not invisible:
            violations.append(
                "P3 arm is not clustering-blind (flat_mass/dominant_share "
                "moved) — it no longer isolates palette_coherence")

        css = Path(td) / "bite-css-rects.png"
        w, h = 384, 320
        gates._png.encode(str(css), w, h, gates._synth.make_css_rect_scene(7, w, h))
        s = _foreign_share(gates, palette, css)
        print(f"  P4 bite     synthetic CSS rectangles           "
              f"{s:7.2%} -> {'FAIL(good)' if s > limit else 'PASSES(bad)'}")
        if s <= limit:
            violations.append(
                f"P4 synthetic CSS-rectangle scene PASSES the palette gate "
                f"({s:.2%} <= {limit:.0%}) — the gate no longer catches the "
                f"class its own docstring names")

    # P5 — cross-family, against every archived corpus that is present.
    archives = sorted(d for d in corpus.glob(ARCHIVE_GLOB)
                      if d.is_dir() and d.resolve() != corpus.resolve())
    if not archives:
        print("  P5 cross    NOT RUN — no archived corpus present")
        not_run.append("P5 cross-family (no archived corpus dir on disk)")
    for arch in archives:
        imgs = [p for cls in ("positive", "negative", "palette")
                for p in _corpus_images(arch, cls)]
        if not imgs:
            print(f"  P5 cross    NOT RUN — {arch.name} has no images on disk")
            not_run.append(f"P5 cross-family ({arch.name} pixels not assembled)")
            continue
        worst = 1.0
        bad = []
        for p in imgs:
            s = _foreign_share(gates, palette, p)
            worst = min(worst, s)
            if s <= limit:
                bad.append(f"{p.name} {s:.2%}")
        print(f"  P5 cross    {arch.name:34s} {len(imgs)} imgs, "
              f"min foreign {worst:7.2%} -> {'FAIL(good)' if not bad else 'LEAK'}")
        for b in bad:
            violations.append(
                f"P5 archived foreign-family image PASSES the palette gate: "
                f"{b} (<= {limit:.0%}) — the corpora are not separated")
    return violations, not_run


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

    palette = None
    if args.cmd in ("palette", "all"):
        if not _corpus_images(corpus, "positive"):
            print(f"no positives under {corpus}/positive — cannot fit palette",
                  file=sys.stderr)
            return 1
        inputs = palette_inputs(corpus)
        pal = fit_palette(gates, inputs, args.quant_bits, args.min_bin_share)
        out = out_dir / "palette.json"
        out.write_text(json.dumps(pal, indent=2) + "\n")
        palette = pal
        print(f"wrote {out} ({len(pal['bins'])} bins from "
              f"{len(inputs)} inputs "
              f"({len(_corpus_images(corpus, 'positive'))} positive + "
              f"{len(_corpus_images(corpus, 'palette'))} palette-class), "
              f"{pal['source_pixels']} px)")

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
        if palette is None:
            ppath = out_dir / "palette.json"
            if not ppath.is_file():
                print(f"no palette at {ppath} — run palette first",
                      file=sys.stderr)
                return 1
            palette = json.loads(ppath.read_text())
        violations = prove(gates, corpus, bounds)
        pal_viol, not_run = prove_palette(gates, corpus, palette)
        violations += pal_viol
        if violations:
            print("PROVE FAILED:")
            for v in violations:
                print(f"  - {v}")
            rc = 1
        else:
            print("PROVE OK: composition — negatives trip a clustering bound, "
                  "positives trip none; art family — positives and owned-art "
                  "negatives are palette-native, the bite arms are not")
        # Printed AFTER the verdict, always: an arm that did not run is a
        # disabled sensor, not a pass, and must not be invisible in a green run.
        for n in not_run:
            print(f"NOT RUN (not a pass): {n}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
