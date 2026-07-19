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
# The tree that carries framework/ — derived from THIS lib's location, never
# from $CABINET_ROOT (callers legitimately point CABINET_ROOT at an instance
# root that has no framework/, e.g. tests; the envelope validator must still
# import from the checkout this lib rides in).
TRIG_FRAMEWORK_ROOT="$(cd "$TRIG_LIB_DIR/../../.." && pwd)"

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
    local _nudge="🔔 Trigger received — a new officer message is queued on your stream (cabinet:triggers:${target}). Take one tool action now so the post-tool-use hook surfaces it, then process + ACK it per your loop prompt (gather-then-decide; surface to the Chair; never DM the Captain)."
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
    # A wake without a queued payload is actively misleading, and returning
    # success lets callers record work as dispatched when Redis received
    # nothing.  Propagate delivery failure so the caller can retry/rollback.
    return 1
  fi

  # Cabinet Memory embed of officer_trigger REMOVED 2026-07-12 (org-memory
  # study §4 C3): the trigger exhaust is nervous-system plumbing, not
  # knowledge — embedding every trigger_send made officer_trigger 59% of the
  # semantic store and crowded the HNSW candidate pool before ranking. The
  # durable "who was told what when" record is kept by the XADD data plane
  # (above) and the append-only trigger-archive JSONL (exhaust-archive.py);
  # grep answers audit questions without a paid Voyage embed per trigger.

  # Control plane: wake the target's live session so this trigger becomes an
  # actual LLM turn within seconds. The XADD above is the durable data plane;
  # without this, an IDLE officer never advances to read the trigger (the MCP
  # channel notification + post-tool-use hook only surface on the officer's
  # NEXT turn, which for an idle pane is up to a /loop-cadence away — root cause
  # 2026-06-25). Fully detached + best-effort: see trigger_wake_officer.
  trigger_wake_officer "$target"
}

# Echo the OLDER (numerically smaller) of two Redis stream ids (<ms>-<seq>).
# Used by #32 to clamp the ack-trim boundary to the exhaust-archive cursor so
# the trim never runs AHEAD of the daily archive. A malformed operand loses to
# the valid one (a bad cursor can only ever narrow, never widen, the trim).
_min_stream_id() {
  local a="$1" b="$2"
  [[ "$a" =~ ^[0-9]+-[0-9]+$ ]] || { echo "$b"; return; }
  [[ "$b" =~ ^[0-9]+-[0-9]+$ ]] || { echo "$a"; return; }
  local ams="${a%-*}" aseq="${a#*-}" bms="${b%-*}" bseq="${b#*-}"
  if [ "$ams" -lt "$bms" ] || { [ "$ams" -eq "$bms" ] && [ "$aseq" -le "$bseq" ]; }; then
    echo "$a"
  else
    echo "$b"
  fi
}

