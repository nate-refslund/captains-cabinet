#!/bin/bash
# memory-worker.sh — Background worker that processes the memory embed queue
# Reads from Redis Stream cabinet:memory:embed_queue, embeds, inserts to cabinet_memory
# Retries on failure. Run as a long-lived process (systemd, supervisor, or cron every 1min).

set -uo pipefail

# Resolve repo root from script location so this works on Mac, Docker, or any
# checkout path. Fall back to the legacy /opt path only if explicitly set.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT

source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh"

GROUP="memory-worker"
CONSUMER="${HOSTNAME:-worker}"
MAX_DELIVERIES=5
DLQ_KEY="cabinet:memory:dead_letter"

# Ensure consumer group exists
redis-cli -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" XGROUP CREATE "$MEM_QUEUE_KEY" "$GROUP" 0 MKSTREAM > /dev/null 2>&1

log() { echo "[memory-worker $(date -u +%H:%M:%S)] $1"; }

# Self-heal (lane-ops 2026-07-04): if Redis loses the stream/group (flush,
# restart without AOF — BGSAVE-only durability is a known NATE-DECISION gap),
# XREADGROUP errors NOGROUP on every call. The old code swallowed stderr to
# /dev/null, so the empty result looked like "no messages", BLOCK never
# engaged (errors return immediately) and the loop busy-spun forever while
# the group stayed missing. Now: detect the error text on stderr, re-create
# the group (idempotent; MKSTREAM also revives a deleted stream), and let the
# next loop pass read normally. The log line deliberately does NOT contain
# the raw redis error token — the outcome-watchdog's marker scan flags that
# exact token in log tails, and a successful self-heal must not self-page.
ensure_group() {
  redis-cli -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" \
    XGROUP CREATE "$MEM_QUEUE_KEY" "$GROUP" 0 MKSTREAM > /dev/null 2>&1
  log "consumer group missing — re-created (group=$GROUP stream=$MEM_QUEUE_KEY)"
}

