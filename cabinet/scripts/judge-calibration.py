#!/usr/bin/env python3.12
"""judge-calibration.py — measure verdict_judge ↔ verdict_human agreement and
maintain the demotion-precondition proof (flywheel step 3; fresh review
2026-07-04 §6.3 / Align-Evals pattern).

Deterministic and OFFLINE: it measures verdicts already RECORDED on the
consequence ledger (raw rows, superseded judge opinions included — see
framework/fidelity/judge_calibration.py's pairing model) against the human
labels (verdict_human rows, June 2026 window onward by default). It invokes
NO LLM, opens NO network connection, and carries NO credentials — the judging
already happened when the supply lane's verifier / fidelity scorer wrote the
verdict_judge rows.

THE HARD BAR: agreement >= 80% over >= 10 pairs (JUDGE_HARD_BAR / MIN_PAIRS —
code constants in framework/fidelity/judge_calibration.py, deliberately NOT
flags: a bar loosenable from argv is not a bar). Until the bar is met and the
proof is fresh (< 14d), `judge_verdicts_may_demote()` returns False and NO
verdict_judge row may count toward demotion — the supply lane's verifier
(framework/probes/verifier.py, not edited by this lane) checks that function
before emitting demotion-capable judge verdicts.

Status proof: $CABINET_EVENT_LOG_DIR/judge-calibration-status.json, written
ATOMICALLY on every successful measurement — INCLUDING a below-bar one, so a
freshly failing calibration closes the flag immediately. On a measurement
ERROR the status is NOT written (a fabricated proof is worse than an aging
one; the 14-day max-age expires the old proof on its own).

All measurement logic lives in framework/fidelity/judge_calibration.py — this
file is a thin CLI so the supply lane can schedule it BY PATH
(cabinet/services.yml is owned by the supply lane and is not touched here).

Usage:
  python3.12 cabinet/scripts/judge-calibration.py                 # June->now
  python3.12 cabinet/scripts/judge-calibration.py --since 2026-06-01 --until 2026-07-01
  python3.12 cabinet/scripts/judge-calibration.py --json --no-write

Exit codes: 0 = bar met (proof written; judge may gate demotion);
            1 = bar NOT met (below bar or insufficient pairs; failing proof
                written unless --no-write — the flag is/stays closed);
            2 = error (nothing written; previous proof ages out).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.fidelity.judge_calibration import (  # noqa: E402
    DEFAULT_SINCE,
    JUDGE_HARD_BAR,
    MIN_PAIRS,
    collect_pairs,
    compute_agreement,
    judge_verdicts_may_demote,
    status_path,
    write_status,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Measure LLM-judge (verdict_judge) agreement with the "
                    "Captain's labels (verdict_human) and maintain the "
                    "demotion-precondition proof."
    )
    ap.add_argument(
        "--since", default=DEFAULT_SINCE,
        help=f"human-label window start, ISO inclusive (default {DEFAULT_SINCE} "
             "— the June human-labeled fidelity cases)",
    )
    ap.add_argument(
        "--until", default=None,
        help="human-label window end, ISO exclusive (default: open)",
    )
    ap.add_argument(
        "--json", action="store_true",
        help="emit the machine-readable report instead of the human one",
    )
    ap.add_argument(
        "--no-write", action="store_true",
        help="measure + report only; do not touch the status proof "
             "(inspection mode for humans; the scheduled run writes)",
    )
    args = ap.parse_args(argv)

    try:
        pairs = collect_pairs(since=args.since, until=args.until)
        report = compute_agreement(pairs)
        if not args.no_write:
            write_status(report, since=args.since, until=args.until)
    except Exception as exc:  # noqa: BLE001 — CLI boundary: report, exit 2
        print(f"ERROR: calibration failed (no status written): {exc!r}",
              file=sys.stderr)
        return 2

    allowed = judge_verdicts_may_demote() if not args.no_write else None
    if args.json:
        out = dict(report)
        out.update({"since": args.since, "until": args.until,
                    "status_path": str(status_path()),
                    "written": not args.no_write,
                    "judge_verdicts_may_demote": allowed})
        print(json.dumps(out, sort_keys=True))
    else:
        rate = report["agreement_rate"]
        rate_s = f"{rate:.3f}" if rate is not None else "unmeasured"
        print(
            f"judge calibration [{args.since} .. {args.until or 'now'}]: "
            f"{report['pairs']} pair(s), agreement={rate_s} "
            f"(hard bar {JUDGE_HARD_BAR} over >= {MIN_PAIRS} pairs) -> "
            f"bar_met={report['bar_met']}"
            + ("" if args.no_write
               else f"; proof @ {status_path()}; may_demote={allowed}")
        )

    return 0 if report["bar_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
