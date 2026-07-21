#!/usr/bin/env python3.12
"""task-sync-drift-falsifier.py — nightly canonical↔mirror drift check.

The task-sync runner (cabinet/scripts/task_sync_runner.py, 900s services row)
CLAIMS the external tracker mirrors the Cabinet's canonical tasks. A sync
that silently stops mirroring is invisible until an operator trusts a stale
board — this falsifier samples both sides nightly and appends ONE verdict
line per run to the runtime ledger:

    cabinet/logs/task-sync-drift.jsonl        (gitignored via cabinet/logs/*)

Verdict statuses (the `status` field of each JSONL line):
  ok                      sampled rows agree (or nothing is linked yet)
  drift                   >=1 sampled task diverges canonical vs mirror  → exit 1
  error                   adapter/canonical infrastructure broke        → exit 1
  no-adapters-configured  active project is plugin-routed / has no tasks
                          block / no active project — HONEST no-op, exit 0
  adapter-not-implemented configured adapter is a skeleton (pull raises
                          NotImplementedError) — honest no-op, exit 0
  canonical-unreadable    no canonical source CONFIGURED (no psql binary or
                          no conn string, and no
                          TASK_SYNC_DRIFT_CANONICAL_JSON) — exit 0.
                          A CONFIGURED store whose read FAILS (psql exits
                          non-zero, times out, or emits garbage) is `error`
                          exit 1 instead — credential rot / a dead DB must
                          never park this watchdog green (2026-07-17 review)

Canonical side: TASK_SYNC_DRIFT_CANONICAL_JSON (a JSON list of
{external_id,title,status[,linked_kind]} rows — test seam + non-Postgres
deployments) else ONE CONSTANT read-only SELECT over `officer_tasks`
(json_agg — untrusted titles ride inside JSON string escaping, never TSV;
falsifier-report.py psql discipline: NEON_CONNECTION_STRING from env else
cabinet/.env, the VALUE goes into psql argv ONLY and is never printed).
Mirror side: the configured adapter's pull(). Sample: N rows
(TASK_SYNC_DRIFT_SAMPLE_N, default 10) rotated deterministically by date.

SECURITY: task titles are UNTRUSTED tracker text — they are compared, then
SCRUBBED (printable-only, length-capped) before entering the JSONL/exception
notes, never shell-interpolated (argv lists only), never formatted into SQL.

Escalation ladder (cabinet-doctor documents the same story):
  1st drift verdict   → doctor shows AMBER with the self-heal hint
                        (re-run `bash cabinet/cron/task-sync.sh`, then re-run
                        this falsifier — a fresh passing line clears AMBER).
  drift AGAIN on the  → self-heal failed: THIS script (never the read-only
  next distinct date    doctor) files ONE captain card through the attention
                        gateway (attention-submit.sh — gate dedups/quiet-
                        hours it) and stamps `escalated` on the line.

Modes:
  (default)  one sampling run, append verdict line, exit per status above
  --probe    NO DB / NO network / NO adapter import: inspect the latest
             ledger line for cabinet-doctor. Prints exactly one token line:
               NOFILE                      no ledger yet (nightly never ran)
               BADLINE                     latest line unparseable
               STALE age=<s> status=<s>    latest verdict older than
                                           TASK_SYNC_DRIFT_STALE_S (48h
                                           default — the nightly appends even
                                           in no-op mode, so stale = the cron
                                           itself is dead)
               NOSYNC status=<s> age=<s>   honest no-op class (see exits 0)
               OK age=<s> sampled=<n>
               DRIFT n=<consecutive-breach-dates> drift_count=<k> age=<s>
               ERROR age=<s>

Scheduled nightly 04:20 via cabinet/services.yml (task-sync-drift row).
Tests: cabinet/scripts/tests/test_task_sync_drift_falsifier.py.
"""
from __future__ import annotations

# Module-level imports stay STDLIB-ONLY: the doctor's --probe path must work
# on any box with no yaml/psql/framework importable. Adapter/runner imports
# happen lazily inside run().
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

def _repo_root() -> Path:
    """Resolved per call, not at import: tests + launchd both retarget via
    the CABINET_ROOT env var."""
    return Path(os.environ.get("CABINET_ROOT") or Path(__file__).resolve().parents[2])

#: adapter destination → officer_tasks.linked_kind (the schema's CHECK set).
#: LOOKUP CONTRACT (2026-07-17): an UNMAPPED destination only ever compares
#: kind-less canonical rows; if kind-bearing rows exist for an unmapped
#: destination the run is a LOUD `error` verdict (missing mapping = config
#: bug), NEVER a cross-tracker comparison — sampling github/linear-linked
#: rows against a new tracker's mirror would manufacture false presence
#: drift and a false captain card. New adapter ⇒ add its row here (runbook
#: §2, cabinet/runbooks/task-adapter-authoring.md).
_LINKED_KIND_BY_DESTINATION = {"github-issues": "github", "linear": "linear"}

#: officer_tasks.status (+blocked overlay) → CanonicalTask.status
_CANONICAL_STATUS = {"queue": "open", "wip": "in_progress", "done": "done",
                     "cancelled": "cancelled"}

