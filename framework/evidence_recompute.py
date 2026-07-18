"""HP-2 independent recompute legs — REPORT-ONLY shadow verifier (staged dark).

THE HONEST CLAIM (design of record 2026-07-16 §2.3 HP-2, §2.5; mandatory in
this docstring, on every report line, and in the runbook): this leg is a
DIFFERENT producer identity but the SAME OS user until the HP-1 deploy
ceremony lands — its independence comes from re-deriving outcomes from RAW
artifacts (undo-journal row bytes, gate pack + archived patch bytes, the
consequence ledger, org-event day files), never from a trust-domain
boundary. A same-user attacker who forges the raw artifacts consistently
still passes, and root forges everything — necessary, not sufficient.

WHAT IT DOES: for each fuel-bearing machine-claimed outcome kind, it
re-derives the outcome from raw artifacts WITHOUT reading the producer's
claimed verdict as an input to the derivation (the claim is read only to
COMPARE), and appends ONE verification event per checked outcome to its
OWN evidence day trial (``evt-recompute-<yyyymmdd>``) with
``agreement: agree | disagree | underivable:<reason>``:

  1. act-lane TTL outcomes — the undo-sweep's ``ttl_ok`` /
     ``silent_revert`` machine labels, re-derived from the undo-journal
     row bytes (status/executed_at/reversed_at/ttl_expires_at/canary/demo)
     joined by the ledger row's ``undo-journal:<jid>`` ref; the
     silent-revert attribution needs the (injected) artifact probe — probe
     absent is an HONEST SKIP (``underivable:artifact-unavailable``),
     never a guess;
  2. gate verdicts — the learning gate's ratify packs, re-derived from
     pack bytes: archived-patch sha256 recomputed and compared to the
     pack's claim, stage-status→verdict consistency per ratify's control
     flow, ``applies_nothing`` invariant, pack↔store gate receipt
     equality, and — ONLY where a pack names a CI-checkable commit — the
     ``gh`` check-runs probe (feature-detected; ``gh`` absent is an
     honest ``underivable:artifact-unavailable``, never a guess);
  3. graduation transitions — ``graduation_transition`` org events,
     re-derived by re-running the germline ``graduation.evaluate`` over
     the consequence ledger at the claimed time, plus the org-mirror
     receipt sha cross-check.

DISCRIMINATOR LAW (verbatim polarity): a contradiction is claimed only
with AFFIRMATIVE evidence — raw bytes that contradict the claim. Absence
(journal row GC'd after 30d, archived patch missing, purged trial, probe
unavailable, ledger window gone) is ``underivable:<reason>`` and passes
through; absence alone never renders tamper.

SHADOW LAW (Phase-4 binds): every output is a report. Nothing the minter
reads; disagree events are INFORMATION for the Captain's weekly review.
Structurally enforced:

* READ-ONLY toward both planes EXCEPT the one sanctioned write: appends to
  its OWN ``evt-recompute-*`` day trials via the public
  ``EvidenceRecorder`` API. Ledger reads ride
  ``framework.fidelity.consequence.read_ledger`` (symlink-fenced,
  sim-quarantined); journal reads ride ``action_undo._read_journal``
  (symlink-fenced, last-write-wins); store reads ride the public
  ``read_events`` API (verification-gated; the signed anti-rollback
  watermark advancing on a trial's FIRST verify is the sanctioned store
  byte change). This module never writes org events, never writes the
  ledger or journal, never opens ``.signing-key``, and never constructs a
  recorder over an ABSENT store (construction would create scaffolding) —
  when the store is absent it derives and reports, recording nothing.
* Report files live OUTSIDE both planes: default
  ``cabinet/logs/evidence-recompute-report.jsonl`` (gitignored runtime,
  Captain-facing). ``write_report`` REFUSES an output path inside the
  store or the consequence-ledger dir.
* Never-a-score: report lines carry verdicts-per-outcome and COUNTS, never
  rates. This module's name contains the ``framework.evidence`` substring,
  so the officer hook screen makes its CLI unreachable from officer
  context by construction.
* Exit codes carry no verdict signal (0 = measured, findings or not;
  2 = could not measure). Nothing may key a gate on this process.
* Classification honesty: the event detail keys this producer mints
  (``target``, ``agreement``, ``claim``, ``rederived``, ``claim_sha256``,
  ``legs``…) are UNREGISTERED in the germline classification registry and
  therefore read back as producer-asserted (the fail-closed default —
  ``classify_detail_key`` renders nothing independently established by
  omission). Promoting them to independently_established is a
  ceremony-gated germline registry change that requires this checker to
  exist first — the documented registry pattern; queued as a
  deploy-ceremony line item in docs/runbooks/evidence-recompute.md, never
  part of this dark wave.
* TRUSTED-CORE FORWARD OBLIGATION (design §3 Phase-4 item 5): while
  Phase-4 shadow law binds, these events are structurally an untrusted
  report that the fuel-integrity checker re-verifies against raw recorder
  evidence. The moment they are allowed to SATISFY the third leg for
  actual minting (the enforce flip), this module either enters
  immutable-core via the ``pending:`` procedure or its events keep being
  re-derived at consume time — an explicit ceremony item, never implicit.

Idempotence / exhaust discipline: one event per checked outcome; re-runs
skip outcomes whose ``claim_sha256`` already has an event in the window's
recompute day trials — the dedup scan covers the WHOLE window day range
because recompute events land on their RUN day (wall clock), which for an
old outcome is far from the outcome's own ts (crash-recovery re-checks of
the SAME claim are normal and deduped, never re-minted). The window is
the ONE imported calibration freshness horizon (``STATUS_MAX_AGE_DAYS``)
— no new number.

Sibling-module precedent: framework/evidence_anchor.py and
framework/evidence_mirror.py (top-level framework/ observers OUTSIDE the
schg-locked framework/evidence package). python3.12 only (the evidence
package needs 3.11+). The scheduled runner is
cabinet/scripts/evidence-recompute.py (services row shipped
``disabled: true`` — dark by default; the Captain ceremony enables it).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from framework import evidence_freeze  # §2.4 judging-freeze respect
from framework import evidence_mirror
from framework.evidence import EvidenceError, EvidenceRecorder
from framework.evidence import identity
from framework.evidence.lifecycle import valid_id_or_none
from framework.fidelity.consequence import (
    _consequence_log_dir,  # the ONE env rule (judge_calibration precedent)
    read_ledger,
)
from framework.fidelity.graduation import evaluate as graduation_evaluate
from framework.frontdoor import action_undo
# R-11: the freshness horizon is IMPORTED, never redefined, never a flag.
from framework.fidelity.judge_calibration import STATUS_MAX_AGE_DAYS
from framework.learning import gate

SCHEMA = "cabinet.evidence-recompute-report/v1"

#: Mandatory text on every report line (see module docstring).
HONEST_CLAIM = (
    "independent recomputation by a DIFFERENT producer identity but the "
    "SAME OS user until HP-1 (OS-user/key isolation) lands — independence "
    "comes from re-deriving outcomes from raw artifacts, never from a "
    "trust-domain boundary; a same-user attacker who forges the raw "
    "artifacts consistently still passes, and root forges everything — "
    "necessary, not sufficient"
)

#: The verification-event vocabulary (detail.action + agreement values).
ACTION = "recompute_verification"
AGREE = "agree"
DISAGREE = "disagree"
UNDERIVABLE = "underivable"  # always suffixed ":<reason>" on events

#: Day-trial taxonomy class for this producer's own writes (the one
#: sanctioned write surface): ``evt-recompute-<yyyymmdd>``.
TRIAL_CLASS = "recompute"

#: Documented copies of producer marker text (the same documented-copy
#: pattern gate.py itself uses for the TTL marker): the outcome-evidence
#: prefixes binder_wire._ACTED_VERDICTS mints for the two machine labels.
TTL_OK_MARKER = "ttl-48h survived"
SILENT_REVERT_MARKER = "silent revert"

#: Report home (repo-relative; cabinet/logs/* is gitignored runtime).
REPORT_REL = ("cabinet", "logs", "evidence-recompute-report.jsonl")

#: Dedup/join scans never walk more than this many days even under an
#: extreme explicit ``--since`` (bounded store probing; the default window
#: is STATUS_MAX_AGE_DAYS and never comes near it).
MAX_SCAN_DAYS = 400

_UNDO_REF_PREFIX = "undo-journal:"
_GATE_TRIAL_PREFIX = "evt-learning-gate-"
_GATE_RECEIPT_ACTION = "gate_ratify"
_ORG_MIRROR_ACTION = "org_event_mirror"
_GRADUATION_EVENT_TYPE = "graduation_transition"

#: Pack keys that name a CI-checkable commit (future-proof: today's ratify
#: packs carry none, so the default path never spawns ``gh`` — the leg
#: engages only when a pack affirmatively names a commit).
_CI_COMMIT_KEYS = ("commit", "ci_commit")

#: Fallback identity when the process is unattested (tests; library use).
_ACTOR = {"kind": "system", "id": "evidence-recompute"}
_COMPONENT = {"name": "evidence-recompute", "version": "1"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _day8(ts: str) -> str | None:
    day = (ts or "")[:10].replace("-", "")
    if len(day) == 8 and day.isdigit():
        return day
    return None


def _adjacent_days(day8: str) -> list[str]:
    """day-1, day, day+1 — receipts and claims can land across a UTC
    midnight (the join-window discipline)."""
    try:
        base = datetime.strptime(day8, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return [day8]
    return [(base + timedelta(days=delta)).strftime("%Y%m%d")
            for delta in (-1, 0, 1)]


def _window_days(since: str, now_dt: datetime) -> list[str]:
    """Every yyyymmdd from (since-day − 1) through (today + 1), bounded by
    MAX_SCAN_DAYS. Recompute events land on their RUN day (wall clock) —
    for an old outcome that is far from the outcome's own ts, so the
    idempotence scan must cover the whole window, never ts-day ±1."""
    end = now_dt + timedelta(days=1)
    start: datetime | None = None
    start_day = _day8(since)
    if start_day is not None:
        try:
            start = datetime.strptime(start_day, "%Y%m%d").replace(
                tzinfo=timezone.utc) - timedelta(days=1)
        except ValueError:
            start = None
    if start is None or (end - start).days > MAX_SCAN_DAYS:
        start = end - timedelta(days=MAX_SCAN_DAYS)
    days: list[str] = []
    cursor = start
    while cursor.date() <= end.date():
        days.append(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)
    return days


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _canonical_sha256(value: Any) -> str:
    """The documented canonical join recipe — reused from the mirror so the
    two sides can never drift (the judge_calibration import-the-private
    precedent, the same one the fuel-integrity checker rides)."""
    return evidence_mirror._canonical_sha256(value)


def _row_refs(row: dict[str, Any]) -> list[str]:
    refs = row.get("refs")
    return [r for r in refs if isinstance(r, str)] if isinstance(refs, list) else []


def _row_jids(row: dict[str, Any]) -> list[str]:
    return [ref[len(_UNDO_REF_PREFIX):] for ref in _row_refs(row)
            if ref.startswith(_UNDO_REF_PREFIX) and len(ref) > len(_UNDO_REF_PREFIX)]


# ---------------------------------------------------------------------------
# Store access — public API only; never constructs over an absent store.
# ---------------------------------------------------------------------------

def _store_root(explicit: Any | None) -> Path | None:
    """The evidence store root, or None when store access is fenced off.

    An EXPLICIT root (tests / callers) always wins. Under pytest the store
    is unreachable unless ``CABINET_ACTION_EVIDENCE_STORE`` names a scratch
    store — the evidence_mirror pytest fence (2026-07-04 live-store leak
    lesson). Production resolution is repo-derived via the journey
    producer's EVIDENCE_REL (the ONE canonical constant), never
    env-derived (A10)."""
    if explicit is not None:
        return Path(explicit)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        override = os.environ.get("CABINET_ACTION_EVIDENCE_STORE")
        return Path(override) if override else None
    from framework.onboarding.journey import EVIDENCE_REL
    return _repo_root() / EVIDENCE_REL


class _Store:
    """Cached, fail-soft store handle (reader + this producer's writer).

    States: ``("ok", events)`` | ``("missing", None)`` | ``("purged", None)``
    | ``("integrity_failed", code)`` | ``("error", code)`` |
    ``("unavailable", None)``. A recorder is constructed ONLY over a store
    that already exists (``control.json`` present) — a shadow verifier must
    never create a store by looking at it."""

    def __init__(self, store_root: Path | None):
        self.root = Path(store_root) if store_root is not None else None
        self.available = bool(
            self.root is not None and (self.root / "control.json").is_file())
        self._recorder: EvidenceRecorder | None = None
        self._cache: dict[str, tuple[str, Any]] = {}

    def recorder(self) -> EvidenceRecorder:
        if self._recorder is None:
            self._recorder = EvidenceRecorder(self.root)
        return self._recorder

    def state(self, trial_id: str) -> tuple[str, Any]:
        if not self.available:
            return ("unavailable", None)
        if trial_id in self._cache:
            return self._cache[trial_id]
        try:
            events = self.recorder().read_events(trial_id)
            result: tuple[str, Any] = ("ok", events)
        except EvidenceError as exc:
            code = str(getattr(exc, "code", "") or "evidence_error")
            if code == "trial_purged":
                result = ("purged", None)
            elif code == "trial_not_found":
                result = ("missing", None)
            elif code == "ledger_integrity":
                result = ("integrity_failed", code)
            else:
                result = ("error", code)
        except Exception as exc:  # defensive: measurement, never a crash
            result = ("error", type(exc).__name__)
        self._cache[trial_id] = result
        return result

    def invalidate(self, trial_id: str) -> None:
        self._cache.pop(trial_id, None)


def _recompute_trials_for_days(days: list[str]) -> list[str]:
    """Every recompute day-trial id (base + chain segments) for the given
    yyyymmdd days — naming via the mirror's reserved recipe so a future
    volume-chained writer stays joinable."""
    out: list[str] = []
    for day in days:
        for segment in range(evidence_mirror.MAX_CHAIN_SEGMENTS):
            trial_id = evidence_mirror._trial_id(TRIAL_CLASS, segment, day)
            if trial_id not in out:
                out.append(trial_id)
    return out


def _existing_claim_shas(store: _Store, days: list[str]) -> set[str]:
    """claim_sha256 values already recorded — the idempotence guard
    (re-checking the SAME claim is normal; re-minting it is exhaust)."""
    seen: set[str] = set()
    for trial_id in _recompute_trials_for_days(days):
        state, events = store.state(trial_id)
        if state != "ok":
            continue
        for event in events:
            detail = event.get("detail")
            if isinstance(detail, dict) and detail.get("action") == ACTION:
                sha = detail.get("claim_sha256")
                if isinstance(sha, str) and sha:
                    seen.add(sha)
    return seen


# ---------------------------------------------------------------------------
# Raw-artifact readers (org-event day files; ledger/journal ride their
# sanctioned readers directly).
# ---------------------------------------------------------------------------

def _read_org_events(log_dir: Path | None = None) -> list[dict[str, Any]]:
    """Read org-event day files (``events-YYYY-MM-DD.jsonl``) from the
    shared runtime event dir. The org-event writer package is a WRITE
    surface this module must never import (source-law), so the day files
    are read directly with the house symlink fence (a file resolving
    outside the resolved dir is skipped, never followed) and torn/garbled
    lines are skipped — absence degrades to underivable, never a crash."""
    base_dir = Path(log_dir) if log_dir is not None else _consequence_log_dir()
    if not base_dir.exists():
        return []
    try:
        resolved = base_dir.resolve()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(base_dir.glob("events-*.jsonl")):
        try:
            real = path.resolve()
        except OSError:
            continue
        if not (real == resolved or resolved in real.parents):
            continue  # symlink escape — skip, never follow
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue  # torn tail / garbage — honest skip
                    if isinstance(row, dict):
                        rows.append(row)
        except OSError:
            continue
    return rows


# ---------------------------------------------------------------------------
# Leg 1 — act-lane TTL outcomes (undo-journal bytes vs the ledger claim).
# ---------------------------------------------------------------------------

_JOURNAL_REVERSED_STATES = ("reversed", "reversal_failed", "dead_letter")


def _derive_act(kind: str, jrow: dict[str, Any] | None,
                monday_probe: Callable | None,
                now_iso: str) -> tuple[str | None, str]:
    """(rederived, agreement) for one act-lane machine claim.

    The derivation reads ONLY raw journal bytes (+ the injected artifact
    probe for the silent-revert leg) — never the producer's verdict."""
    if jrow is None:
        # 30d journal GC (JOURNAL_RETENTION_D) — an honest gap, never a
        # finding (discriminator law: absence alone renders nothing).
        return None, f"{UNDERIVABLE}:journal-row-gone"
    if jrow.get("canary") or jrow.get("demo"):
        # Affirmative: raw bytes say this row was never sweep-eligible —
        # a machine label minted from it contradicts the producer's own law.
        return "ineligible", DISAGREE
    reversed_seen = bool(jrow.get("reversed_at")) or (
        jrow.get("status") in _JOURNAL_REVERSED_STATES)
    if kind == "act_ttl_ok":
        if reversed_seen:
            return "failed", DISAGREE
        if jrow.get("status") == "void":
            return "void", DISAGREE
        if jrow.get("status") != "executed" or not jrow.get("executed_at"):
            return None, f"{UNDERIVABLE}:journal-row-malformed"
        expires = str(jrow.get("ttl_expires_at") or "")
        if not expires:
            return None, f"{UNDERIVABLE}:journal-row-malformed"
        if expires >= now_iso:
            # The 48h clock has not run out even NOW, yet a survival label
            # exists — affirmatively minted before its own precondition.
            return "ttl-not-elapsed", DISAGREE
        return "ok", AGREE
    # act_silent_revert — outcome ``failed`` claimed.
    if reversed_seen:
        return "failed", AGREE  # the journal itself proves the artifact fell
    if monday_probe is None:
        # The revert claim rests on an artifact-state probe this
        # environment does not carry — honest skip, never a guess.
        return None, f"{UNDERIVABLE}:artifact-unavailable"
    try:
        state = monday_probe(jrow) or {}
    except Exception:
        return None, f"{UNDERIVABLE}:probe-error"
    if not state.get("exists", True) or state.get("archived", False):
        return "failed", AGREE
    return "ok", DISAGREE  # the artifact stands; the revert claim does not


def _act_targets(ledger_rows: list[dict[str, Any]],
                 journal_by_jid: dict[str, dict[str, Any]],
                 monday_probe: Callable | None,
                 since: str, until: str | None,
                 now_iso: str) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for row in ledger_rows:
        ts = str(row.get("ts") or "")
        if ts < since or (until is not None and ts > until):
            continue
        outcome = row.get("outcome") or {}
        status = outcome.get("status")
        evidence = str(outcome.get("evidence") or "")
        if status == "ok" and evidence.startswith(TTL_OK_MARKER):
            kind, claim = "act_ttl_ok", "ok"
        elif status == "failed" and evidence.startswith(SILENT_REVERT_MARKER):
            kind, claim = "act_silent_revert", "failed"
        else:
            continue  # not a machine-labeled act outcome
        jids = _row_jids(row)
        jid = jids[-1] if jids else None
        row_sha = _canonical_sha256(row)
        if jid is None:
            rederived, agreement = None, f"{UNDERIVABLE}:journal-join-missing"
        else:
            rederived, agreement = _derive_act(
                kind, journal_by_jid.get(jid), monday_probe, now_iso)
        target: dict[str, Any] = {
            "target": kind,
            "claim": claim,
            "rederived": rederived,
            "agreement": agreement,
            "row_sha256": row_sha,
            "ts": ts,
        }
        if jid is not None:
            target["jid"] = jid
        target["claim_sha256"] = _canonical_sha256(
            {"target": kind, "jid": jid, "row_sha256": row_sha, "claim": claim})
        targets.append(target)
    return targets


# ---------------------------------------------------------------------------
# Leg 2 — gate verdicts (pack + archived patch bytes vs the pack claim).
# ---------------------------------------------------------------------------

_PASS_STAGES = ("S0_scope", "S1_verify", "S2_falsifier", "S3_ceilings",
                "S4_archive")


def _expected_verdict(stages: dict[str, str]) -> str:
    """Re-derive the verdict ratify's control flow implies from the stage
    statuses: ``refused`` iff S0 refused; ``pass`` iff the five build
    stages all pass; anything else ``fail``."""
    if stages.get("S0_scope") == "refused":
        return "refused"
    if all(stages.get(name) == "pass" for name in _PASS_STAGES):
        return "pass"
    return "fail"


def _default_ci_probe() -> Callable | None:
    """A check-runs probe over the ``gh`` CLI, or None when the environment
    does not carry it (feature-detect — an honest skip, never a guess).
    Arg-list-only subprocess by law; never a shell string."""
    if shutil.which("gh") is None:
        return None

    def probe(commit: str) -> dict[str, Any] | None:
        completed = subprocess.run(
            ["gh", "api",
             "repos/{owner}/{repo}/commits/" + str(commit) + "/check-runs"],
            cwd=str(_repo_root()), capture_output=True, timeout=30)
        if completed.returncode != 0:
            return None
        data = json.loads(completed.stdout.decode("utf-8", errors="replace"))
        runs = data.get("check_runs") or []
        if not runs:
            return None
        ok = all(run.get("conclusion") in ("success", "neutral", "skipped")
                 for run in runs)
        return {"ok": ok, "runs": len(runs)}

    return probe


def _ci_leg(pack: dict[str, Any], claim: str,
            ci_probe: Callable | None) -> str | None:
    """The optional CI cross-check: engages ONLY when the pack affirmatively
    names a commit (discriminator law — a pack that makes no CI claim gets
    no CI leg). Returns a leg status string or None (no leg)."""
    commit = next((str(pack[key]) for key in _CI_COMMIT_KEYS
                   if isinstance(pack.get(key), str) and pack.get(key)), None)
    if commit is None:
        return None
    if ci_probe is None:
        return f"{UNDERIVABLE}:artifact-unavailable"
    try:
        result = ci_probe(commit)
    except Exception:
        return f"{UNDERIVABLE}:probe-error"
    if not result:
        return f"{UNDERIVABLE}:artifact-unavailable"
    if claim == "pass":
        return "pass" if result.get("ok") else "fail"
    return "pass"  # a fail/refused claim is not contradicted by CI state


def _find_gate_receipt(store: _Store, pack_id: str,
                       pack_ts: str) -> tuple[str, dict[str, Any] | None]:
    day = _day8(pack_ts)
    if day is None:
        return (f"{UNDERIVABLE}:receipt-missing", None)
    saw_purged = False
    for adjacent in _adjacent_days(day):
        trial_id = f"{_GATE_TRIAL_PREFIX}{adjacent}"
        state, events = store.state(trial_id)
        if state == "purged":
            saw_purged = True
            continue
        if state == "unavailable":
            return (f"{UNDERIVABLE}:store-unavailable", None)
        if state != "ok":
            continue
        for event in events:
            detail = event.get("detail")
            if (isinstance(detail, dict)
                    and detail.get("action") == _GATE_RECEIPT_ACTION
                    and detail.get("pack_id") == pack_id):
                return ("found", detail)
    if saw_purged:
        return (f"{UNDERIVABLE}:trial-purged", None)
    return (f"{UNDERIVABLE}:receipt-missing", None)


def _gate_targets(packs: list[dict[str, Any]], store: _Store,
                  variants_dir: Path, ci_probe: Callable | None,
                  since: str, until: str | None) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for pack in packs:
        ts = str(pack.get("ts") or "")
        if ts < since or (until is not None and ts > until):
            continue
        pack_id = str(pack.get("pack_id") or "")
        if not pack_id:
            continue
        claim = str(pack.get("verdict") or "")
        sha = str(pack.get("sha256") or "")
        stages = {
            str(s.get("stage")): str(s.get("status"))
            for s in (pack.get("stages") or []) if isinstance(s, dict)
        }
        legs: dict[str, str] = {}
        reason: str | None = None

        legs["applies_nothing"] = (
            "pass" if pack.get("applies_nothing") is True else "fail")
        if legs["applies_nothing"] == "fail":
            reason = reason or "applies-nothing-violated"

        rederived = _expected_verdict(stages)
        legs["stage_consistency"] = "pass" if rederived == claim else "fail"
        if legs["stage_consistency"] == "fail":
            reason = reason or "stage-verdict-inconsistent"

        if claim == "pass":
            patch = variants_dir / f"{sha[:16]}.patch"
            if not patch.is_file():
                legs["archive_sha"] = f"{UNDERIVABLE}:archive-missing"
            else:
                try:
                    recomputed = gate.diff_sha256(
                        patch.read_text(encoding="utf-8"))
                except OSError:
                    recomputed = None
                if recomputed is None:
                    legs["archive_sha"] = f"{UNDERIVABLE}:archive-missing"
                elif recomputed == sha:
                    legs["archive_sha"] = "pass"
                else:
                    legs["archive_sha"] = "fail"
                    reason = reason or "archive-sha-mismatch"

        receipt_state, receipt = _find_gate_receipt(store, pack_id, ts)
        if receipt is not None:
            receipt_stages = receipt.get("stages")
            matches = (
                receipt.get("sha256") == sha
                and receipt.get("verdict") == claim
                and (not isinstance(receipt_stages, dict)
                     or receipt_stages == stages)
            )
            legs["store_receipt"] = "pass" if matches else "fail"
            if not matches:
                reason = reason or "receipt-mismatch"
        else:
            legs["store_receipt"] = receipt_state

        ci_status = _ci_leg(pack, claim, ci_probe)
        if ci_status is not None:
            legs["ci"] = ci_status
            if ci_status == "fail":
                reason = reason or "ci-contradicts-verdict"

        if any(status == "fail" for status in legs.values()):
            agreement = DISAGREE
        else:
            agreement = AGREE  # underivable side legs ride along, reported
        target: dict[str, Any] = {
            "target": "gate_verdict",
            "claim": claim,
            "rederived": rederived,
            "agreement": agreement,
            "pack_id": pack_id,
            "legs": legs,
            "ts": ts,
            "claim_sha256": _canonical_sha256(
                {"target": "gate_verdict", "pack_id": pack_id,
                 "sha256": sha, "claim": claim}),
        }
        if reason:
            target["reason"] = reason
        targets.append(target)
    return targets


# ---------------------------------------------------------------------------
# Leg 3 — graduation transitions (germline evaluate re-run + mirror sha).
# ---------------------------------------------------------------------------

def _org_mirror_leg(store: _Store, event: dict[str, Any]) -> str:
    if not store.available:
        return f"{UNDERIVABLE}:store-unavailable"
    event_id = str(event.get("id") or "")
    day = _day8(str(event.get("created_at") or ""))
    if not event_id or day is None:
        return f"{UNDERIVABLE}:mirror-receipt-missing"
    expected_sha = _canonical_sha256(event)
    for adjacent in _adjacent_days(day):
        for segment in range(evidence_mirror.MAX_CHAIN_SEGMENTS):
            trial_id = evidence_mirror._trial_id(
                evidence_mirror.ORG_TRIAL_CLASS, segment, adjacent)
            state, events = store.state(trial_id)
            if state != "ok":
                continue
            for stored in events:
                detail = stored.get("detail")
                if (isinstance(detail, dict)
                        and detail.get("action") == _ORG_MIRROR_ACTION
                        and detail.get("org_event_id") == event_id):
                    return ("pass" if detail.get("org_event_sha256")
                            == expected_sha else "fail")
    return f"{UNDERIVABLE}:mirror-receipt-missing"


def _cell_has_rows(cell: tuple[str, Any, str],
                   rows: list[dict[str, Any]]) -> bool:
    actor_id, lane, action_type = cell
    for row in rows:
        actor = row.get("actor") or {}
        if (f"{actor.get('kind')}:{actor.get('id')}" == actor_id
                and row.get("lane") == lane
                and row.get("action_type") == action_type):
            return True
    return False


def _graduation_targets(org_events: list[dict[str, Any]],
                        ledger_rows: list[dict[str, Any]], store: _Store,
                        since: str, until: str | None) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for event in org_events:
        if event.get("event_type") != _GRADUATION_EVENT_TYPE:
            continue
        created = str(event.get("created_at") or "")
        if created < since or (until is not None and created > until):
            continue
        payload = event.get("payload") or {}
        cell_map = payload.get("cell") or {}
        actor = cell_map.get("actor")
        action_type = cell_map.get("action_type")
        claim = str(payload.get("to_state") or "")
        event_id = str(event.get("id") or "")
        target: dict[str, Any] = {
            "target": "graduation_transition",
            "claim": claim,
            "org_event_id": event_id,
            "ts": created,
            "claim_sha256": _canonical_sha256(
                {"target": "graduation_transition", "org_event_id": event_id,
                 "claim": claim}),
        }
        if not actor or not action_type or not claim:
            target["rederived"] = None
            target["agreement"] = f"{UNDERIVABLE}:claim-malformed"
            targets.append(target)
            continue
        cell = (str(actor), cell_map.get("lane"), str(action_type))
        target["cell"] = f"{cell[0]}|{cell[1]}|{cell[2]}"
        legs: dict[str, str] = {}
        reason: str | None = None
        if not _cell_has_rows(cell, ledger_rows):
            # The backing window is gone (retention, quarantine, migration):
            # nothing to re-derive from — an honest gap, never a finding.
            rederived, agreement = None, f"{UNDERIVABLE}:ledger-window-gone"
        else:
            claimed_at = _parse_ts(created) or _utc_now()
            try:
                verdict = graduation_evaluate(
                    cell, ledger=ledger_rows, now=claimed_at)
                rederived = str(verdict.get("state") or "")
            except Exception:
                rederived = None
            if rederived is None:
                agreement = f"{UNDERIVABLE}:evaluate-error"
            elif rederived == claim:
                agreement = AGREE
            else:
                # NOTE: the ledger is last-write-wins — rows superseded
                # AFTER the claim legitimately shift this recomputation;
                # a disagree is weekly-review INFORMATION (shadow law),
                # never a tamper verdict by itself.
                agreement = DISAGREE
                reason = "state-mismatch"
        legs["org_mirror"] = _org_mirror_leg(store, event)
        if legs["org_mirror"] == "fail":
            # Affirmative: the signed receipt disagrees with the org-event
            # bytes on disk — one of the two was rewritten after mirroring.
            agreement = DISAGREE
            reason = "mirror-sha-mismatch"
        target["rederived"] = rederived
        target["agreement"] = agreement
        target["legs"] = legs
        if reason:
            target["reason"] = reason
        targets.append(target)
    return targets


# ---------------------------------------------------------------------------
# Recording — the ONE sanctioned write: this producer's own day trial.
# ---------------------------------------------------------------------------

_STATUS_BY_AGREEMENT = {AGREE: "verified", DISAGREE: "unverified"}


def _identity_parts() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    if identity.is_attested():
        return (identity.attested_actor(), identity.attested_component(),
                identity.attestation_detail())
    return (dict(_ACTOR), dict(_COMPONENT), {})


def _record_target(store: _Store, target: dict[str, Any],
                   counts: dict[str, int], existing: set[str],
                   today8: str, seg_state: dict[str, int]) -> None:
    """Append ONE verification event for a checked outcome. Never raises;
    a failed append degrades LOUD on stderr and is counted. A full day
    trial (per-trial event envelope) rolls to the next chain segment —
    the mirror's own naming, so readers scan segments uniformly."""
    if not store.available:
        counts["unrecorded_store_unavailable"] += 1
        target["recorded"] = False
        return
    claim_sha = target["claim_sha256"]
    if claim_sha in existing:
        counts["skipped_existing"] += 1
        target["recorded"] = False
        return
    agreement = target["agreement"]
    status = _STATUS_BY_AGREEMENT.get(agreement, "skipped")
    actor, component, stamp = _identity_parts()
    detail: dict[str, Any] = dict(stamp)
    detail.update({
        "action": ACTION,
        "target": target["target"],
        "agreement": agreement,
        "claim": str(target.get("claim")),
        "rederived": str(target.get("rederived")),
        "claim_sha256": claim_sha,
    })
    for key in ("jid", "row_sha256", "pack_id", "org_event_id", "cell",
                "reason"):
        if target.get(key):
            detail[key] = target[key]
    if isinstance(target.get("legs"), dict):
        detail["legs"] = dict(target["legs"])
    links: list[str] = []
    jid = target.get("jid")
    if jid and valid_id_or_none(f"{_UNDO_REF_PREFIX}{jid}"):
        links.append(f"{_UNDO_REF_PREFIX}{jid}")
    pack_id = target.get("pack_id")
    if pack_id and valid_id_or_none(f"gate-pack:{pack_id}"):
        links.append(f"gate-pack:{pack_id}")
    while seg_state["segment"] < evidence_mirror.MAX_CHAIN_SEGMENTS:
        trial_id = evidence_mirror._trial_id(
            TRIAL_CLASS, seg_state["segment"], today8)
        try:
            recorder = store.recorder()
            context = recorder.trace(trial_id, surface="system",
                                     correlation_id=valid_id_or_none(claim_sha))
            appended = recorder.append(
                context, phase="verification", status=status, actor=actor,
                component=component, detail=detail, links=links)
            counts["recorded"] += 1
            existing.add(claim_sha)
            store.invalidate(trial_id)
            target["recorded"] = True
            target["event_id"] = appended.get("event_id")
            return
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == "trial_event_cap":
                seg_state["segment"] += 1  # roll to the next day segment
                continue
            if code == "trial_purged":
                counts["skipped_purged"] += 1  # retention won — a legal state
            else:
                counts["record_failures"] += 1
                print("evidence-recompute: WARN verification event not "
                      f"recorded ({code or type(exc).__name__})",
                      file=sys.stderr)
            target["recorded"] = False
            return
    counts["record_failures"] += 1
    print("evidence-recompute: WARN verification event not recorded "
          "(all day segments full)", file=sys.stderr)
    target["recorded"] = False


# ---------------------------------------------------------------------------
# The check — read raw artifacts → re-derive → compare → record → report.
# ---------------------------------------------------------------------------

def check_recompute(
    *,
    store_root: Path | str | None = None,
    since: str | None = None,
    until: str | None = None,
    ledger: list[dict[str, Any]] | None = None,
    journal_rows: list[dict[str, Any]] | None = None,
    gate_root: Path | str | None = None,
    org_events: list[dict[str, Any]] | None = None,
    monday_probe: Callable | None = None,
    ci_probe: Callable | None = None,
    record: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the three recompute legs and return the report dict.

    Injected inputs (``ledger`` / ``journal_rows`` / ``org_events`` /
    ``monday_probe`` / ``ci_probe``) are composition/test seams —
    production callers pass nothing and the sanctioned readers run
    (``ci_probe`` defaults to the feature-detected ``gh`` probe, which the
    gate leg consults ONLY for packs that name a commit). ``record=False``
    derives and reports without touching the store's write path."""
    now_dt = now or _utc_now()
    now_iso = _iso(now_dt)
    if since is None:
        # The ONE imported freshness horizon — no new number (R-11).
        since = _iso(now_dt - timedelta(days=STATUS_MAX_AGE_DAYS))
    root = _store_root(store_root)
    store = _Store(root)

    ledger_rows = ledger if ledger is not None else read_ledger()
    rows_j = (journal_rows if journal_rows is not None
              else action_undo._read_journal())
    journal_by_jid = {str(r.get("jid")): r for r in rows_j if r.get("jid")}
    packs = gate._packs(gate_root)
    variants_dir = gate.evidence_dir(gate_root) / "variants"
    events = org_events if org_events is not None else _read_org_events()
    if ci_probe is None:
        ci_probe = _default_ci_probe()

    targets: list[dict[str, Any]] = []
    targets += _act_targets(ledger_rows, journal_by_jid, monday_probe,
                            since, until, now_iso)
    targets += _gate_targets(packs, store, variants_dir, ci_probe,
                             since, until)
    targets += _graduation_targets(events, ledger_rows, store, since, until)

    counts = {
        "recorded": 0, "skipped_existing": 0, "skipped_purged": 0,
        "record_failures": 0, "unrecorded_store_unavailable": 0,
    }
    if record and targets:
        today8 = now_dt.strftime("%Y%m%d")
        scan_days = _window_days(since, now_dt)
        existing = _existing_claim_shas(store, scan_days)
        seg_state = {"segment": 0}
        for target in targets:
            _record_target(store, target, counts, existing, today8, seg_state)
    elif targets:
        for target in targets:
            target["recorded"] = False

    agree = sum(1 for t in targets if t["agreement"] == AGREE)
    disagree = sum(1 for t in targets if t["agreement"] == DISAGREE)
    underivable = sum(
        1 for t in targets if str(t["agreement"]).startswith(UNDERIVABLE))
    by_kind: dict[str, int] = {}
    for target in targets:
        by_kind[target["target"]] = by_kind.get(target["target"], 0) + 1

    summary = {
        "kind": "summary",
        "schema": SCHEMA,
        "ts": now_iso,
        "window": {"since": since, "until": until},
        "store": {"root": str(root) if root is not None else None,
                  "available": store.available},
        "targets_checked": len(targets),
        "agree": agree,
        "disagree": disagree,
        "underivable": underivable,
        "by_kind": by_kind,
        "recording": counts,
        "shadow": True,
        "honest_claim": HONEST_CLAIM,
    }
    for target in targets:
        target["kind"] = "target"
        target["schema"] = SCHEMA
        target["honest_claim"] = HONEST_CLAIM
    report = {
        "schema": SCHEMA,
        "ts": now_iso,
        "window": summary["window"],
        "store": summary["store"],
        "targets": targets,
        "summary": summary,
        "honest_claim": HONEST_CLAIM,
        "shadow": True,
    }
    report["weekly_line"] = weekly_line(report)
    summary["weekly_line"] = report["weekly_line"]
    return report


def weekly_line(report: dict[str, Any]) -> str:
    """The Captain's weekly-review line — COUNTS only, never rates; a
    disagree is INFORMATION for the review, never a gate input."""
    summary = report["summary"]
    return (
        "recompute: {c} checked ({a} agree, {d} disagree, {u} underivable; "
        "{r} recorded) [shadow — report-only] | claim: {claim}".format(
            c=summary["targets_checked"], a=summary["agree"],
            d=summary["disagree"], u=summary["underivable"],
            r=summary["recording"]["recorded"], claim=HONEST_CLAIM)
    )


# ---------------------------------------------------------------------------
# Report writing — OUTSIDE both planes, never anywhere the minter reads.
# ---------------------------------------------------------------------------

def _default_store_root() -> Path:
    from framework.onboarding.journey import EVIDENCE_REL
    return _repo_root() / EVIDENCE_REL


def _refuse_unsafe_out(out_path: Path, store_root: Path | None) -> None:
    resolved = out_path.resolve()
    fences: list[Path] = []
    if store_root is not None:
        fences.append(Path(store_root).resolve())
    else:
        try:
            fences.append(_default_store_root().resolve())
        except Exception:
            pass
    try:
        fences.append(_consequence_log_dir().resolve())
    except Exception:
        pass
    for fence in fences:
        if resolved == fence or fence in resolved.parents:
            raise ValueError(
                f"evidence-recompute report may never land inside {fence} — "
                "the store and the minter's ledger dir are one-way surfaces "
                "for this verifier")


def write_report(report: dict[str, Any], out_path: Path | str | None = None,
                 *, store_root: Path | str | None = None) -> Path:
    """Append the report as JSONL lines (targets, then summary) to a
    Captain-facing file outside both planes (house journal append
    semantics: 0600, O_NOFOLLOW, append-only)."""
    path = (Path(out_path) if out_path is not None
            else _repo_root().joinpath(*REPORT_REL))
    _refuse_unsafe_out(
        path, Path(store_root) if store_root is not None else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = report["targets"] + [report["summary"]]
    payload = "".join(
        json.dumps(line, ensure_ascii=False, sort_keys=True, default=str) + "\n"
        for line in lines)
    fd = os.open(str(path),
                 os.O_WRONLY | os.O_CREAT | os.O_APPEND
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    return path


# ---------------------------------------------------------------------------
# CLI — Captain/launchd context only (the officer hook screen blocks the
# 'framework.evidence' substring, so officers cannot be asked to run this).
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Exit codes carry NO verdict signal by design: 0 = measured
    (agreements, disagreements, or nothing), 2 = could not measure.
    Nothing downstream may key on them — the report file and the recorded
    events are the only output surfaces (shadow law)."""
    parser = argparse.ArgumentParser(
        prog="evidence_recompute",
        description="Report-only independent recompute legs (HP-2). "
                    f"Honest claim: {HONEST_CLAIM}")
    parser.add_argument("--store", default=None,
                        help="evidence store root (default: the repo store)")
    parser.add_argument("--out", default=None,
                        help="report JSONL (default: cabinet/logs/"
                             "evidence-recompute-report.jsonl)")
    parser.add_argument("--since", default=None,
                        help="ISO window start (default: now minus the "
                             "imported calibration freshness horizon)")
    parser.add_argument("--until", default=None, help="ISO window end")
    parser.add_argument("--gate-root", default=None,
                        help="repo root for gate pack files (tests)")
    parser.add_argument("--org-events", default=None,
                        help="org-event JSONL file override (tests)")
    parser.add_argument("--no-write", action="store_true",
                        help="print the summary only; write no report file")
    parser.add_argument("--no-record", action="store_true",
                        help="derive + report only; append no store events")
    args = parser.parse_args(argv)
    # §2.4 tamper response (evidence_freeze consumer contract — this module
    # joins the named Phase-4 shadow services): while the judging-freeze
    # marker is present at the repo root, refuse to run — one plain line,
    # exit 0, zero plane reads, zero writes. FAIL-CLOSED: a broken freeze
    # probe reads FROZEN. Clearing is Captain-only (tamper-drill runbook).
    try:
        frozen = evidence_freeze.is_frozen(_repo_root())
    except Exception:  # noqa: BLE001 — broken probe reads frozen
        frozen = True
    if frozen:
        print("evidence-recompute: frozen — refusing to run (%s)"
              % evidence_freeze.marker_path(_repo_root()))
        return 0
    # Producer identity fixed at process start from constants (never argv
    # payloads, never env). Skipped under pytest: attestation is
    # process-global and a suite process must never inherit this CLI's
    # identity (the same fence class as the store resolver above).
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            identity.attest_process_identity(
                "system", "evidence-recompute", "evidence-recompute")
        except EvidenceError:
            pass  # embedded in an already-attested process — keep its identity
    try:
        org_events = None
        if args.org_events:
            org_events = [
                row for row in
                (json.loads(line) for line in
                 Path(args.org_events).read_text(encoding="utf-8").splitlines()
                 if line.strip())
                if isinstance(row, dict)
            ]
        report = check_recompute(
            store_root=args.store, since=args.since, until=args.until,
            gate_root=args.gate_root, org_events=org_events,
            record=not args.no_record)
        if not args.no_write:
            write_report(report, args.out, store_root=args.store)
        print(report["weekly_line"])
        return 0
    except Exception as exc:  # measurement error — never a fabricated report
        print(f"evidence-recompute: measurement error: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
