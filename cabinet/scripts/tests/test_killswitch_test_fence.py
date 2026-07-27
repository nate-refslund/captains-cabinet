"""No test may reach a control plane it does not own. Mechanically.

INCIDENT 2026-07-27. ``test_killswitch_watchdog.py`` and
``test_kill_switch_events.py`` redirected their children with ``REDIS_URL``
only, while ``_ks_endpoint`` in ``cabinet/scripts/hooks/killswitch-read.sh``
PREFERS ``REDIS_HOST``/``REDIS_PORT`` — both exported by every officer plist.
``test_killswitch_telegram_card.py`` pinned the redis channel but left the
filesystem stop marker on the ambient ``CABINET_ROOT``, and it drives
``deactivate``, which ``rm -f``s that marker. All three were reproduced: the
first two ARMED a foreign control plane, the third DELETED an armed stop marker.

Each failed its own assertions immediately afterwards — which is the point. The
red tells you nothing about what the test already did to the live switch, and
attribution is destroyed by the write itself even when the value is restored.

WHY THIS FILE MUST POISON THE ENVIRONMENT. On a clean env — every CI runner —
none of these variables exist, the resolver falls through to ``REDIS_URL``, and
all three pre-fix files PASS. The hole is invisible exactly where it is tested
and open exactly where it is not. A guard that inherits the runner's clean env
therefore proves nothing; it must deliberately export the runtime's variables at
a canary and check the canary afterwards. That is the "what does the test
environment guarantee that production does not" question, answered in code.

TWO GUARDS, DIFFERENT JOBS:
  * structural — a test that hands the emergency stop a MUTATING verb must go
    through ``lib_killswitch_fence``. Catches a NEW file before it can be run
    on a runtime box. Scope is the write set on purpose: ``status`` is a pure
    read and is not fenced here (``test_killswitch_fail_closed.py`` and
    ``framework/learning/tests/test_gate.py`` are status-only by measurement).
  * behavioral — actually run those files against a canary control plane and an
    armed canary marker, and prove neither moved. This is the incident itself,
    turned into a permanent arm.

NON-VACUITY, verified both directions: checked out at the pre-fix commit and run
under the same poison, the behavioral arm goes RED with the canary key set to
``active`` (redis channel) and the canary marker deleted (marker channel), and
the structural arm goes RED naming the unfenced files.

WHAT THIS FILE DOES **NOT** SEE — stated because a guard that is read as total
coverage is worse than no guard. The detector is tracked ``test_*.py`` naming the
emergency surface AND passing it a quoted mutating verb, so it is structurally
blind to:
  * shell and TypeScript tests (``cabinet/tests/hook-regression/*.sh``,
    ``cabinet/scripts/test-escalation.sh``);
  * a direct ``redis-cli SET/DEL cabinet:killswitch`` that never names the script;
  * every OTHER safety switch — observe-only, captain-vetoes, the act-first kind
    freeze, and the evidence judging-freeze.
Those were swept by hand for this change and the findings recorded in the PR;
they are NOT held green by anything here.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TESTS = REPO / "cabinet" / "scripts" / "tests"

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(REPO)):        # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_killswitch_fence as ksfence  # noqa: E402

_HAVE_REDIS = all(shutil.which(t) for t in ("redis-server", "redis-cli"))
needs_redis = pytest.mark.skipif(
    not _HAVE_REDIS, reason="redis-server/redis-cli not on PATH")

#: A verb that CHANGES the switch. ``status`` is a read and is out of scope —
#: the standing rule is about a live safety switch in a test's WRITE set.
_MUTATING = ("activate", "deactivate")


def _emergency_stop_writers() -> list[Path]:
    """Test files that hand the emergency stop a mutating verb.

    Derived, not listed: any tracked ``test_*.py`` that names the emergency
    surface AND passes it a quoted mutating verb. A new file doing the same is
    picked up with no edit here.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=str(REPO),
        capture_output=True, text=True, timeout=60).stdout.split()
    out = []
    for rel in tracked:
        p = REPO / rel
        if not p.name.startswith("test_") or p.name == Path(__file__).name:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not re.search(r"kill-switch\.sh|killswitch-watchdog", text):
            continue
        verbs = set(re.findall(r"""["'](activate|deactivate)["']""", text))
        if verbs:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# The fence itself
