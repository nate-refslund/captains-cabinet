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


def _read_lines() -> list[dict[str, Any]]:
    path = _hist_path()
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


def _append_line(line: dict[str, Any]) -> None:
    path = _hist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.write(json.dumps(line, sort_keys=True) + "\n")
        fh.flush()
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _previous_date_breached(lines: list[dict[str, Any]], today: str) -> tuple[bool, int]:
    """(last distinct pre-today date ended in breach?, consecutive breach-date
    count ending at that date). Same-day re-runs never escalate — they ARE
    the self-heal attempt."""
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
        if by_date[date].get("status") in _BREACH_STATUSES:
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
    args = parser.parse_args(argv)
    return probe() if args.probe else run()


if __name__ == "__main__":
    sys.exit(main())
