"""Chokepoint telemetry mirrors — org-event + consequence receipts (Phase 2).

The two breadth-plane ledgers (the org-event JSONL written by
``framework/events/emitter.py`` and the consequence JSONL written by
``framework/fidelity/consequence.py``) stay the domain records.  This module
appends a signed RECEIPT about selected, already-happened rows into the
tamper-evident evidence store, through the sanctioned recorder seam only
(``EvidenceRecorder`` — the same lazy-import producer pattern as
``framework/evidence_anchor.py``).  It is deliberately NOT part of the
germline ``framework/evidence`` package.

Recording contract (per-class doctrine, whole-cabinet evidence design
2026-07-16 §3 Phase 2 + R-13)
=============================================================================
* TELEMETRY MIRRORS (this module): receipts about events that ALREADY
  happened.  They degrade LOUD (stderr + doctor-readable marker ledger +
  best-effort ``evidence_mirror_degraded`` org event, cross-process
  rate-limited) and NEVER block or fail the domain emit.  A recorder outage
  must never take down the org's event bus.
* ACT-CLASS producers (action lane, learning/gate, watchdog, session
  lifecycle) are FAIL-CLOSED — evidence-before-action via
  ``framework.evidence.ActLifecycle``.  That contract is Batch B and is
  explicitly NOT implemented here; do not route act-semantic surfaces
  through this module.

Allow-list law (the 59%-plumbing lesson)
=============================================================================
What gets mirrored is an explicit ALLOW-LIST of event classes
(``MIRRORED_ORG_EVENT_TYPES`` — a strict subset of the emitter's
``VALID_EVENT_TYPES``), never a deny-list: a deny-list would silently sign
future nervous-system exhaust as classes are added.  Trigger delivery /
ACK / heartbeat exhaust structurally never reaches either chokepoint (it
rides the Redis Streams bus into the exhaust archive, digested daily by
``framework/evidence_anchor.py``) and MUST stay out of this list forever;
session/notification/subagent/outbox/policy_evaluated/eval-run exhaust is
enumerated in ``NEVER_MIRRORED_EXHAUST`` and pinned disjoint by test.
Consequence rows mirror on lifecycle presence
(``MIRRORED_CONSEQUENCE_LIFECYCLE`` — proposal/outcome/review; the Phase 4
fuel-integrity precursor).  Rows carrying ``sim:true`` are NEVER mirrored.

Correlation (both directions)
=============================================================================
* Forward (org row -> evidence): the emitter stamps
  ``payload[PAYLOAD_KEY] = {"trial_id": <evt-orgmirror-yyyymmdd>}`` into a
  COPY of the payload for allow-listed classes (payload is the only field
  that rides all three org sinks whole).  Consequence rows get one
  namespaced ref string ``evidence-trial:<trial_id>`` appended to ``refs``
  AT THE CHOKEPOINT (so superseding enrichment rows re-carry it).  The ref
  is identity-free for the attention plane (no ``canonical_refs`` extractor
  matches the ``evidence-trial:`` scheme) and never equals the graduation
  sentinel ``demote:direct``.
* Reverse (evidence -> org row): each receipt's ``correlation_id`` is the
  org event id (uuid4) / the consequence row's canonical sha256, and its
  ``detail`` carries ``org_event_id``/``org_event_type``/``ledger_date`` or
  the consequence identity tuple (actor kind:id, action, subject, ts) +
  ``row_sha256`` — ids and digests only, never payload copies.  Join
  recipe: parse the domain JSONL line, re-serialize with
  ``json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)``,
  sha256 it.

Identity (A6)
=============================================================================
The evidence ``actor`` is a FIXED module constant per chokepoint
(``org-event-mirror`` / ``consequence-mirror``) and the ``component`` is
passed in full so the recorder's env-fed provenance fallback never fires
(A10).  The mirrored row's own actor string is DATA inside ``detail``,
never the evidence actor — identity is never payload-derived.  Broker
attestation for daemon producers is a separate ceremony wave.

Volume envelope (R-8 — measured in Phase 1, enforced here)
=============================================================================
``EvidenceRecorder.append`` re-verifies the whole trial per append, so an
unbounded trial is O(n^2) hashing.  Envelope: day-bounded taxonomy trials
(``evt-orgmirror-<yyyymmdd>`` / ``evt-consequence-<yyyymmdd>``, natural
daily reset + per-class retention) + a per-trial cap.
``MAX_MIRROR_EVENTS_PER_TRIAL = 500`` is a CODE constant (never an env var,
never a control.json dial): live volume measured 2026-07-14..16 puts the
allow-listed org-signal classes at ~50-100 events/day and the consequence
ledger at 1-48 rows/day, so 500 is 5-10x headroom.  On overflow the mirror
chains to suffixed segments INSIDE the class token
(``evt-orgmirror-b-<yyyymmdd>`` — keeps ``TRIAL_CLASS_RE`` parsing) up to
``MAX_CHAIN_SEGMENTS``, then degrades loud and skips.  Counting is
observed-sequence based (cross-process accurate via the recorder's returned
``sequence``; a fresh process may overshoot a full segment by ~1 append —
accepted backstop slop).  Trial ids are minted from the WALL-CLOCK landing
date (never the caller-supplied ts, which enrichment can backdate).

Store root + pytest fence (the 2026-07-04 leak lesson)
=============================================================================
The production store root is pinned from ``__file__`` + journey.py's
``EVIDENCE_REL`` constant (the one canonical framework->instance path
coupling — no second literal is minted here), NEVER from env: no
environment variable can steer what gets mirrored or where (the only env
reads below are the pytest fence itself).  Under
``PYTEST_CURRENT_TEST`` the mirror is DISABLED unless the test sets
``CABINET_EVIDENCE_MIRROR_STORE=<scratch store>`` (and optionally
``CABINET_EVIDENCE_MIRROR_MARKER=<scratch marker>``); those overrides are
consulted ONLY under pytest, so a test can never write the live signed
store and production can never be redirected.

Degradation (LOUD, rate-limited, never raising)
=============================================================================
On any mirror failure — recorder unimportable (system Python 3.9 cannot
import ``framework/evidence``: shell-hook CLI producers), recorder
construction/append error, integrity-red trial, cap exhaustion — the
module: (1) prints ONE stderr WARN per (chokepoint, reason) per process;
(2) appends ONE marker line per RATE_LIMIT window (900s, cross-process,
keyed on chokepoint+reason) to the doctor-readable ledger
``cabinet/logs/evidence-mirror-degradations.jsonl`` — line format
``{"ts", "chokepoint", "reason", "message"}``; (3) emits a best-effort
``evidence_mirror_degraded`` org event (registered in VALID_EVENT_TYPES,
NEVER in the mirror allow-list — no recursion).  An integrity-red trial
(EvidenceError ``ledger_integrity``) is tamper evidence: it is degraded
loud and NEVER auto-reminted; the day boundary provides natural recovery.

Officer surface: NONE
=============================================================================
No CLI, no ``__main__``, no read API — producers reach this module through
code-level imports at the two chokepoints only.
``cabinet/scripts/evidence-read.sh`` stays the only officer path; the
receipt detail keys here are not in ``PROJECTION_ALLOWED_DETAIL`` so they
are auto-dropped from the officer projection (never-a-score preserved by
construction).

Known residuals (documented, caught downstream)
=============================================================================
* A forward stamp can dangle when the receipt append later fails (the stamp
  is written before the domain emit, the receipt after) — the daily
  digest-anchor + effect-vs-evidence reconciler surface the gap.
* ``ledger_date`` can be off by one day exactly at the UTC midnight
  boundary between row build and file write.
* Same-user honesty caveat (R2): mirror and domain writer share a uid until
  broker-attested identity (HP-1/Phase 6).

This module must stay importable on system Python 3.9 (the chokepoints are
imported from 3.9 shell-hook CLIs); only the lazy recorder import inside
the append path requires 3.11+.
"""

