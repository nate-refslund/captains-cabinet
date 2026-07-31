"""Fleet dead-man tests — the WATCHER half (cabinet/scripts/fleet-deadman.py).

THE BAR THESE ARMS ARE WRITTEN TO. This program has found, repeatedly, that the
expensive defect is not a wrong answer but a SENSOR THAT CANNOT FAIL. So every
arm below is written to go red against a specific wrong implementation, and the
wrong implementations are named in the test docstrings rather than left implied.
The four that matter most:

  * ``test_answered_and_empty_is_DEAD`` fails against the exact 2026-07-25
    defect (a store that answered with nothing read as "cannot see").
  * ``test_unreadable_store_is_UNKNOWN`` fails against its mirror image (any
    absence read as death, i.e. a false page).
  * ``test_only_ALIVE_pings`` fails against ``state != DEAD``, the fail-open
    that would make every future unknown a silent all-clear.
  * ``test_unknown_state_name_does_not_ping`` fails against ANY negated ping
    predicate, including ones that enumerate today's states correctly.

SANDBOX RULE. Every write in this file is steered by an explicit ``root=``
argument and asserted to land inside ``tmp_path`` BEFORE the write. Nothing here
reads or writes a real config, a real state dir, or a real ~/Library path: the
module's env overrides exist so a test owns every path-steering variable rather
than steering through HOME and hoping.

PLATFORM. Everything here runs on the CI runner, which is not macOS. The one
macOS-only act (``osascript``) is never executed — only its argv is asserted,
which is the part that can be wrong in a way that matters.
"""
from __future__ import annotations

import json
import os

import pytest

import importlib.util as _ilu
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))))
_S = _ilu.spec_from_file_location(
    'fleet_deadman', _os.path.join(_ROOT, 'cabinet/scripts/fleet-deadman.py'))
fw = _ilu.module_from_spec(_S)
_S.loader.exec_module(fw)

NOW = 1_000_000.0


# ── helpers (sandbox-owning by construction) ───────────────────────────────

def _root(tmp_path):
    r = str(tmp_path / "liveness")
    os.makedirs(r, exist_ok=True)
    return r


def _write_pulse(tmp_path, source, ts, *, root=None, body=None):
    root = root or _root(tmp_path)
    d = fw.pulse_dir(root)
    assert d.startswith(str(tmp_path)), f"sandbox escape: {d}"
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{source}.json")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(body if body is not None else
                 json.dumps({"source": source, "ts": ts}))
    return p


def _scan(root):
    return fw.scan(fw.pulse_dir(root))


# ── the three states, and the two ways they get conflated ──────────────────

def test_answered_and_empty_is_DEAD(tmp_path):
    """A readable store holding no pulse for an expected source is a
    MEASUREMENT, and the loudest one available: the fleet has written nothing
    where it writes when alive.

    FAILS AGAINST: the 2026-07-25 defect — treating "the scan found nothing" as
    "I could not scan", which is how every launchd arm switched itself off at
    the exact moment every label was unloaded."""
    root = _root(tmp_path)
    os.makedirs(fw.pulse_dir(root), exist_ok=True)
    v = fw.assess(_scan(root), {"outcome-watchdog": 3600}, NOW)
    assert v["state"] == fw.STATE_DEAD
    assert "no pulse" in v["detail"]


def test_never_pulsed_dir_absent_but_parent_visible_is_DEAD(tmp_path):
    """Pulse dir absent while its parent IS readable: I can see where the fleet
    writes, and it has written nothing. That is an answer, not a blind spot."""
    root = _root(tmp_path)
    assert not os.path.exists(fw.pulse_dir(root))
    s = _scan(root)
    assert s["observed"] is True and s["reason"] == "never-pulsed"
    assert fw.assess(s, {"a": 3600}, NOW)["state"] == fw.STATE_DEAD


def test_unreadable_store_is_UNKNOWN(tmp_path):
    """The store's parent does not exist either — I cannot see where the fleet
    writes at all.

    FAILS AGAINST: the mirror-image defect, where every absence becomes a page.
    A watcher that cannot tell "gone" from "cannot look" is this week's defect
    in the one place it must not be."""
    root = str(tmp_path / "nope" / "liveness")
    s = _scan(root)
    assert s["observed"] is False and s["reason"] == "state-root-unreadable"
    v = fw.assess(s, {"a": 3600}, NOW)
    assert v["state"] == fw.STATE_UNKNOWN


