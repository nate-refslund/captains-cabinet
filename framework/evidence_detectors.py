"""framework.evidence_detectors — Phase-4 SHADOW detectors over the evidence plane.

Whole-cabinet evidence design 2026-07-16, §3 Phase 4 item 1 (detectors, all
read-only, existing shapes). Three jobs, one scheduled pass:

  1. Failure/anomaly CLUSTERING over the Phase-3 query plane — the
     eval-pattern-detector shape (read → cluster → flag, emits nothing),
     reused via its R-12 evidence-input seam
     (framework.measurement.eval_pattern_detector.detect_evidence_patterns).
  2. Recorded-failure TRIAGE — the signal-discriminator FAIL-OPEN pattern
     (framework/frontdoor/signal_discriminator.py, cloned shape, not
     imported — that module is Sentry-specific): a finding is classified
     NOISE only with AFFIRMATIVE evidence (a matching recorded degradation
     that positively attributes it); on ANY uncertainty it is INCONCLUSIVE
     and passes through to the report unchanged. Absence of an explanation
     is never an explanation.
  3. A Captain-facing REPORT — one JSON line per run appended to
     shared/interfaces/evidence-shadow-findings.jsonl, OUTSIDE the store.

SHADOW LAW (binding): detect, never act. Every output of this module is a
report. NOTHING downstream may consume these findings to gate, block,
score, or act — the enforce flip is a LATER Captain-only narrowing, not
this module. Findings are Captain-facing only: never projected through the
officer doorway, never emitted as org events officers read, never surfaced
to the attention feed. This module emits no org events, touches no Redis,
opens no network connection, and runs no subprocess.

WEAK-SIGNAL DOCTRINE (design B9): evidence-pattern matches are weak
signals. They may appear here as report findings; they are never watchdog
expectation ground truth and never all-clear evidence — the evidence-plane
watchdog expectations (framework/watchdog/registry.py) ground exclusively
in invariants (freshness/growth/chain-continuity facts).

HONEST CLAIM (mandatory wording, also stamped on every report row): the
evidence-plane integrity surface this reads detects retroactive
single-plane tamper and INCONSISTENT forgery only; consistent same-user
forgery of both planes stays open until HP-1 (OS-user/key isolation)
lands — necessary, not sufficient.

READ-ONLY toward the store: all reads ride the germline public APIs
(EvidenceRecorder + framework.evidence.query.selector_projection), which
are verification-gated and redacted; served text carries the UNTRUSTED
OBSERVATIONS banner and is treated strictly as data here. The one
sanctioned store byte-change on this path is the verifier's signed
anti-rollback watermark advancing on a trial's first clean verify — the
same side effect as the existing ``verify`` verb. Report files live
outside the store and are never written under instance/evidence/.

FREEZE RESPECT (§2.4 tamper response): when the judging-freeze marker is
present (set by the tamper-response path / game-day drill), this module
refuses to run — one plain line, exit 0, zero reads, zero writes.
Fail-closed: ANY marker presence (garbage content, symlink, stat error)
reads FROZEN, so corrupting the marker can never unfreeze judging.

Placement: top-level framework/ sibling (evidence_mirror.py /
evidence_anchor.py precedent) — deliberately OUTSIDE the schg-locked
framework/evidence/ package. Zero germline diff. The module name contains
the substring "framework.evidence", so the officer hook screen makes it
unreachable from officer context by construction (desired: shadow reports
are Captain-facing only); it runs under launchd/Captain context via
cabinet/scripts/evidence-shadow-detectors.py.

House interpreter: python3.12 (the evidence plane needs >= 3.11; nothing
3.9-context imports this module — and per shadow law, nothing imports it
at all).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.evidence import EvidenceRecorder  # noqa: E402  germline read API, import-only
from framework.evidence.query import selector_projection  # noqa: E402  germline read API
from framework.evidence.verifier import STATUSES  # noqa: E402  the ONE status vocabulary
from framework.measurement.eval_pattern_detector import (  # noqa: E402
    _DEFAULT_MIN_OCCURRENCES,
    _DEFAULT_WINDOW_DAYS,
    _trial_day,
    detect_evidence_patterns,
)
from framework.onboarding.journey import EVIDENCE_REL  # noqa: E402  the ONE store-root constant

SCHEMA = "cabinet.evidence-shadow-findings/v1"

# Captain-facing findings journal (falsifier-series.jsonl precedent: one
# JSONL line per run under shared/interfaces/, gitignored runtime series,
# tail-read by the weekly governance review in a LATER wiring — chosen now,
# deliberately not wired in this batch). Never under instance/evidence/.
JOURNAL_REL = "shared/interfaces/evidence-shadow-findings.jsonl"

# Affirmative-evidence source for triage: the append-only degradation
# marker ledgers (evidence_mirror._write_marker rows {ts, chokepoint,
# reason, ...} and the lifecycle sidecar rows {ts, component, phase,
# error_code, ...} share this file's format family — the doctor's
# evidence_probe_degradations reads both shapes from here too).
DEGRADATION_LEDGER_REL = "cabinet/logs/evidence-mirror-degradations.jsonl"

# The judging-freeze marker home (drill group's framework.evidence_freeze
# owns the authoritative module; the local fallback below keeps the same
# inverted fail direction when that module is absent).
FREEZE_MARKER_REL = "instance/state/evidence-judging-freeze.json"

SHADOW_LAW = (
    "SHADOW: detect, never act. Findings are Captain-facing information only; "
    "no downstream consumer may gate, block, score, or act on them. The "
    "enforce flip is a later Captain-only narrowing."
)
HONEST_CLAIM = (
    "Detects retroactive single-plane tamper and INCONSISTENT forgery only; "
    "consistent same-user forgery of both planes stays open until HP-1 "
    "(OS-user/key isolation) lands — necessary, not sufficient."
)
WEAK_SIGNAL = (
    "Evidence-pattern matches are weak signals (design B9): informational "
    "findings only — never watchdog expectation ground truth, never all-clear "
    "evidence, never a score."
)

# Failure/absence statuses clustered as anomalies. Mirrors the recorder's
# own failure rendering set (recorder._report: refused/failed/interrupted/
# missed/expired) — the v1.1 absence vocabulary (design R-2) makes
# non-occurrence first-class, so absence≠health keying needs no new
# vocabulary. Validated against verifier.STATUSES below so drift fails
# loudly in CI instead of silently under-detecting.
FAILURE_STATUSES = ("failed", "refused", "interrupted", "missed", "expired")

_UNKNOWN_STATUSES = tuple(s for s in FAILURE_STATUSES if s not in STATUSES)
if _UNKNOWN_STATUSES:  # pragma: no cover — vocabulary-drift tripwire
    raise RuntimeError(
        "evidence_detectors failure vocabulary drifted from verifier.STATUSES: "
        + ", ".join(_UNKNOWN_STATUSES)
    )

# Triage verdicts — the discriminator's verdict names, cloned (see the
# FAIL-OPEN law in framework/frontdoor/signal_discriminator.py L28-35;
# that module is not imported: it is Sentry-specific, this is the same
# shape over recorded evidence failures).
NOISE = "noise"
INCONCLUSIVE = "inconclusive"

# Report bound so one pathological store cannot balloon the journal; the
# row says so honestly when it truncates.
MAX_REPORTED_FINDINGS = 50

# Future-timestamp grace when matching degradation rows (clock skew, not a
# power bar — no verdict ever depends on it alone).
_SKEW_S = 900


# ─────────────────────────────────────────────────────────────────────────────
# Judging-freeze respect
# ─────────────────────────────────────────────────────────────────────────────
def judging_frozen(repo_root: Path) -> tuple[bool, str]:
    """(frozen, marker_path) — True when evidence-fed judging is frozen.

    Prefers the marker's owning module (framework.evidence_freeze, the
    tamper-drill group's deliverable) when present. Fallback keeps the same
    FAIL-CLOSED inversion: ANY marker presence — valid JSON, garbage, a
    symlink (even dangling), an unreadable path, a stat error — reads
    FROZEN. Deliberately inverted from the observe-only.sh invalid-marker
    handling so corrupting the marker can never unfreeze judging.
    """
    marker = repo_root / FREEZE_MARKER_REL
    try:
        from framework.evidence_freeze import is_frozen  # type: ignore
    except Exception:  # noqa: BLE001 — module absent/unimportable: local fallback
        pass
    else:
        try:
            return bool(is_frozen(repo_root)), str(marker)
        except Exception:  # noqa: BLE001 — a broken freeze probe reads frozen
            return True, str(marker)
    try:
        present = marker.is_symlink() or marker.exists()
    except OSError:
        present = True
    return present, str(marker)


# ─────────────────────────────────────────────────────────────────────────────
# Triage — the discriminator FAIL-OPEN pattern over recorded failures
# ─────────────────────────────────────────────────────────────────────────────
def _parse_iso_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_degradation_rows(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """(rows, readable) from the append-only degradation ledger.

    A MISSING file is ([], True): no degradations recorded is a normal,
    certain state (the doctor probe reads it the same way). An unreadable
    file is ([], False): uncertainty — triage must then classify nothing as
    NOISE. Malformed lines are skipped (the parseable rows remain usable
    affirmative evidence); row text is untrusted data, parsed only.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return [], True
    except OSError:
        return [], False
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows, True


