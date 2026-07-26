#!/bin/bash
# officer-supervisor-mac.sh — Mac-native officer self-wake safety net (Gap 1).
#
# WHY THIS EXISTS (and why it is NOT cabinet/scripts/officer-supervisor.sh):
# The Docker supervisor (officer-supervisor.sh) assumes ONE tmux session named
# 'cabinet' with an officer per WINDOW (`tmux list-windows -t cabinet`). The Mac
# fleet is the opposite: each officer is its OWN detached tmux session named
# `officer-<role>`, started by its own LaunchAgent (com.cabinet.officer.<role>).
# The Docker supervisor literally cannot see Mac officers, so on Mac it is a
# no-op — that is the reconciliation this script provides.
#
# On Mac, crash-restart is already owned by each officer's LaunchAgent KeepAlive
# (start-officer-mac.sh exits non-zero when claude dies → launchd cycles it). So
# this supervisor does the ONE thing that nothing else does: it periodically
# re-sends the officer's self-wake `/loop` so a session that exited its loop (a
# /loop can be cancelled, or end after a long single turn) gets re-armed without
# a full officer restart. start-officer-mac.sh sends the FIRST /loop at boot;
# this is the recurring safety net on top of it.
#
# It targets the SEPARATE `officer-<role>` sessions (the Mac reality), only
# re-arms sessions that already exist (never starts one — that is the
# LaunchAgent's job), and is idempotent: a duplicate `/loop 5m` simply replaces
# the running loop. Per-officer prompt lives in cabinet/loop-prompts/<role>.txt;
# an officer with no prompt file is skipped (it has no self-wake by design).
#
# Run via com.cabinet.officer-supervisor-mac.plist (StartInterval 7200 = 2h).
# Reversible: `launchctl unload` the plist. No secrets touched.
#
# Usage:
#   bash cabinet/scripts/officer-supervisor-mac.sh           # one pass (launchd)
#   LOOP_INTERVAL=5m bash .../officer-supervisor-mac.sh       # override /loop cadence
#   bash cabinet/scripts/officer-supervisor-mac.sh --daemon  # internal loop (testing)

set -uo pipefail

REPO_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
LOOP_INTERVAL="${LOOP_INTERVAL:-5m}"       # the `/loop <interval>` cadence we re-arm
DAEMON_SLEEP="${DAEMON_SLEEP:-7200}"        # --daemon mode: seconds between passes (~2h)

# Shared paste-safe loop-submit (officer_loop_arm) — same helper start-officer-mac
# uses, so the submit technique lives in ONE place. Sourced best-effort: if it's
# missing we fall back to a guarded inline send below.
# shellcheck source=lib/officer-boot.sh
if [ -f "$REPO_ROOT/cabinet/scripts/lib/officer-boot.sh" ]; then
  source "$REPO_ROOT/cabinet/scripts/lib/officer-boot.sh"
fi

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] [supervisor-mac] $1"; }

# Valid officer slug (mirrors the Cabinet slug contract used everywhere else).
_valid_slug() {
  local s="$1"
  [ -n "$s" ] && [[ "$s" =~ ^[a-z0-9][a-z0-9-]*$ ]] && [ "${#s}" -le 32 ]
}

# Discover Mac officers from their tmux sessions: `officer-<role>` → <role>.
# Fully dynamic — no hardcoded officer list, so a newly-spawned lane CEO is
# picked up automatically on the next pass.
_discover_officers() {
  tmux list-sessions -F '#{session_name}' 2>/dev/null \
    | grep '^officer-' \
    | sed 's/^officer-//' \
    | grep -vE '(-inbound|-outbound)$'   # skip helper sessions, only real officers
}