def test_permission_error_on_store_is_UNKNOWN(tmp_path):
    def boom(_):
        raise PermissionError("nope")

    s = fw.scan(str(tmp_path / "p"), listdir=boom)
    assert s["observed"] is False and s["reason"] == "pulse-dir-unreadable"
    assert fw.assess(s, {"a": 1}, NOW)["state"] == fw.STATE_UNKNOWN


def test_fresh_pulse_is_ALIVE(tmp_path):
    root = _root(tmp_path)
    _write_pulse(tmp_path, "outcome-watchdog", NOW - 10, root=root)
    v = fw.assess(_scan(root), {"outcome-watchdog": 3600}, NOW)
    assert v["state"] == fw.STATE_ALIVE


def test_stale_pulse_is_DEAD(tmp_path):
    root = _root(tmp_path)
    _write_pulse(tmp_path, "outcome-watchdog", NOW - 7200, root=root)
    v = fw.assess(_scan(root), {"outcome-watchdog": 3600}, NOW)
    assert v["state"] == fw.STATE_DEAD
    assert "stale" in v["detail"]


def test_one_second_inside_the_limit_is_ALIVE_and_one_past_is_DEAD(tmp_path):
    """The boundary itself, both sides. A limit that is never exercised at its
    edge is a number nobody has checked."""
    root = _root(tmp_path)
    _write_pulse(tmp_path, "s", NOW - 3600, root=root)
    assert fw.assess(_scan(root), {"s": 3600}, NOW)["state"] == fw.STATE_ALIVE
    assert fw.assess(_scan(root), {"s": 3599}, NOW)["state"] == fw.STATE_DEAD


def test_unreadable_pulse_file_is_UNKNOWN_not_DEAD(tmp_path):
    """A pulse that exists but cannot be believed says nothing about the fleet.
    Reading it as an implicit ts=0 would manufacture a DEAD out of a parse bug —
    a false page with a false reason, which is how real ones stop being read."""
    root = _root(tmp_path)
    _write_pulse(tmp_path, "s", 0, root=root, body="{not json")
    v = fw.assess(_scan(root), {"s": 3600}, NOW)
    assert v["state"] == fw.STATE_UNKNOWN
    assert "unparseable" in v["detail"]


def test_future_pulse_beyond_tolerance_is_UNKNOWN(tmp_path):
    """Two clocks that disagree do not make a measurement."""
    root = _root(tmp_path)
    _write_pulse(tmp_path, "s", NOW + 9999, root=root)
    v = fw.assess(_scan(root), {"s": 3600}, NOW, clock_tolerance_s=300)
    assert v["state"] == fw.STATE_UNKNOWN
    assert "clock skew" in v["detail"]


def test_small_future_skew_inside_tolerance_still_ALIVE(tmp_path):
    root = _root(tmp_path)
    _write_pulse(tmp_path, "s", NOW + 60, root=root)
    assert fw.assess(_scan(root), {"s": 3600}, NOW,
                     clock_tolerance_s=300)["state"] == fw.STATE_ALIVE


def test_DEAD_outranks_UNKNOWN(tmp_path):
    """One source definitively stale, another unreadable. A confirmed death must
    not be downgraded to a shrug because a DIFFERENT file was corrupt."""
    root = _root(tmp_path)
    _write_pulse(tmp_path, "dead", NOW - 99999, root=root)
    _write_pulse(tmp_path, "murky", 0, root=root, body="garbage")
    v = fw.assess(_scan(root), {"dead": 60, "murky": 60}, NOW)
    assert v["state"] == fw.STATE_DEAD
    assert any("murky" in f for f in v["findings"]), \
        "the unknown source must still be reported, not swallowed by the DEAD"


