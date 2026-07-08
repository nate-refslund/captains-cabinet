#!/usr/bin/env python3.12
"""world-aesthetic-gate.py — THE entrypoint for the Cabinet World aesthetic harness.

One gate, three modes (exactly one required):

    --mechanical   Run the six deterministic ratchet gates (aesthetic_gates.py)
                   with the COMMITTED calibrations (calibration/palette.json +
                   clustering_bounds.json) wired in by explicit path. CI-fast,
                   stdlib-only, no LLM anywhere. This is the per-change gate:
                   run it on every renderer/mockup change, like a test.
    --full         Mechanical first — a frame that fails the ratchets never
                   reaches the judge (mechanical-first doctrine). On pass,
                   emit a blinded pairwise VISION-JUDGE run bundle for the
                   --render candidate (judge/judge_protocol.py build) and
                   print the runner handoff. Judgment happens in an agent at
                   call time; verdicts come from `judge_protocol.py ingest`.
    --calibrate    Refit calibration/*.json from the (gitignored) corpus and
                   run the separation proof (calibrate.py all): every corpus
                   negative must trip a bound, every positive must trip none.

Wiring notes:
  * This wrapper only NAMES the committed calibration paths explicitly and
    forwards them — the underlying ratchet still never autoloads anything
    (a ratchet must not change verdicts because a file appeared next to it).
    --palette/--bounds override the defaults; a missing default is forwarded
    as absent (the gate then SKIPS with a finding, or errors under
    --strict-calibration).
  * Runs per-change, never on cron — see the doc note next to the Cabinet
    World rows in cabinet/services.yml.

Exit codes: 0 pass, 1 gate/prove failure (or judge-build refused because
mechanical failed), 2 unusable invocation.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PALETTE = HERE / "calibration" / "palette.json"
DEFAULT_BOUNDS = HERE / "calibration" / "clustering_bounds.json"


def _load(name: str, path: Path):
    """importlib-by-path under a unique module name — no sys.path mutation
    (same contract as _loader.py; `gates` must stay the pre-existing
    cabinet/scripts/gates package)."""
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="world-aesthetic-gate.py",
        description="Cabinet World aesthetic gate — mechanical ratchets, "
                    "vision-judge protocol emission, corpus calibration.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mechanical", action="store_true",
                      help="ratchet gates only (CI-fast)")
    mode.add_argument("--full", action="store_true",
                      help="ratchets + vision-judge run-bundle emission")
    mode.add_argument("--calibrate", action="store_true",
                      help="refit calibrations from the corpus + prove")

    g = p.add_argument_group("mechanical/full inputs (aesthetic_gates.py)")
    g.add_argument("--map", dest="map_path", help="tilemap JSON (map/v1)")
    g.add_argument("--render", dest="render_path",
                   help="render PNG (also the judge candidate under --full)")
    g.add_argument("--labels", dest="labels_path",
                   help="labels JSON (labels/v1)")
    g.add_argument("--palette", dest="palette_path",
                   help=f"palette calibration (default {DEFAULT_PALETTE})")
    g.add_argument("--bounds", dest="bounds_path",
                   help=f"clustering bounds (default {DEFAULT_BOUNDS})")
    g.add_argument("--ui-rects", dest="ui_rects_path",
                   help="sanctioned UI chrome rects JSON")
    g.add_argument("--only", help="gate subset")
    g.add_argument("--skip", help="gates to skip")
    g.add_argument("--out", help="findings JSON output path")
    g.add_argument("--strict", action="store_true",
                   help="warnings also fail")
    g.add_argument("--strict-calibration", action="store_true",
                   help="missing calibration is an error, not a skip")
    g.add_argument("--pixel-scale", type=int, default=None,
                   help="integer render scale (chunky-pixel zoom)")

    j = p.add_argument_group("judge emission (--full)")
    j.add_argument("--seed", type=int, default=None, help="judge RNG seed")
    j.add_argument("--pos-samples", type=int, default=0,
                   help="corpus positives per candidate (0 = all)")
    j.add_argument("--neg-samples", type=int, default=0,
                   help="corpus negatives per candidate (0 = all)")
    j.add_argument("--cal-max-pairs", type=int, default=0,
                   help="cap the hidden calibration cross product (0 = all)")
    j.add_argument("--out-root", default=None,
                   help="judge run-bundle root (default judge/runs/)")

    c = p.add_argument_group("calibration (--calibrate)")
    c.add_argument("--corpus", default=None,
                   help="corpus dir (default corpus/)")
    c.add_argument("--calib-out-dir", default=None,
                   help="calibration output dir (default calibration/)")
    return p


def _mechanical_argv(args) -> list[str]:
    argv: list[str] = []
    palette = args.palette_path or (
        str(DEFAULT_PALETTE) if DEFAULT_PALETTE.is_file() else None)
    bounds = args.bounds_path or (
        str(DEFAULT_BOUNDS) if DEFAULT_BOUNDS.is_file() else None)
    for flag, val in (("--map", args.map_path),
                      ("--render", args.render_path),
                      ("--labels", args.labels_path),
                      ("--palette", palette),
                      ("--bounds", bounds),
                      ("--ui-rects", args.ui_rects_path),
                      ("--only", args.only),
                      ("--skip", args.skip),
                      ("--out", args.out)):
        if val:
            argv += [flag, str(val)]
    if args.strict:
        argv.append("--strict")
    if args.strict_calibration:
        argv.append("--strict-calibration")
    if args.pixel_scale is not None:
        argv += ["--pixel-scale", str(args.pixel_scale)]
    return argv


def run_mechanical(args) -> int:
    runner = _load("world_aesthetic_runner", HERE / "aesthetic_gates.py")
    return runner.main(_mechanical_argv(args))


def run_full(args) -> int:
    rc = run_mechanical(args)
    if rc != 0:
        print("mechanical gates FAILED — vision-judge run not built "
              "(fix the ratchet findings first; the judge only scores "
              "frames that already clear the mechanical floor)",
              file=sys.stderr)
        return rc
    if not args.render_path:
        print("error: --full needs --render (the judge candidate frame)",
              file=sys.stderr)
        return 2
    loader = _load("world_aesthetic_loader", HERE / "_loader.py")
    jp = loader.load_judge().judge_protocol
    build_argv = ["build", "--candidate", str(args.render_path)]
    if args.seed is not None:
        build_argv += ["--seed", str(args.seed)]
    for flag, val in (("--pos-samples", args.pos_samples),
                      ("--neg-samples", args.neg_samples),
                      ("--cal-max-pairs", args.cal_max_pairs)):
        if val:
            build_argv += [flag, str(val)]
    if args.out_root:
        build_argv += ["--out-root", str(args.out_root)]
    rc = jp.main(build_argv)
    return 0 if rc == 0 else (rc if rc in (1, 2) else 1)


def run_calibrate(args) -> int:
    calibrate = _load("world_aesthetic_calibrate", HERE / "calibrate.py")
    argv = ["all"]
    if args.corpus:
        argv += ["--corpus", str(args.corpus)]
    if args.calib_out_dir:
        argv += ["--out-dir", str(args.calib_out_dir)]
    return calibrate.main(argv)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mechanical:
        return run_mechanical(args)
    if args.full:
        return run_full(args)
    return run_calibrate(args)


if __name__ == "__main__":
    sys.exit(main())
