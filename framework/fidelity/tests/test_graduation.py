"""F2 — tests for graduation.evaluate (per-cell autonomy state machine).

Strict TDD. These assert the contract in
docs/authority-matrix-design-2026-06-19.md §3 (Component 3) + §1 Component-1
bars + docs/fidelity-harness-design-2026-06-18.md §7 graduation:

  evaluate(cell=(officer_actor_id, lane, action_type)) -> {state, evidence}
  state in {unmeasured, propose_only, eligible, graduated, demote}

Bar floor (READ from framework/policies/authority-matrix.yml, NOT hardcoded):
  samples>=20, match_rate>=0.85, <=1 divergent in last 10, recency_clean>=14d.
Per-decision-type overrides from the yaml (keyed by risk_class):
  internal_comms 0.90/30/0/21, deploy_nonprod 0.95/30/0/21.

Fitness = outcome_held_rate x review_confirmed_rate (positive signal, NOT
correction-count). FAIL-SAFE: a cell whose ratios are None (no data /
denominator 0) -> 'unmeasured' (never silently eligible). 'demote' when a
wrong-verdict / divergent-cluster drops it sub-bar.

Tests drive the REAL graduation.evaluate over a synthetic consequence ledger
emitted into a tmp CABINET_EVENT_LOG_DIR (the same fixture pattern F0 uses),
so the bar, the cell-key re-key, and the ratios are all the live code paths.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.fidelity.consequence import DIRECT_DEMOTE_REF, emit_consequence
from framework.fidelity import graduation


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    """Isolate the consequence ledger to a tmp dir (mirrors F0's fixture)."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


_NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _emit(
    *,
    ts: str,
    subject: str,
    verdict: str | None = "confirmed",
    status: str = "ok",
    decision: str = "approved",
    actor=None,
    lane: str = "polads",
    action_type: str = "internal_message",
    refs=None,
):
    """Emit one fully-decided consequence row into the tmp ledger."""
    actor = actor or {"kind": "officer", "id": "cos"}
    outcome = {"status": status, "evidence": None if status == "unknown" else "ev"}
    review = {"verdict": verdict} if verdict is not None else None
    emit_consequence(
        ts=ts,
        actor=actor,
        lane=lane,
        action=f"act-{subject}",
        subject=subject,
        action_type=action_type,
        refs=refs,
        proposal={
            "required": True,
            "decision": decision,
            "decided_at": ts if decision else None,
        },
        outcome=outcome,
        review=review,
    )


def _emit_n(
    n: int,
    *,
    verdict: str = "confirmed",
    status: str = "ok",
    action_type: str = "local_edit",
    lane: str = "polads",
    actor=None,
    start_days_ago: int = 60,
    spacing_days: float = 1.0,
):
    """Emit n decided rows for one cell, oldest first, ending well before _NOW."""
    for i in range(n):
        ts = _iso(_NOW - timedelta(days=start_days_ago - i * spacing_days))
        _emit(
            ts=ts,
            subject=f"s{i}",
            verdict=verdict,
            status=status,
            action_type=action_type,
            lane=lane,
            actor=actor,
        )


# A cell whose action_type maps to the `reversible` risk_class (default bar).
REVERSIBLE_CELL = ("officer:cos", "polads", "local_edit")
INTERNAL_CELL = ("officer:cos", "polads", "internal_message")
DEPLOY_CELL = ("officer:cos", "polads", "vercel_deploy_preview")


# --------------------------------------------------------------------------
# 1. unmeasured — no data
# --------------------------------------------------------------------------

class TestUnmeasured:
    def test_no_data_is_unmeasured(self):
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] == "unmeasured"
        assert "evidence" in out

    def test_samples_but_no_review_verdicts_is_unmeasured(self):
        # rows exist but every review verdict is unknown -> review_confirmed_rate
        # denominator is 0 -> None -> unmeasured (never silently eligible).
        for i in range(25):
            ts = _iso(_NOW - timedelta(days=60 - i))
            _emit(ts=ts, subject=f"s{i}", verdict="unknown", status="unknown",
                  action_type="local_edit")
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] == "unmeasured"


