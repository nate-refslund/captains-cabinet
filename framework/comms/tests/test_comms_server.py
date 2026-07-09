"""Comms C2 — the MCP server transport (spec §4). JSON-RPC dispatch parity with
the federation server: initialize / tools/list / tools/call, unknown-method and
unknown-tool errors, and FAIL-CLOSED http Bearer auth (no open-mode, because
this surface reaches the Captain's channel)."""
import json

import pytest

from framework.comms.mcp import server


def test_initialize_returns_server_info():
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp["result"]["serverInfo"]["name"] == "cabinet-comms"
    assert resp["result"]["protocolVersion"] == server.PROTOCOL_VERSION


def test_initialized_notification_is_silent():
    assert server.handle({"method": "notifications/initialized"}) is None


def test_tools_list_exposes_the_full_surface():
    resp = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"send_card", "edit_card", "react", "poll", "set_status",
                     "pin", "unpin", "open_thread", "answer_tap", "read_feed",
                     "stream_thinking", "send_rich_card"}
    # send_card advertises subject as required
    sc = next(t for t in resp["result"]["tools"] if t["name"] == "send_card")
    assert sc["inputSchema"]["required"] == ["subject"]


def test_tools_call_routes_to_dispatch(monkeypatch):
    seen = {}
    monkeypatch.setattr(server.tools, "dispatch",
                        lambda name, args: seen.update(name=name, args=args) or {"status": "sent"})
    resp = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "react", "arguments": {"message_id": 5, "emoji": "👍"}}})
    assert seen["name"] == "react" and seen["args"]["message_id"] == 5
    # result is wrapped as MCP tool content (json text)
    body = json.loads(resp["result"]["content"][0]["text"])
    assert body["status"] == "sent"


def test_tools_call_unknown_tool_is_jsonrpc_error():
    resp = server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                          "params": {"name": "launch_missiles", "arguments": {}}})
    assert resp["error"]["code"] == -32601 and "Tool not found" in resp["error"]["message"]


def test_unknown_method_is_jsonrpc_error():
    resp = server.handle({"jsonrpc": "2.0", "id": 5, "method": "resources/list"})
    assert resp["error"]["code"] == -32601


def test_tools_call_never_raises_even_if_dispatch_returns_error(monkeypatch):
    # dispatch is fail-soft; the server must forward its error dict as a normal result
    monkeypatch.setattr(server.tools, "dispatch", lambda name, args: {"status": "error", "error": "boom"})
    resp = server.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                          "params": {"name": "send_card", "arguments": {"subject": "x"}}})
    assert "result" in resp  # not a transport error — the tool's own error rides inside
    assert json.loads(resp["result"]["content"][0]["text"])["status"] == "error"


def test_http_auth_fails_closed_without_token(monkeypatch):
    monkeypatch.delenv("COMMS_MCP_TOKEN", raising=False)
    assert server.verify_bearer("Bearer anything") is False
    assert server.verify_bearer(None) is False


def test_http_auth_constant_time_match(monkeypatch):
    monkeypatch.setenv("COMMS_MCP_TOKEN", "s3cret")
    assert server.verify_bearer("Bearer s3cret") is True
    assert server.verify_bearer("Bearer wrong") is False
    assert server.verify_bearer("s3cret") is False  # missing scheme
