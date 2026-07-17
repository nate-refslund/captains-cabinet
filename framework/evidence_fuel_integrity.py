"""Phase-4 fuel-integrity check — REPORT-ONLY shadow detector (detect, never act).

THE HONEST CLAIM (design of record 2026-07-16 §3 Phase 4 item 2; mandatory
in this docstring, in every report line, and in the runbook): this check
detects retroactive single-plane tamper and INCONSISTENT forgery only;
consistent same-user forgery of both planes (the same OS user writes the
consequence ledger and the evidence store, and the store signing key is
same-user-readable) stays open until HP-1 (OS-user/key isolation) lands —
necessary, not sufficient.

WHAT IT DOES: out-of-band, it re-derives — for every consequence-ledger row
that would mint graduation promotion fuel (``review.verdict == "confirmed"``
with ``review.source == "verdict_human"``; the compute_ratios contract) —
whether the six Phase-4 preconditions hold, and writes a Captain-facing
report. The six signals, per fuel-bearing row / cell:

  1. verified recorder mirror   — a consequence-mirror receipt exists in the
     evidence store's day-trial class and the trial verifies green;
  2. consequence<->evidence consistency — the receipt's ``row_sha256`` equals
     the sha recomputed over the SURVIVING (last-write-wins) ledger row;
  3. third-leg presence (A5/HP-2) — a Captain label event
     (``governance_review_label`` / ``verdict_human``) re-counted against the
     off-store governance-labels journal digests (B1: externally anchored
     digests, never in-store rows alone; unanchored labels are advisory and
     satisfy nothing — HP-3), or an independent recomputation. The machine
     ttl-survival marker is reported as producer-adjacent, which per A5 is
     NOT corroboration (two same-hand planes agreeing proves nothing);
  4. broker-attested actor (A6) — ``attestation_mode == "process"`` on the
     receipt; process attestation is same-user-DECLARED (identity.py R2
     caveat) and is reported as such, never as broker attestation;
  5. no purge-overlap (A7) — the row's fuel window does not overlap a purged
     day trial (reduced-confidence => would-withhold, design §2.4);
  6. per-cell intent->outcome closure floor and unknown-rate ceiling
     (B2/B10) — floors reuse judge_calibration's JUDGE_HARD_BAR / MIN_PAIRS
     (R-8/R-11: never a second number; the unknown ceiling is the derived
     complement ``1 - JUDGE_HARD_BAR``, not a new constant).

SHADOW LAW (Phase 4): every output is a report. This module NEVER blocks
minting, never gates, never scores, and nothing downstream may consume its
output to act — the enforce flip in front of compute_ratios/evaluate is a
LATER Captain-only narrowing (posture asymmetry, design §2.6), not here.
Structurally enforced:

* READ-ONLY toward both planes. Ledger reads ride
  ``framework.fidelity.consequence.read_ledger`` (the minter's own read
  path, symlink-fenced, sim-quarantined); store reads ride the public
  ``EvidenceRecorder.read_events`` API (verification-gated). The signed
  anti-rollback watermark advancing on a trial's FIRST verify is the one
  sanctioned store byte change (identical to the existing verify verb).
  This module never appends evidence, never emits org events, never emits
  consequence rows, never opens ``.signing-key``, and never constructs a
  recorder over an absent store (construction would create scaffolding).
* Report files live OUTSIDE the store: default
  ``cabinet/logs/fuel-integrity-report.jsonl`` (gitignored runtime,
  Captain-facing; the evidence-mirror-degradations.jsonl precedent).
  ``write_report`` REFUSES an output path inside the store or inside the
  consequence-ledger dir, so the checker can never write anything the
  minter reads.
* Never-a-score: per-cell rates are Captain-facing report content only —
  never officer-projected, never org events, never the attention feed.
  The weekly line carries COUNTS, not rates. This module's name contains
  the ``framework.evidence`` substring, so the officer hook screen makes
  its CLI unreachable from officer context by construction.
* Exit codes carry no verdict signal (0 = measured, findings or not;
  2 = could not measure). Nothing may key a gate on this process.

WEAK-SIGNAL / TRIAGE LAW (signal_discriminator polarity, verbatim): a
finding is NOISE only with affirmative evidence — a missing mirror receipt
explained by a matching consequence-chokepoint row in the degradation
ledger is ``unknown`` (pass-through), never tamper; "tamper-shaped" is
claimed only for affirmative inconsistencies (verification failure, sha
mismatch, claimed trial missing without a purge receipt). Absence alone
never renders tamper.

VERDICT VOCABULARY per fuel row:
  ``grounded``               — all six preconditions affirmatively pass;
  ``ungrounded:<reason>``    — a precondition affirmatively FAILS
                               (tamper-shaped or invariant-violating);
  ``unknown:<reason>``       — insufficiency/absence; passes through.
``would_withhold`` is true for anything not grounded — the fail-closed
HP-2 posture a future enforce flip would take — and in this batch it is
information only.

Sibling-module precedent: framework/evidence_anchor.py and
framework/evidence_mirror.py (top-level framework/ observers OUTSIDE the
schg-locked framework/evidence package). python3.12 only (the evidence
package needs 3.11+); nothing imports this module — grep-provable shadow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from framework import evidence_freeze  # §2.4 judging-freeze respect (stdlib-only)
from framework import evidence_mirror
from framework.evidence import EvidenceError, EvidenceRecorder
from framework.fidelity.consequence import (
    UNSTAMPED_ACTION_TYPE,
    _consequence_log_dir,  # judge_calibration precedent: the ONE env rule
    read_ledger,
)
# R-8/R-11: the floor constants are IMPORTED, never redefined, never flags.
from framework.fidelity.judge_calibration import (
    JUDGE_HARD_BAR,
    MIN_PAIRS,
    STATUS_MAX_AGE_DAYS,
)

SCHEMA = "cabinet.fuel-integrity-report/v1"

#: Mandatory text on every report line (see module docstring).
HONEST_CLAIM = (
    "detects retroactive single-plane tamper and INCONSISTENT forgery only; "
    "consistent same-user forgery of both planes (same OS user writes the "
    "consequence ledger and the evidence store, signing key same-user-"
    "readable) stays open until HP-1 (OS-user/key isolation) lands — "
    "necessary, not sufficient"
)

#: Derived complement of the imported bar — deliberately NOT a second
#: constant (R-11): the closure floor and the unknown ceiling move together.
UNKNOWN_RATE_CEILING = 1.0 - JUDGE_HARD_BAR

#: Promotion fuel per compute_ratios: verdict_human always; verdict_gate is
#: structurally inert today (see gate-fuel note in check_fuel_integrity).
FUEL_SOURCE = "verdict_human"
GATE_SOURCE = "verdict_gate"
_SCOREABLE = ("confirmed", "wrong")  # judge_calibration._SCOREABLE polarity

#: Phase-4 join contract (governance-review.py module docstring, pinned by
#: cabinet/scripts/tests/test_evidence_label_join.py).
LABEL_ACTION = "governance_review_label"
LABEL_SOURCE = "verdict_human"
LABEL_DIGEST_SCHEMA = "cabinet.governance-label-digest/v1"

#: The ttl-survival outcome-evidence prefix (documented copy of gate.py
#: _TTL_OK_MARKER / binder_wire _ACTED_VERDICTS["ttl_ok"] — the same
#: documented-copy pattern gate.py itself uses).
TTL_OK_MARKER = "ttl-48h survived"

#: Report + journal homes (repo-relative). cabinet/logs/* is gitignored
#: (runtime, Captain-facing); the labels journal path mirrors
#: governance-review.py LABELS_JOURNAL_REL.
REPORT_REL = ("cabinet", "logs", "fuel-integrity-report.jsonl")
LABELS_JOURNAL_REL = ("shared", "interfaces", "governance-labels.jsonl")

_UNDO_REF_PREFIX = "undo-journal:"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _day8(ts: str) -> str | None:
    """yyyymmdd of an ISO ts, or None when underivable (never guessed)."""
    day = (ts or "")[:10].replace("-", "")
    if len(day) == 8 and day.isdigit():
        return day
    return None


def _adjacent_days(day8: str) -> list[str]:
    """day-1, day, day+1 — receipts can land across a UTC midnight and
    superseding enrichment lands on its own wall-clock day."""
    try:
        base = datetime.strptime(day8, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return [day8]
    return [(base + timedelta(days=delta)).strftime("%Y%m%d")
            for delta in (-1, 0, 1)]


def _consequence_day_trials(day8: str) -> list[str]:
    """Every consequence day-trial id for one day (base + chain segments) —
    naming reused from the mirror (the join's single source of truth)."""
    return [
        evidence_mirror._trial_id(
            evidence_mirror.CONSEQUENCE_TRIAL_CLASS, segment, day8)
        for segment in range(evidence_mirror.MAX_CHAIN_SEGMENTS)
    ]


def _row_sha256(row: dict[str, Any]) -> str:
    """The documented canonical join recipe — reused from the mirror so the
    two sides can never drift (judge_calibration's import-the-private
    precedent)."""
    return evidence_mirror._canonical_sha256(row)


def _row_refs(row: dict[str, Any]) -> list[str]:
    refs = row.get("refs")
    return [r for r in refs if isinstance(r, str)] if isinstance(refs, list) else []


def _mirror_ref_trials(row: dict[str, Any]) -> list[str]:
    """The trials this row CLAIMS were mirrored (chokepoint-appended refs);
    the last one is the claim for the surviving write."""
    prefix = evidence_mirror.CONSEQUENCE_REF_PREFIX
    seen: list[str] = []
    for ref in _row_refs(row):
        if ref.startswith(prefix):
            trial_id = ref[len(prefix):]
            if trial_id and trial_id not in seen:
                seen.append(trial_id)
    return seen


def _row_jids(row: dict[str, Any]) -> list[str]:
    return [ref[len(_UNDO_REF_PREFIX):] for ref in _row_refs(row)
            if ref.startswith(_UNDO_REF_PREFIX) and len(ref) > len(_UNDO_REF_PREFIX)]


# ---------------------------------------------------------------------------
# Store access — public read API only, never constructs over an absent store.
# ---------------------------------------------------------------------------

class _StoreReader:
    """Cached, fail-soft read_events wrapper.

    States: ``("ok", events)`` | ``("missing", None)`` | ``("purged", None)``
    | ``("integrity_failed", code)`` | ``("error", code)`` |
    ``("unavailable", None)``.  A recorder is constructed ONLY over a store
    that already exists (``control.json`` present): ``EvidenceRecorder``
    creates scaffolding on construction, and a read-only checker must never
    create a store.
    """

    def __init__(self, store_root: Path | None):
        self.root = Path(store_root) if store_root is not None else None
        self.available = bool(
            self.root is not None and (self.root / "control.json").is_file())
        self._recorder: EvidenceRecorder | None = None
        self._cache: dict[str, tuple[str, Any]] = {}

    def _rec(self) -> EvidenceRecorder:
        if self._recorder is None:
            self._recorder = EvidenceRecorder(self.root)
        return self._recorder

    def _purge_receipt_named(self, trial_id: str) -> bool:
        """Purge-receipt presence by NAME (the check_anchor rule): receipt
        files are ``purge-<sha256(trial_id)[:16]>-*.json``.  Name-presence
        only — signature validity is the verifier's job, and a same-user
        forger can plant one; that residual is exactly the HP-1 caveat in
        HONEST_CLAIM."""
        if self.root is None:
            return False
        digest = hashlib.sha256(trial_id.encode("utf-8")).hexdigest()[:16]
        try:
            return any((self.root / "purge-receipts").glob(
                f"purge-{digest}-*.json"))
        except OSError:
            return False

    def state(self, trial_id: str) -> tuple[str, Any]:
        if not self.available:
            return ("unavailable", None)
        if trial_id in self._cache:
            return self._cache[trial_id]
        try:
            events = self._rec().read_events(trial_id)
            result: tuple[str, Any] = ("ok", events)
        except EvidenceError as exc:
            code = str(getattr(exc, "code", "") or "evidence_error")
            if code == "trial_purged":
                result = ("purged", None)
            elif code == "trial_not_found":
                result = ("purged", None) if self._purge_receipt_named(trial_id) \
                    else ("missing", None)
            elif code == "ledger_integrity":
                result = ("integrity_failed", code)
            else:
                result = ("error", code)
        except Exception as exc:  # defensive: measurement, never a crash
            result = ("error", type(exc).__name__)
        self._cache[trial_id] = result
        return result


def _receipt_index(reader: _StoreReader,
                   trial_ids: list[str]) -> dict[str, dict[str, Any]]:
    """row_sha256 -> consequence-mirror receipt metadata across day trials.

    Older receipts matching superseded row versions are normal; the caller
    looks up the SURVIVING row's sha only."""
    index: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        state, events = reader.state(trial_id)
        if state != "ok":
            continue
        for event in events:
            detail = event.get("detail")
            if not isinstance(detail, dict):
                continue
            if detail.get("action") != "consequence_mirror":
                continue
            sha = detail.get("row_sha256")
            if not isinstance(sha, str) or not sha:
                continue
            index.setdefault(sha, {
                "trial_id": trial_id,
                "event_id": event.get("event_id"),
                "attestation": detail.get("attestation_mode") or "unattested",
            })
    return index


# ---------------------------------------------------------------------------
# Third leg — Captain labels re-counted against the off-store journal (B1).
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not Path(path).is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


def _is_captain_label(event: dict[str, Any]) -> bool:
    detail = event.get("detail")
    actor = event.get("actor")
    return (
        isinstance(detail, dict)
        and isinstance(actor, dict)
        and actor.get("kind") == "captain"
        and detail.get("action") == LABEL_ACTION
        and detail.get("source") == LABEL_SOURCE
        and detail.get("result_code") in _SCOREABLE
    )


def _label_index(reader: _StoreReader,
                 journal_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Anchored Captain labels: a label counts ONLY when its journal digest
    row exists (off-store, daily-anchored — the B1 re-count source) AND the
    named trial verifies AND the digest's event_id is present on the trial.
    In-store label events with no journal digest are advisory-only (HP-3)."""
    by_jid: dict[str, list[dict[str, Any]]] = {}
    by_trial: dict[str, list[dict[str, Any]]] = {}
    for row in journal_rows:
        if row.get("schema") != LABEL_DIGEST_SCHEMA:
            continue
        if row.get("verdict") not in _SCOREABLE:
            continue  # unclear: recorded, never scoreable
        trial_id = row.get("trial_id")
        if not isinstance(trial_id, str) or not trial_id:
            continue
        digest_ids = {i for i in (row.get("event_ids") or []) if isinstance(i, str)}
        state, events = reader.state(trial_id)
        if state != "ok":
            continue  # unverifiable ground truth counts for nothing
        for event in events:
            if event.get("event_id") not in digest_ids:
                continue
            if not _is_captain_label(event):
                continue
            detail = event["detail"]
            entry = {
                "trial_id": trial_id,
                "jid": detail.get("jid"),
                "result_code": detail.get("result_code"),
            }
            by_trial.setdefault(trial_id, []).append(entry)
            jid = detail.get("jid")
            if isinstance(jid, str) and jid:
                by_jid.setdefault(jid, []).append(entry)
    return {"by_jid": by_jid, "by_trial": by_trial}


def _has_unanchored_label(events: list[dict[str, Any]] | None) -> bool:
    return any(_is_captain_label(e) for e in events or [])


# ---------------------------------------------------------------------------
# Degradation triage — NOISE only with affirmative evidence.
# ---------------------------------------------------------------------------

def _degradation_explains(degradations: list[dict[str, Any]],
                          row_ts: str) -> str | None:
    """An affirmative consequence-chokepoint degradation row within one day
    of the ledger row's ts explains a missing receipt (the mirror degrades
    LOUD and is 900s rate-limited, so one row can explain many rows in its
    window).  Returns the reason, else None => the absence is unexplained."""
    row_day = _day8(row_ts)
    if row_day is None:
        return None
    window = set(_adjacent_days(row_day))
    for row in degradations:
        if row.get("chokepoint") != "consequence":
            continue
        marker_day = _day8(str(row.get("ts") or ""))
        if marker_day in window:
            return str(row.get("reason") or "degraded")
    return None


# ---------------------------------------------------------------------------
# Cell math — signal 6 (B2/B10), floors from the imported constants only.
# ---------------------------------------------------------------------------

def _cell_key(row: dict[str, Any]) -> tuple[str, Any, str]:
    actor = row.get("actor") or {}
    actor_id = f"{actor.get('kind')}:{actor.get('id')}"
    action_type = row.get("action_type") or UNSTAMPED_ACTION_TYPE
    return (actor_id, row.get("lane"), action_type)


def _risk_strata(action_types: set[str]) -> dict[str, str]:
    """action_type -> matrix risk_class (graduation._risk_class_of pattern,
    re-derived read-only from the authority matrix; germline gets no edits).
    Annotation only — strata never change a verdict in this batch."""
    strata = {at: "unmapped" for at in action_types}
    if UNSTAMPED_ACTION_TYPE in strata:
        strata[UNSTAMPED_ACTION_TYPE] = "unstamped"
    try:
        from framework.authority.matrix import load_matrix, matrix_policy
        policy = matrix_policy(load_matrix())
        for risk_class, spec in (policy.get("risk_classes") or {}).items():
            for at in (spec.get("action_types") or []):
                if at in strata:
                    strata[at] = str(risk_class)
    except Exception:
        return {at: "unresolved" for at in action_types}
    return strata


def _compute_cells(rows: list[dict[str, Any]]) -> dict[tuple, dict[str, Any]]:
    cells: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        cell = cells.setdefault(_cell_key(row), {
            "n": 0, "intents": 0, "closed": 0, "unknown_rows": 0})
        cell["n"] += 1
        proposal_present = isinstance(row.get("proposal"), dict)
        outcome_status = (row.get("outcome") or {}).get("status")
        review_verdict = (row.get("review") or {}).get("verdict")
        if proposal_present:
            cell["intents"] += 1
            if outcome_status in ("ok", "failed"):
                cell["closed"] += 1
        if outcome_status == "unknown" or review_verdict == "unknown":
            cell["unknown_rows"] += 1

    strata = _risk_strata({key[2] for key in cells})
    for key, cell in cells.items():
        cell["stratum"] = strata.get(key[2], "unmapped")
        cell["closure_rate"] = (
            cell["closed"] / cell["intents"] if cell["intents"] else None)
        cell["unknown_rate"] = (
            cell["unknown_rows"] / cell["n"] if cell["n"] else None)
        if cell["n"] < MIN_PAIRS:
            # Below the imported minimum the measurement is not evidence —
            # 'insufficient', never a verdict (R-8/R-11).
            cell["floors"] = "insufficient"
        elif (cell["closure_rate"] is not None
              and cell["closure_rate"] < JUDGE_HARD_BAR):
            cell["floors"] = "fail:closure_below_floor"
        elif (cell["unknown_rate"] is not None
              and cell["unknown_rate"] > UNKNOWN_RATE_CEILING):
            cell["floors"] = "fail:unknown_rate_above_ceiling"
        else:
            # A cell with zero recorded intents has nothing dangling — the
            # closure floor is vacuously met (visible via closure_rate=None).
            cell["floors"] = "pass"
    return cells


# ---------------------------------------------------------------------------
# Per-row evaluation — the six-precondition ladder (design order).
# ---------------------------------------------------------------------------

def _evaluate_row(row: dict[str, Any], *, reader: _StoreReader,
                  receipts: dict[str, dict[str, Any]],
                  labels: dict[str, Any],
                  degradations: list[dict[str, Any]],
                  cells: dict[tuple, dict[str, Any]]) -> dict[str, Any]:
    signals: dict[str, Any] = {
        "mirror": None, "row_sha_match": None, "third_leg": None,
        "attestation": None, "purge_overlap": False, "cell_floors": None,
    }
    tamper_shaped = False
    verdict: str | None = None
    claimed = _mirror_ref_trials(row)
    last_claimed = claimed[-1] if claimed else None

    # -- signals 1+2+5: mirror presence, consistency, purge-overlap --------
    if not reader.available:
        signals["mirror"] = "inconclusive:store_unavailable"
        verdict = "unknown:store_unavailable"
    elif last_claimed is None:
        reason = _degradation_explains(degradations, str(row.get("ts") or ""))
        if reason:
            signals["mirror"] = f"inconclusive:mirror_degraded:{reason}"
            verdict = "unknown:mirror_degraded"
        else:
            # Affirmative invariant violation, NOT a tamper claim: the
            # chokepoint gives every live lifecycle row a mirror ref or a
            # loud degradation row; this row has neither.
            signals["mirror"] = "fail:unmirrored"
            verdict = "ungrounded:unmirrored_row"
    else:
        state, _events = reader.state(last_claimed)
        if state == "integrity_failed":
            signals["mirror"] = "fail:verify_failed"
            tamper_shaped = True
            verdict = "ungrounded:verify_failed"
        elif state == "purged":
            signals["mirror"] = "inconclusive:trial_purged"
            signals["purge_overlap"] = True
            # sanctioned purge, not tamper — but §2.4: overlapping fuel
            # windows are reduced-confidence => withhold widened.
            verdict = "ungrounded:purge_overlap"
        elif state == "missing":
            signals["mirror"] = "fail:trial_missing"
            tamper_shaped = True
            verdict = "ungrounded:trial_missing"
        elif state == "error":
            signals["mirror"] = f"inconclusive:store_error:{_events}"
            verdict = "unknown:store_error"
        else:  # ok — look the surviving row's sha up across the day class
            sha = _row_sha256(row)
            receipt = receipts.get(sha)
            if receipt is not None:
                signals["mirror"] = "pass"
                signals["row_sha_match"] = True
                signals["attestation"] = receipt["attestation"]
                signals["receipt_trial"] = receipt["trial_id"]
            else:
                signals["row_sha_match"] = False
                reason = _degradation_explains(
                    degradations, str(row.get("ts") or ""))
                if reason:
                    signals["mirror"] = f"inconclusive:mirror_degraded:{reason}"
                    verdict = "unknown:mirror_degraded"
                else:
                    # The row claims it was mirrored (ref present, trial
                    # verifies) yet no receipt matches its bytes: the row
                    # was edited after mirroring or the receipt is gone —
                    # the INCONSISTENT forgery this check exists to catch.
                    signals["mirror"] = "fail:row_sha_mismatch"
                    tamper_shaped = True
                    verdict = "ungrounded:row_sha_mismatch"

    # -- signal 3: third leg ------------------------------------------------
    if verdict is None:
        jids = _row_jids(row)
        anchored_by_jid = any(jid in labels["by_jid"] for jid in jids)
        anchored_on_trial = bool(
            last_claimed and labels["by_trial"].get(last_claimed))
        if anchored_by_jid:
            signals["third_leg"] = "human_label_row"
        elif anchored_on_trial:
            signals["third_leg"] = "human_label_trial"
        else:
            trial_events = None
            if last_claimed is not None:
                state, trial_events = reader.state(last_claimed)
                if state != "ok":
                    trial_events = None
            evidence_text = str((row.get("outcome") or {}).get("evidence") or "")
            if _has_unanchored_label(trial_events):
                # in-store only, no journal digest: advisory, mints nothing
                # (HP-3) — and same-user in-store labels are spoofable.
                signals["third_leg"] = "human_label_unanchored"
                verdict = "unknown:third_leg_unanchored"
            elif evidence_text.startswith(TTL_OK_MARKER):
                # machine leg exists but is producer-adjacent (A5: two
                # same-hand planes are not corroboration) — reported, and
                # in this batch never sufficient.
                signals["third_leg"] = "machine_probe_producer_adjacent"
                verdict = "unknown:third_leg_producer_adjacent"
            else:
                signals["third_leg"] = "absent"
                verdict = "unknown:third_leg_absent"

    # -- signal 4: attestation ----------------------------------------------
    if verdict is None:
        if signals.get("attestation") != "process":
            signals["attestation"] = signals.get("attestation") or "unattested"
            # honest today: consequence-mirror receipts do not attest yet
            # (evidence_mirror.py: "attestation for daemon producers is a
            # separate ceremony wave") — absence is insufficiency, not fail.
            verdict = "unknown:attestation_absent"

    # -- signal 6: cell floors ----------------------------------------------
    cell = cells.get(_cell_key(row)) or {}
    signals["cell_floors"] = cell.get("floors")
    if verdict is None:
        floors = cell.get("floors")
        if floors == "insufficient":
            verdict = "unknown:cell_insufficient_pairs"
        elif floors == "fail:closure_below_floor":
            verdict = "ungrounded:cell_closure_below_floor"
        elif floors == "fail:unknown_rate_above_ceiling":
            verdict = "ungrounded:cell_unknown_rate_above_ceiling"

    if verdict is None:
        verdict = "grounded"

    actor = row.get("actor") or {}
    return {
        "kind": "row",
        "schema": SCHEMA,
        "ts": row.get("ts"),
        "actor": f"{actor.get('kind')}:{actor.get('id')}",
        "lane": row.get("lane"),
        "action_type": row.get("action_type") or UNSTAMPED_ACTION_TYPE,
        "subject": str(row.get("subject") or "")[:120],
        "fuel_source": (row.get("review") or {}).get("source"),
        "verdict": verdict,
        "would_withhold": verdict != "grounded",
        "tamper_shaped": tamper_shaped,
        "signals": signals,
        "honest_claim": HONEST_CLAIM,
    }


# ---------------------------------------------------------------------------
# The check — orchestration (read → derive → report; nothing else).
# ---------------------------------------------------------------------------

def _default_store_root() -> Path:
    """repo_root/EVIDENCE_REL via the ONE canonical constant (lazy: journey
    is heavy and tests always pass an explicit scratch root)."""
    from framework.onboarding.journey import EVIDENCE_REL
    return _repo_root() / EVIDENCE_REL


def check_fuel_integrity(
    *,
    store_root: Path | str | None = None,
    since: str | None = None,
    until: str | None = None,
    ledger: list[dict[str, Any]] | None = None,
    labels_journal: Path | str | None = None,
    degradations_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run the six-precondition shadow check and return the report dict.

    Read-only toward both planes; the sole store side effect is the
    sanctioned first-verify watermark advance.  ``ledger`` overrides the
    read_ledger() input for composition/tests; window bounds are inclusive
    ISO strings compared lexicographically (the ledger's own convention).
    """
    now = _utc_now()
    if since is None:
        # Reuse of the ONE freshness horizon (STATUS_MAX_AGE_DAYS) — the
        # report covers the window a calibration proof lives, no new number.
        since = _iso(now - timedelta(days=STATUS_MAX_AGE_DAYS))
    root = Path(store_root) if store_root is not None else _default_store_root()
    reader = _StoreReader(root)

    rows = ledger if ledger is not None else read_ledger(since=since)
    rows = [r for r in rows if str(r.get("ts") or "") >= since]
    if until is not None:
        rows = [r for r in rows if str(r.get("ts") or "") <= until]

    cells = _compute_cells(rows)

    fuel_rows: list[dict[str, Any]] = []
    gate_confirmed = 0
    for row in rows:
        review = row.get("review") or {}
        if review.get("verdict") != "confirmed":
            continue
        source = review.get("source")
        if source == FUEL_SOURCE:
            fuel_rows.append(row)
        elif source == GATE_SOURCE:
            gate_confirmed += 1

    # Candidate day trials: every claimed mirror trial + the ts-day class
    # ±1 day with all chain segments (midnight skew + cap chaining).
    candidate_trials: list[str] = []
    for row in fuel_rows:
        for trial_id in _mirror_ref_trials(row):
            if trial_id not in candidate_trials:
                candidate_trials.append(trial_id)
        day = _day8(str(row.get("ts") or ""))
        if day:
            for adjacent in _adjacent_days(day):
                for trial_id in _consequence_day_trials(adjacent):
                    if trial_id not in candidate_trials:
                        candidate_trials.append(trial_id)

    receipts = _receipt_index(reader, candidate_trials)
    journal_path = (Path(labels_journal) if labels_journal is not None
                    else _repo_root().joinpath(*LABELS_JOURNAL_REL))
    labels = _label_index(reader, _load_jsonl(journal_path))
    marker_path = (Path(degradations_path) if degradations_path is not None
                   else _repo_root().joinpath(*evidence_mirror._MARKER_REL))
    degradations = _load_jsonl(marker_path)

    row_reports = [
        _evaluate_row(row, reader=reader, receipts=receipts, labels=labels,
                      degradations=degradations, cells=cells)
        for row in fuel_rows
    ]

    fuel_cells = {_cell_key(row) for row in fuel_rows}
    cell_reports = []
    for key in sorted(fuel_cells, key=lambda k: (k[0], str(k[1]), k[2])):
        cell = cells[key]
        cell_reports.append({
            "kind": "cell",
            "schema": SCHEMA,
            "cell": [key[0], key[1], key[2]],
            "stratum": cell["stratum"],
            "n": cell["n"],
            "intents": cell["intents"],
            "closed": cell["closed"],
            "closure_rate": cell["closure_rate"],
            "unknown_rows": cell["unknown_rows"],
            "unknown_rate": cell["unknown_rate"],
            "floors": cell["floors"],
            "honest_claim": HONEST_CLAIM,
        })

    grounded = sum(1 for r in row_reports if r["verdict"] == "grounded")
    ungrounded = sum(
        1 for r in row_reports if r["verdict"].startswith("ungrounded"))
    inconclusive = sum(
        1 for r in row_reports if r["verdict"].startswith("unknown"))
    summary = {
        "kind": "summary",
        "schema": SCHEMA,
        "ts": _iso(now),
        "window": {"since": since, "until": until},
        "store": {"root": str(root), "available": reader.available},
        "fuel_rows_checked": len(row_reports),
        "grounded": grounded,
        "ungrounded": ungrounded,
        "inconclusive": inconclusive,
        "would_withhold": len(row_reports) - grounded,
        "cells_checked": len(cell_reports),
        # Baseline honesty (CG-1 Option B): verdict_gate fuel is structurally
        # ZERO today — consequence._label_floor_met is hardwired False (the
        # A3 sensor is absent), so no gate confirm can mint regardless of
        # posture.  Report the count, fabricate no gate-fuel violations.
        # Revisit the 'minted' derivation if/when A3 lands and widens it.
        "gate_fuel": {
            "confirmed_rows": gate_confirmed,
            "minted": 0,
            "note": "structurally zero: label floor (A3) absent — CG-1",
        },
        "shadow": True,
        "honest_claim": HONEST_CLAIM,
    }
    report = {
        "schema": SCHEMA,
        "ts": summary["ts"],
        "window": summary["window"],
        "store": summary["store"],
        "rows": row_reports,
        "cells": cell_reports,
        "summary": summary,
        "honest_claim": HONEST_CLAIM,
        "shadow": True,
    }
    report["weekly_line"] = weekly_line(report)
    summary["weekly_line"] = report["weekly_line"]
    return report


def weekly_line(report: dict[str, Any]) -> str:
    """The Captain's weekly-review line — COUNTS only, never rates, shadow
    labeled, honest-claim footnote (never-a-score: Captain-facing only)."""
    summary = report["summary"]
    return (
        "graduations grounded: {g}/{m} verified "
        "({u} ungrounded, {k} inconclusive; would-withhold {w}) "
        "[shadow — report-only] | claim: {claim}".format(
            g=summary["grounded"], m=summary["fuel_rows_checked"],
            u=summary["ungrounded"], k=summary["inconclusive"],
            w=summary["would_withhold"], claim=HONEST_CLAIM)
    )


# ---------------------------------------------------------------------------
# Report writing — OUTSIDE the store, never anywhere the minter reads.
# ---------------------------------------------------------------------------

def _refuse_unsafe_out(out_path: Path, store_root: Path | None) -> None:
    resolved = out_path.resolve()
    fences: list[Path] = []
    if store_root is not None:
        fences.append(Path(store_root).resolve())
    else:
        # Default-store runs reach here with store_root=None (main() threads
        # args.store verbatim): fence the SAME default root the check read,
        # or an '--out' aimed inside the default store would be accepted —
        # turning the 'never write anything the minter reads' guarantee into
        # a docstring.  Best-effort: an unresolvable default (hermetic env)
        # leaves the ledger-dir fence in force.
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
                f"fuel-integrity report may never land inside {fence} — "
                "the store and the minter's ledger dir are read-only "
                "surfaces for this checker")


