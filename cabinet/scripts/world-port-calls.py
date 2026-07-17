#!/usr/bin/env python3.12
"""world-port-calls.py — dated PORT CALLS from the outcomes ledger's git history.

A PORT CALL is the first date an outcome id's `status:` flips to `achieved`
in instance/config/outcomes.yml — the org's "made port" moments, one stamp
per achieved outcome. The Cabinet World direction surface (morphology v4:
harbor_port_calls / harbor_boat_voyage; grammar-law PR 2026-07-17) renders
these stamps at the quay and folds them into the per-lane course state
(docked_refitting | tacking | adrift — ledger-state semantics only).

EXTRACTION (read-only, replay = git): the exact pattern the calibrated
backtest proved (cabinet/scripts/world-growth-backtest.py extract_history
step 3): `git log --follow --format='%H %cs' -- instance/config/outcomes.yml`
then `git show <sha>:instance/config/outcomes.yml` per revision, oldest →
newest, yaml.safe_load each blob. Lane attribution mirrors the backtest's
_lane_of rule byte-for-byte: explicit `lane:` key, else the outcome-<lane>-NNN
id. Nothing invented, nothing back-filled — an outcome that never flips
simply never stamps.

OUTPUT: shared/interfaces/world/port-calls.json — a REBUILDABLE runtime
read-model (the shared/interfaces/world/ directory is gitignored, the same
class as world-chronicle.jsonl). Replay stance is `git`: regenerate-and-diff
IS the replay; deleting the artifact loses nothing. The engine route reads
it fail-honest (absent file ⇒ no stamps, boat moored — never an invented
voyage).

Usage:
  python3.12 cabinet/scripts/world-port-calls.py            # write the artifact
  python3.12 cabinet/scripts/world-port-calls.py --stdout   # print, no write

No DB, no redis, no network, no secrets. List-argv subprocess only
(shell=False by construction), fixed repo-relative paths.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

REPO = Path(__file__).resolve().parents[2]
OUTCOMES_RELPATH = "instance/config/outcomes.yml"
ARTIFACT_RELPATH = "shared/interfaces/world/port-calls.json"
SCHEMA = "cabinet.world.port-calls/v1"


# ── fenced readers (world-growth-backtest.py _run pattern) ──────────────────

def _run(cmd: List[str], timeout: int = 60) -> Optional[str]:
    """List-argv subprocess, never shell. None on any failure."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    return proc.stdout if proc.returncode == 0 else None


# ── pure fold functions (pytest-covered with fixture blobs, no live git) ────

def lane_of(outcome: dict) -> Optional[str]:
    """Lane of an outcome: explicit lane: else the outcome-<lane>-NNN id
    (byte-mirror of world-growth-backtest.py _lane_of)."""
    lane = outcome.get("lane")
    if isinstance(lane, str) and lane:
        return lane
    oid = str(outcome.get("id", ""))
    if oid.startswith("outcome-"):
        parts = oid[len("outcome-"):].rsplit("-", 1)
        if len(parts) == 2:
            return parts[0]
    return None


def outcome_statuses(doc: object) -> Dict[str, Dict[str, Optional[str]]]:
    """One outcomes.yml document → {outcome_id: {status, lane}}.
    Malformed rows are skipped, never guessed."""
    out: Dict[str, Dict[str, Optional[str]]] = {}
    if not isinstance(doc, dict):
        return out
    for o in doc.get("outcomes") or []:
        if not isinstance(o, dict):
            continue
        oid = o.get("id")
        if not isinstance(oid, str) or not oid:
            continue
        out[oid] = {"status": str(o.get("status", "")), "lane": lane_of(o)}
    return out


def fold_port_calls(
    snapshots: List[Tuple[str, object]],
) -> Dict[str, List[Dict[str, str]]]:
    """snapshots = [(commit_date_iso, parsed outcomes.yml doc), ...] OLDEST
    FIRST. A PORT CALL = the FIRST date an outcome id's status reads
    `achieved`. Returns {lane: [{date, outcome_id}, ...]} with each lane's
    stamps sorted by (date, outcome_id) — deterministic for equal input."""
    first_achieved: Dict[str, Tuple[str, Optional[str]]] = {}
    for date_s, doc in snapshots:
        for oid, rec in outcome_statuses(doc).items():
            if rec["status"] == "achieved" and oid not in first_achieved:
                first_achieved[oid] = (date_s, rec["lane"])
    lanes: Dict[str, List[Dict[str, str]]] = {}
    for oid, (date_s, lane) in sorted(
        first_achieved.items(), key=lambda kv: (kv[1][0], kv[0])
    ):
        lanes.setdefault(lane or "unknown", []).append(
            {"date": date_s, "outcome_id": oid}
        )
    return lanes


def build_artifact(
    lanes: Dict[str, List[Dict[str, str]]],
    generated_at: str,
    source_git_head: Optional[str],
) -> dict:
    """The artifact document (schema cabinet.world.port-calls/v1)."""
    all_dates = [pc["date"] for calls in lanes.values() for pc in calls]
    return {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "source_git_head": source_git_head,
        "port_calls_total": sum(len(v) for v in lanes.values()),
        "last_port_call_date": max(all_dates) if all_dates else None,
        "lanes": {k: lanes[k] for k in sorted(lanes)},
    }


# ── git history extraction (read-only) ──────────────────────────────────────

def extract_snapshots(repo: Path) -> List[Tuple[str, object]]:
    """Every historical version of outcomes.yml, oldest → newest, as
    (commit_date, parsed_doc). Unreadable/unparseable revisions are skipped
    (the fold sees only real parseable states)."""
    raw = _run(["git", "-C", str(repo), "log", "--follow",
                "--format=%H %cs", "--", OUTCOMES_RELPATH]) or ""
    revs = [ln.split() for ln in raw.splitlines() if len(ln.split()) == 2]
    out: List[Tuple[str, object]] = []
    for sha, date_s in reversed(revs):  # git log is newest-first → reverse
        blob = _run(["git", "-C", str(repo), "show", f"{sha}:{OUTCOMES_RELPATH}"])
        if blob is None:
            continue
        try:
            doc = yaml.safe_load(blob)
        except Exception:
            continue
        if isinstance(doc, dict):
            out.append((date_s, doc))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract dated port calls (outcome achieved-flips) from git history")
    ap.add_argument("--repo", default=str(REPO), help="repo root (default: this repo)")
    ap.add_argument("--out", default=None,
                    help=f"artifact path (default: <repo>/{ARTIFACT_RELPATH})")
    ap.add_argument("--stdout", action="store_true",
                    help="print the artifact JSON; do not write the file")
    args = ap.parse_args()

    repo = Path(args.repo)
    snapshots = extract_snapshots(repo)
    if not snapshots:
        print("world-port-calls: no readable outcomes.yml history — "
              "nothing to fold (is this a git checkout?)", file=sys.stderr)
        return 1
    lanes = fold_port_calls(snapshots)
    head = (_run(["git", "-C", str(repo), "rev-parse", "HEAD"]) or "").strip() or None
    artifact = build_artifact(
        lanes,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        source_git_head=head,
    )
    text = json.dumps(artifact, indent=1, sort_keys=True) + "\n"
    if args.stdout:
        sys.stdout.write(text)
        return 0
    out_path = Path(args.out) if args.out else repo / ARTIFACT_RELPATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(text)
    tmp.replace(out_path)  # atomic on POSIX
    print(f"port-calls: {out_path} (total={artifact['port_calls_total']}, "
          f"last={artifact['last_port_call_date']}, lanes={sorted(lanes)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
