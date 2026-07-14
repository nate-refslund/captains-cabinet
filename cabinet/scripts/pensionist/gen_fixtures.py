"""Generate a synthetic private-census queue.json for the pensionist UX review.

Shape: framework/attention/queue.py to_private_census() output. All content is
invented review data — no real pids, no secrets. Vocabulary is the synthetic
Testburg estate (bakery-site / newsletter lanes — Wave G 2026-07-12: fixtures
never name instance lanes or products). generated_at is stamped fresh so the
dashboard reader never falls back.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

NOW = datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def card(id_, kind, what, *, lane=None, blast=("low", "internal"), worst=None,
         pid=None, approve="direct", age_h=None, deadline=None, urgency="batch",
         refs=(), filed_by="officer:cos", state="open", decay=None,
         one_tap=True):
    return {
        "id": id_, "kind": kind, "state": state, "class": None,
        "urgency": urgency,
        "deadline_iso": iso(NOW + timedelta(hours=deadline)) if deadline else None,
        "harm_class": None, "age_h": age_h,
        "blast": {"class": blast[0], "reach": blast[1]},
        "decay_stage": "fresh", "admission": None,
        "pid": pid, "h": None, "what": what,
        "why_now": ({"decay": decay} if decay else None),
        "refs": list(refs),
        "one_tap": ({"approve": approve, "veto": "direct", "defer": "direct",
                     "delegate_back": "direct"} if one_tap else None),
        "blast_worst_case": worst,
        "filed_by": filed_by, "lane": lane,
    }


DECISIONS = [
    card("sit-d1", "draft-outbound",
         "Reply to the flour supplier: the shop's VAT number is fixed on the live site",
         lane="bakery-site", blast=("org", "external"),
         worst="a message reaches a human outside the machine",
         pid="prop-d1-reply-supplier-vat", approve="per-item-approval",
         age_h=26.4, deadline=20, urgency="batch",
         refs=["thread:bakery-site-support-1182", "draft:chair-2026-07-10-01"],
         decay="waiting 26h; 1 demotion"),
    card("sit-d2", "need",
         "Let the cabinet add events to your Work calendar",
         blast=("ceiling", "org"),
         worst="a standing grant widens org authority",
         pid="need-cal-write-2026", age_h=4.2,
         refs=["grant:calendar-write"]),
    card("sit-d3", "action-proposal",
         "Pay the 39 euro monthly card-checkout invoice so webshop testing keeps working",
         lane="bakery-site", blast=("org", "external"),
         worst="money leaves the org",
         pid="prop-d3-checkout-invoice", age_h=49.0, deadline=26,
         refs=["invoice:checkout-2026-07"]),
    card("sit-d4", "escalation",
         "Two officers disagree: ship the newsletter signup beta this week, or hold it for more testing",
         lane="newsletter", blast=("low", "internal"),
         worst="the Chair is holding a judgment open",
         pid="esc-signup-beta", age_h=1.5, urgency="ping-now",
         refs=["thread:newsletter-signup-beta"]),
    card("sit-d5", "germline-handback",
         "New standing rule: officers may send internal Teams replies without asking first",
         blast=("ceiling", "org"),
         worst="a wrong approve amends the germline plane",
         pid="germ-hb-2026-07-10", approve="ritual-print", age_h=3.0,
         refs=["rule:R201-draft"]),
]

DIRECTIONS = [
    card("sit-r1", "outcome-ratification",
         "Goal for the quarter: the bakery site runs self-serve, you only handle sign-offs",
         lane="bakery-site", pid="outcome-q3-bakery-site", approve="ritual-print",
         age_h=90.0),
    card("sit-r2", "action-proposal",
         "Tidy the duplicate people entries in the address book (undo kept for a week)",
         lane="newsletter", worst="a reversible internal artifact needs undoing",
         pid="prop-r2-people-merge", age_h=70.0),
    card("sit-r3", "pipe-prompt",
         "Should the morning brief include your private calendar too?",
         pid=None, one_tap=False, age_h=20.0),
]

DOC = {
    "v": 1,
    "generated_at": iso(NOW),
    "pending_captain_items": 8,
    "pending_total": 11,
    "by_class": {"action-proposal": 4, "draft-outbound": 2, "need": 1,
                 "escalation": 1, "germline-handback": 1, "other": 3},
    "overflow": 3,
    "cap": 5,
    "admission_enforced": True,
    "decisions": DECISIONS,
    "directions": DIRECTIONS,
    "overflow_ids": ["sit-o1", "sit-o2", "sit-o3"],
    "org_routed": [],
    "parked": [],
}

out = Path(sys.argv[1] if len(sys.argv) > 1
           else Path(__file__).resolve().parent / "out") / "queue.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(DOC, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {out} generated_at={DOC['generated_at']}")
