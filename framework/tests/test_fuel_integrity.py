"""Phase-4 fuel-integrity shadow check (framework/evidence_fuel_integrity.py).

Pins the batch's laws on scratch planes only:

* single-plane detection — a hand-forged consequence row with no evidence
  mirror is flagged ungrounded; tampered store bytes fail verification and
  are flagged tamper-shaped;
* THE DOCUMENTED GAP, by name — a CONSISTENT same-user forgery of BOTH
  planes (ledger row + matching signed receipt + forged Captain label +
  forged journal digest, all written by this test as the same OS user)
  PASSES as grounded.  That is exactly the HP-1 residual the honest claim
  states; the test asserts the claim rides the report;
* triage law — a missing receipt explained by a degradation-ledger row is
  inconclusive (pass-through), never tamper (NOISE only with affirmative
  evidence);
* purge-overlap, third-leg/attestation ladder, cell floors;
* read-only proof — the two-pass tree-digest discipline (non-watermark
  bytes identical after pass one; fully byte-identical at rest) over the
  store, and the ledger dir byte-identical always;
* shadow proof — nothing in the repo imports the checker; exit codes carry
  no verdict signal; floor constants are the imported judge_calibration
  objects, with no argv override.

Lives OUTSIDE the germline framework/evidence dir (test_evidence_mirror
precedent).  python3.12 only.  Scratch stores via the evidence-mirror
pytest fence (CABINET_EVIDENCE_MIRROR_STORE / _MARKER) — the live store is
never touched.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import framework.evidence_fuel_integrity as fuel_integrity
from framework import evidence_mirror
from framework.evidence import EvidenceRecorder
from framework.fidelity import consequence as consequence_mod
from framework.fidelity import judge_calibration

REPO = Path(__file__).resolve().parents[2]

_MIRROR_ACTOR = {"kind": "system", "id": "consequence-mirror"}
_MIRROR_COMPONENT = {"name": "evidence-mirror", "version": "1", "commit": "unset"}
_CAPTAIN = {"kind": "captain", "id": "captain"}
_LABEL_COMPONENT = {"name": "governance-review", "version": "1", "commit": "unset"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(offset_s: int = 0) -> str:
    return (_now() + timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today8() -> str:
    return _now().strftime("%Y%m%d")


def _day_trial() -> str:
    return f"evt-consequence-{_today8()}"


@pytest.fixture()
def planes(tmp_path, monkeypatch):
    """Scratch consequence ledger + scratch evidence store + scratch report
    surfaces; the mirror pytest fence is OPEN toward the scratch store."""
    store = tmp_path / "evidence-store"
    marker = tmp_path / "degradations.jsonl"
    events = tmp_path / "events"
    journal = tmp_path / "governance-labels.jsonl"
    out = tmp_path / "report" / "fuel-integrity-report.jsonl"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_STORE", str(store))
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_MARKER", str(marker))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    evidence_mirror._reset_state()
    yield SimpleNamespace(store=store, marker=marker, events=events,
                          journal=journal, out=out, tmp=tmp_path)
    evidence_mirror._reset_state()


def _check(planes, **kw):
    kw.setdefault("store_root", planes.store)
    kw.setdefault("labels_journal", planes.journal)
    kw.setdefault("degradations_path", planes.marker)
    return fuel_integrity.check_fuel_integrity(**kw)


def _fuel_row_kwargs(i: int = 0, **overrides):
    base = dict(
        ts=_ts(i),
        actor={"kind": "officer", "id": "tb-cos"},
        lane="tb-ops",
        action="apply testburg fix",
        subject=f"tb-s-{i}",
        proposal={"required": True, "decision": "approved"},
        outcome={"status": "ok", "evidence": "applied cleanly"},
        review={"verdict": "confirmed", "source": "verdict_human",
                "reviewed_at": _ts(i)},
    )
    base.update(overrides)
    return base


def _emit_fuel_row(i: int = 0, **overrides):
    """A live-pipeline fuel row: emit_consequence appends the ledger row AND
    (fence open) the mirror receipt — the legit both-planes pair."""
    return consequence_mod.emit_consequence(**_fuel_row_kwargs(i, **overrides))


def _emit_filler(i: int):
    """Closed non-fuel row (fills cell n/closure without a review)."""
    return consequence_mod.emit_consequence(**{
        **_fuel_row_kwargs(i), "review": None})


def _fill_cell(start: int = 1, count: int = 9) -> None:
    for i in range(start, start + count):
        _emit_filler(i)


def _hand_append(events_dir: Path, row: dict) -> dict:
    """Forge a ledger row the way a same-user attacker would: a direct
    JSONL append that bypasses the emit chokepoint entirely."""
    day = row["ts"][:10]
    path = events_dir / f"consequence-events-{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    return row


def _forge_receipt(store: Path, row: dict, *, attested: bool = True) -> str:
    """Forge the matching consequence-mirror receipt (same-user can: the
    recorder API and signing key are same-user-reachable — HP-1's point)."""
    sha = evidence_mirror._canonical_sha256(row)
    rec = EvidenceRecorder(store)
    ctx = rec.trace(_day_trial(), surface="system", correlation_id=sha)
    detail = {
        "action": "consequence_mirror",
        "consequence_actor": "officer:tb-cos",
        "consequence_action": row["action"],
        "consequence_subject": row["subject"],
        "consequence_ts": row["ts"],
        "row_sha256": sha,
        "ledger_date": row["ts"][:10],
        "lifecycle": sorted(k for k in ("proposal", "outcome", "review")
                            if row.get(k) is not None),
    }
    if attested:
        detail["attestation_mode"] = "process"
    rec.append(ctx, phase="system", status="succeeded", actor=_MIRROR_ACTOR,
               component=_MIRROR_COMPONENT, detail=detail, links=[])
    return sha


def _forge_label(store: Path, trial_id: str, *, jid: str | None,
                 journal: Path | None, session: str = "s-forge") -> list[dict]:
    """A Captain label event pair on the trial (+ optionally the journal
    digest that anchors it) — the governance-review write_label shape."""
    rec = EvidenceRecorder(store)
    detail = {"action": "governance_review_label", "source": "verdict_human",
              "result_code": "confirmed", "basis": "human_verified",
              "session": session}
    links = []
    if jid:
        detail["jid"] = jid
        links = [f"undo-journal:{jid}"]
    ctx = rec.trace(trial_id, surface="cli")
    events = [
        rec.append(ctx, phase="verification", status="verified",
                   actor=_CAPTAIN, component=_LABEL_COMPONENT,
                   detail=detail, links=links),
        rec.append(ctx, phase="outcome", status="succeeded",
                   actor=_CAPTAIN, component=_LABEL_COMPONENT,
                   detail=detail, links=links),
    ]
    if journal is not None:
        digest = {
            "schema": "cabinet.governance-label-digest/v1",
            "ts": _ts(),
            "session": session,
            "trial_id": trial_id,
            "verdict": "confirmed",
            "basis": "human_verified",
            "event_ids": [e.get("event_id") for e in events],
            "event_hashes": [e.get("event_hash") for e in events],
        }
        journal.parent.mkdir(parents=True, exist_ok=True)
        with open(journal, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(digest, sort_keys=True) + "\n")
    return events


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _non_watermark(tree: dict[str, str]) -> dict[str, str]:
    watermark_files = {".verify-watermarks.json", ".verify-watermarks.lock"}
    return {k: v for k, v in tree.items()
            if Path(k).name not in watermark_files}


def _only_row(report: dict) -> dict:
    assert len(report["rows"]) == 1, report["rows"]
    return report["rows"][0]


# ---------------------------------------------------------------------------
# Deliverable 4a — forged single-plane row (no mirror) => ungrounded
# ---------------------------------------------------------------------------


class TestSinglePlaneForgery:
    def test_forged_row_without_mirror_is_ungrounded(self, planes):
        EvidenceRecorder(planes.store)  # a healthy store exists; the row
        _hand_append(planes.events, _fuel_row_kwargs(0, refs=[]))  # bypassed it
        report = _check(planes)
        row = _only_row(report)
        assert row["verdict"] == "ungrounded:unmirrored_row"
        assert row["would_withhold"] is True
        # absence is a grounding failure, never a tamper claim
        assert row["tamper_shaped"] is False
        assert report["summary"]["grounded"] == 0
        assert "graduations grounded: 0/1" in report["weekly_line"]

    def test_missing_receipt_with_degradation_row_is_inconclusive(self, planes):
        """Triage law: NOISE only with affirmative evidence — a matching
        consequence-chokepoint degradation row explains the absence."""
        EvidenceRecorder(planes.store)
        _hand_append(planes.events, _fuel_row_kwargs(0, refs=[]))
        planes.marker.write_text(json.dumps({
            "ts": _now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "chokepoint": "consequence",
            "reason": "recorder_unimportable",
            "message": "system 3.9 shell hook",
        }) + "\n", encoding="utf-8")
        report = _check(planes)
        row = _only_row(report)
        assert row["verdict"] == "unknown:mirror_degraded"
        assert row["tamper_shaped"] is False
        assert row["would_withhold"] is True  # fail-closed, still withheld


# ---------------------------------------------------------------------------
# Deliverable 4b — tampered store => verification fails => flagged
# ---------------------------------------------------------------------------


class TestStoreTamper:
    def test_tampered_store_bytes_flag_verify_failed(self, planes):
        _emit_fuel_row(0)
        ledger_file = planes.store / "trials" / _day_trial() / "events.jsonl"
        assert ledger_file.is_file()
        data = bytearray(ledger_file.read_bytes())
        data[len(data) // 2] ^= 0xFF  # retroactive single-plane byte flip
        ledger_file.write_bytes(bytes(data))

        report = _check(planes)
        row = _only_row(report)
        assert row["verdict"] == "ungrounded:verify_failed"
        assert row["tamper_shaped"] is True
        assert row["would_withhold"] is True

    def test_row_edited_after_mirroring_is_sha_mismatch(self, planes):
        """The INCONSISTENT-forgery arm: the receipt stands, the ledger row
        was retro-edited => recomputed sha finds no receipt."""
        emitted = _emit_fuel_row(0)
        day = emitted["ts"][:10]
        path = planes.events / f"consequence-events-{day}.jsonl"
        # SAME identity tuple (actor, action, subject, ts) => the appended
        # line supersedes (last write wins); only the outcome bytes change.
        edited = dict(emitted)
        edited["outcome"] = {"status": "ok", "evidence": "laundered"}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(edited) + "\n")

        report = _check(planes)
        row = _only_row(report)
        assert row["verdict"] == "ungrounded:row_sha_mismatch"
        assert row["tamper_shaped"] is True

    def test_claimed_trial_missing_without_receipt(self, planes):
        _emit_fuel_row(0)
        import shutil
        shutil.rmtree(planes.store / "trials" / _day_trial())
        report = _check(planes)
        row = _only_row(report)
        assert row["verdict"] == "ungrounded:trial_missing"
        assert row["tamper_shaped"] is True


# ---------------------------------------------------------------------------
# Deliverable 4c — consistent BOTH-plane forgery passes: THE DOCUMENTED GAP
# ---------------------------------------------------------------------------


class TestConsistentDualPlaneForgeryIsTheDocumentedGap:
    def test_consistent_forgery_of_both_planes_passes_and_claim_rides(
            self, planes):
        """A same-user forger who writes the ledger row, the matching signed
        receipt, a Captain label event AND its journal digest — all four
        surfaces this OS user can write today — produces a GROUNDED verdict.

        THIS IS THE DOCUMENTED GAP, by design: the check detects retroactive
        single-plane tamper and inconsistent forgery only; consistent
        same-user forgery of both planes stays open until HP-1 lands
        (OS-user/key isolation).  Necessary, not sufficient.  The test's
        job is to prove the report says so on every line."""
        jid = "j-tb-forged"
        fuel = _fuel_row_kwargs(0, refs=[
            f"evidence-trial:{_day_trial()}", f"undo-journal:{jid}"])
        _hand_append(planes.events, fuel)
        for i in range(1, 10):  # fill the cell to MIN_PAIRS, all closed
            _hand_append(planes.events, {
                **_fuel_row_kwargs(i), "review": None, "refs": []})
        _forge_receipt(planes.store, fuel, attested=True)
        _forge_label(planes.store, _day_trial(), jid=jid,
                     journal=planes.journal)

        report = _check(planes)
        row = _only_row(report)
        assert row["verdict"] == "grounded", row
        assert row["would_withhold"] is False
        assert row["signals"]["mirror"] == "pass"
        assert row["signals"]["row_sha_match"] is True
        assert row["signals"]["third_leg"] == "human_label_row"
        assert row["signals"]["attestation"] == "process"
        assert report["summary"]["grounded"] == 1

        # the honest claim is mandatory text on EVERY report surface
        claim = fuel_integrity.HONEST_CLAIM
        assert "single-plane tamper" in claim and "HP-1" in claim
        assert report["honest_claim"] == claim
        assert row["honest_claim"] == claim
        assert all(c["honest_claim"] == claim for c in report["cells"])
        assert report["summary"]["honest_claim"] == claim
        assert claim in report["weekly_line"]
        # the docstring carries the claim too (wrapped prose — assert the
        # load-bearing phrases, whitespace-normalized)
        doc = " ".join((fuel_integrity.__doc__ or "").split()).casefold()
        for phrase in ("single-plane tamper", "inconsistent forgery only",
                       "hp-1", "necessary, not sufficient"):
            assert phrase in doc

        out = fuel_integrity.write_report(report, planes.out,
                                          store_root=planes.store)
        for line in out.read_text(encoding="utf-8").splitlines():
            assert json.loads(line)["honest_claim"] == claim


# ---------------------------------------------------------------------------
# Purge overlap (A7 / design §2.4)
# ---------------------------------------------------------------------------


class TestPurgeOverlap:
    def test_purged_day_trial_is_reduced_confidence_withhold(self, planes):
        _emit_fuel_row(0)
        tid = _day_trial()
        EvidenceRecorder(planes.store).purge_trial(
            tid, confirmation=f"PURGE {tid}", actor="captain")
        report = _check(planes)
        row = _only_row(report)
        assert row["verdict"] == "ungrounded:purge_overlap"
        assert row["signals"]["purge_overlap"] is True
        assert row["tamper_shaped"] is False  # sanctioned purge, not tamper
        assert row["would_withhold"] is True


# ---------------------------------------------------------------------------
# Third-leg and attestation ladder (A5/HP-2/HP-3, A6)
# ---------------------------------------------------------------------------


class TestThirdLegAndAttestationLadder:
    def test_no_label_anywhere_is_third_leg_absent(self, planes):
        _emit_fuel_row(0)
        _fill_cell()
        row = _only_row(_check(planes))
        assert row["verdict"] == "unknown:third_leg_absent"
        assert row["signals"]["third_leg"] == "absent"

    def test_in_store_label_without_journal_is_unanchored(self, planes):
        """B1/HP-3: in-store rows alone are not the re-count source — an
        unanchored label is advisory and satisfies nothing."""
        _emit_fuel_row(0)
        _fill_cell()
        _forge_label(planes.store, _day_trial(), jid=None, journal=None)
        row = _only_row(_check(planes))
        assert row["verdict"] == "unknown:third_leg_unanchored"
        assert row["signals"]["third_leg"] == "human_label_unanchored"

    def test_anchored_label_reaches_the_attestation_rung(self, planes):
        """With an anchored trial-scope label, the ladder advances to the
        honest production reality: consequence-mirror receipts carry no
        attestation yet ('a separate ceremony wave') => inconclusive."""
        _emit_fuel_row(0)
        _fill_cell()
        _forge_label(planes.store, _day_trial(), jid=None,
                     journal=planes.journal)
        row = _only_row(_check(planes))
        assert row["verdict"] == "unknown:attestation_absent"
        assert row["signals"]["third_leg"] == "human_label_trial"
        assert row["signals"]["attestation"] == "unattested"

    def test_ttl_marker_is_producer_adjacent_never_sufficient(self, planes):
        _emit_fuel_row(0, outcome={
            "status": "ok",
            "evidence": "ttl-48h survived: artifact probed intact"})
        _fill_cell()
        row = _only_row(_check(planes))
        assert row["verdict"] == "unknown:third_leg_producer_adjacent"
        assert row["signals"]["third_leg"] == "machine_probe_producer_adjacent"
        assert row["would_withhold"] is True  # A5: same-hand planes never corroborate


# ---------------------------------------------------------------------------
# Cell floors (B2/B10) — constants imported, never re-minted (R-8/R-11)
# ---------------------------------------------------------------------------


class TestCellFloors:
    def test_insufficient_pairs_is_inconclusive_not_a_verdict(self, planes):
        jid = "j-tb-1"
        fuel = _fuel_row_kwargs(0, refs=[
            f"evidence-trial:{_day_trial()}", f"undo-journal:{jid}"])
        _hand_append(planes.events, fuel)
        _forge_receipt(planes.store, fuel)
        _forge_label(planes.store, _day_trial(), jid=jid,
                     journal=planes.journal)
        row = _only_row(_check(planes))  # cell n == 1 < MIN_PAIRS
        assert row["verdict"] == "unknown:cell_insufficient_pairs"
        assert row["signals"]["cell_floors"] == "insufficient"

    def test_unknown_rate_ceiling_breach_is_ungrounded(self, planes):
        """B2: 'hard to judge' blocks grounding instead of buying it — all
        intents close (closure 1.0) but 3/10 rows carry unknown verdicts."""
        jid = "j-tb-1"
        fuel = _fuel_row_kwargs(0, refs=[
            f"evidence-trial:{_day_trial()}", f"undo-journal:{jid}"])
        _hand_append(planes.events, fuel)
        for i in range(1, 7):  # 6 clean closed fillers
            _hand_append(planes.events, {
                **_fuel_row_kwargs(i), "review": None, "refs": []})
        for i in range(7, 10):  # 3 closed-but-unjudgeable rows => 0.3 > 0.2
            _hand_append(planes.events, {
                **_fuel_row_kwargs(i), "refs": [],
                "review": {"verdict": "unknown"}})
        _forge_receipt(planes.store, fuel)
        _forge_label(planes.store, _day_trial(), jid=jid,
                     journal=planes.journal)
        row = _only_row(_check(planes))
        assert row["verdict"] == "ungrounded:cell_unknown_rate_above_ceiling"

    def test_dangling_intents_breach_the_closure_floor(self, planes):
        """B10: suppressing the bad-news outcome leg costs grounding — 3/10
        recorded intents never resolve to a terminal outcome."""
        jid = "j-tb-1"
        fuel = _fuel_row_kwargs(0, refs=[
            f"evidence-trial:{_day_trial()}", f"undo-journal:{jid}"])
        _hand_append(planes.events, fuel)
        for i in range(1, 7):  # 6 clean closed fillers
            _hand_append(planes.events, {
                **_fuel_row_kwargs(i), "review": None, "refs": []})
        for i in range(7, 10):  # 3 dangling intents (no outcome) => 0.7 < 0.8
            _hand_append(planes.events, {
                **_fuel_row_kwargs(i), "review": None, "refs": [],
                "outcome": None})
        _forge_receipt(planes.store, fuel)
        _forge_label(planes.store, _day_trial(), jid=jid,
                     journal=planes.journal)
        row = _only_row(_check(planes))
        assert row["verdict"] == "ungrounded:cell_closure_below_floor"

    def test_floor_constants_are_the_imported_objects(self):
        assert fuel_integrity.JUDGE_HARD_BAR is judge_calibration.JUDGE_HARD_BAR
        assert fuel_integrity.MIN_PAIRS is judge_calibration.MIN_PAIRS
        assert fuel_integrity.STATUS_MAX_AGE_DAYS is \
            judge_calibration.STATUS_MAX_AGE_DAYS
        assert fuel_integrity.UNKNOWN_RATE_CEILING == pytest.approx(
            1.0 - judge_calibration.JUDGE_HARD_BAR)
        # no argv override of any floor — a bar loosenable from argv is not
        # a bar (judge-calibration law, reused verbatim)
        source = (REPO / "framework" / "evidence_fuel_integrity.py").read_text(
            encoding="utf-8")
        assert "--bar" not in source
        assert "--min-pairs" not in source
        assert "--floor" not in source


# ---------------------------------------------------------------------------
# Gate-fuel honesty — verdict_gate mints structurally zero today (CG-1)
# ---------------------------------------------------------------------------


class TestGateFuelHonesty:
    def test_gate_confirms_counted_but_minted_zero(self, planes):
        _emit_fuel_row(0, review={"verdict": "confirmed",
                                  "source": "verdict_gate",
                                  "reviewed_at": _ts()})
        report = _check(planes)
        assert report["rows"] == []  # promotion-inert => not a fuel row
        gate = report["summary"]["gate_fuel"]
        assert gate == {"confirmed_rows": 1, "minted": 0,
                        "note": "structurally zero: label floor (A3) "
                                "absent — CG-1"}
        assert "graduations grounded: 0/0" in report["weekly_line"]


# ---------------------------------------------------------------------------
# Deliverable 5 — shadow + read-only proofs
# ---------------------------------------------------------------------------


class TestReadOnlyProof:
    def test_two_pass_tree_digest_byte_stability(self, planes):
        """The label-join discipline, replayed for this read path: pass one
        may advance ONLY the signed verify watermarks (the sanctioned
        first-verify side effect, same as the verify verb); pass two is
        fully byte-identical, watermarks included.  The consequence ledger
        dir is byte-identical across BOTH passes."""
        _emit_fuel_row(0)
        _fill_cell()
        _forge_label(planes.store, _day_trial(), jid=None,
                     journal=planes.journal)

        store_before = _tree_digest(planes.store)
        ledger_before = _tree_digest(planes.events)
        report_1 = _check(planes)
        fuel_integrity.write_report(report_1, planes.out,
                                    store_root=planes.store)
        after_one = _tree_digest(planes.store)
        assert _non_watermark(after_one) == _non_watermark(store_before), (
            "the checker wrote NON-watermark store bytes")
        assert _tree_digest(planes.events) == ledger_before, (
            "the checker wrote the minter's ledger dir")

        report_2 = _check(planes)
        fuel_integrity.write_report(report_2, planes.out,
                                    store_root=planes.store)
        assert _tree_digest(planes.store) == after_one, (
            "a repeated check changed store bytes — reads at tip must be "
            "byte-stable, watermarks included")
        assert _tree_digest(planes.events) == ledger_before
        assert planes.out.is_file()  # the one designed write, outside both

    def test_checker_never_creates_an_absent_store(self, planes, tmp_path):
        absent = tmp_path / "no-store-here"
        _hand_append(planes.events, _fuel_row_kwargs(0, refs=[]))
        report = fuel_integrity.check_fuel_integrity(
            store_root=absent, labels_journal=planes.journal,
            degradations_path=planes.marker)
        assert not absent.exists(), (
            "constructing a recorder over an absent store CREATES it — "
            "the checker must refuse, not scaffold")
        assert report["store"]["available"] is False

    def test_report_refuses_paths_the_minter_reads(self, planes):
        _emit_fuel_row(0)
        report = _check(planes)
        with pytest.raises(ValueError):
            fuel_integrity.write_report(
                report, planes.store / "x.jsonl", store_root=planes.store)
        with pytest.raises(ValueError):
            fuel_integrity.write_report(
                report, planes.events / "x.jsonl", store_root=planes.store)

    def test_report_refuses_default_store_when_no_root_given(
            self, planes, monkeypatch):
        """The default-run fence: main() threads store_root=args.store, which
        is None on default-store runs — the fence must resolve the SAME
        default root the check read, or '--out' aimed inside the default
        store is accepted and the 'never write anything the minter reads'
        guarantee is a docstring, not a fence."""
        _emit_fuel_row(0)
        report = _check(planes)
        monkeypatch.setattr(fuel_integrity, "_default_store_root",
                            lambda: planes.store)
        with pytest.raises(ValueError):
            fuel_integrity.write_report(
                report, planes.store / "x.jsonl", store_root=None)
        assert not (planes.store / "x.jsonl").exists(), (
            "the refusal must land BEFORE any byte is written")


class TestShadowProof:
    def test_nothing_in_the_repo_imports_the_checker(self):
        """Grep-provable shadow: no framework/cabinet python file references
        the module (graduation, gate, policy_engine, trust_ladder, action
        lanes, attention — nothing).  Its output feeds no consumer."""
        offenders = []
        for base in ("framework", "cabinet"):
            for path in sorted((REPO / base).rglob("*.py")):
                rel = str(path.relative_to(REPO))
                if rel in ("framework/evidence_fuel_integrity.py",
                           "framework/tests/test_fuel_integrity.py",
                           # The A2 coverage census enumerates the module
                           # PATH as an infra surface row — enumeration is
                           # not consumption (no import, no report read).
                           "cabinet/scripts/evidence-coverage.py",
                           # Phase-4 integration (2026-07-17): the composed
                           # seam proof drives main() on scratch surfaces —
                           # a test, not a consumer.
                           "framework/tests/test_evidence_phase4_seams.py"):
                    continue
                if "evidence_fuel_integrity" in path.read_text(
                        encoding="utf-8", errors="replace"):
                    offenders.append(rel)
        assert offenders == [], (
            f"shadow law: these files reference the checker: {offenders}")

    def test_checker_source_never_touches_write_surfaces(self):
        source = (REPO / "framework" / "evidence_fuel_integrity.py").read_text(
            encoding="utf-8")
        for forbidden in ("emit_consequence", "reserve_consequence",
                          "mirror_consequence", "framework.events",
                          "purge_trial", "repair_verdict"):
            assert forbidden not in source, (
                f"read-only law: checker source references {forbidden}")

    def test_exit_code_carries_no_verdict_signal(self, planes, capsys):
        EvidenceRecorder(planes.store)
        _hand_append(planes.events, _fuel_row_kwargs(0, refs=[]))
        rc = fuel_integrity.main([
            "--store", str(planes.store),
            "--out", str(planes.out),
            "--labels-journal", str(planes.journal),
            "--degradations", str(planes.marker),
        ])
        assert rc == 0, "findings must not surface as a consumable exit code"
        printed = capsys.readouterr().out
        assert "graduations grounded: 0/1" in printed
        assert "[shadow — report-only]" in printed
        assert planes.out.is_file()

    def test_runbook_carries_the_honest_claim(self):
        runbook = REPO / "docs" / "runbooks" / "fuel-integrity.md"
        text = runbook.read_text(encoding="utf-8")
        assert "single-plane tamper" in text
        assert "HP-1" in text
        assert "necessary, not sufficient" in text
        assert "report-only" in text.lower()
