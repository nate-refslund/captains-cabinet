"""/killswitch Telegram control card — poller command path + live-door proofs.

The captain-controls plan (2026-07-17) Phase 1: the Captain's /killswitch text
gets a mechanical status card from the POLLER process; Halt/Resume taps ride
the allowlisted verb door and execute cabinet/scripts/kill-switch.sh — the
audit row comes from the SCRIPT with CABINET_OFFICER=captain-telegram
provenance. Pinned here:

  * /killswitch routing is anchored + case-tolerant, never mid-sentence;
  * the card reply is mechanical (sendMessage with the minted keyboard) and
    falls OPEN to the Chair relay when the send fails — never silently
    consumed;
  * a NON-captain callback is acked (spinner cleared) but never applied —
    the captain gate sits BEFORE the kill-switch door;
  * run_kill_switch executes the real script against a DISPOSABLE redis
    (skip-if-no-redis idiom from test_redis_state_replay.py): both flips
    read-back-verified, audit rows actor=captain-telegram — attributable
    phone flips;
  * THE EVAL-001b DISTINCTION: with the switch ACTIVE the officer-side
    pre-tool-use hook still REFUSES a deactivate attempt (exit 2), while the
    poller door — this process, no officer hooks — deactivates and signs the
    ledger. Two doors, by design; neither weakened.

Run: python3.12 -m pytest cabinet/scripts/tests/test_killswitch_telegram_card.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
POLLER = REPO / "cabinet/scripts/officer-inbound-poller.py"
SCRIPT = REPO / "cabinet/scripts/kill-switch.sh"
HOOK = REPO / "cabinet/scripts/hooks/pre-tool-use.sh"

import sys  # noqa: E402
_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(REPO)):        # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_killswitch_fence as ksfence  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "officer_inbound_poller_killswitch", POLLER)
poller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poller)

_HAVE_REDIS = all(shutil.which(t) for t in ("redis-server", "redis-cli"))


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    """Never touch the live feed/attention estate from these tests."""
    monkeypatch.setenv("CABINET_FEED_DIR", str(tmp_path / "feed"))
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))


def _noop_log(*_a, **_k):
    pass


# ---------------------------------------------------------------------------
# Command routing — anchored, case-tolerant, @botname-tolerant
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "/killswitch", "/KillSwitch", "  /killswitch  ",
    "/killswitch@CabinetChairBot",
])
def test_killswitch_command_matches(text):
    assert poller.is_killswitch_command(text) is True


@pytest.mark.parametrize("text", [
    "", "/killswitchx", "/killswitch now", "about /killswitch",
    "what does /killswitch do?", "killswitch", "/kill switch",
])
def test_killswitch_command_rejects_non_commands(text):
    assert poller.is_killswitch_command(text) is False


# ---------------------------------------------------------------------------
# The card reply — mechanical send, fail-open floor
# ---------------------------------------------------------------------------

def test_command_reply_sends_status_card_with_minted_keyboard():
    posts = []
    ok = poller.killswitch_command_reply(
        api_post=lambda p, payload: posts.append((p, payload)),
        chat_id="999",
        ks_run=lambda a: (0, "Kill switch: INACTIVE (normal operation)"),
        log=_noop_log)
    assert ok is True
    (path, payload), = posts
    assert path == "sendMessage" and payload["chat_id"] == 999
    assert "🛑 Emergency stop" in payload["text"]
    assert "the cabinet is running" in payload["text"]
    flat = [b["callback_data"]
            for row in payload["reply_markup"]["inline_keyboard"] for b in row]
    assert flat == ["cv2|ksh", "cv2|ksr"]


def test_command_reply_unknown_state_is_fail_closed_wording():
    posts = []
    poller.killswitch_command_reply(
        api_post=lambda p, payload: posts.append(payload),
        chat_id="999", ks_run=lambda a: (2, "Kill switch: UNKNOWN — nope"),
        log=_noop_log)
    assert "treat it as ARMED" in posts[0]["text"]


def test_command_reply_send_failure_returns_false_for_relay_floor():
    def _post(_p, _payload):
        raise RuntimeError("telegram down")
    logs = []
    ok = poller.killswitch_command_reply(
        api_post=_post, chat_id="999",
        ks_run=lambda a: (0, "Kill switch: INACTIVE (normal operation)"),
        log=logs.append)
    assert ok is False
    assert any("falling back to relay" in l for l in logs)


# ---------------------------------------------------------------------------
# Captain gate — a stray's kill-switch tap is acked, never applied
# ---------------------------------------------------------------------------

def _cbq(data="cv2|ksr", frm=555, mid=9):
    return {"id": "cq1", "data": data, "from": {"id": frm},
            "message": {"message_id": mid}}


def test_stray_killswitch_tap_acked_but_never_applied():
    applied, injected, feeds, acked = [], [], [], []
    poller.handle_callback_query(
        _cbq(frm=555), captain="999",
        api_post=lambda p, payload: acked.append(p),
        inject=injected.append, feed_append=feeds.append, log=_noop_log,
        apply_tap=lambda d, **k: applied.append(d) or {"handled": True})
    assert acked == ["answerCallbackQuery"]     # spinner still cleared
    assert applied == [] and injected == [] and feeds == []


def test_captain_killswitch_tap_reaches_the_apply_seam_and_stays_quiet():
    applied, injected, feeds = [], [], []
    poller.handle_callback_query(
        _cbq(frm=999, mid=12), captain="999",
        api_post=lambda p, payload: None,
        inject=injected.append, feed_append=feeds.append, log=_noop_log,
        apply_tap=lambda d, *, message_id=None: applied.append(
            (d, message_id)) or {
            "handled": True, "relay": False, "mode": "killswitch:ksr",
            "outcome": "resumed", "summary": "deactivate rc=0"})
    assert applied == [("cv2|ksr", 12)]
    assert injected == []                       # mechanical — no Chair turn
    assert feeds and feeds[0]["mode"] == "killswitch:ksr"
    assert feeds[0]["outcome"] == "resumed"


# ---------------------------------------------------------------------------
# run_kill_switch — the poller-only door, real script, disposable redis
# ---------------------------------------------------------------------------

def test_unsanctioned_actions_raise():
    with pytest.raises(ValueError):
        poller.run_kill_switch("obliterate")
    with pytest.raises(ValueError):
        poller.run_kill_switch("deactivate; rm -rf /")


def test_missing_script_is_a_loud_tuple_not_an_exception(tmp_path):
    rc, out = poller.run_kill_switch(
        "status", script=str(tmp_path / "absent.sh"))
    # bash exits non-zero for an unreadable script — loud, never raising
    assert rc != 0


pytestmark_redis = pytest.mark.skipif(
    not _HAVE_REDIS, reason="redis-server/redis-cli not on PATH")


@pytest.fixture()
def sandbox_redis(tmp_path):
    """Disposable TCP redis (same idiom as test_kill_switch_events.py; band
    26400+ so parallel suites never collide)."""
    port = None
    proc = None
    for candidate in range(26400, 26420):
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


def _env(port, events_dir):
    """Every killswitch routing channel pinned at the sandbox, then PROVEN.

    This file was PARTIALLY fenced (incident 2026-07-27): it already pinned
    REDIS_HOST/REDIS_PORT for the redis channel, but left the FILESYSTEM stop
    marker on the ambient CABINET_ROOT that the officer plists export — and it
    drives ``deactivate``, which does ``rm -f`` on that marker. Reproduced: with
    CABINET_ROOT ambient, this file DELETED an armed estop marker and only then
    went red. A partial fence is the dangerous kind, because it reads as covered.
    """
    return ksfence.sandbox_env(
        port,
        marker=Path(events_dir).parent / "killswitch-estop-marker",
        extra={"CABINET_EVENT_LOG_DIR": str(events_dir)})


def _events(events_dir: Path) -> list:
    rows = []
    for f in sorted(Path(events_dir).glob("events-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return [r for r in rows
            if str(r.get("event_type", "")).startswith("kill_switch_")]


def _get_key(port):
    return subprocess.run(
        ["redis-cli", "-p", str(port), "GET", "cabinet:killswitch"],
        capture_output=True, text=True, timeout=10).stdout.strip()


@pytestmark_redis
def test_both_flips_verified_with_telegram_provenance(sandbox_redis, tmp_path):
    events = tmp_path / "events"
    env = _env(sandbox_redis, events)
    rc, out = poller.run_kill_switch("activate", env=env)
    assert rc == 0 and "KILL SWITCH ACTIVATED (verified by read-back)" in out
    assert _get_key(sandbox_redis) == "active"
    rc2, out2 = poller.run_kill_switch("deactivate", env=env)
    assert rc2 == 0
    assert "KILL SWITCH DEACTIVATED (verified by read-back)" in out2
    assert _get_key(sandbox_redis) == ""
    rows = _events(events)
    assert [r["event_type"] for r in rows] == [
        "kill_switch_activated", "kill_switch_deactivated"]
    for r in rows:            # the SCRIPT's ledger row carries the provenance
        assert r["actor"] == "captain-telegram"
        assert r["payload"]["via"] == "kill-switch.sh"


@pytestmark_redis
def test_status_read_through_the_door(sandbox_redis, tmp_path):
    env = _env(sandbox_redis, tmp_path / "events")
    rc, out = poller.run_kill_switch("status", env=env)
    assert rc == 0 and "Kill switch: INACTIVE" in out
    assert _events(tmp_path / "events") == []       # status never emits


@pytestmark_redis
def test_resume_tap_end_to_end_flips_and_repaints(sandbox_redis, tmp_path):
    """Tap → tap_wire re-validation → kill-switch.sh → verified output on the
    repainted card → audit row from the script. The whole Phase-1 loop."""
    import sys
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework.comms.surface import tap_wire

    events = tmp_path / "events"
    env = _env(sandbox_redis, events)
    rc, _ = poller.run_kill_switch("activate", env=env)   # arm first
    assert rc == 0 and _get_key(sandbox_redis) == "active"

    paints = []
    res = tap_wire.apply_tap(
        "cv2|ksr", message_id=77,
        edit_text=lambda mid, text, kb: paints.append((mid, text, kb)),
        ks_exec=lambda a: poller.run_kill_switch(a, env=env))
    assert res["handled"] is True and res["relay"] is False
    assert res["outcome"] == "resumed" and res["state"] == "off"
    assert _get_key(sandbox_redis) == ""                  # REALLY cleared
    (mid, text, kb), = paints
    assert mid == 77
    assert "KILL SWITCH DEACTIVATED (verified by read-back)" in text
    assert "the cabinet is running" in text               # fresh status read
    flat = [b["callback_data"] for row in kb for b in row]
    assert flat == ["cv2|ksh", "cv2|ksr"]
    rows = _events(events)
    assert rows[-1]["event_type"] == "kill_switch_deactivated"
    assert rows[-1]["actor"] == "captain-telegram"


@pytestmark_redis
def test_halt_tap_end_to_end_arms_the_switch(sandbox_redis, tmp_path):
    import sys
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework.comms.surface import tap_wire

    events = tmp_path / "events"
    env = _env(sandbox_redis, events)
    paints = []
    res = tap_wire.apply_tap(
        "cv2|ksh", message_id=78,
        edit_text=lambda mid, text, kb: paints.append(text),
        ks_exec=lambda a: poller.run_kill_switch(a, env=env))
    assert res["handled"] is True and res["outcome"] == "halted"
    assert _get_key(sandbox_redis) == "active"
    assert "KILL SWITCH ACTIVATED (verified by read-back)" in paints[0]
    assert "ARMED — everything is halted." in paints[0]
    rows = _events(events)
    assert rows[-1]["event_type"] == "kill_switch_activated"
    assert rows[-1]["actor"] == "captain-telegram"


@pytestmark_redis
def test_failed_flip_states_failure_on_the_card(tmp_path):
    """Executor pointed at a dead port: the flip fails, the repainted card
    says so LOUDLY with the script's own stderr — never silent."""
    import sys
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework.comms.surface import tap_wire

    env = _env(26399, tmp_path / "events")        # nothing listens here
    paints = []
    res = tap_wire.apply_tap(
        "cv2|ksh", message_id=79,
        edit_text=lambda mid, text, kb: paints.append(text),
        ks_exec=lambda a: poller.run_kill_switch(a, env=env))
    assert res["handled"] is False and res["relay"] is True
    assert "🚨 HALT FAILED — NOT verified." in paints[0]
    assert "ACTIVATION FAILED" in paints[0]       # the script's own words
    assert _events(tmp_path / "events") == []     # unverified ⇒ no false row


