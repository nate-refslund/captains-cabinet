#!/bin/bash
# triggers.sh — Shared trigger functions using Redis Streams
# Source this: . /opt/founders-cabinet/cabinet/scripts/lib/triggers.sh
#
# Redis Streams give us: crash recovery (pending until ACK'd),
# delivery audit trail (XINFO), automatic message IDs + timestamps.
#
# FW-074 (Pool Phase 1B): when $CABINET_ACTIVE_PROJECT is set in the
# calling shell, the stream key + consumer group derive the project
# suffix:
#   legacy:  cabinet:triggers:<officer>          group: officer-<officer>
#   pool:    cabinet:triggers:<officer>:<proj>   group: officer-<officer>-<proj>
# Sender can route cross-project by inline-overriding the env var, e.g.:
#   CABINET_ACTIVE_PROJECT=other-proj trigger_send cpo "msg"
# Legacy callsites (no CABINET_ACTIVE_PROJECT) are byte-for-byte unchanged.

# B4 Mac portability (2026-07-03): explicit REDIS_HOST wins, REDIS_URL is the
# fallback, default 127.0.0.1. The old `redis` Docker-DNS default made every
# un-enveloped sender (interactive shells, ad-hoc scripts) silently fail to
# queue on Mac — the stderr warn fired, but the trigger was lost. Docker
# deployments set REDIS_URL/REDIS_HOST in the compose env, so they are
# unaffected by the localhost default.
if [ -n "${REDIS_HOST:-}" ]; then
  TRIG_REDIS_HOST="$REDIS_HOST"
elif [ -n "${REDIS_URL:-}" ]; then
  TRIG_REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
else
  TRIG_REDIS_HOST="127.0.0.1"
fi
TRIG_REDIS_HOST="${TRIG_REDIS_HOST:-127.0.0.1}"
TRIG_REDIS_PORT="${REDIS_PORT:-6379}"
TRIG_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$TRIG_LIB_DIR/../../.." && pwd)}"

# Compute (stream, group, ids_file) for a given target officer based on the
# caller's CABINET_ACTIVE_PROJECT. Echoes "<stream>|<group>|<ids_file>" —
# callers split on '|'. Pure function, no Redis I/O. The slug regex must
# match start-officer.sh's guard so a malformed env var never lands as a
# malformed Redis key. The ids_file path is per-(officer, project) in pool
# mode so concurrent reads by the same officer across different projects
# do not stomp each other's pending-IDs (FW-074 regression: shared file
# path caused pool trigger_ack to drop the wrong IDs).
_trigger_keys() {
  local target="$1"
  local proj="${CABINET_ACTIVE_PROJECT:-}"
  # Slug guard mirrors start-officer.sh (FW-073): regex + 32-char cap. Any
  # malformed slug (length, charset, leading hyphen) falls through to the
  # legacy stream so a corrupted env var never lands as a malformed Redis
  # key or 100-char tmp path.
  if [ -n "$proj" ] && [[ "$proj" =~ ^[a-z0-9][a-z0-9-]*$ ]] && [ "${#proj}" -le 32 ]; then
    echo "cabinet:triggers:${target}:${proj}|officer-${target}-${proj}|/tmp/.trigger_ids_${target}_${proj}"
  else
    echo "cabinet:triggers:${target}|officer-${target}|/tmp/.trigger_ids_${target}"
  fi
}

