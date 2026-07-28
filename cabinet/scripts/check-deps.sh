#!/bin/bash
# check-deps.sh — Non-blocking tool-dependency audit at officer session start.
#
# Prints a warning for every required tool that is missing from PATH.
# Never exits non-zero — callers decide how to handle warnings.
# Wire into entrypoint.sh (Docker) and start-officer-mac.sh (Mac).
#
# To add a required tool: append a "TOOL:description" line to REQUIRED_TOOLS.

# ENFORCEMENT-CRITICAL SET — the binaries cabinet/scripts/hooks/pre-tool-use.sh
# fails CLOSED on. If one is missing or non-functional, no officer tool call
# runs at all, so this audit exists to say WHICH one before anyone goes looking.
#
# The post-tool-use hook has its OWN, DIFFERENT set (below): it drops awk and
# perl, which carry their own fallbacks there, and adds cut/head/mkdir/dirname,
# which a correct audit record needs. Both are recorded verbatim rather than
# described, because an earlier version of this comment called the post-hook set
# "the pre-hook's minus perl" and that was simply false.
#
# Both hooks are the authority; these two lines are the diagnostic.
# cabinet/tests/hook-regression/dependency-preflight.sh (arms WIRE-3, WIRE-4)
# asserts each string equals its hook's `for _dep in ...` loop verbatim, so they
# cannot drift.
ENFORCEMENT_CRITICAL="cat jq grep sed awk tr date perl"
POST_HOOK_DEPS="cat jq grep sed tr cut head date mkdir dirname"

REQUIRED_TOOLS=(
  "cat:enforcement-critical — pre/post-tool-use hooks read the payload with it"
  "grep:enforcement-critical — the matching primitive of nearly every policy gate"
  "sed:enforcement-critical — builds the normalized command/path a gate matches on"
  "awk:enforcement-critical — parses the spend caps; an empty cap reads as unlimited"
  "tr:enforcement-critical — normalizes file paths and commands before the gates"
  "date:enforcement-critical — keys the daily cost ledger; an empty date reads as \$0 spent"
  "perl:enforcement-critical — strips quotes and heredocs before the prohibited-command gate"
  "claude:Claude Code CLI — primary officer runtime"
  "tmux:session multiplexer — officer sessions run inside tmux"
  "redis-cli:Redis client — trigger delivery, heartbeat, cost counters"
  "git:version control — officers commit and push code"
  "gh:GitHub CLI — issue filing, PR management, release downloads"
  "jq:enforcement-critical — every policy gate dispatches on a jq-parsed tool name"
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
  # Name the enforcement-critical misses separately: those do not degrade the
  # cabinet, they STOP it — the hook preflight refuses every tool call until
  # they are back. Anything else here is a capability loss, not a halt.
  BLOCKING=""
  for m in "${MISSING[@]}"; do
    case " $ENFORCEMENT_CRITICAL " in
      *" $m "*) BLOCKING="${BLOCKING:+$BLOCKING }$m" ;;
    esac
  done
  if [ -n "$BLOCKING" ]; then
    echo "[check-deps] ENFORCEMENT-CRITICAL missing: $BLOCKING — cabinet/scripts/hooks/pre-tool-use.sh will refuse EVERY tool call (fail-closed) until these resolve on PATH." >&2
    echo "[check-deps] Note PATH order: officers run with \$HOME/.local/bin ahead of the system dirs, so a shimmed binary there shadows the real one." >&2
  fi
  echo "[check-deps] File a GitHub issue on nate-refslund/captains-cabinet to track the fix." >&2
else
  echo "[check-deps] All required tools present."
fi

exit 0
