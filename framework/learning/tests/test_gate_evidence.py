"""Phase 2 Batch B — learning/gate evidence self-recording tests.

Per-class recording contract (design §3 Phase 2 items 2b/3), proven here:

  * gate.ratify verdicts        → RECEIPT direct producer: degrade LOUD,
                                  never block; org emits + pack bytes stay
                                  byte-identical to BASE.
  * gate-apply APPLY (widening) → ACT-class FAIL-CLOSED: injected evidence
                                  failure ⇒ evidence_before_apply raises and
                                  the apply must refuse BEFORE mutation.
  * apply-watch ROLLBACK (brake)→ ACT-class with the brake exception:
                                  intent recorded before release; injected
                                  evidence failure degrades LOUD and the
                                  decision STILL releases (§2.6 asymmetry).
  * watch open/close, revert    → RECEIPTS: degrade LOUD, never block the
                                  outcomes                domain write.
  * per-pass "watch" decisions  → exhaust: never recorded.

No-double-recording: gate org classes stay pinned mirror-EXHAUST; loop and
trust classes stay mirror-only; a class flows through exactly one path.
Never-a-score: verdict evidence carries statuses only, no aggregates, and
its keys stay out of the officer projection.

Scratch stores ONLY: every call passes an explicit tmp root; the evidence
store is <root>/instance/evidence/v1 by construction — never the live store.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.learning import apply_watch, gate  # noqa: E402

NOW = "2026-07-05T12:00:00Z"
APPLIED = "2026-07-05T00:00:00Z"
IN_WINDOW = "2026-07-06T00:00:00Z"
PAST_WINDOW = "2026-07-08T00:00:01Z"
DAY_TRIAL = "evt-learning-gate-20260705"
SHA = "ab" * 32

_IMMUTABLE_CORE = """\
version: 1
lists: [germline-lock]
files:
  - path: framework/authority/matrix.py
dirs:
  - path: framework/policies/
