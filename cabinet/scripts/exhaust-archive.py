"""exhaust-archive.py — ORG-SENSES-2: the trigger-stream exhaust becomes memory.

The org's nervous-system traffic (``cabinet:triggers:*`` Redis Streams — every
officer wake, mission push, killswitch/veto verb) lives only inside Redis
retention: XTRIM/XDEL and a Redis rebuild erase the record of WHO was told to
do WHAT and WHEN. This organ makes that plane durable + retrievable:

  1. ARCHIVE (append-only, verbatim): every new entry on every
     ``cabinet:triggers:*`` stream is appended as one JSON line to
     ``$CABINET_EXHAUST_ARCHIVE_DIR/triggers/<stream>.jsonl``
     (default ``~/.cabinet/archive/triggers/``). Fields are copied VERBATIM —
     killswitch/veto verbs keep their ``captain_verified`` provenance intact
     (the ledger gate). The archive is never rewritten, only appended.
  2. LAND in org memory: each archived entry is queued onto
     ``cabinet:memory:embed_queue`` (the EXISTING memory-worker seam, same as
     transcript-digest) as ``source_type=trigger-archive`` with a stable
     ``source_id=trig:<stream>:<redis-id>`` — re-runs upsert, never duplicate.
     Embedded content is secret-scrubbed names-not-values (the archive JSONL
     keeps the verbatim row; only the EMBEDDED text is scrubbed — memory rows
     feed prompts, the archive feeds audits).
  3. STATE: last archived redis-id per stream in
     ``~/.cabinet/state/exhaust-archive.json`` (atomic tmp+rename), so each
     sweep reads only the delta (XRANGE exclusive-from).

Chair-DM plane (the other ORG-SENSES-2 half): INBOUND Captain DMs already
land durably in cabinet_memory at capture time (hooks/capture-captain-dm.sh,
source_type=telegram_dm) — cabinet_memory is SQLite, not Redis-retention-
bound, so aged DMs are already queryable and need no second archive.
OUTBOUND Chair turns are journaled to the append-only feed JSONL with
content HASH only (privacy-by-construction) — archiving their text would be
NEW capture, which this row explicitly is not ("durable landing + retrieval,
not new capture"). So this organ owns exactly the trigger plane.

Report-only side effects: archive appends + embed-queue XADDs + its own
state/heartbeat. Never XDELs, never XTRIMs, never ACKs — reading a stream
with XRANGE consumes nothing (officers' consumer groups are untouched).

Usage: python3.12 cabinet/scripts/exhaust-archive.py [--dry-run] [--json]
Scheduled via cabinet/services.yml row ``exhaust-archive`` (daily 04:40
local, after the 04:10 transcript-digest).

sunset: retire if the trigger plane moves off Redis Streams, or if a
first-class event-sourcing store supersedes per-stream JSONL archives.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE_TYPE = "trigger-archive"
STREAM_PATTERN = "cabinet:triggers:*"
MAX_EMBEDS_PER_SWEEP = 500     # embed-queue flood guard (archive is uncapped)
MAX_EMBED_CHARS = 2000

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Names-not-values scrub for EMBEDDED content only (subset of the
# transcript-digest firewall — trigger messages occasionally echo env/errors).
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|"
                r"CONNECTION_STRING|API)[A-Z0-9_]*)\s*[=:]\s*\S+"),
     r"\1=<redacted>"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 <redacted>"),
    (re.compile(r"([a-z][a-z0-9+.-]*://)[^/@\s]+@"), r"\1<redacted>@"),
    (re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{16,}\b"), "<redacted>"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "<redacted>"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "<redacted>"),
    (re.compile(r"\bxox[a-z]-[A-Za-z0-9-]{10,}\b"), "<redacted>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<redacted>"),
]


def scrub(text: str) -> str:
    for rx, repl in _SECRET_PATTERNS:
        text = rx.sub(repl, text)
    return text


# ---------------------------------------------------------------------------
# Paths / state
# ---------------------------------------------------------------------------

def archive_dir() -> Path:
    env = os.environ.get("CABINET_EXHAUST_ARCHIVE_DIR")
    base = Path(env).expanduser() if env else Path.home() / ".cabinet" / "archive"
    return base / "triggers"


def state_path() -> Path:
    env = os.environ.get("CABINET_EXHAUST_STATE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cabinet" / "state" / "exhaust-archive.json"


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    os.replace(tmp, path)


def _safe_name(stream: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", stream)


# ---------------------------------------------------------------------------
# Redis (read-only verbs only: SCAN + XRANGE) — injectable for tests
# ---------------------------------------------------------------------------

def _redis_cli(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    try:
        r = subprocess.run(["redis-cli", "-h", host, "-p", port, *args],
                           capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001 — archival must never crash on transport
        return ""


def list_streams() -> list[str]:
    out = _redis_cli("--scan", "--pattern", STREAM_PATTERN)
    return sorted({ln.strip() for ln in out.splitlines() if ln.strip()})


def read_entries(stream: str, after_id: str | None) -> list[tuple[str, dict]]:
    """New entries (id, fields) strictly after ``after_id`` (None = all).
    XRANGE with an exclusive start consumes nothing — consumer groups and
    pending lists are untouched."""
    start = f"({after_id}" if after_id else "-"
    raw = _redis_cli("--json", "XRANGE", stream, start, "+")
    try:
        rows = json.loads(raw)
    except (ValueError, TypeError):
        return []
    out: list[tuple[str, dict]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        try:
            rid, flat = row[0], row[1]
            if isinstance(flat, dict):
                fields = {str(k): str(v) for k, v in flat.items()}
            else:
                fields = {str(flat[i]): str(flat[i + 1])
                          for i in range(0, len(flat) - 1, 2)}
            out.append((str(rid), fields))
        except (IndexError, TypeError, KeyError):
            continue
    return out


# ---------------------------------------------------------------------------
# Landing seams
# ---------------------------------------------------------------------------

def append_archive(stream: str, rid: str, fields: dict, adir: Path) -> None:
    """One verbatim JSON line, append-only (provenance like captain_verified
    survives untouched)."""
    adir.mkdir(parents=True, exist_ok=True)
    line = {"stream": stream, "id": rid, "fields": fields,
            "archived_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")}
    with open(adir / f"{_safe_name(stream)}.jsonl", "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")


def queue_embed(stream: str, rid: str, fields: dict,
                repo_root: Path = _REPO_ROOT) -> bool:
    """Land the entry in org memory through the existing memory_queue_embed
    seam (args pass as ARGV — never interpolated; injection-safe)."""
    officer = stream.split(":", 2)[2] if stream.count(":") >= 2 else ""
    content = scrub(json.dumps(fields, sort_keys=True))[:MAX_EMBED_CHARS]
    ts_ms = rid.split("-", 1)[0]
    try:
        source_ts = datetime.fromtimestamp(
            int(ts_ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError, OverflowError):
        source_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    metadata = {"stream": stream, "redis_id": rid,
                "sunset": "supersede-on-rearchive; review organ if its "
                          "services.yml row sits disabled >90d"}
    cmd = [
        "bash", "-c",
        'source "$0/cabinet/scripts/lib/memory.sh" && '
        'memory_queue_embed "$1" "$2" "$3" "$4" "$5" "$6" "$7"',
        str(repo_root),
        SOURCE_TYPE,
        f"trig:{stream}:{rid}",
        officer,
        "",  # sender
        content,
        json.dumps(metadata),
        source_ts,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def run_sweep(dry_run: bool = False,
              streams_fn=list_streams,
              entries_fn=read_entries,
              embed_fn=queue_embed) -> dict:
    adir = archive_dir()
    spath = state_path()
    state = load_state(spath)
    last_ids: dict = state.get("last_ids") or {}
    summary = {"streams": 0, "archived": 0, "embedded": 0, "embed_failures": 0,
               "dry_run": dry_run}
    embed_budget = MAX_EMBEDS_PER_SWEEP
    for stream in streams_fn():
        summary["streams"] += 1
        entries = entries_fn(stream, last_ids.get(stream))
        for rid, fields in entries:
            if dry_run:
                summary["archived"] += 1
                continue
            append_archive(stream, rid, fields, adir)
            summary["archived"] += 1
            # State advances on ARCHIVE (the durability floor). An embed
            # failure is logged, not retried via state rewind — the archive
            # line already holds the row; re-embedding is a repair task.
            last_ids[stream] = rid
            if embed_budget > 0:
                if embed_fn(stream, rid, fields):
                    summary["embedded"] += 1
                else:
                    summary["embed_failures"] += 1
                embed_budget -= 1
    if not dry_run:
        state["last_ids"] = last_ids
        state["last_sweep"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        save_state(spath, state)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ORG-SENSES-2 trigger-stream exhaust archive "
                    "(append-only JSONL + org-memory landing; read-only Redis)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    summary = run_sweep(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"exhaust-archive: streams={summary['streams']} "
              f"archived={summary['archived']} embedded={summary['embedded']} "
              f"failures={summary['embed_failures']}"
              + (" (dry-run)" if summary["dry_run"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
