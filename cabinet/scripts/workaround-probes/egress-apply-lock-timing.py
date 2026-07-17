#!/usr/bin/env python3.12
"""Single-contender apply timing probe for the egress-guard apply lock.

Read-only simulation (no guard execution, no lock contention, no fleet
touch): parses ``acquire_apply_lock()`` out of cabinet/scripts/egress-guard.sh
as TEXT and computes the acquire timeout (loop bound x sleep interval), then
compares it against the recorded worst-case apply hold. The 2026-07-16
fleet-down incident class: acquire waited 10s (100 x 0.1s) while an apply
held the lock ~50s and 4-6 KeepAlive labels retried every 30s — losers
failed closed forever (livelock herd).

Registry row: cabinet/config/workarounds.yml (egress apply-lock livelock).
Runner: cabinet/scripts/workaround-retest.sh (verdict contract below).

Exit codes (workaround-retest verdict contract):
  0  defect still present (acquire timeout < worst-case hold)  -> still_needed
  1  defect absent (timeout >= hold, or lock now flock-shaped) -> fix_confirmed
  2  guard unreadable / function unparseable                   -> inconclusive

Usage: egress-apply-lock-timing.py [path-to-egress-guard.sh]
(no argument = the repo's own cabinet/scripts/egress-guard.sh; the argument
exists so tests can point the probe at fixture guard scripts).
"""
from __future__ import annotations

import pathlib
import re
import sys

# Observed 2026-07-16: a guard apply held the lock ~50s worst-case while
# acquire waited only 10s. The fix bar: acquire timeout must cover the
# worst-case hold (retry-with-jitter or flock counts as fixed only if the
# effective wait clears this bar or the lock-acquisition mkdir-spin — the
# `mkdir "$APPLY_LOCK"` poll — is gone; an unrelated `mkdir -p "$EGRESS_DIR"`
# dir-setup line may remain and does NOT keep the row open).
WORST_CASE_APPLY_HOLD_S = 50.0


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        guard = pathlib.Path(argv[1])
    else:
        # probe lives at cabinet/scripts/workaround-probes/ -> repo root is 3 up
        root = pathlib.Path(__file__).resolve().parents[3]
        guard = root / "cabinet" / "scripts" / "egress-guard.sh"
    try:
        src = guard.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 2

    m = re.search(r"^acquire_apply_lock\(\)\s*\{(.*?)^\}", src, re.S | re.M)
    if not m:
        # Function renamed/reshaped (e.g. a flock rewrite) — a human must
        # re-judge the row; never guess a verdict from a shape we don't know.
        return 2
    body = m.group(1)

    # The livelock class IS the mkdir-spin poll-and-give-up on the APPLY lock.
    # Scope the "spin is gone" test to the LOCK-acquisition mkdir (mkdir on
    # $APPLY_LOCK), NOT any mkdir: a realistic flock rewrite keeps the
    # `mkdir -p "$EGRESS_DIR"` directory setup, so a blanket `"mkdir" not in
    # body` would wrongly skip the flock branch and report inconclusive.
    has_lock_mkdir_spin = re.search(r'mkdir\s+["\']?\$\{?APPLY_LOCK', body) is not None
    if "flock" in body and not has_lock_mkdir_spin:
        # mkdir-spin replaced by blocking flock: the livelock class is gone
        # by construction (flock waits, it does not poll-and-give-up).
        return 1

    lt = re.search(r"-lt\s+(\d+)", body)
    sl = re.search(r"sleep\s+([0-9.]+)", body)
    if not (lt and sl):
        return 2
    acquire_timeout_s = int(lt.group(1)) * float(sl.group(1))
    return 0 if acquire_timeout_s < WORST_CASE_APPLY_HOLD_S else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
