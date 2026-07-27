"""Phase-4 SHADOW per-stratum calibration — behavior + law pins.

Pins for framework/evidence_calibration.py (design §3 Phase 4; R-8/R-11):
  * constants BY REFERENCE — the hard bar / MIN_PAIRS / freshness window are
    judge_calibration's, never a second number, never argv-loosenable;
  * pairing semantics mirror collect_pairs (latest scoreable per side,
    window on the HUMAN ts, unclear scores neither, flag<->wrong polarity),
    with the REAL production label writer (governance-review.py) minting the
    Captain leg;
  * B1 re-count — pairs that cannot be re-verified against the store are
    excluded, never counted;
  * status-file discipline — atomic, written on every successful
    measurement (all-uncalibrated launch state included), NEVER written on
    measurement error; readers refuse stale/future proofs and re-derive
    states from stored numbers;
  * store byte-stability — the two-pass tree-digest proof
    (test_evidence_label_join's harness): non-watermark bytes identical
    after the first measurement pass, fully byte-identical at tip;
  * never-a-score / shadow — outputs are Captain-facing only; a repo grep
    proves NOTHING outside this module+test references it or its series
    (zero callers is the designed shadow state).

Hermetic: scratch stores + scratch journals only; the repo-root conftest
fences CABINET_EVENT_LOG_DIR. Synthetic Testburg vocabulary only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from framework import evidence_calibration as ec
from framework.evidence.recorder import EvidenceRecorder
from framework.fidelity import judge_calibration as jc
from framework.onboarding.journey import EVIDENCE_REL

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "framework" / "evidence_calibration.py"

# The REAL production label writer (dash-named Captain CLI) — the same
# importlib pattern as cabinet/scripts/tests/test_evidence_label_join.py.
_GR_SCRIPT = ROOT / "cabinet" / "scripts" / "governance-review.py"
_spec = importlib.util.spec_from_file_location(
    "governance_review_calibration_test", _GR_SCRIPT)
gr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gr)

_OFFICER = {"kind": "officer", "id": "tb-cos"}
_NOW = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# fixture helpers (scratch store + REAL label writer + detector flag rows)
# ---------------------------------------------------------------------------

def _seed_trial(rec: EvidenceRecorder, trial_id: str,
                component: str = "testburg-exec") -> str:
    ctx = rec.trace(trial_id, surface="system")
    detail = {"action": "write_testburg_note"}
    rec.append(ctx, phase="intent", status="started", actor=_OFFICER,
               component={"name": component, "version": "1"}, detail=detail)
    rec.append(ctx, phase="execution", status="succeeded", actor=_OFFICER,
               component={"name": component, "version": "1"}, detail=detail)
    return trial_id


def _label(store: Path, rec: EvidenceRecorder, journal: Path, trial_id: str,
           verdict: str, ts: str | None = None) -> dict:
    """Land a Captain label through the PRODUCTION path (write_label +
    label_digest_record, channel-attested per HP-3 — the writer refuses
    unattested contexts) and append the digest row to the scratch journal.
    `ts` overrides only the JOURNAL row's ts (the window filter's clock)."""
    cand = gr.classify_trial(gr._read_raw_events(store, trial_id))
    cand["trial_id"] = trial_id
    events = gr.write_label(rec, trial_id, verdict, "", cand,
                            session="cal-test", channel=gr.CHANNEL_TTY)
    digest = gr.label_digest_record("cal-test", trial_id, verdict, cand,
                                    events, channel=gr.CHANNEL_TTY)
    if ts is not None:
        digest["ts"] = ts
    gr._append_journal_line(journal, digest)
    return digest


def _fake_digest(journal: Path, trial_id: str, verdict: str,
                 hashes: list[str], ts: str = "2026-07-17T10:00:00.000000Z"
                 ) -> None:
    gr._append_journal_line(journal, {
        "schema": ec.LABEL_DIGEST_SCHEMA, "ts": ts, "session": "cal-test",
        "trial_id": trial_id, "verdict": verdict, "basis": "self_asserted",
        "channel": gr.CHANNEL_TTY,  # attested CLAIM — the store re-check
        "event_ids": ["evd-fake"], "event_hashes": hashes,  # must catch it
    })


def _flag(flags: Path, trial_id: str | None,
          failure_class: str = "polarity-fail", verdict: str | None = None,
          component: str = "testburg-exec",
          ts: str = "2026-07-17T11:00:00.000000Z", **extra) -> None:
    row: dict = {"ts": ts, "component": component,
                 "failure_class": failure_class}
    if trial_id is not None:
        row["trial_id"] = trial_id
    if verdict is not None:
        row["verdict"] = verdict
    row.update(extra)
    flags.parent.mkdir(parents=True, exist_ok=True)
    with flags.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _non_watermark(tree: dict[str, str]) -> dict[str, str]:
    watermark = {".verify-watermarks.json", ".verify-watermarks.lock"}
    return {k: v for k, v in tree.items() if Path(k).name not in watermark}


# ---------------------------------------------------------------------------
# constants by reference (R-11) + journal-literal pin
# ---------------------------------------------------------------------------

def test_constants_by_reference_never_a_second_number():
    src = MODULE_PATH.read_text(encoding="utf-8")
    # Imported, not redefined: no local assignment of the three numbers.
    assert "from framework.fidelity.judge_calibration import" in src
    for name in ("JUDGE_HARD_BAR", "MIN_PAIRS", "STATUS_MAX_AGE_DAYS"):
        assert not re.search(rf"^{name}\s*=", src, re.MULTILINE), (
            f"{name} must be imported by reference, never redefined")
    # No second literal of the bar anywhere in the module.
    assert "0.80" not in src and "0.8 " not in src
    # No argv loosening: a bar someone can lower from argv is not a bar
    # (the docstring may NAME the forbidden knobs; argparse may not add them).
    for flag in ("--bar", "--min-pairs", "--hard-bar", "--max-age"):
        assert f'add_argument("{flag}"' not in src
        assert f"add_argument('{flag}'" not in src
    # The status body self-documents the upstream constants.
    status = ec.measure()
    assert status["hard_bar"] == jc.JUDGE_HARD_BAR
    assert status["min_pairs"] == jc.MIN_PAIRS
    assert status["max_age_days"] == jc.STATUS_MAX_AGE_DAYS
    # One journal literal, pinned equal to the production writer's.
    assert ec.LABELS_JOURNAL_REL == gr.LABELS_JOURNAL_REL


# ---------------------------------------------------------------------------
# pairing: polarity, latest-per-side, window, unclear, unjoinable
# ---------------------------------------------------------------------------

def test_pairing_polarity_window_and_supersession(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)

    for tid in ("evt-tb-agree-1", "evt-tb-disagree-1", "evt-tb-pass-1",
                "evt-tb-unclear-1", "evt-tb-flagonly-1", "evt-tb-labelonly-1",
                "evt-tb-relabel-1", "evt-tb-window-1"):
        _seed_trial(rec, tid)

    _label(store, rec, journal, "evt-tb-agree-1", "wrong")
    _label(store, rec, journal, "evt-tb-disagree-1", "right")
    _label(store, rec, journal, "evt-tb-pass-1", "right")
    _label(store, rec, journal, "evt-tb-unclear-1", "unclear")
    _label(store, rec, journal, "evt-tb-labelonly-1", "wrong")
    _label(store, rec, journal, "evt-tb-relabel-1", "wrong")
    _label(store, rec, journal, "evt-tb-relabel-1", "right")   # re-label wins
    _label(store, rec, journal, "evt-tb-window-1", "wrong",
           ts="2020-01-01T00:00:00.000000Z")                    # pre-window

    _flag(flags, "evt-tb-agree-1")
    _flag(flags, "evt-tb-disagree-1")
    _flag(flags, "evt-tb-pass-1", verdict="pass")
    _flag(flags, "evt-tb-unclear-1")
    _flag(flags, "evt-tb-flagonly-1", failure_class="orphan-fail")
    _flag(flags, "evt-tb-relabel-1")
    _flag(flags, "evt-tb-window-1")
    _flag(flags, None)                                          # unjoinable
    _flag(flags, "evt-tb-relabel-1", verdict="mystery")         # unscoreable
    # An earlier machine row superseded by the later flag above:
    _flag(flags, "evt-tb-agree-1", failure_class="stale-fail",
          ts="2026-07-17T09:00:00.000000Z")

    status = ec.measure(store_root=store, labels_journal=journal,
                        flags_paths=[flags], since="2026-01-01", now=_NOW)

    totals = status["totals"]
    assert totals["labels"]["rows"] == 8
    assert totals["labels"]["unscoreable"] == 1      # unclear scores neither
    assert totals["labels"]["windowed_out"] == 1     # human-ts window filter
    assert totals["flags"]["unjoinable"] == 1
    assert totals["flags"]["unscoreable"] == 1
    assert totals["candidate_pairs"] == 4
    assert totals["counted_pairs"] == 4              # all re-verified green

    key = "component=testburg-exec|failure_class=polarity-fail"
    block = status["strata"][key]
    agreement = block["agreement"]
    # agree: wrong+flag, right+pass · disagree: right+flag, relabel(right)+flag
    assert agreement["pairs"] == 4
    assert agreement["agreements"] == 2
    assert agreement["confusion"] == {
        "hc_jc": 1, "hc_jw": 2, "hw_jc": 0, "hw_jw": 1}
    assert block["state"] == ec.STATE_UNCALIBRATED   # 4 < MIN_PAIRS
    assert block["axes"] == {"component": "testburg-exec",
                             "failure_class": "polarity-fail"}
    # basis-at-label-time: the re-label's basis is human_verified because a
    # captain leg already existed when the superseding label landed.
    assert block["recorded"]["basis"] == {"self_asserted": 3,
                                          "human_verified": 1}

    # Flag-only stratum stays visible as an honest n=0 uncalibrated row.
    orphan = status["strata"][
        "component=testburg-exec|failure_class=orphan-fail"]
    assert orphan["state"] == ec.STATE_UNCALIBRATED
    assert orphan["agreement"]["pairs"] == 0
    assert orphan["agreement"]["agreement_rate"] is None

    # The superseded machine row's stratum still renders (observed axis)…
    assert ("component=testburg-exec|failure_class=stale-fail"
            in status["strata"])
    # …and the latest machine row owns the pair (no double-count).
    assert sum(b["agreement"]["pairs"]
               for b in status["strata"].values()) == 4


# ---------------------------------------------------------------------------
# three-way stratum states at real MIN_PAIRS volume
# ---------------------------------------------------------------------------

def test_stratum_states_three_way(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)

    def _bundle(prefix: str, count: int, verdicts: list[str],
                failure_class: str) -> None:
        for index in range(count):
            tid = f"evt-tb-{prefix}-{index}"
            _seed_trial(rec, tid)
            _label(store, rec, journal, tid, verdicts[index % len(verdicts)])
            _flag(flags, tid, failure_class=failure_class)

    _bundle("s1", jc.MIN_PAIRS, ["wrong"], "s1-fail")           # 100% agree
    _bundle("s2", jc.MIN_PAIRS, ["wrong", "right"], "s2-fail")  # 50% agree
    _bundle("s3", 2, ["wrong"], "s3-fail")                      # thin

    status = ec.measure(store_root=store, labels_journal=journal,
                        flags_paths=[flags], now=_NOW)
    states = {key: block["state"] for key, block in status["strata"].items()}
    assert states == {
        "component=testburg-exec|failure_class=s1-fail": ec.STATE_AT_BAR,
        "component=testburg-exec|failure_class=s2-fail": ec.STATE_BELOW_BAR,
        "component=testburg-exec|failure_class=s3-fail":
            ec.STATE_UNCALIBRATED,
    }
    s1 = status["strata"]["component=testburg-exec|failure_class=s1-fail"]
    assert s1["agreement"]["bar_met"] is True
    assert s1["agreement"]["hard_bar"] == jc.JUDGE_HARD_BAR
    # Shadow law is embedded in the artifact itself.
    assert status["shadow"] is True and status["power"] == "none"
    assert "NO stratum grants power" in status["shadow_note"]

    # The weekly line renders the summary + the shadow disclaimer.
    line = ec.render_weekly_line(status)
    assert line.startswith("calibration: 3 strata (1 at-bar, 1 below-bar, "
                           "1 uncalibrated)")
    assert "shadow (no stratum grants power)" in line
    assert "n=%d" % jc.MIN_PAIRS in line and "agreement=100%" in line

    # read_status re-derives the same states from the stored numbers.
    target = ec.write_status(status, path=tmp_path / "status.json")
    view = ec.read_status(path=target, now=_NOW)
    assert view["usable"] is True
    assert view["states"] == states


# ---------------------------------------------------------------------------
# B1 re-count: unverifiable pairs are excluded, never counted
# ---------------------------------------------------------------------------

def test_b1_reverify_excludes_unbacked_pairs(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)

    _seed_trial(rec, "evt-tb-b1-1")
    # A digest row whose hashes are NOT in the trial (fabricated journal
    # row over a real trial) and one naming a trial that does not exist.
    _fake_digest(journal, "evt-tb-b1-1", "wrong", ["ab" * 32])
    _fake_digest(journal, "evt-tb-ghost-1", "wrong", ["cd" * 32])
    _flag(flags, "evt-tb-b1-1")
    _flag(flags, "evt-tb-ghost-1")

    status = ec.measure(store_root=store, labels_journal=journal,
                        flags_paths=[flags], now=_NOW)
    totals = status["totals"]
    assert totals["candidate_pairs"] == 2
    assert totals["counted_pairs"] == 0
    assert totals["excluded"]["digest_hashes_missing"] == 1
    assert totals["excluded"]["unverified"] == 1
    for block in status["strata"].values():
        assert block["state"] == ec.STATE_UNCALIBRATED
        assert block["agreement"]["pairs"] == 0

    # No store at all: every candidate is excluded as store_unavailable.
    labels = ec.read_label_digests(journal)
    flag_rows, _ = ec.read_detector_flags([flags])
    pairs, _ = ec.collect_stratum_pairs(labels, flag_rows)
    counted, excluded = ec.verify_pairs(None, pairs)
    assert counted == [] and excluded["store_unavailable"] == 2


# ---------------------------------------------------------------------------
# empty-data honesty: the LAUNCH state
# ---------------------------------------------------------------------------

def test_empty_data_launch_state(tmp_path):
    root = tmp_path / "repo"
    (root / "shared" / "interfaces").mkdir(parents=True)
    status = ec.measure(repo_root=root, now=_NOW)
    assert status["strata"] == {}
    assert status["totals"]["labels"]["rows"] == 0
    assert status["totals"]["counted_pairs"] == 0
    assert status["coverage_note"] == ec.LAUNCH_NOTE

    report = ec.render_report(status)
    assert "no scoreable Captain labels yet" in report
    assert "uncalibrated" in report
    assert "SHADOW" in report
    line = ec.render_weekly_line(status)
    assert line == ("calibration: no Captain labels yet — all strata "
                    "uncalibrated — shadow (no stratum grants power)")

    # Labels exist but detectors never flagged a labeled trial: still 0
    # pairs, honestly distinguished from the launch state.
    store = root / EVIDENCE_REL
    rec = EvidenceRecorder(store)
    journal = root / ec.LABELS_JOURNAL_REL
    _seed_trial(rec, "evt-tb-lonely-1")
    _label(store, rec, journal, "evt-tb-lonely-1", "wrong")
    status2 = ec.measure(repo_root=root, now=_NOW)
    assert status2["coverage_note"] == ec.NO_OVERLAP_NOTE
    assert "no detector/label overlap yet" in ec.render_weekly_line(status2)


# ---------------------------------------------------------------------------
# status-file discipline (atomic; stale/future refusal; error writes nothing)
# ---------------------------------------------------------------------------

def test_status_file_discipline(tmp_path):
    target = tmp_path / "status.json"

    # Written on a successful all-uncalibrated measurement (launch state).
    status = ec.measure(now=_NOW)
    ec.write_status(status, path=target)
    body = json.loads(target.read_text())
    assert body["schema"] == ec.STATUS_SCHEMA
    assert body["shadow"] is True and body["power"] == "none"
    assert ec.read_status(path=target, now=_NOW)["usable"] is True

    # Stale proof refused (STATUS_MAX_AGE_DAYS is the upstream constant).
    stale_days = jc.STATUS_MAX_AGE_DAYS + 1
    old = ec.measure(now=_NOW - timedelta(days=stale_days))
    ec.write_status(old, path=target)
    view = ec.read_status(path=target, now=_NOW)
    assert view["usable"] is False and "stale" in view["reason"]

    # Future-dated proof is a clock lie — refused.
    future = ec.measure(now=_NOW + timedelta(days=1))
    ec.write_status(future, path=target)
    view = ec.read_status(path=target, now=_NOW)
    assert view["usable"] is False and "future" in view["reason"]

    # Corrupt file: unusable, never raises.
    target.write_text("{not json")
    assert ec.read_status(path=target, now=_NOW)["usable"] is False

    # Measurement error writes NOTHING: an existing-but-broken labels
    # journal (a directory) must fail loud, not measure zero labels.
    broken = tmp_path / "labels-as-dir.jsonl"
    broken.mkdir()
    fresh_target = tmp_path / "never-written.json"
    rc = ec.main(["--repo-root", str(tmp_path / "repo-x"),
                  "--labels-journal", str(broken),
                  "--status-path", str(fresh_target),
                  "--out-dir", str(tmp_path / "out")])
    assert rc == 2
    assert not fresh_target.exists()
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# store byte-stability: the two-pass tree-digest proof
# ---------------------------------------------------------------------------

def test_measurement_leaves_store_byte_stable(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)
    _seed_trial(rec, "evt-tb-stable-1")
    _label(store, rec, journal, "evt-tb-stable-1", "wrong")
    _flag(flags, "evt-tb-stable-1")

    before = _tree_digest(store)
    status1 = ec.measure(store_root=store, labels_journal=journal,
                         flags_paths=[flags], now=_NOW)
    after_first = _tree_digest(store)
    # Pass 1: the only permitted delta is the verifier's first-verify
    # watermark advance (the sanctioned side effect, same as `verify`).
    assert _non_watermark(after_first) == _non_watermark(before)
    status2 = ec.measure(store_root=store, labels_journal=journal,
                         flags_paths=[flags], now=_NOW)
    # Pass 2 at tip: fully byte-identical, watermark sidecar included.
    assert _tree_digest(store) == after_first
    assert status1["totals"] == status2["totals"]
    assert status1["totals"]["counted_pairs"] == 1


# ---------------------------------------------------------------------------
# CLI end-to-end + report surfaces stay off officer-readable feeds
# ---------------------------------------------------------------------------

def test_cli_end_to_end_writes_captain_surfaces_only(tmp_path, capsys):
    root = tmp_path / "repo"
    store = root / EVIDENCE_REL
    journal = root / ec.LABELS_JOURNAL_REL
    flags = root / ec.FLAGS_JOURNAL_REL
    rec = EvidenceRecorder(store)
    _seed_trial(rec, "evt-tb-cli-1")
    _label(store, rec, journal, "evt-tb-cli-1", "wrong")
    _flag(flags, "evt-tb-cli-1")

    shared_before = _tree_digest(root / "shared")
    status_target = tmp_path / "status.json"
    rc = ec.main(["--repo-root", str(root),
                  "--status-path", str(status_target)])
    out = capsys.readouterr().out
    assert rc == 0
    assert status_target.is_file()

    # Captain surfaces under cabinet/logs (gitignored runtime dir).
    report = root / ec.OUT_DIR_REL / ec.REPORT_BASENAME
    series = root / ec.OUT_DIR_REL / ec.SERIES_BASENAME
    assert report.is_file() and series.is_file()
    rows = [json.loads(line) for line in
            series.read_text().splitlines() if line.strip()]
    assert len(rows) == 1 and rows[0]["schema"] == ec.SERIES_SCHEMA
    assert "shadow (no stratum grants power)" in rows[0]["weekly_line"]
    assert "calibration: stratum " in out    # single-stratum weekly line

    # Officer-readable feed surfaces gained NOTHING: shared/interfaces is
    # byte-identical (the journals there are read-only inputs).
    assert _tree_digest(root / "shared") == shared_before
    # And nothing was written inside the store beyond the watermark advance.
    for path in (report, series, status_target):
        assert store not in path.parents


# ---------------------------------------------------------------------------
# never-a-score / zero-callers: grep-provable shadow
# ---------------------------------------------------------------------------

def _tracked_files(root: Path) -> list[str]:
    """`git ls-files` (fixed argv, read-only) — the same enumeration the
    never-a-score harness uses. The shadow grep is a REPO-law pin; outside a
    git checkout it is meaningless, so no walk fallback: skip loudly."""
    try:
        proc = subprocess.run(["git", "ls-files"], cwd=str(root),
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"git unavailable — tracked-file grep needs git ({exc})")
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip("not a git checkout — tracked-file grep needs git")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def test_shadow_zero_callers_and_never_a_score():
    # cabinet/scripts/evidence-coverage.py is the ONE sanctioned reference
    # outside module+test: the A2 coverage gate must ENUMERATE the module
    # (exact-path SURFACES row) or the module itself trips the gate's
    # unenumerated-surface drift catch.  That reference is classification
    # data only — pinned below to never be an import, so the gate consumes
    # no calibration output and the zero-CONSUMERS shadow state holds.
    allowed = {"framework/evidence_calibration.py",
               "framework/tests/test_evidence_calibration.py",
               "cabinet/scripts/evidence-coverage.py",
               # Phase-4 integration (2026-07-17): the composed seam proof
               # (tests are not consumers) + Captain-facing prose. Neither
               # imports the module into an acting surface.
               "framework/tests/test_evidence_phase4_seams.py",
               "docs/runbooks/evidence-recorder-v1.md",
               "shared/interfaces/reviews/evidence-phase4-shadow-judge-cp1.md",
               # The detectors' own shadow grep NAMES this module in its
               # reference allowlist (the G1↔G3 join row) — an allowlist
               # string in a proof, never an import or a consumer.
               "framework/tests/test_evidence_detectors.py",
               # The docs-sweep glob list names the report/series runtime
               # paths so the runbook may cite them — patterns, never a
               # consumer.
               "cabinet/scripts/docs-sweep-allowlist.txt",
               # HP-3 (2026-07-18): the label-channel test drives the
               # fail-closed pairing seams — a test, never a consumer.
               "cabinet/scripts/tests/test_label_channel_auth.py",
               # HP-1/2/3 integration docs (2026-07-18): the amendment
               # contract and the deploy-ceremony hand-off name the module
               # in prose (fail-closed pairing law, exit checks) — Captain
               # documents, never consumers.
               "docs/proposals/germline-amendment-evidence-hp-2026-07-17.md",
               "docs/runbooks/evidence-hp-deploy.md",
               # Expansion registry (2026-07-27): the architecture baseline sets are
               # the census's inventory of WHICH framework modules exist, so every
               # module path is there by construction — a member-name row in a data
               # file, never an import and never a consumer. A future module under a
               # zero-consumers shadow law needs the same entry in its own landing.
               "cabinet/config/architecture-baseline-sets.yml"}
    needles = (b"evidence_calibration", b"evidence-calibration")
    hits: set[str] = set()
    for rel in _tracked_files(ROOT):
        path = ROOT / rel
        if not path.is_file() or path.is_symlink():
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        if b"\0" in blob[:8192]:
            continue
        if any(needle in blob for needle in needles):
            hits.add(rel)
    assert hits <= allowed, (
        "SHADOW VIOLATION: something outside the calibration module+test "
        f"references it — {sorted(hits - allowed)}")

    # The coverage gate names the module ONLY as enumeration data: any
    # import seam there would make the gate a consumer — forbidden.
    coverage_src = (ROOT / "cabinet" / "scripts" /
                    "evidence-coverage.py").read_text(encoding="utf-8")
    assert not re.search(
        r"(?m)^[ \t]*(?:from[ \t]+framework(?:\.[A-Za-z_.]+)?[ \t]+import\b"
        r"|import[ \t]+framework\b)", coverage_src), (
        "evidence-coverage.py must stay stdlib-only: its calibration "
        "reference is an enumeration string, never an import")

    # The named officer doorways carry no reference (explicit belt).
    for officer_surface in ("cabinet/scripts/evidence-read.sh",
                            "framework/events/emitter.py"):
        text = (ROOT / officer_surface).read_text(encoding="utf-8")
        assert "evidence_calibration" not in text
        assert "evidence-calibration" not in text

    # EVAL-025 hygiene: the module never references the golden-eval scalar
    # series (tokens built by concatenation so THIS file stays clean too).
    src = MODULE_PATH.read_text(encoding="utf-8")
    for token in ("golden-eval-" + "scalar", "golden_" + "scalar"):
        assert token not in src

    # Outputs live outside the store and outside officer feed surfaces.
    assert ec.OUT_DIR_REL == "cabinet/logs"
    assert not ec.STATUS_BASENAME.startswith(("consequence-events", "events-"))
    # No power-granting API exists (shadow: the judge tower's may_* verb
    # has deliberately NO per-stratum analog here).
    exported = [name for name in dir(ec) if "may_" in name or "allow" in name]
    assert exported == [], exported


def test_unclear_label_never_scores(tmp_path):
    """The unscoreable rule end-to-end: a lone unclear label yields zero
    pairs even when flagged, and the stratum stays uncalibrated."""
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)
    _seed_trial(rec, "evt-tb-unclear-only-1")
    _label(store, rec, journal, "evt-tb-unclear-only-1", "unclear")
    _flag(flags, "evt-tb-unclear-only-1")
    status = ec.measure(store_root=store, labels_journal=journal,
                        flags_paths=[flags], now=_NOW)
    assert status["totals"]["candidate_pairs"] == 0
    assert status["totals"]["labels"]["unscoreable"] == 1
    only = next(iter(status["strata"].values()))
    assert only["state"] == ec.STATE_UNCALIBRATED


def test_per_run_findings_dialect_and_ts_inheritance(tmp_path):
    """G1 join-contract dialect 2: a per-run summary row (one JSONL line per
    detector run, falsifier-series precedent) contributes each item of its
    `findings` list as a machine row, inheriting the run row's ts when the
    finding carries none. The inherited ts participates in latest-per-side
    supersession."""
    flags = tmp_path / "flags.jsonl"
    flags.write_text(json.dumps({
        "schema": "cabinet.testburg-detector-run/v1",
        "ts": "2026-07-17T11:30:00.000000Z",
        "findings": [
            {"trial_id": "evt-tb-nested-1", "failure_class": "nested-fail",
             "component": "testburg-exec"},
            {"trial_id": "evt-tb-nested-2", "failure_class": "nested-fail",
             "component": "testburg-exec", "verdict": "pass",
             "ts": "2026-07-17T11:31:00.000000Z"},
            {"failure_class": "no-trial"},          # unjoinable, counted
            "not-a-dict",                            # ignored silently
        ],
    }, sort_keys=True) + "\n")
    # An OLDER flat flag on nested-1 must lose to the nested (inherited-ts)
    # row above.
    _flag(flags, "evt-tb-nested-1", failure_class="stale-fail",
          ts="2026-07-17T09:00:00.000000Z")

    rows, counts = ec.read_detector_flags([flags])
    assert counts == {"rows": 4, "unjoinable": 1, "unscoreable": 0}
    by_trial = {}
    for row in sorted(rows, key=lambda r: r["ts"]):
        by_trial[row["trial_id"]] = row
    assert by_trial["evt-tb-nested-1"]["failure_class"] == "nested-fail"
    assert by_trial["evt-tb-nested-1"]["ts"] == "2026-07-17T11:30:00.000000Z"
    assert by_trial["evt-tb-nested-1"]["verdict"] == "flag"   # no verdict ⇒ flag
    assert by_trial["evt-tb-nested-2"]["verdict"] == "pass"
    assert by_trial["evt-tb-nested-2"]["ts"] == "2026-07-17T11:31:00.000000Z"


def test_axis_strings_are_data_not_markup(tmp_path):
    """Evidence-derived axis strings are UNTRUSTED data: control chars and
    newlines are stripped before they become stratum keys or Captain-report
    lines, and overlong values are capped — a hostile component name cannot
    inject report lines or split a stratum key."""
    flags = tmp_path / "flags.jsonl"
    _flag(flags, "evt-tb-inject-1",
          component="bad\nname\r# fake heading",
          failure_class="x" * 500)
    rows, _ = ec.read_detector_flags([flags])
    assert len(rows) == 1
    assert "\n" not in rows[0]["component"]
    assert "\r" not in rows[0]["component"]
    assert rows[0]["component"] == "bad name # fake heading"
    assert len(rows[0]["failure_class"]) <= ec._AXIS_MAX_LEN + 1

    status = ec.measure(labels_journal=None, flags_paths=[flags], now=_NOW)
    for key in status["strata"]:
        assert "\n" not in key and "\r" not in key
    report = ec.render_report(status)
    assert "# fake heading" not in report.splitlines()  # never a line of its own


def test_symlinked_journal_is_a_measurement_error(tmp_path):
    """A symlinked ground-truth journal is refused loud (never a silent
    zero-label measurement) — and refusal writes nothing."""
    real = tmp_path / "real.jsonl"
    real.write_text("")
    link = tmp_path / "labels.jsonl"
    link.symlink_to(real)
    with pytest.raises(ec.CalibrationError):
        ec.read_label_digests(link)