def triage_finding(
    finding: dict[str, Any],
    degradation_rows: list[dict[str, Any]],
    *,
    ledger_readable: bool = True,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    now: Optional[datetime] = None,
) -> tuple[str, str]:
    """Classify one cluster finding: (verdict, why).

    FAIL-OPEN law, verbatim from the discriminator contract: classify NOISE
    ONLY with affirmative evidence — here, a recorded degradation row whose
    chokepoint/component EXACTLY matches the finding's component and whose
    timestamp falls inside the detection window (a recorded, rate-limited
    degradation positively explains recorded failures from that component
    in its window). On ANY uncertainty — unreadable ledger, unparseable
    timestamps, no exact attribution — return INCONCLUSIVE and the caller
    PASSES THE FINDING THROUGH unchanged. Never suppress a finding that
    cannot be positively explained. Fuzzy/substring matches are deliberately
    NOT affirmative (a loose pattern that quietly explains everything is the
    named failure mode this law exists to kill).

    Shadow note: NOISE findings are still REPORTED — triage informs the
    Captain's read; it never drops rows in this batch.
    """
    if not ledger_readable:
        return INCONCLUSIVE, (
            "degradation ledger unreadable — uncertainty is never noise; "
            "passes through"
        )
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    component = finding.get("component")
    if not isinstance(component, str) or not component:
        return INCONCLUSIVE, "finding carries no component — passes through"
    for row in degradation_rows:
        who = row.get("chokepoint") or row.get("component")
        if who != component:
            continue
        ts = _parse_iso_utc(row.get("ts"))
        if ts is None:
            continue  # unparseable timestamp is uncertainty, never affirmative
        if ts < cutoff or ts > now + timedelta(seconds=_SKEW_S):
            continue
        reason = row.get("reason") or row.get("error_code")
        reason = reason if isinstance(reason, str) else "?"
        return NOISE, (
            "explained by recorded degradation "
            f"{component}/{reason[:80]} at {row.get('ts')} "
            "(affirmative attribution; still reported — shadow)"
        )
    return INCONCLUSIVE, (
        "no affirmative degradation attribution — passes through (fail-open)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Detection pass — query plane → cluster seam → triage → report dict
# ─────────────────────────────────────────────────────────────────────────────
def run_detection(
    store_root: Path,
    *,
    degradation_ledger: Path,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    min_occurrences: int = _DEFAULT_MIN_OCCURRENCES,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """One read-only detection pass; returns the report row (does not write).

    Reads exclusively through the germline query plane: one by-status
    selector query per failure status (the R-2 absence statuses are
    first-class selector values), each verification-gated and redacted with
    honest counts. Windowing is coarse — projection records deliberately
    carry no wall-clock timestamp, so the window filters on the trial id's
    day token; trials without a day-bounded id are included regardless and
    the report says so.
    """
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=window_days)).strftime("%Y%m%d")
    end = now.strftime("%Y%m%d")
    recorder = EvidenceRecorder(store_root)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    query_counts: dict[str, dict[str, Any]] = {}
    for status in FAILURE_STATUSES:
        projection = selector_projection(recorder, f"by-status:{status}", limit=1000)
        query_counts[status] = projection["counts"]
        for trial in projection["trials"]:
            if trial.get("verification") != "verified":
                # Unverified stubs stay visible in the honest counts; their
                # content is never clustered (fail-closed display upstream).
                continue
            trial_id = trial.get("trial_id")
            if not isinstance(trial_id, str):
                continue
            day = _trial_day(trial_id)
            if day is not None and not (start <= day <= end):
                continue
            for record in trial.get("records", []):
                if record.get("status") not in FAILURE_STATUSES:
                    continue  # projection serves whole trials; keep failures only
                event_id = record.get("event_id")
                key = (trial_id, str(event_id))
                if event_id is not None and key in seen:
                    continue
                seen.add(key)
                tagged = dict(record)
                tagged["trial_id"] = trial_id
                rows.append(tagged)

    findings = detect_evidence_patterns(rows, min_occurrences=min_occurrences)
    degradation_rows, ledger_readable = load_degradation_rows(degradation_ledger)
    for finding in findings:
        verdict, why = triage_finding(
            finding,
            degradation_rows,
            ledger_readable=ledger_readable,
            window_days=window_days,
            now=now,
        )
        finding["verdict"] = verdict
        finding["verdict_why"] = why

    truncated = len(findings) > MAX_REPORTED_FINDINGS
    reported = findings[:MAX_REPORTED_FINDINGS]
    return {
        "schema": SCHEMA,
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "shadow",
        "shadow_law": SHADOW_LAW,
        "honest_claim": HONEST_CLAIM,
        "weak_signal": WEAK_SIGNAL,
        "window": {
            "since": start,
            "until": end,
            "window_days": window_days,
            "note": (
                "window filters on day-bounded trial ids; trials without a "
                "day token are included regardless (projection records carry "
                "no wall-clock)"
            ),
        },
        "query_counts": query_counts,
        "failure_records": len(rows),
        "findings": reported,
        "findings_truncated": truncated,
        "counts": {
            "clusters_flagged": len(findings),
            "noise_explained": sum(1 for f in findings if f["verdict"] == NOISE),
            "inconclusive": sum(1 for f in findings if f["verdict"] == INCONCLUSIVE),
        },
    }