from __future__ import annotations

import hashlib
import json
import os
import string
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Reviewable constants — the allow-lists ARE the mirror policy.
# ---------------------------------------------------------------------------

#: Org-event classes that mirror (R-1 org-signal/authority selection).
#: A strict subset of framework.events.emitter.VALID_EVENT_TYPES — pinned by
#: framework/tests/test_evidence_mirror.py.  ADDITIONS are reviewed policy
#: changes: never add trigger delivery/ACK/heartbeat classes, session or
#: notification exhaust, or any class emitted per-call rather than
#: per-decision.
MIRRORED_ORG_EVENT_TYPES = frozenset({
    # Captain authority signals
    "captain_goal_declared",
    "captain_outcome_ratified",
    "captain_decision_logged",
    "captain_boundary_set",
    "captain_gate_bounced",
    # Role authority lifecycle
    "role_created",
    "role_charter_changed",
    "role_capability_added",
    "role_capability_removed",
    "role_authority_changed",
    "role_suspended",
    "role_reactivated",
    "role_retired",
    "role_hat_assigned",
    "role_hat_removed",
    "role_hat_promoted",
    "role_evolved",
    # Mission lifecycle
    "mission_created",
    "mission_activated",
    "mission_completed",
    "mission_failed",
    # Work graph — verification signal only (creation/start/completion
    # volume stays on the domain ledger; work_item_completed additionally
    # rides 3.9 shell hooks and carries a junk-row history).
    "work_item_verified",
    # Policy decisions (policy_evaluated is per-call exhaust — excluded)
    "policy_blocked",
    "policy_updated",
    # Fidelity harness org-signal
    "fidelity_case_evaluated",
    "fidelity_case_leak_detected",
    "fidelity_case_scored",
    "fidelity_case_labeled",
    # Graduation / self-improvement
    "graduation_transition",
    "skill_promoted",
    "self_improvement_loop_started",
    "self_improvement_loop_completed",
    # Capability-gap Captain decisions (pipeline steps excluded)
    "capability_gap_approved",
    "capability_gap_declined",
    "capability_gap_resolved",
    # Trust ladder
    "trust_rung_proposed",
    "trust_rung_granted",
    # Safety / control plane
    "kill_switch_activated",
    "kill_switch_deactivated",
    "spending_limit_reached",
    "cap_alarm",
    "kind_unfrozen",
    # Sovereign needs ledger
    "need_filed",
    "need_granted",
    "need_denied",
    "need_snoozed",
    "need_expired",
    "need_escalated",
})

