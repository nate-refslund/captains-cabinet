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
# Fleet default: Opus 4.8 1M (Fable 5 is access-gated on this account, 2026-06-23; Captain-set).
# Override per-officer via CABINET_MODEL=... (e.g. claude-sonnet-4-6 to downgrade, or
# claude-fable-5[1m] once Fable access returns).
MODEL="${CABINET_MODEL:-claude-opus-4-8[1m]}"
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

# Build the MCP overlay stack (highest precedence last):
#   base                                .mcp.json.mac-native (curated core)
#   + instance/config/extra-mcps.json   captain-declared extras (ALL officers;
#                                       rendered by install-extensions.sh)
#   + per-officer cua overlay           instance/agents/<o>/mcp.json when the
#                                       deployment provides one, else the shipped
#                                       template cabinet/mcp-overlays/cua-driver.mcp.json
# Deep-merge preserves base mcpServers; later layers add/override by key.
# R128 (egg plan 2026-07-07): instance/agents/ is instance payload and leaves
# the egg at packaging — cabinet/mcp-overlays/ is the capability's shipped
# template home, so a fresh hatch's drives_computer officers keep computer-use
# wiring instead of silently losing it. Instance overlay wins when present.
EXTRA_MCPS="instance/config/extra-mcps.json"
PER_OFFICER_MCP="instance/agents/$OFFICER/mcp.json"
CUA_TEMPLATE_MCP="cabinet/mcp-overlays/cua-driver.mcp.json"

MCP_LAYERS=("$MCP_BASE")
[ -f "$EXTRA_MCPS" ] && MCP_LAYERS+=("$EXTRA_MCPS")
if [ "$HAS_CUA_DRIVER" = "true" ]; then
  if [ -f "$PER_OFFICER_MCP" ]; then
    MCP_LAYERS+=("$PER_OFFICER_MCP")
  elif [ -f "$CUA_TEMPLATE_MCP" ]; then
    MCP_LAYERS+=("$CUA_TEMPLATE_MCP")
  fi
fi