def test_one_unknown_source_forbids_ALIVE(tmp_path):
    """ALIVE is a claim about ALL expected sources, so a single unreadable one
    is enough to withhold it."""
    root = _root(tmp_path)
    _write_pulse(tmp_path, "good", NOW - 5, root=root)
    _write_pulse(tmp_path, "murky", 0, root=root, body="}{")
    assert fw.assess(_scan(root), {"good": 60, "murky": 60},
                     NOW)["state"] == fw.STATE_UNKNOWN


# ── the degenerate end ─────────────────────────────────────────────────────

def test_no_expectations_is_UNKNOWN_unarmed_never_ALIVE(tmp_path):
    """The degenerate end, and the one a naive implementation gets wrong: with
    an empty expectation set, "every expected source is fresh" is vacuously true
    and an all() over nothing returns ALIVE. An unarmed watcher reporting a
    healthy fleet is worse than no watcher."""
    root = _root(tmp_path)
    _write_pulse(tmp_path, "s", NOW, root=root)
    v = fw.assess(_scan(root), {}, NOW)
    assert v["state"] == fw.STATE_UNKNOWN
    assert v["reason"] == "unarmed"
    assert fw.decide_ping(v) is False


def test_absent_config_is_unarmed(tmp_path):
    cfg = fw.load_config(str(tmp_path / "absent.yml"))
    assert cfg["_present"] is False
    assert cfg["expect"] == {}
    assert fw.assess(_scan(_root(tmp_path)), cfg["expect"],
                     NOW)["state"] == fw.STATE_UNKNOWN


def test_disabled_config_expects_nothing(tmp_path):
    p = tmp_path / "fw.yml"
    p.write_text("enabled: false\nexpect:\n  a: 60\n")
    assert fw.load_config(str(p))["expect"] == {}


def test_unparseable_config_degrades_to_unarmed_not_to_a_default_greenlight(tmp_path):
    p = tmp_path / "fw.yml"
    p.write_text("\x00\x01 not a config at all\n")
    cfg = fw.load_config(str(p))
    assert cfg["expect"] == {}


# ── the ping predicate: the fail-open that must not exist ──────────────────

@pytest.mark.parametrize("state,expected", [
    (fw.STATE_ALIVE, True),
    (fw.STATE_DEAD, False),
    (fw.STATE_UNKNOWN, False),
])
def test_only_ALIVE_pings(state, expected):
    """FAILS AGAINST: ``state != DEAD``. UNKNOWN must starve the external
    watcher exactly as DEAD does — from the far end of the wire, "I cannot
    tell" and "it is gone" deserve the same alarm."""
    assert fw.decide_ping({"state": state}) is expected


def test_unknown_state_name_does_not_ping():
    """A state this module has never heard of must not ping.

    FAILS AGAINST: any negated predicate, including one that enumerates today's
    three states correctly — because tomorrow's fourth state, or a bug that
    yields one, would become a silent all-clear."""
    assert fw.decide_ping({"state": "PROBABLY_FINE"}) is False
    assert fw.decide_ping({}) is False
    assert fw.decide_ping(None) is False


# ── pulse: the fleet side ──────────────────────────────────────────────────

def test_pulse_writes_and_scan_reads_it_back(tmp_path):
    root = _root(tmp_path)
    res = fw.deadman.pulse("outcome-watchdog", root=root, now=lambda: NOW)
    assert res["wrote"] is True and res["reason"] == "ok"
    assert res["path"].startswith(str(tmp_path)), "sandbox escape"
    s = _scan(root)
    assert s["observed"] is True
    assert s["pulses"]["outcome-watchdog"]["ts"] == NOW


def test_scan_ignores_a_file_whose_name_is_not_a_safe_source(tmp_path):
    root = _root(tmp_path)
    d = fw.pulse_dir(root)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ".hidden.json"), "w") as fh:
        fh.write("{}")
    with open(os.path.join(d, "notes.txt"), "w") as fh:
        fh.write("x")
    assert _scan(root)["pulses"] == {}


# ── notification: transition-only, and injection-proof ─────────────────────

def test_notify_only_on_state_change():
    dead = {"state": fw.STATE_DEAD}
    assert fw.should_notify(None, dead) is True
    assert fw.should_notify(dead, dead) is False, \
        "a watcher that notifies every poll trains its reader to dismiss it"
    assert fw.should_notify(dead, {"state": fw.STATE_UNKNOWN}) is True