_NOSYNC_STATUSES = {"no-adapters-configured", "adapter-not-implemented",
                    "canonical-unreadable"}
_BREACH_STATUSES = {"drift", "error"}

# ONE constant read-only SELECT (json_agg keeps untrusted titles inside JSON
# string escaping — a title with tabs/newlines cannot split rows). No task
# text is EVER interpolated into SQL: the statement below is a literal.
_CANONICAL_SQL = (
    "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
    "SELECT id, title, status, blocked, linked_kind, linked_id "
    "FROM officer_tasks "
    "WHERE linked_id IS NOT NULL AND linked_kind IS NOT NULL "
    "ORDER BY id LIMIT 500) t"
)


def _hist_path() -> Path:
    return _repo_root() / "cabinet" / "logs" / "task-sync-drift.jsonl"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"task-sync-drift: WARN {name}={raw!r} is not an int — using {default}",
              file=sys.stderr)
        return default


def _scrub(value: Any, cap: int = 80) -> str:
    """Untrusted tracker text → inert, printable, capped string for the
    ledger/log. Never raises."""
    text = str(value)
    clean = "".join(ch if ch.isprintable() else " " for ch in text)
    return clean[:cap] + ("…" if len(clean) > cap else "")


# ---------------------------------------------------------------------------
# canonical side
# ---------------------------------------------------------------------------


class CanonicalReadError(RuntimeError):
    """The canonical store is CONFIGURED but the read FAILED (psql non-zero
    exit, timeout, exec failure, unparseable output).

    run() maps this to status=error, exit 1: a broken canonical store must
    be LOUD (probe ERROR → doctor AMBER), never a silent canonical-unreadable
    no-op — a rotated credential or dead DB would otherwise park the drift
    watchdog green forever (2026-07-17 review). The message carries ONLY an
    inert reason (exception class name / psql exit code) — NEVER argv or
    stderr, both of which can hold the connection string."""


def _canonical_from_json_seam() -> list[dict[str, Any]] | None:
    seam = os.environ.get("TASK_SYNC_DRIFT_CANONICAL_JSON", "").strip()
    if not seam:
        return None
    rows = json.loads(Path(seam).read_text())
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("TASK_SYNC_DRIFT_CANONICAL_JSON must be a JSON list of objects")
    return rows