# --------------------------------------------------------------------------
# 2. propose_only — measured but sub-bar (not enough samples / below match)
# --------------------------------------------------------------------------

class TestProposeOnly:
    def test_too_few_samples_is_propose_only(self):
        # clean confirms but only 5 samples < bar.samples (20) -> not graduated.
        _emit_n(5, verdict="confirmed", action_type="local_edit")
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] == "propose_only"

    def test_below_match_rate_is_propose_only(self):
        # 25 samples but only ~0.6 confirmed -> below 0.85 default bar, but the
        # wrong rate is too diffuse to be a demote cluster in the last 10.
        for i in range(25):
            ts = _iso(_NOW - timedelta(days=120 - i * 2))
            v = "confirmed" if i % 5 != 0 else "wrong"  # 1-in-5 wrong, spread out
            _emit(ts=ts, subject=f"s{i}", verdict=v, action_type="local_edit")
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] in ("propose_only", "demote")
        # The point: it is NOT graduated/eligible (below the 0.85 match bar).
        assert out["state"] != "graduated"
        assert out["state"] != "eligible"


# --------------------------------------------------------------------------
# 3. eligible / graduated — clears the bar
# --------------------------------------------------------------------------

class TestGraduated:
    def test_clean_full_bar_is_graduated(self):
        # 25 clean confirms, last one >14d ago -> clears default bar fully.
        _emit_n(25, verdict="confirmed", status="ok", action_type="local_edit",
                start_days_ago=60, spacing_days=1.0)
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] == "graduated"
        ev = out["evidence"]
        assert ev["sample_count"] >= 20
        assert ev["match_rate"] >= 0.85

    def test_recency_not_yet_clean_is_eligible_not_graduated(self):
        # 25 clean confirms but the most recent sample is only 3 days old, so
        # recency_clean (days since last sample / since last wrong) < 14d.
        _emit_n(25, verdict="confirmed", status="ok", action_type="local_edit",
                start_days_ago=27, spacing_days=1.0)  # last sample ~3d ago
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] == "eligible"
        assert out["state"] != "graduated"

    def test_internal_comms_uses_tighter_bar_from_yaml(self):
        # internal_comms override bar is 0.90/30/0/21. 25 clean confirms would
        # graduate a reversible (default 20) cell, but is BELOW the internal
        # samples floor (30) -> not graduated.
        _emit_n(25, verdict="confirmed", status="ok",
                action_type="internal_message", start_days_ago=80, spacing_days=1.0)
        out = graduation.evaluate(INTERNAL_CELL, now=_NOW)
        assert out["state"] != "graduated"  # 25 < 30 samples floor


# --------------------------------------------------------------------------
# 4. demote — a wrong verdict / divergent cluster drops it sub-bar
# --------------------------------------------------------------------------

