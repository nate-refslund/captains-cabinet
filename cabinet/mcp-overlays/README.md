# cabinet/mcp-overlays/ — shipped per-capability MCP overlay templates

Capability-gated MCP overlays merged into an officer's `--mcp-config` by
`cabinet/scripts/start-officer-mac.sh` (jq deep-merge over the
`.mcp.json.mac-native` base; base `mcpServers` are preserved, later layers
add/override by key).

- `cua-driver.mcp.json` — computer-use driver wiring for officers with the
  `drives_computer` capability (`cabinet/officer-capabilities.conf`).

Merge precedence: a per-officer instance overlay at
`instance/agents/<officer>/mcp.json` wins when present; the template here is
the fallback. `instance/agents/` is instance payload and leaves the egg at
packaging — without this shipped home, a fresh hatch's `drives_computer`
officers would silently lose computer-use wiring (no crash, no red test).
Egg plan row R128 (`docs/plans/operative-egg-plan-2026-07-07.md`).
