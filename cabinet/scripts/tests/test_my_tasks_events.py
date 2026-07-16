"""my-tasks.sh v1.3 durable task events (cabinet:tasks:events) — contracts.

Exercises the REAL script + the REAL lib/triggers.sh task_event_emit + the
REAL framework/triggers/envelope.py validator, with fake psql/redis-cli
transports on PATH (argv logged NUL-separated for byte-exact assertions —
the test_model_fallback_pager.py fake-transport convention). What is pinned:

  * emit-on-transition — every mutating verb lands exactly ONE XADD on
    cabinet:tasks:events carrying {task_id, old_status, new_status, actor,
    context_slug, ts} + an A6 envelope that passes envelope.validate();
  * no-emit-on-noop — block on an already-blocked row and unblock on an
    already-unblocked row (idempotent by spec §3.3) emit NOTHING; a failed
    mutation emits nothing and publishes nothing;
  * envelope law is a real GATE — an envelope validate() rejects (oversize
    `from`) is REFUSED at the producer: no XADD, loud stderr, and the verb
    still succeeds (emission is best-effort by design);
  * injection controls — a title carrying $(...) / backticks / quotes /
    pipes never reaches the event, the pub/sub payload, or a shell (canary
    file), and a title embedding "\n99|..." cannot spoof the event's task_id
    (parse anchors on the FIRST returning row);
  * pub/sub byte-parity — the dashboard SSE contract: exactly one PUBLISH to
    cabinet:tasks:updated per mutation whose payload byte-shape is exactly
    {"officer_slug":"<slug>","timestamp":"<ISO>Z"} — the event stream adds
    NOTHING to what existing consumers see.

Run: python3.12 -m pytest cabinet/scripts/tests/test_my_tasks_events.py -q
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet" / "scripts" / "my-tasks.sh"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from framework.triggers import envelope as envelope_mod  # noqa: E402

EVENTS_STREAM = "cabinet:tasks:events"
EVENTS_GROUP = "task-watch"
PUBSUB_CHANNEL = "cabinet:tasks:updated"
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
# The dashboard SSE contract, byte-exact modulo the clock (key order included).
PUBSUB_PAYLOAD_RE = re.compile(
    r'\{"officer_slug":"cto","timestamp":"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"\}'
)

CALL_MARK = b"--CALL--\0"


def _write_fake(bin_dir: Path, name: str, body: str) -> None:
    p = bin_dir / name
    p.write_text("#!/bin/bash\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def env(tmp_path):
    """Fake transports + a context-carrying CABINET_ROOT + argv logs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    cab_root = tmp_path / "root"
    (cab_root / "instance" / "config" / "contexts").mkdir(parents=True)
    (cab_root / "instance" / "config" / "contexts" / "testctx.yml").write_text(
        "slug: testctx\n")

    redis_log = log_dir / "redis.argv"
    psql_sql = log_dir / "psql.sql"
    # psql fake: swallow stdin (the heredoc SQL, logged), answer $PSQL_STDOUT.
    _write_fake(bin_dir, "psql",
                'cat >> "$PSQL_SQL_LOG"\n'
                'printf \'%s\\n\' "$PSQL_STDOUT"\n'
                'exit "${PSQL_RC:-0}"\n')
    # redis-cli fake: NUL-exact argv log, one --CALL-- marker per invocation.
    _write_fake(bin_dir, "redis-cli",
                'printf -- \'--CALL--\\0\' >> "$REDIS_ARGV_LOG"\n'
                'printf \'%s\\0\' "$@" >> "$REDIS_ARGV_LOG"\n'
                'exit 0\n')

    base = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "NEON_CONNECTION_STRING": "postgres://stub/stub",
        "CABINET_OFFICER": "cto",
        "CABINET_ROOT": str(cab_root),
        "REDIS_HOST": "127.0.0.1",
        "REDIS_ARGV_LOG": str(redis_log),
        "PSQL_SQL_LOG": str(psql_sql),
        # census kill-knob: never append envelope-violations lines into the
        # checkout from tests; enforcement stays deterministically ON.
        "CABINET_ENVELOPE_REPORT": "0",
        "CABINET_ENVELOPE_ENFORCE": "1",
    }
    base.pop("CABINET_CONTEXT", None)
    return {"env": base, "redis_log": redis_log, "tmp": tmp_path}


def _run(env: dict, psql_stdout: str, *argv: str, psql_rc: int = 0,
         officer_override: str | None = None) -> subprocess.CompletedProcess:
    e = dict(env["env"])
    e["PSQL_STDOUT"] = psql_stdout
    e["PSQL_RC"] = str(psql_rc)
    args = ["bash", str(SCRIPT), *argv, "--context", "testctx"]
    if officer_override is not None:
        args += ["--as", officer_override]
    return subprocess.run(args, env=e, capture_output=True, text=True,
                          timeout=60)