"""


def _mkroot(tmp_path) -> Path:
    root = tmp_path / "cab"
    (root / "framework" / "policies").mkdir(parents=True)
    (root / "shared" / "interfaces").mkdir(parents=True)
    (root / "framework" / "policies" / "immutable-core.yml").write_text(
        _IMMUTABLE_CORE)
    return root


def _diff(path: str) -> str:
    return (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
            "@@ -1 +1 @@\n-x\n+y\n")


def _ok_runner(stage, spec):
    return {"ok": True, "detail": f"{stage} ok"}


def _ok_probe():
    return {"ok": True, "detail": "probe ok"}


# Scratch repos mirror the production layout via the ONE canonical store
# constant (the journey producer's EVIDENCE_REL) — never a re-typed literal.
from framework.onboarding.journey import EVIDENCE_REL  # noqa: E402

_EV_TOP = Path(EVIDENCE_REL).parts[0]


def _store(root: Path) -> Path:
    return root / EVIDENCE_REL


def _events(root: Path, trial_id: str) -> list[dict]:
    path = _store(root) / "trials" / trial_id / "events.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().split("\n")
            if line.strip()]


def _verify(root: Path, trial_id: str) -> dict:
    from framework.evidence.verifier import verify_trial
    return verify_trial(_store(root), trial_id)


def _break_store(root: Path) -> None:
    """Injected evidence-plane failure: the store parent is a regular FILE,
    so EvidenceRecorder construction cannot ever succeed."""
    (root / _EV_TOP).parent.mkdir(parents=True, exist_ok=True)
    (root / _EV_TOP).write_text("not a directory")


def _corrupt_ledger(root: Path, trial_id: str) -> None:
    """Injected integrity failure: garbage row in an existing trial ledger."""
    path = _store(root) / "trials" / trial_id / "events.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("not-json\n")


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    monkeypatch.delenv("CABINET_ROOT", raising=False)
    monkeypatch.delenv("CABINET_EVIDENCE_DIR", raising=False)
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    # Deterministic producer identity per test: reset the process-frozen
    # attestation (monkeypatch restores the prior value afterwards).
    from framework.evidence import identity
    monkeypatch.setattr(identity, "_ATTESTED", None)
    # Pin non-root (the house pattern): the producers refuse evidence
    # appends at euid 0 by construction; root-guard tests re-pin to 0.
    monkeypatch.setattr(gate.os, "geteuid", lambda: 501)
    monkeypatch.setattr(apply_watch.os, "geteuid", lambda: 501)


@pytest.fixture()
def root(tmp_path):
    return _mkroot(tmp_path)


def _org_capture(monkeypatch):
    captured: list[tuple[str, dict]] = []

    def fake_emit(event_type, *, actor=None, payload=None, **kw):
        captured.append((event_type, dict(payload or {})))
        return {"event_type": event_type}

    import framework.events.emitter as emitter
    monkeypatch.setattr(emitter, "emit", fake_emit)
    return captured


# ---------------------------------------------------------------------------
# gate.ratify — RECEIPT-class verdict evidence (degrade loud, never block)
# ---------------------------------------------------------------------------

class TestGateVerdictReceipt:
    def test_pass_records_one_signed_verdict_event(self, root):
        diff = _diff("framework/learning/x.py")
        pack = gate.ratify({"diff": diff, "gap_id": "gap-1234abcd",
                            "lane": "bakery"},
                           root=root, runner=_ok_runner, probe_fn=_ok_probe,
                           now=NOW)
        assert pack["verdict"] == "pass"
        events = _events(root, DAY_TRIAL)
        assert len(events) == 1
        ev = events[0]
        assert ev["phase"] == "verification" and ev["status"] == "verified"
        detail = ev["detail"]
        assert detail["action"] == "gate_ratify"
        assert detail["pack_id"] == pack["pack_id"]
        assert detail["sha256"] == gate.diff_sha256(diff)
        assert detail["verdict"] == "pass"
        assert detail["gap_id"] == "gap-1234abcd"
        assert detail["lane"] == "bakery"
        # per-stage STATUS summary only (statuses, never scores/counts)
        assert detail["stages"] == {
            "S0_scope": "pass", "S1_verify": "pass", "S2_falsifier": "pass",
            "S3_ceilings": "pass", "S4_archive": "pass", "S5_verdict": "pass",
        }
        assert f"gate-pack:{pack['pack_id']}" in ev["links"]
        # unattested library call → process-constant fallback identity
        assert ev["actor"] == {"kind": "system", "id": "learning-gate"}
        assert ev["component"]["name"] == "learning-gate"
        assert "attestation_mode" not in detail
        # determinism: stored bytes == hashed bytes, the trial verifies
        assert _verify(root, DAY_TRIAL)["ok"] is True

    def test_refused_verdict_cites_need_and_stage_statuses(self, root,
                                                           monkeypatch):
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        pack = gate.ratify(
            {"diff": _diff("framework/authority/matrix.py")},
            root=root, runner=_ok_runner, probe_fn=_ok_probe, now=NOW)
        assert pack["verdict"] == "refused"
        events = _events(root, DAY_TRIAL)
        assert len(events) == 1
        ev = events[0]
        assert ev["status"] == "refused"
        assert ev["detail"]["need_id"] == pack["need_id"]
        assert f"cabinet-need:{pack['need_id']}" in ev["links"]
        assert ev["detail"]["stages"]["S0_scope"] == "refused"
        assert ev["detail"]["stages"]["S1_verify"] == "skipped"

    def test_two_ratifies_share_the_day_trial(self, root):
        for name in ("a.py", "b.py"):
            gate.ratify({"diff": _diff(f"framework/learning/{name}")},
                        root=root, runner=_ok_runner, probe_fn=_ok_probe,
                        now=NOW)
        events = _events(root, DAY_TRIAL)
        assert len(events) == 2
        assert _verify(root, DAY_TRIAL)["ok"] is True

    def test_receipt_failure_never_blocks_ratify(self, root, monkeypatch,
                                                 capsys):
        _break_store(root)
        captured = _org_capture(monkeypatch)
        pack = gate.ratify({"diff": _diff("framework/learning/x.py")},
                           root=root, runner=_ok_runner, probe_fn=_ok_probe,
                           now=NOW)
        # the domain outcome is untouched: verdict, pack file, org emits
        assert pack["verdict"] == "pass"
        pack_file = (root / "shared" / "interfaces" / "gate-evidence" /
                     f"{pack['pack_id']}.json")
        assert json.loads(pack_file.read_text())["verdict"] == "pass"
        assert [t for t, _ in captured] == ["eval_run_started", "eval_passed"]
        # ...and the failure is LOUD
        assert "evidence not recorded" in capsys.readouterr().err

    def test_happy_path_outputs_identical_with_and_without_evidence_plane(
            self, tmp_path, monkeypatch):
        """BASE-count byte-stability: same org classes, same pack keys, same
        verdict whether the evidence plane is healthy or broken — recording
        is the only delta."""
        diff = _diff("framework/learning/x.py")
        packs, orgs = [], []
        for broken in (False, True):
            root = _mkroot(tmp_path / ("b" if broken else "a"))
            if broken:
                _break_store(root)
            captured = _org_capture(monkeypatch)
            packs.append(gate.ratify({"diff": diff}, root=root,
                                     runner=_ok_runner, probe_fn=_ok_probe,
                                     now=NOW))
            orgs.append([t for t, _ in captured])
        healthy, broken_pack = packs
        assert healthy == broken_pack  # identical pack dicts
        assert orgs[0] == orgs[1] == ["eval_run_started", "eval_passed"]
        # correlation flows one-way: no evidence/trial key leaks into packs
        assert set(healthy) == {"pack_id", "proposal_id", "gap_id", "lane",
                                "summary", "sha256", "ts", "stages",
                                "verdict", "applies_nothing"}

    def test_attested_process_identity_rides_the_receipt(self, root):
        from framework.evidence import identity
        identity.attest_process_identity("system", "learning-gate",
                                         "learning-gate")
        gate.ratify({"diff": _diff("framework/learning/x.py")}, root=root,
                    runner=_ok_runner, probe_fn=_ok_probe, now=NOW)
        ev = _events(root, DAY_TRIAL)[0]
        assert ev["detail"]["attestation_mode"] == "process"
        assert ev["actor"] == {"kind": "system", "id": "learning-gate"}


# ---------------------------------------------------------------------------
# evidence_before_apply — ACT-class FAIL-CLOSED (evidence before action)
# ---------------------------------------------------------------------------

class TestEvidenceBeforeApply:
    def test_happy_path_records_intent_and_proposed(self, root):
        ids = apply_watch.evidence_before_apply("pack-1234abcd", sha256=SHA,
                                                root=root)
        assert ids["trial_id"] == "gate-apply-pack-1234abcd"
        events = _events(root, ids["trial_id"])
        assert [(e["phase"], e["status"]) for e in events] == [
            ("intent", "started"), ("policy", "proposed")]
        assert events[0]["detail"]["pack_id"] == "pack-1234abcd"
        assert events[0]["detail"]["sha256"] == SHA
        assert "gate-pack:pack-1234abcd" in events[1]["links"]
        assert events[0]["trace_id"] == ids["trace_id"]
        assert events[0]["action_id"] == ids["action_id"]
        assert _verify(root, ids["trial_id"])["ok"] is True

    def test_broken_store_fails_closed(self, root):
        """Injected store failure ⇒ the apply REFUSES before any mutation."""
        _break_store(root)
        with pytest.raises(apply_watch.GateApplyEvidenceError):
            apply_watch.evidence_before_apply("pack-1234abcd", sha256=SHA,
                                              root=root)

    def test_corrupt_trial_ledger_fails_closed(self, root):
        ids = apply_watch.evidence_before_apply("pack-1234abcd", sha256=SHA,
                                                root=root)
        _corrupt_ledger(root, ids["trial_id"])
        with pytest.raises(apply_watch.GateApplyEvidenceError):
            apply_watch.evidence_before_apply("pack-1234abcd", sha256=SHA,
                                              root=root)

    def test_unrecordable_pack_id_fails_closed(self, root):
        with pytest.raises(apply_watch.GateApplyEvidenceError) as exc:
            apply_watch.evidence_before_apply("pack with spaces", root=root)
        assert exc.value.code == "evidence_id_invalid"
        assert not _store(root).exists()  # nothing was minted

    def test_root_caller_refused_before_any_store_byte(self, root,
                                                       monkeypatch):
        """Root-ownership poisoning guard: euid 0 refuses BEFORE any store
        file exists — the daemon must drop to the invoking user."""
        monkeypatch.setattr(apply_watch.os, "geteuid", lambda: 0)
        with pytest.raises(apply_watch.GateApplyEvidenceError) as exc:
            apply_watch.evidence_before_apply("pack-1234abcd", root=root)
        assert exc.value.code == "evidence_root_refused"
        assert not _store(root).exists()

    def test_root_receipt_degrades_and_never_blocks_domain_write(
            self, root, monkeypatch, capsys):
        monkeypatch.setattr(apply_watch.os, "geteuid", lambda: 0)
        row = apply_watch.record_apply("pack-1234abcd", applied_at=APPLIED,
                                       revert_plan="p", root=root)
        assert row["status"] == "watching"  # the domain write landed
        assert not _store(root).exists()    # no root-minted store files
        assert "watch-open evidence not recorded" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# record_apply — RECEIPT completion; the watch row is never blocked/enriched
# ---------------------------------------------------------------------------

class TestRecordApplyReceipt:
    def test_completion_threads_the_preflight_ids(self, root):
        ids = apply_watch.evidence_before_apply("pack-1234abcd", sha256=SHA,
                                                root=root)
        row = apply_watch.record_apply(
            "pack-1234abcd", applied_at=APPLIED, revert_plan="p", sha256=SHA,
            root=root, evidence_context=ids)
        events = _events(root, ids["trial_id"])
        assert [(e["phase"], e["status"]) for e in events] == [
            ("intent", "started"), ("policy", "proposed"),
            ("execution", "succeeded"), ("receipt", "succeeded"),
            ("outcome", "succeeded")]
        # one action, one id set — the cross-process handoff held
        assert {e["action_id"] for e in events} == {ids["action_id"]}
        assert {e["correlation_id"] for e in events} == {ids["correlation_id"]}
        receipt = events[3]
        assert receipt["detail"]["action"] == "gate_apply_watch_open"
        assert receipt["detail"]["watch_until"] == row["watch_until"]
        assert "gate-watch:pack-1234abcd" in receipt["links"]
        assert _verify(root, ids["trial_id"])["ok"] is True

    def test_watch_row_bytes_unchanged_by_evidence(self, root):
        """Evidence cites the pack_id-keyed row; it never enriches it."""
        apply_watch.record_apply("pack-1234abcd", applied_at=APPLIED,
                                 revert_plan="p", sha256=SHA, root=root)
        rows = [json.loads(line) for line in
                apply_watch.watch_path(root).read_text().splitlines()]
        assert len(rows) == 1
        assert set(rows[0]) == {"pack_id", "status", "applied_at",
                                "watch_until", "revert_plan", "sha256",
                                "applied_by"}

    def test_receipt_failure_never_blocks_the_watch_row(self, root, capsys):
        _break_store(root)
        row = apply_watch.record_apply("pack-1234abcd", applied_at=APPLIED,
                                       revert_plan="p", root=root)
        assert row["status"] == "watching"
        assert "pack-1234abcd" in apply_watch.watch_path(root).read_text()
        assert "watch-open evidence not recorded" in capsys.readouterr().err

    def test_fresh_context_when_no_preflight(self, root):
        apply_watch.record_apply("pack-1234abcd", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        events = _events(root, "gate-apply-pack-1234abcd")
        assert [(e["phase"], e["status"]) for e in events] == [
            ("execution", "succeeded"), ("receipt", "succeeded"),
            ("outcome", "succeeded")]


# ---------------------------------------------------------------------------
# evaluate — rollback is the brake (degrade LOUD, never blocked); close and
# per-pass watch decisions keep their class
# ---------------------------------------------------------------------------

class TestWatchTransitions:
    def test_rollback_records_intent_before_release(self, root):
        apply_watch.record_apply(
            "pack-red", applied_at=APPLIED,
            revert_plan="git -c core.hooksPath=/dev/null apply -R v.patch",
            root=root)
        decisions = apply_watch.evaluate(
            now=IN_WINDOW, root=root,
            red_signals_fn=lambda a, n: ["kind frozen after apply: pm_write"])
        # decision dict shape is byte-identical to BASE
        assert decisions == [{
            "pack_id": "pack-red", "decision": "rollback",
            "reason": "kind frozen after apply: pm_write",
            "revert_plan": "git -c core.hooksPath=/dev/null apply -R v.patch",
        }]
        events = _events(root, "gate-apply-pack-red")
        tail = [(e["phase"], e["status"], e["detail"].get("action"))
                for e in events[-2:]]
        assert tail == [("intent", "started", "gate_revert"),
                        ("policy", "proposed", "gate_revert")]
        assert "kind frozen after apply" in events[-2]["detail"]["reason"]
        assert _verify(root, "gate-apply-pack-red")["ok"] is True

    def test_rollback_releases_even_with_broken_evidence_plane(
            self, root, capsys):
        """THE brake-exception proof: injected evidence failure ⇒ the
        rollback decision still releases, loudly — never fail-closed."""
        apply_watch.record_apply("pack-red", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        _corrupt_ledger(root, "gate-apply-pack-red")
        decisions = apply_watch.evaluate(
            now=IN_WINDOW, root=root, red_signals_fn=lambda a, n: ["red"])
        assert decisions[0]["decision"] == "rollback"  # the brake released
        merged = apply_watch._merged(apply_watch.watch_path(root))
        assert merged["pack-red"]["status"] == "rollback"
        # LOUD: the degradation marker sidecar carries the flip
        sidecar = _store(root) / "degradations.jsonl"
        assert sidecar.is_file() and sidecar.read_text().strip()

    def test_rollback_releases_when_store_is_unconstructable(
            self, tmp_path, capsys):
        root = _mkroot(tmp_path)
        apply_watch.record_apply("pack-red", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        # break the plane AFTER the watch row exists: swap the store for a file
        import shutil
        shutil.rmtree(root / _EV_TOP)
        _break_store(root)
        decisions = apply_watch.evaluate(
            now=IN_WINDOW, root=root, red_signals_fn=lambda a, n: ["red"])
        assert decisions[0]["decision"] == "rollback"
        assert "rollback decision releases anyway" in capsys.readouterr().err

    def test_close_transition_records_verification(self, root):
        apply_watch.record_apply("pack-ok", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        decisions = apply_watch.evaluate(now=PAST_WINDOW, root=root,
                                         red_signals_fn=lambda a, n: [])
        assert decisions[0]["decision"] == "close"
        events = _events(root, "gate-apply-pack-ok")
        assert (events[-1]["phase"], events[-1]["status"]) == \
            ("verification", "verified")
        assert events[-1]["detail"]["action"] == "gate_apply_watch_close"
        assert events[-1]["detail"]["reason"] == "72h clean"

    def test_watch_pass_is_exhaust_and_records_nothing(self, tmp_path):
        """Per-pass still-watching decisions are trigger exhaust: an
        all-watch evaluate writes NOTHING anywhere (existing tree-purity
        pin, restated against the evidence store explicitly)."""
        root = _mkroot(tmp_path)
        (root / "shared" / "interfaces" / "gate-apply-watch.jsonl").write_text(
            json.dumps({"pack_id": "pack-w", "status": "watching",
                        "applied_at": APPLIED,
                        "watch_until": "2026-07-08T00:00:00Z",
                        "revert_plan": "p"}) + "\n")
        before = {p for p in root.rglob("*") if p.is_file()}
        decisions = apply_watch.evaluate(now=IN_WINDOW, root=root,
                                         red_signals_fn=lambda a, n: [])
        assert decisions[0]["decision"] == "watch"
        after = {p for p in root.rglob("*") if p.is_file()}
        assert before == after
        assert not _store(root).exists()

    def test_revert_outcome_receipt(self, root, capsys):
        apply_watch.record_apply("pack-red", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        apply_watch.evidence_revert_outcome("pack-red", ok=True, root=root)
        events = _events(root, "gate-apply-pack-red")
        assert [(e["phase"], e["status"]) for e in events[-2:]] == [
            ("execution", "succeeded"), ("outcome", "undone")]
        apply_watch.evidence_revert_outcome("pack-red", ok=False,
                                            reason="git apply -R failed",
                                            root=root)
        events = _events(root, "gate-apply-pack-red")
        assert [(e["phase"], e["status"]) for e in events[-2:]] == [
            ("execution", "failed"), ("outcome", "failed")]
        # degrade-loud, never raises
        _corrupt_ledger(root, "gate-apply-pack-red")
        apply_watch.evidence_revert_outcome("pack-red", ok=True, root=root)


# ---------------------------------------------------------------------------
# One class, one path — the no-double-recording law
# ---------------------------------------------------------------------------

class TestOnePathPerClass:
    def test_gate_org_classes_stay_exhaust_never_mirrored(self):
        from framework import evidence_mirror
        gate_classes = {"eval_run_started", "eval_passed", "eval_failed"}
        assert gate_classes <= evidence_mirror.NEVER_MIRRORED_EXHAUST
        assert not (gate_classes & evidence_mirror.MIRRORED_ORG_EVENT_TYPES)

    def test_loop_and_trust_classes_stay_mirror_only(self):
        """Covered by the Batch A org mirror — a direct producer here would
        double-record; this module must never touch them."""
        from framework import evidence_mirror
        mirrored = {"self_improvement_loop_started",
                    "self_improvement_loop_completed", "skill_promoted",
                    "trust_rung_proposed", "trust_rung_granted",
                    "role_evolved", "role_hat_promoted",
                    "need_filed", "need_granted", "need_denied"}
        assert mirrored <= evidence_mirror.MIRRORED_ORG_EVENT_TYPES
        src = Path(gate.__file__).read_text() + \
            Path(apply_watch.__file__).read_text()
        for cls in mirrored:
            assert cls not in src

    def test_ratify_emits_only_the_existing_eval_classes(self, root,
                                                         monkeypatch):
        captured = _org_capture(monkeypatch)
        gate.ratify({"diff": _diff("framework/learning/x.py")}, root=root,
                    runner=_ok_runner, probe_fn=_ok_probe, now=NOW)
        assert {t for t, _ in captured} <= {"eval_run_started", "eval_passed",
                                            "eval_failed"}

    def test_apply_watch_emits_no_org_events(self):
        src = Path(apply_watch.__file__).read_text()
        assert "framework.events" not in src


# ---------------------------------------------------------------------------
# Never-a-score + officer projection stay closed
# ---------------------------------------------------------------------------

class TestNeverAScore:
    def test_verdict_detail_carries_no_aggregates(self, root):
        gate.ratify({"diff": _diff("framework/learning/x.py"),
                     "gap_id": "gap-1"}, root=root, runner=_ok_runner,
                    probe_fn=_ok_probe, now=NOW)
        detail = _events(root, DAY_TRIAL)[0]["detail"]
        assert set(detail) <= {"action", "pack_id", "sha256", "verdict",
                               "stages", "proposal_id", "gap_id", "lane",
                               "need_id", "attestation_mode"}
        flat = list(detail.values()) + list(detail["stages"].values())
        assert not any(isinstance(v, (int, float)) for v in flat)

    def test_new_detail_keys_stay_out_of_officer_projection(self):
        from framework.evidence.recorder import PROJECTION_ALLOWED_DETAIL
        for key in ("pack_id", "sha256", "verdict", "stages", "need_id",
                    "gap_id", "proposal_id", "lane", "applied_at",
                    "watch_until", "applied_by", "reason", "revert_plan"):
            assert key not in PROJECTION_ALLOWED_DETAIL


# ---------------------------------------------------------------------------
# A2 coverage — the learning-gate surface reads WIRED, nothing unenumerated
# ---------------------------------------------------------------------------

class TestCoverageGate:
    def test_learning_gate_surface_is_wired(self):
        import importlib.util
        script = Path(_ROOT) / "cabinet" / "scripts" / "evidence-coverage.py"
        spec = importlib.util.spec_from_file_location("evidence_coverage",
                                                      script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        report = mod.reconcile(Path(_ROOT))
        rows = {r["id"]: r for r in report["surfaces"]}
        assert rows["learning-gate"]["status"] == "WIRED"
        producers = set(rows["learning-gate"]["producers"])
        assert {"framework/learning/gate.py",
                "framework/learning/apply_watch.py"} <= producers
        assert not any(u["file"].startswith("framework/learning/")
                       for u in report["unenumerated"])