#: Hard exhaust: classes that must NEVER enter the allow-list above (the
#: 59%-plumbing lesson — ~94% of live org-event volume is the first three).
#: This set is documentation + a test tripwire, not a runtime gate: the
#: runtime gate is allow-list membership only.
NEVER_MIRRORED_EXHAUST = frozenset({
    "session_started",
    "session_ended",
    "notification_received",
    "subagent_completed",
    "outbox_queued",
    "outbox_dispatched",
    "outbox_failed",
    "policy_evaluated",
    "eval_run_started",
    "eval_passed",
    "eval_failed",
    "ovi_snapshot_computed",
    "experience_recorded",
    "self_proposal_prepared",
    "account_flow_surfaced",
    # the mirror's own degradation signal — mirroring it would recurse a
    # dead recorder
    "evidence_mirror_degraded",
})

#: Consequence rows mirror when they carry at least one lifecycle object
#: (and no sim marker).  Presence-based because consequence rows have no
#: class field — the lifecycle vocabulary IS the class.
MIRRORED_CONSEQUENCE_LIFECYCLE = frozenset({"proposal", "outcome", "review"})

#: Reserved payload key the emitter stamps for allow-listed org classes
#: (forward correlation).  Producers must not use this key themselves.
PAYLOAD_KEY = "evidence_mirror"

#: Namespaced ref stamped into consequence ``refs`` (forward correlation).
#: '<ns>:<value>' convention; must never equal consequence.DIRECT_DEMOTE_REF.
CONSEQUENCE_REF_PREFIX = "evidence-trial:"

#: Org event class emitted (best-effort) when the mirror degrades.  MUST
#: stay out of MIRRORED_ORG_EVENT_TYPES.
DEGRADATION_EVENT_TYPE = "evidence_mirror_degraded"

#: Day-bounded taxonomy classes (recorder TRIAL_CLASS_RE:
#: ``evt-<class>-<yyyymmdd>``).  Chain segments live INSIDE the class token
#: ("orgmirror-b") so retention parsing never breaks.
ORG_TRIAL_CLASS = "orgmirror"
CONSEQUENCE_TRIAL_CLASS = "consequence"

#: R-8 envelope constants — CODE constants by law (never env, never
#: control.json).  Provenance: live volume measured 2026-07-14..16
#: (org-signal ~50-100 events/day/trial; consequence 1-48 rows/day).
MAX_MIRROR_EVENTS_PER_TRIAL = 500
MAX_CHAIN_SEGMENTS = 6  # base + b..f -> worst case 3000 receipts/day/class