def test_recovery_to_ALIVE_is_never_a_notification():
    assert fw.should_notify({"state": fw.STATE_DEAD},
                            {"state": fw.STATE_ALIVE}) is False


def test_notify_command_passes_strings_as_arguments_never_as_script_text():
    """The reason string is built from config values and filenames. Interpolated
    into AppleScript source, one stray quote is arbitrary-code execution; passed
    as ``argv`` to an ``on run argv`` handler, it is inert data.

    Asserted over EXACTLY what is executed — the function returns argv and stdin
    with no re-slicing by the runner, so this cannot pass while the executed
    command differs."""
    nasty = 'x" & (do shell script "touch /tmp/pwned") & "'
    argv, script = fw.notify_command("Cabinet fleet", nasty)
    assert nasty not in script, "the payload reached the AppleScript source"
    assert "do shell script" not in script
    assert "on run argv" in script
    assert argv == ["osascript", "-", "Cabinet fleet", nasty]

    # And the runner must execute that argv verbatim, with that script on stdin.
    seen = {}

    class R:
        returncode = 0

    def spy(a, **kw):
        seen["argv"], seen["input"] = a, kw.get("input")
        return R()

    mod = fw
    real = mod.subprocess.run
    mod.subprocess.run = spy
    try:
        assert fw._osascript_notify("Cabinet fleet", nasty) is True
    finally:
        mod.subprocess.run = real
    assert seen["argv"] == argv and seen["input"] == script


# ── verdict file ───────────────────────────────────────────────────────────

def test_verdict_round_trips_and_lands_inside_the_sandbox(tmp_path):
    root = _root(tmp_path)
    res = fw.write_verdict({"state": fw.STATE_DEAD, "detail": "x"},
                           root=root, now=lambda: NOW)
    assert res["wrote"] is True
    assert res["path"].startswith(str(tmp_path)), "sandbox escape"
    back = fw.read_verdict(root=root)
    assert back["state"] == fw.STATE_DEAD
    assert back["checked_at_epoch"] == NOW


def test_read_verdict_returns_None_rather_than_a_guess(tmp_path):
    root = _root(tmp_path)
    assert fw.read_verdict(root=root) is None
    with open(os.path.join(root, fw.FLEET_STATE_FILE), "w") as fh:
        fh.write("[]")
    assert fw.read_verdict(root=root) is None


# ── the whole pass ─────────────────────────────────────────────────────────

def test_check_end_to_end_alive_pings_once(tmp_path):
    root = _root(tmp_path)
    fw.deadman.pulse("s", root=root, now=lambda: NOW)
    pings, notes = [], []
    v = fw.check(root=root, cfg={"expect": {"s": 3600}}, now=lambda: NOW,
                 emit=lambda e: pings.append(e) or {"emitted": True, "reason": "ok"},
                 notify=lambda t, b: notes.append(b) or True)
    assert v["state"] == fw.STATE_ALIVE
    assert pings == [fw.EVENT_FLEET_ALIVE]
    assert notes == [], "ALIVE is not news"
    assert v["pinged"] is True and v["verdict_written"] is True


def test_check_end_to_end_dead_does_not_ping_and_notifies_once(tmp_path):
    root = _root(tmp_path)
    fw.deadman.pulse("s", root=root, now=lambda: NOW - 99999)
    pings, notes = [], []

    def run():
        return fw.check(root=root, cfg={"expect": {"s": 60}}, now=lambda: NOW,
                        emit=lambda e: pings.append(e) or {"emitted": True},
                        notify=lambda t, b: notes.append(b) or True)

    v1 = run()
    v2 = run()
    assert v1["state"] == v2["state"] == fw.STATE_DEAD
    assert pings == [], "a DEAD fleet must starve the external watcher"
    assert len(notes) == 1, "notify on the transition, not on every poll"
    assert v1["notified"] is True and v2["notified"] is False


