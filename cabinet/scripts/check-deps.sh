#!/bin/bash
# check-deps.sh — Non-blocking tool-dependency audit at officer session start.
#
# Prints a warning for every required tool that is missing from PATH.
# Never exits non-zero — callers decide how to handle warnings.
# Wire into entrypoint.sh (Docker) and start-officer-mac.sh (Mac).
#
# To add a required tool: append a "TOOL:description" line to REQUIRED_TOOLS.

REQUIRED_TOOLS=(
  "claude:Claude Code CLI — primary officer runtime"
  "tmux:session multiplexer — officer sessions run inside tmux"
  "redis-cli:Redis client — trigger delivery, heartbeat, cost counters"
  "git:version control — officers commit and push code"
  "gh:GitHub CLI — issue filing, PR management, release downloads"
  "jq:JSON processor — MCP config merging, capability resolution"
  "curl:HTTP client — research APIs, Telegram, external calls"
  "python3:Python runtime — psycopg2 embeds, research scripts"
  "node:Node.js runtime — MCP server execution"
  "bun:Bun runtime — Channels plugin, Telegram bot"
  "npx:npm package runner — Playwright installs"
)

MISSING=()

for entry in "${REQUIRED_TOOLS[@]}"; do
  tool="${entry%%:*}"
  desc="${entry#*:}"
  if ! command -v "$tool" > /dev/null 2>&1; then
    MISSING+=("$tool")
    echo "[check-deps] MISSING: $tool — $desc" >&2
  fi
done

if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "[check-deps] ${#MISSING[@]} tool(s) missing: ${MISSING[*]}" >&2
  echo "[check-deps] File a GitHub issue on nate-refslund/captains-cabinet to track the fix." >&2
else
  echo "[check-deps] All required tools present."
fi

exit 0