# ---------------------------------------------------------------------------

def test_fence_knows_every_channel_the_resolver_consults():
    """Drift arm: a NEW routing variable in the resolver must not slip in
    silently under-fenced. Derived from the consumer, so this goes red the day
    someone teaches killswitch-read.sh a new endpoint variable."""
    unknown = ksfence.derive_channels() - ksfence._HANDLERS
    assert not unknown, (
        f"killswitch-read.sh now routes on {sorted(unknown)}, which "
        "lib_killswitch_fence cannot sandbox — tests would fall through to "
        "whatever those name.")


def test_derive_channels_finds_the_channels_that_caused_the_incident():
    """Non-vacuity for the derivation: it must actually FIND the variables,
    not return an empty set that trivially satisfies the arm above."""
    found = ksfence.derive_channels()
    for required in ("REDIS_HOST", "REDIS_PORT", "REDIS_URL",
                     "CABINET_ROOT", "CABINET_ESTOP_MARKER"):
        assert required in found, f"{required} not derived from the resolver"


def test_derivation_excludes_resolver_outputs():
    """The resolver's own result variables are not inputs; if they leak in,
    the fence's unknown-channel arm becomes noisy and gets disabled."""
    found = ksfence.derive_channels()
    assert "KS_VERDICT" not in found and "KS_REASON" not in found


def test_the_read_only_key_knob_is_not_offered_as_a_fence():
    """`KILLSWITCH_KEY` steers only the READ — `kill-switch.sh` hardcodes the
    key on BOTH write paths. A test pointing it at a sandbox key would arm the
    LIVE switch and then read back a different, empty key: it would print
    ACTIVATION FAILED having already done the damage. So it must not be a
    parameter, and the fence must pin it to the literal the writer uses."""
    import inspect
    assert "key" not in inspect.signature(ksfence.sandbox_env).parameters, (
        "sandbox_env must not offer a key= knob — see the docstring on "
        "_WRITER_KEY for the failure it re-creates.")
    switch = (REPO / "cabinet" / "scripts" / "kill-switch.sh").read_text(
        encoding="utf-8")
    assert f"SET {ksfence._WRITER_KEY} active" in switch
    assert f"DEL {ksfence._WRITER_KEY}" in switch


def test_fence_refuses_the_pre_fix_env_shape(tmp_path):
    """The exact env the broken files built: REDIS_URL at the sandbox with an
    ambient REDIS_HOST/REDIS_PORT pointing elsewhere. Must REFUSE, not run."""
    marker = tmp_path / "estop"
    bad = dict(os.environ)
    bad.update({"REDIS_URL": "redis://127.0.0.1:26999",
                "REDIS_HOST": "127.0.0.1", "REDIS_PORT": "6379",
                "CABINET_ESTOP_MARKER": str(marker)})
    with pytest.raises(ksfence.KillswitchFenceError) as exc:
        ksfence.assert_isolated(bad, port=26999, marker=marker)
    assert "6379" in str(exc.value)          # names where it would have gone


def test_fence_refuses_an_unfenced_stop_marker(tmp_path):
    """`deactivate` unlinks the resolved marker, so a marker that escapes the
    tmp dir is a live-switch write. CABINET_ROOT ambient is the real case."""
    fake_root = tmp_path / "pretend-live"
    (fake_root / "instance" / "config").mkdir(parents=True)
    bad = dict(os.environ)
    bad.update({"REDIS_URL": "redis://127.0.0.1:26999",
                "REDIS_HOST": "127.0.0.1", "REDIS_PORT": "26999",
                "CABINET_ROOT": str(fake_root)})
    bad.pop("CABINET_ESTOP_MARKER", None)
    with pytest.raises(ksfence.KillswitchFenceError) as exc:
        ksfence.assert_isolated(bad, port=26999, marker=tmp_path / "estop")
    assert "stop marker" in str(exc.value)


def test_fence_overrides_a_poisoned_ambient_environment(tmp_path):
    """The positive arm: sandbox_env must WIN over the runtime's variables."""
    marker = tmp_path / "estop"
    poisoned = dict(os.environ)
    poisoned.update({"REDIS_HOST": "127.0.0.1", "REDIS_PORT": "6379",
                     "CABINET_ROOT": "/Users/nate/captains-cabinet"})
    env = ksfence.sandbox_env(26999, marker=marker, base=poisoned)
    got = ksfence.resolve_in_env(env)
    assert got["port"] == "26999"
    assert Path(got["marker"]).resolve() == marker.resolve()