#: Cross-process degradation rate limit (seconds) — one marker line + one
#: degradation org event per (chokepoint, reason) per window.
RATE_LIMIT_SECONDS = 900

#: Fixed producer identities (A6 — never payload-derived).
ORG_MIRROR_ACTOR = {"kind": "system", "id": "org-event-mirror"}
CONSEQUENCE_MIRROR_ACTOR = {"kind": "system", "id": "consequence-mirror"}
MIRROR_COMPONENT = {"name": "evidence-mirror", "version": "1", "commit": "unset"}

# Marker ledger location (pinned from __file__, never env).
_MARKER_REL = ("cabinet", "logs", "evidence-mirror-degradations.jsonl")


# ---------------------------------------------------------------------------
# Module state — per-process, guarded by one lock.
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()
_counts: dict[str, int] = {}          # trial_id -> highest observed sequence
_segments: dict[tuple, int] = {}      # (class, yyyymmdd) -> active segment
_recorders: dict[str, Any] = {}       # store_root(str) -> EvidenceRecorder
_stderr_seen: set = set()             # (chokepoint, reason) warned already
_degrading = threading.local()        # re-entrancy guard for _degrade


def _reset_state() -> None:
    """Test-only: clear per-process caches (module state is process-global)."""
    global _prod_store_root
    with _LOCK:
        _counts.clear()
        _segments.clear()
        _recorders.clear()
        _stderr_seen.clear()
        _prod_store_root = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


_prod_store_root = None  # positive cache — resolution imports journey once


def _production_store_root() -> Path:
    """The live store root under the repo, from the ONE canonical constant.

    The relative store path is owned by framework/onboarding/journey.py
    (``EVIDENCE_REL`` — the already-baselined framework->instance layer
    coupling); importing that constant keeps the coupling in exactly one
    place instead of minting a second layer-separation debt row.  The
    import pulls the evidence package and therefore FAILS on system Python
    3.9 — callers degrade loud (``store_root_unresolvable``), never crash
    the emit.
    """
    global _prod_store_root
    if _prod_store_root is None:
        from framework.onboarding.journey import EVIDENCE_REL
        _prod_store_root = _repo_root() / EVIDENCE_REL
    return _prod_store_root


def _store_root() -> "Path | None":
    """The pinned store root, or None when mirroring is disabled.

    The ONLY env reads in this module are the pytest fence below: under
    PYTEST_CURRENT_TEST the mirror is off unless the test supplies a scratch
    store — a pytest run can never touch the live signed store (2026-07-04
    leak lesson), and production resolution never consults env (A10).
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        override = os.environ.get("CABINET_EVIDENCE_MIRROR_STORE")
        return Path(override) if override else None
    return _production_store_root()


def _marker_path() -> "Path | None":
    if os.environ.get("PYTEST_CURRENT_TEST"):
        override = os.environ.get("CABINET_EVIDENCE_MIRROR_MARKER")
        return Path(override) if override else None
    return _repo_root().joinpath(*_MARKER_REL)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_sha256(value: Any) -> str:
    """sha256 over the documented canonical form (the join recipe)."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# Reservation — deterministic day trial ids + the R-8 cap.
# ---------------------------------------------------------------------------

def _trial_id(cls: str, segment: int, day: str) -> str:
    suffix = "" if segment == 0 else "-" + string.ascii_lowercase[segment]
    return "evt-" + cls + suffix + "-" + day


def _reserve(cls: str, chokepoint: str) -> "dict | None":
    try:
        root = _store_root()
    except Exception as exc:
        # Production root resolution failed (e.g. Python 3.9 cannot import
        # the evidence package via journey) — LOUD, rate-limited, no stamp.
        _degrade(chokepoint, "store_root_unresolvable", str(exc))
        return None
    if root is None:
        return None
    day = _utc_now().strftime("%Y%m%d")  # wall-clock landing date, never ts
    with _LOCK:
        segment = _segments.get((cls, day), 0)
        while segment < MAX_CHAIN_SEGMENTS:
            trial_id = _trial_id(cls, segment, day)
            if _counts.get(trial_id, 0) < MAX_MIRROR_EVENTS_PER_TRIAL:
                _segments[(cls, day)] = segment
                return {"trial_id": trial_id, "store_root": str(root)}
            segment += 1
        _segments[(cls, day)] = segment
    _degrade(
        chokepoint,
        "trial_cap_exhausted",
        "all %d day segments full for %s-%s" % (MAX_CHAIN_SEGMENTS, cls, day),
    )
    return None


