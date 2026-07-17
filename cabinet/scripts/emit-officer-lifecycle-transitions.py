#!/usr/bin/env python3.12
"""emit-officer-lifecycle-transitions.py — officer session lifecycle receipts.

WHY (evidence program Phase 2 Batch B, 2026-07-17): officer session
lifecycle is produced by GERMLINE hooks (cabinet/scripts/hooks/ — schg-
locked), and the classes those hooks emit (session_started has no live
emitter at all; session_ended rides a 3.9 path-exec that structurally never
reaches the org→evidence mirror) are pinned nervous-system EXHAUST
(framework/evidence_mirror.py NEVER_MIRRORED_EXHAUST) — ~94% of live org
volume, never to be widened into the mirror. So lifecycle evidence comes
from the house pattern for observing an schg-locked surface from an
UNLOCKED caller (precedent: cabinet/scripts/emit-graduation-transitions.py):
a state-diff sweep that emits NEW officer-scoped TRANSITION classes which
the Batch A org→evidence mirror signs.

WHAT IT OBSERVES (all read-only):
  * tmux sessions named ``officer-<slug>`` (helper ``-inbound``/``-outbound``
    panes excluded) — the officer's session container;
  * Redis ``cabinet:heartbeat:liveness:<slug>`` (SET by the germline
    session-start hook at boot, TTL 30min, tool-call refreshed);
  * Redis ``cabinet:session:terminated:<slug>`` = ``<ts>|reason=<reason>``
    (SET by the germline on-session-end hook, TTL 24h) — the clean-end
    stamp, carried verbatim in the receipt payload for joinability with the
    hook's generic session_ended exhaust row;
  * ``instance/memory/tier2/<slug>/.session-state.json`` ``captured_at``
    (written by the germline pre-compact hook) — the compaction signal.
    The JSON field is read, never the file mtime (deterministic, no
    GNU/BSD stat divergence).

WHAT IT EMITS (transitions ONLY — never per-poll rows, the 59%-plumbing
law): ``officer_session_started`` / ``officer_session_ended`` (reason from
the terminated stamp; ``reason="unobserved"`` when the session vanishes
without a stamp — crash/kill, no hook fired) / ``officer_session_compacted``.
Scoping decision (named): restart receipts belong to
cabinet/cron/heartbeat-watchdog.sh (the actor that kickstarts) and limit
wakes to cabinet/cron/limit-reset-watchdog.sh — this sweep deliberately
does not double-record those verbs. A restart that completes between two
sweeps is cadence-quantized (may appear as nothing, or as ended+started).

RECORDING CLASS: RECEIPT — everything here already happened. Emits are
best-effort per transition; a broken evidence plane degrades LOUD inside
the emitter's mirror chokepoint and never blocks anything (this sweep
takes no actions at all).

FAIL-SAFE INVARIANTS (the graduation-transitions idiom):
  * A probe error is UNOBSERVABLE, never a state change: tmux/Redis/state-
    file read failures carry the previous state forward and emit nothing —
    an outage must never read as a fleet-wide session-end storm.
  * FIRST RUN (no state file) seeds the baseline WITHOUT emitting. Officers
    appearing after the baseline emit ``first_sighting: true``.
  * Delivery is AT-LEAST-ONCE: a transition whose emit failed reverts that
    officer's remembered field so the same transition re-detects next
    sweep. Consumers must tolerate duplicates.
  * Crash-loop storm guard: at most MAX_EMITS_PER_OFFICER_PER_DAY receipts
    per officer per UTC day (KeepAlive + ThrottleInterval=30 can cycle a
    wedged officer ~2880x/day; the mirror's day-trial cap is shared
    estate-wide). Over-cap transitions are DROPPED loudly (state still
    advances) — the cap exists to stop a storm, not to queue it.

Everything is read-only except the state file + org-event appends via the
existing validated emitter (imported in-module so the org→evidence mirror
fires in-process). No network beyond localhost Redis via redis-cli; no
secrets; no argv secrets. python3.12 (house interpreter).

Run:      python3.12 cabinet/scripts/emit-officer-lifecycle-transitions.py
              [--dry-run] [--state-file PATH]
Schedule: cabinet/services.yml row ``officer-lifecycle-transitions``
          (ships disabled — the Batch B ceremony enables it).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

ACTOR = "officer-lifecycle-sweep"
EVENT_STARTED = "officer_session_started"
EVENT_ENDED = "officer_session_ended"
EVENT_COMPACTED = "officer_session_compacted"
LIFECYCLE_EVENT_TYPES = frozenset({EVENT_STARTED, EVENT_ENDED, EVENT_COMPACTED})

#: Crash-loop storm guard. CODE constant by law — never an env var, never a
#: config dial (no env var may bear fuel, A10).
MAX_EMITS_PER_OFFICER_PER_DAY = 24

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

_DEFAULT_STATE_FILE = os.path.expanduser(
    "~/Library/Application Support/cabinet/state/officer-lifecycle.json")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_TMUX_NO_SERVER_RE = re.compile(r"no server running|error connecting",
                                re.IGNORECASE)

LIVENESS_PREFIX = "cabinet:heartbeat:liveness:"
TERMINATED_PREFIX = "cabinet:session:terminated:"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def state_file_path(cli_override: Optional[str] = None) -> Path:
    """CLI flag > env override (fenced tests) > the unlocked live default
    (the exact precedent of emit-graduation-transitions.py — the override
    steers only this sweep's own memory, never what is recorded or where
    evidence lands)."""
    return Path(cli_override
                or os.environ.get("CABINET_OFFICER_LIFECYCLE_STATE_FILE")
                or _DEFAULT_STATE_FILE)


def _valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug)) and not slug.endswith(
        ("-inbound", "-outbound"))


# ---------------------------------------------------------------------------
# Probes — every failure degrades to None (UNOBSERVABLE), never a phantom
# observation. Subprocesses use list argv only (no shell interpolation).
# ---------------------------------------------------------------------------

def _run(cmd: List[str], timeout: int = 10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except Exception:
        return None


def _redis(*args: str) -> Optional[str]:
    """redis-cli stdout (stripped), or None when Redis is unobservable."""
    r = _run(["redis-cli", "-h", REDIS_HOST, "-p", REDIS_PORT, *args])
    if r is None or r.returncode != 0:
        return None
    return (r.stdout or "").strip()


def redis_reachable() -> bool:
    return _redis("-t", "2", "PING") == "PONG"


def tmux_officer_sessions() -> Optional[Set[str]]:
    """Officer slugs with a live tmux session, () when the server reports no
    sessions, None when tmux is UNOBSERVABLE (missing binary / ambiguous
    error — never inferred as 'everything ended')."""
    r = _run(["tmux", "list-sessions", "-F", "#{session_name}"])
    if r is None:
        return None
    if r.returncode != 0:
        if _TMUX_NO_SERVER_RE.search(r.stderr or ""):
            return set()  # a real observation: the server holds no sessions
        return None
    out: Set[str] = set()
    for line in (r.stdout or "").splitlines():
        name = line.strip()
        if not name.startswith("officer-"):
            continue
        slug = name[len("officer-"):]
        if _valid_slug(slug):
            out.add(slug)
    return out


def redis_officer_keys(prefix: str) -> Optional[Set[str]]:
    out = _redis("KEYS", prefix + "*")
    if out is None:
        return None
    slugs: Set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            slug = line[len(prefix):]
            if _valid_slug(slug):
                slugs.add(slug)
    return slugs


def session_state_captured_at(officer: str) -> Optional[str]:
    """The pre-compact hook's captured_at JSON field — deterministic, never
    the file mtime (no stat, no GNU/BSD divergence). None = absent or
    unreadable (unobservable)."""
    path = (_REPO_ROOT / "instance" / "memory" / "tier2" / officer
            / ".session-state.json")
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    value = doc.get("captured_at") if isinstance(doc, dict) else None
    return value if isinstance(value, str) and value else None


def roster_slugs() -> Set[str]:
    out: Set[str] = set()
    roles = _REPO_ROOT / "instance" / "roles" / "active"
    if roles.is_dir():
        for yml in sorted(roles.glob("*.yml")):
            slug = yml.stem
            if slug != "TEMPLATE" and _valid_slug(slug):
                out.add(slug)
    return out


def observe(officer: str, tmux_set: Optional[Set[str]],
            redis_ok: bool) -> Dict[str, Any]:
    """One officer's observation snapshot.

    running:     True | False | None(unobservable). False ONLY when tmux was
                 genuinely observed absent AND liveness is not fresh — a
                 liveness expiry alone is an idle officer, never a death
                 (the heartbeat-watchdog B3 lesson).
    terminated:  the stamp string ('' = no stamp) | None(unobservable).
    captured_at: compaction stamp | None(absent/unreadable).
    """
    liveness: Optional[bool] = None
    terminated: Optional[str] = None
    if redis_ok:
        exists = _redis("EXISTS", LIVENESS_PREFIX + officer)
        if exists in ("0", "1"):
            liveness = exists == "1"
        stamp = _redis("GET", TERMINATED_PREFIX + officer)
        if stamp is not None:
            terminated = "" if stamp == "(nil)" else stamp
    if tmux_set is not None:
        running: Optional[bool] = (officer in tmux_set) or (liveness is True)
    else:
        running = True if liveness is True else None
    return {
        "running": running,
        "terminated": terminated,
        "captured_at": session_state_captured_at(officer),
    }


# ---------------------------------------------------------------------------
# Pure transition detection — the unit tests' seam (no IO, no emits).
# ---------------------------------------------------------------------------

def parse_terminated_stamp(stamp: str) -> Tuple[str, str]:
    """'<ts>|reason=<reason>' -> (ts, reason); tolerant of missing parts."""
    ts, _, rest = stamp.partition("|")
    if rest.startswith("reason="):
        reason = rest[len("reason="):] or "unknown"
    else:
        reason = rest or "unknown"
    return ts, reason


def sweep(observed: Dict[str, Dict[str, Any]],
          prev: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """Diff observations against last-seen state.

    Returns {"current": {officer: state}, "transitions": [t...],
    "baseline": bool}. Each transition carries type/payload plus a
    ``revert`` (officer, field, previous_value) triple for the at-least-once
    contract. An unobservable probe (None) carries the previous state
    forward and can never produce a transition.
    """
    baseline = prev is None
    prev_map: Dict[str, Dict[str, Any]] = dict(prev or {})
    officers = sorted(set(observed) | set(prev_map))

    current: Dict[str, Dict[str, Any]] = {}
    transitions: List[Dict[str, Any]] = []

    for officer in officers:
        obs = observed.get(officer) or {
            "running": None, "terminated": None, "captured_at": None}
        po = prev_map.get(officer)
        first_sighting = po is None
        prev_running = bool(po.get("running")) if po else False
        prev_term = str(po.get("terminated") or "") if po else ""
        prev_cap = str(po.get("captured_at") or "") if po else ""

        running_obs = obs.get("running")      # True | False | None
        term_obs = obs.get("terminated")      # str ('' = no stamp) | None
        cap_obs = obs.get("captured_at")      # str | None

        # Remembered values: an unobservable/expired probe never erases
        # memory — the stamp only advances what we know.
        term_now = term_obs if term_obs else prev_term
        cap_now = cap_obs if cap_obs is not None else prev_cap
        running_now = prev_running if running_obs is None else bool(running_obs)

        # 1. Clean end — a NEW terminated stamp (hook-observed, has reason).
        if term_obs and term_obs != prev_term and not first_sighting:
            ended_at, reason = parse_terminated_stamp(term_obs)
            transitions.append({
                "type": EVENT_ENDED,
                "payload": {
                    "officer": officer,
                    "reason": reason,
                    "ended_at": ended_at,
                    # verbatim stamp for joinability with the hook's generic
                    # session_ended exhaust row (named duplication)
                    "stamp": term_obs,
                    "observed_via": "terminated-stamp",
                },
                "revert": (officer, "terminated", prev_term),
            })
        # 2. Crash end — observed down (tmux absent + liveness not fresh),
        #    was running, and no fresh stamp explains it (no hook fired).
        elif running_obs is False and prev_running and not first_sighting:
            transitions.append({
                "type": EVENT_ENDED,
                "payload": {
                    "officer": officer,
                    "reason": "unobserved",
                    "ended_at": None,
                    "stamp": None,
                    "observed_via": "tmux-absent",
                },
                "revert": (officer, "running", True),
            })

        # 3. Start — observed running where we last knew not-running.
        if running_obs is True and not prev_running:
            transitions.append({
                "type": EVENT_STARTED,
                "payload": {
                    "officer": officer,
                    "first_sighting": first_sighting,
                    "observed_via": "tmux-or-liveness",
                },
                "revert": (officer, "running", False),
            })

        # 4. Compaction — captured_at advanced (first sighting of the field
        #    is a silent baseline, not a transition).
        if cap_obs and prev_cap and cap_obs != prev_cap and not first_sighting:
            transitions.append({
                "type": EVENT_COMPACTED,
                "payload": {"officer": officer, "captured_at": cap_obs},
                "revert": (officer, "captured_at", prev_cap),
            })

        current[officer] = {
            "running": running_now,
            "terminated": term_now,
            "captured_at": cap_now,
        }

    return {"current": current, "transitions": transitions,
            "baseline": baseline}


# ---------------------------------------------------------------------------
# State file — atomic rewrite, corrupt file re-seeds (flood guard).
# ---------------------------------------------------------------------------

def load_state(path: Path) -> Optional[Dict[str, Any]]:
    """The whole state doc, or None for BASELINE (missing/corrupt file —
    re-seed silently rather than emit N bogus transitions against broken
    memory)."""
    try:
        with open(path) as f:
            doc = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        print("emit-officer-lifecycle-transitions: WARN state file "
              "unreadable — re-seeding baseline", file=sys.stderr)
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("officers"), dict):
        return None
    return doc


def write_state(path: Path, officers: Dict[str, Dict[str, Any]],
                emit_counts: Dict[str, int], emit_date: str,
                now_iso: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "updated_at": now_iso,
        "officers": officers,
        "emit_date": emit_date,
        "emit_counts": emit_counts,
    }
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".officer-lc-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f, ensure_ascii=False, sort_keys=True, indent=1)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Detect + emit officer session lifecycle transitions "
                    "into org_events (see module docstring).")
    ap.add_argument("--dry-run", action="store_true",
                    help="print would-be transitions; emit nothing, write "
                         "no state")
    ap.add_argument("--state-file", default=None,
                    help="override the last-seen state file path")
    args = ap.parse_args(argv)

    now = _now()
    now_iso = _iso(now)
    today = now.strftime("%Y%m%d")

    # Mirror allow-list self-check — LOUD, never blocking: a lifecycle class
    # dropped from the allow-list would land org rows UNSIGNED; the daily
    # digest-anchor still covers the breadth ledger, but a human must see it.
    try:
        from framework import evidence_mirror
        missing = LIFECYCLE_EVENT_TYPES - evidence_mirror.MIRRORED_ORG_EVENT_TYPES
        if missing:
            print("emit-officer-lifecycle-transitions: WARN lifecycle "
                  "class(es) missing from the evidence-mirror allow-list — "
                  "org rows land UNSIGNED: %s" % ", ".join(sorted(missing)),
                  file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — self-check only, never fatal
        print("emit-officer-lifecycle-transitions: WARN mirror self-check "
              "unavailable: %s" % exc, file=sys.stderr)

    path = state_file_path(args.state_file)
    doc = load_state(path)
    prev = None if doc is None else doc.get("officers", {})

    redis_ok = redis_reachable()
    tmux_set = tmux_officer_sessions()

    officers: Set[str] = roster_slugs() | set(prev or {})
    if tmux_set:
        officers |= tmux_set
    if redis_ok:
        for prefix in (LIVENESS_PREFIX, TERMINATED_PREFIX):
            found = redis_officer_keys(prefix)
            if found:
                officers |= found

    observed = {o: observe(o, tmux_set, redis_ok) for o in sorted(officers)}
    result = sweep(observed, prev)

    emit_counts: Dict[str, int] = {}
    if doc is not None and doc.get("emit_date") == today:
        raw_counts = doc.get("emit_counts")
        if isinstance(raw_counts, dict):
            emit_counts = {
                k: v for k, v in raw_counts.items()
                if isinstance(k, str) and isinstance(v, int)
            }

    suppress = result["baseline"]
    emitted = 0
    emit_failures = 0
    capped: List[str] = []

    if args.dry_run:
        for t in result["transitions"]:
            print("[dry-run] %s %s" % (
                t["type"], json.dumps(t["payload"], sort_keys=True)))
    elif suppress:
        # Flood guard: first sighting of the whole estate is a SEED, not N
        # transitions — the state file becomes the baseline silently.
        pass
    else:
        from framework.events.emitter import emit
        for t in result["transitions"]:
            officer = t["payload"]["officer"]
            if emit_counts.get(officer, 0) >= MAX_EMITS_PER_OFFICER_PER_DAY:
                if officer not in capped:
                    capped.append(officer)
                continue  # DROP (state still advances) — cap stops storms
            try:
                emit(t["type"], actor=ACTOR, payload=t["payload"])
                emitted += 1
                emit_counts[officer] = emit_counts.get(officer, 0) + 1
            except Exception as exc:  # noqa: BLE001
                emit_failures += 1
                # At-least-once: revert the remembered field so the SAME
                # transition re-detects and re-emits on the next sweep.
                rev_officer, field, prev_value = t["revert"]
                result["current"].setdefault(rev_officer, {})[field] = prev_value
                print("emit-officer-lifecycle-transitions: WARN emit failed "
                      "for %s/%s: %s" % (rev_officer, t["type"], exc),
                      file=sys.stderr)
        for officer in capped:
            print("emit-officer-lifecycle-transitions: WARN daily emit cap "
                  "(%d) reached for %s — dropping further transitions today "
                  "(crash-loop storm guard)"
                  % (MAX_EMITS_PER_OFFICER_PER_DAY, officer), file=sys.stderr)

    if not args.dry_run:
        try:
            write_state(path, result["current"], emit_counts, today, now_iso)
        except OSError as exc:
            print("emit-officer-lifecycle-transitions: state write failed: "
                  "%s" % exc, file=sys.stderr)
            return 1

    summary = {
        "ts": now_iso,
        "officers": len(result["current"]),
        "transitions": len(result["transitions"]),
        "emitted": emitted,
        "emit_failures": emit_failures,
        "capped_officers": len(capped),
        "baseline_seeded": bool(suppress and not args.dry_run),
        "redis_observed": bool(redis_ok),
        "tmux_observed": tmux_set is not None,
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
