#!/usr/bin/env python3.12
"""fleet-deadman.py — is the fleet ALIVE, DEAD, or can I not tell?

Runs OUTSIDE the fleet. Reads the pulse files that fleet jobs write through
``framework.liveness.deadman.pulse`` and answers with exactly one of three
states. When — and only when — the answer is ALIVE it pings an off-machine
watcher, so the off-machine watcher alarms on the ABSENCE of a ping.

WHY IT EXISTS. On 2026-07-25 every ``com.cabinet.*`` launchd label on the live
box was unloaded. Every in-repo sensor was a job in that same set, so the fault
and its detectors were removed in one act, and every escalation tier terminated
at the Chair — itself a supervised officer. Nothing reported anything for five
days while the dashboard rendered and every gate stayed green.

WHY THE PING IS ON ALIVE AND NOT ON FAILURE. A watcher that must NOTICE a
failure fails with it; a watcher that must be REASSURED does not. Chained this
way, one signal covers three different deaths:

  * the fleet dies      → this says DEAD  → no ping → external alarm
  * this watcher dies   → nothing pings            → external alarm
  * the whole box dies  → nothing pings            → external alarm

The third is why no local surface can replace the external leg, and the second
is why this must never ping on its own behalf: an ALIVE ping asserts a measured
fact about the fleet, never "I ran".

THREE STATES, AND THE ONE THAT IS ALWAYS GOT WRONG.

  ALIVE    every expected source pulsed inside its limit. Measured.
  DEAD     the pulse store ANSWERED, and a source is stale or has never pulsed.
  UNKNOWN  the store could not be asked, or a pulse could not be believed, or
           the clocks disagree, or nothing is configured to expect.

The failure this file exists to not repeat: with every label unloaded,
``launchctl list`` answered perfectly well with zero cabinet rows, and the check
written for exactly that event read it as "I cannot see launchd" and switched
ITSELF off. An answered scan holding nothing is a MEASUREMENT, and a very loud
one. So here: a readable pulse store containing no pulse for an expected source
is DEAD, not UNKNOWN. Only a store that could not be READ AT ALL is UNKNOWN —
and the two are told apart by whether the store's PARENT is readable, the one
observation that distinguishes "the fleet wrote nothing" from "I cannot see
where the fleet writes".

UNKNOWN NEVER PINGS. ``decide_ping`` is ``state == ALIVE``, deliberately not
``state != DEAD``: pinging while you cannot tell converts every future blind
spot into a silent all-clear.

WHY THIS PLANE. It sits beside ``ledger-liveness-check.py`` and
``healthchecks-drill.py`` — the cabinet's other operational dead-men — because
that is what it is: a scheduled runner that looks at this box and pings out. The
EMITTER is universal and lives in ``framework/liveness/deadman.py`` with the
Captain-contact heartbeats; the scanning, the decision and the notification are
operations.

WHY PYTHON AND NOT SHELL. CI is ubuntu and its only shell coverage is
``bash -n``, a syntax check that executes nothing, so a shell watcher would be
untested by construction on the one platform that exists. Everything decidable
without launchd is a pure function, exercised by
``cabinet/scripts/tests/test_fleet_deadman.py`` on the CI runner.

INERT BY DEFAULT, AND VISIBLY SO. With no config there is nothing to expect, so
the verdict is UNKNOWN/``unarmed`` — never ALIVE. ``--status`` answers "armed,
and which legs" offline, because an absence detector that is itself silently
absent produces the same observable — no pings — as a dead fleet.

STANDARD LIBRARY ONLY, and no import of anything it watches. The single
framework import is the emitter package, which is itself stdlib-only and
guarded.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from framework.liveness import deadman  # noqa: E402

STATE_ALIVE = "ALIVE"
STATE_DEAD = "DEAD"
STATE_UNKNOWN = "UNKNOWN"

EVENT_FLEET_ALIVE = deadman.EVENT_FLEET_ALIVE
CONFIG_ENV = "CABINET_FLEETWATCH_CONFIG"
FLEET_STATE_FILE = "fleet-state.json"

# Defaults chosen LOOSER than any real cadence, so the first alarm a deployment
# ever sees is a real one. Overridden per source in the config.
DEFAULT_MAX_AGE_S = 5400          # 90 min
# A pulse dated meaningfully in the future means the two clocks disagree, and a
# staleness judgement across disagreeing clocks is not a measurement.
DEFAULT_CLOCK_TOLERANCE_S = 300

# Re-exported so this file reads as one surface; both resolve in the emitter,
# which is the half the fleet jobs import.
pulse_dir = deadman.pulse_dir
state_dir = deadman.state_dir
safe_source = deadman.safe_source
_atomic_write = deadman._atomic_write


def config_path(default: str = "") -> str:
    """Resolve this watcher's config path through the ratified env seam."""
    override = (os.environ.get(CONFIG_ENV) or "").strip()
    if override:
        return os.path.expanduser(override)
    try:
        from framework import env as _env

        return str(_env.fleetwatch_config_path(default))
    except Exception:
        return str(default)


