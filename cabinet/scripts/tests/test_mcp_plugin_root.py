#!/usr/bin/env python3
"""Marketplace-install regression: the root .mcp.json is the PLUGIN's MCP
manifest (``.claude-plugin/plugin.json`` declares ``"mcpServers": "./.mcp.json"``),
so every local-command server whose args point at a repo-relative file MUST
resolve that path against ``${CLAUDE_PLUGIN_ROOT}`` (the plugin's install
directory), NEVER ``${CLAUDE_PROJECT_DIR}`` (the USER's open project — which
under a marketplace/plugin install is some unrelated repo where the cabinet's
``cabinet/…`` / ``framework/…`` files do not exist).

House precedent: ledger row AUD-6 — "plugin ships hooks/rules payload …
hooks/hooks.json with ${CLAUDE_PLUGIN_ROOT} paths". This test extends the same
contract to the two local-command MCP servers (redis-trigger-channel, the bun
TypeScript channel; cabinet-comms, the python3.12 comms server).

Runs under ``python -m pytest cabinet/scripts/tests -q`` (cabinet-ci.yml).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MCP_JSON = REPO / ".mcp.json"
PLUGIN_JSON = REPO / ".claude-plugin" / "plugin.json"

# A local-command server runs a bundled interpreter over a path inside the pack.
# (http/npx servers carry no pack-relative path and are out of scope.)
_LOCAL_COMMANDS = {"bun", "python3", "python3.12", "python", "node", "deno"}


def _servers() -> dict:
    return json.loads(MCP_JSON.read_text(encoding="utf-8"))["mcpServers"]


def _path_args(server: dict) -> list[str]:
    """Args that reference a CLAUDE_* base directory (i.e. a pack-relative path).
    Ignores plain env vars like ${OFFICER_NAME} / ${REDIS_URL} that legitimately
    live in the ``env`` block, not ``args``."""
    return [a for a in server.get("args", []) if "${CLAUDE_" in a]


def test_plugin_manifest_declares_this_mcp_json() -> None:
    """The contract premise: plugin.json points its mcpServers at ./.mcp.json,
    so .mcp.json is consumed in PLUGIN context (where CLAUDE_PLUGIN_ROOT is set),
    not project context. If this pin ever changes, the plugin-root rule below
    must be re-derived rather than silently kept."""
    manifest = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    assert manifest.get("mcpServers") == "./.mcp.json", (
        "plugin.json no longer declares mcpServers: './.mcp.json' — re-derive the "
        f"plugin-root path contract; got {manifest.get('mcpServers')!r}"
    )


def test_no_project_dir_in_mcp_json() -> None:
    """${CLAUDE_PROJECT_DIR} must not appear anywhere in the plugin's .mcp.json:
    under a marketplace install it resolves to the USER's project, so any
    cabinet/framework path built on it fails to resolve (the server never
    starts). This is the exact bug this file regresses against."""
    raw = MCP_JSON.read_text(encoding="utf-8")
    assert "${CLAUDE_PROJECT_DIR}" not in raw, (
        "${CLAUDE_PROJECT_DIR} found in .mcp.json — a marketplace-installed plugin "
        "resolves bundled paths against ${CLAUDE_PLUGIN_ROOT}, not the user's "
        "project dir. Swap it to ${CLAUDE_PLUGIN_ROOT}."
    )


def test_local_command_servers_use_plugin_root() -> None:
    """Every local-command server's pack-relative path arg uses
    ${CLAUDE_PLUGIN_ROOT}, and the target file actually exists under the pack
    root (so a real marketplace install resolves it)."""
    offenders: list[str] = []
    checked = 0
    for name, server in _servers().items():
        if server.get("type") == "http":
            continue
        if server.get("command") not in _LOCAL_COMMANDS:
            continue
        for arg in _path_args(server):
            checked += 1
            if "${CLAUDE_PLUGIN_ROOT}" not in arg:
                offenders.append(f"{name}: {arg!r} does not use ${{CLAUDE_PLUGIN_ROOT}}")
                continue
            rel = arg.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1]
            if not (REPO / rel).exists():
                offenders.append(f"{name}: bundled path does not exist under pack root: {rel}")
    assert not offenders, "plugin-root MCP path violations:\n  " + "\n  ".join(offenders)
    assert checked >= 2, f"expected >=2 local-command path args to check, saw {checked}"


def test_known_local_command_servers_pinned() -> None:
    """Explicit pin on the two shipped local-command servers so a rename/removal
    is caught, not silently skipped by the generic walk above."""
    servers = _servers()
    for name, needle in (
        ("redis-trigger-channel", "${CLAUDE_PLUGIN_ROOT}/cabinet/channels/redis-trigger-channel/index.ts"),
        ("cabinet-comms", "${CLAUDE_PLUGIN_ROOT}/framework/comms/mcp/server.py"),
    ):
        assert name in servers, f"expected local-command MCP server '{name}' in .mcp.json"
        assert any(needle in a for a in servers[name].get("args", [])), (
            f"{name} args must reference {needle!r}; got {servers[name].get('args')!r}"
        )


if __name__ == "__main__":
    test_plugin_manifest_declares_this_mcp_json()
    test_no_project_dir_in_mcp_json()
    test_local_command_servers_use_plugin_root()
    test_known_local_command_servers_pinned()
    print("test_mcp_plugin_root: all passed")
