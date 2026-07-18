"""Phase-4 composed seam proofs — the ACTUAL cross-group joins, one scratch store.

The four Phase-4 groups (detectors G1, fuel-integrity G2, calibration G3,
tamper-drill/freeze G4) each carry their own harness; those prove each
module against its OWN fixtures. This file proves the joints between them
against the REAL artifacts — never per-group mocks (integration law,
2026-07-17):

  * G1→G3 — the detector findings journal G1 actually appends
    (per-run summary rows whose `findings[]` carry `trials` sample ids and
    triage verdicts noise|inconclusive) is consumed by G3's pairing and
    produces COUNTED, store-re-verified pairs with the right polarity
    (inconclusive⇒flag⇒wrong; noise⇒pass⇒confirmed).
  * G4→G1+G2+G3 (+ the HP-2 recompute leg) — while the judging-freeze
    marker is present every shadow service refuses to run: one plain
    line, rc 0, zero reads, zero writes (the §2.4 tamper response's
    consumer contract, exercised against the real modules).
  * Composed read-only law — one pass of all three services leaves the
    store byte-stable modulo the sanctioned first-verify watermark
    advance; a second composed pass is fully byte-identical; every report
    surface lands OUTSIDE the store.

Everything here is scratch: scratch repo root, scratch store, scratch
journals, scratch marker (lifted+removed in-test — the sanctioned
drill-harness cleanup of a SCRATCH marker). Synthetic Seamburg vocabulary
only. Shadow law holds throughout: this file is a test, not a consumer —
each group's zero-consumers grep proof lists it by name.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path

from framework import evidence_calibration as ec
from framework import evidence_detectors as ed
from framework import evidence_freeze
from framework import evidence_fuel_integrity as efi
from framework import evidence_recompute as erc
from framework.evidence.recorder import EvidenceRecorder
from framework.measurement.eval_pattern_detector import _DEFAULT_MIN_OCCURRENCES
from framework.onboarding.journey import EVIDENCE_REL  # the ONE store-root constant

ROOT = Path(__file__).resolve().parents[2]

# The REAL production label writer (dash-named Captain CLI) — the same
# importlib pattern as test_evidence_calibration.py.
_GR_SCRIPT = ROOT / "cabinet" / "scripts" / "governance-review.py"
_spec = importlib.util.spec_from_file_location(
    "governance_review_seam_test", _GR_SCRIPT)
gr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gr)

_OFFICER = {"kind": "officer", "id": "sb-cos"}


# ---------------------------------------------------------------------------
# scratch-repo builder (the composed scenario every test starts from)
# ---------------------------------------------------------------------------

def _seed_failure_trial(rec: EvidenceRecorder, trial_id: str,
                        component: str, result_code: str) -> str:
    ctx = rec.trace(trial_id, surface="system")
    comp = {"name": component, "version": "1"}
    rec.append(ctx, phase="intent", status="started", actor=_OFFICER,
               component=comp, detail={"action": "seamburg_probe"})
    rec.append(ctx, phase="execution", status="failed", actor=_OFFICER,
               component=comp, detail={"action": "seamburg_probe",
                                       "result_code": result_code})
    return trial_id


def _label(store: Path, rec: EvidenceRecorder, journal: Path,
           trial_id: str, verdict: str) -> dict:
    """Land a Captain label through the PRODUCTION path and append the
    digest row to the scratch governance-labels journal."""
    cand = gr.classify_trial(gr._read_raw_events(store, trial_id))
    cand["trial_id"] = trial_id
    events = gr.write_label(rec, trial_id, verdict, "", cand,
                            session="seam-test", channel=gr.CHANNEL_TTY)
    digest = gr.label_digest_record("seam-test", trial_id, verdict, cand,
                                    events, channel=gr.CHANNEL_TTY)
    gr._append_journal_line(journal, digest)
    return digest


def _build_scratch_repo(root: Path) -> dict:
    """One scratch repo root carrying the house-relative surfaces:

      * a store at <root>/<journey.EVIDENCE_REL> (the default ed.main
        resolves under --repo-root; imported, never a mirrored literal)
        with TWO failure clusters: component seamburg-exec (no degradation
        recorded → triage INCONCLUSIVE → machine flag) and component
        seamburg-mirror (matching in-window degradation row → triage NOISE
        → machine pass);
      * Captain labels via the real writer: one seamburg-exec trial labeled
        `wrong` (agrees with flag) and one seamburg-mirror trial labeled
        `right`→confirmed (agrees with pass);
      * the degradation ledger row that makes the NOISE attribution
        affirmative (exact component match, in-window ts).
    """
    store = root / EVIDENCE_REL
    labels = root / "shared" / "interfaces" / "governance-labels.jsonl"
    labels.parent.mkdir(parents=True, exist_ok=True)
    rec = EvidenceRecorder(store)

    exec_trials = [
        _seed_failure_trial(rec, f"evt-sb-exec-{i}", "seamburg-exec", "sb-x")
        for i in range(1, _DEFAULT_MIN_OCCURRENCES + 1)
    ]
    mirror_trials = [
        _seed_failure_trial(rec, f"evt-sb-mir-{i}", "seamburg-mirror", "sb-m")
        for i in range(1, _DEFAULT_MIN_OCCURRENCES + 1)
    ]

    # The Captain CLI's input vocabulary is right|wrong|unclear; the journal
    # digest rows carry the scoreable confirmed|wrong the pairing reads.
    _label(store, rec, labels, exec_trials[0], "wrong")
    _label(store, rec, labels, mirror_trials[0], "right")

    degradations = root / "cabinet" / "logs" / "evidence-mirror-degradations.jsonl"
    degradations.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    degradations.write_text(json.dumps({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "chokepoint": "seamburg-mirror",
        "reason": "sb-degraded",
    }, sort_keys=True) + "\n", encoding="utf-8")

    return {"root": root, "store": store, "labels": labels,
            "exec_trials": exec_trials, "mirror_trials": mirror_trials,
            "journal": root / "shared" / "interfaces"
                            / "evidence-shadow-findings.jsonl"}


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _non_watermark(tree: dict[str, str]) -> dict[str, str]:
    watermark = {".verify-watermarks.json", ".verify-watermarks.lock"}
    return {k: v for k, v in tree.items() if Path(k).name not in watermark}


def _run_calibration(scenario: dict,
                     status_name: str = "status.json") -> tuple[int, Path]:
    status_target = scenario["root"] / status_name
    rc = ec.run(repo_root=scenario["root"],
                status_target=status_target,
                out_dir=scenario["root"] / "cabinet" / "logs")
    return rc, status_target


# ---------------------------------------------------------------------------
# G1 → G3: the actual journal joins the actual pairing
# ---------------------------------------------------------------------------

def test_detector_journal_joins_calibration_pairing(tmp_path, capsys):
    scenario = _build_scratch_repo(tmp_path)
    assert ed.main(["--repo-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "shadow report appended" in out
    report = json.loads(scenario["journal"].read_text().splitlines()[-1])
    verdicts = {f["component"]: f["verdict"] for f in report["findings"]}
    # The triage split the composed scenario is built around:
    assert verdicts["seamburg-exec"] == ed.INCONCLUSIVE
    assert verdicts["seamburg-mirror"] == ed.NOISE

    rc, status_target = _run_calibration(scenario)
    assert rc == 0
    status = json.loads(status_target.read_text())

    # The join carried: every finding row was joinable (G1's `trials` key)
    # and scoreable (G1's noise|inconclusive vocabulary) — zero silent drops.
    assert status["totals"]["flags"]["rows"] == len(report["findings"])
    assert status["totals"]["flags"]["unjoinable"] == 0
    assert status["totals"]["flags"]["unscoreable"] == 0
    # Two Captain labels → two candidate pairs, both re-verified against the
    # store (B1) and counted.
    assert status["totals"]["candidate_pairs"] == 2
    assert status["totals"]["counted_pairs"] == 2
    assert status["totals"]["excluded"] == {
        "store_unavailable": 0, "unverified": 0, "purged": 0,
        "digest_hashes_missing": 0}

    # Polarity across the seam: inconclusive⇒flag⇒wrong (agrees with the
    # Captain's `wrong`), noise⇒pass⇒confirmed (agrees with `confirmed`).
    strata = status["strata"]
    by_component = {block["axes"]["component"]: block
                    for block in strata.values()}
    exec_agreement = by_component["seamburg-exec"]["agreement"]
    mirror_agreement = by_component["seamburg-mirror"]["agreement"]
    assert exec_agreement["pairs"] == 1
    assert exec_agreement["confusion"]["hw_jw"] == 1  # human wrong, judge wrong
    assert mirror_agreement["pairs"] == 1
    assert mirror_agreement["confusion"]["hc_jc"] == 1  # both confirmed
    # Shadow law rides the artifact itself.
    assert status["shadow"] is True
    assert status["power"] == "none"
    for block in strata.values():  # thin pairs stay honestly uncalibrated
        assert block["state"] == ec.STATE_UNCALIBRATED


# ---------------------------------------------------------------------------
# G4 → G1 + G2 + G3: the freeze marker halts all three shadow services
# ---------------------------------------------------------------------------

def test_freeze_marker_halts_all_three_services(tmp_path, capsys, monkeypatch):
    scenario = _build_scratch_repo(tmp_path)
    marker = evidence_freeze.freeze(tmp_path, "seam-proof", set_by="seam-test",
                                    drill=True)
    try:
        assert evidence_freeze.is_frozen(tmp_path)

        # G1 refuses: rc 0, one plain line, journal never created.
        assert ed.main(["--repo-root", str(tmp_path)]) == 0
        assert "frozen — refusing to run" in capsys.readouterr().out
        assert not scenario["journal"].exists()

        # G3 refuses: rc 0, status file never written.
        sink = io.StringIO()
        status_target = tmp_path / "frozen-status.json"
        rc = ec.run(repo_root=tmp_path, status_target=status_target,
                    out_dir=tmp_path / "cabinet" / "logs", out=sink)
        assert rc == 0
        assert "frozen — refusing to run" in sink.getvalue()
        assert not status_target.exists()

        # G2 refuses: rc 0, report file never created (repo root pinned to
        # the scratch tree so the marker under test is the one consulted).
        monkeypatch.setattr(efi, "_repo_root", lambda: tmp_path)
        fuel_out = tmp_path / "cabinet" / "logs" / "fuel-frozen.jsonl"
        assert efi.main(["--store", str(scenario["store"]),
                         "--out", str(fuel_out)]) == 0
        assert "frozen — refusing to run" in capsys.readouterr().out
        assert not fuel_out.exists()

        # The HP-2 recompute leg refuses the same way (the fourth shadow
        # service): rc 0, one plain line, report never created, zero store
        # appends while frozen.
        monkeypatch.setattr(erc, "_repo_root", lambda: tmp_path)
        recompute_out = tmp_path / "cabinet" / "logs" / "recompute-frozen.jsonl"
        assert erc.main(["--store", str(scenario["store"]),
                         "--out", str(recompute_out)]) == 0
        assert "frozen — refusing to run" in capsys.readouterr().out
        assert not recompute_out.exists()
    finally:
        # Sanctioned drill-harness cleanup of a SCRATCH marker (uchg would
        # otherwise outlive the test and break tmp_path collection).
        evidence_freeze._lift_immutable(marker)
        marker.unlink(missing_ok=True)

    # Cleared marker: G1 runs again (the freeze was the only inhibitor).
    assert not evidence_freeze.is_frozen(tmp_path)
    assert ed.main(["--repo-root", str(tmp_path)]) == 0
    assert scenario["journal"].exists()


# ---------------------------------------------------------------------------
# Composed read-only law: byte-stable store, all surfaces outside it
# ---------------------------------------------------------------------------

def test_composed_pass_store_byte_stable_and_surfaces_outside(
        tmp_path, capsys, monkeypatch):
    scenario = _build_scratch_repo(tmp_path)
    store = scenario["store"]
    pre = _tree_digest(store)

    # An empty consequence-ledger dir of its own so the composed G2 run is
    # hermetic against rows other tests wrote into the session sandbox.
    ledger_dir = tmp_path / "consequence-events"
    ledger_dir.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(ledger_dir))
    fuel_out = tmp_path / "cabinet" / "logs" / "fuel-integrity-report.jsonl"

    def _one_pass(status_name: str) -> None:
        assert ed.main(["--repo-root", str(tmp_path)]) == 0
        rc, status_target = _run_calibration(scenario, status_name)
        assert rc == 0
        assert status_target.exists()
        assert efi.main(["--store", str(store),
                         "--out", str(fuel_out)]) == 0

    _one_pass("status-pass1.json")
    after_first = _tree_digest(store)
    # First composed pass: only the sanctioned first-verify watermark
    # sidecar may differ from the seeded store.
    assert _non_watermark(after_first) == _non_watermark(pre)

    _one_pass("status-pass2.json")
    # Second composed pass: fully byte-identical (watermark advance is
    # first-verify-only; no new code path writes a store byte).
    assert _tree_digest(store) == after_first

    # Every produced surface lands OUTSIDE the store tree.
    produced = [
        scenario["journal"],
        tmp_path / "status-pass1.json",
        tmp_path / "status-pass2.json",
        tmp_path / "cabinet" / "logs" / ec.REPORT_BASENAME,
        tmp_path / "cabinet" / "logs" / ec.SERIES_BASENAME,
        fuel_out,
    ]
    store_resolved = store.resolve()
    for path in produced:
        assert path.exists(), path
        assert store_resolved not in path.resolve().parents, path
    # And the weekly lines carry the shadow/honest-claim framing.
    out = capsys.readouterr().out
    assert "shadow" in out
    assert "HP-1" in out