# Wake a target officer's LIVE session so a queued trigger becomes an actual
# LLM turn within SECONDS — the control-plane half of trigger delivery.
#
# WHY THIS EXISTS (root cause 2026-06-25, the Captain's #1 reliability blocker):
# Putting a trigger on the Redis stream (XADD, above) is only the DATA plane.
# The redis-trigger-channel MCP consumes it and fires a `notifications/claude/
# channel` notification — but that notification does NOT wake an IDLE Claude
# Code session. It is the SAME idle-delivery flaw commit 96dff1b already proved
# for the telegram Channels plugin ("fetches one update, injects, then stalls
# until processed — which never happens while idle"). Evidence: a round-trip
# wake-test reached every officer's stream (pending=0, lag=0) yet NO officer
# acted for 6+ minutes — they only woke when their own `/loop 5m` next ticked.
# The post-tool-use safety-net hook has the same limitation: it only surfaces a
# trigger on the officer's NEXT tool action, so a truly idle pane never advances.
#
# THE FIX (proven, mechanism-tested 2026-06-25 — woke an idle officer in 5s):
# the ONE wake path that demonstrably re-invokes an idle Mac officer is
# `tmux send-keys` into its `officer-<role>` session — exactly what the inbound
# poller (96dff1b) and officer_loop_arm use. We nudge the pane to take a turn;
# the trigger CONTENT is still delivered by the hook/channel on that turn, so
# the nudge text is intentionally minimal (no content duplication).
#
# Safety / correctness:
#   * Idle-gated — only injects when the pane is NOT mid-turn ("esc to interrupt"
#     absent). A busy officer will see the trigger via the hook on its current
#     turn's tool calls anyway, so we never risk mid-turn input corruption.
#   * Session-existence guarded — `tmux has-session` must succeed. Where the
#     session is not local (Docker's single `cabinet` session, or the officer is
#     down), this no-ops cleanly; delivery falls back to the channel/hook.
#   * Killswitch-guarded — never nudge while the Cabinet is halted.
#   * Best-effort + fully detached — runs in a backgrounded subshell, all errors
#     swallowed, so a missing tmux or a dead pane can NEVER break trigger_send
#     (the XADD already succeeded — the trigger is durable regardless).
#   * Debounced — a per-(officer) Redis lock (3s TTL) coalesces a burst of
#     near-simultaneous sends into ONE wake, so we don't machine-gun Enter into
#     the pane when several triggers land at once.
#
# Usage: trigger_wake_officer <target_officer>
trigger_wake_officer() {
  local target="$1"
  [ -n "$target" ] || return 0

  # Detach EVERYTHING below: the wake is a courtesy nudge on top of a trigger
  # that is already durably queued. It must never delay or fail the caller.
  (
    # Need tmux to wake a Mac officer pane. Absent (e.g. Docker entrypoint
    # without the right target, or CI) → nothing to do.
    command -v tmux >/dev/null 2>&1 || exit 0

    local session="officer-${target}"
    tmux has-session -t "$session" 2>/dev/null || exit 0

    # Killswitch — do not nudge officers while the Cabinet is halted.
    local _ks
    _ks=$(redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
      GET cabinet:killswitch 2>/dev/null)
    [ "$_ks" = "active" ] && exit 0

    # Debounce: coalesce a burst into one wake. SET NX with a short TTL — if the
    # lock already exists a wake is already in flight/just fired, so skip. Best-
    # effort: if redis is unreachable the SET returns empty and we proceed (a
    # spurious extra Enter at an idle prompt is harmless).
    local _lock
    _lock=$(redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
      SET "cabinet:trigger-wake:${target}" "$(date -u +%s)" NX EX 3 2>/dev/null)
    [ "$_lock" = "OK" ] || exit 0

    # Idle-gate: only inject when the pane is NOT actively processing a turn.
    # "esc to interrupt" is CC's active-turn indicator (same probe the inbound
    # poller + boot driver use). If busy, the officer will surface the trigger
    # via the post-tool-use hook on its current turn — no nudge needed.
    local _tail
    _tail=$(tmux capture-pane -t "$session" -p 2>/dev/null \
      | grep -v '^[[:space:]]*$' | tail -6)
    if echo "$_tail" | grep -q 'esc to interrupt'; then
      exit 0
    fi

    # Wake. Minimal nudge — the trigger CONTENT rides the hook/channel on the
    # turn this triggers. Paste-safe submit (text, settle, C-m separately, then
    # verify + nudge a second C-m) mirrors officer_loop_arm: a fused trailing
    # C-m is swallowed as a paste and never submits (observed 2026-06-24).
    local _nudge="🔔 Trigger received — a new officer message is queued on your stream (cabinet:triggers:${target}). Take one tool action now so the post-tool-use hook surfaces it, then process + ACK it per your loop prompt (gather-then-decide; surface to the Chair; never DM Nate)."
    tmux send-keys -t "$session" "$_nudge" 2>/dev/null || exit 0
    sleep 0.6
    tmux send-keys -t "$session" C-m 2>/dev/null
    sleep 2
    if ! tmux capture-pane -t "$session" -p 2>/dev/null \
         | grep -v '^[[:space:]]*$' | tail -6 | grep -q 'esc to interrupt'; then
      tmux send-keys -t "$session" C-m 2>/dev/null
    fi
  ) >/dev/null 2>&1 &
  disown 2>/dev/null || true
}

