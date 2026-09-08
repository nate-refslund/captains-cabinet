"""Atomic task claims with a lease, derived from the event ledger.

WHAT THIS CLOSES.  Until this module existed the pull path had no claim at all:
``session_bridge.get_next_task`` filtered ready-and-assigned nodes and handed
the SAME node to every caller, so two live holders of one responsibility both
believed they owned it.  The compiler's ``work_item_started`` overlay could not
help — the only producer of that event sent a ``task_ref`` and never the
``task_id``/``outcome_id`` pair the overlay keys on, so a started event had
never once been applied.

THE SHAPE, and why it is this one.

* **Storage is the event ledger, and nothing else.**  The work-graph status
  overlay is already replay-derived; a claims table would be a SECOND truth
  that can disagree with the first, and this tree has shipped one such dead
  twin before.  Liveness is therefore a question asked of the ledger: the
  latest ``work_item_started`` for a task that carries a ``claim_id``, with no
  terminal event and no release after it, and an ``expires_at`` still in the
  future.

* **One lock across replay → decide → emit.**  The emitter's own per-file lock
  covers a single append; it cannot make check-then-act atomic, which is
  exactly why two claimers both succeed without this.  The lock file lives in
  the ledger directory and is resolved through the emitter's OWN resolver, so
  the pytest ledger fence covers it too.

* **A lease, not a heartbeat.**  Expiry is computed from ledger timestamps.
  There is no timer, no daemon and nothing to keep alive: a holder that dies
  stops renewing, and the task returns to the ready set the moment the lease
  runs out.  The default is 900 s — three wake cadences of the 300 s tick the
  pull path actually runs at — and every tick that finds the holder's own live
  claim renews it.

* **The token is unguessable.**  ``claim_id`` is a uuid4 minted at the instant
  the started event is emitted.  A sequential ``#n`` token would be forgeable
  by any process that can count, and the token is the credential a completion
  is fenced on.

* **Nothing here raises into the pull path.**  A claim-path failure appends one
  line to ``claims.err`` beside the ledger and the caller gets ``None``; the
  officer's prompt hook must never die because a lock file was unwritable.

PYTHON 3.9.  Every module the locked session hook can import stays importable
and correct under 3.9 (the officer PATH's ``python3`` is 3.9 on the reference
box).  That means ``from __future__ import annotations``, no runtime ``X | Y``,
no ``match``, and no 3.10+ standard library.

Usage:
    from framework.missions import claims

    held = claims.claim("outcome-001-task-000", "outcome-001", holder)
    if held:
        claims.complete("outcome-001-task-000", "outcome-001", holder,
                        claim_id=held["claim_id"], status="done")

CLI:
    python3.12 -m framework.missions.claims claim|renew|complete|live --json
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

# Ensure framework root is importable (path-exec CLI producers)
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

# _event_log_dir is deliberately the EMITTER's resolver rather than a second
# copy of the same rule: the pytest ledger fence and CABINET_EVENT_LOG_DIR must
# resolve to one directory for the lock, the error file and the ledger, or a
# test would take a lock in one place and replay from another.
from framework.events.emitter import _event_log_dir, emit, replay  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default lease, in seconds.  Three wake cadences of the 300 s tick the pull
#: path runs at, so a tick that renews on every pass never loses a task, and a
#: killed holder's task returns within a quarter hour rather than a half hour.
DEFAULT_LEASE_SECONDS = 900

#: A lease shorter than a minute cannot survive one tick; one longer than a day
#: is indistinguishable from no lease at all.  MIN_LEASE_SECONDS is the
#: PRODUCTION floor and never moves.
MIN_LEASE_SECONDS = 60
MAX_LEASE_SECONDS = 86400

#: The hard minimum under every floor, override included: a lease of zero or
#: less is expired the instant it is minted, which is not a short lease but a
#: broken one.
ABSOLUTE_MIN_LEASE_SECONDS = 1

#: Env override for the default lease (the drill sets a short one).
LEASE_ENV = "CABINET_CLAIM_LEASE_SECONDS"

#: The ONLY sub-floor path (contract A2.9).  The acceptance drill exports 1 so
#: its kill-and-take-over stages run on 2-5 s leases and finish in seconds;
#: nothing in production sets it.  It can only ever LOWER the floor -- a value
#: above MIN_LEASE_SECONDS is clamped back down to it -- so no environment can
#: use this to lengthen a production lease, which is the liveness signal the
#: whole pull path reads.
LEASE_FLOOR_ENV = "CABINET_CLAIM_LEASE_FLOOR_SECONDS"

#: Env override for the holder identity (the germline bundle exports it).
WORKER_ID_ENV = "CABINET_WORKER_ID"

LOCK_FILENAME = ".work-claims.lock"
ERROR_FILENAME = "claims.err"

STARTED = "work_item_started"
RENEWED = "work_item_claim_renewed"
RELEASED = "work_item_claim_released"

#: Terminal events end a claim chain.  `verified` is here because a verified
#: node is DONE in the overlay; a claim on a done node is meaningless.
TERMINAL_EVENT_TYPES = (
    "work_item_completed",
    "work_item_failed",
    "work_item_verified",
)

#: Every event type the liveness replay needs, in one list so a caller cannot
#: replay a subset and derive a claim that is already released.
CLAIM_EVENT_TYPES: List[str] = [STARTED, RENEWED, RELEASED] + list(TERMINAL_EVENT_TYPES)

#: Release reasons.  `superseded` is reserved for a future takeover that is not
#: an expiry; nothing emits it in this unit.
RELEASE_REASONS = ("expired", "released", "superseded")

#: Refusal codes carried by ClaimRefused.
REFUSAL_CODES = ("stale_claim", "not_holder", "no_token", "already_terminal")


class ClaimRefused(Exception):
    """A completion was refused by the fence.  ``code`` is one of REFUSAL_CODES."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