def append_report(journal: Path, report: dict[str, Any]) -> None:
    """Append ONE JSON line to the Captain-facing journal (outside the store)."""
    journal.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(report, ensure_ascii=False, sort_keys=True)
    with open(journal, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point (scheduled via cabinet/scripts/evidence-shadow-detectors.py)
# ─────────────────────────────────────────────────────────────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Phase-4 SHADOW detectors over the evidence plane (read-only; "
            "Captain-facing report only)."
        )
    )
    # --store/--journal/--repo-root are test/drill seams (scratch stores
    # only), argparse-validated paths, never thresholds. The clustering
    # knobs mirror eval_pattern_detector's own CLI and default to the ONE
    # shared threshold set (R-12) — no power flows from them in shadow.
    parser.add_argument("--store", default=None,
                        help="Store root override (scratch stores/tests). "
                             f"Default: <repo>/{EVIDENCE_REL}.")
    parser.add_argument("--journal", default=None,
                        help=f"Journal override. Default: <repo>/{JOURNAL_REL}.")
    parser.add_argument("--repo-root", default=None,
                        help="Repo root override (tests point the freeze "
                             "marker and defaults at a scratch tree).")
    parser.add_argument("--window-days", type=int, default=_DEFAULT_WINDOW_DAYS,
                        help=f"Rolling window (default: {_DEFAULT_WINDOW_DAYS})")
    parser.add_argument("--min-occurrences", type=int,
                        default=_DEFAULT_MIN_OCCURRENCES,
                        help=f"Cluster threshold (default: {_DEFAULT_MIN_OCCURRENCES})")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _REPO_ROOT

    frozen, marker = judging_frozen(repo_root)
    if frozen:
        # §2.4: evidence-fed judging is frozen — refuse to run. One plain
        # line (the service log / Chair triage reads it), exit 0, zero
        # store reads, zero report writes. Clearing the marker is
        # Captain-only, by hand, per the tamper-drill runbook.
        print(f"evidence-shadow-detectors: frozen — refusing to run ({marker})")
        return 0

    store = Path(args.store) if args.store else repo_root / EVIDENCE_REL
    journal = Path(args.journal) if args.journal else repo_root / JOURNAL_REL
    try:
        store_resolved = store.resolve()
        journal_resolved = journal.parent.resolve() / journal.name
    except OSError:
        print("evidence-shadow-detectors: FATAL cannot resolve store/journal paths",
              file=sys.stderr)
        return 2
    if str(journal_resolved).startswith(str(store_resolved) + "/"):
        # Report files NEVER live inside the store (byte-stability law).
        print("evidence-shadow-detectors: FATAL journal path sits inside the "
              "evidence store — refusing", file=sys.stderr)
        return 2

    if not store.is_dir():
        print(f"evidence-shadow-detectors: no store at {store} — evidence "
              "plane not activated; nothing to detect")
        return 0

    try:
        report = run_detection(
            store,
            degradation_ledger=repo_root / DEGRADATION_LEDGER_REL,
            window_days=args.window_days,
            min_occurrences=args.min_occurrences,
        )
        append_report(journal, report)
    except Exception as exc:  # noqa: BLE001 — measurement error is a loud, typed exit
        # FATAL is deliberate: the watchdog error-marker floor scans service
        # logs for it, so a broken detector pages the Chair for free.
        print("evidence-shadow-detectors: FATAL measurement error: "
              f"{exc.__class__.__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 2

    counts = report["counts"]
    print(
        "evidence-shadow-detectors: shadow report appended "
        f"(clusters={counts['clusters_flagged']} "
        f"noise_explained={counts['noise_explained']} "
        f"inconclusive={counts['inconclusive']} "
        f"failure_records={report['failure_records']}) → {journal}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
