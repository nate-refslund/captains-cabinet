"""Comms C2 — MCP PROTOCOL integration test.

The unit tests drive ``server.handle()`` directly; THIS one spawns the real
server binary as a subprocess (exactly how Claude Code launches a stdio MCP)
and drives a full JSON-RPC roundtrip over its stdio — initialize → tools/list →
tools/call — with the NULL channel bound so nothing is ever sent. This is the
end-to-end proof a handler unit test can't give: the actual process, started
from a cold ``python server.py``, speaks the actual protocol and survives a
malformed frame.
"""
import json
import os
import subprocess
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SERVER = os.path.join(_ROOT, "framework", "comms", "mcp", "server.py")


def _roundtrip(messages, timeout=30):
    """Feed JSON-RPC lines to a FRESH server subprocess (null channel bound);
    return (parsed responses, stderr)."""
    env = dict(os.environ, CABINET_CHANNEL="null")  # clean-room: every send no-ops
    proc = subprocess.Popen(
        [sys.executable, _SERVER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, cwd=_ROOT,
    )
    payload = "".join(json.dumps(m) + "\n" for m in messages)
    try:
        out, err = proc.communicate(payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    return [json.loads(ln) for ln in out.splitlines() if ln.strip()], err


def test_server_subprocess_full_roundtrip():
    resp, _err = _roundtrip([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "read_feed", "arguments": {"cursor": 0}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "send_card", "arguments": {"subject": "integration probe"}}},
    ])
    by_id = {r.get("id"): r for r in resp}
    # initialize handshake
    assert by_id[1]["result"]["serverInfo"]["name"] == "cabinet-comms"
    assert by_id[1]["result"]["protocolVersion"]
    # tools/list exposes the full surface
    names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert {"send_card", "edit_card", "react", "poll", "read_feed",
            "stream_thinking", "send_rich_card"} <= names
    # tools/call read_feed → ok, wrapped as MCP tool content (json text)
    body = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert body["status"] == "ok"
    # tools/call send_card through the NULL channel → routed, nothing sent, and
    # crucially a real JSON-RPC *result* (the process did not crash on the call)
    assert "result" in by_id[4]


def test_server_subprocess_survives_bad_frame():
    """A valid-JSON but non-object frame must not kill the process — the very
    next call still answers (the isinstance guard + run_stdio try/except)."""
    resp, _err = _roundtrip([
        [1, 2, 3],                                            # non-dict frame
        {"jsonrpc": "2.0", "id": 9, "method": "initialize"},  # must still answer
    ])
    by_id = {r.get("id"): r for r in resp}
    assert by_id[9]["result"]["serverInfo"]["name"] == "cabinet-comms"


def test_server_unknown_tool_is_error_not_crash():
    resp, _err = _roundtrip([
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "launch_missiles", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 2, "method": "initialize"},  # still alive after
    ])
    by_id = {r.get("id"): r for r in resp}
    assert by_id[1]["error"]["code"] == -32601
    assert by_id[2]["result"]["serverInfo"]["name"] == "cabinet-comms"