# Send a trigger to an officer
# Usage: trigger_send <target_officer> "<message>"
trigger_send() {
  local target="$1" message="$2"
  local sender="${OFFICER_NAME:-unknown}"
  local timestamp=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

  local keys stream group _ids_file
  keys=$(_trigger_keys "$target")
  IFS='|' read -r stream group _ids_file <<< "$keys"

  # Ensure consumer group exists for the target
  redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XGROUP CREATE "$stream" "$group" 0 MKSTREAM > /dev/null 2>&1

  # Add message to stream. Fail LOUD on XADD error — silent drop of a
  # deploy-notify or Captain-relay trigger is how the validators miss a
  # production push entirely (audit Finding #1, 2026-04-21). stderr only,
  # so normal success remains silent.
  local _xadd_err
  _xadd_err=$(redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XADD "$stream" '*' \
    sender "$sender" \
    message "[$timestamp] From $sender: $message" \
    2>&1 > /dev/null)
  if [ $? -ne 0 ] || [ -n "$_xadd_err" ]; then
    echo "trigger_send WARN: XADD to $stream failed (${_xadd_err:-redis unreachable?}) — trigger NOT queued, sender=$sender" >&2
  fi

  # Cabinet Memory: queue trigger for semantic indexing (fire-and-forget).
  # FW-077: redirect bg subshell stdout+stderr to /dev/null and disown so
  # bash's job-control "Done" message cannot leak the env vars exported by
  # memory.sh's `set -a; source cabinet/.env` (NEON_CONNECTION_STRING +
  # others) into the calling officer's session JSONL. The disown drops the
  # job from the parent's job table entirely so no completion notice fires.
  # set-u-safe root (2026-07-02, CI 28619006556): a `CABINET_ROOT=x . triggers.sh`
  # source prefix unwinds after the source, so this function self-resolves.
  local mem_root="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
  if [ -f "$mem_root/cabinet/scripts/lib/memory.sh" ]; then
    (
      source "$mem_root/cabinet/scripts/lib/memory.sh" 2>/dev/null
      if declare -f memory_queue_embed > /dev/null; then
        local source_id="trg-$(date -u +%Y%m%dT%H%M%S)-${sender}-to-${target}"
        local metadata
        metadata=$(jq -nc --arg sender "$sender" --arg target "$target" \
          '{sender: $sender, target: $target}')
        memory_queue_embed "officer_trigger" "$source_id" "$sender" "$sender" \
          "[$sender → $target] $message" "$metadata" \
          "$(date -u +%Y-%m-%dT%H:%M:%SZ)" 2>/dev/null || true
      fi
    ) >/dev/null 2>&1 &
    disown 2>/dev/null || true
  fi

  # Control plane: wake the target's live session so this trigger becomes an
  # actual LLM turn within seconds. The XADD above is the durable data plane;
  # without this, an IDLE officer never advances to read the trigger (the MCP
  # channel notification + post-tool-use hook only surface on the officer's
  # NEXT turn, which for an idle pane is up to a /loop-cadence away — root cause
  # 2026-06-25). Fully detached + best-effort: see trigger_wake_officer.
  trigger_wake_officer "$target"
}

