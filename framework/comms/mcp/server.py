#!/usr/bin/env python3
"""framework.comms.mcp.server — the Comms MCP server (C2).

The officer-facing, LLM-native comms surface. A thin stdlib-only JSON-RPC
transport (stdio + optional http) around ``framework.comms.tools.dispatch`` —
every tool routes through ``framework.attention.gate`` (charter class, dedup,
quiet-hours, external-comms floor, Chair-live T2) and then the bound
``ChannelAdapter`` (channel-agnostic), so an officer's ``send_card`` inherits
the ENTIRE Attention Gateway and CANNOT bypass the one door, the charter, or
the external-comms floor. Mirrors ``cabinet/mcp-server/server.py`` (the only
other stdlib stdio+http server) so its hardening carries over verbatim:
ThreadingHTTPServer, Bearer auth, ``/health``, OSError-on-disconnect catch.

FOUNDATION-FIRST: framework code, no launcher literals. The repo root is found
file-relatively (``parents[3]``) or from ``CABINET_ROOT``; the channel it binds
is instance data resolved through ``framework.comms.get_channel`` — a clean-room
box binds the null adapter and every tool degrades to a no-op.

Transport is chosen by ``COMMS_MCP_TRANSPORT`` (``stdio`` default). HTTP mode
is FAIL-CLOSED: without ``COMMS_MCP_TOKEN`` set, every request is 401 — unlike
the federation server's dev open-mode, because this surface reaches the
Captain's own channel and must never be open by omission.
"""
from __future__ import annotations

import hmac
import json
import os
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# --- repo-root bootstrap (no launcher literal; CABINET_ROOT or file-relative) ---
_ROOT = pathlib.Path(os.environ.get("CABINET_ROOT", "")) if os.environ.get("CABINET_ROOT") \
    else pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from framework.comms import tools  # noqa: E402  (after path bootstrap)

SERVER_NAME = "cabinet-comms"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"

TRANSPORT = os.environ.get("COMMS_MCP_TRANSPORT", "stdio").strip().lower()
HTTP_PORT = int(os.environ.get("COMMS_MCP_PORT", "7472"))


# ---------------------------------------------------------------
# Tool surface — schemas over framework.comms.tools (the dispatch core)
# ---------------------------------------------------------------

def _obj(props: dict, required: "list[str] | None" = None) -> dict:
    schema = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_ARR = {"type": "array"}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "send_card",
        "description": (
            "Present ONE situation card to the Captain. Give the STRUCTURED "
            "situation (subject, what's happening, step chain, evidence) — the "
            "gateway renders the terse card, folds repeats into the SAME standing "
            "card (edits in place, never a duplicate), honors quiet hours, and "
            "routes an exceptional one to Chair T2. This is the one door; there is "
            "no other outbound path to the Captain."
        ),
        "inputSchema": _obj({
            "subject": _STR, "situation": _STR, "kind": _STR, "lane": _STR,
            "evidence": _ARR, "urgency": {"type": "string", "enum": ["ping-now", "batch-into-next-briefing", "FYI-digest"]},
            "steps": _ARR, "deadline_iso": _STR, "pid_marker": _STR,
            "injection_suspect": _BOOL, "chair_review": _BOOL,
        }, required=["subject"]),
    },
    {
        "name": "edit_card",
        "description": "Update a standing card in place (flip a step's state) — same one-message guarantee as send_card.",
        "inputSchema": _obj({
            "situation_key": _STR, "subject": _STR, "situation": _STR,
            "steps": _ARR, "state": _STR, "evidence": _ARR,
        }, required=["situation_key"]),
    },
    {
        "name": "react",
        "description": "Set ONE contextual emoji reaction on a message (the LLM layer, supersedes the poller's instant receipt-react). Empty emoji clears it.",
        "inputSchema": _obj({"message_id": _INT, "emoji": _STR}, required=["message_id", "emoji"]),
    },
    {
        "name": "poll",
        "description": "Ask the Captain an AskUserQuestion-style select (native poll) — question + options, optionally multi-select.",
        "inputSchema": _obj({
            "question": _STR, "options": _ARR, "multi": _BOOL, "silent": _BOOL,
        }, required=["question", "options"]),
    },
    {
        "name": "set_status",
        "description": "Show an ephemeral status while composing ('typing' or 'thinking'). Non-persistent; a courtesy signal, not a message.",
        "inputSchema": _obj({"kind": {"type": "string", "enum": ["typing", "thinking"]}}),
    },
    {
        "name": "pin",
        "description": "Pin a message in the Captain's chat (e.g. the active standing card for a high-stakes situation).",
        "inputSchema": _obj({"message_id": _INT}, required=["message_id"]),
    },
    {
        "name": "unpin",
        "description": "Unpin a message (or the most recent pin if no id given).",
        "inputSchema": _obj({"message_id": _INT}),
    },
    {
        "name": "open_thread",
        "description": "Open a per-lane thread/topic in the Captain's DM so a lane's cards group together. Returns thread_id.",
        "inputSchema": _obj({"lane": _STR}, required=["lane"]),
    },
    {
        "name": "answer_tap",
        "description": "Acknowledge a button tap (stops the client spinner), optionally with a short toast.",
        "inputSchema": _obj({"tap_id": _STR, "toast": _STR}, required=["tap_id"]),
    },
    {
        "name": "read_feed",
        "description": (
            "The never-re-read cursor read of the outbound/inbound feed. Pass the "
            "cursor you last held; get back only rows since then plus a new cursor. "
            "This is how an officer sees what the Captain has ALREADY been shown so "
            "it never re-surfaces a handled situation or re-reads the same messages."
        ),
        "inputSchema": _obj({"cursor": _INT, "max_n": _INT}),
    },
]


