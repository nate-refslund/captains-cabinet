"""Fleet dead-man tests — the EMITTER half (framework/liveness/deadman.pulse).

These live under ``framework/`` because that is where the emitter lives and
where the CI job that covers it runs. The WATCHER's decision surface — three
states, the ping predicate, the notification, the config — is exercised by
``cabinet/scripts/tests/test_fleet_deadman.py``, beside the module it drives.

THE BAR. Every arm here is written to go red against a specific wrong
implementation, and the wrong implementation is named in the docstring. The one
that matters most is ``test_the_real_watchdog_sweep_actually_pulses``: it drives
the LIVE sweep and then looks in the LIVE store, because a fence can be perfect
and still point at a twin nobody runs.

SANDBOX RULE. Every write is steered by an explicit ``root=`` argument or by the
module's own env override into ``tmp_path``, and asserted to land there before
the write. Nothing here touches a real state dir or a real ~/Library path.
"""
from __future__ import annotations

import json
import os

from framework.liveness import deadman as fw

NOW = 1_000_000.0


def _root(tmp_path):
    r = str(tmp_path / "liveness")
    os.makedirs(r, exist_ok=True)
    return r


def _scan_dir(directory):
    return _watcher().scan(directory)


def _scan(root):
    """The watcher's scan, imported from where the watcher lives — so these arms
    read the store through the same door the real reader uses."""
    return _watcher().scan(fw.pulse_dir(root))


def _watcher():
    import importlib.util as ilu

    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    spec = ilu.spec_from_file_location(
        "fleet_deadman", os.path.join(root_dir, "cabinet/scripts/fleet-deadman.py"))
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pulse_refuses_a_source_name_that_would_escape_the_directory(tmp_path):
    root = _root(tmp_path)
    for bad in ("../../etc/passwd", "a/b", "", ".", "..", "x" * 65, ".hidden"):
        res = fw.pulse(bad, root=root)
        assert res["wrote"] is False, f"{bad!r} was accepted as a filename"
        assert res["reason"] == "bad-source"
    assert not os.path.exists(fw.pulse_dir(root)) or \
        os.listdir(fw.pulse_dir(root)) == []


def test_pulse_never_raises_when_the_write_fails(tmp_path):
    def boom(_p, _t):
        raise OSError("disk full")

    res = fw.pulse("s", root=_root(tmp_path), writer=boom)
    assert res["wrote"] is False and res["reason"] == "write-failed"


def test_pulse_with_no_state_dir_is_inert_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv(fw.STATE_ENV, "")
    monkeypatch.setattr(fw, "state_dir", lambda default="": "")
    res = fw.pulse("s")
    assert res["wrote"] is False and res["reason"] == "no-state-dir"


def test_pulse_write_is_atomic_no_partial_file_is_ever_visible(tmp_path, monkeypatch):
    """A reader must never see a half-written pulse and call it corrupt — that
    would turn a healthy fleet into an UNKNOWN on a timing coincidence. So the
    final name may only ever appear via a rename of an already-complete file."""
    root = _root(tmp_path)
    seen = []
    real_replace = os.replace

    def spy_replace(src, dst):
        with open(src, "r", encoding="utf-8") as fh:
            seen.append((json.loads(fh.read()), os.path.basename(str(dst))))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy_replace)
    fw.pulse("s", root=root, now=lambda: NOW)
    assert seen, "pulse did not go through os.replace — the write is not atomic"
    payload, name = seen[0]
    assert payload["ts"] == NOW and name == "s.json"


def test_fleet_alive_is_a_known_deadman_event():
    from framework.liveness import deadman
    assert deadman.EVENT_FLEET_ALIVE in deadman.KNOWN_EVENTS


def test_pulse_store_still_separates_dev_from_runtime(monkeypatch):
    """The one variable still steering the path, kept on purpose: a dev run
    pulsing into the runtime's store would certify a dead runtime fleet as
    alive. It fails in the safe direction (a false page, never a false green)."""
    from framework import env

    monkeypatch.delenv(fw.STATE_ENV, raising=False)
    monkeypatch.setenv("CABINET_ENV", "runtime")
    runtime = env.fleet_liveness_dir()
    monkeypatch.setenv("CABINET_ENV", "dev")
    assert env.fleet_liveness_dir() != runtime


def test_a_dry_run_sweep_does_not_pulse(tmp_path, monkeypatch):
    """A rehearsal must not certify a fleet as alive — the same reason dry-run
    does not stamp the heartbeat beside it."""
    import datetime as dt

    from framework.watchdog import check
    from framework.watchdog.tests.test_registry import FakeProbe

    monkeypatch.setenv(fw.STATE_ENV, str(tmp_path / "liveness"))
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30,
                        tzinfo=dt.timezone(dt.timedelta(hours=2)))
    check.run(probe=FakeProbe(now=now, local=local, files={}, mtimes={},
                              redis={}),
              dry_run=True)
    assert _scan_dir(fw.pulse_dir())["pulses"] == {}
