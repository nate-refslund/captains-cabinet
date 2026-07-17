#!/usr/bin/env python3
"""killswitch-watchdog.py — re-arm the emergency stop when it is cleared
without a sanctioned audit row (captain-controls Phase 1, ratified 2026-07-17).

WHY (docs/plans/captain-controls-no-terminal-2026-07-17.md, "Raw-write
backstop"): local Redis has no auth, so a raw ``DEL cabinet:killswitch``
bypasses the E-stop silently (the 2026-07-15→16 unattributable clearing).
Every SANCTIONED flip rides cabinet/scripts/kill-switch.sh, which leaves an
attributable ledger row (kill_switch_activated / kill_switch_deactivated,
payload.via="kill-switch.sh"). This watchdog closes the raw-write gap: when
the switch reads INACTIVE but the ledger shows the newest arm was never
followed by a sanctioned deactivation, it re-arms via the SAME sanctioned
surface (``bash kill-switch.sh activate`` with
CABINET_OFFICER=killswitch-watchdog, so the re-arm signs its name in the
audit trail) and tells the Captain ONCE, in plain English, through the one
Telegram door (framework/frontdoor/channel.py — degrade-quiet when absent).

THE E-STOP ASYMMETRY (the design's one law): halting stays easy — this
watchdog only ever ACTIVATES. It never deactivates anything, and it never
fights a sanctioned resume: a kill_switch_deactivated row with
payload.via="kill-switch.sh" at/after the newest arm is the Captain's
ceremony and ends the matter.

PROVENANCE, NOT ROW ORDER: the staged authority-transitions sweep
(cabinet/scripts/emit-authority-transitions.py) emits kill_switch_* rows as
OBSERVATIONS (actor "authority-watch", payload.attribution="state-observed",
no ``via`` key). An observed deactivation row merely DESCRIBES the raw clear
this watchdog exists to catch — it sanctions nothing; treating "newest row is
a deactivation" as sanction would let that sweep mask every raw clear it
observes. The verdict therefore keys on the newest ARM of ANY provenance (a
raw SET is still an arm — ``activate`` is unrestricted by design) vs the
newest SANCTIONED deactivation (payload.via == "kill-switch.sh"), never on
bare row order.

GRACE: a legitimate ceremony can hold the key clear for a moment (the DEL
lands an instant before its audit row; an activate…deactivate pair can be
seconds apart). The anomaly must PERSIST past a grace window (default 90s,
env CABINET_KILLSWITCH_REARM_GRACE_S / --grace-s) before the watchdog acts.
The anomaly clock is keyed to the newest activation row's id in the state
file, so a new arm/clear episode restarts the clock; any sanctioned outcome
(resume, or the switch reading active again) clears it.

FAIL-SAFE INVARIANTS:
  * Unreachable control plane (redis down) → loud WARN, NO-OP. Everything
    else already treats unreachable as ACTIVE (kill-switch.sh status's
    fail-closed contract); a guessed re-arm against a dead plane proves
    nothing.
  * Missing/unreadable events dir → loud WARN, NO-OP: with no ledger the
    clear cannot be attributed either way, and re-arming over a possibly
    sanctioned resume would fight the Captain (the one law's hard-off side).
    Never a guessed re-arm.
  * No activation on record (cold deployment, empty ledger) → NO-OP.
  * Re-arm failure (kill-switch.sh nonzero, or hung past its 30s timeout) →
    FATAL line + exit 1 so launchd surfaces it; the anomaly state is KEPT so
    the next tick retries.
  * The captain notification is best-effort AFTER the verified re-arm — a
    dead Telegram door never unwinds or blocks the safety action (the
    evidence-anchor _send_receipt idiom).

Run:      python3.12 cabinet/scripts/killswitch-watchdog.py [--dry-run]
              [--state-file PATH] [--grace-s N]
Schedule: cabinet/services.yml row ``killswitch-watchdog`` (interval 60s;
          ships disabled — staged; the enable is a deploy step: remove the
          flag, generate-plists, load).
State:    ~/Library/Application Support/cabinet/state/killswitch-watchdog.json
          (override: CABINET_KILLSWITCH_WATCHDOG_STATE_FILE / --state-file)
Tests:    cabinet/scripts/tests/test_killswitch_watchdog.py (disposable
          redis + tmp CABINET_EVENT_LOG_DIR, the test_kill_switch_events.py
          idiom).
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The identity every re-arm signs into the audit trail (CABINET_OFFICER for
# the kill-switch.sh child) — attributable, distinct from any officer.
ACTOR = "killswitch-watchdog"

KILLSWITCH_KEY = "cabinet:killswitch"
KILL_SWITCH_SCRIPT = _REPO_ROOT / "cabinet" / "scripts" / "kill-switch.sh"

#: The sanctioned surfaces' payload marker (pinned by
#: test_kill_switch_events.py: every kill-switch.sh row carries it).
SANCTIONED_VIA = "kill-switch.sh"

DEFAULT_GRACE_S = 90

_DEFAULT_STATE_FILE = os.path.expanduser(
    "~/Library/Application Support/cabinet/state/killswitch-watchdog.json")

#: Newest-first ledger scan stops at the first day file containing an
#: activation row; this cap only bounds the pathological no-activation-ever
#: estate walk.
_MAX_DAY_FILES = 400

_LOG_PREFIX = "killswitch-watchdog"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> Optional[dt.datetime]:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _warn(msg: str) -> None:
    print(f"{_LOG_PREFIX}: WARN {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Observers
# ---------------------------------------------------------------------------

def _redis_hostport() -> Tuple[str, str]:
    """REDIS_URL parse with kill-switch.sh parity (default 127.0.0.1:6379,
    docker-legacy ``redis`` hostname coerced — the same residue guard the
    brake script and emit-authority-transitions.py carry)."""
    url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
    hostport = url.split("://", 1)[-1].split("/", 1)[0]
    host, _, port = hostport.partition(":")
    host = host.strip() or "127.0.0.1"
    if host == "redis":
        host = "127.0.0.1"
    port = port.strip() or "6379"
    return host, port


def observe_killswitch() -> Optional[str]:
    """'active' | 'inactive', or None when the control plane is unobservable
    (identical contract to emit-authority-transitions.observe_killswitch)."""
    host, port = _redis_hostport()
    try:
        proc = subprocess.run(
            ["redis-cli", "-h", host, "-p", port, "GET", KILLSWITCH_KEY],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    if value.startswith("(error"):
        return None
    if value == "(nil)":
        value = ""
    return "active" if value == "active" else "inactive"


def _events_dir() -> Path:
    """The emitter's ledger dir resolution: explicit env first, then the
    emitter's own resolver (ONE source for the durable default), then the
    documented default verbatim if framework is unimportable."""
    explicit = os.environ.get("CABINET_EVENT_LOG_DIR")
    if explicit:
        return Path(explicit)
    try:
        from framework.events import emitter
        return emitter._event_log_dir()
    except Exception:
        return Path(os.path.expanduser(
            "~/Library/Application Support/cabinet/events"))


def _read_rows_one_file(path: Path) -> List[Dict[str, Any]]:
    """kill_switch_* rows of one day file (shared flock like emitter.replay;
    an undecodable line — e.g. a crash-torn tail — is skipped, never fatal)."""
    rows: List[Dict[str, Any]] = []
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        with os.fdopen(os.dup(fd), "rb") as f:
            for raw in f:
                if not raw.strip():
                    continue
                try:
                    event = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    continue
                if str(event.get("event_type", "")).startswith("kill_switch_"):
                    rows.append(event)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    return rows


def read_kill_switch_rows(events_dir: Path) -> List[Dict[str, Any]]:
    """kill_switch_* rows sufficient for the verdict: day files are scanned
    NEWEST-FIRST and the scan stops after the first file containing an
    activation row — every sanctioned deactivation at/after that arm
    necessarily lives in that file or a newer one (all already collected).

    Raises FileNotFoundError when the ledger dir is absent (the caller's
    loud fail-safe no-op branch)."""
    if not events_dir.is_dir():
        raise FileNotFoundError(str(events_dir))
    files = sorted(events_dir.glob("events-*.jsonl"), reverse=True)
    if len(files) > _MAX_DAY_FILES:
        _warn(f"ledger scan capped at newest {_MAX_DAY_FILES} day files "
              f"({len(files)} present)")
        files = files[:_MAX_DAY_FILES]
    rows: List[Dict[str, Any]] = []
    for f in files:
        try:
            file_rows = _read_rows_one_file(f)
        except OSError as exc:
            _warn(f"unreadable ledger file {f.name}: {exc}")
            continue
        rows.extend(file_rows)
        if any(r.get("event_type") == "kill_switch_activated"
               for r in file_rows):
            break
    return rows


# ---------------------------------------------------------------------------
# State file (the authority-sweep shape: atomic rewrite, corrupt = re-seed)
# ---------------------------------------------------------------------------

def state_file_path(cli_override: Optional[str] = None) -> Path:
    return Path(cli_override
                or os.environ.get("CABINET_KILLSWITCH_WATCHDOG_STATE_FILE")
                or _DEFAULT_STATE_FILE)


def load_state(path: Path) -> Dict[str, Any]:
    try:
        with open(path) as f:
            doc = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        _warn("state file unreadable — re-seeding (grace restarts)")
        return {}
    state = doc.get("state") if isinstance(doc, dict) else None
    return state if isinstance(state, dict) else {}


def write_state(path: Path, state: Dict[str, Any], now: dt.datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"updated_at": _iso(now), "state": state}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".ksw-wd-")
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
# Pure verdict (no IO) — the unit tests' seam
# ---------------------------------------------------------------------------

def _created_at(row: Dict[str, Any]) -> str:
    # Emitter rows all carry the same isoformat shape; a missing field sorts
    # oldest (defensive only — never emitted that way).
    return str(row.get("created_at") or "")


def _is_sanctioned(row: Dict[str, Any]) -> bool:
    payload = row.get("payload")
    return isinstance(payload, dict) and payload.get("via") == SANCTIONED_VIA


def decide(switch_state: str,
           rows: List[Dict[str, Any]],
           prev: Dict[str, Any],
           now: dt.datetime,
           grace_s: int) -> Dict[str, Any]:
    """One tick's verdict for an OBSERVED switch state against the ledger.

    Returns {"action", "reason", "state" (the new state dict),
    "anomaly_age_s" (present on the anomaly path)}. Actions:
      noop-active | noop-cold | noop-sanctioned-resume |
      grace-pending | re-arm
    """
    state = dict(prev)

    if switch_state == "active":
        state.pop("anomaly", None)
        return {"action": "noop-active",
                "reason": "switch armed — nothing to defend", "state": state}

    activations = [r for r in rows
                   if r.get("event_type") == "kill_switch_activated"]
    newest_arm = max(activations, key=_created_at, default=None)
    if newest_arm is None:
        state.pop("anomaly", None)
        return {"action": "noop-cold",
                "reason": "no arm on record — nothing was cleared",
                "state": state}

    sanctioned_deacts = [r for r in rows
                         if r.get("event_type") == "kill_switch_deactivated"
                         and _is_sanctioned(r)]
    newest_sanctioned_deact = max(sanctioned_deacts, key=_created_at,
                                  default=None)
    if (newest_sanctioned_deact is not None
            and _created_at(newest_sanctioned_deact)
            >= _created_at(newest_arm)):
        state.pop("anomaly", None)
        return {"action": "noop-sanctioned-resume",
                "reason": "newest arm has a sanctioned kill-switch.sh "
                          "deactivation at/after it", "state": state}

    # Unattributed clear: the newest arm was never sanctioned-deactivated,
    # yet the key is gone. Episode identity = that arm row's id.
    anomaly_key = str(newest_arm.get("id") or _created_at(newest_arm))
    anomaly = prev.get("anomaly") if isinstance(prev.get("anomaly"), dict) else {}
    first_seen = _parse_iso(str(anomaly.get("first_seen") or ""))
    if anomaly.get("key") != anomaly_key or first_seen is None:
        state["anomaly"] = {"key": anomaly_key, "first_seen": _iso(now)}
        return {"action": "grace-pending", "anomaly_age_s": 0,
                "reason": "unattributed clear first seen — waiting out the "
                          "ceremony grace", "state": state}

    age_s = int((now - first_seen).total_seconds())
    if age_s < grace_s:
        state["anomaly"] = dict(anomaly)
        return {"action": "grace-pending", "anomaly_age_s": age_s,
                "reason": "unattributed clear inside the ceremony grace",
                "state": state}

    state["anomaly"] = dict(anomaly)
    return {"action": "re-arm", "anomaly_age_s": age_s,
            "reason": "switch cleared without a sanctioned deactivation row, "
                      "persisted past the grace", "state": state}


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def rearm() -> subprocess.CompletedProcess:
    """Re-arm through the SAME sanctioned surface every other flip uses.
    kill-switch.sh verifies by read-back and writes the audit row itself;
    CABINET_OFFICER makes the row attributable to this watchdog."""
    env = dict(os.environ)
    env["CABINET_OFFICER"] = ACTOR
    return subprocess.run(
        ["bash", str(KILL_SWITCH_SCRIPT), "activate"],
        env=env, capture_output=True, text=True, timeout=30)


def notify_captain(text: str) -> str:
    """ONE plain-English line through the one sanctioned Telegram door
    (framework/frontdoor/channel.py). Credless-safe presence check on the
    channel's own env NAMES first (values never printed); any failure is a
    WARN, never an unwind — the evidence-anchor _send_receipt idiom."""
    has_token = bool(os.environ.get("TELEGRAM_BOT_TOKEN")
                     or os.environ.get("TELEGRAM_COS_TOKEN"))
    has_captain = bool(os.environ.get("CAPTAIN_TELEGRAM_ID"))
    if not has_token or not has_captain:
        return "skipped-unconfigured"
    try:
        from framework.frontdoor import channel
        response = channel.send(text)
    except Exception as exc:  # noqa: BLE001 — never unwind the re-arm
        _warn(f"captain notification failed: {exc}")
        return "failed"
    if isinstance(response, dict):
        if response.get("sent"):
            return "sent"
        return str(response.get("status") or "failed")
    return "failed"


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Re-arm the kill switch when it was cleared without a "
                    "sanctioned audit row (see module docstring).")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the verdict; no re-arm, no notification, "
                         "no state write")
    ap.add_argument("--state-file", default=None,
                    help="override the anomaly state file path")
    ap.add_argument("--grace-s", type=int, default=None,
                    help=f"ceremony grace seconds (default env "
                         f"CABINET_KILLSWITCH_REARM_GRACE_S or "
                         f"{DEFAULT_GRACE_S})")
    args = ap.parse_args(argv)

    if args.grace_s is not None:
        grace_s = args.grace_s
    else:
        try:
            grace_s = int(os.environ.get(
                "CABINET_KILLSWITCH_REARM_GRACE_S", DEFAULT_GRACE_S))
        except ValueError:
            _warn("bad CABINET_KILLSWITCH_REARM_GRACE_S — using default")
            grace_s = DEFAULT_GRACE_S

    now = _now()
    summary: Dict[str, Any] = {"ts": _iso(now), "grace_s": grace_s,
                               "dry_run": bool(args.dry_run)}
    rc = 0

    switch = observe_killswitch()
    summary["switch"] = switch or "unobservable"

    if switch is None:
        # Fail-safe: everything else already treats an unreachable plane as
        # ACTIVE; a re-arm attempt against it could verify nothing.
        _warn("control plane unreachable — cannot read the switch; "
              "fail-safe no-op (fleet redis health pages elsewhere)")
        summary["action"] = "noop-unobservable-redis"
        print(json.dumps(summary, sort_keys=True))
        return 0

    events_dir = _events_dir()
    rows: List[Dict[str, Any]] = []
    if switch == "inactive":
        try:
            rows = read_kill_switch_rows(events_dir)
        except FileNotFoundError:
            _warn(f"events dir missing ({events_dir}) — the clear cannot be "
                  "attributed either way; fail-safe no-op, NO re-arm")
            summary["action"] = "noop-events-unreadable"
            print(json.dumps(summary, sort_keys=True))
            return 0

    state_path = state_file_path(args.state_file)
    prev = load_state(state_path)
    verdict = decide(switch, rows, prev, now, grace_s)
    summary["action"] = verdict["action"]
    summary["reason"] = verdict["reason"]
    if "anomaly_age_s" in verdict:
        summary["anomaly_age_s"] = verdict["anomaly_age_s"]
    new_state = verdict["state"]

    if verdict["action"] == "re-arm" and not args.dry_run:
        try:
            proc: Optional[subprocess.CompletedProcess] = rearm()
        except subprocess.TimeoutExpired:
            proc = None
        if proc is not None and proc.returncode == 0:
            summary["rearm_rc"] = 0
            # Verified by kill-switch.sh's own read-back; audit row written
            # by the script (actor = killswitch-watchdog via CABINET_OFFICER).
            new_state.pop("anomaly", None)
            new_state["last_rearm"] = {"at": _iso(now),
                                       "notified": None}
            summary["notified"] = notify_captain(
                "The emergency stop was cleared by something that didn't "
                f"sign its name — I re-armed it. ({_iso(now)})")
            new_state["last_rearm"]["notified"] = summary["notified"]
        else:
            # The FATAL path — a hung kill-switch.sh (>30s TimeoutExpired)
            # lands here alongside the nonzero exits: keep the anomaly so
            # the next tick retries; loud so launchd surfaces it.
            if proc is None:
                summary["rearm_rc"] = "timeout"
                detail = "kill-switch.sh hung past its 30s timeout"
            else:
                summary["rearm_rc"] = proc.returncode
                detail = (f"rc={proc.returncode}: "
                          f"{(proc.stderr or proc.stdout or '').strip()[:200]}")
            print(f"{_LOG_PREFIX}: FATAL re-arm failed ({detail})",
                  file=sys.stderr)
            rc = 1

    if not args.dry_run and new_state != prev:
        try:
            write_state(state_path, new_state, now)
        except OSError as exc:
            print(f"{_LOG_PREFIX}: FATAL state write failed: {exc}",
                  file=sys.stderr)
            rc = 1

    print(json.dumps(summary, sort_keys=True))
    return rc


if __name__ == "__main__":
    sys.exit(main())
