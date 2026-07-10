"""Tests for framework.fidelity.aggregate — the per-cell fidelity matrix + drift.

Per docs/fidelity-harness-design-2026-06-18.md §232-237 (component 6,
`aggregate.py`): roll case scores into per-(lane × decision-type) cell metrics
over a rolling window (decision_match_rate, partial_rate, divergent_rate,
style_win_rate, mechanics_fail_rate, sample_count) + CUSUM drift per cell, and
read the consequence ledger (read_ledger / compute_ratios) for the graduation
ratios. REUSES retrodiction aggregate + cusum via the retro shim — never
re-derives.

Strict TDD: these assertions describe the contract before aggregate.py exists.
"""

from __future__ import annotations

import pytest

from framework.fidelity import aggregate as agg
from framework.fidelity.aggregate import CellStats, compute_matrix


# ---------------------------------------------------------------------------
# Synthetic case-score row builder (the scorer.py CaseScore-shaped dict that
# aggregate rolls up). Mirrors the retrodiction score_case row surface: a
# judge.verdict, style_win, mechanics list, plus the cell key fields.
# ---------------------------------------------------------------------------
def _row(actor, lane, action_type, verdict, *, style_win=True,
         mechanics=None, reply_ts="2026-06-10T08:00:00Z", case_id="c"):
    return {
        "actor": actor,
        "lane": lane,
        "action_type": action_type,
        "case_id": case_id,
        "reply_ts": reply_ts,
        "channel": "teams",
        "language": "da",
        "person": "p",
        "style_clone": 0.9,
        "style_baseline": 0.5,
        "centroid_clone": None,
        "centroid_baseline": None,
        "style_win": style_win,
        "mechanics": list(mechanics or []),
        "judge": {"verdict": verdict, "rationale": "", "what_diverged": "",
                  "real_decision": "", "draft_decision": ""},
    }


# ---------------------------------------------------------------------------
# CellStats — the per-cell carrier
# ---------------------------------------------------------------------------
class TestCellStats:
    def test_carries_all_rates_and_sample_count(self):
        cs = CellStats(
            decision_match_rate=0.8, partial_rate=0.1, divergent_rate=0.1,
            style_win_rate=0.5, mechanics_fail_rate=0.0, sample_count=10,
        )
        assert cs.decision_match_rate == 0.8
        assert cs.partial_rate == 0.1
        assert cs.divergent_rate == 0.1
        assert cs.style_win_rate == 0.5
        assert cs.mechanics_fail_rate == 0.0
        assert cs.sample_count == 10
        # drift flag defaults False; series carried for inspection.
        assert cs.drift_alarm is False

    def test_unmeasured_cell_has_none_rates(self):
        # No-silent-caps: an unmeasured cell reads None, never a silent 0.0.
        cs = CellStats()
        assert cs.decision_match_rate is None
        assert cs.partial_rate is None
        assert cs.divergent_rate is None
        assert cs.style_win_rate is None
        assert cs.mechanics_fail_rate is None
        assert cs.sample_count == 0
        assert cs.drift_alarm is False


# ---------------------------------------------------------------------------
# compute_matrix — per-cell rates from synthetic case-score rows
# ---------------------------------------------------------------------------
class TestComputeMatrix:
    def test_per_cell_rates_match_expected(self):
        actor = {"kind": "officer", "id": "chair"}
        rows = [
            _row(actor, "send-1to1-reply", "reply", "match"),
            _row(actor, "send-1to1-reply", "reply", "match"),
            _row(actor, "send-1to1-reply", "reply", "partial"),
            _row(actor, "send-1to1-reply", "reply", "divergent",
                 style_win=False, mechanics=["language"]),
        ]
        matrix = compute_matrix(case_scores=rows)
        key = ("officer:chair", "send-1to1-reply", "reply")
        assert key in matrix
        cell = matrix[key]
        # 2 match / 4 judged
        assert cell.decision_match_rate == pytest.approx(0.5)
        assert cell.partial_rate == pytest.approx(0.25)
        assert cell.divergent_rate == pytest.approx(0.25)
        # 3 of 4 style_win=True
        assert cell.style_win_rate == pytest.approx(0.75)
        # 1 of 4 carries a mechanics flag
        assert cell.mechanics_fail_rate == pytest.approx(0.25)
        assert cell.sample_count == 4

    def test_distinct_cells_are_separated(self):
        a1 = {"kind": "officer", "id": "chair"}
        a2 = {"kind": "officer", "id": "bakery-ceo"}
        rows = [
            _row(a1, "send-1to1-reply", "reply", "match"),
            _row(a2, "triage", "prioritize", "divergent"),
        ]
        matrix = compute_matrix(case_scores=rows)
        assert ("officer:chair", "send-1to1-reply", "reply") in matrix
        assert ("officer:bakery-ceo", "triage", "prioritize") in matrix
        assert matrix[("officer:chair", "send-1to1-reply", "reply")].decision_match_rate == 1.0
        assert matrix[("officer:bakery-ceo", "triage", "prioritize")].divergent_rate == 1.0

    def test_empty_input_yields_empty_matrix(self):
        assert compute_matrix(case_scores=[], ledger=[]) == {}


