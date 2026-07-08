#!/usr/bin/env python3.12
"""Aesthetic-gate runner: mechanical ratchets over map data + renders.

Usage:
    aesthetic_gates.py --map MAP.json [--render OUT.png] [--labels LABELS.json]
                       [--palette calibration/palette.json]
                       [--bounds calibration/clustering_bounds.json]
                       [--ui-rects RECTS.json] [--only g1,g2] [--skip g1]
                       [--out findings.json] [--strict] [--strict-calibration]
                       [--pixel-scale N] [--max-foreign F] [--spam-ratio F]

Gates + required inputs (a gate with a missing input is SKIPPED with an info
finding, never silently dropped):
    edge_continuity    --map
    connectivity       --map
    scale_lint         --map
    label_overlap      --labels (+ --render for PNG-dims cross-check)
    palette_coherence  --render (+ --palette calibration)
    clustering         --map and/or --render (+ --bounds calibration)

Output: findings JSON (schema cabinet.world.aesthetic-findings/v1) on stdout
and optionally --out. Exit codes: 0 = pass (warnings allowed unless --strict),
1 = at least one error finding (or warn under --strict), 2 = unusable
invocation (no inputs / unreadable / invalid map).

Calibration files are passed EXPLICITLY (no autoload): a ratchet must never
change verdicts because a file appeared next to it.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_loader():
    spec = importlib.util.spec_from_file_location(
        "world_aesthetic_loader", HERE / "_loader.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aesthetic_gates.py",
        description="Mechanical aesthetic ratchets for Cabinet World.")
    p.add_argument("--map", dest="map_path", help="tilemap JSON (map/v1)")
    p.add_argument("--render", dest="render_path", help="render PNG")
    p.add_argument("--labels", dest="labels_path",
                   help="labels JSON (labels/v1)")
    p.add_argument("--palette", dest="palette_path",
                   help="palette calibration JSON")
    p.add_argument("--bounds", dest="bounds_path",
                   help="clustering bounds calibration JSON")
    p.add_argument("--ui-rects", dest="ui_rects_path",
                   help="JSON list of sanctioned UI chrome rects [x,y,w,h]")
    p.add_argument("--only", help="comma-separated gate subset to run")
    p.add_argument("--skip", help="comma-separated gates to skip")
    p.add_argument("--out", help="also write findings JSON here")
    p.add_argument("--strict", action="store_true",
                   help="warnings also fail (exit 1)")
    p.add_argument("--strict-calibration", action="store_true",
                   help="missing palette/bounds calibration is an error")
    p.add_argument("--pixel-scale", type=int, default=1,
                   help="integer render scale (chunky-pixel zoom), default 1")
    p.add_argument("--max-foreign", type=float, default=None,
                   help="palette foreign-mass limit (default 0.05)")
    p.add_argument("--spam-ratio", type=float, default=None,
                   help="label area/render area limit per zoom (default 0.15)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    gates_pkg = _load_loader().load_gates()
    C = gates_pkg._common

    if not (args.map_path or args.render_path or args.labels_path):
        print("error: nothing to check — pass --map and/or --render/--labels",
              file=sys.stderr)
        return 2

    selected = list(gates_pkg.GATE_ORDER)
    if args.only:
        wanted = [g.strip() for g in args.only.split(",") if g.strip()]
        unknown = [g for g in wanted if g not in gates_pkg.GATES]
        if unknown:
            print(f"error: unknown gate(s): {', '.join(unknown)}",
                  file=sys.stderr)
            return 2
        selected = [g for g in gates_pkg.GATE_ORDER if g in wanted]
    if args.skip:
        skipped_names = {g.strip() for g in args.skip.split(",")}
        selected = [g for g in selected if g not in skipped_names]

    map_data = None
    findings: list[dict] = []
    skipped: list[dict] = []
    if args.map_path:
        try:
            map_data = C.load_map(args.map_path)
        except (OSError, ValueError) as e:
            print(f"error: cannot load map: {e}", file=sys.stderr)
            return 2
    ui_rects = None
    if args.ui_rects_path:
        try:
            ui_rects = C.load_json(args.ui_rects_path)
        except (OSError, ValueError) as e:
            print(f"error: cannot load --ui-rects: {e}", file=sys.stderr)
            return 2
    labels = None
    if args.labels_path:
        try:
            labels = C.load_json(args.labels_path)
        except (OSError, ValueError) as e:
            print(f"error: cannot load labels: {e}", file=sys.stderr)
            return 2
    for path, flag in ((args.render_path, "--render"),
                       (args.palette_path, "--palette"),
                       (args.bounds_path, "--bounds")):
        if path and not Path(path).is_file():
            print(f"error: {flag} file not found: {path}", file=sys.stderr)
            return 2

    strict_cal = {"strict_calibration": True} if args.strict_calibration else {}
    gates_run: list[str] = []

    def skip(gate: str, reason: str):
        skipped.append({"gate": gate, "reason": reason})
        findings.append(C.finding(gate, "GATE_SKIPPED", C.SEV_INFO,
                                  f"skipped: {reason}"))

    for name in selected:
        mod = gates_pkg.GATES[name]
        try:
            if name in ("edge_continuity", "connectivity", "scale_lint"):
                if map_data is None:
                    skip(name, "needs --map")
                    continue
                findings.extend(mod.check(map_data, config=dict(strict_cal)))
            elif name == "label_overlap":
                if labels is None:
                    skip(name, "needs --labels")
                    continue
                cfg = dict(strict_cal)
                if args.spam_ratio is not None:
                    cfg["spam_ratio"] = args.spam_ratio
                findings.extend(mod.check(
                    labels, image_path=args.render_path, config=cfg))
            elif name == "palette_coherence":
                if args.render_path is None:
                    skip(name, "needs --render")
                    continue
                cfg = dict(strict_cal)
                if ui_rects is not None:
                    cfg["ui_rects"] = ui_rects
                if args.max_foreign is not None:
                    cfg["max_foreign"] = args.max_foreign
                findings.extend(mod.check(
                    args.render_path, palette=args.palette_path, config=cfg))
            elif name == "clustering":
                if map_data is None and args.render_path is None:
                    skip(name, "needs --map and/or --render")
                    continue
                cfg = dict(strict_cal)
                cfg["pixel_scale"] = args.pixel_scale
                findings.extend(mod.check(
                    map_data=map_data, image_path=args.render_path,
                    bounds=args.bounds_path, config=cfg))
            gates_run.append(name)
        except Exception as e:  # a broken gate must fail loudly, not pass
            findings.append(C.finding(
                name, "GATE_CRASH", C.SEV_ERROR,
                f"gate crashed: {type(e).__name__}: {e}"))
            gates_run.append(name)

    counts = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    exit_code = 0
    if counts["error"] or (args.strict and counts["warn"]):
        exit_code = 1

    envelope = {
        "schema": gates_pkg.FINDINGS_SCHEMA,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {k: v for k, v in (
            ("map", args.map_path), ("render", args.render_path),
            ("labels", args.labels_path), ("palette", args.palette_path),
            ("bounds", args.bounds_path)) if v},
        "gates_run": gates_run,
        "skipped": skipped,
        "counts": counts,
        "ok": exit_code == 0,
        "findings": findings,
    }
    text = json.dumps(envelope, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
