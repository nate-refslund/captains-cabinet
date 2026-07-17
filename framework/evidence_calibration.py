"""Phase-4 SHADOW per-stratum calibration: detector flags vs Captain labels.

WHAT (whole-cabinet evidence design 2026-07-16 §3 Phase 4; R-8/R-11): pair
the machine leg (shadow evidence-detector FLAG rows, kept OUTSIDE the store)
with the Captain leg (governance-review label digests, the Phase-3 ground
truth) per stratum — stratum = the detector's own cluster key, component ×
failure-class — and publish per-stratum agreement STATE:

    uncalibrated          pairs < MIN_PAIRS (the measurement is not evidence)
    calibrated-below-bar  pairs >= MIN_PAIRS, agreement below the hard bar
    calibrated-at-bar     pairs >= MIN_PAIRS, agreement at/above the hard bar

SHADOW LAW (binding in this batch): NO stratum grants ANY power regardless
of state. This module exposes no power-granting API at all — deliberately no
per-stratum analog of judge_verdicts_may_demote(); the status file is
calibration DATA only, the INPUT to a later Captain-only Phase-5 admission
decision. Nothing downstream may consume these outputs to gate, block,
score, or act. Zero callers is the designed state (pinned by
framework/tests/test_evidence_calibration.py's repo grep).

CONSTANTS BY REFERENCE (R-11 — never a second number, never a flag): the
agreement hard bar (the >=80% code constant JUDGE_HARD_BAR), MIN_PAIRS, and
the proof-freshness window STATUS_MAX_AGE_DAYS are IMPORTED from
framework.fidelity.judge_calibration and applied PER STRATUM. There are no
--bar/--min-pairs CLI knobs: a bar loosenable from argv is not a bar. The
agreement math itself is judge_calibration.compute_agreement, called once
per stratum bucket; pairing semantics mirror collect_pairs (latest scoreable
verdict per side wins; the window filters on the HUMAN label ts; 'unclear'
scores neither side; polarity flag<->wrong / pass<->confirmed).

B1 RE-COUNT DISCIPLINE: every counted pair is re-verified against the
evidence store through the public germline APIs only (verifier.verify_trial
green + the journal digest's event_hashes present among the trial's events
via EvidenceRecorder.read_events). Pairs that cannot be re-counted are
EXCLUDED and tallied honestly, never counted. The verifier's signed
anti-rollback watermark advancing on a trial's first clean verify is the one
sanctioned read side effect (identical to `python3.12 -m framework.evidence
verify`); no other store byte may change, and no output of this module ever
lives inside the store.

HONEST CLAIM (mandatory wording): Captain labels are token-gated but
tamper-EVIDENT only, not tamper-proof, until HP-3 lands — in a same-UID
deployment a process that can read the store signing key can forge the
label channel; the per-pair re-count against journal digests plus the daily
external anchor is the designed precursor, necessary but not sufficient.
Uncalibrated strata are the EXPECTED launch state while label volume is
thin (the per-session label cap is a code constant); pooling strata or
lowering floors are the named wrong moves — the correct reading of a thin
stratum is "no power there" (and in this batch, no power anywhere).

SURFACES (Captain-facing ONLY — never-a-score): the status file lives at
$CABINET_EVENT_LOG_DIR/evidence-calibration-status.json (the consequence
ledger's ONE env rule, outside repo and store; the repo-root pytest fence
covers it automatically); the human report and the run series live under
cabinet/logs/ (gitignored runtime dir). Per-stratum agreement rates are
evidence-derived aggregates: they must never appear in org events officers
read, the officer evidence projection, the attention feed, or any
shared/interfaces feed surface. The module name keeps the officer-hook
substring screen ('framework.evidence') so officer sessions cannot invoke
it — shadow reports are Captain-facing by construction.

CLI (Captain/launchd contexts only — the officer hook layer's substring
screen on 'framework.evidence' blocks officer sessions from this module by
name, by design):

    python3.12 -m framework.evidence_calibration          # from repo root

Exit codes (main): 0 measured (status written — including the honest
all-uncalibrated launch state); 1 status written but a Captain render
degraded (LOUD); 2 measurement error — NOTHING written, the previous proof
ages out (a fabricated proof is worse than an aging one). A later
services.yml row (judge-calibration daily-cadence template, shipped
`disabled: true` staged-dark per the evidence-anchor precedent) plus a thin
cabinet/scripts path-exec wrapper are the scheduling seam — deliberately
not in this module's batch.

This module is intentionally NOT part of the germline framework/evidence
package (evidence_anchor/evidence_mirror sibling precedent): it is an
external, read-only observer of the store and of Captain-owned journals.
Syntax stays 3.9-clean and the evidence plane is lazy-imported, but the
supported interpreter is python3.12 (the recorder requires 3.11+).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# Constants + math BY REFERENCE (R-11). Private-helper reuse (_atomic_write,
# _parse_ts, _SCOREABLE) is deliberate, same-repo, same posture as
# judge_calibration's own reuse of consequence privates: duplicating any of
# them would mint a second rule that can drift.
from framework import evidence_freeze  # §2.4 judging-freeze respect (stdlib-only)
from framework.fidelity.consequence import _consequence_log_dir
from framework.fidelity.judge_calibration import (
    JUDGE_HARD_BAR,
    MIN_PAIRS,
    STATUS_MAX_AGE_DAYS,
    _SCOREABLE,
    _atomic_write,
    _parse_ts,
    compute_agreement,
)

# --- constants (identifiers and vocabulary — the NUMBERS live upstream) ------

STATUS_SCHEMA = "cabinet.evidence-calibration-status/v1"
STATUS_FORMAT = 1
STATUS_BASENAME = "evidence-calibration-status.json"

SERIES_SCHEMA = "cabinet.evidence-calibration-series/v1"
SERIES_BASENAME = "evidence-calibration.jsonl"
REPORT_BASENAME = "evidence-calibration-report.md"
OUT_DIR_REL = "cabinet/logs"  # gitignored runtime dir; Captain-facing home

# Read-only source literals. Framework cannot import the dash-named Captain
# CLI (cabinet/scripts/governance-review.py), so the journal literal is
# repeated here and PINNED equal to gr.LABELS_JOURNAL_REL by
# test_evidence_calibration (evidence-anchor.py DEFAULT_LABEL_FILES repeats
# it the same way).
LABELS_JOURNAL_REL = "shared/interfaces/governance-labels.jsonl"
LABEL_DIGEST_SCHEMA = "cabinet.governance-label-digest/v1"
# The Phase-4 detector findings journal (G1 coordination point — the map's
# chosen name). Detector rows are weak signals; here they are only ever the
# MACHINE LEG of a calibration pair, never ground truth (B9).
FLAGS_JOURNAL_REL = "shared/interfaces/evidence-shadow-findings.jsonl"

STATE_UNCALIBRATED = "uncalibrated"
STATE_BELOW_BAR = "calibrated-below-bar"
STATE_AT_BAR = "calibrated-at-bar"

# Machine-verdict normalization (tolerant across detector row dialects).
# A finding row with NO verdict field IS a flag; a present-but-unknown token
# scores neither side (fail-closed attribution, mirroring collect_pairs'
# treatment of source None/system).
# G1 triage vocabulary (evidence_detectors' discriminator verdicts, the
# actual journal dialect — seam-reconciled at Phase-4 integration):
# "inconclusive" = the cluster finding passed through triage un-explained,
# so the machine leg's position is FLAG; "noise" = triage affirmatively
# explained the cluster away (recorded degradation attribution), so the
# machine's final position is PASS — it would not raise the trial. Both are
# still reported by G1 (shadow); here they are polarity inputs only.
_FLAG_TOKENS = frozenset({
    "flag", "flagged", "fail", "failed", "anomaly", "finding",
    "would_withhold", "wrong", "inconclusive",
})
_PASS_TOKENS = frozenset({
    "pass", "passed", "ok", "clean", "grounded", "confirmed", "noise",
})
# Polarity (reused from the judge-calibration tower, restated once): a
# detector FLAG asserts the trial's claim is wrong; an explicit PASS asserts
# it held. Absence of a flag row is NEVER a pass (absence != health).
_MACHINE_TO_VERDICT = {"flag": "wrong", "pass": "confirmed"}

_UNSPECIFIED = "(unspecified)"

SHADOW_NOTE = (
    "Phase 4 SHADOW: NO stratum grants power regardless of its state. "
    "This file is calibration DATA only — the input to a later Captain-only "
    "Phase-5 admission decision. Nothing may consume it to gate, block, "
    "score, or act."
)
HONESTY_NOTE = (
    "Captain labels are token-gated but tamper-EVIDENT only (not "
    "tamper-proof) until HP-3; every counted pair is re-verified against "
    "the evidence store (verify green + digest event hashes present) and "
    "label digests ride the daily external anchor. Uncalibrated strata are "
    "the expected launch state while label volume is thin — the correct "
    "reading is 'no power there', never a pooled or lowered floor."
)
LAUNCH_NOTE = (
    "LAUNCH STATE: no scoreable Captain labels yet — every stratum is "
    "uncalibrated. Nothing is wrong; the first weekly governance review "
    "starts filling this."
)
NO_OVERLAP_NOTE = (
    "Captain labels exist but no detector flag names a labeled trial yet — "
    "0 pairs; every stratum stays uncalibrated until the legs overlap."
)


class CalibrationError(Exception):
    """A measurement error: the run must write NOTHING (the previous status
    ages out via STATUS_MAX_AGE_DAYS rather than being papered over)."""


def status_path() -> Path:
    """Status-file path under the consequence ledger's ONE env rule
    (CABINET_EVENT_LOG_DIR, else the durable per-user default). Distinct
    basename, outside the ledger glob families and outside repo + store."""
    return _consequence_log_dir() / STATUS_BASENAME


def _now_iso(now: Optional[datetime] = None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _evidence_plane():
    """Lazy germline imports (public APIs only). Module import stays cheap
    and 3.9-safe; the store is only touched where a pair must be re-counted."""
    from framework.evidence.recorder import EvidenceError, EvidenceRecorder
    from framework.evidence.verifier import TRIAL_ID_RE, verify_trial
    return EvidenceError, EvidenceRecorder, TRIAL_ID_RE, verify_trial


# ---------------------------------------------------------------------------
# input readers (read-only; loud on suspicious inputs, honest on absence)
# ---------------------------------------------------------------------------

def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    """Rows of a Captain-owned JSONL journal. Missing file -> [] (honest
    absence). A path that EXISTS but is a symlink, a non-file, or unreadable
    -> CalibrationError: silently measuring 0 labels over a broken ground-
    truth source would write a fresh all-uncalibrated proof that masks data
    loss (never-write-on-error discipline)."""
    if path.is_symlink():
        raise CalibrationError(f"journal is a symlink (refused): {path}")
    if not path.exists():
        return []
    if not path.is_file():
        raise CalibrationError(f"journal is not a regular file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CalibrationError(f"journal unreadable: {path} ({exc})") from exc
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue  # junk line: skipped, never executed, never fatal
        if isinstance(row, dict):
            rows.append(row)
    return rows


def read_label_digests(journal: Path) -> list[dict[str, Any]]:
    """Normalized Captain-label rows from the governance-labels journal:
    {trial_id, ts, verdict, basis, event_ids, event_hashes}. Only
    label-digest rows count (the journal also carries session markers)."""
    out: list[dict[str, Any]] = []
    for row in _read_jsonl_rows(journal):
        if row.get("schema") != LABEL_DIGEST_SCHEMA:
            continue
        trial_id = row.get("trial_id")
        verdict = row.get("verdict")
        if not isinstance(trial_id, str) or not isinstance(verdict, str):
            continue
        out.append({
            "trial_id": trial_id,
            "ts": str(row.get("ts") or ""),
            "verdict": verdict,
            "basis": str(row.get("basis") or ""),
            "event_ids": [e for e in (row.get("event_ids") or [])
                          if isinstance(e, str)],
            "event_hashes": [h for h in (row.get("event_hashes") or [])
                             if isinstance(h, str)],
        })
    return out


_AXIS_MAX_LEN = 120


def _clean_axis(value: Any) -> str:
    """Axis strings originate in evidence-derived detector rows — UNTRUSTED
    data, never markup. Strip control chars (newlines included), collapse
    whitespace, cap length, so a hostile component name cannot inject lines
    into the Captain report or split a stratum key."""
    text = " ".join(str(value).split())
    text = "".join(ch for ch in text if ch.isprintable())
    if len(text) > _AXIS_MAX_LEN:
        text = text[:_AXIS_MAX_LEN] + "…"
    return text or _UNSPECIFIED


def _machine_axes(row: dict[str, Any]) -> tuple[str, str]:
    component = row.get("component")
    if isinstance(component, dict):
        component = component.get("name")
    component = _clean_axis(component) if component else _UNSPECIFIED
    failure_class: Optional[str] = None
    for key in ("failure_class", "failure_type", "result_code", "status"):
        value = row.get(key)
        if value:
            failure_class = _clean_axis(value)
            break
    return component, failure_class or _UNSPECIFIED


def _machine_verdict(row: dict[str, Any]) -> Optional[str]:
    raw = row.get("verdict", row.get("machine_verdict"))
    if raw is None:
        return "flag"  # a finding row IS a flag
    token = str(raw).strip().lower()
    if token in _FLAG_TOKENS:
        return "flag"
    if token in _PASS_TOKENS:
        return "pass"
    return None  # unknown vocabulary: scores neither side (fail-closed)


def read_detector_flags(paths: Iterable[Path]) -> tuple[
        list[dict[str, Any]], dict[str, int]]:
    """Normalized machine-leg rows from detector findings journals, plus
    honest skip counts. Join contract (G1 coordination), two dialects:
      * flat rows — joinable iff the row names `trial_id` (str), `trial_ids`
        (list of str), or `trials` (G1's actual cluster-finding key: the
        ≤5-sample trial-id list detect_evidence_patterns emits — the sample
        cap bounds the join surface honestly; un-sampled trials of a large
        cluster simply never pair);
      * per-run summary rows (the falsifier-series one-line-per-run
        precedent) — a row carrying `findings: [...]` contributes each dict
        item as its own machine row, inheriting the parent row's ts when the
        finding has none.
    Optional per-row fields: `ts`, `verdict`, `component` (str or {name}),
    `failure_class` (falling back to failure_type/result_code/status). Rows
    without a trial id are an honest gap (pre-evidence findings) — skipped
    and counted, never guessed."""
    rows: list[dict[str, Any]] = []
    counts = {"rows": 0, "unjoinable": 0, "unscoreable": 0}

    def _one(row: dict[str, Any], inherited_ts: str) -> None:
        counts["rows"] += 1
        trial_ids = row.get("trial_ids")
        if not isinstance(trial_ids, list):
            trial_ids = row.get("trials")  # G1 finding dialect (sample ids)
        if not isinstance(trial_ids, list):
            trial_ids = [row.get("trial_id")]
        trial_ids = [t for t in trial_ids if isinstance(t, str) and t]
        if not trial_ids:
            counts["unjoinable"] += 1
            return
        verdict = _machine_verdict(row)
        if verdict is None:
            counts["unscoreable"] += 1
            return
        component, failure_class = _machine_axes(row)
        ts = str(row.get("ts") or row.get("detected_at") or inherited_ts)
        for trial_id in trial_ids:
            rows.append({
                "trial_id": trial_id,
                "ts": ts,
                "verdict": verdict,
                "component": component,
                "failure_class": failure_class,
            })

    for path in paths:
        for row in _read_jsonl_rows(Path(path)):
            findings = row.get("findings")
            if isinstance(findings, list):
                run_ts = str(row.get("ts") or row.get("detected_at") or "")
                for finding in findings:
                    if isinstance(finding, dict):
                        _one(finding, run_ts)
                continue
            _one(row, "")
    return rows, counts


# ---------------------------------------------------------------------------
# pairing (collect_pairs semantics, subject := trial_id)
# ---------------------------------------------------------------------------

def _stratum_key(component: str, failure_class: str) -> str:
    def _clean(value: str) -> str:
        return value.replace("|", "/").replace("=", ":")
    return "component=%s|failure_class=%s" % (
        _clean(component), _clean(failure_class))


def collect_stratum_pairs(
    labels: list[dict[str, Any]],
    flags: list[dict[str, Any]],
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Candidate pairs + totals. Mirrors judge_calibration.collect_pairs:
    ts-sorted stable so the latest verdict per side wins; only scoreable
    label verdicts (confirmed|wrong) enter — 'unclear' neither scores nor
    supersedes; the since/until window filters on the HUMAN ts only (ISO
    strings compare lexicographically). The stratum comes from the MACHINE
    row (the detector's cluster key); the label's basis is recorded per pair
    as data, not as a stratum."""
    humans: dict[str, dict[str, Any]] = {}
    label_counts = {"rows": len(labels), "scoreable": 0, "unscoreable": 0,
                    "windowed_out": 0}
    for row in sorted(labels, key=lambda r: r.get("ts", "")):
        if row["verdict"] not in _SCOREABLE:
            label_counts["unscoreable"] += 1
            continue
        ts = row.get("ts", "")
        if since is not None and ts < since:
            label_counts["windowed_out"] += 1
            continue
        if until is not None and ts >= until:
            label_counts["windowed_out"] += 1
            continue
        label_counts["scoreable"] += 1
        humans[row["trial_id"]] = row  # ts-sorted: last scoreable wins

    machines: dict[str, dict[str, Any]] = {}
    for row in sorted(flags, key=lambda r: r.get("ts", "")):
        machines[row["trial_id"]] = row  # latest machine row wins

    pairs: list[dict[str, Any]] = []
    for trial_id in sorted(set(humans) & set(machines)):
        human = humans[trial_id]
        machine = machines[trial_id]
        judge_verdict = _MACHINE_TO_VERDICT[machine["verdict"]]
        pairs.append({
            "subject": trial_id,
            "human": human["verdict"],
            "judge": judge_verdict,
            "human_ts": human.get("ts", ""),
            "judge_ts": machine.get("ts", ""),
            "agree": human["verdict"] == judge_verdict,
            "stratum": _stratum_key(machine["component"],
                                    machine["failure_class"]),
            "axes": {"component": machine["component"],
                     "failure_class": machine["failure_class"]},
            "basis": human.get("basis", ""),
            "event_ids": human.get("event_ids", []),
            "event_hashes": human.get("event_hashes", []),
        })

    # Axes index over ALL normalized machine rows (not just the latest-per-
    # trial winners): every stratum a detector ever named stays visible as
    # an honest n=0 row even when its rows were superseded or excluded.
    stratum_axes: dict[str, dict[str, str]] = {}
    for machine in flags:
        key = _stratum_key(machine["component"], machine["failure_class"])
        stratum_axes.setdefault(key, {
            "component": machine["component"],
            "failure_class": machine["failure_class"],
        })
    totals = {
        "labels": label_counts,
        "candidate_pairs": len(pairs),
        "stratum_axes": stratum_axes,
    }
    return pairs, totals