# ---------------------------------------------------------------------------
# Clock — ONE helper, so nothing in the claim path invents its own now()
# ---------------------------------------------------------------------------


def utcnow() -> datetime:
    """The single clock for the claim path (timezone-aware UTC)."""
    return datetime.now(timezone.utc)


def parse_ts(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None."""
    if not value:
        return None
    if isinstance(value, datetime):
        stamp = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            stamp = datetime.fromisoformat(text)
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def is_expired(expires_at: Any, now: Optional[datetime] = None) -> bool:
    """True when *expires_at* parses and is at or before *now*.

    An unparseable or absent expiry is NOT expired: the legacy started shape
    carries no lease, and treating "no lease" as "expired" would make every
    historical started event resurrect its task.
    """
    stamp = parse_ts(expires_at)
    if stamp is None:
        return False
    return stamp <= (now or utcnow())


# ---------------------------------------------------------------------------
# Failure record — the pull path must never die on the claim path
# ---------------------------------------------------------------------------


def error_path() -> Path:
    """Where claim-path failures are recorded (beside the ledger)."""
    return _event_log_dir() / ERROR_FILENAME


def record_error(message: str) -> bool:
    """Append one line to ``claims.err``.  Best-effort; never raises.

    Returns True when the line landed.  The caller does not care — a claim
    path that raised here would be the very failure this file exists to
    absorb — but the sensors do.
    """
    try:
        target = error_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        line = "{0} {1}\n".format(utcnow().isoformat(), message)
        with open(str(target), "a", encoding="utf-8") as handle:
            handle.write(line)
        return True
    except Exception:  # noqa: BLE001 — a recorder that raises is worse than one that misses
        return False


# ---------------------------------------------------------------------------
# Holder identity
# ---------------------------------------------------------------------------


def _parent_of(pid: int) -> Optional[int]:
    """The parent pid of *pid*, or None when it cannot be determined."""
    proc_stat = Path("/proc") / str(pid) / "stat"
    try:
        if proc_stat.exists():
            # comm can contain spaces and parentheses; the ppid is the field
            # after the closing paren.
            raw = proc_stat.read_text()
            tail = raw.rsplit(")", 1)[-1].split()
            return int(tail[1])
    except Exception:  # noqa: BLE001 — fall through to ps
        pass
    try:
        out = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:  # noqa: BLE001 — no ps, no ancestry, weakened holder
        return None
    if out.returncode != 0:
        return None
    text = out.stdout.decode("utf-8", "replace").strip()
    if not text.isdigit():
        return None
    return int(text)


def session_pid() -> Optional[int]:
    """The pid of the process that spawned this process's parent.

    The locked hook runs a FRESH python every tick, and the hook shell is fresh
    with it, so neither is stable.  The process above them — the session that
    fires the hook — is stable for the life of that session and distinct
    between two sessions of one role, which is exactly the identity a claim
    needs.  Returns None when the ancestry cannot be read.
    """
    try:
        parent = os.getppid()
    except Exception:  # noqa: BLE001
        return None
    if parent <= 1:
        return None
    grandparent = _parent_of(parent)
    if grandparent is None or grandparent <= 1:
        return None
    return grandparent


def derive_holder(role_slug: str) -> str:
    """Derive the holder identity for *role_slug*.

    ``CABINET_WORKER_ID`` wins when set (the germline bundle exports a
    session-scoped id).  Otherwise the holder is ``<role>@session:<pid>`` of the
    session process, so two live sessions of one role are distinguishable with
    no ceremony.  When the ancestry cannot be read the holder weakens to the
    bare role slug — two sessions would then share it — and the weakening is
    written down rather than assumed away.
    """
    explicit = os.environ.get(WORKER_ID_ENV)
    if explicit and explicit.strip():
        return explicit.strip()
    pid = session_pid()
    if pid is not None:
        return "{0}@session:{1}".format(role_slug, pid)
    record_error(
        "holder weakened to the bare role slug {0!r}: the session process could "
        "not be resolved, so two sessions of this role share one identity".format(
            role_slug
        )
    )
    return role_slug


# ---------------------------------------------------------------------------
# Lock + lease
# ---------------------------------------------------------------------------


def lock_path() -> Path:
    """The claims lock file, in the ledger's own directory."""
    return _event_log_dir() / LOCK_FILENAME


@contextlib.contextmanager
def claims_lock() -> Iterator[None]:
    """Hold LOCK_EX across replay → decide → emit.

    The emitter's per-file lock nests inside this one and covers one append;
    only this lock makes check-then-act atomic.  Reads take no lock.
    """
    log_dir = _event_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(log_dir / LOCK_FILENAME), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def resolve_lease_floor() -> int:
    """The smallest lease :func:`resolve_lease` will hand back, in seconds.

    MIN_LEASE_SECONDS unless ``CABINET_CLAIM_LEASE_FLOOR_SECONDS`` lowers it,
    and then never below ABSOLUTE_MIN_LEASE_SECONDS and never above
    MIN_LEASE_SECONDS.  Unset, empty and unparseable all mean the production
    floor: a drill that mistypes its floor gets a slow honest run, never a
    silent one-second lease that expires under its own stages.
    """
    raw = os.environ.get(LEASE_FLOOR_ENV)
    if raw is None or not str(raw).strip():
        return MIN_LEASE_SECONDS
    try:
        floor = int(str(raw).strip())
    except ValueError:
        record_error(
            "{0}={1!r} is not an integer; using the {2} s floor".format(
                LEASE_FLOOR_ENV, raw, MIN_LEASE_SECONDS
            )
        )
        return MIN_LEASE_SECONDS
    if floor < ABSOLUTE_MIN_LEASE_SECONDS:
        return ABSOLUTE_MIN_LEASE_SECONDS
    if floor > MIN_LEASE_SECONDS:
        return MIN_LEASE_SECONDS
    return floor


def resolve_lease(lease_s: Optional[int] = None) -> int:
    """Resolve the lease in seconds, clamped to [floor, MAX].

    The floor is MIN_LEASE_SECONDS in production and only the drill's env
    lowers it (:func:`resolve_lease_floor`).
    """
    if lease_s is None:
        raw = os.environ.get(LEASE_ENV)
        if raw is not None and str(raw).strip():
            try:
                lease_s = int(str(raw).strip())
            except ValueError:
                record_error(
                    "{0}={1!r} is not an integer; using the {2} s default".format(
                        LEASE_ENV, raw, DEFAULT_LEASE_SECONDS
                    )
                )
                lease_s = DEFAULT_LEASE_SECONDS
        else:
            lease_s = DEFAULT_LEASE_SECONDS
    lease_s = int(lease_s)
    floor = resolve_lease_floor()
    if lease_s < floor:
        return floor
    if lease_s > MAX_LEASE_SECONDS:
        return MAX_LEASE_SECONDS
    return lease_s


# ---------------------------------------------------------------------------
# Replay-derived state
# ---------------------------------------------------------------------------


def _claim_from_started(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = event.get("payload") or {}
    return {
        "claim_id": payload.get("claim_id"),
        "task_id": payload.get("task_id"),
        "outcome_id": payload.get("outcome_id"),
        "holder": payload.get("holder"),
        "actor": event.get("actor"),
        "started_at": payload.get("started_at") or event.get("created_at"),
        "lease_s": payload.get("lease_s"),
        "expires_at": payload.get("expires_at"),
        "renewals": 0,
    }


def replay_states() -> Dict[str, Dict[str, Any]]:
    """Per-task claim state derived from the ledger, newest chain wins.

    ``{task_id: {"claim": Claim|None, "terminal": bool, "released": bool}}``.
    A ``work_item_started`` with no ``claim_id`` is the legacy hook shape: it is
    IGNORED for liveness (it can neither open nor close a claim), because it
    carries no lease, no holder and no token to fence on.
    """
    states: Dict[str, Dict[str, Any]] = {}
    for event in replay(event_types=CLAIM_EVENT_TYPES):
        payload = event.get("payload") or {}
        task_id = payload.get("task_id")
        if not task_id:
            continue
        kind = event.get("event_type")
        state = states.setdefault(
            task_id, {"claim": None, "terminal": False, "released": False}
        )
        if kind == STARTED:
            if not payload.get("claim_id"):
                continue  # legacy shape — invisible to the claim plane
            state["claim"] = _claim_from_started(event)
            state["terminal"] = False
            state["released"] = False
        elif kind == RENEWED:
            claim = state["claim"]
            if claim is not None and claim["claim_id"] == payload.get("claim_id"):
                if payload.get("expires_at"):
                    claim["expires_at"] = payload["expires_at"]
                if payload.get("lease_s") is not None:
                    claim["lease_s"] = payload["lease_s"]
                claim["renewals"] = int(claim.get("renewals") or 0) + 1
        elif kind == RELEASED:
            claim = state["claim"]
            if claim is not None and claim["claim_id"] == payload.get("claim_id"):
                state["released"] = True
        else:  # a terminal event
            state["terminal"] = True
    return states


def _live_from_state(
    state: Optional[Dict[str, Any]], now: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    if not state:
        return None
    claim = state.get("claim")
    if claim is None or state.get("terminal") or state.get("released"):
        return None
    if is_expired(claim.get("expires_at"), now):
        return None
    return dict(claim)


def live_claim(task_id: str, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """The live claim on *task_id*, or None."""
    return _live_from_state(replay_states().get(task_id), now)


def live_claims(now: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
    """Every live claim, keyed by task id."""
    out: Dict[str, Dict[str, Any]] = {}
    for task_id, state in replay_states().items():
        claim = _live_from_state(state, now)
        if claim is not None:
            out[task_id] = claim
    return out


def latest_claim_id(task_id: str) -> Optional[str]:
    """The most recent claim token minted for *task_id*, live or not.

    The fence compares against THIS, not against liveness: a token from a claim
    that has since expired is stale, and a completion carrying it must be
    refused rather than silently accepted because nobody holds the task now.
    """
    state = replay_states().get(task_id)
    if not state or not state.get("claim"):
        return None
    return state["claim"]["claim_id"]


# ---------------------------------------------------------------------------
# The claim primitives
# ---------------------------------------------------------------------------


def claim(
    task_id: str,
    outcome_id: str,
    holder: str,
    *,
    actor: Optional[str] = None,
    lease_s: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Claim *task_id* for *holder*, or return None when someone else holds it.

    Idempotent for the holder: a second call while its own claim is live
    returns that claim and emits nothing.  Taking over an EXPIRED claim emits
    ``work_item_claim_released{reason: expired}`` for the previous holder under
    the same lock, so the ledger records who lost the task and why.
    """
    lease = resolve_lease(lease_s)
    with claims_lock():
        moment = now or utcnow()
        states = replay_states()
        state = states.get(task_id)
        existing = _live_from_state(state, moment)
        if existing is not None:
            if existing.get("holder") == holder:
                return existing
            return None
        if state and state.get("terminal"):
            return None  # a finished task is not claimable
        previous = (state or {}).get("claim")
        if previous is not None and not (state or {}).get("released"):
            emit(
                RELEASED,
                actor=actor or holder,
                payload={
                    "task_id": task_id,
                    "outcome_id": previous.get("outcome_id") or outcome_id,
                    "claim_id": previous.get("claim_id"),
                    "holder": previous.get("holder"),
                    "reason": "expired",
                },
            )
        claim_id = str(uuid.uuid4())
        expires_at = moment + timedelta(seconds=lease)
        payload = {
            "task_id": task_id,
            "outcome_id": outcome_id,
            "claim_id": claim_id,
            "holder": holder,
            "actor": actor or holder,
            "started_at": moment.isoformat(),
            "lease_s": lease,
            "expires_at": expires_at.isoformat(),
        }
        emit(STARTED, actor=actor or holder, payload=payload)
        return {
            "claim_id": claim_id,
            "task_id": task_id,
            "outcome_id": outcome_id,
            "holder": holder,
            "actor": actor or holder,
            "started_at": payload["started_at"],
            "lease_s": lease,
            "expires_at": payload["expires_at"],
            "renewals": 0,
        }


def renew(
    claim_id: str,
    holder: str,
    *,
    lease_s: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Extend *claim_id* for *holder*, or return None.

    None when the token is not the task's latest, the holder does not match, the
    task is terminal or released, or the lease already ran out — an expired
    claim is gone, and letting its holder renew it would make the lease
    something other than the liveness signal.
    """
    lease = resolve_lease(lease_s)
    with claims_lock():
        moment = now or utcnow()
        for task_id, state in replay_states().items():
            current = state.get("claim")
            if current is None or current.get("claim_id") != claim_id:
                continue
            if state.get("terminal") or state.get("released"):
                return None
            if current.get("holder") != holder:
                return None
            if is_expired(current.get("expires_at"), moment):
                return None
            expires_at = moment + timedelta(seconds=lease)
            emit(
                RENEWED,
                actor=current.get("actor") or holder,
                payload={
                    "task_id": task_id,
                    "outcome_id": current.get("outcome_id"),
                    "claim_id": claim_id,
                    "holder": holder,
                    "lease_s": lease,
                    "expires_at": expires_at.isoformat(),
                    "renewals": int(current.get("renewals") or 0) + 1,
                },
            )
            renewed = dict(current)
            renewed["lease_s"] = lease
            renewed["expires_at"] = expires_at.isoformat()
            renewed["renewals"] = int(current.get("renewals") or 0) + 1
            return renewed
        return None


def release(claim_id: str, holder: str, reason: str) -> bool:
    """Give up *claim_id*.  Returns True when a release was recorded.

    Internal: no CLI verb exposes this.  The pull path never releases (the
    lease does that for it); a release exists so a takeover can name the
    previous holder, and so a caller that knows it is done can hand the task
    back before its lease runs out.
    """
    if reason not in RELEASE_REASONS:
        raise ValueError(
            "release reason must be one of {0}: {1!r}".format(RELEASE_REASONS, reason)
        )
    with claims_lock():
        for task_id, state in replay_states().items():
            current = state.get("claim")
            if current is None or current.get("claim_id") != claim_id:
                continue
            if state.get("terminal") or state.get("released"):
                return False
            if current.get("holder") != holder:
                return False
            emit(
                RELEASED,
                actor=current.get("actor") or holder,
                payload={
                    "task_id": task_id,
                    "outcome_id": current.get("outcome_id"),
                    "claim_id": claim_id,
                    "holder": holder,
                    "reason": reason,
                },
            )
            return True
        return False


def complete(
    task_id: str,
    outcome_id: str,
    holder: Optional[str] = None,
    *,
    claim_id: Optional[str] = None,
    status: str = "done",
    evidence_text: Optional[str] = None,
    evidence_path: Optional[str] = None,
    task_index: Optional[int] = None,
    actor: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Record a completion, fenced on the claim token.  Raises ClaimRefused.

    The fence, in order:

    * ``already_terminal`` — the task already has a terminal event.
    * ``stale_claim`` — a token was supplied and it is NOT the task's latest
      claim token.  Liveness is deliberately not consulted: a token from a
      claim that has since expired is stale, and accepting it because nobody
      holds the task now is the classic lost-update.
    * ``not_holder`` — a holder was asserted and it is not the claim's holder.
      A caller that supplies a valid token and no holder is trusted BY THE
      TOKEN; the token is the credential, and the holder identity a shell
      completion can derive is not stable enough to be one.
    * ``no_token`` — a live claim exists and no token was supplied.
    * otherwise allowed.  No live claim and no token is the COMPATIBILITY path
      for callers that predate claims; it is flipped to fail-closed once every
      pull carries a claim.
    """
    if status not in ("done", "failed"):
        raise ValueError("status must be 'done' or 'failed': {0!r}".format(status))
    event_type = "work_item_completed" if status == "done" else "work_item_failed"
    with claims_lock():
        moment = now or utcnow()
        state = replay_states().get(task_id)
        if state and state.get("terminal"):
            raise ClaimRefused(
                "already_terminal",
                "task {0} already carries a terminal event".format(task_id),
            )
        current = (state or {}).get("claim")
        latest = current.get("claim_id") if current else None
        live = _live_from_state(state, moment)
        if claim_id is not None:
            if claim_id != latest:
                raise ClaimRefused(
                    "stale_claim",
                    "claim {0} is not the latest claim on {1}".format(claim_id, task_id),
                )
            if holder is not None and current is not None and current.get("holder") != holder:
                raise ClaimRefused(
                    "not_holder",
                    "{0} does not hold claim {1}".format(holder, claim_id),
                )
        elif live is not None:
            raise ClaimRefused(
                "no_token",
                "task {0} is claimed by {1}; supply --claim".format(
                    task_id, live.get("holder")
                ),
            )
        payload = {
            "task_id": task_id,
            "outcome_id": outcome_id,
            "status": status,
            "claim_id": claim_id,
            "holder": holder or (current.get("holder") if current else None),
            "evidence_text": evidence_text or None,
            "evidence_path": evidence_path or None,
        }
        if task_index is not None:
            payload["task_index"] = int(task_index)
        return emit(event_type, actor=actor or holder or "system", payload=payload)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit_json(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, default=str))
    elif obj is not None:
        print(obj if isinstance(obj, str) else json.dumps(obj, indent=2, default=str))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claims",
        description="Atomic task claims with a lease, derived from the event ledger.",
    )
    # --json lives on the VERBS, not on the top level. Defined in both places
    # argparse would let the subparser's default silently overwrite a flag the
    # caller passed before the verb, which is a flag that reads as accepted and
    # does nothing.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="verb", required=True)

    take = sub.add_parser("claim", help="claim a task", parents=[common])
    take.add_argument("--task-id", required=True)
    take.add_argument("--outcome-id", required=True)
    take.add_argument("--holder")
    take.add_argument("--role")
    take.add_argument("--actor")
    take.add_argument("--lease-s", type=int)

    again = sub.add_parser("renew", help="extend a claim", parents=[common])
    again.add_argument("--claim", required=True, dest="claim_id")
    again.add_argument("--holder", required=True)
    again.add_argument("--lease-s", type=int)

    done = sub.add_parser(
        "complete", help="record a completion, fenced on the token", parents=[common]
    )
    done.add_argument("--task-id", required=True)
    done.add_argument("--outcome-id", required=True)
    done.add_argument("--holder")
    done.add_argument("--claim", dest="claim_id")
    done.add_argument("--status", default="done", choices=["done", "failed"])
    done.add_argument("--evidence-text")
    done.add_argument("--evidence-path")
    done.add_argument("--task-index", type=int)
    done.add_argument("--actor")

    sub.add_parser("live", help="print every live claim", parents=[common])

    args = parser.parse_args(argv)

    if args.verb == "claim":
        holder = args.holder or derive_holder(args.role or args.actor or "unknown")
        held = claim(
            args.task_id,
            args.outcome_id,
            holder,
            actor=args.actor,
            lease_s=args.lease_s,
        )
        _emit_json(held, args.json)
        return 0 if held else 3

    if args.verb == "renew":
        renewed = renew(args.claim_id, args.holder, lease_s=args.lease_s)
        _emit_json(renewed, args.json)
        return 0 if renewed else 3

    if args.verb == "complete":
        try:
            event = complete(
                args.task_id,
                args.outcome_id,
                args.holder,
                claim_id=args.claim_id,
                status=args.status,
                evidence_text=args.evidence_text,
                evidence_path=args.evidence_path,
                task_index=args.task_index,
                actor=args.actor,
            )
        except ClaimRefused as refused:
            sys.stderr.write("claims: refused ({0}) {1}\n".format(refused.code, refused))
            _emit_json({"refused": refused.code}, args.json)
            return 4
        _emit_json(event, args.json)
        return 0

    _emit_json(live_claims(), args.json)
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    sys.exit(main())
