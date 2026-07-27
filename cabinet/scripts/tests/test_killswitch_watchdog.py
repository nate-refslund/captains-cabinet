"""killswitch-watchdog re-arm backstop (captain-controls Phase 1, 2026-07-17).

Raw ``DEL cabinet:killswitch`` bypasses the E-stop silently; the watchdog
re-arms whenever the switch reads INACTIVE while the ledger's newest arm has
no sanctioned (payload.via="kill-switch.sh") deactivation at/after it — after
a ceremony grace, through kill-switch.sh itself (attributable audit row), with
ONE plain-English captain notification through the channel door.

BEHAVIORAL tests ride the test_kill_switch_events.py idiom: a disposable
redis + a tmp CABINET_EVENT_LOG_DIR, driving the REAL kill-switch.sh (worktree
copy) and the REAL watchdog script via subprocess. Channel notification is
proven ATTEMPTED by reaching the real door with fake env creds present — in a
non-runtime env ``allow_sends()`` is False, so the door answers
``blocked-dev`` with ZERO network (belt: TELEGRAM_API_BASE points at a dead
local port).

SAFETY (incident 2026-07-27): this file ACTIVATES a real emergency stop, so
every child goes through ``lib_killswitch_fence``. Redirecting with REDIS_URL
alone was not enough — the shared resolver prefers REDIS_HOST/REDIS_PORT and
resolves the stop marker from CABINET_ROOT, all of which the officer plists
export, so the fence pins every channel the resolver consults and then PROVES
the redirection took by asking that resolver where it would go. It refuses to
run rather than fall through to whatever it finds.

UNIT tests hit the pure ``decide()`` seam directly — including the
authority-transitions interplay: an OBSERVED (actor authority-watch,
attribution=state-observed, no ``via``) deactivation row describes the raw
clear and must never sanction it.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SWITCH = REPO / "cabinet/scripts/kill-switch.sh"
WATCHDOG = REPO / "cabinet/scripts/killswitch-watchdog.py"

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(REPO)):        # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_killswitch_fence as ksfence  # noqa: E402

_HAVE_REDIS = all(shutil.which(t) for t in ("redis-server", "redis-cli"))
needs_redis = pytest.mark.skipif(
    not _HAVE_REDIS, reason="redis-server/redis-cli not on PATH")

_spec = importlib.util.spec_from_file_location("killswitch_watchdog", WATCHDOG)
ksw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ksw)

UTC = dt.timezone.utc


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture()
def sandbox_redis(tmp_path):
    port = None
    proc = None
    for candidate in range(26200, 26220):
        proc = subprocess.Popen(
            ["redis-server", "--port", str(candidate), "--bind", "127.0.0.1",
             "--save", "", "--appendonly", "no", "--dir", str(tmp_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            ping = subprocess.run(["redis-cli", "-p", str(candidate), "PING"],
                                  capture_output=True, text=True)
            if "PONG" in ping.stdout:
                port = candidate
                break
            time.sleep(0.1)
        if port:
            break
        proc.kill()
    assert port, "could not start disposable redis"
    yield port
    proc.kill()


def _fenced_env(port, events_dir, base=None, extra=None):
    """Child env with EVERY killswitch routing channel pinned at the sandbox.

    Setting REDIS_URL alone is NOT a fence: ``_ks_endpoint`` in
    hooks/killswitch-read.sh PREFERS REDIS_HOST/REDIS_PORT, and the officer
    plists export exactly those — so on the runtime's normal environment these
    tests drove ``kill-switch.sh activate`` against the LIVE control plane
    (incident 2026-07-27). The stop marker went the same way via CABINET_ROOT,
    and ``deactivate`` unlinks it. The fence derives the channel set from the
    resolver and PROVES the redirection took, or refuses to run.
    """
    return ksfence.sandbox_env(
        port,
        marker=Path(events_dir).parent / "killswitch-estop-marker",
        base=base, extra=extra)


def _base_env(port, events_dir, state_file, grace_s):
    import os
    base = dict(os.environ)
    base.pop("CABINET_ENV", None)         # never runtime: the door must gate
    return _fenced_env(port, events_dir, base=base, extra={
        "CABINET_EVENT_LOG_DIR": str(events_dir),
        "CABINET_KILLSWITCH_WATCHDOG_STATE_FILE": str(state_file),
        "CABINET_KILLSWITCH_REARM_GRACE_S": str(grace_s),
        # Fake creds so notify reaches the REAL channel door (which answers
        # blocked-dev in non-runtime env, zero network); belt: dead API base.
        "TELEGRAM_COS_TOKEN": "test-token",
        "CAPTAIN_TELEGRAM_ID": "12345",
        "TELEGRAM_API_BASE": "http://127.0.0.1:9",
    })


def _run_switch(action, port, events_dir, extra_env=None):
    env = _fenced_env(port, events_dir, extra={
        "CABINET_EVENT_LOG_DIR": str(events_dir), **(extra_env or {})})
    return subprocess.run(["bash", str(SWITCH), action], env=env,
                          capture_output=True, text=True, timeout=30)


def _run_watchdog(port, events_dir, state_file, grace_s=0, args=()):
    env = _base_env(port, events_dir, state_file, grace_s)
    return subprocess.run(
        [sys.executable, str(WATCHDOG), *args], env=env,
        capture_output=True, text=True, timeout=60)


def _summary(proc):
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    assert lines, f"no summary line (stderr: {proc.stderr})"
    return json.loads(lines[-1])


def _events(events_dir: Path) -> list:
    rows = []
    for f in sorted(Path(events_dir).glob("events-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return [r for r in rows if str(r.get("event_type", "")).startswith(
        "kill_switch_")]


def _redis_get(port):
    out = subprocess.run(
        ["redis-cli", "-p", str(port), "GET", "cabinet:killswitch"],
        capture_output=True, text=True)
    return out.stdout.strip()


# ---------------------------------------------------------------------------
# Behavioral (disposable redis + tmp ledger, the brief's four scenarios)
# ---------------------------------------------------------------------------

@needs_redis
def test_switch_active_is_a_noop(sandbox_redis, tmp_path):
    events = tmp_path / "events"
    assert _run_switch("activate", sandbox_redis, events).returncode == 0
    proc = _run_watchdog(sandbox_redis, events, tmp_path / "state.json")
    assert proc.returncode == 0, proc.stderr
    assert _summary(proc)["action"] == "noop-active"
    assert _redis_get(sandbox_redis) == "active"
    assert len(_events(events)) == 1          # nothing new emitted


@needs_redis
def test_sanctioned_resume_is_never_fought(sandbox_redis, tmp_path):
    events = tmp_path / "events"
    assert _run_switch("activate", sandbox_redis, events).returncode == 0
    assert _run_switch("deactivate", sandbox_redis, events).returncode == 0
    # grace 0: even with no grace protection the sanctioned resume holds.
    proc = _run_watchdog(sandbox_redis, events, tmp_path / "state.json",
                         grace_s=0)
    assert proc.returncode == 0, proc.stderr
    assert _summary(proc)["action"] == "noop-sanctioned-resume"
    assert _redis_get(sandbox_redis) == ""    # still resumed
    assert [r["event_type"] for r in _events(events)] == [
        "kill_switch_activated", "kill_switch_deactivated"]


@needs_redis
def test_unattributed_clear_rearms_after_grace_with_notification(
        sandbox_redis, tmp_path):
    events = tmp_path / "events"
    state = tmp_path / "state.json"
    assert _run_switch("activate", sandbox_redis, events).returncode == 0
    # The bypass: a raw DEL, no ceremony, no audit row.
    subprocess.run(["redis-cli", "-p", str(sandbox_redis), "DEL",
                    "cabinet:killswitch"], capture_output=True, check=True)

    # Tick 1 — inside the grace: observed, never fought yet.
    t1 = _run_watchdog(sandbox_redis, events, state, grace_s=1)
    assert t1.returncode == 0, t1.stderr
    assert _summary(t1)["action"] == "grace-pending"
    assert _redis_get(sandbox_redis) == ""
    assert len(_events(events)) == 1

    time.sleep(1.2)

    # Tick 2 — the anomaly persisted past the grace: re-arm + notify.
    t2 = _run_watchdog(sandbox_redis, events, state, grace_s=1)
    assert t2.returncode == 0, t2.stderr
    summary = _summary(t2)
    assert summary["action"] == "re-arm"
    assert summary["rearm_rc"] == 0
    # Notification ATTEMPTED through the real door; the non-runtime gate
    # answers blocked-dev (zero network) — proving the path was exercised.
    assert summary["notified"] == "blocked-dev"

    assert _redis_get(sandbox_redis) == "active"
    rows = _events(events)
    assert [r["event_type"] for r in rows] == [
        "kill_switch_activated", "kill_switch_activated"]
    assert rows[-1]["actor"] == "killswitch-watchdog"     # signs its name
    assert rows[-1]["payload"]["via"] == "kill-switch.sh"  # sanctioned surface

    doc = json.loads(state.read_text(encoding="utf-8"))
    assert "anomaly" not in doc["state"]                  # episode closed
    assert doc["state"]["last_rearm"]["notified"] == "blocked-dev"


@needs_redis
def test_grace_protects_an_inflight_ceremony(sandbox_redis, tmp_path):
    """activate … deactivate seconds later: the watchdog observes the cleared
    key mid-ceremony but must wait out the grace; once the sanctioned
    deactivation row lands it stands down entirely."""
    events = tmp_path / "events"
    state = tmp_path / "state.json"
    assert _run_switch("activate", sandbox_redis, events).returncode == 0
    subprocess.run(["redis-cli", "-p", str(sandbox_redis), "DEL",
                    "cabinet:killswitch"], capture_output=True, check=True)

    mid = _run_watchdog(sandbox_redis, events, state, grace_s=600)
    assert _summary(mid)["action"] == "grace-pending"
    assert _redis_get(sandbox_redis) == ""                # never fought

    # The ceremony completes: sanctioned deactivation row lands.
    assert _run_switch("deactivate", sandbox_redis, events).returncode == 0

    after = _run_watchdog(sandbox_redis, events, state, grace_s=600)
    assert _summary(after)["action"] == "noop-sanctioned-resume"
    assert _redis_get(sandbox_redis) == ""
    assert len([r for r in _events(events)
                if r["event_type"] == "kill_switch_activated"]) == 1
    doc = json.loads(state.read_text(encoding="utf-8"))
    assert "anomaly" not in doc["state"]                  # episode cleared


@needs_redis
def test_missing_events_dir_is_a_loud_failsafe_noop(sandbox_redis, tmp_path):
    # Switch INACTIVE (key absent) + no ledger dir: the clear cannot be
    # attributed either way — never a guessed re-arm.
    missing = tmp_path / "never-created"
    proc = _run_watchdog(sandbox_redis, missing, tmp_path / "state.json")
    assert proc.returncode == 0, proc.stderr
    assert _summary(proc)["action"] == "noop-events-unreadable"
    assert "WARN" in proc.stderr and "fail-safe no-op" in proc.stderr
    assert _redis_get(sandbox_redis) == ""                # untouched


def test_unreachable_redis_is_a_loud_failsafe_noop(tmp_path):
    """Probe-listed invariant: a dead control plane → WARN + fail-safe
    no-op, rc 0 (everything else already treats unreachable as ACTIVE; a
    guessed re-arm proves nothing). Port 9 refuses instantly; a missing
    redis-cli binary lands on the same None branch, so no redis marker."""
    events = tmp_path / "events"
    events.mkdir()
    state = tmp_path / "state.json"
    proc = _run_watchdog(9, events, state)
    assert proc.returncode == 0, proc.stderr
    assert _summary(proc)["action"] == "noop-unobservable-redis"
    assert "WARN" in proc.stderr and "unreachable" in proc.stderr
    assert not state.exists()                             # nothing written


@needs_redis
def test_dry_run_reports_but_never_acts(sandbox_redis, tmp_path):
    events = tmp_path / "events"
    state = tmp_path / "state.json"
    assert _run_switch("activate", sandbox_redis, events).returncode == 0
    subprocess.run(["redis-cli", "-p", str(sandbox_redis), "DEL",
                    "cabinet:killswitch"], capture_output=True, check=True)
    proc = _run_watchdog(sandbox_redis, events, state, grace_s=0,
                         args=("--dry-run",))
    assert proc.returncode == 0, proc.stderr
    # grace 0 + no prior state: first sighting still only starts the clock.
    assert _summary(proc)["action"] == "grace-pending"
    assert not state.exists()                             # no state write
    assert _redis_get(sandbox_redis) == ""
    assert len(_events(events)) == 1


@needs_redis
def test_dry_run_never_rearms_even_past_grace(sandbox_redis, tmp_path):
    """Mutation pin: deleting the ``not args.dry_run`` guard on the re-arm
    branch must fail a test. Anomaly state pre-seeded past the grace (keyed
    to the REAL arm row, decide()'s key fallback mirrored): the verdict is
    REPORTED as re-arm, but dry-run performs no SET, no rearm_rc, no
    notification, no state write."""
    events = tmp_path / "events"
    state = tmp_path / "state.json"
    assert _run_switch("activate", sandbox_redis, events).returncode == 0
    subprocess.run(["redis-cli", "-p", str(sandbox_redis), "DEL",
                    "cabinet:killswitch"], capture_output=True, check=True)
    arm = _events(events)[0]
    arm_key = str(arm.get("id") or arm.get("created_at") or "")
    state.write_text(json.dumps({
        "updated_at": "2026-07-01T00:00:00Z",
        "state": {"anomaly": {"key": arm_key,
                              "first_seen": "2026-07-01T00:00:00Z"}}}),
        encoding="utf-8")
    before = state.read_text(encoding="utf-8")
    proc = _run_watchdog(sandbox_redis, events, state, grace_s=1,
                         args=("--dry-run",))
    assert proc.returncode == 0, proc.stderr
    summary = _summary(proc)
    assert summary["action"] == "re-arm"                  # verdict reported…
    assert "rearm_rc" not in summary                      # …never executed
    assert "notified" not in summary
    assert _redis_get(sandbox_redis) == ""                # no SET
    assert len(_events(events)) == 1                      # no new audit row
    assert state.read_text(encoding="utf-8") == before    # no state write


# ---------------------------------------------------------------------------
# Unit — the pure decide() seam (no redis, runs everywhere incl. Linux CI)
# ---------------------------------------------------------------------------

def _ts(minute, second=0):
    return dt.datetime(2026, 7, 1, 12, minute, second, tzinfo=UTC).isoformat()


def _row(rid, etype, created, *, sanctioned=False, observed=False):
    payload = {"killswitch_id": "cabinet:killswitch"}
    if sanctioned:
        payload["via"] = "kill-switch.sh"
    if observed:
        payload["attribution"] = "state-observed"
    return {"id": rid, "event_type": etype, "created_at": created,
            "actor": "authority-watch" if observed else "captain",
            "payload": payload}


NOW = dt.datetime(2026, 7, 1, 13, 0, 0, tzinfo=UTC)


def test_decide_active_clears_anomaly():
    prev = {"anomaly": {"key": "arm-a", "first_seen": "2026-07-01T12:00:00Z"}}
    v = ksw.decide("active", [], prev, NOW, 90)
    assert v["action"] == "noop-active"
    assert "anomaly" not in v["state"]


def test_decide_cold_ledger_is_noop():
    v = ksw.decide("inactive", [], {}, NOW, 90)
    assert v["action"] == "noop-cold"


def test_decide_observed_deactivation_never_sanctions():
    """The authority-transitions sweep records the raw clear as an OBSERVED
    kill_switch_deactivated row (attribution=state-observed, no via). Newest
    row order must not fool the watchdog: the clear stays unattributed."""
    rows = [
        _row("arm-a", "kill_switch_activated", _ts(0), sanctioned=True),
        _row("obs-a", "kill_switch_deactivated", _ts(5), observed=True),
    ]
    v1 = ksw.decide("inactive", rows, {}, NOW, 90)
    assert v1["action"] == "grace-pending"
    # Same episode persisting past the grace → re-arm.
    later = NOW + dt.timedelta(seconds=120)
    v2 = ksw.decide("inactive", rows, v1["state"], later, 90)
    assert v2["action"] == "re-arm"
    assert v2["anomaly_age_s"] >= 90


def test_decide_sanctioned_resume_wins_over_observer_noise():
    rows = [
        _row("arm-a", "kill_switch_activated", _ts(0), sanctioned=True),
        _row("dea-a", "kill_switch_deactivated", _ts(5), sanctioned=True),
        _row("obs-a", "kill_switch_deactivated", _ts(6), observed=True),
    ]
    v = ksw.decide("inactive", rows, {}, NOW, 90)
    assert v["action"] == "noop-sanctioned-resume"
    assert "anomaly" not in v["state"]


def test_decide_new_arm_after_sanctioned_resume_is_a_new_episode():
    """A later arm (even an OBSERVED one — a raw SET is still an arm) with no
    sanctioned deactivation after it re-opens the anomaly."""
    rows = [
        _row("arm-a", "kill_switch_activated", _ts(0), sanctioned=True),
        _row("dea-a", "kill_switch_deactivated", _ts(5), sanctioned=True),
        _row("arm-b", "kill_switch_activated", _ts(10), observed=True),
    ]
    v = ksw.decide("inactive", rows, {}, NOW, 90)
    assert v["action"] == "grace-pending"
    assert v["state"]["anomaly"]["key"] == "arm-b"


def test_decide_anomaly_key_change_restarts_the_grace_clock():
    prev = {"anomaly": {"key": "arm-a",
                        "first_seen": "2026-07-01T11:00:00Z"}}  # long ago
    rows = [_row("arm-b", "kill_switch_activated", _ts(50), sanctioned=True)]
    v = ksw.decide("inactive", rows, prev, NOW, 90)
    assert v["action"] == "grace-pending"          # new episode, fresh clock
    assert v["state"]["anomaly"]["key"] == "arm-b"
    assert v["anomaly_age_s"] == 0


def test_decide_rearm_only_past_grace_same_episode():
    rows = [_row("arm-a", "kill_switch_activated", _ts(0), sanctioned=True)]
    first = ksw.decide("inactive", rows, {}, NOW, 90)
    assert first["action"] == "grace-pending"
    inside = ksw.decide("inactive", rows, first["state"],
                        NOW + dt.timedelta(seconds=30), 90)
    assert inside["action"] == "grace-pending"
    past = ksw.decide("inactive", rows, first["state"],
                      NOW + dt.timedelta(seconds=91), 90)
    assert past["action"] == "re-arm"


def test_rearm_timeout_lands_on_the_fatal_path(tmp_path, monkeypatch, capsys):
    """A kill-switch.sh hang past rearm()'s 30s timeout must land on the
    same FATAL contract as a nonzero exit: FATAL line, rc 1, anomaly KEPT
    so the next tick retries — never a raw traceback."""
    rows = [_row("arm-a", "kill_switch_activated", _ts(0), sanctioned=True)]
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "updated_at": "2026-07-01T00:00:00Z",
        "state": {"anomaly": {"key": "arm-a",
                              "first_seen": "2026-07-01T00:00:00Z"}}}),
        encoding="utf-8")
    monkeypatch.setattr(ksw, "observe_killswitch", lambda: "inactive")
    monkeypatch.setattr(ksw, "read_kill_switch_rows", lambda _d: rows)

    def _hang():
        raise subprocess.TimeoutExpired(cmd="kill-switch.sh", timeout=30)

    monkeypatch.setattr(ksw, "rearm", _hang)
    rc = ksw.main(["--state-file", str(state), "--grace-s", "1"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "FATAL" in captured.err and "timeout" in captured.err
    summary = json.loads(captured.out.strip().splitlines()[-1])
    assert summary["action"] == "re-arm"
    assert summary["rearm_rc"] == "timeout"
    doc = json.loads(state.read_text(encoding="utf-8"))
    assert doc["state"]["anomaly"]["key"] == "arm-a"      # retry next tick


def test_watchdog_only_ever_activates():
    """E-stop asymmetry pin: the watchdog's source must never call the
    deactivate verb — halting is its only power."""
    src = WATCHDOG.read_text(encoding="utf-8")
    import re
    calls = re.findall(r'"deactivate"', src)
    assert calls == [], "watchdog must never invoke deactivate"


def test_service_row_is_manifested():
    """The clock lives in cabinet/services.yml (fleet-manifest law): row
    present, 60s cadence, watchdog kind. The disabled pin is CONDITIONAL —
    the test_cron_officer_targets W10 convention: `disabled: true` is
    allowed ONLY alongside a non-empty `disabled_reason`, so the documented
    enable ceremony (remove the flag, generate-plists, load) never turns
    this test red the day the safety organ is armed."""
    import yaml
    services = yaml.safe_load(
        (REPO / "cabinet/services.yml").read_text(encoding="utf-8"))["services"]
    row = {s.get("name"): s for s in services}.get("killswitch-watchdog")
    assert row, "killswitch-watchdog row missing from cabinet/services.yml"
    assert row.get("label") == "com.cabinet.killswitch-watchdog"
    assert row.get("kind") == "watchdog"
    assert row.get("command") == (
        "python3.12 cabinet/scripts/killswitch-watchdog.py")
    assert row.get("schedule", {}).get("interval_s") == 60
    if row.get("disabled"):
        reason = str(row.get("disabled_reason") or "").strip()
        assert reason, (
            "killswitch-watchdog disabled WITHOUT a disabled_reason — "
            "silent unscheduling is the W10 regression class")