def reserve_org(event_type: str) -> "dict | None":
    """Reservation for the org-event chokepoint. Never raises.

    Returns ``{"trial_id", "store_root"}`` for allow-listed classes when the
    mirror is enabled, else None.  The trial id is deterministic pre-write so
    the emitter can stamp it into the payload BEFORE the immutable domain
    append (forward correlation without a recorder round-trip).
    """
    try:
        if event_type not in MIRRORED_ORG_EVENT_TYPES:
            return None
        return _reserve(ORG_TRIAL_CLASS, "org")
    except Exception:  # reservation must never break the emitter
        return None


def reserve_consequence(event: Any) -> "dict | None":
    """Reservation for the consequence chokepoint. Never raises.

    Mirrors only live lifecycle rows: no ``sim`` marker and at least one of
    proposal/outcome/review present.  Adds ``ref`` — the namespaced string
    the chokepoint appends to the row's ``refs``.
    """
    try:
        if not isinstance(event, dict) or event.get("sim"):
            return None
        if not any(key in event for key in MIRRORED_CONSEQUENCE_LIFECYCLE):
            return None
        slot = _reserve(CONSEQUENCE_TRIAL_CLASS, "consequence")
        if slot is not None:
            slot["ref"] = CONSEQUENCE_REF_PREFIX + slot["trial_id"]
        return slot
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Receipt appends — the sanctioned recorder seam (no CLI, imports only).
# ---------------------------------------------------------------------------

def _import_recorder():
    """Lazy germline import — the ONLY framework/evidence coupling.

    Raises on system Python 3.9 (framework/evidence/redaction.py uses
    3.11+ regex syntax); callers degrade loud.  Kept as a seam so tests can
    fault-inject the unimportable case.
    """
    from framework.evidence.recorder import EvidenceRecorder
    return EvidenceRecorder


def _recorder(store_root: str):
    """One recorder per process per store root (construction is heavy:
    signing-key load + pending/purge recovery scans)."""
    with _LOCK:
        recorder = _recorders.get(store_root)
    if recorder is not None:
        return recorder
    recorder_cls = _import_recorder()
    recorder = recorder_cls(Path(store_root))
    with _LOCK:
        _recorders.setdefault(store_root, recorder)
        return _recorders[store_root]


def _note_sequence(trial_id: str, sequence: Any) -> None:
    with _LOCK:
        previous = _counts.get(trial_id, 0)
        if isinstance(sequence, int) and not isinstance(sequence, bool) and sequence > previous:
            _counts[trial_id] = sequence
        else:
            _counts[trial_id] = previous + 1


def _append_receipt(
    slot: dict,
    *,
    actor: dict,
    detail: dict,
    correlation_id: "str | None",
) -> None:
    recorder = _recorder(slot["store_root"])
    context = recorder.trace(
        slot["trial_id"], surface="system", correlation_id=correlation_id
    )
    appended = recorder.append(
        context,
        phase="system",
        status="succeeded",
        actor=dict(actor),
        component=dict(MIRROR_COMPONENT),
        detail=detail,
        links=[],
    )
    _note_sequence(slot["trial_id"], appended.get("sequence"))


def mirror_org_event(event: dict, slot: dict) -> None:
    """Append one receipt for an already-written org event. Never raises."""
    try:
        created_at = str(event.get("created_at") or "")
        detail = {
            "action": "org_event_mirror",
            "org_event_id": str(event.get("id") or ""),
            "org_event_type": str(event.get("event_type") or ""),
            "org_created_at": created_at,
            # ids + digests only, never payload copies (redaction doctrine)
            "org_event_sha256": _canonical_sha256(event),
            "ledger_date": created_at[:10],
        }
        correlation = str(event.get("id") or "") or None
        _append_receipt(
            slot,
            actor=ORG_MIRROR_ACTOR,
            detail=detail,
            correlation_id=correlation,
        )
    except Exception as exc:
        _degrade("org", _reason_of(exc), str(exc))


