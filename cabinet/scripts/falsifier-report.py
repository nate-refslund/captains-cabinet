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
   cells_accumulating, cells_graduated, proactive_cards_7d,
   memory_ingestion, recall_drops, session_insert_failures,
   labels_7d, time_to_graduation_days, cost_7d, spend}

Growth metrics (§4.2, 2026-07-09 — "verdict throughput is the gap", the
egg-analysis verdict): labels_7d counts the week's raw label supply
({verdict: scored review verdicts, outcome_resolved: ok/failed outcome
rows}); time_to_graduation_days walks each GRADUATED cell's rows and
reports days from the cell's first stamped row to the earliest
row-granular time the graduation bar was met ({cells: {actor|lane|type:
days}, median}) — the exact evidence the cell-granularity question
(§4.3-3) is deferred on. Pure measurement, same read-only inputs.

Change-cost telemetry (§4.2, 2026-07-09): cost_7d sums the revived cost
ledger (cabinet:cost:tokens:daily:<date> hashes, live since 07-07 — fields
<officer>_input/_output/_cache_write/_cache_read/_cost_micro) over the
window and divides by the week's label supply: cost_micro_per_label is the
org's actual price of one unit of learning — the number EIG ordering needs.
null when unmeasurable (no readable day / zero labels), never a silent 0.

Durable spend history (2026-07-26, after the Captain removed every spend cap):
`spend` snapshots THAT DAY's figures — total + per-officer cost_micro from the
token hash, and per-lane cost_micro/calls/units from the SEPARATE lane hash
(cabinet:cost:lanes:daily:<date>). Both Redis ledgers expire after 8 days, so
without this snapshot nothing on the box remembers what a normal week costs and
no anomaly detector has a trailing baseline to stand on. Money is not the scarce
resource here (the work rides a subscription) — Captain ATTENTION is — so this
is history for a relative comparison, never an input to a dollar threshold.
`spend` is null when unmeasurable, and a null DAY is no evidence, never a zero.

Memory-ingestion liveness (P1c, 2026-07-07): the capture hooks feeding
cabinet_memory are best-effort exit-0 BY DESIGN (a hook must never fail the
officer tool call), which historically meant zero observability — 11/16
source classes had never landed a single row and nothing said so. Each daily
line now also carries:

  * memory_ingestion — compact per-source_type object
    {"<source_type>": {"n": <rowcount>, "latest": <max created_at, ISO-UTC>}}
    from ONE constant read-only SELECT over cabinet_memory. Connection string
    comes from NEON_CONNECTION_STRING (env) else cabinet/.env — the VALUE is
    used for psql argv only and is NEVER printed or logged. Unmeasurable
    (no psql / no conn string / query failed) degrades to null + one ALERT
    line, never a crash.
  * recall_drops — Redis GET cabinet:memory:recall_drops (0 when absent).
  * session_insert_failures — Redis GET cabinet:memory:session_insert_failures
    (incremented by the pre-compact.sh wrapper when a session_memories INSERT
    fails; 0 when absent).

WIRED source classes (a capture path exists in the live fleet:
captain_decision, telegram_dm, reflection, skill, experience_record,
session_memory) whose max(created_at) is older than 7 days — or which have
no rows at all — produce an "ALERT:" line on stdout, i.e. in this job's log
digest (~/.cabinet/logs/falsifier-daily.log). "ALERT" is deliberately NOT in
the outcome-watchdog's JOB_ERROR_MARKERS: a stale ingestion class is digest
material for the Captain's readout, not a fleet page.

