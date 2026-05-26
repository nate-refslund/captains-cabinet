#!/bin/bash
# start-officer-mac.sh — Start an Officer Claude Code session on Mac native.
#
# Invoked by LaunchAgent (com.cabinet.officer.<role>.plist). Reads officer
# capabilities, builds the right Claude Code invocation flags (telegram_bot
# gate + cua-driver MCP overlay), starts a detached tmux session, and launches
# claude inside.
#
# Per Spec 059 v1.1 Checkpoint 2.7 + CTO v1.1 #4 (tmux new-session -d) + Spec
# 060 v1.1 (telegram_bot capability gate) + Spec 061 v1.2 (drives_computer
# capability gate with jq deep-merge per CTO v1.1 #1 CRITICAL).
#
# Usage (LaunchAgent calls this):
#   /bin/bash $REPO_ROOT/cabinet/scripts/start-officer-mac.sh <officer>

set -euo pipefail

OFFICER="${1:?Usage: start-officer-mac.sh <officer>}"
REPO_ROOT="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"
LOGS_DIR="$HOME/Library/Logs/cabinet"
SESSION_NAME="officer-$OFFICER"
MODEL="${CABINET_MODEL:-claude-opus-4-7}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
MAC_DRY_RUN="${CABINET_MAC_DRY_RUN:-0}"

shell_quote() {
  printf '%q' "$1"
}

mkdir -p "$LOGS_DIR"

cd "$REPO_ROOT"

# Source .env (TELEGRAM tokens, NEON_CONNECTION_STRING, etc.)
# Audit-fix 2026-05-23: drop silent 2>/dev/null — surface a WARN to stderr so
# missing/unreadable .env produces a visible diagnostic in officer.err.log.
if [ -f "cabinet/.env" ]; then
  set -a; source cabinet/.env; set +a
else
  echo "[WARN] start-officer-mac.sh: cabinet/.env not found at $REPO_ROOT/cabinet/.env — officer will boot without secrets" >&2
fi

export CABINET_ROOT="$REPO_ROOT"
export REPO_ROOT="$CABINET_ROOT"
export CABINET_LOG_DIR="${CABINET_LOG_DIR:-$REPO_ROOT/memory/logs}"
export REDIS_URL="${REDIS_URL:-redis://$REDIS_HOST:$REDIS_PORT}"
mkdir -p "$CABINET_LOG_DIR"

if [ "$MAC_DRY_RUN" != "1" ]; then
  # Assemble runtime constitution + safety + preset (idempotent).
  # Audit-fix 2026-05-23: capture exit status via PIPESTATUS — `tail` always exits 0.
  bash cabinet/scripts/load-preset.sh 2>&1 | tail -3 >&2
  LOAD_PRESET_RC="${PIPESTATUS[0]}"
  if [ "$LOAD_PRESET_RC" -ne 0 ]; then
    echo "[ERROR] start-officer-mac.sh: load-preset.sh exited $LOAD_PRESET_RC — runtime constitution may be incomplete" >&2
    # Don't abort — let officer try to boot anyway, but logged for debug
  fi

  # Dep audit — non-blocking, logs any missing tools to stderr
  bash "$REPO_ROOT/cabinet/scripts/check-deps.sh" 2>&1 | tee -a "$LOGS_DIR/officer-$OFFICER.out.log" || true
fi

# ===========================================================
# Capability resolution (Spec 060 + Spec 061 capability gates)
# ===========================================================
# Returns "true" if officer has the capability, "false" otherwise
read_capability() {
  local role="$1" cap="$2"
  if grep -E "^${role}:${cap}$" cabinet/officer-capabilities.conf > /dev/null 2>&1; then
    echo "true"
  else
    echo "false"
  fi
}

HAS_TELEGRAM=$(read_capability "$OFFICER" "telegram_bot")
HAS_CUA_DRIVER=$(read_capability "$OFFICER" "drives_computer")

