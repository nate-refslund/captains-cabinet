"""SOV-8 Evidence Gate tests — S0 Ring-0 refusal (+ need), stage
short-circuit, ceiling probes, evidence packs, and the D16 run_gate_review
5-condition machine bar (sovereign-gated, guardian no-op)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.learning import gate  # noqa: E402

NOW = "2026-07-05T12:00:00Z"

_IMMUTABLE_CORE = """\
version: 1
lists: [germline-lock, hook-s5, hook-s5b, base-safety]
files:
  - path: framework/authority/matrix.py
  - path: cabinet/scripts/kill-switch.sh
dirs:
  - path: framework/policies/
runtime_appended:
  - path: shared/interfaces/needs-ledger.jsonl
hook_protected:
  - path: instance/config/autonomy.yml
"""


def _mkroot(tmp_path, *, core: str | None = _IMMUTABLE_CORE) -> Path:
    root = tmp_path / "cab"
    (root / "framework" / "policies").mkdir(parents=True)
    (root / "shared" / "interfaces").mkdir(parents=True)
    if core is not None:
        (root / "framework" / "policies" / "immutable-core.yml").write_text(core)
    return root


def _diff(path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n-x\n+y\n"
    )


def _ok_runner(stage, spec):
    return {"ok": True, "detail": f"{stage} ok"}


def _ok_probe():
    return {"ok": True, "detail": "probe ok"}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    monkeypatch.delenv("CABINET_POSTURE", raising=False)
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    monkeypatch.delenv("CABINET_ROOT", raising=False)


# ---------------------------------------------------------------------------
# Ring-0 parsing + matching
# ---------------------------------------------------------------------------

class TestRing0:
    def test_load_ring0_all_classes(self, tmp_path):
        root = _mkroot(tmp_path)
        r0 = gate.load_ring0(root)
        assert r0 is not None
        assert "framework/authority/matrix.py" in r0["files"]
        assert "shared/interfaces/needs-ledger.jsonl" in r0["files"]
        assert "instance/config/autonomy.yml" in r0["files"]
        assert "framework/policies/" in r0["dirs"]

    def test_load_ring0_missing_or_corrupt_is_none(self, tmp_path):
        root = _mkroot(tmp_path, core=None)
        assert gate.load_ring0(root) is None
        (root / "framework" / "policies" / "immutable-core.yml").write_text(
            "files: 'not-a-list'")
        assert gate.load_ring0(root) is None

    def test_touches_every_class_and_escape(self, tmp_path):
        r0 = gate.load_ring0(_mkroot(tmp_path))
        # exact file, dir-cover, runtime_appended, hook_protected, escape
        for p in ("framework/authority/matrix.py",
                  "framework/policies/base-safety.yml",
                  "shared/interfaces/needs-ledger.jsonl",
                  "instance/config/autonomy.yml",
                  "../outside.py",
                  "/etc/passwd"):
            assert gate.touches_ring0([p], r0) == [p], p
        assert gate.touches_ring0(["framework/learning/loop_helper.py"], r0) == []

    def test_diff_paths_dedup_and_devnull(self):
        text = (
            "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
            "diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n"
        )
        assert gate.diff_paths(text) == ["x.py", "gone.py"]


# ---------------------------------------------------------------------------
# ratify — S0 refusal + short-circuit + verdicts
# ---------------------------------------------------------------------------

class TestRatify:
    def test_s0_refuses_ring0_diff_and_files_need(self, tmp_path, monkeypatch):
        root = _mkroot(tmp_path)
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        pack = gate.ratify(
            {"diff": _diff("framework/authority/matrix.py"), "summary": "forge"},
            root=root, runner=_ok_runner, probe_fn=_ok_probe, now=NOW)
        assert pack["verdict"] == "refused"
        s0 = pack["stages"][0]
        assert s0["stage"] == "S0_scope" and s0["status"] == "refused"
        assert "framework/authority/matrix.py" in s0["detail"]
        # later stages short-circuited
        assert {s["status"] for s in pack["stages"][1:-1]} == {"skipped"}
        # need filed + returned
        assert pack.get("need_id", "").startswith("NEED-")
        ledger = (root / "shared" / "interfaces" / "needs-ledger.jsonl").read_text()
        assert pack["need_id"] in ledger and "Ring-0" in ledger

    def test_s0_refuses_when_immutable_core_unreadable(self, tmp_path):
        root = _mkroot(tmp_path, core=None)
        pack = gate.ratify({"diff": _diff("framework/learning/x.py")},
                           root=root, runner=_ok_runner, probe_fn=_ok_probe,
                           now=NOW)
        assert pack["verdict"] == "refused"
        assert "immutable-core.yml unreadable" in pack["stages"][0]["detail"]

    def test_s0_refuses_empty_diff(self, tmp_path):
        root = _mkroot(tmp_path)
        pack = gate.ratify({"diff": "  "}, root=root, runner=_ok_runner,
                           probe_fn=_ok_probe, now=NOW)
        assert pack["verdict"] == "refused"

    def test_stage_short_circuit_on_s1(self, tmp_path):
        root = _mkroot(tmp_path)

        def failing_runner(stage, spec):
            return {"ok": stage != "S1_verify", "detail": stage}

        pack = gate.ratify({"diff": _diff("framework/learning/x.py")},
                           root=root, runner=failing_runner,
                           probe_fn=_ok_probe, now=NOW)
        assert pack["verdict"] == "fail"
        by = {s["stage"]: s["status"] for s in pack["stages"]}
        assert by["S0_scope"] == "pass"
        assert by["S1_verify"] == "fail"
        assert by["S2_falsifier"] == "skipped"
        assert by["S3_ceilings"] == "skipped"
        assert by["S4_archive"] == "skipped"

    def test_s3_probe_failure_fails_pack(self, tmp_path):
        root = _mkroot(tmp_path)
        pack = gate.ratify(
            {"diff": _diff("framework/learning/x.py")},
            root=root, runner=_ok_runner,
            probe_fn=lambda: {"ok": False, "detail": "ceiling auto leak"},
            now=NOW)
        assert pack["verdict"] == "fail"
        by = {s["stage"]: s["status"] for s in pack["stages"]}
        assert by["S3_ceilings"] == "fail" and by["S4_archive"] == "skipped"

    def test_pass_writes_variant_archive_and_pack(self, tmp_path):
        root = _mkroot(tmp_path)
        diff = _diff("framework/learning/x.py")
        pack = gate.ratify({"diff": diff, "gap_id": "gap-1234abcd"},
                           root=root, runner=_ok_runner, probe_fn=_ok_probe,
                           now=NOW)
        assert pack["verdict"] == "pass"
        assert pack["applies_nothing"] is True
        sha16 = gate.diff_sha256(diff)[:16]
        variant = root / "shared" / "interfaces" / "gate-evidence" / "variants" / f"{sha16}.patch"
        assert variant.read_text() == diff
        pack_file = root / "shared" / "interfaces" / "gate-evidence" / f"pack-{sha16}.json"
        on_disk = json.loads(pack_file.read_text())
        assert on_disk["verdict"] == "pass" and on_disk["sha256"] == gate.diff_sha256(diff)
        # evidence lookups (capability_gaps.can_install consumes these)
        assert gate.evidence_verdict(gap_id="gap-1234abcd", root=root) == "pass"
        assert gate.evidence_verdict(gap_id="gap-other", root=root) is None
        assert gate.evidence_verdict(root=root) is None

    def test_live_ceiling_probe_is_green_on_shipped_floor(self):
        # The shipped floor must never resolve a ceiling to unconditional
        # auto in either posture (eval-017's behavioral assertion).
        res = gate.ceiling_probe()
        assert res["ok"], res["detail"]

    def test_default_runner_refuses_root(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate.os, "geteuid", lambda: 0)
        res = gate._default_runner("S1_verify", {"cwd": str(tmp_path)})
        assert res["ok"] is False and "root" in res["detail"]

    def test_default_runner_fails_closed_without_workdir(self, monkeypatch):
        monkeypatch.setattr(gate.os, "geteuid", lambda: 501)
        res = gate._default_runner("S1_verify", {"cwd": None})
        assert res["ok"] is False
        assert "sandbox harness not built" in res["detail"]


# ---------------------------------------------------------------------------
# run_gate_review — D16 fuel, 5-condition bar
# ---------------------------------------------------------------------------

def _acted(subject, ts=NOW, *, actor_id="polads-ceo", lane="polads",
           action_type="task_status_move", review=None,
           evidence="ttl-48h survived; artifact intact; no reversal; no cascade flag",
           status="ok"):
    ev = {
        "ts": ts,
        "actor": {"kind": "officer", "id": actor_id},
        "lane": lane,
        "action": "board_move",
        "subject": subject,
        "refs": [],
        "action_type": action_type,
        "proposal": {"required": False, "decision": None},
        "outcome": {"status": status, "evidence": evidence},
    }
    if review is not None:
        ev["review"] = review
    return ev


class TestRunGateReview:
    def _review(self, ledger, **kw):
        emitted = []
        kw.setdefault("posture", "sovereign")
        kw.setdefault("now", NOW)
        kw.setdefault("canary_green_fn", lambda kind: True)
        kw.setdefault("falsifier_green_fn", lambda: True)
        kw.setdefault("is_vetoed_fn", lambda at: False)
        kw.setdefault("emit_fn", lambda **ev: emitted.append(ev))
        report = gate.run_gate_review(ledger=ledger, **kw)
        return report, emitted

    def test_guardian_is_noop_ledger_untouched(self):
        emitted = []
        report = gate.run_gate_review(
            ledger=[_acted("s1")], posture="guardian", now=NOW,
            emit_fn=lambda **ev: emitted.append(ev))
        assert report == {"posture": "guardian", "stamped": [],
                          "considered": 0, "skipped": "posture"}
        assert emitted == []

    def test_default_posture_resolves_guardian_without_config(self):
        # No posture.yml anywhere in the test env ⇒ resolve_posture guardian
        report = gate.run_gate_review(ledger=[_acted("s1")], now=NOW)
        assert report["skipped"] == "posture"

    def test_stamps_row_clearing_all_five_conditions(self):
        report, emitted = self._review([_acted("s-clean")])
        assert [s["subject"] for s in report["stamped"]] == ["s-clean"]
        assert len(emitted) == 1
        ev = emitted[0]
        assert ev["review"] == {"verdict": "confirmed", "source": "verdict_gate",
                                "reviewed_at": NOW}
        assert ev["subject"] == "s-clean"
        assert ev["outcome"]["status"] == "ok"
        assert "5-condition machine bar" in ev["outcome"]["evidence"]

    def test_condition_ttl_ok_required(self):
        # acted but never swept ttl_ok (plain ok outcome, no marker)
        report, emitted = self._review(
            [_acted("s-nottl", evidence="landed fine")])
        assert report["stamped"] == [] and emitted == []

    def test_condition_no_undo(self):
        # an undo supersedes to outcome failed + review wrong — never stamped
        undone = _acted("s-undone", status="failed", evidence="captain-undo",
                        review={"verdict": "wrong", "source": "verdict_human"})
        report, emitted = self._review([undone])
        assert report["stamped"] == [] and emitted == []

    def test_never_overwrites_existing_review(self):
        confirmed = _acted("s-human", review={"verdict": "confirmed",
                                              "source": "verdict_human"})
        report, emitted = self._review([confirmed])
        assert report["stamped"] == [] and emitted == []

    def test_condition_no_veto_on_cell(self):
        report, emitted = self._review([_acted("s-veto")],
                                       is_vetoed_fn=lambda at: True)
        assert report["considered"] == 1
        assert report["stamped"] == [] and emitted == []

    def test_condition_canary_green(self):
        report, emitted = self._review([_acted("s-canary")],
                                       canary_green_fn=lambda kind: False)
        assert report["stamped"] == [] and emitted == []

    def test_condition_falsifier_green(self):
        report, emitted = self._review([_acted("s-fals")],
                                       falsifier_green_fn=lambda: False)
        assert report["stamped"] == [] and emitted == []

    def test_condition_demote_cooldown(self):
        # a wrong verdict on the SAME cell 3 days ago blocks gate fuel…
        wrong = _acted("s-wrong", ts="2026-07-02T12:00:00Z", status="failed",
                       evidence="captain-undo",
                       review={"verdict": "wrong", "source": "verdict_human"})
        clean = _acted("s-clean")
        report, emitted = self._review([wrong, clean])
        assert report["stamped"] == [] and emitted == []
        # …but a wrong on ANOTHER cell does not
        other = _acted("s-other-cell", ts="2026-07-02T12:00:00Z",
                       lane="stephie", status="failed", evidence="captain-undo",
                       review={"verdict": "wrong", "source": "verdict_human"})
        report, emitted = self._review([other, clean])
        assert [s["subject"] for s in report["stamped"]] == ["s-clean"]
        # …and a wrong OUTSIDE the cooldown window does not
        stale = _acted("s-stale-wrong", ts="2026-06-01T12:00:00Z",
                       status="failed", evidence="captain-undo",
                       review={"verdict": "wrong", "source": "verdict_human"})
        report, emitted = self._review([stale, clean])
        assert [s["subject"] for s in report["stamped"]] == ["s-clean"]

    def test_unreadable_veto_registry_withholds_fuel(self, monkeypatch):
        # default veto path (no injection) with a broken registry ⇒ fail-closed
        import framework.frontdoor.veto_registry as vr
        monkeypatch.setattr(vr, "is_vetoed",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
        emitted = []
        report = gate.run_gate_review(
            ledger=[_acted("s-x")], posture="sovereign", now=NOW,
            canary_green_fn=lambda kind: True, falsifier_green_fn=lambda: True,
            emit_fn=lambda **ev: emitted.append(ev))
        assert report["stamped"] == [] and emitted == []

    def test_stamped_event_validates_and_counts_in_sovereign_ratios(self):
        # End-to-end: the stamp is schema-valid and compute_ratios counts it
        # as confirmed ONLY under a sovereign posture read (D16 / SOV-7).
        from framework.fidelity.consequence import validate_consequence
        import framework.fidelity.consequence as consequence
        report, emitted = self._review([_acted("s-e2e")])
        assert len(emitted) == 1
        validate_consequence(emitted[0])  # must not raise
        base = _acted("s-e2e")
        stamped_ledger = [base, emitted[0]]
        # collapse manually mirrors read_ledger last-write-wins on identity
        cells_g = consequence.compute_ratios(ledger=[emitted[0]])
        key = ("officer:polads-ceo", "polads", "task_status_move")
        # guardian compute: verdict_gate confirm does NOT count
        assert cells_g[key].confirmed == 0
        # sovereign compute: it does
        try:
            consequence._gate_confirms_now  # sanity: seam exists
            orig = consequence._gate_confirms_now
            consequence._gate_confirms_now = lambda: True
            cells_s = consequence.compute_ratios(ledger=[emitted[0]])
            assert cells_s[key].confirmed == 1
        finally:
            consequence._gate_confirms_now = orig
        assert stamped_ledger  # silence linters

    def test_per_row_failure_isolated(self):
        # one poisoned row (emit raises) must not stop the others
        calls = {"n": 0}

        def flaky_emit(**ev):
            calls["n"] += 1
            if ev["subject"] == "s-bad":
                raise RuntimeError("boom")

        report = gate.run_gate_review(
            ledger=[_acted("s-bad"), _acted("s-good")],
            posture="sovereign", now=NOW,
            canary_green_fn=lambda kind: True, falsifier_green_fn=lambda: True,
            is_vetoed_fn=lambda at: False, emit_fn=flaky_emit)
        assert [s["subject"] for s in report["stamped"]] == ["s-good"]
        assert calls["n"] == 2
