"""kill-switch.sh flip-event audit trail (2026-07-17 amendment, Wave-1 e2).

Every VERIFIED flip of the emergency stop must leave a ledger row
(kill_switch_activated / kill_switch_deactivated) so switch history is
attributable — the incident: the Captain's 2026-07-15 lockdown read INACTIVE
on 07-16 and no record could say which actor cleared it. The ledger must
NEVER block the emergency surface (fail-quiet emit), and an UNVERIFIED flip
must emit nothing (a false "activated" row is worse than none).

These are BEHAVIORAL tests against the real script: a disposable redis
(same skip idiom as test_redis_state_replay.py) + a tmp CABINET_EVENT_LOG_DIR
(the emitter honors it; the repo conftest fences it anyway). The script under
test is the WORKTREE copy — the live inode is schg-locked and syncs via the
Captain ceremony in docs/proposals/germline-amendment-killswitch-events-2026-07-17.md.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet/scripts/kill-switch.sh"

_HAVE_REDIS = all(shutil.which(t) for t in ("redis-server", "redis-cli"))

pytestmark = pytest.mark.skipif(
    not _HAVE_REDIS, reason="redis-server/redis-cli not on PATH")


@pytest.fixture()
def sandbox_redis(tmp_path):
    port = None
    proc = None
    for candidate in range(26000, 26020):
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


def _run(action, port, events_dir, extra_env=None):
    import os
    env = dict(os.environ)
    env["REDIS_URL"] = f"redis://127.0.0.1:{port}"
    env["CABINET_EVENT_LOG_DIR"] = str(events_dir)
    env.update(extra_env or {})
    return subprocess.run(["bash", str(SCRIPT), action], env=env,
                          capture_output=True, text=True, timeout=30)


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


def test_verified_activate_and_deactivate_emit_rows(sandbox_redis, tmp_path):
    events = tmp_path / "events"
    r1 = _run("activate", sandbox_redis, events)
    assert r1.returncode == 0, r1.stderr
    assert "ACTIVATED (verified" in r1.stdout
    r2 = _run("deactivate", sandbox_redis, events)
    assert r2.returncode == 0, r2.stderr
    rows = _events(events)
    assert [r["event_type"] for r in rows] == [
        "kill_switch_activated", "kill_switch_deactivated"]
    for r in rows:
        assert r["payload"]["killswitch_id"] == "cabinet:killswitch"
        assert r["payload"]["via"] == "kill-switch.sh"
        assert r["actor"]  # attributable — never empty


def test_actor_honors_cabinet_officer_env(sandbox_redis, tmp_path):
    events = tmp_path / "events"
    _run("activate", sandbox_redis, events,
         extra_env={"CABINET_OFFICER": "cos"})
    rows = _events(events)
    assert rows and rows[0]["actor"] == "cos"


def test_unverified_flip_emits_nothing(tmp_path):
    """Redis unreachable → activation FAILS loudly (pre-existing contract)
    and must NOT leave a kill_switch_activated row: a false 'activated' in
    the ledger is worse than none."""
    events = tmp_path / "events"
    # A port nothing listens on — the read-back can never verify.
    r = _run("activate", 26099, events)
    assert r.returncode == 1
    assert "FAILED" in r.stderr
    assert _events(events) == []


def test_emit_failure_never_blocks_the_flip(sandbox_redis, tmp_path):
    """The emergency surface outranks its audit trail: with the emitter
    unusable (CABINET_EVENT_LOG_DIR pointing at a FILE), the flip itself
    must still succeed and verify."""
    events = tmp_path / "blocked"
    events.write_text("a file where the dir should be", encoding="utf-8")
    r = _run("activate", sandbox_redis, tmp_path / "unused",
             extra_env={"CABINET_EVENT_LOG_DIR": str(events)})
    assert r.returncode == 0, r.stderr
    assert "ACTIVATED (verified" in r.stdout


def test_status_never_emits(sandbox_redis, tmp_path):
    events = tmp_path / "events"
    _run("status", sandbox_redis, events)
    assert _events(events) == []


def test_event_types_are_registered_with_the_emitter():
    """The types must stay in the emitter registry — an unregistered type
    makes the fail-quiet emit a silent no-op forever (the B4 class)."""
    src = (REPO / "framework/events/emitter.py").read_text(encoding="utf-8")
    assert '"kill_switch_activated"' in src
    assert '"kill_switch_deactivated"' in src


def test_flip_emit_is_fail_quiet_by_source():
    """Source pin: the emit helper must carry `|| true` and discard output —
    the ledger may never block the emergency stop."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "emit_flip_event" in src
    # Body = lines between the function open and the LINE-anchored `}` (the
    # JSON payload inside the body contains `}` characters, so a naive
    # first-brace split truncates before the `|| true`).
    body_lines = []
    in_fn = False
    for line in src.splitlines():
        if line.startswith("emit_flip_event() {"):
            in_fn = True
            continue
        if in_fn and line.strip() == "}":
            break
        if in_fn:
            body_lines.append(line)
    body = "\n".join(body_lines)
    assert body, "emit_flip_event body not found"
    assert "|| true" in body
