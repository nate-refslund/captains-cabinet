#!/usr/bin/env python3.12
"""cog2-parity-falsifier.py — cortex shadow-parity FALSIFIER (§8 sim 6).

COG-2 UNIT 4. Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md
§8 sim 6 (shadow parity), §7.1 (import ban), §7.4 (scope fence). The shadow
world-model (the cortex projection) CLAIMS to answer "what do we believe about
subject X, as of now" faithfully. A projection that silently stops matching the
authoritative record is invisible until an operator trusts a stale belief — so
this falsifier samples the AUTHORITATIVE side each cycle, derives ground truth
with the DOMAIN's own reader, compares it to the projection's as-of answer, and
appends ONE verdict line per run to the runtime ledger:

    cabinet/logs/cog2-parity.jsonl        (gitignored via cabinet/logs/*)

THREE anti-tautology pins make the check falsifiable rather than self-affirming:

  1. AUTHORITATIVE-frame sampling (C-F16). The sample frame is drawn from the
     AUTHORITATIVE side — distinct task_ids from the officer_tasks outbox, and
     identity chains from the consequence ledger's OWN reader — NEVER from the
     projection's belief store. A subject deleted from the store but still live
     on the authoritative side must therefore be sampled and found unanswerable
     (a breach). Sampling the store instead structurally cannot see that drift.

  2. DOMAIN-reader ground truth (C-F17). Ground truth is computed by the domain
     (a direct outbox read / the consequence reader), INDEPENDENTLY of the
     projection. Reading ground truth back through the projection's own answer
     is f(x)==f(x) — it can never disagree with a mistranslation.

  3. IMPORT BAN (C-F17). This file imports NO cortex module at all: the
     projection is queried as an EXTERNAL black box (an operator-configured
     command, COG2_PARITY_CORTEX_CMD), so the falsifier can neither reuse nor
     re-derive the projection's fold in-process. An AST import-graph walk +
     grep backstop (test_cog2_parity.py) fail the suite if a cortex import ever
     appears here.

Verdict statuses (the `status` field of each JSONL line):
  ok            sampled authoritative subjects all match the projection
  breach        >=1 sampled subject disagrees / is unanswerable, OR a per-day
                sample floor is missed                                  → exit 1
  error         a CONFIGURED reader broke (psql/cortex-cmd non-zero / garbage)
                — credential rot must never park the watchdog green      → exit 1
  unconfigured  no parity source on this box (no seam, no outbox conn, no cortex
                reader) — an HONEST no-op                                → exit 0

Sticky re-sampling (C-F18): a breaching subject is force-included every cycle
until it answers cleanly, so a breach that happens not to be naturally sampled
next cycle cannot read ok and reset the escalation counter. Second-consecutive
breach DATE files ONE captain card through the attention gateway (the same
second-date ladder the task-sync-drift falsifier uses). Same-day re-runs are the
self-heal attempt and never escalate.

SECURITY: subject/answer text is UNTRUSTED store text — compared, then SCRUBBED
(printable-only, length-capped) before it enters the JSONL/log, never shell-
interpolated (argv lists only), never formatted into SQL (one constant json_agg
SELECT). A Postgres connection string rides in psql argv ONLY and never appears
in any print/log/ledger/exception.

Modes:
  (default)  one sampling run, append verdict line, exit per status above
  --probe    NO DB / NO network / NO framework import: inspect the latest ledger
             line for cabinet-doctor. Prints exactly one token line:
               NOFILE / BADLINE / STALE age=.. status=.. / NOSYNC status=.. /
               OK age=.. sampled=.. / BREACH n=.. breaches=.. age=.. / ERROR ..

Tests: cabinet/scripts/tests/test_cog2_parity.py.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

# Module top stays STDLIB-ONLY: the --probe path must work on any box with no
# framework/psql importable, and the import ban forbids reaching the projection
# in-process. The domain consequence reader is a LAZY in-function import.
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Zero-evidence sentinel: the projection has no belief for a sampled subject.
# Never a real answer — real answers canonicalize to JSON text.
_UNANSWERED = "\x00unanswered"


def _repo_root() -> Path:
    """Resolved per call, not at import: tests + launchd both retarget via
    CABINET_ROOT."""
    return Path(os.environ.get("CABINET_ROOT") or Path(__file__).resolve().parents[2])


def _hist_path() -> Path:
    return _repo_root() / "cabinet" / "logs" / "cog2-parity.jsonl"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"cog2-parity: WARN {name}={raw!r} is not an int — using {default}",
              file=sys.stderr)
        return default


def _scrub(value: Any, cap: int = 80) -> str:
    """Untrusted store text → inert, printable, capped string. Never raises."""
    clean = "".join(ch if ch.isprintable() else " " for ch in str(value))
    return clean[:cap] + ("…" if len(clean) > cap else "")


def _show(value: Any) -> str:
    return "" if value is None else str(value)


class _ConfiguredButFailing(RuntimeError):
    """A CONFIGURED reader (psql / cortex command) broke — a loud `error`
    verdict, never a silent green. The message carries ONLY an inert reason
    (exception class name / exit code) — never argv or stderr, which can echo a
    connection string."""


# ---------------------------------------------------------------------------
# the pure parity core
# ---------------------------------------------------------------------------

def _canon(value: Any) -> str:
    """An answer → its canonical comparison string. None / the explicit
    "unknown" status → the zero-evidence sentinel (the projection cannot
    answer)."""
    if value is None or value == "unknown":
        return _UNANSWERED
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _rotate_sample(universe: list[str], n: int, date: str) -> list[str]:
    """Deterministic date-rotated sample of up to n subjects from a sorted
    universe — the same sha256(date) offset idiom the drift falsifier uses, so a
    cycle's frame is reproducible and rotates coverage across days."""
    if not universe:
        return []
    offset = int(hashlib.sha256(str(date).encode()).hexdigest(), 16) % len(universe)
    k = min(n, len(universe))
    return [universe[(offset + i) % len(universe)] for i in range(k)]