Everything else is computed read-only from framework.fidelity.consequence
(read_ledger / compute_ratios), framework.fidelity.graduation.evaluate, and a
read-only GET of the actfirst_canary estate cap counters. The ONLY write is
the jsonl append (idempotent: today's line is never duplicated). No Redis
writes, no ledger writes, no secrets in output.

Run: python3.12 cabinet/scripts/falsifier-report.py
Scheduled by cabinet/launchd/com.cabinet.falsifier-daily.plist.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
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

# Source classes with a LIVE capture path in the fleet (P1a/b/c wiring,
# 2026-07-07): captain_decision + skill + reflection via
# post-file-write-memory.sh, telegram_dm via capture-captain-dm.sh /
# post-reply-memory.sh, experience_record via record-experience.sh,
# session_memory via pre-compact.sh. A wired class going silent for
# WINDOW_DAYS is a broken capture hook — exactly the failure the old
# best-effort-exit-0 posture made invisible.
WIRED_SOURCE_TYPES = ("captain_decision", "telegram_dm", "reflection",
                      "skill", "experience_record", "session_memory")

# Constant, read-only aggregate — no user input reaches this string, ever.
_INGESTION_SQL = (
    "SELECT source_type, count(*), "
    "to_char(max(created_at) AT TIME ZONE 'UTC', "
    "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
    "FROM cabinet_memory GROUP BY 1 ORDER BY 1"
)


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


def _counter(redis_get: Optional[Callable[[str], str]], key: str) -> int:
    """Read one non-negative Redis counter; any failure/absence reads 0."""
    if redis_get is None:
        return 0
    try:
        return int(redis_get(key) or 0)
    except Exception:
        return 0


def _cost_7d(now: dt.datetime,
             redis_hgetall: Optional[Callable[[str], Dict[str, str]]],
             labels_total: int) -> Dict[str, Any]:
    """Window cost from the daily cost-ledger hashes (read-only HGETALL).
    Sums every <officer>_{input,output,cost_micro} field per day; a failed /
    absent day contributes nothing. cost_micro_per_label = cost / the week's
    label supply — null when either side is unmeasurable (zero labels means
    "infinite price of learning", reported as null + the labels_7d field
    already says why, never a fake 0)."""
    totals = {"cost_micro": 0, "input_tokens": 0, "output_tokens": 0}
    days_measured = 0
    if redis_hgetall is not None:
        for d in range(WINDOW_DAYS):
            date = (now - dt.timedelta(days=d)).strftime("%Y-%m-%d")
            try:
                fields = redis_hgetall(f"cabinet:cost:tokens:daily:{date}") or {}
            except Exception:
                continue
            if not fields:
                continue
            days_measured += 1
            for name, val in fields.items():
                try:
                    v = int(val)
                except (TypeError, ValueError):
                    continue
                if name.endswith("_cost_micro"):
                    totals["cost_micro"] += v
                elif name.endswith("_input"):
                    totals["input_tokens"] += v
                elif name.endswith("_output"):
                    totals["output_tokens"] += v
    per_label = None
    if days_measured and labels_total > 0:
        per_label = round(totals["cost_micro"] / labels_total)
    return {**totals, "days_measured": days_measured,
            "cost_micro_per_label": per_label}


# Lane ledger field grammar (framework/cost/meter.py::record_lane): a lane rolls
# up as `<lane>_cost_micro` / `_calls` / `_units`, and each principal adds
# `<lane>__<principal>_cost_micro` / `__<principal>_calls`. The DOUBLE underscore
# is what separates the two: splitting on a single "_" would fold every
# per-principal row back into the lane total and double-count it.
_LANE_DIMS = ("cost_micro", "calls", "units")


def _parse_lane_fields(fields: Dict[str, str]) -> Dict[str, Dict[str, int]]:
    """Lane rollups from one lanes-hash, per-principal rows excluded.

    Returns {lane: {"cost_micro": int|absent, "calls": int, "units": int}}.
    ``cost_micro`` is ABSENT (not 0) for an unpriced lane — meter.py records no
    cost field when the vendor's price is unknown, and materialising a 0 here
    would turn "we don't know what this costs" into "this is free", the exact
    lie the meter exists to stop.
    """
    lanes: Dict[str, Dict[str, int]] = {}
    for name, raw in (fields or {}).items():
        for dim in _LANE_DIMS:
            suffix = "_" + dim
            if not name.endswith(suffix):
                continue
            lane = name[: -len(suffix)]
            if "__" in lane:
                break          # per-principal row — already inside the rollup
            try:
                val = int(raw)
            except (TypeError, ValueError):
                break          # unparseable value is not evidence of anything
            lanes.setdefault(lane, {})[dim] = val
            break
    return lanes


def _spend_block(now: dt.datetime,
                 redis_hgetall: Optional[Callable[[str], Dict[str, str]]],
                 ) -> Optional[Dict[str, Any]]:
    """THAT DAY's spend, snapshotted into the durable series.

    WHY THIS EXISTS: the Redis ledgers carry an 8-day TTL, so nothing on this
    box remembers what last month cost. Any "is this spend abnormal?" question
    needs a trailing baseline, and a baseline that evaporates weekly is not one.
    This block is that history — one row per day, appended by the same daily job
    that already computes ``cost_7d``, so it inherits its idempotence (a date is
    never written twice) and needs no new schedule or surface.

    Shape:
      {"date", "total_cost_micro": int|None, "officers": {prefix: micro},
       "lanes": {lane: {"cost_micro"?: int, "calls": int, "units": int}}|None}

    NULL, NEVER A FAKE 0 (the file's standing convention): the whole block is
    null when no reader was injected; ``total_cost_micro``/``officers`` are null
    when the officer hash yielded no fields, and ``lanes`` is null when the lane
    hash yielded none. Through this reader an empty ledger and an unreachable
    Redis look identical, so "no figures came back" is the honest label for
    both — and consumers must treat a null day as NO EVIDENCE rather than as a
    zero. Distinguishing the two is NOT this snapshot's job; it belongs to a
    ``meter-silent`` watchdog row that reads Redis directly and keeps HGETALL's
    None-vs-{} tri-state. That row is NOT IMPLEMENTED — withheld pending a
    two-model direction gate (2026-07-27 scope ruling) — so today nothing
    downstream distinguishes an empty ledger from an unreachable one. The
    tri-state is preserved here so that row can be written later without
    re-plumbing this reader.

    ``officers`` is keyed by the ledger PREFIX — ``<officer>`` or
    ``<officer>_<project>`` — because meter.py joins the two with the same "_"
    it uses before the dimension, so they cannot be split back apart here
    without guessing. The prefix is what the ledger actually says; guessing
    would invent an attribution.
    """
    date = now.strftime("%Y-%m-%d")
    if redis_hgetall is None:
        return None
    try:
        tok = redis_hgetall(f"cabinet:cost:tokens:daily:{date}") or {}
    except Exception:
        tok = {}
    try:
        lane_fields = redis_hgetall(f"cabinet:cost:lanes:daily:{date}") or {}
    except Exception:
        lane_fields = {}

    officers: Optional[Dict[str, int]] = None
    total: Optional[int] = None
    if tok:
        officers = {}
        total = 0
        for name, raw in tok.items():
            if not name.endswith("_cost_micro"):
                continue
            try:
                val = int(raw)
            except (TypeError, ValueError):
                continue
            officers[name[: -len("_cost_micro")]] = val
            total += val

    lanes = _parse_lane_fields(lane_fields) if lane_fields else None
    return {"date": date, "total_cost_micro": total, "officers": officers,
            "lanes": lanes}


def _default_redis_hgetall(key: str) -> Dict[str, str]:
    """HGETALL via redis-cli (read-only; launchd has no redis-py)."""
    import shutil as _sh
    cli = _sh.which("redis-cli") or "/opt/homebrew/bin/redis-cli"
    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    proc = subprocess.run([cli, "-h", host, "-p", port, "--raw",
                           "HGETALL", key],
                          capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        return {}
    lines = [l for l in proc.stdout.split("\n") if l != ""]
    return {lines[i]: lines[i + 1] for i in range(0, len(lines) - 1, 2)}


def _neon_conn() -> Optional[str]:
    """NEON_CONNECTION_STRING from the environment, else parsed line-by-line
    from cabinet/.env (launchd runs carry no login env). The returned VALUE
    goes into psql argv ONLY — never into any print/log/series output."""
    conn = os.environ.get("NEON_CONNECTION_STRING", "").strip()
    if conn:
        return conn
    try:
        for raw in (_REPO_ROOT / "cabinet" / ".env").read_text().splitlines():
            line = raw.strip()
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if line.startswith("NEON_CONNECTION_STRING="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return val or None
    except OSError:
        return None
    return None


def _psql_bin() -> Optional[str]:
    """psql from PATH, else the Homebrew install (launchd-minimal-PATH class
    of failure — same trap that killed retro-trigger)."""
    found = shutil.which("psql")
    if found:
        return found
    brew = "/opt/homebrew/bin/psql"
    return brew if os.path.exists(brew) else None


def read_memory_ingestion() -> Optional[Dict[str, Dict[str, Any]]]:
    """Per-source_type ingestion liveness from ONE constant read-only SELECT:
    {source_type: {"n": rowcount, "latest": ISO-UTC max(created_at)}}.

    None (json null in the series) when unmeasurable — psql or the connection
    string is unavailable, or the query failed. Degrade, never crash: the
    rest of the daily line must still append."""
    conn = _neon_conn()
    psql = _psql_bin()
    if not conn or not psql:
        return None
    try:
        proc = subprocess.run(
            [psql, conn, "-X", "-q", "-t", "-A", "-F", "\t",
             "-c", _INGESTION_SQL],
            capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out: Dict[str, Dict[str, Any]] = {}
    for line in proc.stdout.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 3 or not parts[0]:
            continue
        try:
            n = int(parts[1])
        except ValueError:
            continue
        out[parts[0]] = {"n": n, "latest": parts[2] or None}
    return out


def stale_wired_classes(ingestion: Optional[Dict[str, Dict[str, Any]]],
                        now: dt.datetime) -> List[str]:
    """WIRED classes whose latest row is older than WINDOW_DAYS — or which
    have never landed a row at all (both are a dead capture path). Empty when
    ingestion is unmeasurable (the caller emits its own UNMEASURABLE alert —
    absence of data must not read as 'all six classes broke today')."""
    if ingestion is None:
        return []
    floor = _iso(now - dt.timedelta(days=WINDOW_DAYS))
    stale: List[str] = []
    for st in WIRED_SOURCE_TYPES:
        row = ingestion.get(st)
        latest = str(row.get("latest") or "") if row else ""
        if not latest or latest < floor:      # ISO-UTC strings sort lexically
            stale.append(st)
    return stale


def _parse_ts(ts: str) -> Optional[dt.datetime]:
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _cell_rows(ledger: List[Dict[str, Any]], cell) -> List[Dict[str, Any]]:
    """This cell's stamped rows, ts-ordered (same keying as compute_ratios:
    actor 'kind:id', lane, action_type-with-sentinel)."""
    actor_id, lane, atype = cell
    rows = []
    for ev in ledger:
        if not isinstance(ev, dict):
            continue
        a = ev.get("actor") or {}
        if f"{a.get('kind')}:{a.get('id')}" != actor_id:
            continue
        if ev.get("lane") != lane:
            continue
        if (ev.get("action_type") or UNSTAMPED_ACTION_TYPE) != atype:
            continue
        rows.append(ev)
    return sorted(rows, key=lambda e: str(e.get("ts") or ""))


def _days_to_graduation(cell, ledger: List[Dict[str, Any]],
                        now: dt.datetime) -> Optional[float]:
    """Days from the cell's FIRST stamped row to the earliest row-granular
    time the graduation bar was met (prefix walk: evaluate with the ledger
    truncated at each row's ts). Row-granular = an upper bound when the
    recency clock matured between rows; in that case the current-clock
    evaluation closes the walk. None when the span is uncomputable."""
    from framework.fidelity import graduation
    rows = _cell_rows(ledger, cell)
    first = _parse_ts(rows[0].get("ts")) if rows else None
    if first is None:
        return None
    for ev in rows:
        t = _parse_ts(ev.get("ts"))
        if t is None:
            continue
        prefix = [e for e in ledger if isinstance(e, dict)
                  and str(e.get("ts") or "") <= str(ev.get("ts"))]
        if graduation.evaluate(cell, ledger=prefix,
                               now=t)["state"] == "graduated":
            return round((t - first).total_seconds() / 86400, 2)
    if graduation.evaluate(cell, ledger=ledger,
                           now=now)["state"] == "graduated":
        return round((now - first).total_seconds() / 86400, 2)
    return None


def compute_line(ledger: List[Dict[str, Any]], *,
                 now: Optional[dt.datetime] = None,
                 redis_get: Optional[Callable[[str], str]] = None,
                 ingestion: Optional[Dict[str, Dict[str, Any]]] = None,
                 redis_hgetall: Optional[
                     Callable[[str], Dict[str, str]]] = None,
                 ) -> Dict[str, Any]:
    """The pure daily falsifier line from a (deduped) consequence ledger.

    `ledger` / `now` / `redis_get` / `ingestion` are injected so tests run
    fully fixtured; production passes the live ledger, local Redis, and
    read_memory_ingestion()'s result (None → json null, honest unmeasured).
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
    grad_days: Dict[str, float] = {}
    for cell, ratios in compute_ratios(ledger=ledger).items():
        if cell[2] == UNSTAMPED_ACTION_TYPE or ratios.sample_count == 0:
            continue
        state = graduation.evaluate(cell, ledger=ledger, now=now)["state"]
        if state == "graduated":
            cells_graduated += 1
            days = _days_to_graduation(cell, ledger, now)
            if days is not None:
                grad_days["|".join(str(k) for k in cell)] = days
        else:
            cells_accumulating += 1

    # §4.2 growth metrics — the week's raw label supply (the learning core
    # runs on labels; the egg verdict named throughput THE gap) + how long
    # graduated cells actually took. Median over an empty set is None
    # (honest unmeasured, never a silent 0).
    labels_verdict_7d = sum(
        1 for ev in recent
        if (ev.get("review") or {}).get("verdict") in ("confirmed", "wrong"))
    outcome_resolved_7d = sum(
        1 for ev in recent
        if (ev.get("outcome") or {}).get("status") in ("ok", "failed"))
    spans = sorted(grad_days.values())
    median_days = None
    if spans:
        mid = len(spans) // 2
        median_days = (spans[mid] if len(spans) % 2
                       else round((spans[mid - 1] + spans[mid]) / 2, 2))

    return {
        "date": now.strftime("%Y-%m-%d"),
        "acted_7d": max(acted_ledger, acted_counter),
        "approved_7d": approved_7d,
        "reversal_rate_7d": reversal_rate,
        "stamped_rows_total": stamped_rows_total,
        "cells_accumulating": cells_accumulating,
        "cells_graduated": cells_graduated,
        "proactive_cards_7d": proactive_cards_7d,
        "labels_7d": {"verdict": labels_verdict_7d,
                      "outcome_resolved": outcome_resolved_7d},
        # §4.2 change-cost telemetry — what a unit of learning costs.
        "cost_7d": _cost_7d(now, redis_hgetall, labels_verdict_7d),
        # Durable per-day spend history (the Redis ledgers expire in 8 days;
        # this is the only trailing baseline an anomaly detector can stand on).
        "spend": _spend_block(now, redis_hgetall),
        "time_to_graduation_days": {"cells": grad_days,
                                    "median": median_days},
        # P1c memory-ingestion liveness (compact; null = unmeasurable, {} =
        # measured-and-empty — the two must never be conflated).
        "memory_ingestion": ingestion,
        "recall_drops": _counter(redis_get, "cabinet:memory:recall_drops"),
        "session_insert_failures": _counter(
            redis_get, "cabinet:memory:session_insert_failures"),
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
    ingestion = read_memory_ingestion()
    line = compute_line(read_ledger(), now=now,
                        redis_get=actfirst_canary._default_redis_get,
                        ingestion=ingestion,
                        redis_hgetall=_default_redis_hgetall)

    # Digest alerts (stdout → the job's log). Printed on EVERY run — including
    # the already-reported no-op path — so the daily digest never goes quiet
    # about a dead capture class just because the line already appended.
    alerts: List[str] = []
    if ingestion is None:
        alerts.append(
            "ALERT: memory-ingestion liveness UNMEASURABLE (psql or "
            "NEON_CONNECTION_STRING unavailable) — a falsifier you cannot "
            "measure is theater")
    else:
        for st in stale_wired_classes(ingestion, now):
            row = ingestion.get(st) or {}
            alerts.append(
                f"ALERT: memory ingestion stale for wired class '{st}' — "
                f"latest={row.get('latest') or 'never'} "
                f"(older than {WINDOW_DAYS}d)")

    if _already_reported(SERIES_PATH, line["date"]):
        print(f"[{_iso(now)}] falsifier-report: {line['date']} already reported — no-op")
        for a in alerts:
            print(a)
        return 0
    SERIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SERIES_PATH, "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
    print(f"[{_iso(now)}] falsifier-report: {json.dumps(line, sort_keys=True)}")
    for a in alerts:
        print(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