def test_check_reports_what_it_actually_did_not_what_it_attempted(tmp_path):
    """A failed ping must read as a failed ping. "The alarm was sent" is exactly
    the class of claim this program has found false over and over."""
    root = _root(tmp_path)
    fw.deadman.pulse("s", root=root, now=lambda: NOW)
    v = fw.check(root=root, cfg={"expect": {"s": 3600}}, now=lambda: NOW,
                 emit=lambda e: {"emitted": False, "reason": "transport-error"},
                 notify=lambda t, b: True)
    assert v["state"] == fw.STATE_ALIVE
    assert v["pinged"] is False and v["ping_reason"] == "transport-error"


def test_check_dry_run_touches_nothing(tmp_path):
    root = _root(tmp_path)
    fw.deadman.pulse("s", root=root, now=lambda: NOW)
    pings = []
    v = fw.check(root=root, cfg={"expect": {"s": 3600}}, now=lambda: NOW,
                 emit=lambda e: pings.append(e) or {"emitted": True},
                 notify=lambda t, b: True, allow_side_effects=False)
    assert v["state"] == fw.STATE_ALIVE
    assert pings == [] and v["pinged"] is False
    assert not os.path.exists(os.path.join(root, fw.FLEET_STATE_FILE))


def test_check_survives_a_deadman_that_raises(tmp_path):
    root = _root(tmp_path)
    fw.deadman.pulse("s", root=root, now=lambda: NOW)

    def boom(_e):
        raise RuntimeError("network gone")

    v = fw.check(root=root, cfg={"expect": {"s": 3600}}, now=lambda: NOW,
                 emit=boom, notify=lambda t, b: True)
    assert v["pinged"] is False and v["ping_reason"] == "RuntimeError"


# ── arming state ───────────────────────────────────────────────────────────

def test_status_reports_the_two_legs_separately(tmp_path):
    """Local-only is a real posture and NOT the same as armed. Reporting one
    boolean would let a deployment with no off-machine leg read as covered — and
    the off-machine leg is the only one that survives the box."""
    p = tmp_path / "fw.yml"
    p.write_text("expect:\n  s: 60\n")
    st = fw.status(config_path_override=str(p),
                   deadman_status=lambda: {"events": {fw.EVENT_FLEET_ALIVE: "no-slug"}})
    assert st["local"] is True
    assert st["external"] is False
    assert st["external_reason"] == "no-slug"
    assert st["armed"] is True


def test_status_is_offline(tmp_path, monkeypatch):
    def no_net(*a, **k):
        raise AssertionError("status() must never touch the network")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", no_net)
    st = fw.status(config_path_override=str(tmp_path / "absent.yml"),
                   deadman_status=lambda: {"events": {}})
    assert st["armed"] is False and st["local"] is False


def test_status_survives_a_broken_deadman(tmp_path):
    def boom():
        raise ImportError("deadman is gone")

    st = fw.status(config_path_override=str(tmp_path / "absent.yml"),
                   deadman_status=boom)
    assert st["external"] is False
    assert st["external_reason"] == "deadman-unavailable"


# ── config parsing ─────────────────────────────────────────────────────────

def test_config_shape(tmp_path):
    p = tmp_path / "fw.yml"
    p.write_text(
        "# comment\n"
        "enabled: true\n"
        "max_age_s: 120  # trailing comment\n"
        "clock_tolerance_s: 30\n"
        "expect:\n"
        "  outcome-watchdog: 900\n"
        "  officer-inbound:\n"          # no number → falls back to max_age_s
        "  ../evil: 60\n"               # unsafe name → dropped
    )
    cfg = fw.load_config(str(p))
    assert cfg["max_age_s"] == 120 and cfg["clock_tolerance_s"] == 30
    assert cfg["expect"] == {"outcome-watchdog": 900, "officer-inbound": 120}