# Read NEW triggers for an officer (marks them as pending until ACK'd)
# Usage: trigger_read <officer>
# Outputs: message content lines (one per trigger)
# Sets TRIGGER_IDS variable with space-separated message IDs for ACK
trigger_read() {
  local officer="$1"

  local keys stream group ids_file
  keys=$(_trigger_keys "$officer")
  IFS='|' read -r stream group ids_file <<< "$keys"

  # Ensure consumer group exists (silence BUSYGROUP if already exists)
  redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XGROUP CREATE "$stream" "$group" 0 MKSTREAM > /dev/null 2>&1

  local output
  output=$(redis-cli --raw -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XREADGROUP GROUP "$group" worker COUNT 50 \
    STREAMS "$stream" '>' 2>/dev/null)

  if [ -z "$output" ]; then
    echo "" > "$ids_file"
    return 1
  fi

  # Write message IDs to temp file (survives subshell capture). In pool
  # mode the file path is per-(officer, project) so concurrent reads
  # across projects do not stomp each other (FW-074).
  echo "$output" | grep -E '^[0-9]+-[0-9]+$' | tr '\n' ' ' > "$ids_file"
  # Output message content
  echo "$output" | awk '/^message$/{getline; print}'
}

# Safety-net read — re-surface triggers that were delivered to the group but
# left UN-ACKed and idle past a grace window, regardless of which consumer
# (channel/worker) originally claimed them. Used by the post-tool-use hook so
# it NEVER steals fresh (id ">") triggers from the live redis-trigger-channel
# MCP consumer (that race silently starved the Chair — root cause 2026-06-25).
#
# NOTE this hook is a BACKSTOP, not the wake. Re-invoking an IDLE officer to take
# the turn on which this (and the channel) surface a trigger is done by
# trigger_wake_officer (tmux send-keys), called from trigger_send. This hook only
# runs once the officer is already taking a turn; its job is to recover triggers
# the channel stranded (pushed-but-died, or channel down), not to wake the pane.
#
# Mechanism: XAUTOCLAIM transfers ownership of entries idle >= GRACE_MS to the
# `worker` consumer and returns them. CONSUMER-SIDE ACK (AUD-12, audit #32,
# 2026-07-07): the channel MCP no longer ACKs on notification emit — delivery
# is not processing, and the old ack-on-emit lost any trigger when the session
# crashed between push and wake. Every trigger now stays PENDING until the
# officer's trigger_ack. So this safety net covers BOTH the classic
# crash/outage cases (channel pushed-but-died, channel down) AND
# channel-delivered triggers the officer has not ACKed within the grace
# window: the reclaim re-surfaces the content AND writes the ids_file the
# officer's `trigger_ack <role> "$(cat ids_file)"` pipeline consumes — which
# is exactly how channel-delivered triggers get their consumer-side ACK.
# At-least-once by construction: duplicates possible, silent loss is not.
#
# GRACE_MS default 30000 (30s): comfortably longer than the channel's 5s BLOCK
# loop, so the live channel always wins the fresh delivery. Override via
# TRIGGER_SAFETY_NET_GRACE_MS.
# Usage: trigger_read_safety_net <officer>
#   Writes reclaimed IDs to the per-(officer,project) ids_file; echoes message
#   content lines. Returns 1 (and writes empty ids_file) when nothing reclaimed.
trigger_read_safety_net() {
  local officer="$1"
  local grace_ms="${TRIGGER_SAFETY_NET_GRACE_MS:-30000}"

  local keys stream group ids_file
  keys=$(_trigger_keys "$officer")
  IFS='|' read -r stream group ids_file <<< "$keys"

  redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XGROUP CREATE "$stream" "$group" 0 MKSTREAM > /dev/null 2>&1

  # XAUTOCLAIM <key> <group> <consumer> <min-idle-ms> <start> [COUNT n]
  # Claims idle>=grace pending entries for `worker`, starting from 0.
  # --raw output is a flat list: [next-cursor, then for each entry: id, then
  # field/value pairs..., then a trailing deleted-ids array]. We extract the
  # message IDs (NNN-NNN lines) and the value following each literal `message`
  # field — same parse shape as trigger_read.
  local output
  output=$(redis-cli --raw -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XAUTOCLAIM "$stream" "$group" worker "$grace_ms" 0 COUNT 50 2>/dev/null)

  if [ -z "$output" ]; then
    echo "" > "$ids_file"
    return 1
  fi

  # First line of XAUTOCLAIM output is the next cursor (an ID or "0-0") — it is
  # NOT a reclaimed message ID. Drop it so trigger_ack does not try to ACK the
  # cursor. Remaining NNN-NNN tokens are the reclaimed entry IDs.
  local ids
  ids=$(echo "$output" | tail -n +2 | grep -E '^[0-9]+-[0-9]+$' | tr '\n' ' ')
  echo "$ids" > "$ids_file"

  # No real reclaimed IDs (only the cursor) → nothing to surface.
  if [ -z "$(echo "$ids" | tr -d ' ')" ]; then
    return 1
  fi

  echo "$output" | awk '/^message$/{getline; print}'
}

