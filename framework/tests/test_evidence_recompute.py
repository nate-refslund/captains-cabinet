"""HP-2 independent recompute legs (framework/evidence_recompute.py).

Pins the wave's laws on scratch planes only (no live API, no network, no
live store — the conftest env fence + explicit injection seams):

* three legs re-derive fuel-bearing machine outcomes from RAW artifacts
  (undo-journal bytes, gate pack + archived patch bytes, org-event rows +
  the germline graduation.evaluate re-run) and compare against the claim —
  agree / disagree / underivable:<reason>, one verification event per
  checked outcome in the verifier's OWN evt-recompute day trial;
* discriminator law — absence (journal GC, missing patch, no probe, no
  ``gh``) is an honest skip, never a finding, never a guess;
* idempotence — re-runs dedup by claim_sha256 across the WINDOW day range
  (events land on their run day, far from an old outcome's ts);
* read-only proof — two-pass byte stability modulo the sanctioned writes;
  an absent store is never created; report paths inside either plane are
  refused; exit codes carry no verdict signal;
* dark-by-default + shadow — services row ships disabled, zero consumers
  (tracked-files grep with a no-git walk twin), counts never rates, the
  honest claim rides every surface, detail keys read back
  producer-asserted (the fail-closed classification default).

python3.12 only. Lives OUTSIDE the germline framework/evidence dir.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import framework.evidence_recompute as erc
from framework import evidence_freeze
from framework import evidence_mirror
from framework.evidence import EvidenceRecorder
from framework.evidence.classification import (
    PRODUCER_ASSERTED,
    classify_detail_key,
)
from framework.evidence.recorder import PROJECTION_ALLOWED_DETAIL
from framework.fidelity.graduation import evaluate as graduation_evaluate
from framework.learning import gate

REPO_ROOT = Path(__file__).resolve().parents[2]

_CELL = ("officer:tb-cos", "tb-ops", "tb_apply")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(offset_s: int = 0) -> str:
    return _iso(_now() + timedelta(seconds=offset_s))


def _today8() -> str:
    return _now().strftime("%Y%m%d")


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _non_watermark(tree: dict[str, str]) -> dict[str, str]:
    watermark_files = {".verify-watermarks.json", ".verify-watermarks.lock"}
    return {k: v for k, v in tree.items()
            if Path(k).name not in watermark_files}


@pytest.fixture()
def planes(tmp_path, monkeypatch):
    """Scratch everything: store (pre-created — the module never creates
    one), consequence-ledger dir, undo dir, gate root, report out."""
    store = tmp_path / "evidence-store"
    events = tmp_path / "events"
    undo = tmp_path / "undo"
    gate_root = tmp_path / "gate-root"
    out = tmp_path / "report" / "evidence-recompute-report.jsonl"
    events.mkdir()
    undo.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
    monkeypatch.setenv("CABINET_UNDO_DIR", str(undo))
    monkeypatch.delenv("CABINET_ACTION_EVIDENCE_STORE", raising=False)
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    EvidenceRecorder(store)  # scaffold the scratch store up front
    return SimpleNamespace(store=store, events=events, undo=undo,
                           gate_root=gate_root, out=out, tmp=tmp_path)


def _check(planes, **kw):
    kw.setdefault("store_root", planes.store)
    kw.setdefault("ledger", [])
    kw.setdefault("journal_rows", [])
    kw.setdefault("gate_root", planes.gate_root)
    kw.setdefault("org_events", [])
    kw.setdefault("ci_probe", lambda commit: None)  # hermetic: never gh
    return erc.check_recompute(**kw)


# --- act-lane builders ------------------------------------------------------

def _act_row(jid: str, *, status: str = "ok",
             evidence: str = "ttl-48h survived; artifact intact",
             ts: str | None = None) -> dict:
    return {
        "ts": ts or _ts(-3 * 86400),
        "actor": {"kind": "officer", "id": "tb-cos"},
        "lane": "tb-ops",
        "action": "apply testburg fix",
        "action_type": "tb_apply",
        "subject": f"tb-{jid}",
        "proposal": {"required": False, "decision": None},
        "outcome": {"status": status, "evidence": evidence},
        "refs": [f"undo-journal:{jid}"],
    }


def _journal_row(jid: str, **overrides) -> dict:
    base = {
        "jid": jid,
        "ts": _ts(-3 * 86400),
        "status": "executed",
        "executed_at": _ts(-3 * 86400),
        "reversed_at": None,
        "ttl_expires_at": _ts(-1 * 86400),  # the 48h clock has run out
        "canary": False,
    }
    base.update(overrides)
    return base


def _recorded_events(planes) -> list[dict]:
    rec = EvidenceRecorder(planes.store)
    return rec.read_events(f"evt-recompute-{_today8()}")


def _only_target(report: dict) -> dict:
    assert len(report["targets"]) == 1, report["targets"]
    return report["targets"][0]


# --- gate builders ----------------------------------------------------------

def _write_pack(planes, *, verdict: str = "pass", diff: str = "--- a\n+++ b\n",
                stages: list[tuple[str, str]] | None = None,
                applies_nothing: bool = True, archive: bool = True,
                sha_override: str | None = None, extra: dict | None = None) -> dict:
    sha = sha_override or gate.diff_sha256(diff)
    if stages is None:
        stages = [("S0_scope", "pass"), ("S1_verify", "pass"),
                  ("S2_falsifier", "pass"), ("S3_ceilings", "pass"),
                  ("S4_archive", "pass"), ("S5_verdict", verdict)]
    pack = {
        "pack_id": f"pack-{sha[:16]}",
        "ts": _ts(-2 * 86400),
        "sha256": sha,
        "verdict": verdict,
        "applies_nothing": applies_nothing,
        "stages": [{"stage": name, "status": status}
                   for name, status in stages],
    }
    if extra:
        pack.update(extra)
    edir = gate.evidence_dir(planes.gate_root)
    (edir / "variants").mkdir(parents=True, exist_ok=True)
    (edir / f"{pack['pack_id']}.json").write_text(
        json.dumps(pack, indent=2), encoding="utf-8")
    if archive:
        (edir / "variants" / f"{sha[:16]}.patch").write_text(
            diff, encoding="utf-8")
    return pack


def _write_gate_receipt(planes, pack: dict, *, sha: str | None = None,
                        verdict: str | None = None) -> None:
    rec = EvidenceRecorder(planes.store)
    day = str(pack["ts"])[:10].replace("-", "")
    ctx = rec.trace(f"evt-learning-gate-{day}", surface="system")
    rec.append(ctx, phase="verification", status="verified",
               actor={"kind": "system", "id": "learning-gate"},
               component={"name": "learning-gate", "version": "1"},
               detail={
                   "action": "gate_ratify",
                   "pack_id": pack["pack_id"],
                   "sha256": sha if sha is not None else pack["sha256"],
                   "verdict": verdict if verdict is not None else pack["verdict"],
                   "stages": {s["stage"]: s["status"] for s in pack["stages"]},
               },
               links=[f"gate-pack:{pack['pack_id']}"])


# --- graduation builders ----------------------------------------------------

def _grad_ledger(n: int = 3) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append({
            "ts": _ts(-(5 - i) * 86400),
            "actor": {"kind": "officer", "id": "tb-cos"},
            "lane": _CELL[1],
            "action": "apply testburg fix",
            "action_type": _CELL[2],
            "subject": f"tb-grad-{i}",
            "proposal": {"required": True, "decision": "approved"},
            "outcome": {"status": "ok", "evidence": "applied"},
            "review": {"verdict": "confirmed", "source": "verdict_human",
                       "reviewed_at": _ts(-(5 - i) * 86400)},
        })
    return rows


def _org_event(to_state: str, *, created: str | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "event_type": "graduation_transition",
        "actor": "system:emit-graduation-transitions",
        "payload": {
            "cell": {"actor": _CELL[0], "lane": _CELL[1],
                     "action_type": _CELL[2]},
            "from_state": None,
            "to_state": to_state,
        },
        "parent_id": None,
        "created_at": created or _ts(-3600),
    }


def _write_org_mirror(planes, event: dict, *, sha: str | None = None) -> None:
    rec = EvidenceRecorder(planes.store)
    day = str(event["created_at"])[:10].replace("-", "")
    ctx = rec.trace(f"evt-orgmirror-{day}", surface="system")
    rec.append(ctx, phase="system", status="succeeded",
               actor={"kind": "system", "id": "org-event-mirror"},
               component={"name": "evidence-mirror", "version": "1"},
               detail={
                   "action": "org_event_mirror",
                   "org_event_id": event["id"],
                   "org_event_type": event["event_type"],
                   "org_event_sha256": (
                       sha if sha is not None
                       else evidence_mirror._canonical_sha256(event)),
               },
               links=[])


# ---------------------------------------------------------------------------
# Leg 1 — act-lane TTL outcomes
# ---------------------------------------------------------------------------


class TestActLeg:
    def test_ttl_ok_agree_records_one_verification_event(self, planes):
        jid = "j-tb-1"
        report = _check(planes, ledger=[_act_row(jid)],
                        journal_rows=[_journal_row(jid)])
        target = _only_target(report)
        assert target["target"] == "act_ttl_ok"
        assert target["agreement"] == "agree"
        assert target["rederived"] == "ok"
        assert target["recorded"] is True
        events = _recorded_events(planes)
        assert len(events) == 1
        event = events[0]
        assert event["phase"] == "verification"
        assert event["status"] == "verified"
        detail = event["detail"]
        assert detail["action"] == "recompute_verification"
        assert detail["agreement"] == "agree"
        assert detail["jid"] == jid
        assert detail["claim"] == "ok"
        assert event["links"] == [f"undo-journal:{jid}"]
        assert report["summary"]["agree"] == 1

    def test_ttl_ok_with_reversed_journal_disagrees(self, planes):
        jid = "j-tb-2"
        report = _check(
            planes, ledger=[_act_row(jid)],
            journal_rows=[_journal_row(jid, status="reversed",
                                       reversed_at=_ts(-3600))])
        target = _only_target(report)
        assert target["agreement"] == "disagree"
        assert target["rederived"] == "failed"
        assert _recorded_events(planes)[0]["status"] == "unverified"

    def test_ttl_not_elapsed_disagrees(self, planes):
        jid = "j-tb-3"
        report = _check(
            planes, ledger=[_act_row(jid)],
            journal_rows=[_journal_row(jid, ttl_expires_at=_ts(86400))])
        assert _only_target(report)["rederived"] == "ttl-not-elapsed"
        assert _only_target(report)["agreement"] == "disagree"

    def test_canary_row_is_never_sweep_eligible(self, planes):
        jid = "j-tb-4"
        report = _check(planes, ledger=[_act_row(jid)],
                        journal_rows=[_journal_row(jid, canary=True)])
        assert _only_target(report)["rederived"] == "ineligible"
        assert _only_target(report)["agreement"] == "disagree"

    def test_journal_row_gone_is_an_honest_gap(self, planes):
        """30d journal GC — underivable, never a finding, still recorded
        (status ``skipped``: the non-derivation is itself evidence)."""
        jid = "j-tb-5"
        report = _check(planes, ledger=[_act_row(jid)], journal_rows=[])
        target = _only_target(report)
        assert target["agreement"] == "underivable:journal-row-gone"
        assert target["rederived"] is None
        assert report["summary"]["underivable"] == 1
        assert _recorded_events(planes)[0]["status"] == "skipped"

    def test_silent_revert_probe_matrix(self, planes):
        """Reversed journal proves the claim without a probe; no probe =
        honest skip; a standing artifact contradicts the revert claim."""
        revert = "silent revert: artifact missing without a captain undo"
        jid = "j-tb-6"
        row = _act_row(jid, status="failed", evidence=revert)
        # journal itself proves the fall
        report = _check(
            planes, ledger=[row],
            journal_rows=[_journal_row(jid, status="reversal_failed")],
            record=False)
        assert _only_target(report)["agreement"] == "agree"
        # probe unavailable -> honest skip, never a guess
        report = _check(planes, ledger=[row],
                        journal_rows=[_journal_row(jid)], record=False)
        assert (_only_target(report)["agreement"]
                == "underivable:artifact-unavailable")
        # probed artifact stands -> the revert claim does not
        report = _check(planes, ledger=[row],
                        journal_rows=[_journal_row(jid)],
                        monday_probe=lambda jrow: {"exists": True},
                        record=False)
        assert _only_target(report)["agreement"] == "disagree"
        # probed artifact archived -> agree
        report = _check(planes, ledger=[row],
                        journal_rows=[_journal_row(jid)],
                        monday_probe=lambda jrow: {"exists": True,
                                                   "archived": True},
                        record=False)
        assert _only_target(report)["agreement"] == "agree"


# ---------------------------------------------------------------------------
# Leg 2 — gate verdicts
# ---------------------------------------------------------------------------


class TestGateLeg:
    def test_consistent_pack_with_receipt_agrees(self, planes):
        pack = _write_pack(planes)
        _write_gate_receipt(planes, pack)
        report = _check(planes)
        target = _only_target(report)
        assert target["target"] == "gate_verdict"
        assert target["agreement"] == "agree"
        assert target["legs"] == {
            "applies_nothing": "pass", "stage_consistency": "pass",
            "archive_sha": "pass", "store_receipt": "pass"}
        event = _recorded_events(planes)[0]
        assert event["detail"]["pack_id"] == pack["pack_id"]
        assert event["links"] == [f"gate-pack:{pack['pack_id']}"]

    def test_archived_patch_sha_mismatch_disagrees(self, planes):
        pack = _write_pack(planes, sha_override=gate.diff_sha256("laundered"))
        # the archived patch bytes hash to something else entirely
        edir = gate.evidence_dir(planes.gate_root)
        (edir / "variants").mkdir(parents=True, exist_ok=True)
        (edir / "variants" /
         f"{pack['sha256'][:16]}.patch").write_text("other", encoding="utf-8")
        report = _check(planes, record=False)
        target = _only_target(report)
        assert target["agreement"] == "disagree"
        assert target["legs"]["archive_sha"] == "fail"
        assert target["reason"] == "archive-sha-mismatch"

    def test_stage_verdict_inconsistency_disagrees(self, planes):
        _write_pack(planes, verdict="pass",
                    stages=[("S0_scope", "pass"), ("S1_verify", "fail"),
                            ("S2_falsifier", "skipped"),
                            ("S3_ceilings", "skipped"),
                            ("S4_archive", "skipped"),
                            ("S5_verdict", "pass")])
        report = _check(planes, record=False)
        target = _only_target(report)
        assert target["agreement"] == "disagree"
        assert target["rederived"] == "fail"
        assert target["legs"]["stage_consistency"] == "fail"

    def test_refused_pack_rederives_refused(self, planes):
        _write_pack(planes, verdict="refused", archive=False,
                    stages=[("S0_scope", "refused"),
                            ("S1_verify", "skipped"),
                            ("S2_falsifier", "skipped"),
                            ("S3_ceilings", "skipped"),
                            ("S4_archive", "skipped"),
                            ("S5_verdict", "refused")])
        report = _check(planes, record=False)
        target = _only_target(report)
        assert target["rederived"] == "refused"
        assert target["legs"]["stage_consistency"] == "pass"

    def test_applies_nothing_violation_disagrees(self, planes):
        _write_pack(planes, applies_nothing=False)
        report = _check(planes, record=False)
        target = _only_target(report)
        assert target["agreement"] == "disagree"
        assert target["reason"] == "applies-nothing-violated"

    def test_missing_receipt_is_an_underivable_leg_not_a_finding(self, planes):
        _write_pack(planes)
        report = _check(planes, record=False)
        target = _only_target(report)
        assert target["agreement"] == "agree"
        assert target["legs"]["store_receipt"] == "underivable:receipt-missing"

    def test_receipt_divergence_disagrees(self, planes):
        pack = _write_pack(planes)
        _write_gate_receipt(planes, pack, sha="f" * 64)
        report = _check(planes, record=False)
        target = _only_target(report)
        assert target["agreement"] == "disagree"
        assert target["legs"]["store_receipt"] == "fail"
        assert target["reason"] == "receipt-mismatch"

    def test_ci_leg_engages_only_on_named_commits(self, planes, monkeypatch):
        # No commit named: no CI leg, and no gh subprocess may ever spawn.
        monkeypatch.setattr(erc.subprocess, "run",
                            lambda *a, **k: pytest.fail("gh spawned"))
        _write_pack(planes)
        report = _check(planes, record=False)
        assert "ci" not in _only_target(report)["legs"]

    def test_ci_gh_absent_is_honest_skip_and_failure_disagrees(
            self, planes, monkeypatch):
        pack_extra = {"commit": "a" * 40}
        _write_pack(planes, extra=pack_extra)
        # feature-detect says no gh -> underivable, never a guess
        monkeypatch.setattr(erc.shutil, "which", lambda name: None)
        report = _check(planes, record=False, ci_probe=None)
        assert (_only_target(report)["legs"]["ci"]
                == "underivable:artifact-unavailable")
        # an injected CI probe that contradicts a pass verdict disagrees
        report = _check(planes, record=False,
                        ci_probe=lambda commit: {"ok": False, "runs": 2})
        target = _only_target(report)
        assert target["legs"]["ci"] == "fail"
        assert target["agreement"] == "disagree"
        assert target["reason"] == "ci-contradicts-verdict"


# ---------------------------------------------------------------------------
# Leg 3 — graduation transitions
# ---------------------------------------------------------------------------


class TestGraduationLeg:
    def test_rerun_agrees_with_the_claimed_state(self, planes):
        ledger = _grad_ledger()
        expected = graduation_evaluate(_CELL, ledger=ledger,
                                       now=_now())["state"]
        event = _org_event(expected)
        _write_org_mirror(planes, event)
        report = _check(planes, ledger=ledger, org_events=[event])
        target = _only_target(report)
        assert target["target"] == "graduation_transition"
        assert target["agreement"] == "agree"
        assert target["legs"]["org_mirror"] == "pass"

    def test_state_mismatch_disagrees(self, planes):
        ledger = _grad_ledger()
        event = _org_event("graduated")  # never true for a 3-row cell
        _write_org_mirror(planes, event)
        report = _check(planes, ledger=ledger, org_events=[event],
                        record=False)
        target = _only_target(report)
        assert target["agreement"] == "disagree"
        assert target["reason"] == "state-mismatch"

    def test_mirror_sha_mismatch_disagrees(self, planes):
        ledger = _grad_ledger()
        expected = graduation_evaluate(_CELL, ledger=ledger,
                                       now=_now())["state"]
        event = _org_event(expected)
        _write_org_mirror(planes, event, sha="0" * 64)  # rewritten bytes
        report = _check(planes, ledger=ledger, org_events=[event],
                        record=False)
        target = _only_target(report)
        assert target["agreement"] == "disagree"
        assert target["legs"]["org_mirror"] == "fail"
        assert target["reason"] == "mirror-sha-mismatch"

    def test_ledger_window_gone_is_underivable(self, planes):
        event = _org_event("eligible")
        report = _check(planes, ledger=[], org_events=[event], record=False)
        target = _only_target(report)
        assert target["agreement"] == "underivable:ledger-window-gone"
        assert target["rederived"] is None


# ---------------------------------------------------------------------------
# Idempotence + read-only discipline
# ---------------------------------------------------------------------------


class TestExhaustDiscipline:
    def test_rerun_dedups_by_claim_sha(self, planes):
        jid = "j-tb-idem"
        kw = dict(ledger=[_act_row(jid)], journal_rows=[_journal_row(jid)])
        first = _check(planes, **kw)
        assert first["summary"]["recording"]["recorded"] == 1
        second = _check(planes, **kw)
        assert second["summary"]["recording"]["recorded"] == 0
        assert second["summary"]["recording"]["skipped_existing"] == 1
        assert len(_recorded_events(planes)) == 1

    def test_dedup_scans_the_whole_window_not_ts_adjacent_days(self, planes):
        """An event minted on an EARLIER run day (neither the outcome's
        ts-day nor today) still dedups — recompute events land on their
        run day, so the scan must cover the window."""
        jid = "j-tb-old"
        row = _act_row(jid, ts=_ts(-10 * 86400))
        jrow = _journal_row(jid, ts=_ts(-10 * 86400),
                            executed_at=_ts(-10 * 86400),
                            ttl_expires_at=_ts(-8 * 86400))
        run_day = _now() - timedelta(days=6)  # between ts-day and today
        first = _check(planes, ledger=[row], journal_rows=[jrow], now=run_day)
        assert first["summary"]["recording"]["recorded"] == 1
        second = _check(planes, ledger=[row], journal_rows=[jrow])
        assert second["summary"]["recording"]["skipped_existing"] == 1
        assert second["summary"]["recording"]["recorded"] == 0

    def test_two_pass_byte_stability_modulo_sanctioned_writes(self, planes):
        jid = "j-tb-bytes"
        kw = dict(ledger=[_act_row(jid)], journal_rows=[_journal_row(jid)])
        _check(planes, **kw)
        after_one = _tree_digest(planes.store)
        _check(planes, **kw)  # dedup pass: reads verify (watermark only)
        after_two = _tree_digest(planes.store)
        assert _non_watermark(after_two) == _non_watermark(after_one), (
            "a dedup re-run wrote non-watermark store bytes")
        _check(planes, **kw)
        assert _tree_digest(planes.store) == after_two, (
            "reads at tip must be byte-stable, watermarks included")

    def test_absent_store_derives_reports_and_never_creates(self, tmp_path,
                                                            monkeypatch):
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
        absent = tmp_path / "no-store-here"
        jid = "j-tb-absent"
        report = erc.check_recompute(
            store_root=absent, ledger=[_act_row(jid)],
            journal_rows=[_journal_row(jid)], gate_root=tmp_path,
            org_events=[], ci_probe=lambda commit: None)
        assert not absent.exists(), (
            "constructing a recorder over an absent store CREATES it — "
            "the verifier must refuse, not scaffold")
        target = _only_target(report)
        assert target["agreement"] == "agree"  # derivation still ran
        assert target["recorded"] is False
        assert (report["summary"]["recording"]
                ["unrecorded_store_unavailable"] == 1)
        assert report["store"]["available"] is False

    def test_no_targets_means_zero_store_writes(self, planes):
        before = _tree_digest(planes.store)
        report = _check(planes)
        assert report["summary"]["targets_checked"] == 0
        assert _tree_digest(planes.store) == before

    def test_pytest_fence_blocks_default_store_resolution(self, monkeypatch):
        monkeypatch.delenv("CABINET_ACTION_EVIDENCE_STORE", raising=False)
        assert erc._store_root(None) is None  # recording fenced OFF in suites

    def test_report_refuses_paths_either_plane_reads(self, planes):
        report = _check(planes, record=False)
        with pytest.raises(ValueError):
            erc.write_report(report, planes.store / "x.jsonl",
                             store_root=planes.store)
        with pytest.raises(ValueError):
            erc.write_report(report, planes.events / "x.jsonl",
                             store_root=planes.store)
        out = erc.write_report(report, planes.out, store_root=planes.store)
        assert out.is_file()


# ---------------------------------------------------------------------------
# CLI + freeze + weekly line
# ---------------------------------------------------------------------------


class TestCliAndFreeze:
    def _seed_disagree(self, planes) -> None:
        jid = "j-tb-cli"
        day = _ts(-3 * 86400)[:10]
        row = _act_row(jid)
        (planes.events / f"consequence-events-{day}.jsonl").write_text(
            json.dumps(row) + "\n", encoding="utf-8")
        jrow = _journal_row(jid, status="reversed", reversed_at=_ts(-3600))
        (planes.undo / f"undo-journal-{day}.jsonl").write_text(
            json.dumps(jrow) + "\n", encoding="utf-8")

    def test_exit_code_carries_no_verdict_signal(self, planes, capsys):
        self._seed_disagree(planes)
        rc = erc.main(["--store", str(planes.store),
                       "--out", str(planes.out)])
        assert rc == 0, "a disagreement must not surface as an exit code"
        printed = capsys.readouterr().out
        assert "recompute: 1 checked (0 agree, 1 disagree" in printed
        assert "[shadow — report-only]" in printed
        assert "%" not in printed and " rate" not in printed  # counts only
        assert planes.out.is_file()
        for line in planes.out.read_text(encoding="utf-8").splitlines():
            assert json.loads(line)["honest_claim"] == erc.HONEST_CLAIM

    def test_frozen_marker_refuses_zero_writes(self, planes, capsys,
                                               monkeypatch):
        self._seed_disagree(planes)
        monkeypatch.setattr(erc, "_repo_root", lambda: planes.tmp)
        marker = evidence_freeze.freeze(planes.tmp, "hp2-proof",
                                        set_by="hp2-test", drill=True)
        try:
            store_before = _tree_digest(planes.store)
            rc = erc.main(["--store", str(planes.store),
                           "--out", str(planes.out)])
            assert rc == 0
            assert "frozen — refusing to run" in capsys.readouterr().out
            assert not planes.out.exists()
            assert _tree_digest(planes.store) == store_before
        finally:
            evidence_freeze._lift_immutable(marker)
            marker.unlink(missing_ok=True)

    def test_honest_claim_rides_every_surface(self, planes):
        jid = "j-tb-claim"
        report = _check(planes, ledger=[_act_row(jid)],
                        journal_rows=[_journal_row(jid)], record=False)
        claim = erc.HONEST_CLAIM
        assert "SAME OS user" in claim and "HP-1" in claim
        assert report["honest_claim"] == claim
        assert report["summary"]["honest_claim"] == claim
        assert all(t["honest_claim"] == claim for t in report["targets"])
        assert claim in report["weekly_line"]
        doc = " ".join((erc.__doc__ or "").split()).casefold()
        for phrase in ("same os user", "hp-1", "raw artifacts",
                       "necessary, not sufficient", "never a guess"):
            assert phrase in doc


# ---------------------------------------------------------------------------
# Shadow, classification, and dark-by-default proofs
# ---------------------------------------------------------------------------

_REFERENCE_ALLOWLIST = {
    # Expansion registry (2026-07-27): a future module under this same
    # shadow law needs the identical one-line entry in its own landing.
    "cabinet/config/architecture-baseline-sets.yml":
        "the architecture baseline sets are the census's inventory of WHICH framework modules exist, so every module path is there by construction — a member-name row in a data file, never an import and never a consumer",
    # Specifics ratchet (2026-07-28): same class, same forcing rule.
    "framework/tests/framework-specifics-baseline.txt":
        "the specifics-ratchet DEBT LEDGER keys one line per known third-party literal by the framework path that carries it, so a module that carries one is there by construction — a path-keyed debt row in a data file, never an import and never a consumer",
    "framework/evidence_recompute.py": "the module itself",
    "framework/tests/test_evidence_recompute.py": "this proof",
    "cabinet/scripts/evidence-recompute.py": "the thin scheduled runner",
    "cabinet/services.yml": "the staged-dark service row",
    "cabinet/scripts/evidence-coverage.py":
        "the A2 census ENUMERATES the module (producer row) — source-text "
        "scan only, no output consumed",
    "framework/tests/test_evidence_phase4_seams.py":
        "the composed Phase-4 freeze proof (tests are not consumers)",
    "framework/tests/test_fuel_integrity.py":
        "the third-leg join proof forges recompute events BY SHAPE "
        "(actor id + action string) — a test, never a consumer",
    "docs/runbooks/evidence-recompute.md":
        "runbook prose — the Captain-facing contract",
    "instance/config/watchdog.yml":
        "the staged-dark liveness id, commented out until the ceremony",
    "instance/config/watchdog.yml.example":
        "the shipped twin (egg-export's watchdog-default transform "
        "materializes the live file from it) carries the same staged-dark "
        "liveness id, commented out until the ceremony",
    "cabinet/scripts/docs-sweep-allowlist.txt":
        "the docs-sweep glob list names the report's runtime path so the "
        "runbook may cite it — a pattern line, never a consumer",
    "docs/proposals/germline-amendment-evidence-hp-2026-07-17.md":
        "the HP-1/2/3 amendment contract (prose names the module and its "
        "shadow law — a Captain document, never a consumer)",
    "docs/runbooks/evidence-hp-deploy.md":
        "the fresh-cabinet deploy-ceremony hand-off (prose cites the "
        "enable steps and exit checks — never a consumer)",
    "shared/interfaces/reviews/evidence-hp-preconditions-cp1.md":
        "the FW-019 checkpoint review for the HP batch (prose records the "
        "composed proofs — never a consumer)",
    "shared/interfaces/reviews/fix-evidence-append-quadratic-cp2.md":
        "the FW-019 checkpoint review for the append-quadratic fix — its "
        "PYTEST_CURRENT_TEST sibling table cites this module's two pytest "
        "fences by file:line as UNMEASURED-claim candidates. A row in a "
        "review table, never an import and never a consumer",
}


def _tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO_ROOT),
                             capture_output=True, check=True)
        return [p for p in out.stdout.decode().split("\0") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Exported tree (null-hatch runs the suite from a .git-less export):
        # walk the shipped files instead. Runtime-only paths (gitignored in
        # the dev repo, absent from a fresh export) are excluded so both
        # modes prove the same shipped-file set.
        skip_dirs = {".git", "node_modules", "__pycache__", ".next",
                     ".venv", "dist", "build"}
        skip_prefixes = ("cabinet/logs/", "instance/evidence/",
                         "instance/state/")
        rels: list[str] = []
        for root, dirs, files in os.walk(REPO_ROOT):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), REPO_ROOT)
                rel = rel.replace(os.sep, "/")
                if rel.startswith(skip_prefixes):
                    continue
                rels.append(rel)
        return rels


class TestShadowProof:
    def test_zero_consumers_grep_with_no_git_twin(self):
        """Shadow law: nothing in the shipped tree references the verifier
        outside the allowlist — its events and report feed no gate, no
        score, no act path."""
        offenders = []
        for rel in _tracked_files():
            if rel in _REFERENCE_ALLOWLIST:
                continue
            path = REPO_ROOT / rel
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue
            if "evidence_recompute" in text or "evidence-recompute" in text:
                offenders.append(rel)
        assert offenders == [], (
            "recompute output referenced outside the allowlist (shadow "
            f"law): {offenders}")

    def test_module_source_law(self):
        source = (REPO_ROOT / "framework" / "evidence_recompute.py").read_text(
            encoding="utf-8")
        # Never a writer toward either plane, never a purge/repair verb,
        # never the org-event writer, never a shell string, never Redis or
        # network reach beyond the arg-list gh probe.
        for forbidden in ("emit_consequence", "reserve_consequence",
                          "mirror_consequence", "framework.events",
                          "purge_trial", "repair_verdict", "emitter",
                          "shell=True", "os.system", "trigger_send",
                          "StrictRedis", "redis-cli", "urllib",
                          "http.client", "requests"):
            assert forbidden not in source, forbidden
        # Never the report-only scalar series (EVAL-025 C1; tokens built by
        # concatenation so THIS file never contains them either).
        for token in ("golden-eval-" + "scalar", "golden_" + "scalar"):
            assert token not in source, token
        # Mandatory doctrine strings.
        for required in ("SHADOW LAW", "HP-1", "underivable",
                         "necessary, not sufficient", "never rates",
                         "DISCRIMINATOR LAW"):
            assert required.lower() in source.lower(), required
        # No floor/bar argv overrides; the window constant is imported.
        assert "--bar" not in source
        assert "STATUS_MAX_AGE_DAYS" in source

    def test_detail_keys_read_back_producer_asserted_and_unprojected(self):
        """Classification honesty: the minted keys are UNREGISTERED, so the
        registry's fail-closed default renders them producer-asserted —
        promotion is the documented ceremony, never this wave. None of
        them may leak into the officer projection."""
        minted = ("agreement", "claim", "rederived", "claim_sha256",
                  "target", "legs", "cell", "org_event_id")
        for key in minted:
            assert classify_detail_key(key) == PRODUCER_ASSERTED, key
            assert key not in PROJECTION_ALLOWED_DETAIL, key

    def test_services_row_is_armed_and_still_shadow(self):
        """ARMED by the Captain's 2026-07-26 ceremony (it shipped
        `disabled: true` staged-dark before that). The SHADOW LAW is what this
        class exists to protect and it is unchanged by the arming: recompute
        reports only, nothing the minter reads — pinned by the zero-consumer
        proof above, which is untouched. This test now pins the ARMED shape:
        no parking flag, still one command, still declaring shadow."""
        services = (REPO_ROOT / "cabinet" / "services.yml").read_text(
            encoding="utf-8")
        block = services.split("- name: evidence-recompute", 1)[1]
        block = block.split("- name: ", 1)[0]
        assert "disabled: true" not in block
        assert "disabled_reason:" not in block
        assert "python3.12 cabinet/scripts/evidence-recompute.py" in block
        command_line = next(l for l in block.splitlines() if "command:" in l)
        assert "&&" not in command_line
        assert "shadow" in block

    def test_runbook_carries_the_honest_claim_and_ceremony_items(self):
        runbook = REPO_ROOT / "docs" / "runbooks" / "evidence-recompute.md"
        text = runbook.read_text(encoding="utf-8")
        assert "SAME OS user" in text and "HP-1" in text
        assert "necessary, not sufficient" in text
        assert "report-only" in text.lower()
        assert "underivable" in text
        assert "root forges everything" in text
        # the two forward ceremonies are EXPLICIT line items, never implicit
        assert "classification registry" in text.lower()
        assert "immutable-core" in text
        assert "pending:" in text
