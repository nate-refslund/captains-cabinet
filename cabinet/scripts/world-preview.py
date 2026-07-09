#!/usr/bin/env python3.12
"""world-preview.py — Captain's growth-ladder preview tool (WORLD-V1A T1).

Renders ONE still PNG of the world at a chosen maturity, so the Captain can
edit cabinet/world/growth-ladders.yml VALUES, look at the result, and commit
— no orchestrator in the loop (spec v2 §15.3: "Ships with a preview tool —
world-preview --maturity <index|date>").

HONEST-CHEAPER CHOICE (T1 brief): this is the PIL twin reusing the proven
compositor lineage — it replays REAL history through the config via
world-growth-backtest.py (the calibration-gate harness, same math the TS
era-engine mirrors) and paints the selected day with the compose_growth
painter now landed at cabinet/scripts/world-compose/. Nothing is invented:
  --maturity 2026-06-28        → that real day's resolved world
  --maturity 0.30              → the FIRST real day whose era index ≥ 0.30
                                 (an index beyond lived history is refused
                                 honestly — the tool never fabricates state)

Every render can be gated: --gate runs world-aesthetic-gate.py --mechanical
on the emitted frame (fix composition, never thresholds).

Read-only over the estate (sqlite -readonly, git log, yaml). Deterministic:
replay + painting are pure functions of (history, config, date).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]
DEFAULT_CONFIG = REPO / "cabinet" / "world" / "growth-ladders.yml"
DEFAULT_COMPOSITOR = SCRIPTS / "world-compose"
GATE = SCRIPTS / "world-aesthetic" / "world-aesthetic-gate.py"
VALIDATOR = SCRIPTS / "world-growth-validate.py"


def _load_backtest():
    """Import world-growth-backtest.py as a module (hyphenated filename)."""
    spec = importlib.util.spec_from_file_location(
        "world_growth_backtest", SCRIPTS / "world-growth-backtest.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _resolve_day(timeline: dict, maturity: str) -> dict:
    days = timeline["days"]
    # date form
    try:
        d = dt.date.fromisoformat(maturity)
        for rec in days:
            if rec["date"] == d.isoformat():
                return rec
        raise SystemExit(
            f"--maturity {maturity}: outside lived history "
            f"({days[0]['date']} … {days[-1]['date']}) — nothing to render honestly"
        )
    except ValueError:
        pass
    # index form
    try:
        idx = float(maturity)
    except ValueError:
        raise SystemExit(f"--maturity must be YYYY-MM-DD or a float index (got {maturity!r})")
    for rec in days:
        if rec["index"] >= idx:
            return rec
    top = max(r["index"] for r in days)
    raise SystemExit(
        f"--maturity {idx}: the org's lived history tops out at index {top:.3f} "
        f"({days[-1]['date']}) — a higher maturity has not been earned; "
        "the preview never fabricates state"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render one still of the world at a maturity (index or date)"
    )
    ap.add_argument("--maturity", required=True, help="YYYY-MM-DD or era-index float")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG),
                    help="growth-ladders yml (default: the live law file)")
    ap.add_argument("--out", default=None,
                    help="output PNG path (default: /tmp/world-preview-<maturity>.png)")
    ap.add_argument("--db", default=None, help="org-runtime sqlite (backtest default)")
    ap.add_argument("--history", default=None,
                    help="reuse a previously extracted history.json (faster loop)")
    ap.add_argument("--compositor-dir", default=str(DEFAULT_COMPOSITOR),
                    help="dir holding world-unified/ + world-next/ (in-repo default)")
    ap.add_argument("--gate", action="store_true",
                    help="run world-aesthetic-gate.py --mechanical on the frame")
    ap.add_argument("--emit-timeline", default=None,
                    help="also write the full replay timeline JSON here")
    args = ap.parse_args()

    bt = _load_backtest()

    # config: refuse malformed/untruthful law before rendering anything
    check = subprocess.run(
        [sys.executable, str(VALIDATOR), "--quiet", args.config], check=False
    )
    if check.returncode != 0:
        raise SystemExit("config refused by world-growth-validate.py — fix it first")
    config = yaml.safe_load(Path(args.config).read_text())

    if args.history:
        history = json.loads(Path(args.history).read_text())
        if "series" not in history or "days" not in history:
            raise SystemExit(
                f"--history {args.history} is not an extract_history dump "
                "(want the history.json a backtest run emits, not a timeline)"
            )
    else:
        db = Path(args.db) if args.db else Path(bt.DB_DEFAULT)
        raw = bt._sqlite_ro(db, "SELECT MAX(substr(created_at,1,10)) FROM org_events;")
        if not raw or not raw.strip():
            raise SystemExit(f"org_events unreadable at {db} — no history, no preview")
        history = bt.extract_history(db, REPO, dt.date.fromisoformat(raw.strip()))

    timeline = bt.replay(config, history)
    if args.emit_timeline:
        Path(args.emit_timeline).write_text(json.dumps(timeline, indent=1, sort_keys=True))

    rec = _resolve_day(timeline, args.maturity)
    print(
        f"day {rec['date']} · era {rec['era']} @ index {rec['index']:.3f} · "
        f"{sum(1 for c in rec['changes'] if c['kind'] == 'growth')} growth changes that day"
    )

    out = Path(args.out) if args.out else Path(f"/tmp/world-preview-{args.maturity.replace('/', '-')}.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    # one-day slice through the PROVEN strip painter; frame_dates emits the
    # chrome-free native frame (the aesthetic-gate unit)
    sliced = {**timeline, "days": [rec]}
    workdir = out.parent / f".world-preview-{rec['date']}"
    workdir.mkdir(exist_ok=True)
    strip_png = workdir / "strip.png"
    bt.render_strip(sliced, strip_png, Path(args.compositor_dir), frame_dates=[rec["date"]])
    frame = workdir / f"frame-{timeline['candidate']}-{rec['date']}.png"
    if not frame.exists():
        raise SystemExit(f"compositor did not emit {frame} — see errors above")
    shutil.move(str(frame), str(out))
    shutil.rmtree(workdir, ignore_errors=True)
    print(f"still: {out}")

    if args.gate:
        gate = subprocess.run(
            [sys.executable, str(GATE), "--mechanical", "--render", str(out)],
            check=False,
        )
        if gate.returncode != 0:
            raise SystemExit("aesthetic gate FAILED on this preview — fix composition, never thresholds")
        print("aesthetic gate: GREEN (mechanical)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
