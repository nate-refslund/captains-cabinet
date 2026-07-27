#!/usr/bin/env python3
"""capture.py — one command: compose a world state, draw it, and judge it.

    python3.12 cabinet/scripts/world-capture/capture.py --state hamlet
    python3.12 cabinet/scripts/world-capture/capture.py --state camp
    python3.12 cabinet/scripts/world-capture/capture.py --state hamlet --no-verify

It runs three things in order, all of them REAL — no fixtures, no cached frame:

  1. emit.ts, in node, calling the SAME composeLayout the world suite tests.
     No browser: the layout is a pure function, so the blueprint the checks read
     needs nothing but node and the shipped pack.
  2. raster.py, which draws the frame plus the sprites-free ground layer and the
     forward/reverse id buffers.
  3. checks/verify.py, which runs all twelve invariants and prints the
     unchecked-surface list.

WHY THE CHECKS ARE MIRRORED INTO THIS REPO (mirror/, byte-identical, guarded by
sync-checks.py --check): a sensor that only exists on one laptop is not a gate.
The originals live in the private meta workspace; the mirror is what CI runs,
and the sync script fails if the two ever differ, so there is exactly one
authority and one way to notice drift.

CAPTURE AT SCALE 1.0 TO JUDGE. --scale exists for eyeballing; the checks
carry absolute-pixel constants, so a shrunk frame is measured at a different
relative resolution and invents defects (see --scale's help for the numbers).

EXIT CODE IS verify.py's, unchanged. A red arm here is a red build.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MIRROR = HERE / "mirror"
DEFAULT_PACK_DIR = REPO / "cabinet" / "dashboard" / "public" / "world-assets" / "originals" / "iso"


def node_major() -> int:
    try:
        v = subprocess.run(["node", "-v"], capture_output=True, text=True, check=True).stdout
        return int(v.strip().lstrip("v").split(".")[0])
    except Exception:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="hamlet",
                    help="a fixture name under states/, or a path to one")
    ap.add_argument("--pack-dir", default=str(DEFAULT_PACK_DIR),
                    help="directory holding world-pack.json and its atlas PNGs")
    ap.add_argument("--out", default=None, help="output directory (default /tmp/world-capture/<state>)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="scale the whole frame. FOR EYEBALLING ONLY, NEVER FOR JUDGING: world_checks.py carries absolute-pixel constants (road_mask steps 3px, check_shadows samples 3/7/12px below a base and takes its bare reference at max(70, w*1.5)), so a shrunk frame is measured at a different relative resolution. Measured at --scale 0.45 on a frame that is GREEN at 1.0: on_road invents one sprite and shadows drops to 46-54%%, under its 55%% floor. Capture at 1.0 to judge.")
    ap.add_argument("--seed", type=int, default=0, help="ground-texture seed (not the world seed)")
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()

    fixture = Path(a.state) if os.path.sep in a.state else HERE / "states" / f"{a.state}.json"
    if not fixture.exists():
        print(f"capture: no state fixture at {fixture}", file=sys.stderr)
        return 2
    name = json.loads(fixture.read_text()).get("name", fixture.stem)

    pack_dir = Path(a.pack_dir)
    pack = pack_dir / "world-pack.json"
    if not pack.exists():
        print(f"capture: no world-pack.json under {pack_dir}", file=sys.stderr)
        return 2

    out = Path(a.out) if a.out else Path("/tmp/world-capture") / name
    out.mkdir(parents=True, exist_ok=True)

    # ---- 1. the layout, from the real composeLayout -----------------------
    # node's own type stripping needs 22.6+; below that there is no way to run
    # the dashboard's TypeScript without a build step, and saying so beats
    # emitting a stale blueprint from a cached file.
    if node_major() < 22:
        print(f"capture: node {node_major()} cannot strip TypeScript — need >= 22 "
              "(the CI arm runs the emitter in-process through vitest instead)",
              file=sys.stderr)
        return 2
    emit = subprocess.run(
        ["node", "--import", str(HERE / "resolve-ts.mjs"), str(HERE / "emit.ts"),
         "--pack", str(pack), "--state", str(fixture), "--out", str(out)],
        cwd=str(HERE), text=True, capture_output=True)
    sys.stdout.write(_quiet(emit.stdout))
    if emit.returncode != 0:
        sys.stderr.write(emit.stderr)
        return emit.returncode

    # ---- 2. the pixels ----------------------------------------------------
    assets = out / "assets"
    if assets.exists():
        # A stale asset from a previous state would be swept by the three
        # asset-level checks and reported against a frame that never drew it.
        shutil.rmtree(assets)
    frame = out / "frame.png"
    r = subprocess.run(
        [sys.executable, str(HERE / "raster.py"),
         "--draw", str(out / "draw.json"), "--blueprint", str(out / "blueprint.json"),
         "--pack", str(pack), "--atlas", str(pack_dir), "--assets", str(assets),
         "--out", str(frame), "--scale", str(a.scale), "--seed", str(a.seed)],
        cwd=str(HERE), text=True)
    if r.returncode != 0:
        return r.returncode

    if a.no_verify:
        print(f"capture: wrote {frame} (verify skipped by request)")
        return 0

    # ---- 3. the twelve invariants -----------------------------------------
    v = subprocess.run(
        [sys.executable, str(MIRROR / "checks" / "verify.py"),
         "--render", str(frame), "--assets", str(assets),
         "--allow-ambient", str(HERE / "ambient-nature.txt")],
        text=True)
    return v.returncode


def _quiet(s: str) -> str:
    """Drop node's TYPELESS_PACKAGE_JSON chatter; keep everything the tool said."""
    keep = [ln for ln in s.splitlines()
            if "MODULE_TYPELESS_PACKAGE_JSON" not in ln
            and not ln.startswith("Reparsing as ES module")
            and not ln.startswith("To eliminate this warning")
            and not ln.startswith("(Use `node")]
    return "\n".join(keep) + ("\n" if keep else "")


if __name__ == "__main__":
    raise SystemExit(main())
