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
REPO_ROOT="${CABINET_SOURCE_REPO:-${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}}"
export CABINET_SOURCE_REPO="$REPO_ROOT"
export CABINET_ROOT="$REPO_ROOT"
LOGS_DIR="$HOME/Library/Logs/cabinet"
SESSION_NAME="officer-$OFFICER"
MODEL="${CABINET_MODEL:-claude-opus-4-7}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

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

# Assemble runtime constitution + safety + preset (idempotent).
# Audit-fix 2026-05-23: capture exit status via PIPESTATUS — `tail` always exits 0.
# Dry-run skip: in CABINET_MAC_DRY_RUN=1 the fake repo has no load-preset / check-deps;
# we only need to materialise CLAUDE_CMD so tests can grep it. Side-effecting calls
# are skipped — the dry-run gate exits 0 long before tmux/redis/boot logic anyway.
if [ "${CABINET_MAC_DRY_RUN:-0}" != "1" ]; then
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
  MCP_FLAG="--mcp-config $MERGED_MCP_PATH"
elif [ "$MCP_BASE" = ".mcp.json.mac-native" ]; then
  # Mac-native base is the source of truth; pass it explicitly even without overlay
  MCP_FLAG="--mcp-config $REPO_ROOT/$MCP_BASE"
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
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SETEX "cabinet:heartbeat:$OFFICER" 900 "$(date -u +%s)" > /dev/null 2>&1 || true

# Export OFFICER_NAME for hooks (stop-hook.sh + post-tool-use.sh etc.)
export OFFICER_NAME="$OFFICER"

# Audit-fix 2026-05-23: per memory feedback_telegram_state_dir.md, each officer
# needs a distinct TELEGRAM_STATE_DIR or Telegram polling state collides across
# officers. Linux start-officer.sh sets this at line 280; mirror on Mac.
export TELEGRAM_STATE_DIR="$HOME/Library/Application Support/cabinet/telegram-state/$OFFICER"
mkdir -p "$TELEGRAM_STATE_DIR"

# ===========================================================
# Native --agent probe (CC v2.1.150+: claude --agent <name> runs the whole
# session as that officer; supersedes the legacy boot-prompt-only approach).
# ===========================================================
# Gated by:
#   * CABINET_USE_NATIVE_AGENT (default on; set to 0 to force-disable)
#   * presence of .claude/agents/<officer>.md in the repo
#   * `claude` binary on PATH
#   * `claude --help` advertising the --agent flag
AGENT_FLAG=""
if [ "${CABINET_USE_NATIVE_AGENT:-1}" = "1" ] \
  && [ -f "$REPO_ROOT/.claude/agents/$OFFICER.md" ] \
  && command -v claude >/dev/null 2>&1 \
  && claude --help 2>&1 | grep -q -- '--agent'; then
  AGENT_FLAG="--agent $OFFICER"
fi

# Build the claude invocation
CLAUDE_CMD="cd $REPO_ROOT && claude --model $MODEL $MCP_FLAG $TELEGRAM_FLAG $AGENT_FLAG --dangerously-skip-permissions --effort max"

# ===========================================================
# Dry-run gate — print plan & exit before any tmux/redis/launch side-effects.
# Used by cabinet/scripts/test-mac-dry-run.sh to verify flag assembly without a
# real Mac host. Behaviour: stdout reports the assembled command + whether the
# native --agent flag was picked up, then exits 0.
# ===========================================================
if [ "${CABINET_MAC_DRY_RUN:-0}" = "1" ]; then
  echo "$CLAUDE_CMD"
  if [ -n "$AGENT_FLAG" ]; then
    echo "native_agent=true"
  else
    echo "native_agent=false"
  fi
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
#
# Hardening 2026-05-26 (Strategy B): launchd's KeepAlive watches THIS wrapper
# script. The old logic waited on `tmux display-message #{pid}` — that's the
# tmux server process tied to the session, NOT the claude inside. If claude
# crashed to a shell prompt inside tmux, the session stayed alive and launchd
# saw nothing wrong. Officer "running" but doing nothing.
#
# Fix: wait on the tmux PANE pid (the shell that has claude as its child). When
# claude exits to the shell, OR the shell itself dies, pane_pid disappears and
# we exit non-zero so launchd restarts us. Also publish that pid to a sentinel
# file + Redis so heartbeat-watchdog can do a `kill -0` cross-check.
PANE_PID=$(tmux list-panes -t "$SESSION_NAME" -F '#{pane_pid}' 2>/dev/null | head -1)
if [ -z "$PANE_PID" ]; then
  echo "[ERROR] start-officer-mac.sh: tmux pane for $SESSION_NAME has no pane_pid — session likely died during boot" >&2
  exit 1
fi

# Sentinel file: persists across the wrapper lifetime; heartbeat-watchdog reads
# it for `kill -0` liveness probing the actual claude process tree.
SENTINEL_DIR="$HOME/Library/Caches/cabinet"
mkdir -p "$SENTINEL_DIR"
echo "$PANE_PID" > "$SENTINEL_DIR/$OFFICER.pane.pid"

# Also stash in Redis (TTL'd to twice the watchdog interval — 600s — so a dead
# watchdog can't leave a stale pid claim around forever).
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SETEX "cabinet:officer:pane-pid:$OFFICER" 600 "$PANE_PID" > /dev/null 2>&1 || true

echo "start-officer-mac.sh: $OFFICER pane_pid=$PANE_PID (sentinel: $SENTINEL_DIR/$OFFICER.pane.pid)"

# Wait on the pane shell. If claude exits to shell, the shell stays — that's
# still a busted state. So also probe the pane CONTENT for an idle prompt
# pattern: if we see a bare shell prompt for >2 consecutive checks (60s), the
# pane is broken even though the PID lives. Exit non-zero to let KeepAlive cycle.
SHELL_PROMPT_STREAK=0
while kill -0 "$PANE_PID" 2>/dev/null; do
  sleep 30
  # Re-refresh Redis pane-pid TTL so the watchdog always has a live anchor.
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
    SETEX "cabinet:officer:pane-pid:$OFFICER" 600 "$PANE_PID" > /dev/null 2>&1 || true
  # Detect claude-exited-to-shell. A live CC pane shows "esc to interrupt" or
  # ">" input cursor in the last few lines. A bare zsh/bash prompt with the
  # user@host marker means CC died and we're just looking at a shell.
  PANE_TAIL=$(tmux capture-pane -t "$SESSION_NAME" -p 2>/dev/null | grep -v '^[[:space:]]*$' | tail -5 || true)
  if echo "$PANE_TAIL" | grep -qE '^[^>]*[%#\$][[:space:]]*$' && \
     ! echo "$PANE_TAIL" | grep -qE '(esc to interrupt|Bypassing Permissions|^[[:space:]]*>)'; then
    SHELL_PROMPT_STREAK=$((SHELL_PROMPT_STREAK + 1))
    if [ "$SHELL_PROMPT_STREAK" -ge 2 ]; then
      echo "[ERROR] start-officer-mac.sh: $OFFICER claude exited to shell (pane_pid=$PANE_PID still alive) — exiting non-zero for KeepAlive restart" >&2
      tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
      exit 1
    fi
  else
    SHELL_PROMPT_STREAK=0
  fi
done
echo "[INFO] start-officer-mac.sh: $OFFICER pane_pid=$PANE_PID exited — letting KeepAlive cycle" >&2
exit 1   # pane died — let KeepAlive restart us