# ---------------------------------------------------------------------------
# CUSUM drift — a drifting per-cell series trips the alarm
# ---------------------------------------------------------------------------
class TestDrift:
    def test_drifting_series_trips_cusum(self):
        # Build a per-cell match-rate series that starts high then SUSTAINS a
        # collapse — CUSUM (reused at its retrodiction defaults k=0.5, h=4.0)
        # fires a 'down' alarm once the downward deviation accumulates past h.
        # A single bad window is correctly ignored as noise; a sustained shift
        # is real drift, which is what the thermostat must catch.
        actor = {"kind": "officer", "id": "chair"}
        lane, at = "send-1to1-reply", "reply"
        rows = []
        # 5 windows all-match (rate 1.0), then 10 windows all-divergent (0.0).
        for w in range(5):
            for _ in range(4):
                rows.append(_row(actor, lane, at, "match",
                                 reply_ts=f"2026-06-{10 + w:02d}T08:00:00Z"))
        for w in range(10):
            for _ in range(4):
                rows.append(_row(actor, lane, at, "divergent",
                                 reply_ts=f"2026-06-{15 + w:02d}T08:00:00Z"))
        matrix = compute_matrix(case_scores=rows, window_by="day")
        cell = matrix[("officer:chair", lane, at)]
        assert cell.drift_alarm is True
        # the collapse is downward
        assert any(d == "down" for _, d in cell.drift_alarms)

    def test_stable_series_no_drift(self):
        actor = {"kind": "officer", "id": "chair"}
        lane, at = "send-1to1-reply", "reply"
        rows = []
        for w in range(6):
            for _ in range(4):
                rows.append(_row(actor, lane, at, "match",
                                 reply_ts=f"2026-06-{10 + w:02d}T08:00:00Z"))
        matrix = compute_matrix(case_scores=rows, window_by="day")
        cell = matrix[("officer:chair", lane, at)]
        assert cell.drift_alarm is False


# ---------------------------------------------------------------------------
# Consequence-ledger augmentation — graduation ratios join the same cell key
# ---------------------------------------------------------------------------
class TestLedgerAugmentation:
    def test_ledger_ratios_attach_to_matching_cell(self):
        actor = {"kind": "officer", "id": "chair"}
        rows = [_row(actor, "send-1to1-reply", "reply", "match")]
        # An explicit ledger of consequence events for the SAME cell.
        ledger = [
            {"ts": "2026-06-10T09:00:00Z", "actor": actor,
             "lane": "send-1to1-reply", "action": "reply to X",
             "subject": "thread-1", "action_type": "reply",
             "proposal": {"decision": "approved"}},
            {"ts": "2026-06-10T10:00:00Z", "actor": actor,
             "lane": "send-1to1-reply", "action": "reply to Y",
             "subject": "thread-2", "action_type": "reply",
             "outcome": {"status": "ok"}},
        ]
        matrix = compute_matrix(case_scores=rows, ledger=ledger)
        cell = matrix[("officer:chair", "send-1to1-reply", "reply")]
        assert cell.ratios is not None
        assert cell.ratios.approval_unchanged_rate == 1.0
        assert cell.ratios.outcome_held_rate == 1.0

    def test_cell_with_only_ledger_no_scores_has_none_fidelity_rates(self):
        # A cell present only in the ledger (no graded case scores) is SURFACED
        # (no-silent-caps) but its fidelity rates stay None — unmeasured.
        actor = {"kind": "officer", "id": "chair"}
        ledger = [
            {"ts": "2026-06-10T09:00:00Z", "actor": actor,
             "lane": "triage", "action": "prioritize",
             "subject": "board-1", "action_type": "prioritize",
             "proposal": {"decision": "approved"}},
        ]
        matrix = compute_matrix(case_scores=[], ledger=ledger)
        key = ("officer:chair", "triage", "prioritize")
        assert key in matrix
        cell = matrix[key]
        assert cell.decision_match_rate is None
        assert cell.style_win_rate is None
        assert cell.sample_count == 0
        assert cell.ratios is not None
        assert cell.ratios.approval_unchanged_rate == 1.0


# ---------------------------------------------------------------------------
# Reuse boundary — must go through the retro shim, not re-derive
# ---------------------------------------------------------------------------
class TestReuseBoundary:
    def test_uses_retro_aggregate_and_cusum(self):
        # The module must reference the shim's aggregate + cusum (reuse, not
        # re-derive). Assert the names resolve to the shim's objects.
        from framework.fidelity import retro
        assert agg.aggregate is retro.aggregate
        assert agg.cusum is retro.cusum