# ---------------------------------------------------------------------------
# THE DISTINCTION (EVAL-001b intact): officer session refused, poller door open
# ---------------------------------------------------------------------------

@pytestmark_redis
@pytest.mark.skipif(not shutil.which("jq"), reason="hook needs jq")
def test_officer_hook_still_refuses_while_poller_door_deactivates(
        sandbox_redis, tmp_path):
    events = tmp_path / "events"
    env = _env(sandbox_redis, events)
    rc, _ = poller.run_kill_switch("activate", env=env)
    assert rc == 0 and _get_key(sandbox_redis) == "active"

    # (a) OFFICER side: the germline pre-tool-use hook refuses the deactivate
    # attempt from a hooked session — EVAL-001b, byte-untouched by this lane.
    hook_env = dict(os.environ)
    hook_env.update({"OFFICER_NAME": "cos",
                     "REDIS_HOST": "127.0.0.1",
                     "REDIS_PORT": str(sandbox_redis)})
    attempt = json.dumps({
        "tool_name": "Bash",
        "tool_input": {
            "command": "bash cabinet/scripts/kill-switch.sh deactivate"}})
    p = subprocess.run(["bash", str(HOOK)], input=attempt,
                       capture_output=True, text=True, env=hook_env,
                       timeout=90)
    assert p.returncode == 2
    assert "KILL SWITCH" in p.stderr
    assert _get_key(sandbox_redis) == "active"     # refusal really held

    # (b) POLLER door: same action, same redis, NO officer hooks in the path —
    # deactivates, read-back verified, and SIGNS the ledger.
    rc2, out2 = poller.run_kill_switch("deactivate", env=env)
    assert rc2 == 0
    assert "KILL SWITCH DEACTIVATED (verified by read-back)" in out2
    assert _get_key(sandbox_redis) == ""
    rows = _events(events)
    assert rows[-1]["event_type"] == "kill_switch_deactivated"
    assert rows[-1]["actor"] == "captain-telegram"