# Remove only the stream prefix that this consumer group has conclusively
# processed.  MAXLEN is unsafe for consumer groups: it knows nothing about the
# pending-entry list and can evict both an unacknowledged payload and a payload
# that the group has not read yet.  The safe MINID boundary is:
#   * the oldest pending id, when any delivery remains unacknowledged; or
#   * the group's last-delivered id, when the PEL is empty.
# XTRIM MINID removes entries strictly *older* than the boundary, retaining the
# boundary itself.  Probe/parse failures fail safe by skipping the trim.
# #32: the boundary is further CLAMPED to the exhaust-archive's durable cursor
# (below) so the ACK-trim never erases entries the daily archive has not yet
# read — the officer-ACK boundary races ahead of the 04:40 archive sweep.
_trigger_trim_processed_prefix() {
  local stream="$1" group="$2"
  local boundary="" groups_info="" group_count="" only_group=""

  # This trigger topology has one group per officer stream.  If an observer or
  # future consumer adds another group, a boundary safe for one group may be
  # unread/pending in the other.  Fail safe by retaining the stream rather than
  # guessing at a cross-group minimum.
  if ! groups_info=$(redis-cli --raw -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XINFO GROUPS "$stream" 2>/dev/null); then
    return 0
  fi
  group_count=$(printf '%s\n' "$groups_info" | awk '$0 == "name" { count++ } END { print count + 0 }')
  only_group=$(printf '%s\n' "$groups_info" | awk '$0 == "name" { getline; print; exit }')
  if [ "$group_count" -ne 1 ] || [ "$only_group" != "$group" ]; then
    return 0
  fi

  if ! boundary=$(redis-cli --raw -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XPENDING "$stream" "$group" - + 1 2>/dev/null \
    | awk '/^[0-9]+-[0-9]+$/ { print; exit }'); then
    boundary=""
  fi

  if [ -z "$boundary" ]; then
    if ! boundary=$(printf '%s\n' "$groups_info" \
      | awk '$0 == "last-delivered-id" { getline; print; exit }'); then
      boundary=""
    fi
  fi

  if [[ ! "$boundary" =~ ^[0-9]+-[0-9]+$ ]] || [ "$boundary" = "0-0" ]; then
    return 0
  fi

  # #32: never trim AHEAD of the daily exhaust-archive. Clamp the boundary to
  # the archive's durable per-stream cursor; if the archive has not recorded
  # this stream (state missing/unreadable, or a corrupt cursor), fail SAFE by
  # retaining the whole stream. CABINET_TRIGGER_TRIM_IGNORE_ARCHIVE=1 opts a
  # deployment out (lean streams over the durable audit trail). The state path
  # + stream name cross into python as argv — never interpolated into code.
  if [ "${CABINET_TRIGGER_TRIM_IGNORE_ARCHIVE:-0}" != "1" ]; then
    local _astate="${CABINET_EXHAUST_STATE:-$HOME/.cabinet/state/exhaust-archive.json}"
    local _acur=""
    if [ -r "$_astate" ]; then
      # `|| true` keeps a missing/failed interpreter from tripping a caller's
      # `set -e`; the try/except already makes python print "" on any error.
      _acur=$(python3.12 -c 'import json,sys
try:
    print((json.load(open(sys.argv[1])).get("last_ids") or {}).get(sys.argv[2], ""))
except Exception:
    print("")' "$_astate" "$stream" 2>/dev/null || true)
    fi
    if [ -z "$_acur" ] || [[ ! "$_acur" =~ ^[0-9]+-[0-9]+$ ]]; then
      return 0                                    # archive cursor unknown/corrupt -> retain all
    fi
    boundary=$(_min_stream_id "$boundary" "$_acur")   # older of officer-progress, archived cursor
  fi

  redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XTRIM "$stream" MINID "$boundary" > /dev/null 2>&1 || true
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

  # Keep the stream lean without deleting pending or unread payloads.
  _trigger_trim_processed_prefix "$stream" "$group"
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

# ---------------------------------------------------------------------------
# /tasks board events — durable, A6-enveloped (see cabinet/docs/tasks-board.md)
# ---------------------------------------------------------------------------
# task_event_emit <actor> <context_slug> <task_id> <old_status> <new_status>
#
# Durable data-plane sibling of my-tasks.sh's thin `cabinet:tasks:updated`
# pub/sub broadcast (which stays byte-identical for the dashboard SSE): every
# REAL task transition also lands ONE entry on the $TASK_EVENTS_STREAM Redis
# stream so consumers (watchdogs, officers) can react to task changes without
# polling Postgres. Envelope law (ledger rows A6/A12) applies because this is
# a NEW typed surface — never grandfathered:
#   * the entry carries a TYPED envelope built + judged through
#     framework/triggers/envelope.py: report_only() census BESIDE the XADD
#     (fail-open) and enforce() as the GATE before it (fail-CLOSED: a typed
#     envelope that fails validate() is refused — no XADD, loud stderr).
#   * payload rides as flat argv field pairs (never shell-interpolated):
#     task_id, old_status, new_status, actor, context_slug, ts.
#   * task TITLES / reasons / free text stay OUT of the event BY DESIGN —
#     untrusted and unnecessary; the id suffices for any consumer that needs
#     detail (join on officer_tasks).
# Closed-set input guards keep garbage off the bus even if a caller's parsing
# drifts: task_id must be numeric; statuses must come from the board's
# vocabulary ('' old_status = row creation). old_status/new_status express the
# EFFECTIVE state: the `blocked` boolean overlay surfaces as status 'blocked'.
#
# Consumer contract: at-least-once (XREADGROUP redelivery) — dedupe on the
# envelope id (envelope.ReplayWindow) or process idempotently. The exemplar
# consumer is cabinet/scripts/task-events-watch.py (group $TASK_EVENTS_GROUP);
# additional consumers create their OWN groups. Stream is not MAXLEN-capped
# (MAXLEN is unsafe under consumer groups — see _trigger_trim_processed_prefix);
# trimming is a consumer/ops concern.
#
# Fail directions: missing redis-cli/python3.12, refused envelope, or XADD
# error → WARN on stderr + return 1 (mirror trigger_send's fail-loud stance).
# Callers whose mutation already committed treat this best-effort (`|| true`).
TASK_EVENTS_STREAM="cabinet:tasks:events"
TASK_EVENTS_GROUP="task-watch"

task_event_emit() {
  local actor="${1:-}" ctx="${2:-}" task_id="${3:-}" old_status="${4:-}" new_status="${5:-}"

  if [ -z "$actor" ] || [ -z "$ctx" ]; then
    echo "task_event_emit WARN: actor + context_slug required — event NOT queued" >&2
    return 1
  fi
  if ! [[ "$task_id" =~ ^[0-9]+$ ]]; then
    echo "task_event_emit WARN: non-numeric task_id — event NOT queued" >&2
    return 1
  fi
  case "$old_status" in
    ""|queue|wip|blocked) : ;;
    *) echo "task_event_emit WARN: unknown old_status — event NOT queued" >&2; return 1 ;;
  esac
  case "$new_status" in
    queue|wip|blocked|done|cancelled) : ;;
    *) echo "task_event_emit WARN: unknown new_status — event NOT queued" >&2; return 1 ;;
  esac
  if ! command -v redis-cli >/dev/null 2>&1; then
    echo "task_event_emit WARN: redis-cli missing — task event NOT queued (task_id=$task_id)" >&2
    return 1
  fi
  if ! command -v python3.12 >/dev/null 2>&1; then
    # Typed surface, fail-closed: no validator → no send (never XADD unjudged).
    echo "task_event_emit WARN: python3.12 missing — task event NOT queued (task_id=$task_id)" >&2
    return 1
  fi

  # Build the typed envelope and judge it (report_only BESIDE + enforce GATE).
  # All values cross into python via TE_* env vars — never interpolated into
  # code. Output on success: line 1 = envelope JSON, line 2 = event ts.
  local _emit_out
  _emit_out=$(TE_ACTOR="$actor" TE_CTX="$ctx" TE_TASK_ID="$task_id" \
    TE_OLD="$old_status" TE_NEW="$new_status" \
    TE_STREAM="$TASK_EVENTS_STREAM" TE_FW_ROOT="$TRIG_FRAMEWORK_ROOT" \
    python3.12 - <<'TASK_EVENT_PY'
import json
import os
import sys
import time

root = os.environ["TE_FW_ROOT"]
if root not in sys.path:
    sys.path.insert(0, root)
from framework.triggers import envelope

# ULID: 48-bit ms timestamp + 80-bit randomness, Crockford base32 (matches
# envelope.ULID_RE — no I, L, O, U).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ms = int(time.time() * 1000) & ((1 << 48) - 1)
_n = (_ms << 80) | int.from_bytes(os.urandom(10), "big")
_ulid = "".join(_CROCKFORD[(_n >> (5 * i)) & 31] for i in range(25, -1, -1))

actor = os.environ["TE_ACTOR"]
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
env_payload = {
    "id": _ulid,
    "from": actor,          # judged by validate() — oversize/garbage is REFUSED
    "to": "task-watchers",
    "kind": "evidence",     # a transition report cites its source (taint.sources)
    "provenance": "cabinet/scripts/my-tasks.sh -> triggers.sh task_event_emit",
    "taint": {"tier": "officer", "sources": ["officer_tasks", "cabinet/scripts/my-tasks.sh"]},
    "budget": 0,
}
fields = {
    "envelope": json.dumps(env_payload, ensure_ascii=False),
    "task_id": os.environ["TE_TASK_ID"],
    "old_status": os.environ["TE_OLD"],
    "new_status": os.environ["TE_NEW"],
    "actor": actor,
    "context_slug": os.environ["TE_CTX"],
    "ts": ts,
}
# A6 census BESIDE (fail-open, never blocks); A12 enforce as the GATE.
envelope.report_only("triggers.task_event_emit", os.environ["TE_STREAM"], fields)
blocked, _verdict, reasons = envelope.enforce(fields)
if blocked:
    print("task_event_emit BLOCKED by envelope law: " + "; ".join(reasons), file=sys.stderr)
    sys.exit(3)
sys.stdout.write(fields["envelope"] + "\n" + ts + "\n")
TASK_EVENT_PY
)
  local _rc=$?
  if [ $_rc -ne 0 ] || [ -z "$_emit_out" ]; then
    echo "task_event_emit WARN: envelope build/validation failed (rc=$_rc) — task event NOT queued (task_id=$task_id)" >&2
    return 1
  fi
  local _env_json _ts
  _env_json=$(printf '%s\n' "$_emit_out" | head -n 1)
  _ts=$(printf '%s\n' "$_emit_out" | sed -n '2p')

  # Ensure the exemplar consumer group exists from the FIRST event (offset 0
  # + MKSTREAM), mirroring trigger_send's group bootstrap.
  redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XGROUP CREATE "$TASK_EVENTS_STREAM" "$TASK_EVENTS_GROUP" 0 MKSTREAM > /dev/null 2>&1

  # Fail LOUD on XADD error (same stance + shape as trigger_send).
  local _xadd_err
  _xadd_err=$(redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
    XADD "$TASK_EVENTS_STREAM" '*' \
    envelope "$_env_json" \
    task_id "$task_id" \
    old_status "$old_status" \
    new_status "$new_status" \
    actor "$actor" \
    context_slug "$ctx" \
    ts "$_ts" \
    2>&1 > /dev/null)
  if [ $? -ne 0 ] || [ -n "$_xadd_err" ]; then
    echo "task_event_emit WARN: XADD to $TASK_EVENTS_STREAM failed (${_xadd_err:-redis unreachable?}) — task event NOT queued (task_id=$task_id)" >&2
    return 1
  fi
  return 0
}
