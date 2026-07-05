#!/usr/bin/env python3.12
"""build-regression-corpus.py — harvest human corrections into the frozen
regression corpus (flywheel step 1; fresh review 2026-07-04 §6.2).

Reads the consequence ledger READ-ONLY (framework.fidelity.consequence.
read_ledger — deduped, sim-quarantined, symlink-fenced, honoring
CABINET_EVENT_LOG_DIR) and freezes every historical human correction
(edit / skip / veto / undo / human-wrong verdict_human rows) as a replayable
case under framework/fidelity/regression_corpus/ — an UNLOCKED dir
(deliberately NOT memory/golden-evals/, which is germline schg-locked; see
cabinet/scripts/germline-lock.sh DIRS).

Each case = {input situation (leak-safe replay reference), the human verdict,
the graduation cell}. All harvest/serialization logic lives in
framework/fidelity/regression_corpus_lib.py — this file is a thin CLI so the
supply lane can schedule it BY PATH (cabinet/services.yml is owned by the
supply lane and is not touched here).

Idempotent + deterministic: same ledger -> byte-identical corpus; re-runs only
APPEND new cases; existing case files are FROZEN and never rewritten. A
regeneration that disagrees with a frozen file is an integrity alarm
(append-only violation upstream or serialization drift) — the frozen file is
kept verbatim and this exits 3 so the cadence surfaces it.

The ONLY writes are into the corpus dir. No network, no LLM, no Redis, no
secrets (none exist to leak — pure local file IO).

Usage:
  python3.12 cabinet/scripts/build-regression-corpus.py            # full harvest
  python3.12 cabinet/scripts/build-regression-corpus.py --since 2026-06-01
  python3.12 cabinet/scripts/build-regression-corpus.py --corpus-dir /tmp/c --json

Exit codes: 0 = harvested clean (including an honest 0-correction ledger);
            3 = frozen-conflict(s) detected (corpus kept frozen — investigate);
            2 = error (NO corpus mutation is trusted; nothing to act on).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.fidelity.regression_corpus_lib import (  # noqa: E402
    DEFAULT_CORPUS_DIR,
    extract_corrections,
    write_corpus,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Freeze human corrections from the consequence ledger "
                    "into the replayable regression corpus."
    )
    ap.add_argument(
        "--corpus-dir", default=str(DEFAULT_CORPUS_DIR),
        help="corpus root (default: framework/fidelity/regression_corpus/). "
             "Tests point this at a temp dir.",
    )
    ap.add_argument(
        "--since", default=None,
        help="ISO lower bound on ledger event ts (inclusive). Default: ALL "
             "history — the task is to harvest every historical correction.",
    )
    ap.add_argument(
        "--json", action="store_true",
        help="emit the machine-readable summary instead of the human one",
    )
    args = ap.parse_args(argv)

    try:
        cases = extract_corrections(since=args.since)
        summary = write_corpus(cases, corpus_dir=Path(args.corpus_dir))
    except Exception as exc:  # noqa: BLE001 — CLI boundary: report, exit 2
        print(f"ERROR: harvest failed: {exc!r}", file=sys.stderr)
        return 2

    if args.json:
        # Drop the embedded manifest body (it lives on disk); keep the counts.
        out = {k: v for k, v in summary.items() if k != "manifest"}
        out["fingerprint"] = summary["manifest"]["fingerprint"]
        out["kinds"] = summary["manifest"]["kinds"]
        print(json.dumps(out, sort_keys=True))
    else:
        m = summary["manifest"]
        print(
            f"regression corpus @ {args.corpus_dir}: "
            f"{len(summary['written'])} new, {len(summary['unchanged'])} unchanged, "
            f"{len(summary['conflicts'])} frozen-conflict(s); "
            f"total {summary['total_on_disk']} case(s) "
            f"kinds={m['kinds']} fingerprint={m['fingerprint'][:12]}"
        )

    if summary["conflicts"]:
        # Frozen files were KEPT; the disagreement itself is the alarm.
        print(
            "FROZEN-CONFLICT: regenerated case(s) disagree with frozen files: "
            + ", ".join(summary["conflicts"]),
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