def mirror_consequence(event: dict, slot: dict) -> None:
    """Append one receipt for an already-written consequence row. Never raises.

    Consequence rows have no id: the join key is the identity tuple
    (actor kind:id, action, subject, ts) + the canonical row sha256.
    """
    try:
        actor = event.get("actor") or {}
        detail = {
            "action": "consequence_mirror",
            "consequence_actor": "%s:%s" % (actor.get("kind"), actor.get("id")),
            "consequence_action": str(event.get("action") or ""),
            "consequence_subject": str(event.get("subject") or ""),
            "consequence_ts": str(event.get("ts") or ""),
            "row_sha256": _canonical_sha256(event),
            "ledger_date": _utc_now().strftime("%Y-%m-%d"),
            "lifecycle": sorted(
                key for key in MIRRORED_CONSEQUENCE_LIFECYCLE if key in event
            ),
        }
        _append_receipt(
            slot,
            actor=CONSEQUENCE_MIRROR_ACTOR,
            detail=detail,
            correlation_id=detail["row_sha256"],
        )
    except Exception as exc:
        _degrade("consequence", _reason_of(exc), str(exc))


# ---------------------------------------------------------------------------
# LOUD degradation — stderr + doctor marker + best-effort org event.
# ---------------------------------------------------------------------------

def _reason_of(exc: BaseException) -> str:
    if isinstance(exc, (ImportError, SyntaxError)) or type(exc).__module__ in (
        "re", "sre_constants", "sre_parse",
    ):
        # system Python 3.9 cannot import framework/evidence — the named
        # coverage gap for shell-hook CLI producers.
        return "recorder_unimportable"
    if type(exc).__name__ == "EvidenceError":
        # typed recorder refusal (e.g. ledger_integrity = tamper evidence —
        # never auto-remint; the day boundary recovers).
        return "evidence_" + str(getattr(exc, "code", "error"))
    return "recorder_error"


def _rate_limited(chokepoint: str, reason: str) -> bool:
    """True when a matching marker line already landed inside the window.

    Cross-process: reads the marker ledger tail (best effort). Any read
    problem means NOT rate-limited — degrading twice beats degrading never.
    """
    path = _marker_path()
    if path is None:
        return False
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 16384))
            tail = handle.read().decode("utf-8", "replace")
    except OSError:
        return False
    now = time.time()
    for line in reversed([l for l in tail.split("\n") if l.strip()][-20:]):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("chokepoint") != chokepoint or row.get("reason") != reason:
            continue
        try:
            ts = datetime.strptime(
                str(row.get("ts")), "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return False
        return (now - ts) < RATE_LIMIT_SECONDS
    return False


def _write_marker(chokepoint: str, reason: str, message: str) -> None:
    path = _marker_path()
    if path is None:
        return
    row = {
        "ts": _utc_now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "chokepoint": chokepoint,
        "reason": reason,
        "message": str(message)[:200],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        os.write(fd, (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def _emit_degradation_event(chokepoint: str, reason: str) -> None:
    from framework.events.emitter import emit  # lazy — avoids import cycles
    emit(
        DEGRADATION_EVENT_TYPE,
        actor="system",
        payload={"chokepoint": chokepoint, "reason": reason},
    )


def _degrade(chokepoint: str, reason: str, message: str) -> None:
    """LOUD, rate-limited, never-raising degradation. The domain emit that
    triggered this has ALREADY succeeded — this is pure signal."""
    try:
        key = (chokepoint, reason)
        with _LOCK:
            first = key not in _stderr_seen
            _stderr_seen.add(key)
        if first:
            print(
                "evidence-mirror: WARN degraded (%s/%s): %s"
                % (chokepoint, reason, str(message)[:300]),
                file=sys.stderr,
            )
        if getattr(_degrading, "active", False):
            return  # re-entrancy: never degrade about degrading
        _degrading.active = True
        try:
            if _marker_path() is None:
                # No cross-process ledger available (pytest without a marker
                # override): degrade once per process per reason instead.
                limited = not first
            else:
                limited = _rate_limited(chokepoint, reason)
            if not limited:
                try:
                    _write_marker(chokepoint, reason, message)
                except Exception:
                    pass
                try:
                    _emit_degradation_event(chokepoint, reason)
                except Exception:
                    pass
        finally:
            _degrading.active = False
    except Exception:
        pass