# ---------------------------------------------------------------------------
# B1 re-count: verify every candidate pair against the store
# ---------------------------------------------------------------------------

def verify_pairs(
    store_root: Optional[Path],
    pairs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """(counted_pairs, excluded_counts). A pair counts ONLY when its trial
    verifies green (public verifier) AND every event hash in its journal
    digest is present among the trial's events (read via the public
    recorder API — the read advances the first-verify watermark, the one
    sanctioned side effect). Everything else is excluded and tallied:
    store_unavailable / unverified / purged / digest_hashes_missing.
    The store is never written and never healed: absent/symlinked store
    roots are not touched at all."""
    excluded = {"store_unavailable": 0, "unverified": 0, "purged": 0,
                "digest_hashes_missing": 0}
    if not pairs:
        return [], excluded
    if store_root is None:
        excluded["store_unavailable"] = len(pairs)
        return [], excluded
    store_root = Path(store_root)
    if store_root.is_symlink() or not (store_root / "trials").is_dir():
        excluded["store_unavailable"] = len(pairs)
        return [], excluded

    EvidenceError, EvidenceRecorder, TRIAL_ID_RE, verify_trial = (
        _evidence_plane())
    recorder = EvidenceRecorder(store_root)
    hashes_by_trial: dict[str, Optional[set]] = {}
    purged_trials: set = set()
    for trial_id in sorted({p["subject"] for p in pairs}):
        if not TRIAL_ID_RE.fullmatch(trial_id):
            hashes_by_trial[trial_id] = None
            continue
        result = verify_trial(store_root, trial_id)
        if not result.get("ok"):
            hashes_by_trial[trial_id] = None
            continue
        try:
            events = recorder.read_events(trial_id)
        except EvidenceError as exc:
            if getattr(exc, "code", "") == "trial_purged":
                purged_trials.add(trial_id)
            hashes_by_trial[trial_id] = None
            continue
        hashes_by_trial[trial_id] = {
            e.get("event_hash") for e in events
            if isinstance(e, dict) and e.get("event_hash")}

    counted: list[dict[str, Any]] = []
    for pair in pairs:
        trial_hashes = hashes_by_trial.get(pair["subject"])
        if trial_hashes is None:
            key = ("purged" if pair["subject"] in purged_trials
                   else "unverified")
            excluded[key] += 1
            continue
        digest_hashes = pair.get("event_hashes") or []
        if not digest_hashes or not set(digest_hashes) <= trial_hashes:
            excluded["digest_hashes_missing"] += 1
            continue
        counted.append(pair)
    return counted, excluded


# ---------------------------------------------------------------------------
# per-stratum agreement + state
# ---------------------------------------------------------------------------

def stratum_state(agreement: dict[str, Any]) -> str:
    """Three-way state from an agreement block, RE-DERIVED from the numbers
    (never trusted from a stored flag — judge_calibration's belt-and-braces).
    In Phase 4 the state grants nothing regardless of its value."""
    n = agreement.get("pairs")
    if not isinstance(n, int) or isinstance(n, bool) or n < MIN_PAIRS:
        return STATE_UNCALIBRATED
    rate = agreement.get("agreement_rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        return STATE_UNCALIBRATED
    if float(rate) >= JUDGE_HARD_BAR:
        return STATE_AT_BAR
    return STATE_BELOW_BAR


def measure(
    repo_root: Optional[Path] = None,
    store_root: Optional[Path] = None,
    labels_journal: Optional[Path] = None,
    flags_paths: Optional[list[Path]] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """One full shadow measurement -> the status body (nothing written).
    With repo_root given, defaults resolve to the house locations: the
    governance-labels journal, the detector findings journal, and the store
    at journey.EVIDENCE_REL (the ONE canonical store-path constant)."""
    if repo_root is not None:
        repo_root = Path(repo_root)
        if labels_journal is None:
            labels_journal = repo_root / LABELS_JOURNAL_REL
        if flags_paths is None:
            flags_paths = [repo_root / FLAGS_JOURNAL_REL]
        if store_root is None:
            from framework.onboarding.journey import EVIDENCE_REL
            store_root = repo_root / EVIDENCE_REL

    labels = (read_label_digests(Path(labels_journal))
              if labels_journal is not None else [])
    flags, flag_counts = read_detector_flags(
        [Path(p) for p in (flags_paths or [])])
    pairs, totals = collect_stratum_pairs(labels, flags,
                                          since=since, until=until)
    counted, excluded = verify_pairs(
        Path(store_root) if store_root is not None else None, pairs)

    by_stratum: dict[str, list[dict[str, Any]]] = {}
    for pair in counted:
        by_stratum.setdefault(pair["stratum"], []).append(pair)
    # Every stratum any machine leg has ever named appears — a stratum with
    # zero counted pairs renders as an honest uncalibrated n=0 row, so the
    # launch surface (and any all-excluded stratum) stays visible.
    stratum_axes = totals.pop("stratum_axes")
    all_strata = sorted(set(by_stratum) | set(stratum_axes)
                        | {p["stratum"] for p in pairs})
    strata: dict[str, dict[str, Any]] = {}
    for key in all_strata:
        stratum_pairs = by_stratum.get(key, [])
        agreement = compute_agreement(stratum_pairs)
        basis_counts: dict[str, int] = {}
        for pair in stratum_pairs:
            basis = pair.get("basis") or _UNSPECIFIED
            basis_counts[basis] = basis_counts.get(basis, 0) + 1
        strata[key] = {
            "axes": stratum_axes.get(
                key, stratum_pairs[0]["axes"] if stratum_pairs else {}),
            "state": stratum_state(agreement),
            "agreement": agreement,
            "recorded": {"basis": basis_counts},
        }

    labels_scoreable = totals["labels"]["scoreable"]
    if labels_scoreable == 0:
        coverage_note = LAUNCH_NOTE
    elif not counted:
        coverage_note = NO_OVERLAP_NOTE
    else:
        coverage_note = ("%d counted pair(s) across %d stratum/strata."
                         % (len(counted), len(strata)))

    return {
        "schema": STATUS_SCHEMA,
        "format": STATUS_FORMAT,
        "computed_at": _now_iso(now),
        "since": since,
        "until": until,
        "hard_bar": JUDGE_HARD_BAR,
        "min_pairs": MIN_PAIRS,
        "max_age_days": STATUS_MAX_AGE_DAYS,
        "shadow": True,
        "power": "none",
        "shadow_note": SHADOW_NOTE,
        "honesty_note": HONESTY_NOTE,
        "coverage_note": coverage_note,
        "sources": {
            "labels_journal": (str(labels_journal)
                               if labels_journal is not None else None),
            "flags": [str(p) for p in (flags_paths or [])],
            "store_root": (str(store_root)
                           if store_root is not None else None),
        },
        "totals": {
            "labels": totals["labels"],
            "flags": flag_counts,
            "candidate_pairs": totals["candidate_pairs"],
            "counted_pairs": len(counted),
            "excluded": excluded,
        },
        "strata": strata,
    }


# ---------------------------------------------------------------------------
# status file (judge-calibration discipline: atomic; write every successful
# measurement incl. all-uncalibrated; never write on error; readers refuse
# stale/future proofs and re-derive states from the stored numbers)
# ---------------------------------------------------------------------------

def write_status(status: dict[str, Any],
                 path: Optional[Path] = None) -> Path:
    target = Path(path) if path is not None else status_path()
    _atomic_write(target, json.dumps(status, sort_keys=True, indent=2) + "\n")
    return target


def read_status(
    path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """{"usable": bool, "reason": str, "status": body|None,
    "states": {stratum: state}|None}. `usable` means fresh-and-well-formed
    FOR REPORTING ONLY — it grants nothing (shadow law; there is no
    'allowed' here by design). States are re-derived from the stored
    agreement numbers, never read back from the file. Never raises."""
    if now is None:
        now = datetime.now(timezone.utc)
    target = Path(path) if path is not None else status_path()
    try:
        body = json.loads(target.read_text())
    except (OSError, ValueError):
        return {"usable": False,
                "reason": f"no readable calibration status at {target}",
                "status": None, "states": None}
    if (not isinstance(body, dict) or body.get("format") != STATUS_FORMAT
            or body.get("schema") != STATUS_SCHEMA):
        return {"usable": False, "reason": "unknown status format",
                "status": None, "states": None}
    computed_at = _parse_ts(body.get("computed_at"))
    if computed_at is None:
        return {"usable": False, "reason": "unparseable computed_at",
                "status": body, "states": None}
    age_days = (now - computed_at).total_seconds() / 86400.0
    if age_days < 0:
        return {"usable": False, "reason": "computed_at is in the future",
                "status": body, "states": None}
    if age_days > STATUS_MAX_AGE_DAYS:
        return {"usable": False,
                "reason": ("status stale (%.1fd > %.1fd)"
                           % (age_days, STATUS_MAX_AGE_DAYS)),
                "status": body, "states": None}
    strata = body.get("strata")
    if not isinstance(strata, dict):
        return {"usable": False, "reason": "malformed strata",
                "status": body, "states": None}
    states: dict[str, str] = {}
    for key, block in sorted(strata.items()):
        agreement = (block.get("agreement")
                     if isinstance(block, dict) else None)
        states[key] = stratum_state(agreement
                                    if isinstance(agreement, dict) else {})
    return {"usable": True,
            "reason": "fresh status (%.1fd old) — reporting only, no power"
                      % age_days,
            "status": body, "states": states}


# ---------------------------------------------------------------------------
# renders (Captain-facing)
# ---------------------------------------------------------------------------

def _pct(rate: Any) -> str:
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        return "n/a"
    return "%d%%" % int(round(float(rate) * 100))


def render_weekly_line(status: dict[str, Any]) -> str:
    """The one weekly-review line ('calibration: stratum X n=.. agreement=..%
    — shadow'). Wire-ready for the governance-review station tail; deliberately
    NOT wired there in this batch (shared surface, later 3-line diff)."""
    strata = status.get("strata") or {}
    suffix = " — shadow (no stratum grants power)"
    labels_scoreable = (((status.get("totals") or {}).get("labels") or {})
                        .get("scoreable", 0))
    if not strata:
        if not labels_scoreable:
            return ("calibration: no Captain labels yet — all strata "
                    "uncalibrated" + suffix)
        return "calibration: no detector/label overlap yet — 0 pairs" + suffix
    counts = {STATE_AT_BAR: 0, STATE_BELOW_BAR: 0, STATE_UNCALIBRATED: 0}
    for block in strata.values():
        counts[stratum_state(block.get("agreement") or {})] += 1

    def _pairs_of(item: tuple) -> int:
        agreement = item[1].get("agreement") or {}
        n = agreement.get("pairs")
        return n if isinstance(n, int) and not isinstance(n, bool) else 0

    top_key, top_block = max(sorted(strata.items()), key=_pairs_of)
    top_agreement = top_block.get("agreement") or {}
    detail = "stratum %s n=%d agreement=%s" % (
        top_key, _pairs_of((top_key, top_block)),
        _pct(top_agreement.get("agreement_rate")))
    if len(strata) == 1:
        return "calibration: " + detail + suffix
    return ("calibration: %d strata (%d at-bar, %d below-bar, "
            "%d uncalibrated); top %s%s"
            % (len(strata), counts[STATE_AT_BAR], counts[STATE_BELOW_BAR],
               counts[STATE_UNCALIBRATED], detail, suffix))


def render_report(status: dict[str, Any]) -> str:
    """Small Captain report (markdown). Counts and per-stratum agreement —
    Captain-facing only; never projected to officers."""
    totals = status.get("totals") or {}
    labels = totals.get("labels") or {}
    flags = totals.get("flags") or {}
    excluded = totals.get("excluded") or {}
    lines = [
        "# Evidence calibration — per-stratum (Phase 4 SHADOW)",
        "",
        "computed_at: %s   window: %s .. %s" % (
            status.get("computed_at"), status.get("since") or "-",
            status.get("until") or "-"),
        "hard bar: >=%s agreement over >=%s pairs per stratum "
        "(constants imported from judge_calibration — R-11)" % (
            status.get("hard_bar"), status.get("min_pairs")),
        "",
        "> %s" % status.get("shadow_note", SHADOW_NOTE),
        "",
        "## Totals",
        "",
        "- Captain label rows: %s (scoreable %s, unclear/unscoreable %s, "
        "outside window %s)" % (
            labels.get("rows", 0), labels.get("scoreable", 0),
            labels.get("unscoreable", 0), labels.get("windowed_out", 0)),
        "- detector flag rows: %s (unjoinable %s, unknown-verdict %s)" % (
            flags.get("rows", 0), flags.get("unjoinable", 0),
            flags.get("unscoreable", 0)),
        "- pairs: %s candidate -> %s counted (excluded: store_unavailable "
        "%s, unverified %s, purged %s, digest_hashes_missing %s)" % (
            totals.get("candidate_pairs", 0), totals.get("counted_pairs", 0),
            excluded.get("store_unavailable", 0),
            excluded.get("unverified", 0), excluded.get("purged", 0),
            excluded.get("digest_hashes_missing", 0)),
        "",
        "%s" % status.get("coverage_note", ""),
        "",
        "## Strata (component × failure-class)",
        "",
    ]
    strata = status.get("strata") or {}
    if not strata:
        lines.append("_(no strata observed yet — no detector flags and no "
                     "pairs)_")
    for key, block in sorted(strata.items()):
        agreement = block.get("agreement") or {}
        confusion = agreement.get("confusion") or {}
        lines.append(
            "- `%s` — **%s** · pairs=%s agreement=%s · confusion "
            "hc_jc=%s hc_jw=%s hw_jc=%s hw_jw=%s · basis mix: %s" % (
                key, stratum_state(agreement), agreement.get("pairs", 0),
                _pct(agreement.get("agreement_rate")),
                confusion.get("hc_jc", 0), confusion.get("hc_jw", 0),
                confusion.get("hw_jc", 0), confusion.get("hw_jw", 0),
                json.dumps((block.get("recorded") or {}).get("basis") or {},
                           sort_keys=True)))
    lines += [
        "",
        "## Honest claim",
        "",
        "%s" % status.get("honesty_note", HONESTY_NOTE),
        "",
        "weekly line: %s" % render_weekly_line(status),
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# run + CLI (path knobs only — the numbers are code constants upstream)
# ---------------------------------------------------------------------------

def _append_series_row(series: Path, row: dict[str, Any]) -> None:
    """O_APPEND + O_NOFOLLOW + 0600 (the governance-labels journal append
    pattern) — one row per run, outside the store, gitignored runtime dir."""
    series.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
    fd = os.open(series,
                 os.O_WRONLY | os.O_CREAT | os.O_APPEND
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def run(
    repo_root: Optional[Path] = None,
    store_root: Optional[Path] = None,
    labels_journal: Optional[Path] = None,
    flags_paths: Optional[list[Path]] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    status_target: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
    out=None,
) -> int:
    """Measure -> write status -> render Captain report + series row.
    Returns 0 measured, 1 status written but a Captain render degraded
    (LOUD, mirrors governance-review's export contract). Measurement errors
    propagate to main(), which writes nothing and exits 2."""
    def _say(text: str) -> None:
        print(text, file=out if out is not None else sys.stdout)

    if repo_root is not None:
        # §2.4 tamper response (evidence_freeze consumer contract): while
        # the judging-freeze marker is present, evidence-fed judging refuses
        # to run — one plain line, rc 0, zero reads, zero writes (the
        # previous status ages out honestly rather than being papered over).
        # FAIL-CLOSED: a broken freeze probe reads FROZEN. API calls with
        # repo_root=None (explicit scratch paths, unit tests of the math)
        # carry no marker location and skip the check; every scheduled/CLI
        # path sets repo_root.
        try:
            frozen = evidence_freeze.is_frozen(repo_root)
        except Exception:  # noqa: BLE001 — broken probe reads frozen
            frozen = True
        if frozen:
            _say("evidence-calibration: frozen — refusing to run (%s)"
                 % evidence_freeze.marker_path(repo_root))
            return 0

    status = measure(repo_root=repo_root, store_root=store_root,
                     labels_journal=labels_journal, flags_paths=flags_paths,
                     since=since, until=until, now=now)
    target = write_status(status, path=status_target)
    _say("status: %s" % target)

    rc = 0
    if out_dir is None and repo_root is not None:
        out_dir = Path(repo_root) / OUT_DIR_REL
    if out_dir is not None:
        try:
            out_dir = Path(out_dir)
            report_path = out_dir / REPORT_BASENAME
            _atomic_write(report_path, render_report(status))
            states = {key: stratum_state((block or {}).get("agreement") or {})
                      for key, block in (status.get("strata") or {}).items()}
            _append_series_row(out_dir / SERIES_BASENAME, {
                "schema": SERIES_SCHEMA,
                "ts": status["computed_at"],
                "weekly_line": render_weekly_line(status),
                "totals": status["totals"],
                "states": states,
                "status_path": str(target),
            })
            _say("report: %s" % report_path)
        except OSError as exc:
            rc = 1
            _say("WARN: Captain render degraded (%s) — the status file "
                 "itself is written." % exc)
    _say(render_weekly_line(status))
    return rc


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evidence_calibration",
        description=("Phase-4 SHADOW per-stratum calibration (detector "
                     "flags vs Captain labels). Reports only; grants "
                     "nothing. The hard bar and MIN_PAIRS are code "
                     "constants imported from judge_calibration — "
                     "deliberately not flags."))
    parser.add_argument("--repo-root", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--store", type=Path, default=None,
                        help="evidence store root override (scratch runs)")
    parser.add_argument("--labels-journal", type=Path, default=None)
    parser.add_argument("--flags", type=Path, action="append", default=None,
                        help="detector findings journal (repeatable)")
    parser.add_argument("--since", default=None,
                        help="ISO lower bound on the HUMAN label ts")
    parser.add_argument("--until", default=None,
                        help="ISO upper bound (exclusive) on the HUMAN ts")
    parser.add_argument("--status-path", type=Path, default=None,
                        help="status file override (default: "
                             "$CABINET_EVENT_LOG_DIR/" + STATUS_BASENAME + ")")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="report/series dir override (default: "
                             "<repo-root>/" + OUT_DIR_REL + ")")
    args = parser.parse_args(argv)
    try:
        return run(repo_root=args.repo_root, store_root=args.store,
                   labels_journal=args.labels_journal,
                   flags_paths=args.flags, since=args.since,
                   until=args.until, status_target=args.status_path,
                   out_dir=args.out_dir)
    except (CalibrationError, OSError) as exc:
        print("FATAL: measurement error — nothing written (%s)" % exc,
              file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover — thin CLI shell
    sys.exit(main())