# ---------------------------------------------------------------------------
# Structural — a new writer cannot reintroduce the hole unnoticed
# ---------------------------------------------------------------------------

def test_every_emergency_stop_writer_uses_the_fence():
    writers = _emergency_stop_writers()
    assert writers, (
        "found NO test that flips the emergency stop — the detector is broken, "
        "and a guard that matches nothing is not a guard.")
    unfenced = [p.relative_to(REPO) for p in writers
                if "lib_killswitch_fence" not in p.read_text(
                    encoding="utf-8", errors="replace")]
    assert not unfenced, (
        "these tests hand the emergency stop a mutating verb without going "
        f"through lib_killswitch_fence: {[str(p) for p in unfenced]}. Setting "
        "REDIS_URL alone is not a fence — the resolver prefers "
        "REDIS_HOST/REDIS_PORT and takes the stop-marker path from "
        "CABINET_ROOT, all of which the officer plists export.")


# ---------------------------------------------------------------------------
# Behavioral — the incident, as a permanent arm
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@needs_redis
def test_emergency_stop_writers_cannot_reach_an_unfenced_control_plane(tmp_path):
    """Run every emergency-stop writer with the OFFICER RUNTIME's environment
    exported at a canary, and prove the canary never moved.

    This is the only arm that tests the property directly rather than a proxy
    for it: not "does the file mention the fence" but "can this file reach a
    control plane it does not own".
    """
    writers = _emergency_stop_writers()
    assert writers, "no emergency-stop writers found — detector broken"

    port = _free_port()
    data = tmp_path / "canary-redis"
    data.mkdir()
    proc = subprocess.Popen(
        ["redis-server", "--port", str(port), "--bind", "127.0.0.1",
         "--save", "", "--appendonly", "no", "--dir", str(data)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def cli(*args):
        return subprocess.run(["redis-cli", "-p", str(port), *args],
                              capture_output=True, text=True,
                              timeout=15).stdout.strip()
    try:
        for _ in range(100):
            if cli("PING") == "PONG":
                break
            time.sleep(0.05)
        else:  # pragma: no cover - environment failure
            pytest.skip("canary redis did not come up")

        # An ARMED stop marker under a canary CABINET_ROOT: `deactivate`
        # unlinks whatever the marker path resolves to.
        canary_root = tmp_path / "canary-cabinet"
        (canary_root / "instance" / "config").mkdir(parents=True)
        canary_marker = canary_root / "instance" / "config" / "estop"
        canary_marker.write_text("active\n", encoding="utf-8")

        # A sentinel key so "the canary was never written" is measured against
        # a known non-empty baseline rather than against zero.
        cli("SET", "canary:sentinel", "untouched")
        before = cli("DBSIZE")

        env = dict(os.environ)
        env.update({                     # the officer runtime's normal env
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": str(port),
            "CABINET_ROOT": str(canary_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        env.pop("CABINET_ESTOP_MARKER", None)
        env.pop("REDIS_URL", None)

        run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             *[str(p) for p in writers]],
            cwd=str(REPO), env=env, capture_output=True, text=True, timeout=900)

        assert cli("GET", "cabinet:killswitch") == "", (
            "A TEST ARMED A CONTROL PLANE IT DOES NOT OWN. The canary redis "
            "holds cabinet:killswitch — on a real officer box that is the "
            f"Captain's emergency stop.\n{run.stdout[-3000:]}")
        assert canary_marker.is_file(), (
            "A TEST DELETED AN ARMED E-STOP MARKER outside its sandbox "
            "(kill-switch.sh deactivate unlinks the resolved marker path).\n"
            f"{run.stdout[-3000:]}")
        assert cli("DBSIZE") == before, (
            f"canary keyspace changed ({before} -> {cli('DBSIZE')}); a test "
            f"wrote to a control plane it does not own.\n{run.stdout[-3000:]}")
        assert run.returncode == 0, (
            "emergency-stop writers must also PASS under the officer "
            f"runtime's environment:\n{run.stdout[-3000:]}\n{run.stderr[-2000:]}")
    finally:
        proc.kill()
        proc.wait(timeout=10)
