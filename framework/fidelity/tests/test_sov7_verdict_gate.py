"""SOV-7 / D16 — verdict_gate machine promotion, sovereign-only.

_REVIEW_SOURCES gains "verdict_gate" (stamped upstream by the learning gate's
run_gate_review for acted rows clearing its full machine bar). compute_ratios
counts a gate confirm toward `confirmed` (promotion fuel) ONLY while the
posture resolves sovereign AT COMPUTE TIME; guardian ignores it, any resolver
failure is guardian (fail-closed), and `wrong` counts from any source in both
postures. Posture is read per compute, so a sovereign→guardian flip only ever
REDUCES confirmed counts — pinned below.

These tests are trust-path (consequence) — they run on lib-less installs too.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.authority import posture as posture_mod
from framework.fidelity.consequence import (
    ConsequenceValidationError,
    _REVIEW_SOURCES,
    _gate_confirms_now,
    compute_ratios,
    emit_consequence,
    validate_consequence,
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Isolate the ledger AND the posture resolution: CABINET_ROOT points at
    an empty tmp tree (no posture.yml ⇒ guardian), no CABINET_POSTURE env, so
    the default world in every test is honestly guardian."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("CABINET_POSTURE", raising=False)
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return tmp_path


def _emit_reviewed(subject, verdict, source, ts="2026-07-04T08:00:00+00:00"):
    """One acted+reviewed ledger row with an attributed review source."""
    review = {"verdict": verdict}
    if source is not None:
        review["source"] = source
    emit_consequence(
        ts=ts, actor={"kind": "officer", "id": "cos"}, lane="polads",
        action=f"act-{subject}", subject=subject,
        action_type="internal_message",
        proposal={"required": True, "decision": "approved",
                  "decided_at": ts},
        outcome={"status": "ok", "evidence": "ev"},
        review=review,
    )


_CELL = ("officer:cos", "polads", "internal_message")


# ---------------------------------------------------------------------------
# vocabulary — the schema accepts the new source, rejects drift
# ---------------------------------------------------------------------------

class TestReviewSourceVocabulary:
    def test_verdict_gate_in_sources(self):
        assert "verdict_gate" in _REVIEW_SOURCES

    def test_validate_accepts_verdict_gate(self):
        ev = {
            "ts": "2026-07-04T08:00:00+00:00",
            "actor": {"kind": "officer", "id": "cos"},
            "lane": "polads", "action": "a", "subject": "s",
            "review": {"verdict": "confirmed", "source": "verdict_gate"},
        }
        assert validate_consequence(ev) is None

    def test_validate_still_rejects_unknown_source(self):
        ev = {
            "ts": "2026-07-04T08:00:00+00:00",
            "actor": {"kind": "officer", "id": "cos"},
            "lane": "polads", "action": "a", "subject": "s",
            "review": {"verdict": "confirmed", "source": "verdict_wishful"},
        }
        with pytest.raises(ConsequenceValidationError, match="review.source"):
            validate_consequence(ev)


# ---------------------------------------------------------------------------
# _gate_confirms_now — fail-closed posture read
# ---------------------------------------------------------------------------

class TestGateConfirmsNow:
    def test_guardian_default_world_is_false(self):
        # no posture.yml under CABINET_ROOT ⇒ resolve_posture ⇒ guardian
        assert _gate_confirms_now() is False

    def test_sovereign_resolution_is_true(self, monkeypatch):
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        assert _gate_confirms_now() is True

    def test_resolver_exception_is_guardian(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("posture backend down")
        monkeypatch.setattr(posture_mod, "resolve_posture", boom)
        assert _gate_confirms_now() is False


# ---------------------------------------------------------------------------
# compute_ratios — sovereign-gated promotion fuel
# ---------------------------------------------------------------------------

class TestVerdictGateCounting:
    def _seed(self):
        _emit_reviewed("h1", "confirmed", "verdict_human")
        _emit_reviewed("g1", "confirmed", "verdict_gate")
        _emit_reviewed("g2", "confirmed", "verdict_gate")

    def test_guardian_ignores_gate_confirms(self):
        """Default (no posture config) ⇒ guardian ⇒ gate confirms are inert;
        only the human confirm fuels the cell — bit-identical to the
        pre-D16 flavor-A split."""
        self._seed()
        cell = compute_ratios()[_CELL]
        assert cell.confirmed == 1

    def test_sovereign_counts_gate_confirms(self, monkeypatch):
        self._seed()
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        cell = compute_ratios()[_CELL]
        assert cell.confirmed == 3  # human + both gate confirms

    def test_wrong_counts_from_gate_in_both_postures(self, monkeypatch):
        """Machine evidence may demote in EVERY posture — wrong is never
        posture-gated (EARN-DEMOTION: evidence beats posture)."""
        _emit_reviewed("w1", "wrong", "verdict_gate")
        cell = compute_ratios()[_CELL]
        assert cell.wrong == 1  # guardian
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        cell = compute_ratios()[_CELL]
        assert cell.wrong == 1  # sovereign — unchanged

    def test_flip_to_guardian_only_reduces_confirmed(self, monkeypatch):
        """Posture is read at COMPUTE time: the same ledger yields fewer (or
        equal) confirmed under guardian than under sovereign — gate fuel is
        revocable, never grandfathered (D16 pin)."""
        self._seed()
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        sovereign_cell = compute_ratios()[_CELL]
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "guardian")
        guardian_cell = compute_ratios()[_CELL]
        assert guardian_cell.confirmed <= sovereign_cell.confirmed
        assert sovereign_cell.confirmed == 3
        assert guardian_cell.confirmed == 1  # only the human confirm survives
        # everything not gate-sourced is posture-invariant
        assert guardian_cell.wrong == sovereign_cell.wrong
        assert guardian_cell.approved == sovereign_cell.approved
        assert guardian_cell.ok == sovereign_cell.ok
        assert guardian_cell.sample_count == sovereign_cell.sample_count

    def test_resolver_exception_drops_gate_confirms(self, monkeypatch):
        """A broken posture backend fails CLOSED: gate confirms are not
        counted (guardian semantics), the compute itself never raises."""
        self._seed()

        def boom(*a, **k):
            raise RuntimeError("redis down")
        monkeypatch.setattr(posture_mod, "resolve_posture", boom)
        cell = compute_ratios()[_CELL]
        assert cell.confirmed == 1

    def test_posture_never_read_without_gate_rows(self, monkeypatch):
        """Guardian bit-identity is structural: a ledger with NO verdict_gate
        confirm never touches the posture resolver at all."""
        _emit_reviewed("h1", "confirmed", "verdict_human")
        _emit_reviewed("j1", "confirmed", "verdict_judge")
        _emit_reviewed("w1", "wrong", "verdict_gate")  # wrong needs no posture

        def tripwire(*a, **k):
            raise AssertionError("resolve_posture consulted without a "
                                 "verdict_gate confirm in the ledger")
        monkeypatch.setattr(posture_mod, "resolve_posture", tripwire)
        cell = compute_ratios()[_CELL]
        assert cell.confirmed == 1
        assert cell.wrong == 1

    def test_judge_and_legacy_confirms_still_inert_in_sovereign(
            self, monkeypatch):
        """D16 widens ONLY verdict_gate: verdict_judge and unattributed
        confirms stay promotion-inert even in sovereign (the flavor-A
        contract is narrowed, not dissolved)."""
        _emit_reviewed("j1", "confirmed", "verdict_judge")
        _emit_reviewed("l1", "confirmed", None)
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        cell = compute_ratios()[_CELL]
        assert cell.confirmed == 0

    def test_env_drop_brake_narrows_gate_fuel(self, monkeypatch, tmp_path):
        """CABINET_POSTURE=guardian (the emergency drop-brake) wins over any
        config — gate confirms stop counting through the REAL resolver."""
        self._seed()
        monkeypatch.setenv("CABINET_POSTURE", "guardian")
        cell = compute_ratios()[_CELL]
        assert cell.confirmed == 1
