#!/usr/bin/env python3.12
"""memory-contradictions.py — §4.2 belief invalidation (propose-only pass).

The supersession plumbing is fully live — cabinet_memory.superseded_by,
the partial-unique live-rows index, memory-reconcile.sh's superseded_by IS
NULL filters, the nightly drift repair — but NOTHING ever sets it from
SEMANTIC conflict: two live rows can assert contradictory beliefs forever
and both keep feeding recall. This pass proposes supersession candidates;
it NEVER applies them. False-positive supersession is memory LOSS, so
auto-apply stays off until precision is measured over a soak (the exact
REPORT_ONLY pattern the self-improvement loop is running right now) —
apply is a Captain (or post-soak ruling) step, not this organ's.

Detection (deterministic, no LLM — reviewable, replayable):
  * NEAR-DUPLICATE  same source_type + token-Jaccard >= 0.75 → the newer
    row is proposed to supersede the older (the storage layer's own
    upsert semantics, extended to rows that lack a shared source_id).
  * CONTRADICTION-CUE  token-Jaccard >= 0.35 AND the newer row carries a
    negation/supersession cue the older lacks (never / no longer /
    retired / superseded / replaced / instead / deprecated / moved to /
    do not) → proposed with the cue named.

Bounds: same-source_type buckets only, newest ``BUCKET_CAP`` rows per
bucket (the O(n²) pair walk stays small), content window 90 days.

Output: proposals appended to
``shared/interfaces/memory-supersession-proposals.jsonl`` — one line per
(old,new) pair, stable sha8 id, skip-known on re-run, status "proposed".
``memory-supersede-apply.py`` (the post-soak apply organ, added
2026-07-15) consumes the file and stamps rows consumed; this script's
ONLY writes are that append + stdout. The SELECT is constant and
read-only (same psql/NEON_CONNECTION_STRING discipline as
falsifier-report.py — the connection VALUE is argv-only, never printed).

Run: python3.12 cabinet/scripts/memory-contradictions.py [--dry-run] [--json]
Scheduled via the services.yml row ``memory-contradictions`` (weekly, Sun
05:30). The apply organ runs on its OWN row ``memory-supersede-apply``
(Sun 05:45) — one command per row, because the generated-plist wrapper
``exec``s the command and a ``&&`` chain would never reach the second
program.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]

PROPOSALS_PATH = (_REPO_ROOT / "shared" / "interfaces" /
                  "memory-supersession-proposals.jsonl")
BUCKET_CAP = 400          # newest rows per source_type bucket
WINDOW_DAYS = 90
NEAR_DUP_JACCARD = 0.75
CUE_JACCARD = 0.35
MAX_PROPOSALS_PER_RUN = 200
_SNIPPET = 200

_CUES = ("never", "no longer", "not anymore", "retired", "superseded",
         "replaced", "instead of", "instead,", "deprecated", "moved to",
         "do not", "don't", "stopped", "obsolete")

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_STOP = {"the", "and", "for", "with", "that", "this", "from", "was", "are",
         "has", "have", "had", "not", "但", "into", "over", "its", "his",
         "her", "their", "our", "your", "will", "would", "should", "can"}


def _tokens(text: str) -> set:
    return {w for w in _WORD_RE.findall((text or "").lower())
            if w not in _STOP}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cues_in(text: str) -> List[str]:
    low = (text or "").lower()
    return [c for c in _CUES if c in low]


def _pid(old_id: str, new_id: str) -> str:
    return "sup-" + hashlib.sha256(f"{old_id}|{new_id}".encode()
                                   ).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Row supply — injectable; production reads one constant read-only SELECT.
# ---------------------------------------------------------------------------

_ROWS_SQL = (
    "SELECT id, source_type, officer, left(content, 1200), "
    "to_char(coalesce(source_created_at, created_at) AT TIME ZONE 'UTC', "
    "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
    "FROM cabinet_memory "
    "WHERE superseded_by IS NULL "
    "AND coalesce(source_created_at, created_at) > NOW() - interval '%d days' "
    "ORDER BY source_type, coalesce(source_created_at, created_at) DESC"
    % WINDOW_DAYS
)


def _neon_conn() -> Optional[str]:
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


def load_live_rows() -> Optional[List[dict]]:
    """Live-row slice via one constant read-only SELECT; None = unmeasurable
    (no psql / no conn / query failed) — degrade, never crash."""
    conn = _neon_conn()
    psql = shutil.which("psql") or (
        "/opt/homebrew/bin/psql"
        if os.path.exists("/opt/homebrew/bin/psql") else None)
    if not conn or not psql:
        return None
    try:
        proc = subprocess.run(
            [psql, conn, "-X", "-q", "-t", "-A", "-F", "\t",
             "-c", _ROWS_SQL],
            capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001
        return None
    if proc.returncode != 0:
        return None
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 5 or not parts[0]:
            continue
        rows.append({"id": parts[0], "source_type": parts[1],
                     "officer": parts[2], "content": parts[3],
                     "ts": parts[4]})
    return rows


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------

def propose(rows: List[dict]) -> List[dict]:
    """Deterministic pair walk inside source_type buckets (newest-first)."""
    buckets: Dict[str, List[dict]] = {}
    for r in rows:
        buckets.setdefault(str(r.get("source_type") or ""), []).append(r)
    proposals: List[dict] = []
    for stype, bucket in sorted(buckets.items()):
        bucket = sorted(bucket, key=lambda r: str(r.get("ts") or ""),
                        reverse=True)[:BUCKET_CAP]
        toks = [_tokens(r.get("content") or "") for r in bucket]
        for i in range(len(bucket)):          # newer (bucket is newest-first)
            for j in range(i + 1, len(bucket)):   # older
                if len(proposals) >= MAX_PROPOSALS_PER_RUN:
                    return proposals
                new, old = bucket[i], bucket[j]
                if new.get("id") == old.get("id"):
                    continue
                sim = jaccard(toks[i], toks[j])
                reason = None
                cues: List[str] = []
                if sim >= NEAR_DUP_JACCARD:
                    reason = "near-duplicate"
                elif sim >= CUE_JACCARD:
                    old_cues = set(_cues_in(old.get("content") or ""))
                    cues = [c for c in _cues_in(new.get("content") or "")
                            if c not in old_cues]
                    if cues:
                        reason = "contradiction-cue"
                if not reason:
                    continue
                proposals.append({
                    "proposal_id": _pid(str(old["id"]), str(new["id"])),
                    "status": "proposed",       # NEVER applied by this organ
                    "reason": reason,
                    "cues": cues,
                    "jaccard": round(sim, 3),
                    "source_type": stype,
                    "old": {"id": old["id"], "ts": old.get("ts"),
                            "snippet": str(old.get("content") or "")[:_SNIPPET]},
                    "new": {"id": new["id"], "ts": new.get("ts"),
                            "snippet": str(new.get("content") or "")[:_SNIPPET]},
                })
    return proposals


def known_ids(path: Path) -> set:
    out = set()
    try:
        with open(path) as f:
            for line in f:
                try:
                    pid = json.loads(line).get("proposal_id")
                except json.JSONDecodeError:
                    continue
                if pid:
                    out.add(pid)
    except OSError:
        pass
    return out


def run_pass(*, rows: Optional[List[dict]] = None,
             out_path: Optional[Path] = None,
             dry_run: bool = False) -> dict:
    path = out_path or PROPOSALS_PATH
    measurable = True
    if rows is None:
        rows = load_live_rows()
        if rows is None:
            measurable = False
            rows = []
    proposals = propose(rows)
    seen = known_ids(path)
    fresh = [p for p in proposals if p["proposal_id"] not in seen]
    if not dry_run and fresh:
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            for p in fresh:
                f.write(json.dumps({**p, "proposed_at": now},
                                   sort_keys=True) + "\n")
    return {"rows": len(rows), "proposals": len(proposals),
            "new": len(fresh), "known": len(seen),
            "measurable": measurable, "dry_run": dry_run}


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(
        description="Belief-invalidation pass — propose (never apply) "
                    "cabinet_memory supersession candidates.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    summary = run_pass(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        note = "" if summary["measurable"] else \
            " ALERT: cabinet_memory unmeasurable (psql/conn unavailable)"
        print(f"memory-contradictions: rows={summary['rows']} "
              f"proposals={summary['proposals']} new={summary['new']}"
              + (" (dry-run)" if summary["dry_run"] else "") + note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
