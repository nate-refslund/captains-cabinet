"""UNDO-3 — TTL-survival sweep + silent-revert detection + journal GC.

The hourly reconciler of the trust-inversion undo plane (grand-plan §3 W2·L2,
impl-plan §2.2). SCHEDULED since 2026-07-04: the ``com.cabinet.undo-sweep``
LaunchAgent (hand-made plist, loaded per cabinet/launchd/INSTALL-flip.md) runs
run-undo-sweep.sh hourly, and the ``undo-sweep`` row in ``cabinet/services.yml``
puts it under the outcome-watchdog's manifest-derived no-silent-cron floor
(lane-ops 2026-07-04).

It reads the write-ahead undo journal (``action_undo``) and, for every acted
step past its 48h TTL whose CURRENT acted ledger record is still
``outcome=unknown``, emits the estate's FIRST MACHINE OUTCOME LABELS through the
ONE shared ``binder_wire.acted_verdict_event`` builder — so a TTL event can never
erase a landed human 👍 (the same read-modify-write, field-preserving supersede):

  - artifact intact past 48h  -> ``outcome=ok`` + evidence, review UNTOUCHED
    (there is NO 'held' enum — ok + evidence IS held; the schema stays
    ``{ok, failed, unknown}``). This is where graduation's Gate-2 clock starts.
  - artifact gone without a Captain undo -> ``outcome=failed`` + ``review=wrong``,
    ``source=verdict_judge`` — UNLESS the Monday activity log attributes the
    delete to the Captain's user id, then ``verdict_human`` (his hand is his verdict).

Idempotency AND the ordering guarantee come from ONE gate: only rows whose
current ledger record is still ``outcome=unknown`` are reconciled. A human
confirm/undo already moved the cell to ok/failed, so the sweep skips it and can
never double-emit or overwrite a human verdict.

Rows stamped ``canary: true`` (the guard's own probe traffic) or ``demo: true``
are never reconciled at all — synthetic rows must not mint machine outcome
labels. (The hatch's demo receipt, emit-demo-receipt.sh, is never journaled at
all since the 2026-07-10 fix pass; the demo skip stays as defense-in-depth for
any future demo-stamped row.)

Also GCs undo-journal files older than the 30-day retention floor and computes
the per-cell human-revert-rate for TI-7 / the retro to consume.

Batch B (whole-cabinet Evidence program): each verdict ALSO lands as
verification+outcome receipt events on the act's evidence trial — the journal
row's ``evidence_trial_id``, stamped by the executor at write-ahead time —
with detail {outcome, source, jid} and an ``undo-journal:<jid>`` link.
RECEIPT-class per the per-class recording contract: the label observes an
already-happened outcome, so a broken evidence plane degrades LOUD (stderr +
store-root degradations sidecar) and NEVER blocks the acted_verdict_event
supersede. Rows without the key (pre-evidence journals) are an honest gap.

Stdlib-only, importable under system Python 3.9.6 (``from __future__`` + Optional
annotations). Fully fixtured: the journal rows, the Monday probe, the ledger
reader, and the emit are all injected callables — no live API is ever reached in
a test. All subprocess (via the injected probe's transport) is arg-list only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from framework.acting import loop
from framework.env import captain_name
from framework.fidelity.consequence import (
    UNSTAMPED_ACTION_TYPE, emit_consequence, read_ledger)
from framework.frontdoor import action_undo
from framework.frontdoor.binder_wire import acted_verdict_event

# The Monday activity-log events that count as a REVERT of a lane-created item
# (an archive / delete / a column wiped back). Attribution to the Captain's user id on
# any of these upgrades a silent revert to a human verdict.
_REVERT_EVENTS = frozenset({
    "archive_pulse", "delete_pulse", "restore_pulse",
    "update_column_value", "change_column_value",
})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# --- Monday probe (the first machine-outcome supply; pure, injected transport) --

def item_state(monday_post: Callable, item_id: str) -> Dict[str, Any]:
    """Whether a Monday item still exists and is active. An empty items array =
    not found (a hard delete); ``state`` in {archived, deleted} = reverted.
    Resilient to a fake / partial response."""
    data = monday_post("query($id: [ID!]) { items(ids: $id) { id state } }",
                       {"id": [str(item_id)]})
    items = (data or {}).get("items") or []
    if not items:
        return {"exists": False, "archived": False}
    state = (items[0] or {}).get("state")
    return {"exists": True, "archived": state in ("archived", "deleted")}


def item_activity(monday_post: Callable, item_id: str,
                  since: Optional[str] = None) -> List[Dict[str, Any]]:
    """The item's activity-log entries (event / user_id / ts) at or after
    ``since`` — the attribution source for a Captain-caused revert."""
    data = monday_post(
        "query($id: [ID!]) { items(ids: $id) {"
        " activity_logs { event user_id created_at } } }", {"id": [str(item_id)]})
    items = (data or {}).get("items") or []
    logs = (items[0].get("activity_logs") if items else []) or []
    out: List[Dict[str, Any]] = []
    for lg in logs:
        if not isinstance(lg, dict):
            continue
        ts = lg.get("created_at")
        if since and ts and str(ts) < str(since):
            continue
        out.append({"event": lg.get("event"), "user_id": lg.get("user_id"), "ts": ts})
    return out


def make_monday_probe(monday_post: Callable, *,
                      nate_user_id: Optional[str] = None) -> Callable[[dict], dict]:
    """Build the artifact probe the sweep injects: given a journal row, report
    ``{exists, archived, reverted_by_captain}`` for its Monday item. A row with no
    Monday item (e.g. a calendar backend) is reported intact — the calendar
    surface has no cheap state probe, and we NEVER fabricate a revert we cannot
    prove."""
    def probe(row: dict) -> Dict[str, Any]:
        item_id = (row.get("created") or {}).get("monday_id")
        if not item_id:
            return {"exists": True, "archived": False, "reverted_by_captain": False}
        st = item_state(monday_post, str(item_id))
        reverted_by_captain = False
        if (not st.get("exists") or st.get("archived")) and nate_user_id:
            acts = item_activity(monday_post, str(item_id), since=row.get("executed_at"))
            reverted_by_captain = any(
                str(a.get("user_id")) == str(nate_user_id)
                and a.get("event") in _REVERT_EVENTS for a in acts)
        return {"exists": st.get("exists", True),
                "archived": st.get("archived", False),
                "reverted_by_captain": reverted_by_captain}
    return probe


def _probe_verdict(row: dict, monday_probe: Optional[Callable]):
    """(verdict, source, evidence) for a past-TTL row. No probe, a probe error,
    or an intact artifact -> ttl_ok (conservative — a revert is never invented).
    A missing/archived artifact -> silent_revert (verdict_human iff the Captain's hand)."""
    if monday_probe is None:
        return "ttl_ok", None, None
    try:
        state = monday_probe(row) or {}
    except Exception:
        return "ttl_ok", None, None
    if state.get("exists", True) and not state.get("archived", False):
        return "ttl_ok", None, None
    if state.get("reverted_by_captain"):
        return ("silent_revert", "verdict_human",
                f"silent revert attributed to {captain_name()} (Monday activity log)")
    return "silent_revert", "verdict_judge", None


def _past_ttl(row: dict, now: str) -> bool:
    exp = row.get("ttl_expires_at")
    return bool(exp) and str(exp) < str(now)   # ISO strings sort lexicographically


# --- evidence receipts (Batch B: machine outcome labels on the act's trial) --
#
# RECEIPT-class by the per-class recording contract: the sweep's ttl_ok /
# silent_revert labels OBSERVE an outcome that already happened, so a broken
# evidence plane degrades LOUD and NEVER blocks the acted_verdict_event
# supersede (the domain write) — fail-closed recording here would let a dead
# evidence plane block the consequence ledger, inverting the brake. Rows
# without an ``evidence_trial_id`` (pre-evidence journals) are an honest gap,
# skipped silently. All evidence imports are LAZY so this module stays
# importable under system Python 3.9 (the evidence plane itself runs 3.12 —
# run-undo-sweep.sh pins CABINET_PYTHON).

_DEGRADATION_SIDECAR = "degradations.jsonl"   # lifecycle.DEGRADATION_SIDECAR
_MARKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _evidence_store_root(explicit: Optional[Any]) -> Optional[Path]:
    """The evidence store root, or None when recording is disabled.

    An EXPLICIT root (tests / callers) always wins. Under pytest recording is
    OFF unless ``CABINET_ACTION_EVIDENCE_STORE`` names a scratch store — the
    evidence_mirror pytest fence (2026-07-04 leak lesson: a suite run must
    never touch the live signed store). Production resolution is repo-derived
    (explicit-constructor-arg law), never env-derived (A10)."""
    if explicit is not None:
        return Path(explicit)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        override = os.environ.get("CABINET_ACTION_EVIDENCE_STORE")
        return Path(override) if override else None
    # Production resolution rides the journey producer's EVIDENCE_REL — the
    # ONE canonical store constant (evidence_mirror._production_store_root
    # idiom); imported lazily so this module stays 3.9-importable.
    from framework.onboarding.journey import EVIDENCE_REL
    return Path(__file__).resolve().parents[2] / EVIDENCE_REL


def _marker_field(value: Any) -> str:
    s = str(value)
    return s if _MARKER_ID_RE.fullmatch(s) else "invalid"


def _note_receipt_degradation(root: Optional[Path], trial_id: Any,
                              code: Any) -> None:
    """Make one receipt degradation LOUD without ever raising: a stderr
    warning plus one content-free, unsigned marker line appended to the
    store-root degradations sidecar (the lifecycle marker shape — a broken
    plane cannot sign its own distress; the doctor may read the sidecar)."""
    try:
        print("undo-sweep: WARN evidence outcome receipt degraded "
              f"(trial={_marker_field(trial_id)} code={_marker_field(code)}) — "
              "the ledger supersede already landed; the trial is missing its "
              "outcome label", file=sys.stderr)
    except Exception:
        pass
    if root is None:
        return
    try:
        line = json.dumps({
            "schema": "cabinet.evidence-degradation/v1",
            "ts": _now(),
            "trial_id": _marker_field(trial_id),
            "component": "undo-sweep",
            "phase": "receipt",
            "error_code": _marker_field(code),
        }, sort_keys=True) + "\n"
        fd = os.open(root / _DEGRADATION_SIDECAR,
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:
        pass


def _record_outcome_receipt(row: dict, *, outcome: str, source: Optional[str],
                            result_code: str,
                            store: Optional[Any],
                            counts: Dict[str, int]) -> None:
    """Append the sweep's machine label to the ACT's evidence trial
    (verification + outcome events on the trial named by the journal row's
    ``evidence_trial_id``), linked back to the undo-journal row. Never raises;
    never precedes or blocks the consequence emit."""
    trial_id = row.get("evidence_trial_id")
    if not trial_id:
        counts["skipped"] += 1                 # pre-evidence row — honest gap
        return
    root = _evidence_store_root(store)
    if root is None:
        counts["skipped"] += 1                 # recording fenced off (pytest)
        return
    jid = str(row.get("jid") or "")
    try:
        from framework.evidence import identity
        from framework.evidence.lifecycle import valid_id_or_none
        from framework.evidence.recorder import EvidenceRecorder

        if valid_id_or_none(str(trial_id)) is None:
            counts["skipped"] += 1             # forged/garbled id — never append
            return
        recorder = EvidenceRecorder(root)
        context = recorder.trace(
            str(trial_id), surface="system",
            correlation_id=valid_id_or_none(str(row.get("cid") or "")))
        if identity.is_attested():
            actor = identity.attested_actor()
            component = identity.attested_component()
            stamp = identity.attestation_detail()
        else:
            actor = {"kind": "system", "id": "undo-sweep"}
            component = {"name": "undo-sweep", "version": "1+evidence-v1"}
            stamp = {}
        detail = dict(stamp)
        detail.update({"action": "undo_sweep_reconcile", "outcome": outcome,
                       "result_code": result_code, "jid": jid})
        if source:
            detail["source"] = source          # verdict_judge | verdict_human
        links = ["undo-journal:" + jid] if jid else []
        recorder.append(context, phase="verification",
                        status="verified" if outcome == "ok" else "unverified",
                        actor=actor, component=component,
                        detail=detail, links=links)
        recorder.append(context, phase="outcome",
                        status="succeeded" if outcome == "ok" else "failed",
                        actor=actor, component=component,
                        detail=detail, links=links)
        counts["recorded"] += 1
    except Exception as exc:
        if getattr(exc, "code", None) == "trial_purged":
            counts["skipped"] += 1             # retention won — a legal state
            return
        counts["degraded"] += 1
        _note_receipt_degradation(
            root, trial_id, getattr(exc, "code", None) or type(exc).__name__)


# --- the sweep ---------------------------------------------------------------

def run_sweep(*, now: Optional[str] = None,
              journal_rows: Optional[List[dict]] = None,
              monday_probe: Optional[Callable] = None,
              read_ledger_fn: Optional[Callable[[], List[dict]]] = None,
              emit: Optional[Callable[..., Any]] = None,
              gc: bool = True,
              journal_dir: Optional[str] = None,
              retention_days: int = action_undo.JOURNAL_RETENTION_D,
              evidence_store: Optional[Any] = None) -> Dict[str, Any]:
    """One reconciliation pass. Emits a superseding ttl_ok / silent_revert event
    per eligible past-TTL step (idempotent via the outcome=unknown gate), then
    computes the human-revert-rate and (optionally) GCs old journal files.

    Batch B: AFTER each verdict emit, the machine label also lands as
    verification+outcome receipt events on the act's evidence trial (the
    journal row's ``evidence_trial_id``) — RECEIPT-class: degrade LOUD, never
    block the ledger supersede. ``evidence_store`` points the receipts at an
    explicit store root (tests inject a scratch store; default is the
    repo-derived production store behind the pytest fence)."""
    now = now or _now()
    read_ledger_fn = read_ledger_fn or read_ledger
    emit = emit or emit_consequence
    rows = journal_rows if journal_rows is not None else action_undo._read_journal()
    by_identity = {loop.proposal_id(e): e for e in read_ledger_fn()}

    ttl_ok: List[str] = []
    reverts: List[str] = []
    skipped = 0
    ev_counts: Dict[str, int] = {"recorded": 0, "skipped": 0, "degraded": 0}
    for r in rows:
        # canary rows are the guard's own probe traffic; demo rows are
        # synthetic (demo: true) — neither is a real act, so neither may mint
        # a ttl_ok/silent_revert machine label (a probe-less past-TTL demo
        # row would otherwise conservatively verdict ttl_ok: a fake ok-label
        # from fake work). Defense-in-depth: the hatch's demo receipt
        # (emit-demo-receipt.sh) is never journaled at all since 2026-07-10.
        if (r.get("status") != "executed" or not r.get("executed_at")
                or r.get("canary") or r.get("demo")):
            continue
        if not _past_ttl(r, now):
            continue
        base = action_undo.acted_event(None, r)
        rec = by_identity.get(loop.proposal_id(base), base)
        if (rec.get("outcome") or {}).get("status") != "unknown":
            skipped += 1                       # confirmed / undone / already reconciled
            continue
        verdict, source, evidence = _probe_verdict(r, monday_probe)
        if verdict == "ttl_ok":
            emit(**acted_verdict_event(rec, "ttl_ok", reviewed_at=now))
            ttl_ok.append(r.get("jid"))
            # receipt AFTER the domain write, never blocking it (Batch B).
            _record_outcome_receipt(r, outcome="ok", source=None,
                                    result_code="ttl_ok",
                                    store=evidence_store, counts=ev_counts)
        else:
            emit(**acted_verdict_event(rec, "silent_revert", source=source,
                                       evidence=evidence, reviewed_at=now))
            reverts.append(r.get("jid"))
            _record_outcome_receipt(r, outcome="failed", source=source,
                                    result_code="silent_revert",
                                    store=evidence_store, counts=ev_counts)

    result: Dict[str, Any] = {
        "ttl_ok": ttl_ok, "silent_reverts": reverts, "skipped": skipped,
        "evidence_receipts": ev_counts,
        "human_revert_rates": human_revert_rates(read_ledger_fn()),
    }
    if gc:
        result["gc"] = gc_journal(now=now, retention_days=retention_days,
                                  journal_dir=journal_dir)
    return result


# --- per-cell human-revert-rate (TI-7 / retro input) -------------------------

def human_revert_rates(ledger: List[dict]) -> Dict[str, Dict[str, Any]]:
    """Per (actor, lane, action_type) ACTED cell: the fraction of settled acts
    the Captain reverted with his own hand. Only rows with
    ``proposal.required==false`` (acted, never proposed) and a settled outcome
    (ok/failed) count; a human revert is ``outcome=failed`` +
    ``review={wrong, verdict_human}``. Keyed by ``actor|lane|action_type`` for a
    json-friendly return."""
    cells: Dict[tuple, Dict[str, Any]] = {}
    for e in ledger:
        prop = e.get("proposal") or {}
        if prop.get("required") is not False:
            continue
        outcome = (e.get("outcome") or {}).get("status")
        if outcome not in ("ok", "failed"):
            continue
        actor = e.get("actor") or {}
        key = (f"{actor.get('kind')}:{actor.get('id')}", e.get("lane"),
               e.get("action_type") or UNSTAMPED_ACTION_TYPE)
        c = cells.setdefault(key, {"acts": 0, "human_reverts": 0})
        c["acts"] += 1
        review = e.get("review") or {}
        if (outcome == "failed" and review.get("verdict") == "wrong"
                and review.get("source") == "verdict_human"):
            c["human_reverts"] += 1
    out: Dict[str, Dict[str, Any]] = {}
    for key, c in cells.items():
        c["rate"] = (c["human_reverts"] / c["acts"]) if c["acts"] else None
        out["|".join(str(x) for x in key)] = c
    return out


# --- journal GC (>30d) -------------------------------------------------------

_JOURNAL_NAME_RE = re.compile(r"^undo-journal-(\d{4}-\d{2}-\d{2})\.jsonl$")


def gc_journal(*, now: Optional[str] = None,
               retention_days: int = action_undo.JOURNAL_RETENTION_D,
               journal_dir: Optional[str] = None) -> Dict[str, Any]:
    """Prune ``undo-journal-YYYY-MM-DD.jsonl`` files older than the retention
    floor. A file that old is well past every window (48h TTL, 9d pointer), so
    all its rows are settled. The date comes from the fixed basename (never
    caller input); a symlink resolving outside the dir is skipped (same fence as
    ``action_undo._safe_journal_files``)."""
    base = Path(journal_dir) if journal_dir else action_undo._undo_dir()
    if not base.exists():
        return {"pruned": [], "kept": 0}
    now_dt = _parse_iso(now) or datetime.now(timezone.utc)
    cutoff = (now_dt - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    resolved = base.resolve()
    pruned: List[str] = []
    kept = 0
    for f in sorted(base.glob("undo-journal-*.jsonl")):
        try:
            real = f.resolve()
        except OSError:
            continue
        if not (real == resolved or resolved in real.parents):
            continue                           # symlink escape — skip, never follow
        m = _JOURNAL_NAME_RE.match(f.name)
        if not m:
            continue
        if m.group(1) < cutoff:
            try:
                f.unlink()
                pruned.append(f.name)
            except OSError:
                pass
        else:
            kept += 1
    return {"pruned": pruned, "kept": kept}