class TestDemote:
    def test_divergent_cluster_in_last10_demotes(self):
        # 25 historic clean confirms, then 2 wrongs in the most recent 10
        # (>=2 divergent in last 10 = demote trigger, tighter than promote <=1).
        _emit_n(25, verdict="confirmed", status="ok", action_type="local_edit",
                start_days_ago=120, spacing_days=2.0)
        # two fresh wrongs (most recent window)
        _emit(ts=_iso(_NOW - timedelta(days=2)), subject="w1", verdict="wrong",
              status="failed", action_type="local_edit")
        _emit(ts=_iso(_NOW - timedelta(days=1)), subject="w2", verdict="wrong",
              status="failed", action_type="local_edit")
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] == "demote"

    def test_single_fresh_wrong_is_not_graduated(self):
        # One fresh wrong verdict breaks the recency-clean streak -> cannot be
        # graduated even with an otherwise strong history.
        _emit_n(25, verdict="confirmed", status="ok", action_type="local_edit",
                start_days_ago=120, spacing_days=2.0)
        _emit(ts=_iso(_NOW - timedelta(days=1)), subject="w1", verdict="wrong",
              status="failed", action_type="local_edit")
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] != "graduated"

    def test_single_plain_wrong_alone_does_not_demote(self):
        # Contrast baseline for B2.9: ONE plain wrong (no fabrication marker) is
        # 1 divergent < 2 -> NOT a demote (it's eligible/propose_only, not demote).
        _emit_n(25, verdict="confirmed", status="ok", action_type="local_edit",
                start_days_ago=120, spacing_days=2.0)
        _emit(ts=_iso(_NOW - timedelta(days=1)), subject="w1", verdict="wrong",
              status="failed", action_type="local_edit")
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] != "demote"

    def test_single_fabrication_demotes_directly(self):
        # B2.9: ONE B2.8-verified fabrication (wrong + DIRECT_DEMOTE_REF) demotes
        # directly, even though divergent_last10 == 1 < the ≥2 cluster threshold.
        _emit_n(25, verdict="confirmed", status="ok", action_type="local_edit",
                start_days_ago=120, spacing_days=2.0)
        _emit(ts=_iso(_NOW - timedelta(days=1)), subject="fab", verdict="wrong",
              status="failed", action_type="local_edit",
              refs=[DIRECT_DEMOTE_REF, "verdict-kind:fabrication"])
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] == "demote"
        assert out["evidence"]["fabrication_demote"] is True
        assert out["evidence"]["divergent_last10"] == 1   # single sample, yet demoted

    def test_aged_out_fabrication_no_longer_bites(self):
        # Symmetric ramp-down: a fabrication older than the last-10-scored window
        # (10 clean confirms after it) no longer demotes.
        _emit(ts=_iso(_NOW - timedelta(days=60)), subject="oldfab", verdict="wrong",
              status="failed", action_type="local_edit",
              refs=[DIRECT_DEMOTE_REF])
        _emit_n(12, verdict="confirmed", status="ok", action_type="local_edit",
                start_days_ago=40, spacing_days=2.0)
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["evidence"]["fabrication_demote"] is False
        assert out["state"] != "demote"


# --------------------------------------------------------------------------
# 5. the bar is READ from the yaml, not hardcoded
# --------------------------------------------------------------------------

class TestBarReadFromYaml:
    def test_evaluate_uses_a_patched_bar(self, monkeypatch):
        # If the bar truly comes from authority-matrix.yml (via the matrix
        # loader), monkeypatching the loaded bar must change the verdict. Drop
        # the default samples floor to 3 and a 5-sample clean cell graduates.
        real_load = graduation._load_bars

        def fake_bars():
            bars = real_load()
            bars = {k: dict(v) for k, v in bars.items()}
            bars["default"]["samples"] = 3
            bars["default"]["recency_clean_days"] = 14
            return bars

        monkeypatch.setattr(graduation, "_load_bars", fake_bars)
        _emit_n(5, verdict="confirmed", status="ok", action_type="local_edit",
                start_days_ago=60, spacing_days=1.0)
        out = graduation.evaluate(REVERSIBLE_CELL, now=_NOW)
        assert out["state"] == "graduated"  # 5 >= patched floor of 3

    def test_default_bar_values_come_from_the_shipped_yaml(self):
        # The bar dict graduation reads must match the shipped YAML floor — i.e.
        # graduation does NOT carry a second hardcoded bar (A0 reconciled-bar).
        from framework.authority.matrix import load_matrix, matrix_policy
        policy = matrix_policy(load_matrix())
        yaml_bars = policy["bars"]
        loaded = graduation._load_bars()
        assert loaded["default"] == yaml_bars["default"]
        assert loaded["internal_comms"] == yaml_bars["internal_comms"]
        assert loaded["deploy_nonprod"] == yaml_bars["deploy_nonprod"]

    def test_bar_for_cell_selects_risk_class_override(self):
        # internal_message maps to the internal_comms risk_class -> its bar
        # override (samples 30) is selected, not the default (20).
        bar = graduation._bar_for_action_type("internal_message")
        assert bar["samples"] == 30
        assert bar["match_rate"] == 0.90
        # a reversible action_type falls back to the default bar.
        dbar = graduation._bar_for_action_type("local_edit")
        assert dbar["samples"] == 20
        assert dbar["match_rate"] == 0.85