# ===========================================================
# MCP config — Mac base + (if drives_computer) overlay
# ===========================================================
# Per Spec 061 v1.1 CTO #1 CRITICAL: jq DEEP-MERGE preserving framework mcpServers.
# Shallow merge would silently overwrite notion/linear/neon/library with overlay-only.
# Audit-fix 2026-05-23: base is .mcp.json.mac-native (Mac-resolved paths + localhost
# Redis), NOT .mcp.json (which has Docker DNS + /opt paths from Hetzner). Mac-side
# always uses the .mac-native base. Audit-fix: umask 077 on /tmp output (secret hygiene).
MCP_BASE=".mcp.json.mac-native"
[ ! -f "$MCP_BASE" ] && MCP_BASE=".mcp.json"   # graceful fallback if mac-native variant missing

MERGED_MCP_PATH="$HOME/Library/Caches/cabinet/merged-mcp-${OFFICER}.json"
mkdir -p "$(dirname "$MERGED_MCP_PATH")"

if [ "$HAS_CUA_DRIVER" = "true" ] && [ -f "instance/agents/$OFFICER/mcp.json" ]; then
  ( umask 077
    jq -s '.[0] as $base | .[1] as $overlay
           | $base * $overlay
           | .mcpServers = ($base.mcpServers + $overlay.mcpServers)' \
       "$MCP_BASE" "instance/agents/$OFFICER/mcp.json" \
       > "$MERGED_MCP_PATH"
  )
  MCP_FLAG="--mcp-config $(shell_quote "$MERGED_MCP_PATH")"
elif [ "$MCP_BASE" = ".mcp.json.mac-native" ]; then
  # Mac-native base is the source of truth; pass it explicitly even without overlay
  MCP_FLAG="--mcp-config $(shell_quote "$REPO_ROOT/$MCP_BASE")"
else
  MCP_FLAG=""  # Claude Code reads .mcp.json by default (Hetzner fallback)
fi

# ===========================================================
# Telegram bot token resolution
# ===========================================================
# Lead-only (per Spec 060 v1.1): only officers with telegram_bot=true get a bot token.
# Non-Lead officers run Telegram-dark (no --channels plugin:telegram).
TELEGRAM_FLAG=""
if [ "$HAS_TELEGRAM" = "true" ]; then
  OFFICER_UPPER=$(echo "$OFFICER" | tr '[:lower:]' '[:upper:]')
  TOKEN_VAR="TELEGRAM_${OFFICER_UPPER}_TOKEN"
  BOT_TOKEN="${!TOKEN_VAR:-}"
  if [ -n "$BOT_TOKEN" ]; then
    export TELEGRAM_BOT_TOKEN="$BOT_TOKEN"
    TELEGRAM_FLAG="--channels plugin:telegram@claude-plugins-official"
  else
    echo "start-officer-mac.sh: telegram_bot=true but $TOKEN_VAR not set in env" >&2
  fi
fi

# ===========================================================
# Heartbeat — SETEX 900s TTL per Spec 064 v1.1 CTO #3
# ===========================================================
if [ "$MAC_DRY_RUN" != "1" ]; then
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
    SETEX "cabinet:heartbeat:$OFFICER" 900 "$(date -u +%s)" > /dev/null 2>&1 || true
fi

# Export OFFICER_NAME for hooks (stop-hook.sh + post-tool-use.sh etc.)
export OFFICER_NAME="$OFFICER"

# Audit-fix 2026-05-23: per memory feedback_telegram_state_dir.md, each officer
# needs a distinct TELEGRAM_STATE_DIR or Telegram polling state collides across
# officers. Linux start-officer.sh sets this at line 280; mirror on Mac.
export TELEGRAM_STATE_DIR="$HOME/Library/Application Support/cabinet/telegram-state/$OFFICER"
mkdir -p "$TELEGRAM_STATE_DIR"