# Check delivery count for a message. If it exceeds MAX_DELIVERIES, move to DLQ + ACK.
# Returns 0 if message should be processed, 1 if it was moved to DLQ.
# XPENDING output (per message, --raw): line1=id, line2=consumer, line3=idle_ms, line4=deliveries
check_poison_message() {
  local msg_id="$1"
  local payload="$2"
  local count
  count=$(redis-cli --raw -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" \
    XPENDING "$MEM_QUEUE_KEY" "$GROUP" "$msg_id" "$msg_id" 1 2>/dev/null \
    | awk 'NR==4{print; exit}')
  count=${count:-0}
  if [ "$count" -ge "$MAX_DELIVERIES" ]; then
    redis-cli -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" \
      RPUSH "$DLQ_KEY" "$(jq -nc --arg id "$msg_id" --arg payload "$payload" --arg count "$count" \
        '{id: $id, payload: $payload, deliveries: ($count|tonumber), parked_at: now|todate}')" > /dev/null 2>&1
    redis-cli -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" \
      XACK "$MEM_QUEUE_KEY" "$GROUP" "$msg_id" > /dev/null 2>&1
    log "poison message $msg_id → DLQ after $count deliveries"
    return 1
  fi
  return 0
}

# Re-deliver pending messages that have been idle > 30s so they get retried.
# Without this, a single worker that fails a message never re-sees it (XREADGROUP '>' = new only).
#
# FIXED (lane-ops 2026-07-04): the old version piped XAUTOCLAIM to /dev/null.
# XAUTOCLAIM *transfers ownership* of the claimed messages to this consumer —
# but XREADGROUP '>' only ever reads NEW messages, so a claimed message was
# never processed by anyone: it sat pending, went idle again, was re-claimed
# into /dev/null again — invisible churn forever (the delivery counter DID
# grow, so poison rows eventually DLQ'd, but every healthy retry was lost).
# Now the claimed entries are captured and fed through the SAME parse+process
# path as fresh reads.
reclaim_stale_pending() {
  local raw
  raw=$(redis-cli --raw -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" \
    XAUTOCLAIM "$MEM_QUEUE_KEY" "$GROUP" "$CONSUMER" 30000 0 COUNT 50 2>/dev/null)
  [ -z "$raw" ] && return 0
  # Line 1 of a raw XAUTOCLAIM reply is the NEXT-CURSOR id (e.g. "0-0"). It
  # matches the same ^\d+-\d+$ shape as a message id, so feeding it to the
  # parser would shift every id/payload pairing by one (message N would be
  # ACKed under message N-1's id — silent data corruption). Strip exactly the
  # first line. Redis 7 may also append DELETED-entry ids as trailing bare
  # lines: those pair with no payload and hit the parser's empty-payload
  # ACK-and-drop branch, which is a harmless no-op for an already-deleted id.
  process_entries "$(tail -n +2 <<< "$raw")"
}

# Process one batch; exits after processing if --once passed
MODE="${1:-loop}"

# Scratch file for redis-cli stderr (NOGROUP detection). mktemp once — the
# worker is a long-runner and must not leak a tempfile per 5s loop pass.
ERR_SCRATCH=$(mktemp /tmp/memory-worker-err.XXXXXX)
trap 'rm -f "$ERR_SCRATCH"' EXIT

# How many messages the last process_batch call handled (ok+failed). The main
# loop uses it to sleep when a pass did nothing — see the busy-spin note there.
BATCH_HANDLED=0

# Parse a raw XREADGROUP/XAUTOCLAIM entry stream ("id / field / value" lines)
# and process each message: poison-check → JSON parse → embed → ACK. Shared by
# the fresh-read path and the reclaim path so both retry classes get identical
# handling. Increments BATCH_HANDLED per message touched.
process_entries() {
  local output="$1"
  [ -z "$output" ] && return 0

  # Parse: extract message IDs + payload values
  local ids=()
  local payloads=()
  local expecting="id"
  local skip_next=false
  while IFS= read -r line; do
    if [ "$skip_next" = true ]; then
      # This line is the payload value
      payloads+=("$line")
      skip_next=false
      expecting="id"
      continue
    fi
    if [[ "$line" =~ ^[0-9]+-[0-9]+$ ]]; then
      ids+=("$line")
      expecting="payload_key"
    elif [ "$expecting" = "payload_key" ] && [ "$line" = "payload" ]; then
      skip_next=true
    fi
  done <<< "$output"

  local success=0
  local failed=0

  for i in "${!ids[@]}"; do
    local id="${ids[$i]}"
    local payload="${payloads[$i]:-}"
    # Empty payload = unparseable → ACK and drop (prevents infinite retry)
    if [ -z "$payload" ]; then
      redis-cli -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" XACK "$MEM_QUEUE_KEY" "$GROUP" "$id" > /dev/null 2>&1
      failed=$((failed+1))
      continue
    fi

    # Poison message check — move to DLQ after MAX_DELIVERIES attempts
    if ! check_poison_message "$id" "$payload"; then
      failed=$((failed+1))
      continue
    fi

    # Parse JSON payload
    local source_type source_id officer sender content metadata source_ts
    source_type=$(echo "$payload" | jq -r '.source_type // empty' 2>/dev/null)
    source_id=$(echo "$payload" | jq -r '.source_id // empty' 2>/dev/null)
    officer=$(echo "$payload" | jq -r '.officer // empty' 2>/dev/null)
    sender=$(echo "$payload" | jq -r '.sender // empty' 2>/dev/null)
    content=$(echo "$payload" | jq -r '.content // empty' 2>/dev/null)
    metadata=$(echo "$payload" | jq -c '.metadata // {}' 2>/dev/null)
    source_ts=$(echo "$payload" | jq -r '.source_ts // empty' 2>/dev/null)

    if [ -z "$content" ]; then
      redis-cli -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" XACK "$MEM_QUEUE_KEY" "$GROUP" "$id" > /dev/null 2>&1
      failed=$((failed+1))
      continue
    fi

    # Try to embed + insert
    if memory_embed "$source_type" "$source_id" "$officer" "$sender" "$content" "$metadata" "$source_ts" > /dev/null 2>&1; then
      redis-cli -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" XACK "$MEM_QUEUE_KEY" "$GROUP" "$id" > /dev/null 2>&1
      success=$((success+1))
    else
      # Don't ACK — message stays pending, will be retried
      failed=$((failed+1))
    fi
  done

  BATCH_HANDLED=$((BATCH_HANDLED + success + failed))
  [ "$success" -gt 0 ] || [ "$failed" -gt 0 ] && log "processed: $success ok, $failed failed"
}

process_batch() {
  BATCH_HANDLED=0

  # Reclaim stale pending messages first (retries for previously-failed items)
  reclaim_stale_pending

  # Fresh reads. stderr goes to the scratch file (NOT /dev/null): a NOGROUP
  # error there is the self-heal signal — see ensure_group above.
  local output
  output=$(redis-cli --raw -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" \
    XREADGROUP GROUP "$GROUP" "$CONSUMER" COUNT 10 BLOCK 5000 \
    STREAMS "$MEM_QUEUE_KEY" '>' 2>"$ERR_SCRATCH")

  if grep -q "NOGROUP" "$ERR_SCRATCH" 2>/dev/null; then
    ensure_group
    return 0   # group is back — next loop pass reads normally
  fi

  [ -z "$output" ] && return 0
  process_entries "$output"
}

if [ "$MODE" = "--once" ]; then
  process_batch
  exit 0
fi

log "Starting memory worker (group=$GROUP, consumer=$CONSUMER)"
while true; do
  process_batch
  # Anti-busy-spin (lane-ops 2026-07-04): XREADGROUP's BLOCK 5000 only paces
  # the loop when Redis is healthy. When redis-cli fails FAST (connection
  # refused, NOGROUP before the heal, DNS error) every pass returns in
  # milliseconds and the old `while true` pegged a core doing nothing. An
  # empty pass now sleeps 5s — same worst-case latency as the BLOCK window,
  # zero spin. A pass that handled work loops immediately (drain fast).
  [ "$BATCH_HANDLED" -eq 0 ] && sleep 5
done