def parity_scan(*, authoritative: dict[str, Any], cortex: dict[str, Any],
                date: str, prior_open_breaches: Any = (), sample_n: int | None = None,
                floor: int | None = None, sampling_frame: str = "authoritative",
                ground_truth_source: str = "domain",
                resample: str = "sticky") -> dict[str, Any]:
    """Compare the projection's answers to domain ground truth for a rotated
    sample of AUTHORITATIVE subjects. PURE — takes the two resolved data planes
    (authoritative = subject → domain ground-truth answer; cortex = subject →
    the projection's as-of answer) and returns the verdict dict. No I/O.

    Documented MUTANT SEAMS (kwargs; NEVER production):
      sampling_frame="store"       draw the frame from the projection's beliefs,
                                   not the authoritative side — structurally
                                   cannot sample a store-deleted subject (C-F16).
      ground_truth_source="adapter" read ground truth THROUGH the projection's
                                   own answer — f(x)==f(x), blind to a
                                   mistranslation (C-F17).
      resample="memoryless"        drop the sticky force-include — a breach not
                                   naturally re-sampled reads ok and games the
                                   second-consecutive counter (C-F18).
    """
    sample_n = _env_int("COG2_PARITY_SAMPLE_N", 10) if sample_n is None else sample_n
    floor = _env_int("COG2_PARITY_SAMPLE_FLOOR", 3) if floor is None else floor

    # 1. SAMPLE FRAME — the authoritative side (the anti-tautology pin). The
    # "store" mutant draws from the projection instead and misses deletions.
    universe = sorted(cortex.keys()) if sampling_frame == "store" else sorted(
        authoritative.keys())
    sampled = list(_rotate_sample(universe, sample_n, date))

    # 2. STICKY RE-SAMPLING — force-include prior open breaches still present on
    # the frame, so a flapping breach cannot hide by being unsampled (C-F18).
    if resample != "memoryless":
        present = set(universe)
        for subject in prior_open_breaches or ():
            if subject in present and subject not in sampled:
                sampled.append(subject)

    # 3. COMPARE domain ground truth to the projection's answer.
    breaches: list[dict[str, str]] = []
    open_breaches: list[str] = []
    for subject in sampled:
        proj = _canon(cortex.get(subject))
        truth = _canon(cortex.get(subject)) if ground_truth_source == "adapter" \
            else _canon(authoritative.get(subject))
        if truth != proj:
            reason = "unanswered" if proj == _UNANSWERED else "mismatch"
            breaches.append({"subject": _scrub(subject, 80), "reason": reason,
                             "domain": _scrub(_show(authoritative.get(subject))),
                             "cortex": _scrub(_show(cortex.get(subject)))})
            if subject in authoritative:
                open_breaches.append(subject)

    effective_floor = min(floor, len(universe))
    floor_ok = len(sampled) >= effective_floor
    status = "breach" if (breaches or not floor_ok) else "ok"
    return {"status": status, "sampled": len(sampled),
            "sampled_subjects": sampled, "frame_size": len(universe),
            "breaches": breaches, "open_breaches": sorted(set(open_breaches)),
            "floor": floor, "floor_ok": floor_ok}


