#!/usr/bin/env python3
"""cabinet/scripts/meta-cognition/anomaly_report.py

The aggregation half of anomaly-scan.sh (Layer 2 DETECT). Reads the already-
emitted telemetry — tool-call JSONL logs, hook-fire JSONL, and Redis-sourced
reflection/cost/schedule values passed in via env — and prints a compact,
FACTUAL snapshot. It surfaces measured numbers (and the obvious mechanical
signals: stuck-loop repeats, overdue schedules) but does NOT decide what is
"anomalous" — the CoS applies the confidence floor in the retro.

Env (set by anomaly-scan.sh):
  ANOM_FILES        space-separated tool-call JSONL paths (window)
  ANOM_HOOK_FILES   space-separated hook-fire JSONL paths
  ANOM_REFLECTIONS  cabinet:reflections:count value (string)
  ANOM_SCHED_PAIRS  "<key>=<iso-ts>\n..." last-run stamps
  ANOM_COST_PAIRS   "<key>=<value>\n..." per-officer cost counters
  ANOM_JSON         "1" → emit JSON, else human-readable

Stdlib only. No network. No secrets emitted (cost = token counts).
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import sys


def _read_jsonl(paths: list[str]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        if not p:
            continue
        try:
            with open(p) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
        except OSError:
            continue
    return rows


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _age_hours(iso: str) -> float | None:
    iso = (iso or "").strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            t = dt.datetime.strptime(iso, fmt).replace(tzinfo=dt.timezone.utc)
            return (_now() - t).total_seconds() / 3600.0
        except Exception:
            continue
    return None


# Expected cadence (hours) per scheduled task, for the "overdue" signal. A task
# stamped longer ago than its cadence x slack is a probable silent-loop defect.
CADENCE_HOURS = {
    "briefing": 12, "retrospective": 48, "reflection": 12,
    "research": 4, "backlog": 12, "principle-harvest": 48,
}
OVERDUE_SLACK = 2.0  # only flag at 2x the cadence (avoids jitter)


def build_report() -> dict:
    files = (os.environ.get("ANOM_FILES") or "").split()
    hook_files = (os.environ.get("ANOM_HOOK_FILES") or "").split()
    rows = _read_jsonl(files)

    # 1) Per-officer tool-call volume.
    by_officer = collections.Counter(r.get("officer", "unknown") for r in rows)

    # 2) Stuck-loop signal: same (officer, tool, input-preview) repeated many
    #    times in a row is a probable spin. Count max identical-consecutive runs.
    stuck = []
    prev_key = None
    run = 0
    worst = {}
    for r in rows:
        key = (r.get("officer"), r.get("tool"),
               json.dumps(r.get("input"), sort_keys=True, default=str)[:160])
        if key == prev_key:
            run += 1
        else:
            run = 1
            prev_key = key
        if run > worst.get(key, 0):
            worst[key] = run
    for key, n in worst.items():
        if n >= 8:  # 8+ identical consecutive calls = likely spin
            stuck.append({"officer": key[0], "tool": key[1], "consecutive": n})

    # 3) Hook fires per hook file (storm = fires on ~everything; dead = never).
    hook_counts = {}
    for hf in hook_files:
        name = os.path.basename(hf).replace(".jsonl", "")
        hook_counts[name] = len(_read_jsonl([hf]))

    # 4) Reflections cadence (raw count — the CoS compares to work volume).
    reflections = (os.environ.get("ANOM_REFLECTIONS") or "").strip()

    # 5) Overdue scheduled tasks (probable silent loop).
    overdue = []
    for line in (os.environ.get("ANOM_SCHED_PAIRS") or "").splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        task = k.rsplit(":", 1)[-1]
        cad = CADENCE_HOURS.get(task)
        age = _age_hours(v)
        if cad and age is not None and age > cad * OVERDUE_SLACK:
            overdue.append({"task": k, "age_hours": round(age, 1), "cadence_hours": cad})

    # 6) Per-officer cost (token counts) — divergence is a CoS judgment vs volume.
    cost = {}
    for line in (os.environ.get("ANOM_COST_PAIRS") or "").splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        cost[k.rsplit(":", 1)[-1] if k.count(":") >= 3 else k] = v.strip()

    return {
        "window_files": files,
        "tool_calls_total": len(rows),
        "tool_calls_by_officer": dict(by_officer.most_common()),
        "stuck_loop_signals": stuck,
        "hook_fire_counts": hook_counts,
        "reflections_count": reflections,
        "overdue_scheduled_tasks": overdue,
        "per_officer_cost": cost,
        "note": (
            "FACTUAL snapshot only. Apply the CONFIDENCE FLOOR (anomaly-ledger.md): "
            "graduate a surprise to a meta-cognition proposal ONLY if it is a measured "
            "deviation AND implies a testable hypothesis or probable defect AND is "
            "actionable. Else it is a silent counter."
        ),
    }


def human(rep: dict) -> str:
    L = []
    L.append("=== Anomaly telemetry snapshot (Layer 2 DETECT) ===")
    L.append(f"tool-calls in window: {rep['tool_calls_total']} across {len(rep['window_files'])} day-file(s)")
    if rep["tool_calls_by_officer"]:
        L.append("by officer: " + ", ".join(f"{k}={v}" for k, v in rep["tool_calls_by_officer"].items()))
    if rep["stuck_loop_signals"]:
        L.append("STUCK-LOOP signals (>=8 identical consecutive calls — probable spin):")
        for s in rep["stuck_loop_signals"]:
            L.append(f"  - {s['officer']} · {s['tool']} · {s['consecutive']}x")
    else:
        L.append("stuck-loop signals: none")
    if rep["hook_fire_counts"]:
        L.append("hook fires: " + ", ".join(f"{k}={v}" for k, v in rep["hook_fire_counts"].items()))
    L.append(f"reflections:count = {rep['reflections_count'] or '(unset)'}")
    if rep["overdue_scheduled_tasks"]:
        L.append("OVERDUE scheduled tasks (>2x cadence — probable silent loop):")
        for o in rep["overdue_scheduled_tasks"]:
            L.append(f"  - {o['task']} : {o['age_hours']}h old (cadence {o['cadence_hours']}h)")
    else:
        L.append("overdue scheduled tasks: none")
    if rep["per_officer_cost"]:
        L.append("per-officer cost (token counts): " + ", ".join(f"{k}={v}" for k, v in rep["per_officer_cost"].items()))
    L.append("")
    L.append(rep["note"])
    return "\n".join(L)


def main() -> int:
    rep = build_report()
    if (os.environ.get("ANOM_JSON") or "") == "1":
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(human(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