# ── the watcher side: could I ask, and what did it say ─────────────────────

def scan(directory: str, *, parent: str | None = None, listdir=None,
         reader=None, isdir=None) -> dict:
    """Look at the pulse store. Returns
    ``{"observed": bool, "pulses": dict, "reason": str}``.

    ``observed`` is the ONLY thing that distinguishes "I could not ask" from
    "it answered". ``observed=True`` with ``pulses == {}`` is an answer, and a
    loud one: the fleet has written nothing where it writes when it is alive.

    The discriminator for an ABSENT pulse directory is whether its PARENT is a
    readable directory. Parent readable ⇒ I can see where the fleet writes and
    it has written nothing ⇒ observed, empty. Parent unreadable/absent ⇒ I
    cannot see the store at all ⇒ NOT observed. Collapsing those two is the
    2026-07-25 defect, and it is the reason this function returns a flag rather
    than ``None``-or-dict: a flag cannot be accidentally truthiness-tested."""
    _listdir = listdir or os.listdir
    _isdir = isdir or os.path.isdir
    if not directory:
        return {"observed": False, "pulses": {}, "reason": "no-pulse-dir-configured"}
    try:
        names = _listdir(directory)
    except FileNotFoundError:
        par = parent if parent is not None else os.path.dirname(directory)
        try:
            visible = bool(par) and _isdir(par)
        except Exception:
            visible = False
        if visible:
            return {"observed": True, "pulses": {}, "reason": "never-pulsed"}
        return {"observed": False, "pulses": {},
                "reason": "state-root-unreadable"}
    except NotADirectoryError:
        return {"observed": False, "pulses": {}, "reason": "pulse-dir-not-a-directory"}
    except PermissionError:
        return {"observed": False, "pulses": {}, "reason": "pulse-dir-unreadable"}
    except OSError:
        return {"observed": False, "pulses": {}, "reason": "pulse-dir-unreadable"}

    pulses: dict = {}
    for name in names:
        if not name.endswith(".json"):
            continue
        source = name[: -len(".json")]
        if not safe_source(source):
            continue
        pulses[source] = _read_pulse(os.path.join(directory, name), reader)
    return {"observed": True, "pulses": pulses, "reason": "ok"}