def _neon_conn() -> str | None:
    """NEON_CONNECTION_STRING from env, else parsed line-by-line from
    cabinet/.env. The returned VALUE goes into psql argv ONLY — never into
    any print/log/ledger output (falsifier-report.py discipline)."""
    conn = os.environ.get("NEON_CONNECTION_STRING", "").strip()
    if conn:
        return conn
    try:
        for raw in (_repo_root() / "cabinet" / ".env").read_text().splitlines():
            line = raw.strip()
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if line.startswith("NEON_CONNECTION_STRING="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return val or None
    except OSError:
        return None
    return None


def _canonical_from_postgres() -> list[dict[str, Any]] | None:
    """None = NOT CONFIGURED (no conn string or no psql binary) — the honest
    canonical-unreadable no-op. A configured-but-failing read raises
    CanonicalReadError instead: the two must never be conflated (a failure
    note claiming "no psql/conn string" while both exist would be false, and
    the silence would mute the watchdog)."""
    conn = _neon_conn()
    psql = shutil.which("psql") or (
        "/opt/homebrew/bin/psql" if os.path.exists("/opt/homebrew/bin/psql") else None)
    if not conn or not psql:
        return None
    try:
        result = subprocess.run(
            [psql, conn, "--no-psqlrc", "-X", "-v", "ON_ERROR_STOP=1", "-A", "-t",
             "-c", _CANONICAL_SQL],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        # type name ONLY — str(TimeoutExpired) embeds the argv, which holds
        # the connection string; OSError strerror can name filesystem paths.
        raise CanonicalReadError(
            f"psql invocation failed: {type(exc).__name__}") from None
    if result.returncode != 0:
        # exit code ONLY — psql stderr can echo the conn string/host/user
        raise CanonicalReadError(f"psql exited {result.returncode}")
    try:
        rows = json.loads(result.stdout.strip() or "[]")
    except json.JSONDecodeError:
        raise CanonicalReadError("psql output is not parseable JSON") from None
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise CanonicalReadError("psql output is not a JSON list of objects")
    out = []
    for r in rows:
        status = _CANONICAL_STATUS.get(str(r.get("status")), "open")
        if r.get("blocked") and status == "in_progress":
            status = "blocked"
        out.append({
            "external_id": str(r.get("linked_id")),
            "linked_kind": r.get("linked_kind"),
            "title": r.get("title") or "",
            "status": status,
        })
    return out


# ---------------------------------------------------------------------------
# verdict ledger
# ---------------------------------------------------------------------------


def _read_lines(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or _hist_path()
    if not path.exists():
        return []
    out = []
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"status": "_unparseable"}
        out.append(parsed)
    return out


def _append_line(line: dict[str, Any], path: Path | None = None) -> None:
    path = path or _hist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.write(json.dumps(line, sort_keys=True) + "\n")
        fh.flush()
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _previous_date_breached(lines: list[dict[str, Any]], today: str,
                            breach_statuses: set[str] | None = None) -> tuple[bool, int]:
    """(last distinct pre-today date ended in breach?, consecutive breach-date
    count ending at that date). Same-day re-runs never escalate — they ARE
    the self-heal attempt. `breach_statuses` defaults to the drift set; the
    COG-1 parity reader passes {"breach"} to reuse the SAME second-date ladder."""
    breach_statuses = breach_statuses or _BREACH_STATUSES
    by_date: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in lines:
        date = str(line.get("date", ""))
        if not date or date >= today:
            continue
        if date not in by_date:
            order.append(date)
        by_date[date] = line  # last line of that date wins
    consecutive = 0
    for date in reversed(order):
        if by_date[date].get("status") in breach_statuses:
            consecutive += 1
        else:
            break
    return consecutive > 0, consecutive


def _escalate(destination: str, drift_count: int, sampled: int, breach_dates: int) -> str:
    """File ONE captain card through the attention gateway. Fixed-shape text:
    counts + destination slug only — NEVER raw task text."""
    script = os.environ.get(
        "TASK_SYNC_DRIFT_ATTENTION_SUBMIT",
        str(_repo_root() / "cabinet" / "scripts" / "attention-submit.sh"),
    )
    situation = (
        f"Task-sync drift persisted across {breach_dates + 1} nightly verdicts on "
        f"{destination}: {drift_count} of {sampled} sampled tasks diverge between the "
        "canonical store and the external mirror. The self-heal (bash "
        "cabinet/cron/task-sync.sh, then re-run cabinet/scripts/task-sync-drift-"
        "falsifier.py) did not clear it. Ledger: cabinet/logs/task-sync-drift.jsonl"
    )
    try:
        result = subprocess.run(
            ["bash", script, "task-sync-drift", "Task-sync drift persisted", situation],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"task-sync-drift: WARN captain-card submit failed: {type(exc).__name__}",
              file=sys.stderr)
        return "attempt-failed"
    if result.returncode != 0:
        print("task-sync-drift: WARN captain-card submit exited "
              f"{result.returncode} (gate error — see attention gateway logs)",
              file=sys.stderr)
        return "attempt-failed"
    return "card-filed"


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


def _line_skeleton(status: str, destination: str, note: str = "") -> dict[str, Any]:
    now = _now()
    return {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": now.strftime("%Y-%m-%d"),
        "status": status,
        "destination": destination,
        "sampled": 0,
        "drift_count": 0,
        "drifts": [],
        "consecutive_breach_dates": 0,
        "escalated": None,
        "note": note,
    }


def run() -> int:
    # Lazy imports: probe mode must never need these.
    repo_src = str(Path(__file__).resolve().parents[2])
    if repo_src not in sys.path:
        sys.path.insert(0, repo_src)
    from cabinet.scripts.task_adapters.base import NoOpTaskAdapter, get_adapter

    try:
        from cabinet.scripts.task_sync_runner import _active_project_config
        project_config = _active_project_config()
    except (FileNotFoundError, ValueError):
        line = _line_skeleton("no-adapters-configured", "none",
                              note="no active project configured — nothing to sync")
        _append_line(line)
        print("task-sync-drift: no-adapters-configured (no active project) — honest no-op")
        return 0

    try:
        adapter = get_adapter(project_config)
    except ValueError as exc:
        line = _line_skeleton("error", "unknown", note=_scrub(exc, cap=200))
        _append_line(line)
        print(f"task-sync-drift: ERROR adapter selection failed: {_scrub(exc, cap=200)}",
              file=sys.stderr)
        return 1

    if isinstance(adapter, NoOpTaskAdapter):
        line = _line_skeleton("no-adapters-configured", adapter.destination,
                              note="active project is plugin-routed / has no tasks block")
        _append_line(line)
        print("task-sync-drift: no-adapters-configured — honest no-op (loud-degrade)")
        return 0

    destination = adapter.destination

    # canonical side
    try:
        canonical = _canonical_from_json_seam()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        line = _line_skeleton("error", destination,
                              note=f"canonical JSON seam unreadable: {_scrub(exc, cap=160)}")
        _append_line(line)
        print(f"task-sync-drift: ERROR {line['note']}", file=sys.stderr)
        return 1
    if canonical is None:
        try:
            canonical = _canonical_from_postgres()
        except CanonicalReadError as exc:
            # CONFIGURED but broken (rotated credential, dead DB, dropped
            # table, garbage output) — the exact silent-mirror-rot class this
            # organ exists to make loud. NEVER degrade to the no-op verdict.
            line = _line_skeleton(
                "error", destination,
                note=f"canonical store configured but unreadable: {_scrub(exc, cap=160)}")
            _append_line(line)
            print(f"task-sync-drift: ERROR {line['note']}", file=sys.stderr)
            return 1
    if canonical is None:
        line = _line_skeleton("canonical-unreadable", destination,
                              note="no canonical source configured "
                                   "(no psql/conn string, no JSON seam)")
        _append_line(line)
        print("task-sync-drift: canonical-unreadable — cannot measure, honest no-op")
        return 0

    # mirror side
    try:
        mirror_tasks = adapter.pull()
    except NotImplementedError:
        line = _line_skeleton("adapter-not-implemented", destination,
                              note="configured adapter is a skeleton — pull() not implemented")
        _append_line(line)
        print(f"task-sync-drift: adapter-not-implemented ({destination}) — honest no-op")
        return 0
    except Exception as exc:  # noqa: BLE001 — infra breakage is a real finding
        line = _line_skeleton("error", destination,
                              note=f"adapter pull failed: {type(exc).__name__}: "
                                   f"{_scrub(exc, cap=160)}")
        _append_line(line)
        print(f"task-sync-drift: ERROR {line['note']}", file=sys.stderr)
        return 1

    wanted_kind = _LINKED_KIND_BY_DESTINATION.get(destination)
    if wanted_kind is None:
        # Unmapped destination + kind-bearing canonical rows = config bug,
        # surfaced LOUD (see the map's lookup contract above). Kinds are
        # untrusted store text — scrubbed before they touch the note.
        kinded = sorted({_scrub(r.get("linked_kind"), 24)
                         for r in canonical if r.get("linked_kind")})
        if kinded:
            line = _line_skeleton(
                "error", destination,
                note=(f"destination '{destination}' has no _LINKED_KIND_BY_"
                      f"DESTINATION entry but canonical rows carry linked_kind="
                      f"{','.join(kinded)} — add the mapping (cabinet/runbooks/"
                      "task-adapter-authoring.md §2) so the falsifier compares "
                      "the right rows"))
            _append_line(line)
            print(f"task-sync-drift: ERROR {line['note']}", file=sys.stderr)
            return 1
    rows = [
        r for r in canonical
        if r.get("external_id")
        and (r.get("linked_kind") is None or r.get("linked_kind") == wanted_kind)
    ]
    rows.sort(key=lambda r: str(r["external_id"]))

    line = _line_skeleton("ok", destination)
    if not rows:
        line["note"] = "no linked canonical rows for this adapter — nothing to compare"
        _append_line(line)
        print(f"task-sync-drift: ok ({destination}) — no linked rows yet")
        return 0

    sample_n = max(1, _env_int("TASK_SYNC_DRIFT_SAMPLE_N", 10))
    offset = int(hashlib.sha256(line["date"].encode()).hexdigest(), 16) % len(rows)
    sample = [rows[(offset + i) % len(rows)] for i in range(min(sample_n, len(rows)))]

    mirror = {str(t.external_id): t for t in mirror_tasks if t.external_id}
    drifts: list[dict[str, str]] = []
    for row in sample:
        eid = str(row["external_id"])
        mirrored = mirror.get(eid)
        if mirrored is None:
            drifts.append({"external_id": _scrub(eid, 40), "field": "presence",
                           "canonical": "present", "mirror": "missing"})
            continue
        for fld in ("status", "title"):
            want, have = row.get(fld), getattr(mirrored, fld)
            if want is not None and str(want) != str(have):
                drifts.append({"external_id": _scrub(eid, 40), "field": fld,
                               "canonical": _scrub(want), "mirror": _scrub(have)})

    line["sampled"] = len(sample)
    line["drift_count"] = len(drifts)
    line["drifts"] = drifts[:20]

    if drifts:
        line["status"] = "drift"
        prior = _read_lines()
        prev_breached, consecutive = _previous_date_breached(prior, line["date"])
        line["consecutive_breach_dates"] = consecutive + 1
        if prev_breached:
            line["escalated"] = _escalate(
                destination, len(drifts), len(sample), consecutive)
        _append_line(line)
        print(
            f"task-sync-drift: DRIFT {len(drifts)}/{len(sample)} sampled tasks diverge "
            f"({destination}); consecutive breach dates={line['consecutive_breach_dates']}"
            + (f"; escalated={line['escalated']}" if line["escalated"] else
               "; self-heal: bash cabinet/cron/task-sync.sh, then re-run this falsifier"),
            file=sys.stderr,
        )
        return 1

    _append_line(line)
    print(f"task-sync-drift: ok — {len(sample)} sampled tasks agree ({destination})")
    return 0


# ===========================================================================
# COG-1 outbox parity (§8.3) — the falsifier gains the parity-log read
# ===========================================================================
# The relay (framework/outbox/relay.py) WRITES a per-cycle liveness sample to
# cabinet/logs/cog1-parity.jsonl each drain. This falsifier — already an ENABLED
# nightly fleet row — READS that log, applies the per-day freshness floor + the
# asymmetric effective-mapped predicate, and escalates two consecutive breach
# windows through its EXISTING second-date captain-card ladder. The relay only
# WRITES; the liveness chain terminates HERE (manifest-visible, doctor-probed).
#
# Vocabulary fence (§7): parity keys on OUTBOX ROWS + officer_task_history + the
# windowed legacy stream cabinet:tasks:events (read read-only via redis-cli, so
# all THREE §8.3 clauses evaluate at runtime), NEVER on the central outbox_*
# event ledger — so the three outbox_* writer families (relay proper,
# task_sync_runner telemetry now stamped kind='task_sync_telemetry', channels
# journal) are never double-counted here.

_COG1_ETL_ACTOR = "cpo-etl"          # 047/038 recognized suppression actor-role
_COG1_FLOOR = 1000                   # of 1,440 nominal cycles/day @60s (§8.3)
_COG1_NOMINAL = 1440
_COG1_FLOOR_LOOKBACK_DAYS = 45       # bound the window series (soak is ≤ ~2 wks)
_COG1_LEGACY_STREAM = "cabinet:tasks:events"   # the §8.3 legacy⊆outbox comparand:
                                     # the live authoritative exhaust my-tasks.sh
                                     # task_event_emit writes (lib/triggers.sh:519)
                                     # — NOT the relay's cabinet:tasks:events:shadow


def _cog1_parity_log_path() -> Path:
    """The relay-written per-cycle SAMPLE log (input). Env override for the
    harness; else the cabinet/logs/* default (gitignored, no .gitignore edit)."""
    override = os.environ.get("CABINET_COG1_PARITY_LOG", "").strip()
    return Path(override) if override else (
        _repo_root() / "cabinet" / "logs" / "cog1-parity.jsonl")


def _cog1_verdict_path() -> Path:
    """The falsifier-written daily VERDICT ledger (output / escalation history —
    drives the two-consecutive ladder, exactly as task-sync-drift.jsonl does)."""
    return _repo_root() / "cabinet" / "logs" / "cog1-parity-verdict.jsonl"


def _as_date(value: Any) -> dt.date:
    if value is None:
        return _now().date()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def cog1_parity_predicate(*, outbox_rows: list[dict[str, Any]],
                          history_transitions: list[dict[str, Any]],
                          legacy_stream: list[dict[str, Any]] | None = None
                          ) -> dict[str, Any]:
    """Asymmetric, EFFECTIVE-mapped parity predicate (§8.3). PURE — takes the
    three data planes and returns {status, breaches, counts}. It NEVER consumes
    the central outbox_* event ledger (no double-count across the three writer
    families).

    Clauses (all keyed on the EFFECTIVE transition (task_id, eff_old, eff_new)):
      - legacy ⊆ outbox — ASYMMETRIC: dashboard-origin transitions are
        outbox-only by design, so outbox ⊄ legacy is NOT a breach. Skipped when
        the legacy comparand is unavailable (shadow-only soak).
      - coverage — every non-'cpo-etl' history transition has EXACTLY one outbox
        row (catches BOTH writer stacks: my-tasks.sh AND the dashboard lib).
      - no phantom — no outbox row lacks a history row.
    'cpo-etl' history transitions are EXCLUDED (the recognized 047/038
    suppression actor writes history but no outbox row, by design).

    The relay's effective mapping is REUSED (ONE mapping, §6.1): matching raw
    columns against the legacy 'blocked' overlay would false-breach every block.
    """
    from collections import Counter
    # Lazy import keeps the module top stdlib-only for the --probe path.
    from framework.outbox.relay import (effective_old_status,
                                        effective_new_status)

    def okey(r: dict) -> tuple:
        return (int(r["task_id"]),
                effective_old_status(r.get("old_status"), r.get("old_blocked")),
                effective_new_status(r.get("new_status"), r.get("new_blocked")))

    def hkey(h: dict) -> tuple:
        return (int(h["task_id"]),
                effective_old_status(h.get("from_status"), h.get("from_blocked")),
                effective_new_status(h.get("to_status"), h.get("to_blocked")))

    def lkey(e: dict) -> tuple:
        # legacy stream carries ALREADY-effective status (my-tasks.sh rewrites
        # OLD_STATUS/new_status to 'blocked' on block); INSERT-arm NULL -> ''.
        return (int(e["task_id"]), e.get("old_status") or "", e["new_status"])

    outbox_ctr = Counter(okey(r) for r in outbox_rows)
    hist_ctr = Counter(hkey(h) for h in history_transitions
                       if h.get("actor") != _COG1_ETL_ACTOR)   # suppression
    breaches: list[tuple[str, int]] = []

    missing = hist_ctr - outbox_ctr   # history transitions with no outbox row
    phantom = outbox_ctr - hist_ctr   # outbox rows with no history row
    if missing:
        breaches.append(("history_not_covered", sum(missing.values())))
    if phantom:
        breaches.append(("phantom_outbox", sum(phantom.values())))

    legacy_count = 0
    if legacy_stream is not None:
        legacy_ctr = Counter(lkey(e) for e in legacy_stream)
        legacy_count = sum(legacy_ctr.values())
        uncovered = legacy_ctr - outbox_ctr        # legacy ⊄ outbox (loss)
        if uncovered:
            breaches.append(("legacy_not_covered", sum(uncovered.values())))

    return {
        "status": "breach" if breaches else "ok",
        "breaches": breaches,
        "counts": {"outbox": sum(outbox_ctr.values()),
                   "history_effective": sum(hist_ctr.values()),
                   "legacy": legacy_count},
    }


def cog1_freshness_floor(sample_lines: list[dict[str, Any]], *,
                         floor: int = _COG1_FLOOR, today: Any = None
                         ) -> dict[str, Any]:
    """Per-day liveness floor over the relay's per-cycle SAMPLE log (§8.3). Each
    line is one relay cycle; a COMPLETE UTC day (strictly before `today`) with
    fewer than `floor` cycles — OR an ABSENT day inside the observed range — is
    a BREACH window, so a dead/never-armed relay cannot pass the soak vacuously.
    The current partial day is NOT judged. Returns {per_date, windows:
    [(date,count,breach)], latest_window, latest_breach}."""
    today_d = _as_date(today)
    counts: dict[str, int] = {}
    for line in sample_lines:
        date = str(line.get("ts") or "")[:10]
        if len(date) == 10:
            counts[date] = counts.get(date, 0) + 1
    present_complete = sorted(d for d in counts if _as_date(d) < today_d)
    windows: list[tuple[str, int, bool]] = []
    if present_complete:
        start = max(_as_date(present_complete[0]),
                    today_d - dt.timedelta(days=_COG1_FLOOR_LOOKBACK_DAYS))
        end = today_d - dt.timedelta(days=1)   # yesterday = latest complete day
        day = start
        while day <= end:
            key = day.isoformat()
            count = counts.get(key, 0)
            windows.append((key, count, count < floor))
            day += dt.timedelta(days=1)
    latest = windows[-1] if windows else None
    return {"per_date": counts, "windows": windows, "latest_window": latest,
            "latest_breach": bool(latest and latest[2])}


def _cog1_window_floor_ms(outbox_rows: list[dict[str, Any]]) -> int | None:
    """Epoch-ms of the EARLIEST outbox occurred_at — the moment 047's capture
    trigger went live, i.e. the instant the pilot window opens (§8.3). None = no
    outbox rows captured yet (nothing to ground; predicate is trivially ok). The
    stamp is an ISO-8601 string from row_to_json (UTC, +00:00 offset)."""
    earliest: float | None = None
    for r in outbox_rows:
        raw = r.get("occurred_at")
        if not raw:
            continue
        try:
            ts = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        epoch = ts.timestamp()
        if earliest is None or epoch < earliest:
            earliest = epoch
    return int(earliest * 1000) if earliest is not None else None


def _parse_legacy_entries(raw: str) -> list[dict[str, Any]]:
    """Parse `redis-cli --json XRANGE` output → [{task_id, old_status,
    new_status}]. Tolerant per row (task-events-watch.py:127 _parse_entries
    stance — a malformed / task_id-less row is DROPPED, never raises). The legacy
    stream carries ALREADY-EFFECTIVE status (lib/triggers.sh:507), matching the
    predicate's lkey; only the three fields the predicate keys on are kept, so
    untrusted stream text never travels further."""
    try:
        entries = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for row in entries:
        try:
            flat = row[1]
        except (IndexError, TypeError, KeyError):
            continue
        if isinstance(flat, dict):
            fields = {str(k): str(v) for k, v in flat.items()}
        elif isinstance(flat, list):
            fields = {str(flat[i]): str(flat[i + 1])
                      for i in range(0, len(flat) - 1, 2)}
        else:
            continue
        tid = fields.get("task_id", "")
        if not tid.isdigit() or "new_status" not in fields:
            continue
        out.append({"task_id": int(tid),
                    "old_status": fields.get("old_status", ""),
                    "new_status": fields["new_status"]})
    return out


def _cog1_legacy_stream_from_redis(start_id: str = "-") -> list[dict[str, Any]]:
    """Read the legacy authoritative stream cabinet:tasks:events read-only from
    `start_id` — a bare epoch-ms bounds the §8.3 window SERVER-SIDE (XRANGE from
    the ms is inclusive), so pre-047 events are never fetched. Uses a redis-cli
    argv subprocess (the house read idiom, task-events-watch.py:112 — no shell,
    fixed argv, REDIS_HOST/REDIS_PORT). Raises CanonicalReadError on a transport
    failure carrying ONLY the exit code / exception class name (never argv or
    stderr — the _neon_conn discipline), so the caller can degrade the clause to
    'skipped' without suppressing the DB-grounded coverage/phantom clauses."""
    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = os.environ.get("REDIS_PORT", "6379")
    redis_cli = shutil.which("redis-cli")
    if not redis_cli:
        raise CanonicalReadError("redis-cli not found")
    try:
        result = subprocess.run(
            [redis_cli, "-h", host, "-p", str(port), "--json",
             "XRANGE", _COG1_LEGACY_STREAM, start_id, "+"],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CanonicalReadError(
            f"legacy stream read failed: {type(exc).__name__}") from None
    if result.returncode != 0:
        raise CanonicalReadError(f"redis-cli XRANGE exited {result.returncode}")
    return _parse_legacy_entries(result.stdout)


def _cog1_window_from_postgres() -> tuple[list, list, list | None] | None:
    """Read the predicate's THREE planes for the §8.3 runtime check (the
    _canonical_from_postgres discipline: conn string in argv ONLY; json_agg keeps
    untrusted text inside JSON escaping). None = not configured (predicate
    skipped; the floor still runs).

    §8.3 WINDOW — all three planes share ONE bound so the comparison is sound on
    a REAL work store, which carries pre-047 history AND a pre-047 legacy stream;
    an unwindowed read would count every pre-pilot transition a loss and breach
    every night. The window OPENS at the earliest outbox occurred_at (the instant
    047's capture trigger went live): outbox IS the window (it defines the
    floor), so it is read whole; officer_task_history is filtered to
    transition_at >= that floor (shared DB clock — coverage/phantom stay exact);
    the legacy stream is XRANGE'd from the same floor in ms.

    The legacy plane is READ HERE (the conformance fix) so the asymmetric
    legacy⊆outbox loss clause — the M1 instrument — actually evaluates at runtime
    and not only under the JSON seam. It degrades to None on a redis blip (clause
    skipped, coverage/phantom/freshness unaffected — the freshness floor is the
    independent liveness gate).

    S0 (2026-07-20): the production work store is PostgreSQL 17.10; psql speaks
    any-major wire, so whatever psql resolves reads the major-17 store fine."""
    conn = _neon_conn()
    psql = shutil.which("psql") or (
        "/opt/homebrew/bin/psql" if os.path.exists("/opt/homebrew/bin/psql") else None)
    if not conn or not psql:
        return None

    def _read(sql: str) -> list[dict[str, Any]]:
        result = subprocess.run(
            [psql, conn, "--no-psqlrc", "-X", "-v", "ON_ERROR_STOP=1", "-A", "-t",
             "-c", sql], capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise CanonicalReadError(f"psql exited {result.returncode}")
        try:
            rows = json.loads(result.stdout.strip() or "[]")
        except json.JSONDecodeError:
            raise CanonicalReadError("psql output is not parseable JSON") from None
        if not isinstance(rows, list):
            raise CanonicalReadError("psql output is not a JSON list")
        return rows

    # outbox: read whole (it defines the window floor); occurred_at drives the
    # floor for the two ground-truth planes.
    outbox = _read(
        "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
        "SELECT task_id, old_status, new_status, old_blocked, new_blocked, actor, "
        "occurred_at "
        "FROM officer_tasks_outbox ORDER BY id) t")
    # coverage/no-phantom ground truth, WINDOWED to the pilot span so pre-047
    # history (no outbox row by construction) is never counted (§8.3).
    history = _read(
        "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
        "SELECT task_id, from_status, to_status, from_blocked, to_blocked, actor "
        "FROM officer_task_history "
        "WHERE transition_at >= (SELECT MIN(occurred_at) FROM officer_tasks_outbox) "
        "ORDER BY id) t")
    floor_ms = _cog1_window_floor_ms(outbox)
    legacy: list[dict[str, Any]] | None = None
    if floor_ms is not None:
        try:
            legacy = _cog1_legacy_stream_from_redis(str(floor_ms))
        except CanonicalReadError:
            legacy = None   # redis blip → skip the belt-and-suspenders clause;
            #                 coverage/phantom/freshness are unaffected
    return outbox, history, legacy


def _cog1_window_data() -> tuple[list, list, list | None] | None:
    """Resolve the predicate's data planes: the COG1_PARITY_DATA_JSON seam
    (tests / non-Postgres) else the read-only Postgres read. None = unavailable
    (predicate skipped)."""
    seam = os.environ.get("COG1_PARITY_DATA_JSON", "").strip()
    if seam:
        data = json.loads(Path(seam).read_text())
        return (list(data.get("outbox_rows") or []),
                list(data.get("history_transitions") or []),
                data.get("legacy_stream"))
    return _cog1_window_from_postgres()


def _escalate_cog1(reason: str, breach_dates: int) -> str:
    """File ONE captain card for a persistent COG-1 outbox-parity breach through
    the SAME attention gateway the drift escalation uses (second-date
    semantics). Fixed-shape text — counts + reason slug only, never raw task
    text; the gateway dedups/quiet-hours it."""
    script = os.environ.get(
        "TASK_SYNC_DRIFT_ATTENTION_SUBMIT",
        str(_repo_root() / "cabinet" / "scripts" / "attention-submit.sh"))
    situation = (
        f"COG-1 outbox parity breached across {breach_dates + 1} consecutive "
        f"nightly windows ({reason}). Either the outbox relay stopped draining "
        "(freshness floor: fewer than 1,000 of ~1,440 daily cycles / an absent "
        "day) or the co-committed outbox rows diverge from officer_task_history "
        "(coverage/phantom). The mirror is NOT safe to cut over. Ledger: "
        "cabinet/logs/cog1-parity.jsonl + cog1-parity-verdict.jsonl")
    try:
        result = subprocess.run(
            ["bash", script, "cog1-outbox-parity",
             "COG-1 outbox parity breach persisted", situation],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"cog1-parity: WARN captain-card submit failed: {type(exc).__name__}",
              file=sys.stderr)
        return "attempt-failed"
    if result.returncode != 0:
        print("cog1-parity: WARN captain-card submit exited "
              f"{result.returncode} (gate error — see attention gateway logs)",
              file=sys.stderr)
        return "attempt-failed"
    return "card-filed"


def run_cog1_parity(*, today: Any = None) -> int:
    """Nightly COG-1 outbox-parity read (§8.3). Applies the freshness floor to
    the relay's sample log + the asymmetric predicate to the current window,
    appends ONE verdict line, and escalates two consecutive breach windows via
    the existing captain-card ladder. Absent sample log = the pilot's relay
    never armed here = honest no-op (exit 0)."""
    parity_log = _cog1_parity_log_path()
    if not parity_log.exists():
        return 0  # no pilot on this box — nothing to read (not a breach)

    today_d = _as_date(today)
    today_s = today_d.isoformat()

    samples: list[dict[str, Any]] = []
    for raw in parity_log.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            samples.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    floor = cog1_freshness_floor(samples, today=today_d)
    floor_breach = floor["latest_breach"]

    predicate: dict[str, Any] | None = None
    predicate_breach = False
    data_note = ""
    try:
        window = _cog1_window_data()
    except (OSError, ValueError, json.JSONDecodeError, CanonicalReadError) as exc:
        window = None
        data_note = f"parity data unreadable: {_scrub(exc, 120)}"
    if window is not None:
        outbox_rows, history, legacy = window
        predicate = cog1_parity_predicate(
            outbox_rows=outbox_rows, history_transitions=history,
            legacy_stream=legacy)
        predicate_breach = predicate["status"] == "breach"

    breach = bool(floor_breach or predicate_breach)
    latest = floor["latest_window"]
    reasons: list[str] = []
    if floor_breach:
        reasons.append(f"freshness-floor({latest[1]}<{_COG1_FLOOR} on {latest[0]})")
    if predicate_breach:
        reasons.append("predicate:" + ",".join(
            f"{name}={n}" for name, n in predicate["breaches"]))
    if reasons:
        note = "; ".join(reasons)
    elif predicate is None:
        note = "floor met; predicate skipped"
    else:
        note = "floor met; predicate ok"
    if data_note:
        note = f"{note}; {data_note}"

    line = {
        "ts": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": today_s,
        "status": "breach" if breach else "ok",
        "floor_breach": bool(floor_breach),
        "predicate_breach": bool(predicate_breach),
        "window_date": latest[0] if latest else None,
        "window_samples": latest[1] if latest else None,
        "predicate_skipped": predicate is None,
        "note": note[:400],
        "escalated": None,
    }

    prior = _read_lines(_cog1_verdict_path())
    prev_breached, consecutive = _previous_date_breached(
        prior, today_s, breach_statuses={"breach"})
    if breach and prev_breached:
        line["escalated"] = _escalate_cog1("; ".join(reasons) or "breach",
                                           consecutive)
    _append_line(line, _cog1_verdict_path())

    if breach:
        print(f"cog1-parity: BREACH ({note})"
              + (f"; escalated={line['escalated']}" if line["escalated"]
                 else "; self-heal window"), file=sys.stderr)
        return 1
    print(f"cog1-parity: ok ({note})")
    return 0


# ---------------------------------------------------------------------------
# --probe (cabinet-doctor): pure file inspection
# ---------------------------------------------------------------------------


def probe() -> int:
    path = _hist_path()
    if not path.exists():
        print("NOFILE")
        return 0
    last: dict[str, Any] | None = None
    for raw in path.read_text().splitlines():
        if raw.strip():
            try:
                last = json.loads(raw)
            except json.JSONDecodeError:
                last = None
    if not isinstance(last, dict):
        print("BADLINE")
        return 0
    try:
        ts = dt.datetime.strptime(str(last.get("ts")), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc)
    except ValueError:
        print("BADLINE")
        return 0
    age = int((_now() - ts).total_seconds())
    status = str(last.get("status"))
    stale_s = _env_int("TASK_SYNC_DRIFT_STALE_S", 172800)
    if age > stale_s:
        print(f"STALE age={age}s status={status}")
        return 0
    if status in _NOSYNC_STATUSES:
        print(f"NOSYNC status={status} age={age}s")
        return 0
    if status == "ok":
        print(f"OK age={age}s sampled={last.get('sampled', 0)}")
        return 0
    if status == "drift":
        print(f"DRIFT n={last.get('consecutive_breach_dates', 1)} "
              f"drift_count={last.get('drift_count', 0)} age={age}s")
        return 0
    if status == "error":
        print(f"ERROR age={age}s")
        return 0
    print("BADLINE")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task-sync drift falsifier")
    parser.add_argument("--probe", action="store_true",
                        help="inspect the latest verdict line for cabinet-doctor "
                             "(no DB, no network, no adapter imports)")
    parser.add_argument("--cog1-parity", action="store_true",
                        help="COG-1 §8.3: read the outbox parity log, apply the "
                             "freshness floor + predicate, escalate on two "
                             "consecutive breach windows")
    args = parser.parse_args(argv)
    if args.probe:
        return probe()
    if args.cog1_parity:
        return run_cog1_parity()
    # Default nightly invocation runs BOTH the tracker-drift check AND the COG-1
    # outbox-parity read (§8.3 — the falsifier "gains the parity-log read" on its
    # existing enabled row; no services.yml edit). The COG-1 read is a clean
    # no-op when the parity log is absent (the pilot's relay never armed here).
    rc_drift = run()
    rc_cog1 = run_cog1_parity()
    return rc_drift or rc_cog1


if __name__ == "__main__":
    sys.exit(main())