if [ "${#MCP_LAYERS[@]}" -gt 1 ]; then
  # jq reduce: fold each overlay's mcpServers into the accumulator.
  # Final pass strips pseudo-server keys starting with "_" (comment/doc
  # entries like "_comment" in overlay files) — Claude Code would try to
  # boot them as real MCP servers otherwise.
  ( umask 077
    jq -s 'reduce .[1:][] as $o (.[0];
             . * $o | .mcpServers = (.mcpServers + ($o.mcpServers // {})))
           | .mcpServers |= with_entries(select(.key|startswith("_")|not))' \
       "${MCP_LAYERS[@]}" > "$MERGED_MCP_PATH"
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
#
# CANONICAL env var: TELEGRAM_<OFFICER_UPPER>_TOKEN (e.g. TELEGRAM_COS_TOKEN).
# Fallbacks, tried in order, first non-empty wins:
#   1. TELEGRAM_<OFFICER_UPPER>_TOKEN       canonical
#   2. TELEGRAM_BOT_TOKEN_<OFFICER_UPPER>   legacy generator/docs name
#   3. TELEGRAM_BOT_TOKEN                   bare name — safe to inherit here
#      because this whole branch is gated on the telegram_bot capability
# Hyphenated slugs (e.g. polads-ceo) map '-' -> '_' for the var name.
TELEGRAM_FLAG=""
if [ "$HAS_TELEGRAM" = "true" ]; then
  OFFICER_UPPER=$(echo "$OFFICER" | tr '[:lower:]-' '[:upper:]_')
  TOKEN_VAR="TELEGRAM_${OFFICER_UPPER}_TOKEN"
  ALT_TOKEN_VAR="TELEGRAM_BOT_TOKEN_${OFFICER_UPPER}"
  BOT_TOKEN="${!TOKEN_VAR:-}"
  RESOLVED_VAR="$TOKEN_VAR"
  if [ -z "$BOT_TOKEN" ]; then
    BOT_TOKEN="${!ALT_TOKEN_VAR:-}"
    RESOLVED_VAR="$ALT_TOKEN_VAR"
  fi
  if [ -z "$BOT_TOKEN" ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
    RESOLVED_VAR="TELEGRAM_BOT_TOKEN"
  fi
  if [ -n "$BOT_TOKEN" ]; then
    export TELEGRAM_BOT_TOKEN="$BOT_TOKEN"
    # Receive path: if an inbound-watchdog LaunchAgent exists for this officer, that
    # poller OWNS getUpdates — do NOT also load --channels, or two pollers on one bot
    # token fight (Telegram 409 Conflict → nothing consumes; observed 2026-06-23). The
    # officer still SENDS via framework.frontdoor.channel.send (token exported above).
    # The Channels plugin's idle-delivery is unreliable; the watchdog is the fix.
    if [ -f "$REPO_ROOT/cabinet/launchd/com.cabinet.officer.$OFFICER-inbound.plist" ]; then
      TELEGRAM_FLAG=""
      echo "start-officer-mac.sh: $OFFICER receive via inbound watchdog — not loading --channels (token resolved from \$$RESOLVED_VAR for sends)" >&2
    else
      TELEGRAM_FLAG="--channels plugin:telegram@claude-plugins-official"
      echo "start-officer-mac.sh: $OFFICER telegram token resolved from \$$RESOLVED_VAR" >&2
    fi
  else
    cat >&2 <<TOKERR
[ERROR] start-officer-mac.sh: officer '$OFFICER' has the telegram_bot capability
[ERROR]   but NO bot token candidate is set. Tried, in order:
[ERROR]     1. $TOKEN_VAR        (canonical)
[ERROR]     2. $ALT_TOKEN_VAR    (legacy generator name)
[ERROR]     3. TELEGRAM_BOT_TOKEN          (bare fallback)
[ERROR]   Set the canonical var in cabinet/.env:
[ERROR]     $TOKEN_VAR=<bot token from BotFather>
[ERROR]   Continuing WITHOUT --channels — this officer boots Telegram-dark
[ERROR]   until the token is set and the officer is restarted.
TOKERR
  fi
fi

# Export OFFICER_NAME for hooks (stop-hook.sh + post-tool-use.sh etc.)
export OFFICER_NAME="$OFFICER"

# ===========================================================
# CABINET_LANE — load-bearing lane dimension [FIX-4]
# ===========================================================
# framework/authority/lane.py resolve_lane() reads CABINET_LANE FIRST as the
# lane of the F+A cell tuple (officer, lane, action_type). The Mac officer is
# single-project-per-LaunchAgent (no --project flag), so its lane source is
# instance/config/active-project.txt (the same active-context machinery the
# Linux script's legacy mode uses). Read defensively + whitespace-strip, then
# validate against the slug allowlist (mirrors start-officer.sh FW-073 regex) so
# a malformed active-project.txt cannot inject into the exported value. Export
# ONLY when a valid slug exists — an empty CABINET_LANE would shadow PROJECT in
# resolve_lane; omitting it lets resolve_lane fall through to PROJECT then None
# (fail-safe → unmeasured cell, propose-only at the gate).
CABINET_LANE_SLUG=""
if [ -f "$REPO_ROOT/instance/config/active-project.txt" ]; then
  CABINET_LANE_SLUG=$(tr -d '[:space:]' < "$REPO_ROOT/instance/config/active-project.txt" 2>/dev/null)
fi
if [ -n "$CABINET_LANE_SLUG" ] && [[ "$CABINET_LANE_SLUG" =~ ^[a-z0-9][a-z0-9-]*$ ]] && [ "${#CABINET_LANE_SLUG}" -le 32 ]; then
  export CABINET_LANE="$CABINET_LANE_SLUG"
else
  # Scrub any inherited/stale value so a non-conforming active-project.txt or a
  # poisoned parent env can't silently shadow PROJECT/None in resolve_lane.
  unset CABINET_LANE
  CABINET_LANE_SLUG=""
fi

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
# $MODEL is single-quoted: model ids can carry a [1m] context suffix (e.g.
# claude-opus-4-8[1m]) and this command is typed into a zsh pane, which would
# glob the unquoted brackets ("zsh: no matches found"). Single quotes pass it literally.
# OFFICER_NAME/CABINET_OFFICER are pinned ON the command (not just exported in this
# script): tmux send-keys runs claude in the SESSION's env, which inherits the tmux
# SERVER's global env. When the server was first started by another officer (e.g. cos),
# a new session would otherwise launch claude as OFFICER_NAME=cos and mis-attribute every
# heartbeat / cost / log / tier2 write to cos. Forcing them here pins the real identity.
CLAUDE_CMD="cd $REPO_ROOT && OFFICER_NAME='$OFFICER' CABINET_OFFICER='$OFFICER' claude --model '$MODEL' $MCP_FLAG $TELEGRAM_FLAG $AGENT_FLAG --dangerously-skip-permissions --effort max"

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
  # [FIX-4] surface the resolved lane so test-mac-dry-run.sh can assert the
  # CABINET_LANE export contract. Printed ONLY when a slug resolved (empty →
  # no line → resolve_lane falls through, fail-safe).
  if [ -n "${CABINET_LANE:-}" ]; then
    echo "CABINET_LANE=$CABINET_LANE"
  fi
  exit 0
fi

# ===========================================================
# Heartbeat — SETEX 900s TTL per Spec 064 v1.1 CTO #3
# ===========================================================
# Below the dry-run gate ON PURPOSE: --dry-run must write nothing (no Redis
# keys, no tmux, no files) — it only prints the assembled command.
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SETEX "cabinet:heartbeat:$OFFICER" 900 "$(date -u +%s)" > /dev/null 2>&1 || true

# ===========================================================
# tmux session + claude launch
# ===========================================================
# tmux new-session -d creates detached (no terminal attached) — per CTO v1.1 #4
# LaunchAgent doesn't have a TTY, so attached tmux would fail to start.

# Kill any existing session for this officer (idempotent restart)
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Reap orphaned Telegram channel-plugin pollers. The kill-session above kills the
# pane's process tree, but the --channels telegram plugin DETACHES (reparents to
# PID 1) and survives, keeping its getUpdates long-poll alive. Telegram allows only
# ONE getUpdates poll per bot token — a second (orphaned) poller returns 409 Conflict
# and NOTHING consumes, so the officer silently stops receiving DMs (observed
# 2026-06-23 after repeated relaunches). This Cabinet is single-Telegram-voice (only
# the Chair has a bot), so any stray telegram plugin is an orphan to replace.
# (Revisit if a deployment ever runs >1 telegram-capable officer — needs per-token scoping.)
if [ "$HAS_TELEGRAM" = "true" ]; then
  pkill -f 'plugins/cache/claude-plugins-official/telegram' 2>/dev/null \
    && echo "start-officer-mac.sh: reaped orphaned telegram channel-plugin poller(s)" >&2 || true
  sleep 1   # let the token's getUpdates lock release before the new plugin claims it
fi

# Reap orphaned redis-trigger-channel processes + their stale group consumers.
# Same class of bug as the telegram reap above, on the OTHER delivery path:
# each officer runs a `bun run .../redis-trigger-channel/index.ts` MCP that
# joins the Redis consumer group `officer-<officer>` as consumer `channel` and
# injects new triggers into the live session. A Redis group hands each new
# message to exactly ONE consumer, so a stale/orphaned `channel` from a prior
# (dead) session would SPLIT the stream — silently eating triggers the live
# Chair should have woken to (root cause 2026-06-25: notify-officer cos never
# surfaced in the active Chair). The MCP child is normally killed with the
# tmux pane, but it can detach/reparent to PID 1 on crash, and a broken launch
# path that failed to expand $OFFICER_NAME leaked 15 zombies on a junk
# `cabinet:triggers:${OFFICER_NAME}` stream (observed 2026-06-25). The
# invariant we enforce here: exactly ONE live `channel` consumer per officer.
#
# 1) Kill any existing channel process for THIS officer (env OFFICER_NAME=<o>).
#    We are restarting, so any pre-existing one is stale by definition.
for _ch_pid in $(pgrep -f 'redis-trigger-channel/index.ts' 2>/dev/null); do
  _ch_off=$(ps eww -p "$_ch_pid" 2>/dev/null | tr ' ' '\n' | grep '^OFFICER_NAME=' | head -1 | cut -d= -f2-)
  # Match this officer, OR a literal unexpanded ${OFFICER_NAME} leak (junk).
  if [ "$_ch_off" = "$OFFICER" ] || [ "$_ch_off" = '${OFFICER_NAME}' ]; then
    kill -9 "$_ch_pid" 2>/dev/null \
      && echo "start-officer-mac.sh: reaped stale redis-trigger-channel pid=$_ch_pid (OFFICER_NAME='$_ch_off')" >&2 || true
  fi
done
# 2) Drop the stale `channel` group consumer so the new MCP registers clean and
#    inherits no other consumer's pending. Idempotent (no-op if absent). The
#    `worker` consumer (post-tool-use safety net) is intentionally left intact.
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  XGROUP DELCONSUMER "cabinet:triggers:$OFFICER" "officer-$OFFICER" channel > /dev/null 2>&1 || true
# 3) Best-effort cleanup of the junk stream from the unexpanded-variable leak.
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  DEL 'cabinet:triggers:${OFFICER_NAME}' > /dev/null 2>&1 || true

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
BOOT_PROMPT="You are $OFFICER. Read your role definition at .claude/agents/$OFFICER.md and your session start checklist. Read your foundation skills in memory/skills/. Read your tier 2 notes in instance/memory/tier2/$OFFICER/. Then announce yourself on the warroom: bash $REPO_ROOT/cabinet/scripts/send-to-group.sh '<b>$OFFICER online (Mac native).</b> Session started. Checking for pending work.' — then run the calendar boot self-check: bash $REPO_ROOT/cabinet/scripts/calendar-boot-selfcheck.sh (it surfaces ONE warroom line only if the calendar grant is missing for this officer context, and never blocks boot) — then check for pending triggers and overdue work immediately."
officer_boot_drive "$SESSION_NAME" "$BOOT_PROMPT"

# ===========================================================
# Durable self-wake /loop (Gap 1: Mac officers stall after one turn).
# ===========================================================
# A Mac officer runs as its own detached tmux session and only advances when it
# takes a tool action — the post-tool-use hook is what surfaces queued triggers
# (cabinet:triggers:<officer>) and carded work. With no recurring nudge an
# officer does ONE boot burst then sits idle at the prompt forever, stranding
# every trigger and carded decision behind it (observed 2026-06-24:
# polads-ceo + stephie-ceo idle with 4 pending triggers + 4 captain-attention
# cards each). The fix: queue a `/loop 5m <prompt>` after the boot prompt so the
# officer re-checks its triggers + intake + lane work on a cadence and stays
# alive. Per-role prompt in cabinet/loop-prompts/<officer>.txt (gather-then-
# decide; surface to the Chair; never DM Nate). Skipped if no prompt file exists
# (officer simply has no self-wake — no error). Idempotent: each boot is a fresh
# session, and officer_boot_drive already drained the startup prompts, so this
# `/loop` is the session's next command. The officer-supervisor-mac re-sends it
# every ~2h as a safety net if the officer ever exits its loop.
LOOP_FILE="$REPO_ROOT/cabinet/loop-prompts/${OFFICER}.txt"
if [ -f "$LOOP_FILE" ]; then
  LOOP_PROMPT=$(tr '\n' ' ' < "$LOOP_FILE" | sed 's/  */ /g; s/ *$//')
  if [ -n "$LOOP_PROMPT" ]; then
    sleep 5  # let the boot prompt settle into a running turn before queuing /loop
    # officer_loop_arm (from lib/officer-boot.sh, already sourced above) submits
    # the /loop with the paste-safe technique: text, settle, C-m separately, then
    # verify + nudge. A bare `send-keys "... " C-m` would be absorbed as a paste
    # and never submit (observed 2026-06-24).
    officer_loop_arm "$SESSION_NAME" "/loop 5m $LOOP_PROMPT"
    echo "start-officer-mac.sh: $OFFICER self-wake /loop 5m armed from $LOOP_FILE" >&2
  fi
fi

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