def test_shipped_example_parses_and_is_not_itself_the_live_config():
    """The example must remain a valid, readable template — and the repo must
    NOT ship a live fleetwatch.yml, or a fresh clone would inherit another
    deployment's expectations."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    example = os.path.join(root, "instance/config/fleetwatch.yml.example")
    assert os.path.exists(example)
    cfg = fw.load_config(example)
    assert set(cfg["expect"]) == {"outcome-watchdog", "officer-inbound"}
    assert not os.path.exists(os.path.join(root, "instance/config/fleetwatch.yml")), \
        "a live fleetwatch.yml must never be committed"


# ── the store must not move between the writers and the reader ─────────────

def test_pulse_store_does_not_ride_the_event_log_dir(monkeypatch):
    """FAILS AGAINST the defect this shipped with for one draft: deriving the
    pulse store from ``ledger_dir()``.

    The fleet's launchd plists SET ``CABINET_EVENT_LOG_DIR``; the out-of-fleet
    watcher's plist does not. Any resolver honouring it puts the writers and the
    reader in different directories — the fleet pulses into one, the watcher
    scans the other, finds nothing, and reports a confident permanent DEAD."""
    from framework import env

    monkeypatch.delenv(fw.deadman.STATE_ENV, raising=False)
    monkeypatch.delenv("CABINET_EVENT_LOG_DIR", raising=False)
    a = env.fleet_liveness_dir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR",
                       "/somewhere/else/Application Support/cabinet/events")
    b = env.fleet_liveness_dir()
    assert a == b, ("the pulse store moved when CABINET_EVENT_LOG_DIR changed; "
                    "the fleet sets that variable and the watcher does not")


def test_verdict_names_the_directory_it_scanned(tmp_path):
    root = _root(tmp_path)
    fw.deadman.pulse("s", root=root, now=lambda: NOW)
    v = fw.check(root=root, cfg={"expect": {"s": 3600}}, now=lambda: NOW,
                 emit=lambda e: {"emitted": True}, notify=lambda t, b: True)
    assert v["pulse_dir"] == fw.pulse_dir(root)


# ── the call sites: is the sensor wired to the LIVE artifact ───────────────

def test_the_real_watchdog_sweep_actually_pulses(tmp_path, monkeypatch):
    """Not "the call is in the file" — the real ``check.run()`` sweep, driven the
    way its own end-to-end test drives it, must leave a pulse on disk.

    This is the question the week keeps punishing people for skipping: a fence
    can be perfect and point at a twin nobody runs. Here the arm runs the LIVE
    sweep and then looks in the LIVE store, so a call site that is deleted,
    moved behind a branch that never executes, or left in dry-run goes red.

    Sandbox: the pulse store is steered entirely by the module's own env
    override to a directory under ``tmp_path``, asserted before the sweep."""
    import datetime as dt

    from framework.watchdog import check
    from framework.watchdog import registry as reg
    from framework.watchdog.tests.test_registry import FakeProbe

    store = tmp_path / "liveness"
    monkeypatch.setenv(fw.deadman.STATE_ENV, str(store))
    assert fw.pulse_dir().startswith(str(tmp_path)), "sandbox escape"
    assert not os.path.exists(fw.pulse_dir())

    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30,
                        tzinfo=dt.timezone(dt.timedelta(hours=2)))
    probe = FakeProbe(now=now, local=local, files={}, mtimes={}, redis={})

    check.run(probe=probe, dry_run=False)

    s = fw.scan(fw.pulse_dir())
    assert s["observed"] is True
    assert "outcome-watchdog" in s["pulses"], \
        "the live sweep did not pulse — the fleet dead-man is watching nothing"
    assert s["pulses"]["outcome-watchdog"]["ts"] is not None


def test_the_inbound_poller_pulses_only_after_an_answered_poll():
    """The poller's pulse must sit AFTER the `ok` check, so a lane stuck in a
    retry loop reads as dead rather than as a spinning process.

    Asserted structurally over the source: the pulse call must appear after the
    `getUpdates not ok` guard and after the exception handler's `continue`, both
    of which skip it. A poller that pulsed at the top of the loop would have
    reported the 6-day ConnectionRefused wedge as a healthy intake lane."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    src = open(os.path.join(root, "cabinet/scripts/officer-inbound-poller.py"),
               encoding="utf-8").read()
    pulse_at = src.index('_dm.pulse("officer-inbound")')
    ok_guard = src.index('log(f"getUpdates not ok:')
    err_guard = src.index('log(f"getUpdates error:')
    assert ok_guard < pulse_at, "the pulse precedes the ok-guard it depends on"
    assert err_guard < pulse_at, "the pulse precedes the error path that skips it"
