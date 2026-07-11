#!/usr/bin/env python3.12
"""check-brain-health.py — cabinet-side watch on the screenpipe memory estate.

Destination: $CABINET_ROOT/cabinet/scripts/check-brain-health.py (staged 2026-07-06
at ~/.screenpipe/state/brain-probes/staging/ by the brain-quality Wave F
drill-contract lane; installed by the Captain together with the memory-curator-health
services.yml row staged alongside).

Reads ~/.screenpipe/state/brain_health.json (written by the screenpipe
brain-health sensor at 06:00/18:00) and escalates to cos — retro-trigger-style,
via cabinet/scripts/lib/triggers.sh trigger_send — when any eval-021 invariant
regresses or the sensor output goes stale:

  * staleness: generated_ts older than 26h (the freshness floor; sensor runs
    2x/day, so >26h means the sensor itself is down)
  * frozen-core-14 p@1 < 0.90 or p@3 < 0.93
  * probes.leaks > 0 (hits under excluded/parked prefixes)
  * integrity.suppression_remints > 0 (suppressed person stems re-minted)
  * integrity.excluded_leaks > 0 (excluded folders present in the index)

The trigger message tells cos to run the brain-audit skill
(.claude/skills/brain-audit), which owns the audit -> fix waves -> adversarial
verify -> probe gate loop and the curator freeze/unfreeze runbook.

Honest-log contract (one line per run, machine-greppable):
  BRAIN_HEALTH_OK ...          all invariants green
  BRAIN_HEALTH_ESCALATED ...   breach found AND the cos trigger was queued
  FATAL ...                    breach found but we could NOT page (missing
                               health file counts as a breach; missing/broken
                               triggers lib means the page failed) -> rc 1 so
                               launchd + the watchdog floor surface it

Exit codes: 0 = OK or escalated-successfully (this row's job is to watch and
page, not to thrash); 1 = FATAL (could not read health or could not page).

Runs from the services.yml command wrapper (cwd = $CABINET_ROOT, cabinet/.env
sourced, REDIS_HOST set). Stdlib only; no SQL; no secrets read or logged.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HEALTH = Path.home() / ".screenpipe" / "state" / "brain_health.json"
FRESHNESS_FLOOR_H = 26.0      # sensor runs 06:00 + 18:00 -> >26h = sensor down
P1_FLOOR = 0.90               # eval-021 pinned invariants (frozen-core-14)
P3_FLOOR = 0.93
BRAIN_AUDIT_HINT = (
    "run the brain-audit skill (.claude/skills/brain-audit): probe suite "
    "~/.screenpipe/state/brain-probes/ (run_probes.py + expectations.json), "
    "sensor output ~/.screenpipe/state/brain_health.json"
)


def _cabinet_root() -> Path:
    env = os.environ.get("CABINET_ROOT", "").strip()
    return Path(env) if env else Path.cwd()


def _page_cos(msg: str) -> bool:
    """Queue a Redis trigger to cos via the house triggers lib. True on success."""
    root = _cabinet_root()
    lib = root / "cabinet" / "scripts" / "lib" / "triggers.sh"
    if not lib.exists():
        print(f"FATAL triggers lib missing at {lib} — cannot page cos", file=sys.stderr)
        return False
    try:
        r = subprocess.run(
            ["/bin/bash", "-c", f'. "{lib}" && trigger_send cos "$1"', "_", msg],
            capture_output=True, text=True, cwd=str(root), timeout=30,
        )
    except Exception as e:  # subprocess/timeout — page failed, say so loudly
        print(f"FATAL trigger_send raised {type(e).__name__}: {e}", file=sys.stderr)
        return False
    if r.returncode != 0:
        print(f"FATAL trigger_send rc={r.returncode}: {(r.stderr or r.stdout).strip()[:300]}",
              file=sys.stderr)
        return False
    return True


def main() -> int:
    now = datetime.now(timezone.utc)

    if not HEALTH.exists():
        # Missing sensor output IS the staleness failure class — page it.
        msg = (f"BRAIN-QUALITY: sensor output missing ({HEALTH}) — brain-health "
               f"sensor down or never ran; {BRAIN_AUDIT_HINT}")
        paged = _page_cos(msg)
        print(f"BRAIN_HEALTH_ESCALATED missing_file paged={paged}")
        return 0 if paged else 1

    try:
        d = json.loads(HEALTH.read_text())
    except Exception as e:
        msg = (f"BRAIN-QUALITY: sensor output unreadable ({type(e).__name__}) — "
               f"{BRAIN_AUDIT_HINT}")
        paged = _page_cos(msg)
        print(f"BRAIN_HEALTH_ESCALATED unreadable paged={paged}")
        return 0 if paged else 1

    problems = []

    # Freshness floor (26h)
    age_h = None
    try:
        gen = datetime.fromisoformat(str(d.get("generated_ts", "")))
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=timezone.utc)
        age_h = (now - gen).total_seconds() / 3600.0
        if age_h > FRESHNESS_FLOOR_H:
            problems.append(f"stale sensor output age={age_h:.1f}h > {FRESHNESS_FLOOR_H}h floor")
    except Exception:
        problems.append("generated_ts missing/unparseable (treating as stale)")

    probes = d.get("probes") or {}
    integ = d.get("integrity") or {}
    p1 = probes.get("p_at_1")
    p3 = probes.get("p_at_3")
    leaks = probes.get("leaks")
    remints = integ.get("suppression_remints")
    ex_leaks = integ.get("excluded_leaks")

    if isinstance(p1, (int, float)) and p1 < P1_FLOOR:
        problems.append(f"p@1={p1} < {P1_FLOOR}")
    if isinstance(p3, (int, float)) and p3 < P3_FLOOR:
        problems.append(f"p@3={p3} < {P3_FLOOR}")
    if isinstance(leaks, int) and leaks > 0:
        problems.append(f"probe leaks={leaks} (excluded/parked prefixes served)")
    if isinstance(remints, int) and remints > 0:
        problems.append(f"suppression re-mints={remints}")
    if isinstance(ex_leaks, int) and ex_leaks > 0:
        problems.append(f"excluded-folder index leaks={ex_leaks}")

    flag_count = d.get("flag_count")
    summary = (f"p1={p1} p3={p3} leaks={leaks} remints={remints} "
               f"age_h={age_h:.1f}" if age_h is not None else
               f"p1={p1} p3={p3} leaks={leaks} remints={remints} age_h=?")

    if not problems:
        print(f"BRAIN_HEALTH_OK {summary} sensor_flags={flag_count}")
        return 0

    msg = ("BRAIN-QUALITY REGRESSION — " + "; ".join(problems) +
           f" (sensor_flags={flag_count}) — {BRAIN_AUDIT_HINT}")
    paged = _page_cos(msg)
    print(f"BRAIN_HEALTH_ESCALATED {summary} problems={len(problems)} paged={paged}")
    return 0 if paged else 1


if __name__ == "__main__":
    sys.exit(main())