# Re-arm one officer's self-wake /loop if (a) its session exists and (b) it has
# a loop-prompt file. Returns 0 if re-armed, 1 if skipped.
_rearm_officer() {
  local officer="$1"

  _valid_slug "$officer" || { log "skip '$officer' — invalid slug"; return 1; }

  local session="officer-$officer"
  # Only re-arm sessions that already exist — never start one (LaunchAgent's job).
  tmux has-session -t "$session" 2>/dev/null || { log "skip $officer — no tmux session"; return 1; }

  local loop_file="$REPO_ROOT/cabinet/loop-prompts/${officer}.txt"
  # R091: no per-officer prompt -> render the generic {{officer}} tick template.
  if [ ! -f "$loop_file" ] && [ -f "$REPO_ROOT/cabinet/loop-prompts/_template.txt" ]; then
    loop_file=$(mktemp "/tmp/loop-prompt-${officer}.XXXXXX")
    sed "s/{{officer}}/${officer}/g" "$REPO_ROOT/cabinet/loop-prompts/_template.txt" > "$loop_file"
  fi
  [ -f "$loop_file" ] || { log "skip $officer — no loop-prompt file"; return 1; }

  local prompt
  prompt=$(tr '\n' ' ' < "$loop_file" | sed 's/  */ /g; s/ *$//')
  [ -n "$prompt" ] || { log "skip $officer — empty loop-prompt"; return 1; }

  # Kill-switch guard — don't nudge officers while the Cabinet is halted.
  # Through the ONE shared helper (2026-07-25 audit): a raw GET compared to
  # "active" read error text as a clear switch, so officers were re-armed
  # through an armed stop. Anything but a verified CLEAR refuses the re-arm.
  local _ks_helper
  _ks_helper="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/hooks" 2>/dev/null && pwd)/killswitch-read.sh"
  KS_VERDICT=INDETERMINATE; KS_REASON="killswitch helper unavailable"
  if [ -r "$_ks_helper" ]; then
    # shellcheck source=/dev/null
    . "$_ks_helper" 2>/dev/null && killswitch_read
  fi
  if [ "$KS_VERDICT" != "CLEAR" ]; then
    log "emergency stop $KS_VERDICT ($KS_REASON) — not re-arming $officer"
    return 1
  fi

  # Submit the /loop with the paste-safe technique (officer_loop_arm: text, settle,
  # C-m separately, verify + nudge). A bare `send-keys "... " C-m` is swallowed as
  # a paste and never submits (observed 2026-06-24). Re-sending the SAME /loop is
  # safe: Claude Code's CronCreate is idempotent on (interval, prompt) — it re-uses
  # the existing job id rather than stacking a duplicate cron.
  local loop_cmd="/loop $LOOP_INTERVAL $prompt"
  if declare -f officer_loop_arm > /dev/null 2>&1; then
    officer_loop_arm "$session" "$loop_cmd"
  else
    # Fallback if lib/officer-boot.sh wasn't sourced: replicate the technique inline.
    tmux send-keys -t "$session" "$loop_cmd" 2>/dev/null || { log "WARN: send-keys failed for $officer"; return 1; }
    sleep 0.6
    tmux send-keys -t "$session" C-m 2>/dev/null
    sleep 3
    tmux capture-pane -t "$session" -p 2>/dev/null | grep -qE '(esc to interrupt|Scheduled .* Every)' \
      || tmux send-keys -t "$session" C-m 2>/dev/null
  fi
  log "re-armed $officer self-wake (/loop $LOOP_INTERVAL)"
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
    SET "cabinet:supervisor-mac:last-rearm:$officer" "$(date -u +%s)" EX 86400 > /dev/null 2>&1
  return 0
}

run_pass() {
  local officers count=0
  officers=$(_discover_officers)
  if [ -z "$officers" ]; then
    log "no officer-<role> tmux sessions found — nothing to re-arm"
    return 0
  fi
  while IFS= read -r officer; do
    [ -z "$officer" ] && continue
    _rearm_officer "$officer" && count=$((count + 1))
  done <<< "$officers"
  log "pass complete — re-armed $count officer(s)"
}

main() {
  if [ "${1:-}" = "--daemon" ]; then
    log "daemon mode — re-arm pass every ${DAEMON_SLEEP}s"
    while true; do
      run_pass
      sleep "$DAEMON_SLEEP"
    done
  else
    run_pass
  fi
}

main "$@"
