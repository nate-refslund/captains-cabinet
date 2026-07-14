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

Usage:
    python3.12 cabinet/scripts/seed-war-room.py           # plan only
    python3.12 cabinet/scripts/seed-war-room.py --apply   # write the ledger
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The C7 list (proposal §1, "genuinely-needs-Captain, unique, live: ~15").
# keywords: ALL must appear (lowercase) in a live open subject to count as
# already-carded. deadline/harm/leverage/kind ride as ref tags (payload).
C7_ITEMS = [
    {"slug": "polads-v1-release", "lane": "polads",
     "subject": "PolAds v1.0 release — go/no-go",
     "kind": "action-proposal", "keywords": ["polads", "release"],
     "leverage": 5},
    {"slug": "dg-just-coverage", "lane": "polads",
     "subject": "DG-JUST 14-Jul meeting coverage — who attends, what position",
     "kind": "founder-action", "keywords": ["dg-just"],
     "deadline": "2026-07-14T07:00:00Z", "harm": "external_deadline"},
    {"slug": "fleet-vercel-token", "lane": None,
     "subject": "Fleet Vercel token expires TODAY — rotate + reprovision",
     "kind": "founder-action", "keywords": ["vercel", "token"],
     "deadline": "2026-07-10T18:00:00Z", "harm": "external_deadline",
     "leverage": 3},
    {"slug": "h0-germline-ritual", "lane": None,
     "subject": "H0: arm the gateway — sudo germline unlock → git pull "
                "--ff-only → lock (blocks the whole attention plane)",
     "kind": "germline-handback", "keywords": ["germline", "unlock"],
     "leverage": 10},
    {"slug": "transparency-notice-flow", "lane": "polads",
     "subject": "Transparency-notice flow — approve the publisher-facing copy",
     "kind": "action-proposal", "keywords": ["transparency", "notice"]},
    {"slug": "cvr-decision", "lane": "polads",
     "subject": "CVR identifier decision (registration_number vs vat_number)",
     "kind": "action-proposal", "keywords": ["cvr"]},
    {"slug": "about-nate-bio", "lane": None,
     "subject": "about-nate bio — approve the draft",
     "kind": "draft-outbound", "keywords": ["about", "bio"]},
    {"slug": "enforce-admins", "lane": None,
     "subject": "enforce_admins on the framework repo — ratify on/off",
     "kind": "outcome-ratification", "keywords": ["enforce_admins"]},
    {"slug": "layer-sep-ruling", "lane": None,
     "subject": "Layer-separation ruling follow-through — ratify the "
                "instance-policy placement",
     "kind": "outcome-ratification", "keywords": ["layer", "separation"]},
    {"slug": "receipt-mor", "lane": "polads",
     "subject": "Receipt merchant-of-record wording — decide",
     "kind": "action-proposal", "keywords": ["receipt", "mor"]},
    {"slug": "c3-admission-law", "lane": None,
     "subject": "C3: ratify the admission law — room admits only captain-"
                "gated chains; org-decidable routed to the org (first "
                "narrowing of field-test-surface-everything)",
     "kind": "outcome-ratification", "keywords": ["admission", "law"]},
    {"slug": "report-only-arming", "lane": None,
     "subject": "Arm self-improvement REPORT_ONLY=0 after soak — ratify",
     "kind": "outcome-ratification", "keywords": ["report_only"]},
    # dated personal founder-actions (morning-brief carryovers)
    {"slug": "document-signing-passport", "lane": None,
     "subject": "Bring passport for the document signing",
     "kind": "founder-action", "keywords": ["passport"],
     "deadline": "2026-07-10T12:00:00Z", "harm": "external_deadline"},
    {"slug": "advokat-faktura", "lane": None,
     "subject": "Betal advokat-faktura (dokumentunderskrift, "
                "sagsnr. 00000)",
     "kind": "founder-action", "keywords": ["advokat-faktura"],
     "deadline": "2026-07-13T12:00:00Z", "harm": "value_decay"},
    {"slug": "notar-appointment", "lane": None,
     "subject": "Book notar appointment for the document signing",
     "kind": "founder-action", "keywords": ["notar"],
     "harm": "value_decay"},
]


def item_refs(item: dict) -> list:
    refs = [f"thread:seed/{item['slug']}", f"kind:{item['kind']}"]
    if item.get("deadline"):
        refs.append(f"deadline:{item['deadline']}")
    if item.get("harm"):
        refs.append(f"harm:{item['harm']}")
    if item.get("leverage"):
        refs.append(f"leverage:{item['leverage']}")
    return refs


def plan(open_props: list) -> list:
    """[(item, action, why)] — action in {seed, skip-live, skip-seeded}."""
    out = []
    subjects = [(str(p.get("subject") or "").lower(), p) for p in open_props]
    refsets = [set(str(r).lower() for r in (p.get("refs") or []))
               for p in open_props]
    for item in C7_ITEMS:
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

    try:
        open_props = pending_proposals()
    except Exception as e:
        print(f"ERROR: cannot read the ledger ({e}) — refusing to seed",
              file=sys.stderr)
        return 2

    todo = plan(open_props)
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