def _as_date(value: Any) -> dt.date:
    if value is None:
        return _now().date()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def per_day_floor(lines: list[dict[str, Any]], *, today: Any,
                  floor: int) -> dict[str, Any]:
    """Per-day sample floor over the verdict ledger (task e). Each COMPLETE UTC
    day strictly before `today` must carry >= floor sampled subjects; a day with
    fewer — INCLUDING an ABSENT day inside the observed range (the falsifier
    never ran / the projection went dark) — is a BREACH window, so a dead
    falsifier cannot pass the soak vacuously. The current partial day is not
    judged."""
    today_d = _as_date(today)
    counts: dict[str, int] = {}
    for line in lines:
        date = str(line.get("date", ""))
        if len(date) == 10 and _as_date(date) < today_d:
            counts[date] = counts.get(date, 0) + int(line.get("sampled", 0) or 0)
    present = sorted(counts)
    windows: list[tuple[str, int, bool]] = []
    if present:
        start = _as_date(present[0])
        end = today_d - dt.timedelta(days=1)
        day = start
        while day <= end:
            key = day.isoformat()
            count = counts.get(key, 0)
            windows.append((key, count, count < floor))
            day += dt.timedelta(days=1)
    breach = any(w[2] for w in windows)
    return {"windows": windows, "breach": breach,
            "latest_breach": windows[-1][2] if windows else False}


# ---------------------------------------------------------------------------
# verdict ledger
# ---------------------------------------------------------------------------

