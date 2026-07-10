"""SOV-7 / D16 — verdict_gate machine promotion, sovereign-only.

_REVIEW_SOURCES gains "verdict_gate" (stamped upstream by the learning gate's
run_gate_review for acted rows clearing its full machine bar). compute_ratios
counts a gate confirm toward `confirmed` (promotion fuel) ONLY while the
posture resolves sovereign AT COMPUTE TIME; guardian ignores it, any resolver
failure is guardian (fail-closed), and `wrong` counts from any source in both
postures. Posture is read per compute, so a sovereign→guardian flip only ever
REDUCES confirmed counts — pinned below.

[CG-1 Option B, ruled 2026-07-07] narrows the sovereign leg further, pinned in
TestCG1OptionBScope below: a gate confirm counts ONLY for deterministic-
inverse machine evidence (action_type admissible per the existing undo
registry, _det_inverse_gate_fuel_types) AND only in label-floor-met periods
(_label_floor_met — fail-closed False until the A3 sensor exists). The
pre-CG-1 sovereign-count pins are updated accordingly: seeds use a
deterministic-inverse action_type (board_status) with the label floor
monkeypatched met.

These tests are trust-path (consequence) — they run on lib-less installs too.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.authority import posture as posture_mod
from framework.fidelity import consequence as consequence_mod
from framework.fidelity.consequence import (
    ConsequenceValidationError,
    _REVIEW_SOURCES,
    _det_inverse_gate_fuel_types,
    _gate_confirms_now,
    _label_floor_met,
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


def _emit_reviewed(subject, verdict, source, ts="2026-07-04T08:00:00+00:00",
                   action_type="internal_message"):
    """One acted+reviewed ledger row with an attributed review source."""
    review = {"verdict": verdict}
    if source is not None:
        review["source"] = source
    emit_consequence(
        ts=ts, actor={"kind": "officer", "id": "cos"}, lane="bakery",
        action=f"act-{subject}", subject=subject,
        action_type=action_type,
        proposal={"required": True, "decision": "approved",
                  "decided_at": ts},
        outcome={"status": "ok", "evidence": "ev"},
        review=review,
    )


_CELL = ("officer:cos", "bakery", "internal_message")
# [CG-1 Option B] board_status is deterministic-inverse-backed (registered
# monday_compare_restore inverse via ACTION_TYPE_MAP monday_task_update) — the
# admissible-fuel cell the sovereign-count pins seed.
_PM_CELL = ("officer:cos", "bakery", "board_status")


def _floor_met(monkeypatch):
    """Mark every period label-floor-met — the A3 seam patched open so a pin
    can isolate the OTHER conditions (the real default is fail-closed False)."""
    monkeypatch.setattr(consequence_mod, "_label_floor_met", lambda ts: True)


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
            "lane": "bakery", "action": "a", "subject": "s",
            "review": {"verdict": "confirmed", "source": "verdict_gate"},
        }
        assert validate_consequence(ev) is None

    def test_validate_still_rejects_unknown_source(self):
        ev = {
            "ts": "2026-07-04T08:00:00+00:00",
            "actor": {"kind": "officer", "id": "cos"},
            "lane": "bakery", "action": "a", "subject": "s",
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
        # [CG-1 Option B] seeds live on the deterministic-inverse board_status
        # cell — the only kind of cell whose gate confirms may count at all.
        _emit_reviewed("h1", "confirmed", "verdict_human",
                       action_type="board_status")
        _emit_reviewed("g1", "confirmed", "verdict_gate",
                       action_type="board_status")
        _emit_reviewed("g2", "confirmed", "verdict_gate",
                       action_type="board_status")

    def test_guardian_ignores_gate_confirms(self, monkeypatch):
        """Default (no posture config) ⇒ guardian ⇒ gate confirms are inert
        even with the label floor met on an admissible cell; only the human
        confirm fuels it — bit-identical to the pre-D16 flavor-A split."""
        self._seed()
        _floor_met(monkeypatch)
        cell = compute_ratios()[_PM_CELL]
        assert cell.confirmed == 1

    def test_sovereign_counts_gate_confirms(self, monkeypatch):
        """Sovereign + deterministic-inverse cell + label-floor-met period:
        the full CG-1 Option B conjunction — gate confirms count."""
        self._seed()
        _floor_met(monkeypatch)
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        cell = compute_ratios()[_PM_CELL]
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
        _floor_met(monkeypatch)
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        sovereign_cell = compute_ratios()[_PM_CELL]
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "guardian")
        guardian_cell = compute_ratios()[_PM_CELL]
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
        _floor_met(monkeypatch)

        def boom(*a, **k):
            raise RuntimeError("redis down")
        monkeypatch.setattr(posture_mod, "resolve_posture", boom)
        cell = compute_ratios()[_PM_CELL]
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
        confirms stay promotion-inert even in sovereign with the floor met on
        an admissible cell (the flavor-A contract is narrowed, not dissolved).
        [CG-1 Option B] The judge-calibration >=0.8 precondition attaches to
        verdict_judge — and until CG-10 admits calibrated judge confirms by
        germline amendment, NO calibration score changes this pin."""
        _emit_reviewed("j1", "confirmed", "verdict_judge",
                       action_type="board_status")
        _emit_reviewed("l1", "confirmed", None, action_type="board_status")
        _floor_met(monkeypatch)
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        cell = compute_ratios()[_PM_CELL]
        assert cell.confirmed == 0

    def test_env_drop_brake_narrows_gate_fuel(self, monkeypatch, tmp_path):
        """CABINET_POSTURE=guardian (the emergency drop-brake) wins over any
        config — gate confirms stop counting through the REAL resolver."""
        self._seed()
        _floor_met(monkeypatch)
        monkeypatch.setenv("CABINET_POSTURE", "guardian")
        cell = compute_ratios()[_PM_CELL]
        assert cell.confirmed == 1