# Build the claude invocation. Prefer native custom agents when the installed
# Claude Code CLI exposes --agent; otherwise keep the boot-prompt path.
AGENT_FLAG=""
if [ "${CABINET_USE_NATIVE_AGENT:-1}" = "1" ] \
  && [ -f "$REPO_ROOT/.claude/agents/$OFFICER.md" ] \
  && command -v claude >/dev/null 2>&1 \
  && claude --help 2>&1 | grep -q -- '--agent'; then
  AGENT_FLAG="--agent $(shell_quote "$OFFICER")"
fi
CLAUDE_CMD="cd $(shell_quote "$REPO_ROOT") && CABINET_ROOT=$(shell_quote "$CABINET_ROOT") REPO_ROOT=$(shell_quote "$REPO_ROOT") CABINET_LOG_DIR=$(shell_quote "$CABINET_LOG_DIR") REDIS_URL=$(shell_quote "$REDIS_URL") OFFICER_NAME=$(shell_quote "$OFFICER") TELEGRAM_STATE_DIR=$(shell_quote "$TELEGRAM_STATE_DIR") claude $AGENT_FLAG --model $(shell_quote "$MODEL") $MCP_FLAG $TELEGRAM_FLAG --dangerously-skip-permissions --effort max"

if [ "$MAC_DRY_RUN" = "1" ]; then
  echo "start-officer-mac.sh dry-run:"
  echo "  officer=$OFFICER"
  echo "  native_agent=$([ -n "$AGENT_FLAG" ] && echo true || echo false)"
  echo "  command=$CLAUDE_CMD"
  exit 0
fi

# ===========================================================
# tmux session + claude launch
# ===========================================================
# tmux new-session -d creates detached (no terminal attached) — per CTO v1.1 #4
# LaunchAgent doesn't have a TTY, so attached tmux would fail to start.

# Kill any existing session for this officer (idempotent restart)
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Start fresh detached session
tmux new-session -d -s "$SESSION_NAME" -x 220 -y 50

# Send the launch command into the tmux session
tmux send-keys -t "$SESSION_NAME" "$CLAUDE_CMD" C-m

# ===========================================================
# Auto-confirm startup prompts + submit boot prompt.
# Shared logic with Docker start-officer.sh via lib/officer-boot.sh
# (officer_boot_drive) — a fix lands once for both platforms.
# ===========================================================
# shellcheck source=lib/officer-boot.sh
source "$REPO_ROOT/cabinet/scripts/lib/officer-boot.sh"
BOOT_PROMPT="You are $OFFICER. Read your role definition at .claude/agents/$OFFICER.md and your session start checklist. Read your foundation skills in memory/skills/. Read your tier 2 notes in instance/memory/tier2/$OFFICER/. Then announce yourself on the warroom: bash $REPO_ROOT/cabinet/scripts/send-to-group.sh '<b>$OFFICER online (Mac native).</b> Session started. Checking for pending work.' — then check for pending triggers and overdue work immediately."
officer_boot_drive "$SESSION_NAME" "$BOOT_PROMPT"

echo "start-officer-mac.sh: $OFFICER started in tmux session $SESSION_NAME (model=$MODEL, telegram=$HAS_TELEGRAM, cua_driver=$HAS_CUA_DRIVER)"

# Audit-fix 2026-05-23: drop infinite while-true heartbeat loop. The in-session
# claude tool-use hook (stop-hook.sh + post-tool-use.sh) already writes heartbeat
# on every officer action — that's the canonical writer. A second writer here
# would double-stamp + mask the case where the in-session writer is broken.
# LaunchAgent KeepAlive needs the wrapper to stay alive: tmux session keeps
# its process alive in the background, so wait on the tmux session ID.
TMUX_SESSION_PID=$(tmux display-message -p -t "$SESSION_NAME" "#{pid}" 2>/dev/null)
if [ -n "$TMUX_SESSION_PID" ]; then
  # Wait for the tmux session process to exit (which it shouldn't unless
  # claude inside crashes — at which point we want LaunchAgent KeepAlive to
  # restart us, so exit non-zero).
  while kill -0 "$TMUX_SESSION_PID" 2>/dev/null; do
    sleep 30
  done
  exit 1   # tmux session died — let KeepAlive restart us
fi