def _read_lines(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or _hist_path()
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            out.append({"status": "_unparseable"})
    return out


def _append_line(line: dict[str, Any], path: Path | None = None) -> None:
    path = path or _hist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.write(json.dumps(line, sort_keys=True) + "\n")
        fh.flush()
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _latest_open_breaches(lines: list[dict[str, Any]]) -> list[str]:
    """The open-breach carry from the most recent verdict line — the sticky set
    the next cycle force-includes."""
    for line in reversed(lines):
        if isinstance(line.get("open_breaches"), list):
            return [str(s) for s in line["open_breaches"]]
    return []


def _previous_date_breached(lines: list[dict[str, Any]], today: str
                            ) -> tuple[bool, int]:
    """(last distinct pre-today date ended in breach?, trailing-consecutive
    breach-date count). Same-day re-runs never escalate — they ARE the self-heal
    attempt; an intervening ok DATE resets the ladder."""
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
        if by_date[date].get("status") == "breach":
            consecutive += 1
        else:
            break
    return consecutive > 0, consecutive


def _escalate(verdict: dict[str, Any], consecutive: int) -> str:
    """File ONE captain card through the attention gateway. FIXED-SHAPE text —
    counts + reason slug only, NEVER raw subject/answer text (the gateway
    dedups/quiet-hours it)."""
    script = os.environ.get(
        "COG2_PARITY_ATTENTION_SUBMIT",
        str(_repo_root() / "cabinet" / "scripts" / "attention-submit.sh"))
    situation = (
        f"Cortex shadow parity breached across {consecutive + 1} consecutive "
        f"verdicts: {len(verdict['breaches'])} of {verdict['sampled']} sampled "
        "authoritative subjects diverge from the shadow projection's as-of answer "
        "(or the projection cannot answer a live subject). The shadow world-model "
        "is NOT safe to trust for reads. Ledger: cabinet/logs/cog2-parity.jsonl")
    try:
        result = subprocess.run(
            ["bash", script, "cog2-shadow-parity",
             "Cortex shadow parity breach persisted", situation],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"cog2-parity: WARN captain-card submit failed: {type(exc).__name__}",
              file=sys.stderr)
        return "attempt-failed"
    if result.returncode != 0:
        print("cog2-parity: WARN captain-card submit exited "
              f"{result.returncode} (gate error — see attention gateway logs)",
              file=sys.stderr)
        return "attempt-failed"
    return "card-filed"


# ---------------------------------------------------------------------------
# authoritative side (domain reader) + projection reader
# ---------------------------------------------------------------------------

def _neon_conn() -> str | None:
    """NEON_CONNECTION_STRING from env, else parsed from cabinet/.env. The
    VALUE goes into psql argv ONLY — never into any print/log/ledger."""
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


def _which_psql() -> str | None:
    for cand in (shutil.which("psql"),
                 "/opt/homebrew/opt/postgresql@17/bin/psql",
                 "/opt/homebrew/bin/psql"):
        if cand and os.path.exists(cand):
            return cand
    return None


def _psql_json(psql: str, conn: str, sql: str) -> list[dict[str, Any]]:
    """Run one constant json_agg SELECT read-only. conn in argv ONLY; failures
    raise with the exit code / class name only (never argv or stderr)."""
    try:
        result = subprocess.run(
            [psql, conn, "--no-psqlrc", "-X", "-v", "ON_ERROR_STOP=1", "-A", "-t",
             "-c", sql], capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise _ConfiguredButFailing(
            f"psql invocation failed: {type(exc).__name__}") from None
    if result.returncode != 0:
        raise _ConfiguredButFailing(f"psql exited {result.returncode}")
    try:
        rows = json.loads(result.stdout.strip() or "[]")
    except json.JSONDecodeError:
        raise _ConfiguredButFailing("psql output is not parseable JSON") from None
    if not isinstance(rows, list):
        raise _ConfiguredButFailing("psql output is not a JSON list")
    return rows


def _effective_status(status: Any, blocked: Any) -> str:
    """Domain effective status — computed by the domain, INDEPENDENTLY of the
    projection's fold. A blocked in-progress task reads 'blocked'."""
    if blocked and str(status) == "wip":
        return "blocked"
    return str(status)


# ONE constant read-only SELECT — the latest outbox row per task_id (json_agg
# keeps untrusted titles inside JSON string escaping; no text is interpolated).
_OUTBOX_SQL = (
    "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
    "SELECT DISTINCT ON (task_id) task_id, new_status, new_blocked "
    "FROM officer_tasks_outbox ORDER BY task_id, id DESC) t")


def _authoritative_from_consequence() -> dict[str, Any]:
    """Identity chains from the consequence ledger's OWN reader (the domain's
    reader — NOT a projection adapter). Lazy import so the module top stays
    stdlib-only and the --probe path never touches framework. Best-effort:
    absent event dir / any read hiccup → {} (the outbox frame still stands)."""
    if not os.environ.get("CABINET_EVENT_LOG_DIR"):
        return {}
    repo = str(_repo_root())
    if repo not in sys.path:
        sys.path.insert(0, repo)
    try:
        from framework.fidelity import consequence  # lazy, domain reader only
        rows = consequence.read_ledger()
    except Exception:  # noqa: BLE001 — a ledger hiccup must not crash the frame
        return {}
    out: dict[str, Any] = {}
    for ev in rows:
        if not isinstance(ev, dict):
            continue
        subject = "cid:" + "/".join(str(ev.get(k, "")) for k in
                                    ("actor", "fuel_type", "consequence_id"))
        out[subject] = {"decision": ev.get("decision") or ev.get("kind")}
    return out


def _authoritative_from_postgres() -> dict[str, Any] | None:
    """The authoritative sample frame + ground truth: distinct task_ids from the
    outbox (latest effective status) UNION the consequence identity chains. None
    = not configured (no conn/psql) — the honest unconfigured no-op."""
    conn = _neon_conn()
    psql = _which_psql()
    if not conn or not psql:
        return None
    out: dict[str, Any] = {}
    for row in _psql_json(psql, conn, _OUTBOX_SQL):
        tid = row.get("task_id")
        if tid is None:
            continue
        out[str(tid)] = {"status": _effective_status(
            row.get("new_status"), row.get("new_blocked"))}
    out.update(_authoritative_from_consequence())
    return out


def _cortex_from_cmd() -> dict[str, Any] | None:
    """The projection's answers, read as an EXTERNAL black box: an operator-
    configured command (COG2_PARITY_CORTEX_CMD) emitting a JSON object
    {subject: answer}. NO in-process projection import (the import ban). Unset =
    None (no reader on this box); configured-but-failing raises (loud error)."""
    cmd = os.environ.get("COG2_PARITY_CORTEX_CMD", "").strip()
    if not cmd:
        return None
    try:
        result = subprocess.run(shlex.split(cmd), capture_output=True,
                                text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise _ConfiguredButFailing(
            f"cortex reader failed: {type(exc).__name__}") from None
    if result.returncode != 0:
        raise _ConfiguredButFailing(f"cortex reader exited {result.returncode}")
    try:
        data = json.loads(result.stdout.strip() or "{}")
    except json.JSONDecodeError:
        raise _ConfiguredButFailing("cortex reader output is not JSON") from None
    if not isinstance(data, dict):
        raise _ConfiguredButFailing("cortex reader output is not a JSON object")
    return data


def _resolve_data() -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Resolve (authoritative, cortex). The COG2_PARITY_DATA_JSON seam (tests /
    non-Postgres) else the read-only prod readers. None = unconfigured (honest
    no-op); _ConfiguredButFailing propagates as a loud error."""
    seam = os.environ.get("COG2_PARITY_DATA_JSON", "").strip()
    if seam:
        data = json.loads(Path(seam).read_text())
        if not isinstance(data, dict) or "authoritative" not in data:
            raise _ConfiguredButFailing(
                "COG2_PARITY_DATA_JSON must be a JSON object with an "
                "'authoritative' map")
        return (dict(data.get("authoritative") or {}), dict(data.get("cortex") or {}))
    authoritative = _authoritative_from_postgres()
    if authoritative is None:
        return None                      # no authoritative source → unconfigured
    cortex = _cortex_from_cmd()
    if cortex is None:
        return None                      # no projection reader → cannot measure
    return (authoritative, cortex)


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _skeleton(status: str, date: str, note: str = "") -> dict[str, Any]:
    return {
        "ts": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": date,
        "status": status,
        "sampled": 0,
        "frame_size": 0,
        "breaches": [],
        "open_breaches": [],
        "floor_ok": True,
        "day_floor_breach": False,
        "consecutive_breach_dates": 0,
        "escalated": None,
        "note": note,
    }


def run(*, today: Any = None, sample_n: int | None = None,
        resample: str = "sticky", sampling_frame: str = "authoritative",
        ground_truth_source: str = "domain") -> int:
    """One parity cycle: resolve data, sample the authoritative frame, compare to
    the projection, append a verdict line, escalate a second-consecutive breach
    date. `resample`/`sampling_frame`/`ground_truth_source` carry the documented
    mutant seams through to parity_scan (never production)."""
    today_s = _as_date(today).isoformat()

    try:
        data = _resolve_data()
    except _ConfiguredButFailing as exc:
        line = _skeleton("error", today_s, note=_scrub(str(exc), 160))
        _append_line(line)
        print(f"cog2-parity: ERROR {line['note']}", file=sys.stderr)
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        line = _skeleton("error", today_s,
                         note=f"parity data unreadable: {_scrub(exc, 140)}")
        _append_line(line)
        print(f"cog2-parity: ERROR {line['note']}", file=sys.stderr)
        return 1

    if data is None:
        line = _skeleton("unconfigured", today_s,
                         note="no parity source configured (no seam, no outbox "
                              "conn, no cortex reader) — honest no-op")
        _append_line(line)
        print("cog2-parity: unconfigured — nothing to measure, honest no-op")
        return 0

    authoritative, cortex = data
    prior = _read_lines()
    floor = _env_int("COG2_PARITY_SAMPLE_FLOOR", 3)

    verdict = parity_scan(
        authoritative=authoritative, cortex=cortex, date=today_s,
        prior_open_breaches=_latest_open_breaches(prior), sample_n=sample_n,
        floor=floor, sampling_frame=sampling_frame,
        ground_truth_source=ground_truth_source, resample=resample)
    day_floor = per_day_floor(prior, today=today_s, floor=floor)

    breach = verdict["status"] == "breach" or day_floor["breach"]
    line = _skeleton("breach" if breach else "ok", today_s)
    line.update(sampled=verdict["sampled"], frame_size=verdict["frame_size"],
                breaches=verdict["breaches"][:20],
                open_breaches=verdict["open_breaches"],
                floor_ok=verdict["floor_ok"], day_floor_breach=day_floor["breach"])

    if breach:
        prev_breached, consecutive = _previous_date_breached(prior, today_s)
        line["consecutive_breach_dates"] = consecutive + 1
        if prev_breached:
            line["escalated"] = _escalate(verdict, consecutive)

    _append_line(line)

    if breach:
        detail = (f"{len(verdict['breaches'])}/{verdict['sampled']} diverge"
                  if verdict["breaches"] else
                  f"sample floor missed (day_floor={day_floor['breach']}, "
                  f"cycle_floor_ok={verdict['floor_ok']})")
        print(f"cog2-parity: BREACH {detail}; consecutive breach dates="
              f"{line['consecutive_breach_dates']}"
              + (f"; escalated={line['escalated']}" if line["escalated"] else
                 "; self-heal window (rebuild the projection, then re-run)"),
              file=sys.stderr)
        return 1
    print(f"cog2-parity: ok — {verdict['sampled']} sampled subjects agree")
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
    stale_s = _env_int("COG2_PARITY_STALE_S", 172800)
    if age > stale_s:
        print(f"STALE age={age}s status={status}")
        return 0
    if status == "unconfigured":
        print(f"NOSYNC status={status} age={age}s")
        return 0
    if status == "ok":
        print(f"OK age={age}s sampled={last.get('sampled', 0)}")
        return 0
    if status == "breach":
        print(f"BREACH n={last.get('consecutive_breach_dates', 1)} "
              f"breaches={len(last.get('breaches', []))} age={age}s")
        return 0
    if status == "error":
        print(f"ERROR age={age}s")
        return 0
    print("BADLINE")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cortex shadow-parity falsifier (§8 sim 6)")
    parser.add_argument("--probe", action="store_true",
                        help="inspect the latest verdict line for cabinet-doctor "
                             "(no DB, no network, no framework import)")
    args = parser.parse_args(argv)
    if args.probe:
        return probe()
    return run()


if __name__ == "__main__":
    sys.exit(main())
