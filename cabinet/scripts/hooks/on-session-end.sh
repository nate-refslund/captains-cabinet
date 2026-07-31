#!/bin/bash
# on-session-end.sh — Fires when the CC v2.1.150 session terminates (SessionEnd hook)
# Modern replacement for the legacy Stop hook (session-stop.sh) which is now
# reserved for "Claude finished responding" within a session.
#
# Receives on stdin:
#   { session_id, transcript_path, cwd, hook_event_name, reason }
# Reason matcher values: clear, resume, logout, prompt_input_exit,
#                       bypass_permissions_disabled, other
#
# Responsibilities:
#   1. Emit session_ended event
#   2. Flush the transactional outbox if anything is pending (best-effort)
#   3. Stamp Redis with session-end timestamp for the supervisor

HOOK_INPUT=$(cat)
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# Audit #12 (2026-07-07): default was docker-era `redis` (DNS-dead on the
# native Mac deployment) — session telemetry silently no-op'd in any session
# not launched by launchd. Loopback default matches the live deployment.
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"

SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)
REASON=$(echo "$HOOK_INPUT" | jq -r '.reason // "other"' 2>/dev/null)

echo "on-session-end: $OFFICER session=$SESSION_ID reason=$REASON at $TIMESTAMP" >&2

# Stamp Redis (24h TTL) so the supervisor can distinguish "ended cleanly" from "crashed"
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SET "cabinet:session:terminated:$OFFICER" "$TIMESTAMP|reason=$REASON" EX 86400 \
  > /dev/null 2>&1 || true

# Emit session_ended event
python3 "$CABINET_ROOT/framework/events/emitter.py" \
  session_ended "$OFFICER" \
  "{\"session_id\": \"$SESSION_ID\", \"reason\": \"$REASON\", \"ended_at\": \"$TIMESTAMP\"}" \
  2>/dev/null || true

# Best-effort outbox flush. The outbox relay normally runs on cron, but at
# clean session exit we get a free chance to drain anything pending so
# downstream systems see updates before the officer goes idle.
# Audit #14 (2026-07-07): the old path cabinet/scripts/outbox-relay.py never
# existed — this flush silently never ran and cron was the only drain. The
# real entrypoint is the cron wrapper (sources cabinet/.env for adapter
# tokens, cds to repo root, execs `python3 -m framework.outbox.relay`);
# default invocation dispatches pending exactly once.

# --- Bounded run, without GNU `timeout` -------------------------------------
# macOS ships NEITHER `timeout` NOR `gtimeout`, and this box is the only
# deployment there is. A bare `timeout N cmd` therefore exits 127 (command not
# found) before `cmd` is ever started. Probed on this machine:
#   command -v timeout  -> (nothing)   timeout 1 true -> exit 127
# Prefer the real thing when it exists (Docker/Linux/CI), otherwise background
# the command, poll, and kill it. Returns 124 on the deadline, like GNU timeout.
run_bounded() {  # $1 = seconds, rest = command
  local _secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then timeout "$_secs" "$@"; return $?; fi
  if command -v gtimeout >/dev/null 2>&1; then gtimeout "$_secs" "$@"; return $?; fi
  "$@" &
  local _pid=$! _i=0 _limit=$((_secs * 10))
  while [ "$_i" -lt "$_limit" ]; do
    if ! kill -0 "$_pid" 2>/dev/null; then wait "$_pid"; return $?; fi
    sleep 0.1
    _i=$((_i + 1))
  done
  # Braced + redirected: bash reports "Terminated" for an async job when it
  # reaps it, and that notice comes from the SHELL, so a redirect on the child
  # alone does not silence it.
  { kill -TERM "$_pid" 2>/dev/null
    sleep 0.2
    kill -KILL "$_pid" 2>/dev/null
    wait "$_pid"; } 2>/dev/null
  return 124
}

OUTBOX_RELAY="$CABINET_ROOT/cabinet/cron/outbox-relay.sh"
if [ -f "$OUTBOX_RELAY" ]; then
  run_bounded 10 bash "$OUTBOX_RELAY" >/dev/null 2>&1 || true
fi

exit 0