def _redis_calls(env: dict) -> list[list[str]]:
    log: Path = env["redis_log"]
    if not log.exists():
        return []
    out: list[list[str]] = []
    for chunk in log.read_bytes().split(CALL_MARK):
        if not chunk:
            continue
        parts = chunk.split(b"\0")
        # Drop ONLY the artifact of the trailing NUL terminator — interior
        # empties are REAL argv elements (old_status="" on creation events).
        if parts and parts[-1] == b"":
            parts.pop()
        argv = [a.decode("utf-8", "replace") for a in parts]
        if argv:
            out.append(argv)
    return out


def _xadds(env: dict) -> list[list[str]]:
    return [c for c in _redis_calls(env) if "XADD" in c]


def _publishes(env: dict) -> list[list[str]]:
    return [c for c in _redis_calls(env) if "PUBLISH" in c]


def _xadd_fields(call: list[str]) -> dict:
    i = call.index("*")
    pairs = call[i + 1:]
    return {pairs[j]: pairs[j + 1] for j in range(0, len(pairs) - 1, 2)}


def _assert_event(call: list[str], *, task_id: str, old: str, new: str,
                  actor: str = "cto", ctx: str = "testctx") -> dict:
    assert call[call.index("XADD") + 1] == EVENTS_STREAM
    f = _xadd_fields(call)
    assert f["task_id"] == task_id
    assert f["old_status"] == old
    assert f["new_status"] == new
    assert f["actor"] == actor
    assert f["context_slug"] == ctx
    assert ISO_RE.fullmatch(f["ts"]), f["ts"]
    payload = json.loads(f["envelope"])
    ok, reasons = envelope_mod.validate(payload)
    assert ok, f"A6 envelope invalid: {reasons}"
    assert payload["kind"] == "evidence"
    assert envelope_mod.ULID_RE.match(payload["id"])
    assert payload["taint"]["tier"] == "officer"
    assert payload["taint"]["sources"]
    return f


# ---------------------------------------------------------------------------
# Emit-on-transition — every mutating verb
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "verb_args,psql_stdout,task_id,old,new",
    [
        (("start", "Ship the widget"), "cto\n7|Ship the widget", "7", "", "wip"),
        (("queue", "Later thing"), "cto\n8|Later thing", "8", "", "queue"),
        (("done", "7"), "cto\n7|wip|f|Ship the widget", "7", "wip", "done"),
        (("done", "7"), "cto\n7|wip|t|Ship the widget", "7", "blocked", "done"),
        (("block", "7", "waiting on CRO"), "cto\n7|wip|f|Ship", "7", "wip", "blocked"),
        (("block", "5", "waiting"), "cto\n5|queue|f|Ship", "5", "queue", "blocked"),
        (("unblock", "7"), "cto\n7|wip|t|Ship", "7", "blocked", "wip"),
        (("unblock", "5"), "cto\n5|queue|t|Ship", "5", "blocked", "queue"),
        (("cancel", "9"), "cto\n9|queue|f|Old", "9", "queue", "cancelled"),
        (("cancel", "9"), "cto\n9|wip|t|Old", "9", "blocked", "cancelled"),
    ],
    ids=["start", "queue", "done", "done-blocked", "block-wip", "block-queue",
         "unblock-wip", "unblock-queue", "cancel-queue", "cancel-blocked"],
)
def test_emit_on_transition(env, verb_args, psql_stdout, task_id, old, new):
    r = _run(env, psql_stdout, *verb_args)
    assert r.returncode == 0, r.stderr
    xadds = _xadds(env)
    assert len(xadds) == 1, f"expected exactly one event XADD, got {xadds}"
    _assert_event(xadds[0], task_id=task_id, old=old, new=new)


def test_consumer_group_bootstrapped(env):
    r = _run(env, "cto\n7|T", "start", "T")
    assert r.returncode == 0, r.stderr
    groups = [c for c in _redis_calls(env) if "XGROUP" in c]
    assert any(c[c.index("XGROUP"):][:6] ==
               ["XGROUP", "CREATE", EVENTS_STREAM, EVENTS_GROUP, "0", "MKSTREAM"]
               for c in groups), groups


# ---------------------------------------------------------------------------
# No-emit-on-noop (negative controls)
# ---------------------------------------------------------------------------

def test_block_already_blocked_emits_nothing(env):
    # Row matched (reason refresh) but was ALREADY blocked → no transition.
    r = _run(env, "cto\n7|wip|t|Ship", "block", "7", "new reason")
    assert r.returncode == 0, r.stderr
    assert _xadds(env) == []
    assert len(_publishes(env)) == 1  # broadcast behavior unchanged on no-op