def get_tool(name: str) -> "dict | None":
    for t in TOOLS:
        if t["name"] == name:
            return t
    return None


# ---------------------------------------------------------------
# JSON-RPC dispatch (shared by both transports)
# ---------------------------------------------------------------

def make_tool_result(payload: Any) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True, default=str)}]}


def handle(req: dict) -> "dict | None":
    method = req.get("method", "")
    rid = req.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in TOOLS
        ]}}

    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if get_tool(name) is None:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"Tool not found: {name}"}}
        # tools.dispatch is fail-soft: it catches its own exceptions and returns
        # an error dict, so the loop never dies on a bad tool call.
        payload = tools.dispatch(name, args)
        return {"jsonrpc": "2.0", "id": rid, "result": make_tool_result(payload)}

    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


# ---------------------------------------------------------------
# Stdio transport
# ---------------------------------------------------------------

def run_stdio() -> None:
    """Read JSON-RPC from stdin, write responses to stdout, one message per line."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"}}) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(req)
        if resp is None:
            continue
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


# ---------------------------------------------------------------
# HTTP transport (stdlib only) — FAIL-CLOSED (no open-mode)
# ---------------------------------------------------------------

def verify_bearer(auth_header: "str | None") -> bool:
    """True iff the Bearer token matches COMMS_MCP_TOKEN (constant-time).

    FAIL-CLOSED: if COMMS_MCP_TOKEN is unset, EVERY request is refused. Unlike
    the federation server's dev open-mode, this surface reaches the Captain's
    channel, so an unconfigured http listener must be closed, never open.
    """
    want = os.environ.get("COMMS_MCP_TOKEN", "").strip()
    if not want:
        sys.stderr.write("[cabinet-comms] http refused: COMMS_MCP_TOKEN unset (fail-closed)\n")
        return False
    if not auth_header or not auth_header.startswith("Bearer "):
        return False
    return hmac.compare_digest(auth_header[7:], want)


class CommsMCPHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[cabinet-comms-http] {fmt % args}\n")

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._send_json(404, {"error": "not_found", "path": self.path})
            return
        if not verify_bearer(self.headers.get("Authorization")):
            self._send_json(401, {"error": "unauthorized",
                                  "message": "Missing or invalid Authorization: Bearer <token>"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length).decode())
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"}})
            return
        except OSError as exc:  # client disconnected mid-body
            sys.stderr.write(f"[cabinet-comms-http] client disconnected: {exc}\n")
            return
        try:
            resp = handle(req)
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"jsonrpc": "2.0", "id": req.get("id"),
                "error": {"code": -32603, "message": str(exc)}})
            return
        self._send_json(200, resp if resp is not None else {})

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "transport": "http",
                                  "server": {"name": SERVER_NAME, "version": SERVER_VERSION}})
        else:
            self._send_json(404, {"error": "not_found"})


def run_http(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), CommsMCPHandler)
    sys.stderr.write(f"[cabinet-comms] HTTP listening on 127.0.0.1:{port} (POST /mcp, GET /health)\n")
    server.serve_forever()


def main() -> None:
    if TRANSPORT == "http":
        threading.Thread(target=run_http, args=(HTTP_PORT,), daemon=True).start()
        sys.stderr.write(f"[cabinet-comms] Transport: http+stdio (port={HTTP_PORT})\n")
    else:
        if TRANSPORT not in ("stdio", ""):
            sys.stderr.write(f"[cabinet-comms] WARNING: unknown COMMS_MCP_TRANSPORT={TRANSPORT!r}, using stdio\n")
        sys.stderr.write("[cabinet-comms] Transport: stdio\n")
    run_stdio()


if __name__ == "__main__":
    main()
