#!/usr/bin/env python3
"""emit-graduation-transitions.py — make per-cell autonomy state CHANGES visible.

WHY (lane instrument, 2026-07-05): framework/fidelity/graduation.py:267
(`evaluate`) is deliberately STATELESS — it recomputes a cell's state from the
consequence ledger on every call and remembers nothing. That is correct for
the gate (framework/authority — always reads fresh), but it means NOTHING in
the org ever records the MOMENT a cell moved (propose_only -> eligible,
eligible -> graduated, graduated -> demote). Briefings and the falsifier
report can only show snapshots (cells_accumulating / cells_graduated counts,
cabinet/scripts/falsifier-report.py:126), never movement — loop-closure was
invisible. graduation.py is also schg-LOCKED (cabinet/scripts/germline-lock.sh
FILES list), so the transition detector must live in an UNLOCKED caller: this
sweep.

WHAT IT DOES (one pass):
  1. Reads the consequence ledger read-only (consequence.read_ledger — deduped)
     and derives the ACTIVE cell set exactly like the falsifier report does
     (falsifier-report.py:126-134): compute_ratios keys, excluding the
     __unstamped__ sentinel (can never graduate by design) and sample_count==0.
  2. Evaluates each cell with the ONE graduation read (graduation.evaluate —
     bar from authority-matrix.yml, never a second copy).
  3. Compares to the last-seen state persisted in an UNLOCKED JSON state file
     (default: ~/Library/Application Support/cabinet/state/
     graduation-transitions.json; override: CABINET_GRADUATION_STATE_FILE).
  4. On change, emits a typed `graduation_transition` org event
     (framework/events/emitter.py VALID_EVENT_TYPES — registered 2026-07-05)
     with payload {cell:{actor,lane,action_type}, from_state, to_state,
     evidence:{sample_count, match_rate, fitness, divergent_last10}} so the
     briefing/digest layer can SEE cells moving from org_events.
  5. Atomically rewrites the state file (tempfile + os.replace — never a
     half-written state).

FAIL-SAFE INVARIANTS (Corridor):
  * A per-cell evaluate error yields NO verdict for that cell: it is skipped,
    its previous state is carried forward unchanged, and no transition is
    emitted (an error must never read as a state change).
  * A ledger read failure exits 1 with NO emits and NO state write.
  * FIRST RUN (no state file) seeds the baseline WITHOUT emitting (a fresh
    deploy would otherwise flood org_events + the next briefing with N
    baseline "transitions"); pass --emit-baseline to emit the baseline
    explicitly. Cells appearing AFTER the baseline emit from_state=null.
  * Delivery is AT-LEAST-ONCE: a cell whose emit FAILED keeps its previous
    state in the written file, so the transition re-detects and re-emits next
    sweep. (The alternative — state-first — loses the event forever on a
    crash between write and emit; a duplicate visibility event is the safer
    residual. Consumers must tolerate duplicates.)

Everything is read-only except the state file + the org-event append via the
existing validated emitter. No network, no Redis, no secrets, no argv secrets.

Run:      python3 cabinet/scripts/emit-graduation-transitions.py [--dry-run]
              [--emit-baseline] [--state-file PATH]
Schedule: not yet scheduled — pair with the falsifier daily line or a
          services.yml cron entry (services.yml is owned by the supply lane;
          see cabinet/launchd/INSTALL-flip.md for the sibling telemetry jobs).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.fidelity.consequence import (  # noqa: E402
    UNSTAMPED_ACTION_TYPE, compute_ratios, read_ledger)

# The org-event vocabulary entry this sweep owns (framework/events/emitter.py).
EVENT_TYPE = "graduation_transition"
ACTOR = "graduation-sweep"

_DEFAULT_STATE_FILE = os.path.expanduser(
    "~/Library/Application Support/cabinet/state/graduation-transitions.json")

Cell = Tuple[str, Optional[str], str]  # (actor_id "kind:id", lane, action_type)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def state_file_path(cli_override: Optional[str] = None) -> Path:
    """CLI flag > env override (fenced tests) > the unlocked live default."""
    return Path(cli_override
                or os.environ.get("CABINET_GRADUATION_STATE_FILE")
                or _DEFAULT_STATE_FILE)


def _cell_key(cell: Cell) -> str:
    """Canonical JSON-string key for the state file (object keys must be
    strings; a json list round-trips None lanes unambiguously — a '|' join
    would collide on ids containing '|')."""
    return json.dumps(list(cell), ensure_ascii=False)


def _parse_cell_key(key: str) -> Optional[Cell]:
    """Inverse of _cell_key; None for a corrupt entry (dropped fail-safe —
    a key we cannot parse identifies no cell, so it gets no verdict and no
    transition; it simply leaves the state file on the next atomic rewrite)."""
    try:
        parts = json.loads(key)
    except (ValueError, TypeError):
        return None
    if (not isinstance(parts, list) or len(parts) != 3
            or not isinstance(parts[0], str) or not isinstance(parts[2], str)
            or not (parts[1] is None or isinstance(parts[1], str))):
        return None
    return (parts[0], parts[1], parts[2])


def load_state(path: Path) -> Optional[Dict[str, str]]:
    """Last-seen {cell_key: state}. None = no state file yet (BASELINE run —
    distinct from an empty-but-present file, which is a normal run that saw
    zero cells). A corrupt file is treated as baseline (seed, don't flood)."""
    try:
        with open(path) as f:
            doc = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        # Corrupt/unreadable state: we cannot know what was last seen, so we
        # re-seed silently rather than emit N bogus "transitions" against a
        # broken memory (same flood-guard rationale as first run).
        print("emit-graduation-transitions: WARN state file unreadable — "
              "re-seeding baseline", file=sys.stderr)
        return None
    cells = doc.get("cells") if isinstance(doc, dict) else None
    return cells if isinstance(cells, dict) else None


def write_state(path: Path, cells: Dict[str, str], now: dt.datetime) -> None:
    """Atomic rewrite (tempfile + os.replace) — a crash mid-write must never
    leave a torn file that the next run would mis-read as corrupt/baseline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"updated_at": _iso(now), "cells": cells}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".grad-trans-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f, ensure_ascii=False, sort_keys=True, indent=1)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def active_cells(ledger: List[Dict[str, Any]]) -> List[Cell]:
    """The cells worth watching — same filter as falsifier-report.py:126-134:
    the __unstamped__ sentinel bucket is excluded (it can never graduate by
    design), as are empty cells."""
    out: List[Cell] = []
    for cell, ratios in compute_ratios(ledger=ledger).items():
        if cell[2] == UNSTAMPED_ACTION_TYPE or ratios.sample_count == 0:
            continue
        out.append(cell)
    return out


def sweep(ledger: List[Dict[str, Any]],
          prev: Optional[Dict[str, str]],
          *, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    """Pure transition detection (no IO, no emits) — the unit tests' seam.

    Evaluates the UNION of currently-active cells and previously-seen cells:
    a cell whose rows vanished from the ledger (rotation/purge) still gets one
    honest transition to its re-evaluated state (`unmeasured` on no rows)
    instead of silently disappearing from the record.

    Returns {"current": {cell_key: state}, "transitions": [...],
    "errors": [...], "baseline": bool}. On a per-cell evaluate error the cell
    lands in "errors", keeps its previous state in "current" (if any), and
    produces NO transition — no verdict on error, never a spurious change.
    """
    from framework.fidelity import graduation

    now = now or _now()
    baseline = prev is None
    prev_map: Dict[str, str] = dict(prev or {})

    keys: Dict[str, Cell] = {}
    for cell in active_cells(ledger):
        keys[_cell_key(cell)] = cell
    for key in prev_map:
        if key in keys:
            continue
        cell = _parse_cell_key(key)
        # Corrupt key or a stale sentinel entry: identifies no watchable cell.
        if cell is None or cell[2] == UNSTAMPED_ACTION_TYPE:
            continue
        keys[key] = cell

    current: Dict[str, str] = {}
    transitions: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for key in sorted(keys):  # deterministic order → stable emits + tests
        cell = keys[key]
        try:
            verdict = graduation.evaluate(cell, ledger=ledger, now=now)
            state = verdict["state"]
            evidence = verdict.get("evidence") or {}
        except Exception as e:  # noqa: BLE001 — fail-safe: no verdict on error
            errors.append({"cell": key, "error": f"{type(e).__name__}: {e}"})
            if key in prev_map:          # carry the old state forward unchanged
                current[key] = prev_map[key]
            continue
        current[key] = state
        prev_state = prev_map.get(key)
        if prev_state != state:
            transitions.append({
                "cell": {"actor": cell[0], "lane": cell[1],
                         "action_type": cell[2]},
                "from_state": prev_state,   # None = first sighting of the cell
                "to_state": state,
                # Compact evidence subset — enough for a briefing line; the
                # full picture is always re-derivable from graduation.evaluate.
                "evidence": {
                    "sample_count": evidence.get("sample_count"),
                    "match_rate": evidence.get("match_rate"),
                    "fitness": evidence.get("fitness"),
                    "divergent_last10": evidence.get("divergent_last10"),
                },
            })

    return {"current": current, "transitions": transitions,
            "errors": errors, "baseline": baseline}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Detect + emit per-cell graduation/demotion transitions "
                    "into org_events (see module docstring).")
    ap.add_argument("--dry-run", action="store_true",
                    help="print would-be transitions; emit nothing, write no state")
    ap.add_argument("--emit-baseline", action="store_true",
                    help="on the FIRST run (no state file) emit every cell's "
                         "initial state instead of seeding silently")
    ap.add_argument("--state-file", default=None,
                    help="override the last-seen state file path")
    args = ap.parse_args(argv)

    now = _now()
    try:
        ledger = read_ledger()
    except Exception as e:  # noqa: BLE001 — fail-safe: no ledger, no verdicts
        print(f"emit-graduation-transitions: ledger read failed: {e}",
              file=sys.stderr)
        return 1

    path = state_file_path(args.state_file)
    prev = load_state(path)
    result = sweep(ledger, prev, now=now)

    suppress = result["baseline"] and not args.emit_baseline
    emitted = 0
    emit_failures = 0

    if args.dry_run:
        for t in result["transitions"]:
            print(f"[dry-run] {t['cell']} {t['from_state']} -> {t['to_state']}")
    elif suppress:
        # Flood guard: first sighting of the whole estate is a SEED, not N
        # transitions — the state file becomes the baseline silently.
        pass
    else:
        from framework.events.emitter import emit
        for t in result["transitions"]:
            try:
                emit(EVENT_TYPE, actor=ACTOR, payload=t)
                emitted += 1
            except Exception as e:  # noqa: BLE001
                emit_failures += 1
                # At-least-once: revert this cell to its previous state (or
                # drop a first-sighting) so the SAME transition re-detects and
                # re-emits on the next sweep instead of being lost.
                key = _cell_key((t["cell"]["actor"], t["cell"]["lane"],
                                 t["cell"]["action_type"]))
                if t["from_state"] is None:
                    result["current"].pop(key, None)
                else:
                    result["current"][key] = t["from_state"]
                print(f"emit-graduation-transitions: WARN emit failed for "
                      f"{key}: {e}", file=sys.stderr)

    if not args.dry_run:
        try:
            write_state(path, result["current"], now)
        except OSError as e:
            # Events (if any) are already out; next run re-baselines from the
            # old file (or seeds). Loud, non-zero — a sweep that cannot
            # remember is broken even though nothing false was emitted.
            print(f"emit-graduation-transitions: state write failed: {e}",
                  file=sys.stderr)
            return 1

    summary = {
        "ts": _iso(now),
        "cells": len(result["current"]),
        "transitions": len(result["transitions"]),
        "emitted": emitted,
        "emit_failures": emit_failures,
        "eval_errors": len(result["errors"]),
        "baseline_seeded": bool(suppress),
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