def _read_pulse(path: str, reader=None) -> dict:
    """One pulse file → ``{"ts": float|None, "reason": str}``. ``ts is None``
    means the file exists but could not be believed, which is an UNKNOWN about
    THAT source — never a silent zero, because a zero timestamp reads as
    infinitely stale and would manufacture a DEAD out of a read error."""
    try:
        raw = (reader or _read_text)(path)
    except Exception:
        return {"ts": None, "reason": "unreadable"}
    try:
        obj = json.loads(raw)
        ts = float(obj["ts"])
    except Exception:
        return {"ts": None, "reason": "unparseable"}
    return {"ts": ts, "reason": "ok"}


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def assess(scanned: dict, expect: dict, now: float, *,
           clock_tolerance_s: int = DEFAULT_CLOCK_TOLERANCE_S) -> dict:
    """ALIVE / DEAD / UNKNOWN over one scan. Pure; never raises; no I/O.

    PRECEDENCE — DEAD > UNKNOWN > ALIVE. A source I can definitively see is
    stale outranks a source I cannot read: one confirmed death is enough, and
    downgrading it to "I am not sure" because a DIFFERENT file was corrupt is
    how a real alarm gets laundered into a shrug. But a single unreadable source
    is enough to forbid ALIVE, because ALIVE is a claim about ALL of them."""
    try:
        if not expect:
            return _verdict(STATE_UNKNOWN, "unarmed", [],
                            "no expected sources configured")
        if not scanned.get("observed"):
            return _verdict(STATE_UNKNOWN, scanned.get("reason") or "not-observed",
                            [], "the pulse store could not be read")
        pulses = scanned.get("pulses") or {}
        dead: list = []
        unknown: list = []
        ages: dict = {}
        for source in sorted(expect):
            max_age = expect[source]
            entry = pulses.get(source)
            if entry is None:
                dead.append(f"{source}: no pulse (store answered, nothing there)")
                ages[source] = None
                continue
            ts = entry.get("ts")
            if ts is None:
                unknown.append(f"{source}: pulse {entry.get('reason', 'unreadable')}")
                ages[source] = None
                continue
            age = now - float(ts)
            ages[source] = age
            if age < -abs(clock_tolerance_s):
                unknown.append(
                    f"{source}: pulse is {int(-age)}s in the future (clock skew)")
            elif age > max_age:
                dead.append(f"{source}: {int(age)}s stale (limit {int(max_age)}s)")
        if dead:
            return _verdict(STATE_DEAD, "stale-or-missing", dead + unknown,
                            "; ".join(dead + unknown), ages=ages)
        if unknown:
            return _verdict(STATE_UNKNOWN, "unreadable-pulse", unknown,
                            "; ".join(unknown), ages=ages)
        return _verdict(STATE_ALIVE, "ok", [],
                        f"{len(expect)} source(s) fresh", ages=ages)
    except Exception as exc:  # pragma: no cover - belt: assess must NEVER raise
        return _verdict(STATE_UNKNOWN, "internal-error", [], type(exc).__name__)


def _verdict(state: str, reason: str, findings: list, detail: str,
             ages: dict | None = None) -> dict:
    return {"state": state, "reason": reason, "findings": list(findings),
            "detail": detail, "ages_s": ages or {}}


def decide_ping(verdict: dict) -> bool:
    """Ping the off-machine watcher for THIS verdict?

    ``state == ALIVE`` and nothing else. Written as an equality against the one
    affirmative state rather than ``!= DEAD`` on purpose: the negated form makes
    every state this module has not thought of yet — and every future bug that
    yields one — into a silent all-clear. UNKNOWN must starve the watcher
    exactly as DEAD does, because from the far end of the wire "I cannot tell"
    and "it is gone" deserve the same alarm."""
    return bool(verdict) and verdict.get("state") == STATE_ALIVE


# ── delivery ───────────────────────────────────────────────────────────────

def notify_command(title: str, body: str) -> tuple:
    """``(argv, script)`` for a macOS user notification — a surface the Captain
    already has on screen, needing no terminal and no outward-facing channel.

    The strings are passed as ARGUMENTS to an ``on run argv`` handler and the
    script text rides on STDIN, so nothing the caller supplies is ever
    interpolated into AppleScript source: a reason is built from config values
    and filenames, and one stray quote in a source-interpolated form would be an
    arbitrary-AppleScript hole.

    Returns EXACTLY what gets executed — argv and stdin, nothing rearranged by
    the caller. An earlier draft returned a list the runner then re-sliced,
    which meant the test asserted a shape that was not the shape that ran; a
    sensor pointed at something other than the control is this program's
    most-paid defect class, and it is not worth re-earning for one list."""
    script = ('on run argv\n'
              'display notification (item 2 of argv) '
              'with title (item 1 of argv)\n'
              'end run')
    return (["osascript", "-", title, body], script)


