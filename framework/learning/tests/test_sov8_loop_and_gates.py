"""SOV-8 Ring-1 edit tests — loop code-diff routing (never _apply_proposal),
guardian A/A on the loop, posture-aware can_install, and sovereign
evals-green skill auto-promotion."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.events.emitter import replay  # noqa: E402
from framework.learning import self_improvement_loop as sil  # noqa: E402
from framework.learning import skill_induction  # noqa: E402
from framework.learning.capability_gaps import (  # noqa: E402
    approve_gap, can_install, decline_gap)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_PRODUCT_SLUG", "testprod")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CABINET_POSTURE", raising=False)
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    monkeypatch.setattr(
        sil, "_validation_gate",
        lambda: (True, {"scenario_passed": True, "golden_passed": True}))
    yield


def _force_posture(monkeypatch, posture: str) -> None:
    monkeypatch.setattr(sil, "_resolve_posture_safe", lambda: posture)


def _code_diff_proposal(pid="prop-code-1", kind="code_change"):
    return {
        "proposal_id": pid,
        "role_slug": "engineering",
        "trigger": {"failure_type": "runtime_error"},
        "suggested_change": {
            "kind": kind,
            "rationale": "fix the thing",
            "diff": ("diff --git a/framework/learning/x.py b/framework/learning/x.py\n"
                     "--- a/framework/learning/x.py\n"
                     "+++ b/framework/learning/x.py\n"
                     "@@ -1 +1 @@\n-a\n+b\n"),
        },
    }


def _seed_proposal_on_disk(tmp_path, proposal) -> Path:
    import yaml
    pdir = tmp_path / "instance" / "roles" / "proposals"
    pdir.mkdir(parents=True, exist_ok=True)
    path = pdir / f"{proposal['proposal_id']}.yml"
    path.write_text(yaml.safe_dump(proposal, sort_keys=False))
    return path


# ---------------------------------------------------------------------------
# Code-diff proposals — gate.ratify, never _apply_proposal
# ---------------------------------------------------------------------------

class TestCodeDiffRouting:
    def _run_loop_with(self, tmp_path, monkeypatch, proposal):
        path = _seed_proposal_on_disk(tmp_path, proposal)
        monkeypatch.setattr(sil, "propose_from_patterns",
                            lambda **kw: [(path, {"role_slug": "x"})])
        monkeypatch.setattr(sil, "propose_graduations", lambda **kw: [])
        monkeypatch.setattr(sil, "induce_drafts", lambda **kw: [])
        return sil.run_loop()

    def test_is_code_diff_proposal(self):
        assert sil._is_code_diff_proposal(_code_diff_proposal())
        assert sil._is_code_diff_proposal(_code_diff_proposal(kind="code_diff"))
        bare = {"suggested_change": {"kind": "add_hat", "diff": "diff --git ..."}}
        assert sil._is_code_diff_proposal(bare)  # diff field alone qualifies
        assert not sil._is_code_diff_proposal(
            {"suggested_change": {"kind": "add_hat"}})

    def test_never_reaches_apply_proposal(self, tmp_path, monkeypatch):
        def bomb(*a, **kw):
            raise AssertionError("_apply_proposal must never see a code diff")

        monkeypatch.setattr(sil, "_apply_proposal", bomb)
        ratified: list[dict[str, Any]] = []

        import framework.learning.gate as gate

        def fake_ratify(p, **kw):
            ratified.append(p)
            return {"pack_id": "pack-x", "verdict": "pass",
                    "applies_nothing": True}

        monkeypatch.setattr(gate, "ratify", fake_ratify)
        summary = self._run_loop_with(tmp_path, monkeypatch,
                                      _code_diff_proposal())
        detail = summary["proposals"]["detail"]
        assert [d["status"] for d in detail] == ["gate_pass"]
        assert ratified and ratified[0]["diff"].startswith("diff --git")
        assert summary["proposals"]["auto_applied"] == 0

    def test_gate_refusal_status_recorded(self, tmp_path, monkeypatch):
        import framework.learning.gate as gate
        monkeypatch.setattr(
            gate, "ratify",
            lambda p, **kw: {"pack_id": "pack-y", "verdict": "refused"})
        summary = self._run_loop_with(tmp_path, monkeypatch,
                                      _code_diff_proposal("prop-code-2"))
        assert [d["status"] for d in summary["proposals"]["detail"]] == \
            ["gate_refused"]

    def test_broken_gate_parks_for_captain(self, tmp_path, monkeypatch):
        import framework.learning.gate as gate
        monkeypatch.setattr(
            gate, "ratify",
            lambda p, **kw: (_ for _ in ()).throw(RuntimeError("gate down")))
        summary = self._run_loop_with(tmp_path, monkeypatch,
                                      _code_diff_proposal("prop-code-3"))
        assert [d["status"] for d in summary["proposals"]["detail"]] == \
            ["pending_captain_approval"]
        assert summary["proposals"]["auto_applied"] == 0


# ---------------------------------------------------------------------------
# Guardian A/A on the loop — no posture config ⇒ bit-identical behavior
# ---------------------------------------------------------------------------

class TestGuardianAAOnLoop:
    def test_summary_shape_identical_with_and_without_posture_module(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(sil, "propose_from_patterns", lambda **kw: [])
        monkeypatch.setattr(sil, "propose_graduations", lambda **kw: [])
        monkeypatch.setattr(sil, "induce_drafts", lambda **kw: [])

        def _normalize(s):
            s = dict(s)
            s.pop("loop_id", None)
            s.pop("parent_event_id", None)
            return json.dumps(s, sort_keys=True, default=str)

        baseline = sil.run_loop()
        # …now with the posture module actively broken: still identical.
        import framework.authority.posture as posture_mod
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: (_ for _ in ()).throw(OSError()))
        broken = sil.run_loop()
        assert _normalize(baseline) == _normalize(broken)
        # guardian summary never carries sovereign-only keys
        assert "auto_validated" not in baseline["skill_induction"]
        assert "posture" not in baseline

    def test_guardian_never_promotes_skills(self, tmp_path, monkeypatch):
        _force_posture(monkeypatch, "guardian")
        draft = self._seed_draft(tmp_path)
        monkeypatch.setattr(sil, "propose_from_patterns", lambda **kw: [])
        monkeypatch.setattr(sil, "propose_graduations", lambda **kw: [])
        monkeypatch.setattr(sil, "induce_drafts", lambda **kw: [draft])
        summary = sil.run_loop()
        assert "auto_validated" not in summary["skill_induction"]
        assert skill_induction.draft_status(draft) == "draft"
        statuses = {(ev.get("payload") or {}).get("status")
                    for ev in replay(event_types=["skill_promoted"])}
        assert statuses == {"draft_promoted"}

    @staticmethod
    def _seed_draft(tmp_path) -> Path:
        sdir = tmp_path / "memory" / "skills" / "evolved"
        sdir.mkdir(parents=True, exist_ok=True)
        p = sdir / "induced-pattern-test-signal.md"
        p.write_text("---\nname: induced-pattern-test-signal\n"
                     "status: draft\n---\n\n# Induced Skill\n\nbody\n")
        return p


# ---------------------------------------------------------------------------
# Sovereign skill auto-promotion — evals-green only
# ---------------------------------------------------------------------------

class TestSovereignSkillPromotion:
    def _loop_with_draft(self, tmp_path, monkeypatch, **loop_kw):
        draft = TestGuardianAAOnLoop._seed_draft(tmp_path)
        monkeypatch.setattr(sil, "propose_from_patterns", lambda **kw: [])
        monkeypatch.setattr(sil, "propose_graduations", lambda **kw: [])
        monkeypatch.setattr(sil, "induce_drafts", lambda **kw: [draft])
        return draft, sil.run_loop(**loop_kw)

    def test_sovereign_evals_green_promotes(self, tmp_path, monkeypatch):
        _force_posture(monkeypatch, "sovereign")
        draft, summary = self._loop_with_draft(tmp_path, monkeypatch)
        assert skill_induction.draft_status(draft) == "validated"
        assert summary["skill_induction"]["auto_validated"] == 1
        events = replay(event_types=["skill_promoted"])
        auto = [ev for ev in events
                if (ev.get("payload") or {}).get("status") == "auto_validated"]
        assert len(auto) == 1
        assert auto[0]["payload"]["posture"] == "sovereign"
        assert "promoted_by: self_improvement_loop" in draft.read_text()

    def test_sovereign_evals_red_never_promotes(self, tmp_path, monkeypatch):
        _force_posture(monkeypatch, "sovereign")
        monkeypatch.setattr(sil, "_validation_gate",
                            lambda: (False, {"scenario_passed": False,
                                             "golden_passed": True}))
        draft, summary = self._loop_with_draft(tmp_path, monkeypatch)
        assert skill_induction.draft_status(draft) == "draft"
        assert "auto_validated" not in summary["skill_induction"]

    def test_skip_evals_never_promotes_even_sovereign(self, tmp_path,
                                                      monkeypatch):
        _force_posture(monkeypatch, "sovereign")
        draft, summary = self._loop_with_draft(tmp_path, monkeypatch,
                                               skip_evals=True)
        assert skill_induction.draft_status(draft) == "draft"
        assert "auto_validated" not in summary["skill_induction"]

    def test_promote_draft_is_idempotent_and_draft_only(self, tmp_path):
        draft = TestGuardianAAOnLoop._seed_draft(tmp_path)
        assert skill_induction.promote_draft(draft) is True
        assert skill_induction.draft_status(draft) == "validated"
        assert skill_induction.promote_draft(draft) is False  # not draft anymore
        assert skill_induction.promote_draft(tmp_path / "ghost.md") is False


# ---------------------------------------------------------------------------
# can_install — posture-aware, ceiling absolute, decline absolute
# ---------------------------------------------------------------------------

class TestCanInstallPostureAware:
    GAP = "gap-cafe0001"

    def _evidence(self, tmp_path, verdict="pass"):
        edir = tmp_path / "shared" / "interfaces" / "gate-evidence"
        edir.mkdir(parents=True, exist_ok=True)
        (edir / "pack-deadbeef00000000.json").write_text(json.dumps({
            "pack_id": "pack-deadbeef00000000", "gap_id": self.GAP,
            "verdict": verdict, "ts": "2026-07-05T00:00:00Z",
            "applies_nothing": True}))

    def _sovereign(self, monkeypatch):
        import framework.authority.posture as posture_mod
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: "sovereign")

    def test_guardian_no_decision_stays_false(self, tmp_path):
        self._evidence(tmp_path)
        assert can_install(self.GAP) is False

    def test_approved_still_true_any_posture(self):
        approve_gap(self.GAP)
        assert can_install(self.GAP) is True

    def test_sovereign_plus_gate_evidence_allows(self, tmp_path, monkeypatch):
        self._evidence(tmp_path)
        self._sovereign(monkeypatch)
        assert can_install(self.GAP) is True

    def test_sovereign_without_evidence_is_false(self, monkeypatch):
        self._sovereign(monkeypatch)
        assert can_install(self.GAP) is False

    def test_sovereign_with_failing_evidence_is_false(self, tmp_path,
                                                      monkeypatch):
        self._evidence(tmp_path, verdict="fail")
        self._sovereign(monkeypatch)
        assert can_install(self.GAP) is False

    def test_captain_decline_beats_machine_evidence(self, tmp_path,
                                                    monkeypatch):
        self._evidence(tmp_path)
        self._sovereign(monkeypatch)
        decline_gap(self.GAP, reason="no")
        assert can_install(self.GAP) is False

    def test_ceiling_touch_absolute_even_sovereign_with_evidence(
            self, tmp_path, monkeypatch):
        self._evidence(tmp_path)
        self._sovereign(monkeypatch)
        approve_gap(self.GAP)  # even an approval cannot cross the ceiling
        assert can_install(self.GAP, touches={"secrets"}) is False
        assert can_install(self.GAP, touches={"external_comms"}) is False

    def test_fail_closed_on_evidence_reader_error(self, tmp_path, monkeypatch):
        self._sovereign(monkeypatch)
        import framework.learning.gate as gate
        monkeypatch.setattr(
            gate, "evidence_verdict",
            lambda **kw: (_ for _ in ()).throw(OSError("disk")))
        assert can_install(self.GAP) is False
