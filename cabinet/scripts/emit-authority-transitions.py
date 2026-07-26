#!/usr/bin/env python3
"""emit-authority-transitions.py — make control-plane state CHANGES visible.

WHY (evidence program Phase 2 Batch B, R-1 authority/control-plane producer;
whole-cabinet evidence design 2026-07-16 §7 R-1): the org's hardest authority
facts — the kill switch, the germline lock boundary, the effective posture —
live in surfaces that are either germline-locked (cabinet/scripts/
kill-switch.sh, germline-lock.sh) or deliberately event-silent, so NOTHING in
the org ever recorded the MOMENT the kill switch flipped, a germline unlock
window opened/closed, or the effective posture changed.  The kill-switch and
lock scripts must never be edited for telemetry (a pure-bash emergency brake
whose fail-closed contract must never depend on python — §2.6: a tightening
is never evidence-gated), so the transition detector lives in this UNLOCKED
caller — the exact idiom of cabinet/scripts/emit-graduation-transitions.py
(the house precedent for observing an schg-locked surface from an unlocked
sweep).

WHAT IT DOES (one pass):
  1. OBSERVES (all read-only):
       * kill switch — redis GET cabinet:killswitch (REDIS_URL parse identical
         to kill-switch.sh, including the docker-DNS `redis`-host residue
         guard).  Values other than "active" read as inactive, matching the
         status verb.
       * germline boundary — the FILES=()/DIRS=() lock set parsed read-only
         from cabinet/scripts/germline-lock.sh (never a second hand-kept
         copy), each existing path probed via posture.is_locked() with an
         EXPLICIT deployment target (posture.py's canonical attestation
         dispatch: schg on Darwin, ro_mount on docker).  A platform whose
         backend cannot attest (schg off-Darwin) is UNOBSERVABLE — the
         section is skipped and prior state carried, so Linux CI can never
         emit phantom unlock windows.
       * posture resolution — resolve_posture(file_needs=False) +
         narrow_cap() + the attested ruling (an observer read never files a
         need).  A per-process CABINET_POSTURE env brake elsewhere is
         invisible by design (A10) — payloads carry
         resolution_scope=watcher-process to say so honestly.
  2. Diffs against the last-seen state persisted in an UNLOCKED JSON state
     file (default: ~/Library/Application Support/cabinet/state/
     authority-transitions.json; test override:
     CABINET_AUTHORITY_STATE_FILE — a memory location, never fuel).
  3. On change, emits already-registered org events (framework/events/
     emitter.py; all on the evidence-mirror allow-list, so each receives a
     signed receipt via the org-event chokepoint):
       kill_switch_activated / kill_switch_deactivated
       germline_unlock_observed / germline_relock_observed
       posture_changed
  4. Atomically rewrites the state file (tempfile + os.replace).

FAIL-SAFE INVARIANTS (inherited from the graduation sweep):
  * An observation error yields NO verdict for that section: prior state is
    carried forward unchanged and no transition is emitted — an unreachable
    Redis must never read as a kill-switch deactivation, a stat failure must
    never read as an unlock.
  * FIRST RUN (no state file) seeds the baseline WITHOUT emitting; a section
    first observed later (e.g. germline becomes observable) seeds silently
    too.  There is deliberately NO --emit-baseline: an "initial state" emit
    would fabricate an activation/unlock claim after any state-file loss —
    a lie the graduation sweep's visibility-only events can afford but a
    kill-switch record cannot.
  * Delivery is AT-LEAST-ONCE: a section whose emit FAILED keeps its previous
    state in the written file, so the same transition re-detects and re-emits
    next sweep.  Consumers must tolerate a duplicated transition (the
    graduation_transition contract).
  * TRANSITIONS ONLY — a quiet sweep emits nothing (59%-plumbing law); window
    timestamps are sweep-cadence quantized (state the approximation, never
    imply exact-moment capture).
  * Payloads carry state + refs only — counts of locked/unlocked paths and
    changed-path lists, never scores, never per-officer aggregates
    (never-a-score, EVAL-025).

Everything is read-only except the state file + the org-event append via the
existing validated emitter.  Localhost redis-cli read only; no secrets, no
argv secrets.

Run:      python3.12 cabinet/scripts/emit-authority-transitions.py [--dry-run]
              [--state-file PATH]
Schedule: cabinet/services.yml row `authority-transitions` (ships disabled —
          staged like evidence-anchor; the enable is a deploy step:
          generate-plists + load).
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
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Fixed producer identity for every emit from this sweep (the
# graduation-sweep precedent) — never payload-derived, never env-derived.
ACTOR = "authority-watch"

# The kill switch's control-plane key — kill-switch.sh's single source.
KILLSWITCH_KEY = "cabinet:killswitch"

_GERMLINE_SCRIPT_REL = ("cabinet", "scripts", "germline-lock.sh")

_DEFAULT_STATE_FILE = os.path.expanduser(
    "~/Library/Application Support/cabinet/state/authority-transitions.json")

# Bounded payloads: a full-estate unlock lists every path; cap defensively.
_MAX_CHANGED_PATHS = 64

#: Every class this sweep can emit (kill-switch classes pre-registered by
#: Phase 2 item 1; the other three registered by this Batch B wave).  Used by
#: the mirror allow-list self-check in main() — the same LOUD-never-blocking
#: idiom as emit-officer-lifecycle-transitions.py: a class dropped from the
#: allow-list would land its org rows UNSIGNED, and a human must see that.
SWEEP_EVENT_TYPES = frozenset({
    "kill_switch_activated",
    "kill_switch_deactivated",
    "germline_unlock_observed",
    "germline_relock_observed",
    "posture_changed",
})


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def state_file_path(cli_override: Optional[str] = None) -> Path:
    """CLI flag > env override (fenced tests) > the unlocked live default."""
    return Path(cli_override
                or os.environ.get("CABINET_AUTHORITY_STATE_FILE")
                or _DEFAULT_STATE_FILE)


# ---------------------------------------------------------------------------
# Observers — each returns None when its surface is UNOBSERVABLE this sweep
# (an error never reads as a state change).
# ---------------------------------------------------------------------------

def _redis_hostport() -> Tuple[str, str]:
    """REDIS_URL parse with kill-switch.sh parity: default 127.0.0.1:6379,
    docker-legacy `redis` hostname coerced to 127.0.0.1 (the same residue
    guard the brake script and cabinet-doctor carry)."""
    url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
    hostport = url.split("://", 1)[-1].split("/", 1)[0]
    host, _, port = hostport.partition(":")
    host = host.strip() or "127.0.0.1"
    if host == "redis":
        host = "127.0.0.1"
    port = port.strip() or "6379"
    return host, port


def _killswitch_helper_verdict() -> Optional[str]:
    """CLEAR | ACTIVE | INDETERMINATE from the ONE shared reader, or None when
    the reader itself could not run.

    2026-07-25 ADVERSARIAL AUDIT: this module used to run its own
    ``redis-cli GET`` and map "not the literal string active" to "inactive".
    redis-cli prints error replies ON STDOUT WITH EXIT 0, and the ``(error``
    prefix this code guarded on only appears in INTERACTIVE mode — so NOAUTH
    (requirepass), NOPERM (``ACL SETUSER default -get``), WRONGTYPE
    (``LPUSH cabinet:killswitch x``) and LOADING all read as a cleared
    emergency stop. The classification now lives in ONE schg-locked helper,
    cabinet/scripts/hooks/killswitch-read.sh, which also consults the second
    (filesystem marker) stop channel."""
    helper = _REPO_ROOT / "cabinet" / "scripts" / "hooks" / "killswitch-read.sh"
    if not helper.is_file():
        return None
    try:
        proc = subprocess.run(["bash", str(helper)], capture_output=True,
                              text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    verdict = (proc.stdout or "").split("\t", 1)[0].strip()
    return verdict if verdict in ("CLEAR", "ACTIVE", "INDETERMINATE") else None


def observe_killswitch() -> Optional[str]:
    """'active' | 'inactive', or None when the control plane is unobservable.

    NO VERDICT (None) covers every ambiguous outcome — transport error,
    non-zero exit, redis error reply, unrecognised value, unreadable stop
    marker, missing reader. An unreadable switch must never read as a
    deactivation: the status verb prints STOPPED/CANNOT-VERIFY, and we carry
    prior state rather than guessing either way."""
    verdict = _killswitch_helper_verdict()
    if verdict == "ACTIVE":
        return "active"
    if verdict == "CLEAR":
        return "inactive"
    return None


def germline_lock_set(script: Path) -> Optional[Tuple[List[str], List[str]]]:
    """Parse the FILES=( ... ) and DIRS=( ... ) arrays from germline-lock.sh
    (read-only — the script's own enumeration is the ONE source of the locked
    set; a hand-kept copy here would drift).  None when the script is absent
    or the arrays cannot be found — never guess the boundary."""
    try:
        text = script.read_text(encoding="utf-8")
    except OSError:
        return None

    def _array(name: str) -> Optional[List[str]]:
        m = re.search(rf"(?ms)^{name}=\(\n(.*?)^\)", text)
        if not m:
            return None
        items: List[str] = []
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            qm = re.match(r'^"([^"]+)"', line)
            if qm:
                items.append(qm.group(1))
        return items

    files = _array("FILES")
    dirs = _array("DIRS")
    if not files or dirs is None:
        return None
    return files, dirs


def observe_germline(root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """{'unlocked': sorted [...], 'locked_count': n} or None (unobservable).

    Attestation rides posture.py's canonical backend dispatch with an
    EXPLICIT target (no per-file declared-target reads): schg on Darwin,
    ro_mount on docker.  Where the selected backend structurally cannot
    attest (schg off-Darwin — chflags does not exist, every probe would read
    'unlocked' forever) the boundary is UNOBSERVABLE here, not unlocked:
    return None so no phantom window is ever emitted from Linux CI.  Absent
    paths are skipped exactly like the lock script ('lock skips absent
    paths'); a germline-enumerated path BORN unlocked is honestly reported
    as an unlocked path."""
    root = root or _REPO_ROOT
    try:
        from framework.authority import posture
    except Exception:
        return None
    try:
        target = posture.infer_deployment_target()
        backend = posture.ATTESTATION_BACKEND_BY_TARGET.get(target, "schg")
        if backend == "schg" and sys.platform != "darwin":
            return None
        lock_set = germline_lock_set(root.joinpath(*_GERMLINE_SCRIPT_REL))
        if lock_set is None:
            return None
        files, dirs = lock_set
        unlocked: List[str] = []
        locked = 0
        for rel in list(files) + list(dirs):
            path = root / rel
            try:
                if not path.exists():
                    continue
            except OSError:
                continue
            if posture.is_locked(path, target):
                locked += 1
            else:
                unlocked.append(rel)
        return {"unlocked": sorted(unlocked), "locked_count": locked}
    except Exception:
        return None


def observe_posture() -> Optional[Dict[str, Any]]:
    """The effective posture resolution tuple, or None on resolver failure.

    file_needs=False everywhere — an observer read must never file a need
    (the binder receipt-read precedent).  ruling_posture/ruling_attested
    come from the ATTESTED reader only: an unattested ruling reads as absent
    here, which is exactly what the resolver honours for widening."""
    try:
        from framework.authority import posture
        cfg = posture.load_posture_config(file_needs=False)
        return {
            "resolved": posture.resolve_posture(file_needs=False),
            "narrow_cap": posture.narrow_cap(),
            "ruling_posture": (cfg or {}).get("posture"),
            "ruling_attested": cfg is not None,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# State file (the graduation-sweep shape: atomic rewrite, corrupt = re-seed)
# ---------------------------------------------------------------------------

def load_state(path: Path) -> Optional[Dict[str, Any]]:
    """Last-seen {'killswitch': ..., 'germline': ..., 'posture': ...}.
    None = no state file yet (BASELINE run).  A corrupt file re-seeds
    silently rather than emitting N bogus transitions against a broken
    memory (the graduation flood-guard rationale)."""
    try:
        with open(path) as f:
            doc = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        print("emit-authority-transitions: WARN state file unreadable — "
              "re-seeding baseline", file=sys.stderr)
        return None
    state = doc.get("state") if isinstance(doc, dict) else None
    return state if isinstance(state, dict) else None


def write_state(path: Path, state: Dict[str, Any], now: dt.datetime) -> None:
    """Atomic rewrite (tempfile + os.replace) — a crash mid-write must never
    leave a torn file the next run would mis-read as corrupt/baseline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"updated_at": _iso(now), "state": state}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".auth-trans-")
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
# Pure transition detection (no IO, no emits) — the unit tests' seam
# ---------------------------------------------------------------------------