def test_unblock_already_unblocked_emits_nothing(env):
    # Spec §3.3 AC #7 idempotent no-op → matched row, blocked was false.
    r = _run(env, "cto\n7|queue|f|Ship", "unblock", "7")
    assert r.returncode == 0, r.stderr
    assert _xadds(env) == []
    assert len(_publishes(env)) == 1


def test_failed_mutation_emits_and_publishes_nothing(env):
    # No returning row (wrong id/officer/status) → error path: no event, no ping.
    r = _run(env, "cto", "done", "424242")
    assert r.returncode == 1
    assert _xadds(env) == []
    assert _publishes(env) == []


def test_list_emits_nothing(env):
    r = _run(env, "", "list")
    assert r.returncode == 0, r.stderr
    assert _redis_calls(env) == []


# ---------------------------------------------------------------------------
# Envelope law is a real gate (fail-closed negative control)
# ---------------------------------------------------------------------------

def test_enforce_gate_refuses_invalid_envelope_no_xadd(env):
    # A 300-char officer slug lands in the envelope's `from` → validate()
    # rejects (MAX_FIELD_CHARS=256) → enforce() BLOCKS → producer refuses the
    # XADD, warns loudly, and the verb still succeeds (emit is best-effort).
    r = _run(env, "cto\n7|wip|f|Ship", "block", "7", "stuck",
             officer_override="a" * 300)
    assert r.returncode == 0, r.stderr
    assert _xadds(env) == []
    assert "task_event_emit" in r.stderr
    assert "NOT queued" in r.stderr
    assert len(_publishes(env)) == 1  # broadcast is independent of the gate


# ---------------------------------------------------------------------------
# Injection controls — untrusted titles never reach event, card, or a shell
# ---------------------------------------------------------------------------

def test_title_injection_never_reaches_event_or_pubsub(env):
    canary = env["tmp"] / "canary"
    title = f'$(touch {canary}); `touch {canary}`; "quoted" | piped'
    r = _run(env, f"cto\n7|{title}", "start", title)
    assert r.returncode == 0, r.stderr
    assert not canary.exists(), "title reached a shell — command substitution ran"
    xadds = _xadds(env)
    assert len(xadds) == 1
    f = _assert_event(xadds[0], task_id="7", old="", new="wip")
    joined = "\x00".join("\x00".join(c) for c in _redis_calls(env))
    assert "$(touch" not in joined and "`touch" not in joined and "quoted" not in joined, \
        "title bytes leaked into redis argv"
    assert "title" not in f, "event must not carry a title field"


def test_newline_title_cannot_spoof_event_task_id(env):
    # Title embeds "\n99|fake" — a forged row. Event parsing anchors on the
    # FIRST returning row, so the event must carry the REAL id (7).
    r = _run(env, "cto\n7|evil\n99|fake", "start", "evil")
    assert r.returncode == 0, r.stderr
    xadds = _xadds(env)
    assert len(xadds) == 1
    _assert_event(xadds[0], task_id="7", old="", new="wip")


def test_newline_title_cannot_spoof_transition_fields(env):
    r = _run(env, "cto\n7|wip|f|evil\n99|queue|t|fake", "done", "7")
    assert r.returncode == 0, r.stderr
    xadds = _xadds(env)
    assert len(xadds) == 1
    _assert_event(xadds[0], task_id="7", old="wip", new="done")


# ---------------------------------------------------------------------------
# Pub/sub byte-parity — existing SSE consumers see identical payloads
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "verb_args,psql_stdout",
    [
        (("start", "T"), "cto\n7|T"),
        (("queue", "T"), "cto\n8|T"),
        (("done", "7"), "cto\n7|wip|f|T"),
        (("block", "7", "why"), "cto\n7|wip|f|T"),
        (("unblock", "7"), "cto\n7|wip|t|T"),
        (("cancel", "7"), "cto\n7|queue|f|T"),
    ],
    ids=["start", "queue", "done", "block", "unblock", "cancel"],
)
def test_pubsub_payload_byte_parity(env, verb_args, psql_stdout):
    r = _run(env, psql_stdout, *verb_args)
    assert r.returncode == 0, r.stderr
    pubs = _publishes(env)
    assert len(pubs) == 1, "exactly ONE thin refresh ping per mutation"
    call = pubs[0]
    i = call.index("PUBLISH")
    assert call[i + 1] == PUBSUB_CHANNEL
    assert PUBSUB_PAYLOAD_RE.fullmatch(call[i + 2]), (
        f"pub/sub payload drifted from the SSE byte contract: {call[i + 2]!r}")
    assert len(call) == i + 3, "no extra argv after the payload"
