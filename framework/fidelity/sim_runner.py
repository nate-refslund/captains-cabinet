"""SIE-9 — the sim RUNNER over the SIE-7 quarantine (W3, 2026-07-09).

The sim-harness foundation shipped the FENCES (SIE-7 verdict_sim quarantine in
consequence.py, the A8 as-of search fence, fence_lib readers) but never the
runner that uses them — the ratified remaining work item. This module is that
runner: it replays held-out, leak-guarded historical cases (the same
build_cases → run_case → score pipeline as F1) inside a sim process and lets
every emitted consequence event land — quarantined — in a ``*-sim`` ledger
dir, where the SIE-7 chokepoint stamps ``sim: true`` on each row and the live
readers structurally never see them.

FAIL-CLOSED BY CONSTRUCTION. ``run_sim_batch`` refuses to start unless BOTH
halves of the quarantine agree BEFORE any drive:

  * ``CABINET_SIM_MODE=1``            (the emit path stamps sim markers), and
  * ``CABINET_EVENT_LOG_DIR`` ends in ``-sim`` (the write chokepoint accepts
    those markers — a sim-marked row aimed at a live dir raises
    SimQuarantineError inside consequence.py anyway; this pre-flight just
    fails BEFORE spending officer drives).

After the batch it re-reads the quarantine ledger and hard-fails if a single
unmarked (live-shaped) row is present — defense in depth on top of the
chokepoint, so a sim summary can never be produced over a contaminated dir.

Report-only: output is sim-marked quarantined verdict rows (calibration /
judge-training INPUT, per the D5 sequencing — never graduation, breaker or
cell-math fuel; read_ledger drops sim rows for every live consumer) plus an
atomic JSON summary written INSIDE the quarantine dir.

Usage (a deliberate act, never scheduled):
  CABINET_SIM_MODE=1 CABINET_EVENT_LOG_DIR=~/some/events-sim \\
      python3.12 -m framework.fidelity.sim_runner [role] [n_cases]
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from framework import env  # roster-resolved default role
from framework.fidelity import run_f1
from framework.fidelity.consequence import _sim_mode, read_ledger


class SimHarnessError(RuntimeError):
    """[SIE-9] Raised when the sim harness is asked to run outside a correctly
    armed quarantine (or when post-run verification finds the quarantine dir
    carrying live-shaped rows). Always fail BEFORE spending drives."""


def assert_sim_quarantine(environ: dict[str, str] | None = None) -> Path:
    """Pre-flight: prove the process is a sim process AND the ledger target is
    a quarantine dir. Returns the quarantine dir path. Raises SimHarnessError
    otherwise — there is deliberately no way to 'force' past this."""
    env = os.environ if environ is None else environ
    if env.get("CABINET_SIM_MODE") != "1":
        raise SimHarnessError(
            "CABINET_SIM_MODE != '1' — refusing: an unmarked emit from this "
            "batch would be a LIVE consequence row (SIE-7)."
        )
    raw = env.get("CABINET_EVENT_LOG_DIR", "").strip()
    if not raw:
        raise SimHarnessError(
            "CABINET_EVENT_LOG_DIR unset — a sim batch must aim at an "
            "explicit '-sim' quarantine dir, never the default live ledger."
        )
    target = Path(raw).expanduser()
    if not target.name.endswith("-sim"):
        raise SimHarnessError(
            f"CABINET_EVENT_LOG_DIR {target.name!r} lacks the '-sim' suffix — "
            "the SIE-7 write chokepoint would refuse every row; fix the dir, "
            "do not fight the fence."
        )
    return target


def run_sim_batch(
    officer_role: "str | None" = None,
    n_cases: int = 24,
    *,
    people_dir=None,
    gather: Callable | None = None,
    with_intent: bool = True,
    runner: Callable | None = None,
    scorer_fn: Callable | None = None,
    baseline_llm: Callable | None = None,
    write_summary: bool = True,
) -> dict[str, Any]:
    """Drive one quarantined replay batch and verify the quarantine held.

    Thin by design: the pipeline IS run_f1.run_batch (same leakguard, same
    validated emitter, same scorer/judge) — SIE-9 adds the quarantine
    pre-flight, forces emit_scored=True (sim rows are the product), verifies
    zero live-shaped rows landed, and writes an atomic summary artifact into
    the quarantine dir. Injectable runner/scorer/baseline keep tests offline,
    exactly like run_f1's own tests."""
    officer_role = officer_role or env.chair_officer()
    qdir = assert_sim_quarantine()

    kwargs: dict[str, Any] = {}
    if runner is not None:
        kwargs["runner"] = runner
    if scorer_fn is not None:
        kwargs["scorer_fn"] = scorer_fn
    if baseline_llm is not None:
        kwargs["baseline_llm"] = baseline_llm
    result = run_f1.run_batch(
        officer_role=officer_role, n_cases=n_cases, people_dir=people_dir,
        gather=gather, with_intent=with_intent,
        emit_events=True, emit_scored=True, **kwargs,
    )

    # Post-run quarantine verification. In a sim process read_ledger KEEPS sim
    # rows (the runner is their one legitimate reader); any row WITHOUT the
    # marker inside a '-sim' dir means the fence was bypassed somewhere.
    rows = read_ledger()
    n_sim_rows = sum(1 for r in rows if r.get("sim") is True)
    n_live_shaped = len(rows) - n_sim_rows
    if n_live_shaped:
        raise SimHarnessError(
            f"{n_live_shaped} live-shaped row(s) inside quarantine dir "
            f"{qdir} — refusing to summarize a contaminated sim ledger."
        )

    summary: dict[str, Any] = {
        "sim": True,
        "quarantine_dir": str(qdir),
        "officer_role": officer_role,
        "n_cases_requested": n_cases,
        "n_sim_rows": n_sim_rows,
        **{k: v for k, v in result.items() if k != "scores"},
    }
    if write_summary:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out = qdir / f"sim-batch-summary-{stamp}.json"
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(summary, indent=2, sort_keys=True))
        os.replace(tmp, out)  # atomic — no partial summary is ever readable
        summary["summary_path"] = str(out)
    return summary


if __name__ == "__main__":
    import sys

    role = sys.argv[1] if len(sys.argv) > 1 else env.chair_officer()
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    s = run_sim_batch(officer_role=role, n_cases=n)
    print(json.dumps({k: v for k, v in s.items() if k != "scores"}, indent=2))
    print(f"OK - sim batch quarantined: {s['n_sim_rows']} sim rows in "
          f"{s['quarantine_dir']} (n_scored={s['n_scored']}, "
          f"n_leaked={s['n_leaked']})")