# ---------------------------------------------------------------------------
# CG-1 Option B (ruled 2026-07-07) — deterministic-inverse + label-floor scope
# ---------------------------------------------------------------------------

class TestCG1OptionBScope:
    """Pins for the CG-1 Option B narrowing (captain-decisions.md 2026-07-07):
    sovereign verdict_gate fuel is scoped to deterministic-inverse machine
    evidence only, and ttl_ok-derived confirms count only in label-floor-met
    periods. Strictly narrowing — every pin here proves fuel that does NOT
    mint; the only positive control is the full conjunction."""

    def test_non_det_inverse_machine_evidence_mints_no_fuel(self, monkeypatch):
        """A verdict_gate confirm on a NON-deterministic-inverse action_type
        (internal_message has no registered inverse) never counts — even in
        sovereign with the label floor met. The human confirm on the same
        cell still counts (the narrowing touches only machine fuel)."""
        _emit_reviewed("h1", "confirmed", "verdict_human")   # internal_message
        _emit_reviewed("g1", "confirmed", "verdict_gate")    # internal_message
        _floor_met(monkeypatch)
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        cell = compute_ratios()[_CELL]
        assert cell.confirmed == 1  # human only — the gate confirm is inert

    def test_ttl_ok_outside_label_floor_met_period_does_not_count(
            self, monkeypatch):
        """A gate confirm (ttl_ok-derived by run_gate_review's bar) on an
        ADMISSIBLE deterministic-inverse cell still does not count when the
        period is not label-floor-met — and the real, unpatched default is
        that NO period is label-floor-met until the A3 sensor exists."""
        _emit_reviewed("g1", "confirmed", "verdict_gate",
                       action_type="board_status")
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        cell = compute_ratios()[_PM_CELL]  # floor NOT patched — honest default
        assert cell.confirmed == 0

    def test_label_floor_default_is_fail_closed_false(self):
        """The A3 seam's shipped default: no sensor ⇒ no period is
        label-floor-met. Wiring A3 later can only widen from zero under an
        explicit change; silence from an absent Captain is never fuel."""
        assert _label_floor_met("2026-07-07T00:00:00Z") is False
        assert _label_floor_met("") is False

    def test_det_inverse_set_derives_from_the_undo_registry(self):
        """The admissible set reuses the EXISTING representation
        (action_undo.act_first_eligible over the inverse registry +
        action_lane.ACTION_TYPE_MAP) — no hand-kept list to drift."""
        admissible = _det_inverse_gate_fuel_types()
        # registered deterministic inverses ⇒ admissible
        assert "board_status" in admissible      # via monday_task_update
        assert "task_status_move" in admissible  # reversible kind, own inverse
        assert "label" in admissible
        assert "tier2_note" in admissible
        # no registered inverse ⇒ never fuel
        assert "internal_message" not in admissible
        assert "officer_dispatch" not in admissible   # delegate_work: op none
        assert "investigation_run" not in admissible  # read-only: op none

    def test_unavailable_registry_fails_closed_to_no_fuel(self, monkeypatch):
        """If the admissible set cannot be derived (registry unreachable), it
        is EMPTY — sovereign + floor-met still mints nothing."""
        _emit_reviewed("g1", "confirmed", "verdict_gate",
                       action_type="board_status")
        _floor_met(monkeypatch)
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        monkeypatch.setattr(consequence_mod, "_det_inverse_gate_fuel_types",
                            lambda: frozenset())
        cell = compute_ratios()[_PM_CELL]
        assert cell.confirmed == 0

    def test_wrong_still_demotes_regardless_of_scope(self, monkeypatch):
        """The narrowing touches CONFIRM fuel only: a wrong verdict on a
        non-admissible cell in a non-floor-met period still demotes (machine
        evidence may demote/hold from anywhere, never promote)."""
        _emit_reviewed("w1", "wrong", "verdict_gate")  # internal_message
        cell = compute_ratios()[_CELL]
        assert cell.wrong == 1
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")
        cell = compute_ratios()[_CELL]
        assert cell.wrong == 1
