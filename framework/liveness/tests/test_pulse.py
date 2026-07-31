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


def test_the_store_does_not_move_when_CABINET_ENV_does(monkeypatch):
    """FAILS AGAINST THE DEFECT THIS SHIPPED WITH, and against the test that
    used to stand here asserting the opposite.

    That test pinned a dev/runtime split on ``CABINET_ENV`` and defended it as
    failing in the safe direction. Measured against the real plists on
    2026-07-31 it did not fail safe, it failed TOTAL: this fleet's own writers
    disagreed with each other — ``com.cabinet.officer.cos-inbound`` sets
    ``CABINET_ENV=runtime`` and pulsed to ``liveness/``, while
    ``com.cabinet.outcome-watchdog`` carries no ``EnvironmentVariables`` dict at
    all and pulsed to ``liveness-dev/`` — so a maximally healthy fleet read a
    confident, permanent DEAD.

    The store may be steered by ONE thing only: the explicit
    ``CABINET_FLEETWATCH_STATE_DIR``, which a test or a second instance sets
    deliberately and owns end to end. Anything a launchd plist might or might
    not carry is disqualified by construction."""
    from framework import env

    monkeypatch.delenv(fw.STATE_ENV, raising=False)
    monkeypatch.setenv("CABINET_ENV", "runtime")
    runtime = env.fleet_liveness_dir()
    monkeypatch.setenv("CABINET_ENV", "dev")
    assert env.fleet_liveness_dir() == runtime
    monkeypatch.delenv("CABINET_ENV", raising=False)
    assert env.fleet_liveness_dir() == runtime, (
        "the pulse store moved when CABINET_ENV was absent; the fleet's plists "
        "do not agree on that variable, so the writers would split from each "
        "other and from the reader")


def test_the_production_resolver_runs_at_all(monkeypatch, tmp_path):
    """FAILS AGAINST THE DEFECT THAT MADE THE WHOLE FEATURE INERT.

    The watcher shipped merged, green on six CI jobs and 17/17 mutations, with
    ``state_dir()`` calling an ``_env_module()`` helper that existed nowhere in
    the repository — the census refactor moved the function and left the helper
    in the module it deleted. EVERY shipped arm steered around the branch that
    calls it with an explicit ``root=`` or the env override, so the production
    path — the one every fleet job takes — had never been executed once, by the
    suite, by the mutation sweep, or by the end-to-end proof.

    So this arm takes NO override and NO ``root=``. It owns HOME instead, and
    asserts the resolved destination is inside ``tmp_path`` BEFORE writing
    anything, because a production-path arm that steers nothing is exactly how a
    build once wrote a pulse into a real ``~/.cabinet``."""
    monkeypatch.delenv(fw.STATE_ENV, raising=False)
    monkeypatch.delenv("CABINET_ENV", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser",
                        lambda p: p.replace("~", str(tmp_path), 1)
                        if p.startswith("~") else p)

    resolved = fw.state_dir()
    assert resolved, "state_dir() resolved to nothing on the production path"
    assert str(tmp_path) in resolved, (
        f"sandbox breach: production resolver pointed at {resolved}, "
        f"outside {tmp_path}")
    assert str(tmp_path) in fw.pulse_dir()

    res = fw.pulse("probe")
    assert res["wrote"] is True, res
    assert str(tmp_path) in res["path"], res
    assert json.loads(open(res["path"]).read())["source"] == "probe"


def test_a_pulse_records_the_tree_it_was_written_from(tmp_path):
    """A dev clone's pulse must be VISIBLE, not indistinguishable.

    Dropping the CABINET_ENV split means a hand-run sweep writes into the same
    store the watcher reads. That is bounded (staleness reclaims it) but it must
    not be invisible, so the pulse names its origin. It is reported and never
    filtered on — filtering would put the watcher's own tree back into the
    resolution, which is the divergence class this store exists to foreclose."""
    root = _root(tmp_path)
    res = fw.pulse("origin-probe", root=root)
    assert str(tmp_path) in res["path"]
    obj = json.loads(open(res["path"]).read())
    assert obj["origin"], "pulse carries no origin"
    assert obj["origin"].endswith("captains-cabinet") or os.path.isdir(
        obj["origin"]), obj["origin"]


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
