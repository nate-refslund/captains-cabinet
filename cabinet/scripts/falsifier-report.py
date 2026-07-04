#!/usr/bin/env python3.12
"""falsifier-report.py — ONE line/day of falsifier telemetry (READ-ONLY).

Checkpoint 2026-07-04 condition 12: "Scheduled falsifier report line (stamped-
cell count, acted 7d, reversal rate, scout-ref count) so Day-14/30 checkpoints
are observed mechanically." Section 6's verdict was blunt: "a falsifier you
cannot measure is theater" — this script makes the Day-14 / Day-30 / Quarter
falsifiers (F1 stamped cells, F2a/F2b acted+reversal, F3a graduated cells)
measurable by appending one JSON line per day to
shared/interfaces/falsifier-series.jsonl:

  {date, acted_7d, approved_7d, reversal_rate_7d, stamped_rows_total,
   cells_accumulating, cells_graduated, proactive_cards_7d}

Everything is computed read-only from framework.fidelity.consequence
(read_ledger / compute_ratios), framework.fidelity.graduation.evaluate, and a
read-only GET of the actfirst_canary estate cap counters. The ONLY write is
the jsonl append (idempotent: today's line is never duplicated). No network,
no Redis writes, no ledger writes, no secrets.

Run: python3.12 cabinet/scripts/falsifier-report.py
Scheduled by cabinet/launchd/com.cabinet.falsifier-daily.plist.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.fidelity.consequence import (  # noqa: E402
    UNSTAMPED_ACTION_TYPE, compute_ratios, read_ledger)

SERIES_PATH = _REPO_ROOT / "shared" / "interfaces" / "falsifier-series.jsonl"
WINDOW_DAYS = 7


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _acted_rows(ledger: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unattended-act rows: proposal.required is False + a stamped action_type —
    the same RT-B1 marker semantics actfirst_canary._acted_rows/undo_rate use,
    inlined so the report stays importable without the canary module's Redis
    surface."""
    out: List[Dict[str, Any]] = []
    for ev in ledger:
        if not isinstance(ev, dict):
            continue
        if (ev.get("proposal") or {}).get("required") is not False:
            continue
        if not ev.get("action_type"):
            continue
        out.append(ev)
    return out


def _redis_acted_counts(now: dt.datetime,
                        redis_get: Callable[[str], str]) -> int:
    """Sum the actfirst estate day-counters over the window (read-only GET).

    These counters increment at act time BEFORE the (best-effort) post-act
    ledger emit, so they can exceed the ledger count when an emit was lost —
    the honest acted floor. Their 48h TTL means only ~2 days survive; the
    ledger remains the durable 7d record and the report takes the MAX of the
    two supplies. Any Redis error degrades to 0 (ledger-only), never a crash.
    """
    from framework.frontdoor import actfirst_canary
    total = 0
    for d in range(WINDOW_DAYS):
        date = (now - dt.timedelta(days=d)).strftime("%Y-%m-%d")
        try:
            total += int(redis_get(actfirst_canary.estate_key(date)) or 0)
        except Exception:
            return 0
    return total


def compute_line(ledger: List[Dict[str, Any]], *,
                 now: Optional[dt.datetime] = None,
                 redis_get: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
    """The pure daily falsifier line from a (deduped) consequence ledger.

    `ledger` / `now` / `redis_get` are injected so tests run fully fixtured;
    production passes nothing and reads the live ledger + local Redis.
    """
    now = now or _now()
    lo = _iso(now - dt.timedelta(days=WINDOW_DAYS))
    recent = [ev for ev in ledger if isinstance(ev, dict) and ev.get("ts", "") >= lo]

    acted = _acted_rows(recent)
    acted_ledger = len(acted)
    acted_counter = 0
    if redis_get is not None:
        acted_counter = _redis_acted_counts(now, redis_get)
    # `undone` mirrors actfirst_canary.undo_rate: review.verdict == "wrong"
    # (Captain undo OR machine-detected silent revert — the act did not stick).
    # None when there are no acts — an unmeasured rate, never a silent 0.0.
    undone = sum(1 for ev in acted
                 if (ev.get("review") or {}).get("verdict") == "wrong")
    reversal_rate = (undone / acted_ledger) if acted_ledger else None

    approved_7d = sum(1 for ev in recent
                      if (ev.get("proposal") or {}).get("decision") == "approved")
    proactive_cards_7d = sum(1 for ev in recent if ev.get("action") == "action-card")
    stamped_rows_total = sum(1 for ev in ledger
                             if isinstance(ev, dict) and ev.get("action_type"))

    # Cell states via the ONE graduation read (bar from authority-matrix.yml).
    # The __unstamped__ sentinel bucket is excluded from BOTH counts: it can
    # never graduate by design, so counting it as "accumulating" would report
    # progress the learning loop cannot cash (checkpoint: 0/2249 stamped rows
    # sat exactly there).
    from framework.fidelity import graduation
    cells_accumulating = cells_graduated = 0
    for cell, ratios in compute_ratios(ledger=ledger).items():
        if cell[2] == UNSTAMPED_ACTION_TYPE or ratios.sample_count == 0:
            continue
        state = graduation.evaluate(cell, ledger=ledger, now=now)["state"]
        if state == "graduated":
            cells_graduated += 1
        else:
            cells_accumulating += 1

    return {
        "date": now.strftime("%Y-%m-%d"),
        "acted_7d": max(acted_ledger, acted_counter),
        "approved_7d": approved_7d,
        "reversal_rate_7d": reversal_rate,
        "stamped_rows_total": stamped_rows_total,
        "cells_accumulating": cells_accumulating,
        "cells_graduated": cells_graduated,
        "proactive_cards_7d": proactive_cards_7d,
    }


def _already_reported(path: Path, date: str) -> bool:
    """True if a line for `date` is already in the series (idempotence — a
    re-fired launchd job or a manual run never doubles a day)."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    if json.loads(line).get("date") == date:
                        return True
                except json.JSONDecodeError:
                    continue           # a corrupt line never blocks the append
    except OSError:
        return False
    return False


def main() -> int:
    from framework.frontdoor import actfirst_canary
    now = _now()
    line = compute_line(read_ledger(), now=now,
                        redis_get=actfirst_canary._default_redis_get)
    if _already_reported(SERIES_PATH, line["date"]):
        print(f"[{_iso(now)}] falsifier-report: {line['date']} already reported — no-op")
        return 0
    SERIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SERIES_PATH, "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
    print(f"[{_iso(now)}] falsifier-report: {json.dumps(line, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