def _osascript_notify(title: str, body: str) -> bool:
    try:
        argv, script = notify_command(title, body)
        r = subprocess.run(argv, input=script, capture_output=True,
                           text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def should_notify(previous: dict | None, current: dict) -> bool:
    """Notify on a CHANGE of state only.

    A watcher that notifies every poll trains its reader to dismiss it, which
    costs exactly what the silent failure cost. A watcher that notifies only
    once and then goes quiet is indistinguishable from a fixed problem — so the
    standing signal is the verdict FILE and the external ping; the notification
    is the transition."""
    if current.get("state") == STATE_ALIVE:
        return False
    prev_state = (previous or {}).get("state")
    return prev_state != current.get("state")


def write_verdict(verdict: dict, *, root: str = "", now=None, writer=None,
                  makedirs=None) -> dict:
    """Persist the verdict where anything local can read it without a
    datastore, a daemon or a terminal — a plain file the desk surface can read
    while everything else on the box is down. Never raises."""
    try:
        base = root or state_dir()
        if not base:
            return {"wrote": False, "reason": "no-state-dir", "path": ""}
        try:
            (makedirs or os.makedirs)(base, exist_ok=True)
        except Exception:
            return {"wrote": False, "reason": "mkdir-failed", "path": base}
        path = os.path.join(base, FLEET_STATE_FILE)
        stamped = dict(verdict)
        ts = float(now() if now else time.time())
        stamped["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
        stamped["checked_at_epoch"] = ts
        try:
            (writer or _atomic_write)(path, json.dumps(stamped, indent=2,
                                                       sort_keys=True))
        except Exception:
            return {"wrote": False, "reason": "write-failed", "path": path}
        return {"wrote": True, "reason": "ok", "path": path}
    except Exception:  # pragma: no cover
        return {"wrote": False, "reason": "internal-error", "path": ""}


def read_verdict(*, root: str = "", reader=None) -> dict | None:
    """Previous verdict, or None if there is not one that can be believed."""
    base = root or state_dir()
    if not base:
        return None
    try:
        raw = (reader or _read_text)(os.path.join(base, FLEET_STATE_FILE))
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


# ── config ─────────────────────────────────────────────────────────────────

def parse_config(text: str) -> dict:
    """Stdlib-only parse of the fleetwatch config — same narrow shape and same
    survival reasoning as the dead-man's parser (no PyYAML: a watcher that dies
    of a missing dependency is worse than none).

    Accepted: top-level ``key: value`` scalars and 2-space ``key: value`` entries
    under ``expect:``. Unknown lines are ignored per entry. An unparseable file
    degrades to an EMPTY expectation set, which means UNARMED — a bad config can
    only ever silence this watcher, never make it claim a fleet is alive."""
    import re

    cfg: dict = {"enabled": True, "max_age_s": DEFAULT_MAX_AGE_S,
                 "clock_tolerance_s": DEFAULT_CLOCK_TOLERANCE_S,
                 "expect": {}, "_present": True}
    in_expect = False
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            in_expect = False
            if line.strip() == "expect:":
                in_expect = True
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if not m:
                continue
            key, val = m.group(1), _strip_comment(m.group(2))
            if key == "enabled":
                cfg["enabled"] = val.lower() not in ("false", "no", "0", "off")
            elif key in ("max_age_s", "clock_tolerance_s"):
                try:
                    cfg[key] = int(val)
                except ValueError:
                    pass  # keep the default; a typo must not disarm the watcher
            continue
        if in_expect:
            m = re.match(r"^\s{2}([A-Za-z0-9._-]+):\s*(.*)$", line)
            if not m:
                continue
            source = m.group(1)
            if not safe_source(source):
                continue
            val = _strip_comment(m.group(2))
            try:
                cfg["expect"][source] = int(val) if val else cfg["max_age_s"]
            except ValueError:
                cfg["expect"][source] = cfg["max_age_s"]
    if not cfg["enabled"]:
        cfg["expect"] = {}
    return cfg


# The comment-stripper is the EMITTER's, not a second copy: two dead-man configs
# parsed by two subtly different narrow parsers is how one of them silently stops
# honouring a comment convention the operator relies on.
_strip_comment = deadman._strip_comment


def load_config(path: str | None = None) -> dict:
    """Read + parse. Absent/unreadable ⇒ the empty (unarmed) config with
    ``_present=False``; never an exception, never a partial expectation set."""
    p = path if path is not None else config_path()
    if not p:
        cfg = parse_config("")
        cfg["_present"] = False
        cfg["expect"] = {}
        return cfg
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return parse_config(fh.read())
    except Exception:
        cfg = parse_config("")
        cfg["_present"] = False
        cfg["expect"] = {}
        return cfg


# ── arming state ───────────────────────────────────────────────────────────

def status(*, cfg: dict | None = None, config_path_override: str | None = None,
           deadman_status=None) -> dict:
    """Is this watcher armed, and WHICH LEGS — offline, no network, no alarm.

    Two legs, reported separately because they fail separately and cover
    different things:

      ``local``    expectations are configured, so a verdict can be produced and
                   written where the desk pet reads it. Survives the fleet.
      ``external`` the dead-man emitter has a ``fleet_alive`` slug, so ABSENCE
                   is alarmed from off this machine. Survives the box.

    Local-only is a real and useful posture; it is not equivalent to armed, and
    saying so is the whole reason this function reports two booleans instead of
    one. Registering the external check needs an account and a slug — an
    external act, never something this code does on its own."""
    conf = cfg if cfg is not None else load_config(config_path_override)
    local = bool(conf.get("expect"))
    ext_reason = "not-checked"
    external = False
    try:
        if deadman_status is None:
            deadman_status = deadman.status
        st = deadman_status()
        ext_reason = (st.get("events") or {}).get(EVENT_FLEET_ALIVE, "no-event")
        external = ext_reason == "ready"
    except Exception:
        ext_reason = "deadman-unavailable"
    return {"armed": local or external, "local": local, "external": external,
            "external_reason": ext_reason,
            "expect": dict(conf.get("expect") or {}),
            "config_present": bool(conf.get("_present"))}


# ── one pass ───────────────────────────────────────────────────────────────

def check(*, root: str = "", cfg: dict | None = None, now=None,
          scanner=None, emit=None, notify=None, allow_side_effects: bool = True) -> dict:
    """One full pass: scan → assess → persist → notify on change → ping iff ALIVE.

    Returns the verdict augmented with what was actually DONE (``pinged``,
    ``ping_reason``, ``notified``, ``verdict_written``) — reported, not assumed,
    because "the alarm was sent" is exactly the class of claim this program has
    repeatedly found to be false."""
    conf = cfg if cfg is not None else load_config()
    ts = float(now() if now else time.time())
    base = root or state_dir()
    scanned = (scanner or scan)(pulse_dir(base))
    verdict = assess(scanned, conf.get("expect") or {}, ts,
                     clock_tolerance_s=conf.get("clock_tolerance_s",
                                                DEFAULT_CLOCK_TOLERANCE_S))
    verdict["scan_reason"] = scanned.get("reason")
    verdict["observed"] = bool(scanned.get("observed"))
    # Name the directory that was actually scanned. A dead-man whose writers and
    # reader resolve different stores reports a confident, permanent DEAD with no
    # way to see why; printing the path turns that from a mystery into a diff.
    verdict["pulse_dir"] = pulse_dir(base)

    previous = read_verdict(root=base)
    if allow_side_effects:
        written = write_verdict(verdict, root=base, now=lambda: ts)
    else:
        written = {"wrote": False, "reason": "dry-run"}
    verdict["verdict_written"] = bool(written.get("wrote"))
    verdict["verdict_path"] = written.get("path", "")

    verdict["notified"] = False
    if should_notify(previous, verdict) and allow_side_effects:
        body = f"{verdict['state']}: {verdict['detail']}"[:240]
        verdict["notified"] = bool((notify or _osascript_notify)(
            "Cabinet fleet", body))

    if decide_ping(verdict):
        if not allow_side_effects:
            verdict["pinged"], verdict["ping_reason"] = False, "dry-run"
        else:
            try:
                if emit is None:
                    emit = deadman.emit
                res = emit(EVENT_FLEET_ALIVE)
                verdict["pinged"] = bool(res.get("emitted"))
                verdict["ping_reason"] = res.get("reason")
            except Exception as exc:
                verdict["pinged"], verdict["ping_reason"] = False, type(exc).__name__
    else:
        verdict["pinged"] = False
        verdict["ping_reason"] = "not-alive"
    return verdict


_EXIT = {STATE_ALIVE: 0, STATE_DEAD: 1, STATE_UNKNOWN: 2}


def main(argv: list | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="fleet-deadman",
        description="Fleet dead-man: ALIVE / DEAD / UNKNOWN. Exit 0/1/2.")
    ap.add_argument("--status", action="store_true",
                    help="report arming state only; no scan, no ping, no write")
    ap.add_argument("--dry-run", action="store_true",
                    help="scan and decide, but write nothing and ping nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if args.status:
        st = status()
        print(json.dumps(st, indent=2, sort_keys=True) if args.json
              else f"armed={st['armed']} local={st['local']} "
                   f"external={st['external']} ({st['external_reason']})")
        return 0

    v = check(allow_side_effects=not args.dry_run)
    if args.json:
        print(json.dumps(v, indent=2, sort_keys=True))
    else:
        print(f"{v['state']}: {v['detail']} "
              f"(pinged={v['pinged']}/{v['ping_reason']}, notified={v['notified']})")
    return _EXIT.get(v["state"], 2)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
