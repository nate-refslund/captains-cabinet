"""Truth-table tests for the F0.7 ledger-liveness dead-man's starvation decision.

cp2 re-review (2026-07-03) flagged that ledger-liveness-check.py — a trust-path
dead-man just changed by M-2 (unwindowed read) — had ZERO tests. This pins the
pure ``assess(rows, now_dt, poller_alive)`` seam extracted from that script.

``assess`` receives the ALREADY-COLLAPSED ledger (what ``loop.read_ledger`` returns:
last-write-wins by identity tuple). So a decided proposal is modeled as ONLY its
decision event (decision set), never a separate lingering pending event —
``pending_proposals(rows=)`` itself only filters ``decision is None``.

The script lives at cabinet/scripts/ledger-liveness-check.py (hyphenated, not an
importable module name) so it is loaded by path; the test sits under framework/
so CI's `pytest framework/ -q` job runs it (cabinet/ pytests gate only via
explicit per-dir CI steps).
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

from framework.acting import loop

_MODPATH = Path(__file__).resolve().parents[3] / "cabinet" / "scripts" / "ledger-liveness-check.py"
_spec = importlib.util.spec_from_file_location("ledger_liveness_check", _MODPATH)
llc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(llc)

NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
STARVE_H = llc.STARVE_H  # 24 by default


def _iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _proposal(subject: str, hours_ago: float, lane: str = "send-1to1-reply") -> dict:
    """A PENDING proposal (decision=None), ts = hours_ago before NOW."""
    return loop.proposal_event(
        actor={"kind": "officer", "id": "officer:cos"},
        lane=lane, subject=subject, ts=_iso(hours_ago),
    )


def _decision(subject: str, ts_hours_ago: float, decided_hours_ago: float,
              decision: str = "approved", lane: str = "send-1to1-reply") -> dict:
    """A collapsed, DECIDED proposal — the shape read_ledger yields after a
    superseding verdict. ts (proposal creation) is old; decided_at is the
    decision clock, which is what assess() filters decisions by."""
    ev = _proposal(subject, ts_hours_ago, lane)
    ev["proposal"] = {"required": True, "decision": decision,
                      "decided_at": _iso(decided_hours_ago)}
    ev["review"] = {"verdict": "confirmed"}
    return ev


def _assess(rows, poller_alive=True):
    return llc.assess(rows, NOW, poller_alive)


# (a) the canonical starvation: an old pending, channel up, no decisions.
def test_a_pending_old_poller_alive_no_decisions_is_starving():
    r = _assess([_proposal("Erin", STARVE_H + 24)])
    assert r["pending"] == 1 and r["oldest_h"] > STARVE_H
    assert r["decisions_recent"] == 0 and r["starving"] is True


# (b) M-2 regression: a VERY old pending (300h) is still counted — proving the
# decision does not depend on a read window (main() now feeds unwindowed rows).
def test_b_ancient_pending_still_seen_starving():
    r = _assess([_proposal("Erin", 300.0)])
    assert r["pending"] == 1 and r["oldest_h"] >= 300.0
    assert r["starving"] is True


# (c) a fresh decision (recent decided_at) on an OLD-ts proposal suppresses
# starvation even while another old pending exists — decisions filter by
# decided_at, NOT the proposal's original ts.
def test_c_recent_decision_by_decided_at_suppresses():
    rows = [
        _proposal("Erin", 300.0),                       # old, still pending
        _decision("Lena", ts_hours_ago=300.0,             # old proposal...
                  decided_hours_ago=1.0),                 # ...decided 1h ago
    ]
    r = _assess(rows)
    assert r["pending"] == 1                              # Erin still pending
    assert r["decisions_recent"] == 1                     # Lena decision counts (decided_at recent)
    assert r["starving"] is False


# a decision whose decided_at is OUTSIDE the window must NOT suppress.
def test_c2_stale_decision_does_not_suppress():
    rows = [
        _proposal("Erin", 300.0),
        _decision("Lena", ts_hours_ago=300.0, decided_hours_ago=STARVE_H + 5),
    ]
    r = _assess(rows)
    assert r["decisions_recent"] == 0 and r["starving"] is True


# (d) poller dead → NOT starving (an outage the other dead-men own; silence here
# is explained, not evidence-severance).
def test_d_poller_dead_not_starving():
    r = _assess([_proposal("Erin", 300.0)], poller_alive=False)
    assert r["starving"] is False


# (e) unparseable pending ts → counts as ANCIENT (fail-loud), starving.
def test_e_unparseable_ts_counts_ancient_starving():
    p = _proposal("Erin", 1.0)
    p["ts"] = "not-a-timestamp"
    r = _assess([p])
    assert r["oldest_h"] > STARVE_H and r["starving"] is True


# (f) synthetic-lane artifacts are excluded from BOTH pending and decisions.
def test_f_synthetic_excluded_from_math():
    rows = [
        _proposal("synthetic-probe", 300.0, lane="synthetic-test"),
        _decision("synthetic-dec", ts_hours_ago=1.0, decided_hours_ago=1.0,
                  lane="synthetic-test"),
    ]
    r = _assess(rows)
    assert r["pending"] == 0 and r["decisions_recent"] == 0
    assert r["starving"] is False


# (g) nothing pending → not starving (empty ledger and resolved-only ledger).
def test_g_no_pending_not_starving():
    assert _assess([])["starving"] is False
    resolved_only = [_decision("Lena", ts_hours_ago=300.0, decided_hours_ago=200.0)]
    r = _assess(resolved_only)
    assert r["pending"] == 0 and r["starving"] is False


# a FRESH pending (younger than STARVE_H) is normal, not starvation.
def test_fresh_pending_under_threshold_not_starving():
    r = _assess([_proposal("Erin", STARVE_H - 2)])
    assert r["pending"] == 1 and r["oldest_h"] < STARVE_H
    assert r["starving"] is False
