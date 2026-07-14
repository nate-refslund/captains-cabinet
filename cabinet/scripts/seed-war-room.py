#!/usr/bin/env python3.12
"""seed-war-room.py — C7 day-one truth for the war-room census.

Captain ruling C7 (command-center proposal 2026-07-10 §7): the ~15-item
genuinely-needs-Captain list (§1) is the room's day-one truth; everything
else enters only through the admission law.

DEDUP-AWARE BY CONSTRUCTION (H1): most C7 items already live as open binder
cards — re-seeding those would double-card their situations. For each item
this seeder first scans the OPEN proposal set for a subject-keyword match
(case-insensitive, all keywords) and SKIPS live-covered items; only the
doc-shaped orphans (germline handbacks, ratifications, dated founder
actions — exactly the class the starving-queue history says dies in docs)
are filed, through the ONE adapter that exists today: a PENDING consequence-
ledger proposal row (loop.proposal_event → emit_consequence), carrying the
war-room ref tags (thread:seed/<slug> anchor id, kind:/deadline:/harm:/
leverage: payload tags — see framework/attention/situations.py).

Also files the H6 estate-triage row (C5) — idempotent.

DRY-RUN by default; --apply writes. Idempotent: a re-run skips every item
whose seed anchor (thread:seed/<slug>) or keyword-match already has an open
row. Closure: hygiene.propagate_closure binds these by the thread: anchor.

Product/captain-agnostic foundation (2026-07-14): the concrete C7 census
list is deployment-local data, not framework code — it lives in
instance/config/war-room-seed.yml (gitignored; war-room-seed.yml.example
ships the schema + an illustrative example). A fresh clone / absent or
empty instance file means nothing to seed (correct default — never an
invented census), not an error.

Usage:
    python3.12 cabinet/scripts/seed-war-room.py           # plan only
    python3.12 cabinet/scripts/seed-war-room.py --apply   # write the ledger
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

WAR_ROOM_SEED_REL = "instance/config/war-room-seed.yml"


def load_c7_items(root: Path = _ROOT,
                  seed_rel: str = WAR_ROOM_SEED_REL) -> list[dict]:
    """The C7 census list (proposal §1, "genuinely-needs-Captain, unique,
    live: ~15"), sourced from the deployment-local instance/config/
    war-room-seed.yml. keywords: ALL must appear (lowercase) in a live open
    subject to count as already-carded. deadline/harm/leverage/kind ride as
    ref tags (payload). Absent file -> [] (nothing to seed), never an error
    or an invented item."""
    path = root / seed_rel
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("items") or []
    if not isinstance(items, list):
        raise ValueError(f"{path}: 'items:' must be a list")
    # Validate up front (plan()/item_refs() index required keys directly,
    # e.g. item['slug'] -- a malformed operator-authored entry should fail
    # loudly here with the offending index, not deep in plan() as a bare
    # KeyError with no indication which item or field is missing).
    required = ("slug", "subject", "kind", "keywords")
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: items[{i}] must be a mapping, got "
                             f"{type(item).__name__}")
        missing = [k for k in required if k not in item]
        if missing:
            raise ValueError(
                f"{path}: items[{i}] (slug={item.get('slug')!r}) missing "
                f"required field(s): {missing}")
    return items


def item_refs(item: dict) -> list:
    refs = [f"thread:seed/{item['slug']}", f"kind:{item['kind']}"]
    if item.get("deadline"):
        refs.append(f"deadline:{item['deadline']}")
    if item.get("harm"):
        refs.append(f"harm:{item['harm']}")
    if item.get("leverage"):
        refs.append(f"leverage:{item['leverage']}")
    return refs


def plan(open_props: list, c7_items: list[dict]) -> list:
    """[(item, action, why)] — action in {seed, skip-live, skip-seeded}."""
    out = []
    subjects = [(str(p.get("subject") or "").lower(), p) for p in open_props]
    refsets = [set(str(r).lower() for r in (p.get("refs") or []))
               for p in open_props]
    for item in c7_items:
        anchor = f"thread:seed/{item['slug']}"
        if any(anchor in rs for rs in refsets):
            out.append((item, "skip-seeded", "seed anchor already open"))
            continue
        hit = next((p for s, p in subjects
                    if all(k in s for k in item["keywords"])), None)
        if hit is not None:
            out.append((item, "skip-live",
                        f"live card covers it: {hit.get('subject')!r}"))
            continue
        out.append((item, "seed", "no live coverage — filing"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the ledger (default: dry-run plan)")
    args = ap.parse_args()

    from framework.acting.loop import pending_proposals, proposal_event
    from framework.fidelity.consequence import emit_consequence
    from framework.attention import hygiene

    c7_items = load_c7_items()
    if not c7_items:
        print(f"seed-war-room: {WAR_ROOM_SEED_REL} not found or empty — "
              f"nothing to seed (copy war-room-seed.yml.example and fill in "
              f"this deployment's day-one census to use this seeder)",
              file=sys.stderr)
        return 0

    try:
        open_props = pending_proposals()
    except Exception as e:
        print(f"ERROR: cannot read the ledger ({e}) — refusing to seed",
              file=sys.stderr)
        return 2

    todo = plan(open_props, c7_items)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    seeded = 0
    for item, action, why in todo:
        print(f"{action:12} {item['slug']:24} {why}")
        if action != "seed" or not args.apply:
            continue
        ev = proposal_event(
            actor={"kind": "pipe", "id": "war-room-seed"},
            lane=item.get("lane"), subject=item["subject"], ts=now,
            action="action-card", required=True, refs=item_refs(item))
        emit_consequence(**ev)
        seeded += 1

    if args.apply:
        triage = hygiene.file_screenpipe_triage_row()
        print(f"H6 estate-triage row: {triage}")
        print(f"seeded {seeded} item(s); "
              f"{sum(1 for _, a, _w in todo if a != 'seed')} skipped")
    else:
        print(f"\nDRY-RUN: would seed "
              f"{sum(1 for _, a, _w in todo if a == 'seed')} item(s); "
              f"re-run with --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
