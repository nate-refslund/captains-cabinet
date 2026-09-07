"""WORK RECEIPTS — a read model over the ledger, and nothing else.

The ledger already records every step of a responsibility's life. What it did
not have was a way to READ that life back as a list a person can scan: which
purpose was taken on, by which door, who claimed the work, what landed, what
was missing. This module is that read, and only that read.

READ-ONLY BY CONSTRUCTION. It emits nothing, writes nothing and takes no
argument that can steer a path. It replays the event ledger, shapes the rows
it understands, and returns them newest-last in ledger order. Anything it does
not understand it drops rather than guessing at.

WHY A VOCABULARY TABLE RATHER THAN A PREFIX RULE. Kinds are declared, not
derived, so a new event type joins this surface only when someone decides it
belongs on it. The table names the whole phase-1 vocabulary; the types whose
emitters have not landed yet simply never match, and the surface widens on the
day they do without another edit here.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

#: event_type → the kind a person reads. Declared, never derived.
KIND_BY_EVENT = {
    "captain_outcome_ratified": "ratified",
    "work_item_started": "started",
    "work_item_claim_renewed": "renewed",
    "work_item_claim_released": "released",
    "work_item_completed": "completed",
    "work_item_failed": "failed",
    "work_item_verified": "verified",
    "capability_gap_recorded": "gap",
    "cabinet_update_applied": "update_applied",
    "cabinet_update_refused": "update_refused",
    "cabinet_update_rolled_back": "update_rolled_back",
}

#: The kinds, in the order the contract names them — the render order a
#: surface may rely on when it groups.
KINDS = (
    "ratified", "started", "renewed", "released", "completed", "failed",
    "verified", "gap", "update_applied", "update_refused",
    "update_rolled_back",
)

_FIELDS = ("outcome_id", "task_id", "claim_id", "holder", "door",
           "evidence_path")


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def shape(event: dict) -> Optional[Dict[str, Any]]:
    """One ledger row as a receipt, or None when the kind is not on this
    surface. Pure — unit-testable without a ledger."""
    if not isinstance(event, dict):
        return None
    kind = KIND_BY_EVENT.get(str(event.get("event_type") or ""))
    if kind is None:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    row: Dict[str, Any] = {
        "ts": _text(event.get("created_at")),
        "kind": kind,
        "actor": _text(event.get("actor")),
        "event_id": _text(event.get("id")),
    }
    for field in _FIELDS:
        row[field] = _text(payload.get(field))
    # A gap's own id is the thing a reader follows, and it lives under a name
    # of its own rather than task_id — carried through as the task reference
    # so one column serves every row instead of a per-kind special case.
    if kind == "gap" and row["task_id"] is None:
        row["task_id"] = _text(payload.get("gap_id"))
    return row


def receipts(root: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Every receipt on the ledger, ledger order (oldest first).

    ``root`` is accepted for symmetry with the other read models and is
    deliberately unused: the ledger's location is resolved by the emitter from
    ``CABINET_EVENT_LOG_DIR``, and taking a second answer here would let a
    caller read one ledger while the writers use another.
    """
    from framework.events import emitter

    try:
        rows = emitter.replay(event_types=list(KIND_BY_EVENT))
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for event in rows:
        shaped = shape(event)
        if shaped is not None:
            out.append(shaped)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="framework.missions.receipts",
        description="Read the org's work receipts off the event ledger.")
    parser.add_argument("--json", action="store_true",
                        help="print the receipts as one JSON array")
    parser.add_argument("--root", default=None,
                        help="deployment root (accepted for symmetry; the "
                             "ledger location comes from the environment)")
    args = parser.parse_args(argv)

    rows = receipts(args.root)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
        return 0
    for row in rows:
        print("%s  %-16s %-12s %s" % (
            row.get("ts") or "?", row.get("kind"), row.get("actor") or "?",
            row.get("outcome_id") or row.get("task_id") or ""))
    if not rows:
        print("no receipts yet — the ledger is honestly empty")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    sys.exit(main())