# Read PENDING (unacknowledged) triggers — for crash recovery
# Usage: trigger_read_pending <officer>
trigger_read_pending() {
  local officer="$1"

  local keys stream group ids_file
  keys=$(_trigger_keys "$officer")
  IFS='|' read -r stream group ids_file <<< "$keys"

  redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XGROUP CREATE "$stream" "$group" 0 MKSTREAM > /dev/null 2>&1

  local output
  output=$(redis-cli --raw -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XREADGROUP GROUP "$group" worker COUNT 50 \
    STREAMS "$stream" '0' 2>/dev/null)

  if [ -z "$output" ]; then
    echo "" > "$ids_file"
    return 1
  fi

  echo "$output" | grep -E '^[0-9]+-[0-9]+$' | tr '\n' ' ' > "$ids_file"
  echo "$output" | awk '/^message$/{getline; print}'
}

# Acknowledge triggers (mark as processed)
# Usage: trigger_ack <officer> "<id1> <id2> ..."
trigger_ack() {
  local officer="$1" ids="$2"
  [ -z "$ids" ] && return

  local keys stream group _ids_file
  keys=$(_trigger_keys "$officer")
  IFS='|' read -r stream group _ids_file <<< "$keys"

  for id in $ids; do
    redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
      XACK "$stream" "$group" "$id" > /dev/null 2>&1
  done

  # Trim acknowledged messages (keep stream lean)
  redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XTRIM "$stream" MAXLEN '~' 100 > /dev/null 2>&1
}

# Count pending (unacknowledged) triggers
# Usage: trigger_count <officer>
trigger_count() {
  local officer="$1"

  local keys stream group _ids_file
  keys=$(_trigger_keys "$officer")
  IFS='|' read -r stream group _ids_file <<< "$keys"

  redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XGROUP CREATE "$stream" "$group" 0 MKSTREAM > /dev/null 2>&1

  local pending
  pending=$(redis-cli --raw -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XPENDING "$stream" "$group" 2>/dev/null | head -1)

  echo "${pending:-0}"
}

# Echo the per-(officer, project) IDS file path. Useful for callers that
# need to construct the cat | trigger_ack pipeline outside the lib.
# Pool mode: /tmp/.trigger_ids_<officer>_<project>
# Legacy:    /tmp/.trigger_ids_<officer>
trigger_ids_path() {
  # Use ${1:-} so set -u callers don't trip the "unbound variable" trap
  # before our explicit guard runs.
  local officer="${1:-}"
  if [ -z "$officer" ]; then
    echo "trigger_ids_path: officer argument required" >&2
    return 1
  fi
  local keys _stream _group ids_file
  keys=$(_trigger_keys "$officer")
  IFS='|' read -r _stream _group ids_file <<< "$keys"
  echo "$ids_file"
}
