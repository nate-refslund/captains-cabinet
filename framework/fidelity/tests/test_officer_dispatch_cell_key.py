"""[GERM-2, RT-B4] officer_dispatch is a DISTINCT graduation cell from
internal_message. A delegate dispatch (org-internal machine handoff) must never
share a cell with an outbound colleague message — otherwise a dispatch's
accounting would leak into the internal_message cell's graduation math.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.fidelity.consequence import compute_ratios


def test_officer_dispatch_and_internal_message_are_distinct_cells():
    ledger = [
        {"ts": "2026-07-04T10:00:00Z", "actor": {"kind": "officer", "id": "cos"},
         "lane": "cos", "action": "acted:delegate_work", "subject": "s1",
         "action_type": "officer_dispatch", "outcome": {"status": "unknown"}},
        {"ts": "2026-07-04T10:01:00Z", "actor": {"kind": "officer", "id": "cos"},
         "lane": "cos", "action": "queue_draft", "subject": "s2",
         "action_type": "internal_message", "outcome": {"status": "unknown"}},
    ]
    cells = compute_ratios(ledger=ledger)
    assert ("officer:cos", "cos", "officer_dispatch") in cells
    assert ("officer:cos", "cos", "internal_message") in cells
    assert (("officer:cos", "cos", "officer_dispatch")
            != ("officer:cos", "cos", "internal_message"))


def test_consequence_action_types_track_classifier():
    # [GERM-2] the consequence validator's enum mirrors the classifier's, so the
    # three new action_types validate on acted events with no separate diff.
    from framework.fidelity.consequence import _ACTION_TYPES
    from framework.authority.classifier import ACTION_TYPES
    assert set(ACTION_TYPES) <= _ACTION_TYPES