def write_report(report: dict[str, Any], out_path: Path | str | None = None,
                 *, store_root: Path | str | None = None) -> Path:
    """Append the report as JSONL lines (rows, cells, summary) to a
    Captain-facing file outside both planes (house journal append
    semantics: 0600, O_NOFOLLOW, append-only)."""
    path = (Path(out_path) if out_path is not None
            else _repo_root().joinpath(*REPORT_REL))
    _refuse_unsafe_out(
        path, Path(store_root) if store_root is not None else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = report["rows"] + report["cells"] + [report["summary"]]
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
    """Exit codes carry NO verdict signal by design: 0 = measured (findings
    or not), 2 = could not measure.  Nothing downstream may key on them —
    the report file is the only output surface (shadow law).
    No bar/min-pairs/floor argv overrides exist: floors are imported code
    constants (a bar loosenable from argv is not a bar)."""
    parser = argparse.ArgumentParser(
        prog="evidence_fuel_integrity",
        description="Report-only fuel-integrity shadow check (Phase 4). "
                    f"Honest claim: {HONEST_CLAIM}")
    parser.add_argument("--store", default=None,
                        help="evidence store root (default: the repo store)")
    parser.add_argument("--out", default=None,
                        help="report JSONL (default: cabinet/logs/"
                             "fuel-integrity-report.jsonl)")
    parser.add_argument("--since", default=None,
                        help="ISO window start (default: now minus the "
                             "imported calibration freshness horizon)")
    parser.add_argument("--until", default=None, help="ISO window end")
    parser.add_argument("--labels-journal", default=None,
                        help="governance-labels journal path override")
    parser.add_argument("--degradations", default=None,
                        help="evidence-mirror degradation ledger override")
    parser.add_argument("--no-write", action="store_true",
                        help="print the summary only; write nothing")
    args = parser.parse_args(argv)
    # §2.4 tamper response (evidence_freeze consumer contract — this module
    # is one of the three named Phase-4 shadow services): while the
    # judging-freeze marker is present at the repo root, refuse to run —
    # one plain line, exit 0, zero plane reads, zero report writes.
    # FAIL-CLOSED: a broken freeze probe reads FROZEN. Clearing is
    # Captain-only per docs/runbooks/tamper-drill.md.
    try:
        frozen = evidence_freeze.is_frozen(_repo_root())
    except Exception:  # noqa: BLE001 — broken probe reads frozen
        frozen = True
    if frozen:
        print("evidence-fuel-integrity: frozen — refusing to run (%s)"
              % evidence_freeze.marker_path(_repo_root()))
        return 0
    try:
        report = check_fuel_integrity(
            store_root=args.store, since=args.since, until=args.until,
            labels_journal=args.labels_journal,
            degradations_path=args.degradations)
        if not args.no_write:
            write_report(report, args.out, store_root=args.store)
        print(report["weekly_line"])
        return 0
    except Exception as exc:  # measurement error — never a fabricated report
        print(f"fuel-integrity: measurement error: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