def sweep(observed: Dict[str, Any],
          prev: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Diff one pass of observations against the last-seen state.

    ``observed`` sections may be None (unobservable this sweep) — those carry
    the previous section state forward and produce NO transition.  A section
    seen for the FIRST time (baseline run, or a previously-unobservable
    section coming online) seeds silently.  Returns {"current", "transitions"
    (list of {"event_type", "payload", "section"}), "baseline"}.
    """
    baseline = prev is None
    prev_map: Dict[str, Any] = dict(prev or {})
    current: Dict[str, Any] = {}
    transitions: List[Dict[str, Any]] = []

    # --- kill switch ------------------------------------------------------
    ks = observed.get("killswitch")
    ks_prev = prev_map.get("killswitch")
    if ks is None:
        if ks_prev is not None:
            current["killswitch"] = ks_prev      # unobservable: carry forward
    else:
        current["killswitch"] = ks
        if ks_prev in ("active", "inactive") and ks != ks_prev:
            event_type = ("kill_switch_activated" if ks == "active"
                          else "kill_switch_deactivated")
            transitions.append({
                "section": "killswitch",
                "event_type": event_type,
                "payload": {
                    "killswitch_id": KILLSWITCH_KEY,
                    "prior_state": ks_prev,
                    "new_state": ks,
                    # The Redis key carries no invoker — this is an observed
                    # state transition, not an attributed activation; window
                    # precision is the sweep cadence.
                    "attribution": "state-observed",
                    "precision": "sweep-cadence",
                },
            })

    # --- germline boundary --------------------------------------------------
    germ = observed.get("germline")
    germ_prev = prev_map.get("germline")
    if germ is None:
        if germ_prev is not None:
            current["germline"] = germ_prev
    else:
        current["germline"] = germ
        if isinstance(germ_prev, dict):
            old = set(germ_prev.get("unlocked") or [])
            new = set(germ.get("unlocked") or [])
            newly_unlocked = sorted(new - old)
            newly_relocked = sorted(old - new)
            base_payload = {
                "boundary_id": "germline",
                "unlocked_count": len(new),
                "locked_count": germ.get("locked_count"),
                "armed": not new,
                "precision": "sweep-cadence",
            }
            if newly_unlocked:
                transitions.append({
                    "section": "germline",
                    "event_type": "germline_unlock_observed",
                    "payload": {
                        **base_payload,
                        "changed_paths": newly_unlocked[:_MAX_CHANGED_PATHS],
                        "changed_count": len(newly_unlocked),
                    },
                })
            if newly_relocked:
                transitions.append({
                    "section": "germline",
                    "event_type": "germline_relock_observed",
                    "payload": {
                        **base_payload,
                        "changed_paths": newly_relocked[:_MAX_CHANGED_PATHS],
                        "changed_count": len(newly_relocked),
                    },
                })

    # --- posture resolution -------------------------------------------------
    pos = observed.get("posture")
    pos_prev = prev_map.get("posture")
    if pos is None:
        if pos_prev is not None:
            current["posture"] = pos_prev
    else:
        current["posture"] = pos
        if isinstance(pos_prev, dict) and pos != pos_prev:
            transitions.append({
                "section": "posture",
                "event_type": "posture_changed",
                "payload": {
                    "posture": pos.get("resolved"),
                    "prior": pos_prev,
                    "new": pos,
                    # A per-process CABINET_POSTURE brake elsewhere is
                    # invisible to any watcher (A10) — this is THIS process's
                    # resolution, labeled honestly.
                    "resolution_scope": "watcher-process",
                },
            })

    return {"current": current, "transitions": transitions,
            "baseline": baseline}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Detect + emit control-plane authority transitions "
                    "(kill switch, germline windows, posture) into "
                    "org_events (see module docstring).")
    ap.add_argument("--dry-run", action="store_true",
                    help="print would-be transitions; emit nothing, write no state")
    ap.add_argument("--state-file", default=None,
                    help="override the last-seen state file path")
    args = ap.parse_args(argv)

    # Mirror allow-list self-check — LOUD, never blocking (the
    # emit-officer-lifecycle-transitions.py idiom): a sweep class missing
    # from the allow-list would land org rows UNSIGNED; the daily
    # digest-anchor still covers the breadth ledger, but a human must see it.
    try:
        from framework import evidence_mirror
        missing = SWEEP_EVENT_TYPES - evidence_mirror.MIRRORED_ORG_EVENT_TYPES
        if missing:
            print("emit-authority-transitions: WARN sweep class(es) missing "
                  "from the evidence-mirror allow-list — org rows land "
                  "UNSIGNED: %s" % ", ".join(sorted(missing)),
                  file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — self-check only, never fatal
        print("emit-authority-transitions: WARN mirror self-check "
              "unavailable: %s" % exc, file=sys.stderr)

    now = _now()
    observed = {
        "killswitch": observe_killswitch(),
        "germline": observe_germline(),
        "posture": observe_posture(),
    }

    path = state_file_path(args.state_file)
    prev = load_state(path)
    result = sweep(observed, prev)

    # Baseline runs generate no transitions by construction (every section is
    # a first sighting, which seeds silently) — noted for the summary line.
    suppress = result["baseline"]
    emitted = 0
    emit_failures = 0

    if args.dry_run:
        for t in result["transitions"]:
            print(f"[dry-run] {t['event_type']}: {json.dumps(t['payload'], sort_keys=True)}")
    else:
        from framework.events.emitter import emit
        failed_sections: set = set()
        for t in result["transitions"]:
            if t["section"] in failed_sections:
                continue  # section already reverted — re-detect next sweep
            try:
                emit(t["event_type"], actor=ACTOR, payload=t["payload"])
                emitted += 1
            except Exception as e:  # noqa: BLE001
                emit_failures += 1
                failed_sections.add(t["section"])
                # At-least-once: revert this SECTION to its previous state
                # (or drop a first sighting) so the same transition
                # re-detects and re-emits on the next sweep.
                section = t["section"]
                if prev is not None and section in prev:
                    result["current"][section] = prev[section]
                else:
                    result["current"].pop(section, None)
                print(f"emit-authority-transitions: WARN emit failed for "
                      f"{t['event_type']} ({section}): {e}", file=sys.stderr)

    if not args.dry_run:
        try:
            write_state(path, result["current"], now)
        except OSError as e:
            # Events (if any) are already out; next run re-baselines from the
            # old file (or seeds). Loud, non-zero — a sweep that cannot
            # remember is broken even though nothing false was emitted.
            print(f"emit-authority-transitions: state write failed: {e}",
                  file=sys.stderr)
            return 1

    summary = {
        "ts": _iso(now),
        "observed": {k: (v is not None) for k, v in observed.items()},
        "transitions": len(result["transitions"]),
        "emitted": emitted,
        "emit_failures": emit_failures,
        "baseline_seeded": bool(suppress),
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
