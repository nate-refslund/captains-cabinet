#!/usr/bin/env bash
# Shared Redis state capture/comparison helpers for backup.sh and restore-drill.sh.
# shellcheck shell=bash

if [ -n "${CABINET_REDIS_STATE_LIB_LOADED:-}" ]; then
  return 0
fi
CABINET_REDIS_STATE_LIB_LOADED=1

REDIS_STATE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REDIS_STATE_TOOL="$REDIS_STATE_LIB_DIR/redis_state.py"

# Legacy capture exists only so old v2 snapshots can still receive their exact,
# fail-closed restore check.  New backups never use DUMP: its byte encoding is
# not stable when sets, hashes, and streams are reconstructed from AOF.
REDIS_STATE_V2_LUA='-- cabinet-redis-state-v2; local keys=redis.call("KEYS","*"); table.sort(keys); local h={}; local expiries={}; for i,k in ipairs(keys) do local d=redis.call("DUMP",k); h[i]=redis.sha1hex(tostring(string.len(k))..":"..k..d); local ttl=redis.call("PTTL",k); if ttl >= 0 then local t=redis.call("TIME"); local now=tonumber(t[1])*1000+math.floor(tonumber(t[2])/1000); expiries[#expiries+1]=redis.sha1hex(k)..":"..string.format("%.0f",now+ttl); end; end; local out={tostring(#keys)..":"..redis.sha1hex(table.concat(h))}; for _,e in ipairs(expiries) do out[#out+1]=e; end; return out'

REDIS_STATE_V3_LUA=""
IFS= read -r -d '' REDIS_STATE_V3_LUA <<'LUA' || true
-- cabinet-redis-state-v3
local function add(parts, value)
  if value == nil or value == false then value = "<nil>" end
  value = tostring(value)
  parts[#parts + 1] = tostring(string.len(value)) .. ":" .. value
end

local function map_get(values, wanted)
  for i = 1, #values, 2 do
    if values[i] == wanted then return values[i + 1] end
  end
  return nil
end

-- Redis exposes SHA-1 natively, but the backup proof uses SHA-256 throughout.
-- Keep hashing inside the atomic Lua capture so raw keys and values never cross
-- the Redis protocol, enter shell variables, or appear in redis-state.txt.
local band, bor, bxor, bnot = bit.band, bit.bor, bit.bxor, bit.bnot
local lshift, rshift, ror = bit.lshift, bit.rshift, bit.ror
local sha256_k = {
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
}

local function add32(...)
  local total = 0
  for i = 1, select("#", ...) do total = total + select(i, ...) end
  return band(total, 0xffffffff)
end

local function hex32(value)
  if value < 0 then value = value + 4294967296 end
  return string.format("%08x", value)
end

local function sha256(message)
  local message_length = #message
  local bit_length = message_length * 8
  local padded_length = message_length + 9
  local remainder = padded_length % 64
  if remainder ~= 0 then padded_length = padded_length + (64 - remainder) end
  local high = math.floor(bit_length / 4294967296)
  local low = bit_length % 4294967296
  local length_start = padded_length - 7

  -- Read SHA-256 padding as a virtual byte string. Building a Lua table from
  -- every input byte (or expanding string.byte into arguments) overflows the
  -- Redis Lua stack for production-sized strings and streams.
  local function padded_byte(position)
    if position <= message_length then return string.byte(message, position) end
    if position == message_length + 1 then return 0x80 end
    if position < length_start then return 0 end
    local offset = position - length_start
    if offset < 4 then
      return band(rshift(high, (3 - offset) * 8), 0xff)
    end
    return band(rshift(low, (7 - offset) * 8), 0xff)
  end

  local h0, h1, h2, h3 = 0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a
  local h4, h5, h6, h7 = 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
  for chunk = 1, padded_length, 64 do
    local w = {}
    for i = 0, 15 do
      local at = chunk + i * 4
      w[i] = bor(
        lshift(padded_byte(at), 24),
        lshift(padded_byte(at + 1), 16),
        lshift(padded_byte(at + 2), 8),
        padded_byte(at + 3)
      )
    end
    for i = 16, 63 do
      local s0 = bxor(ror(w[i - 15], 7), ror(w[i - 15], 18), rshift(w[i - 15], 3))
      local s1 = bxor(ror(w[i - 2], 17), ror(w[i - 2], 19), rshift(w[i - 2], 10))
      w[i] = add32(w[i - 16], s0, w[i - 7], s1)
    end
    local a, b, c, d, e, f, g, h = h0, h1, h2, h3, h4, h5, h6, h7
    for i = 0, 63 do
      local s1 = bxor(ror(e, 6), ror(e, 11), ror(e, 25))
      local choice = bxor(band(e, f), band(bnot(e), g))
      local temp1 = add32(h, s1, choice, sha256_k[i + 1], w[i])
      local s0 = bxor(ror(a, 2), ror(a, 13), ror(a, 22))
      local majority = bxor(band(a, b), band(a, c), band(b, c))
      local temp2 = add32(s0, majority)
      h, g, f, e, d, c, b, a = g, f, e, add32(d, temp1), c, b, a, add32(temp1, temp2)
    end
    h0, h1, h2, h3 = add32(h0, a), add32(h1, b), add32(h2, c), add32(h3, d)
    h4, h5, h6, h7 = add32(h4, e), add32(h5, f), add32(h6, g), add32(h7, h)
  end
  return hex32(h0) .. hex32(h1) .. hex32(h2) .. hex32(h3)
    .. hex32(h4) .. hex32(h5) .. hex32(h6) .. hex32(h7)
end

local function logical_digest(key, kind)
  local parts = {}
  add(parts, kind)
  if kind == "string" then
    add(parts, redis.call("GET", key))
  elseif kind == "list" then
    local values = redis.call("LRANGE", key, 0, -1)
    add(parts, #values)
    for _, value in ipairs(values) do add(parts, value) end
  elseif kind == "set" then
    local values = redis.call("SMEMBERS", key)
    table.sort(values)
    add(parts, #values)
    for _, value in ipairs(values) do add(parts, value) end
  elseif kind == "zset" then
    local values = redis.call("ZRANGE", key, 0, -1, "WITHSCORES")
    add(parts, #values / 2)
    for _, value in ipairs(values) do add(parts, value) end
  elseif kind == "hash" then
    local flat = redis.call("HGETALL", key)
    local values = {}
    for i = 1, #flat, 2 do values[#values + 1] = {flat[i], flat[i + 1]} end
    table.sort(values, function(a, b) return a[1] < b[1] end)
    add(parts, #values)
    for _, pair in ipairs(values) do add(parts, pair[1]); add(parts, pair[2]) end
  elseif kind == "array" then
    -- Redis 8.8 arrays are sparse and have a durable insertion cursor. Capture
    -- logical occupied index/value pairs plus count, length, and next-insert-
    -- index; exclude slice/directory layout and density statistics because
    -- those are internal encodings that may change across replay.
    local info = redis.call("ARINFO", key)
    local count = tonumber(map_get(info, "count"))
    local length = tonumber(map_get(info, "len"))
    local next_insert = map_get(info, "next-insert-index")
    if count == nil or length == nil or next_insert == nil then
      return redis.error_reply("incomplete Redis array metadata")
    end
    add(parts, "count"); add(parts, count)
    add(parts, "len"); add(parts, length)
    add(parts, "next-insert-index"); add(parts, next_insert)
    local values = {}
    if length > 0 then values = redis.call("ARSCAN", key, 0, length - 1) end
    if #values ~= count then return redis.error_reply("incomplete Redis array capture") end
    add(parts, "values"); add(parts, #values)
    for _, pair in ipairs(values) do add(parts, pair[1]); add(parts, pair[2]) end
  elseif kind == "stream" then
    -- Included recovery state: ordered entries and field/value pairs; length,
    -- last-generated-id, max-deleted-entry-id, entries-added, and
    -- recorded-first-entry-id; each group name, last-delivered-id, entries-read;
    -- every consumer identity (including zero-pending consumers); and each PEL
    -- entry id, owner, and delivery count. Excluded: radix-tree shape and derived
    -- lag/count fields, plus consumer idle/active/seen and PEL delivery-time.
    -- Those clocks are deliberately rebased by Redis during RDB/AOF replay and
    -- are not recovery-stable; the included ownership/count state is durable.
    local info = redis.call("XINFO", "STREAM", key)
    for _, field in ipairs({"length", "last-generated-id", "max-deleted-entry-id", "entries-added", "recorded-first-entry-id"}) do
      add(parts, field)
      add(parts, map_get(info, field))
    end
    local entries = redis.call("XRANGE", key, "-", "+")
    add(parts, "entries")
    add(parts, #entries)
    for _, entry in ipairs(entries) do
      add(parts, entry[1])
      add(parts, #entry[2] / 2)
      for _, field_or_value in ipairs(entry[2]) do add(parts, field_or_value) end
    end
    local groups = redis.call("XINFO", "GROUPS", key)
    table.sort(groups, function(a, b) return map_get(a, "name") < map_get(b, "name") end)
    add(parts, "groups")
    add(parts, #groups)
    for _, group in ipairs(groups) do
      local group_name = map_get(group, "name")
      local pending_count = tonumber(map_get(group, "pending")) or 0
      add(parts, group_name)
      add(parts, map_get(group, "last-delivered-id"))
      add(parts, map_get(group, "entries-read"))

      local consumers = redis.call("XINFO", "CONSUMERS", key, group_name)
      table.sort(consumers, function(a, b) return map_get(a, "name") < map_get(b, "name") end)
      add(parts, "consumers")
      add(parts, #consumers)
      for _, consumer in ipairs(consumers) do add(parts, map_get(consumer, "name")) end

      add(parts, "pel")
      add(parts, pending_count)
      if pending_count > 0 then
        local pending = redis.call("XPENDING", key, group_name, "-", "+", pending_count)
        if #pending ~= pending_count then return redis.error_reply("incomplete stream PEL capture") end
        for _, item in ipairs(pending) do
          add(parts, item[1])
          add(parts, item[2])
          add(parts, item[4])
        end
      end
    end
  else
    return redis.error_reply("unsupported Redis value type: " .. tostring(kind))
  end
  return sha256(table.concat(parts))
end

local time = redis.call("TIME")
local captured_at = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local keys = redis.call("KEYS", "*")
table.sort(keys)
local durable = {}
local volatile = {}
for _, key in ipairs(keys) do
  local type_reply = redis.call("TYPE", key)
  local kind = type_reply.ok or type_reply
  local deadline = redis.call("PEXPIRETIME", key)
  if deadline == -2 then return redis.error_reply("key expired during logical capture") end
  local content = logical_digest(key, kind)
  if type(content) ~= "string" then return content end
  if deadline == -1 then
    local identity = {}
    add(identity, key)
    add(identity, content)
    durable[#durable + 1] = sha256(table.concat(identity))
  elseif deadline >= 0 then
    volatile[#volatile + 1] = sha256(key) .. ":" .. content .. ":" .. string.format("%.0f", deadline)
  else
    return redis.error_reply("invalid PTTL during logical capture")
  end
end
local out = {
  string.format("%.0f", captured_at),
  tostring(#durable) .. ":" .. sha256(table.concat(durable)),
}
for _, record in ipairs(volatile) do out[#out + 1] = record end
return out
LUA

# AOF replay can omit zero-pending consumers and can rebase PEL delivery
# counts even though those fields are part of the exact v3 recovery proof.
# Capture just that repairable state as hex so no raw stream, group, consumer,
# or PEL identifier crosses the Redis protocol boundary.
REDIS_STREAM_REPAIR_V1_LUA=""
IFS= read -r -d '' REDIS_STREAM_REPAIR_V1_LUA <<'LUA' || true
-- cabinet-redis-stream-repair-v1
local function map_get(values, wanted)
  for i = 1, #values, 2 do
    if values[i] == wanted then return values[i + 1] end
  end
  return nil
end

local function hex(value)
  return (string.gsub(value, ".", function(byte)
    return string.format("%02x", string.byte(byte))
  end))
end

local database = ARGV[1]
if not string.match(database, "^%d+$") then
  return redis.error_reply("invalid repair database")
end
local keys = redis.call("KEYS", "*")
table.sort(keys)
local out = {}
for _, key in ipairs(keys) do
  local type_reply = redis.call("TYPE", key)
  local kind = type_reply.ok or type_reply
  if kind == "stream" then
    local groups = redis.call("XINFO", "GROUPS", key)
    table.sort(groups, function(a, b) return map_get(a, "name") < map_get(b, "name") end)
    for _, group in ipairs(groups) do
      local group_name = map_get(group, "name")
      local pending_count = tonumber(map_get(group, "pending"))
      if group_name == nil or pending_count == nil or pending_count < 0 then
        return redis.error_reply("incomplete stream group repair capture")
      end
      local consumers = redis.call("XINFO", "CONSUMERS", key, group_name)
      table.sort(consumers, function(a, b) return map_get(a, "name") < map_get(b, "name") end)
      for _, consumer in ipairs(consumers) do
        local consumer_name = map_get(consumer, "name")
        if consumer_name == nil then
          return redis.error_reply("incomplete stream consumer repair capture")
        end
        out[#out + 1] = table.concat({
          "CONSUMER", database, hex(key), hex(group_name), hex(consumer_name)
        }, " ")
      end
      if pending_count > 0 then
        local pending = redis.call("XPENDING", key, group_name, "-", "+", pending_count)
        if #pending ~= pending_count then
          return redis.error_reply("incomplete stream PEL repair capture")
        end
        for _, item in ipairs(pending) do
          if item[1] == nil or item[2] == nil or tonumber(item[4]) == nil then
            return redis.error_reply("incomplete stream PEL repair entry")
          end
          out[#out + 1] = table.concat({
            "PEL", database, hex(key), hex(group_name), hex(item[1]),
            hex(item[2]), string.format("%.0f", tonumber(item[4]))
          }, " ")
        end
      end
    end
  elseif kind == "none" then
    return redis.error_reply("key expired during stream repair capture")
  end
end
return out
LUA

# The v3 SHA-256 implementation is deliberately self-contained so raw Redis
# keys and values never cross the protocol boundary. That also makes each
# EVAL_RO synchronous and server-blocking while it hashes one database. Large
# deployments must keep capture time below their write-pause budget. Pausing
# callers set REDIS_STATE_DEADLINE_EPOCH_SECONDS; the checks between databases
# fail closed with a clear error, though one unusually large database still
# cannot be pre-empted mid-EVAL and should be split or moved to a streaming
# proof before it approaches the budget.
redis_state_deadline_ok() {
  local deadline="${REDIS_STATE_DEADLINE_EPOCH_SECONDS:-}" now
  [ -n "$deadline" ] || return 0
  case "$deadline" in
    *[!0-9]*|'')
      echo "redis-state: invalid logical fingerprint deadline" >&2
      return 1
      ;;
  esac
  now=$(date +%s) || return 1
  if [ "$now" -ge "$deadline" ]; then
    echo "redis-state: logical fingerprint exceeded the write-pause budget" >&2
    return 1
  fi
}

redis_state_fingerprint() {
  local output="$1" format="$2"
  shift 2
  local -a client=("$@")
  local databases result first second record db tmp="${output}.tmp.$$"
  databases=$("${client[@]}" --raw CONFIG GET databases 2>/dev/null | tail -1) || return 1
  case "$databases" in ''|*[!0-9]*) return 1 ;; esac
  [ "$databases" -gt 0 ] && [ "$databases" -le 1024 ] || return 1
  case "$format" in
    v2) printf 'FORMAT redis-dump-content-expiry-v2\n' > "$tmp" ;;
    v3) printf 'FORMAT redis-logical-content-expiry-v3\n' > "$tmp" ;;
    *) return 1 ;;
  esac
  printf 'DATABASES %s\n' "$databases" >> "$tmp"

  db=0
  while [ "$db" -lt "$databases" ]; do
    if ! redis_state_deadline_ok; then rm -f "$tmp"; return 1; fi
    if [ "$format" = v2 ]; then
      result=$("${client[@]}" -n "$db" --raw EVAL_RO "$REDIS_STATE_V2_LUA" 0 2>/dev/null) || {
        rm -f "$tmp"; return 1;
      }
      first=$(printf '%s\n' "$result" | sed -n '1p')
      if ! printf '%s\n' "$first" | grep -Eq '^[0-9]+:[0-9a-f]{40}$'; then
        rm -f "$tmp"; return 1
      fi
      printf 'DB %s %s\n' "$db" "$first" >> "$tmp"
      while IFS= read -r record; do
        [ -n "$record" ] || continue
        if ! printf '%s\n' "$record" | grep -Eq '^[0-9a-f]{40}:[0-9]+$'; then
          rm -f "$tmp"; return 1
        fi
        printf 'EXPIRY %s %s\n' "$db" "${record/:/ }" >> "$tmp"
      done < <(printf '%s\n' "$result" | sed -n '2,$p')
    else
      result=$("${client[@]}" -n "$db" --raw EVAL_RO "$REDIS_STATE_V3_LUA" 0 2>/dev/null) || {
        rm -f "$tmp"; return 1;
      }
      first=$(printf '%s\n' "$result" | sed -n '1p')
      second=$(printf '%s\n' "$result" | sed -n '2p')
      if ! printf '%s\n' "$first" | grep -Eq '^[0-9]+$' \
        || ! printf '%s\n' "$second" | grep -Eq '^[0-9]+:[0-9a-f]{64}$'; then
        rm -f "$tmp"; return 1
      fi
      printf 'DB %s %s %s\n' "$db" "$first" "${second/:/ }" >> "$tmp"
      while IFS= read -r record; do
        [ -n "$record" ] || continue
        if ! printf '%s\n' "$record" | grep -Eq '^[0-9a-f]{64}:[0-9a-f]{64}:[0-9]+$'; then
          rm -f "$tmp"; return 1
        fi
        printf 'VOLATILE %s %s\n' "$db" "${record//:/ }" >> "$tmp"
      done < <(printf '%s\n' "$result" | sed -n '3,$p')
    fi
    if ! redis_state_deadline_ok; then rm -f "$tmp"; return 1; fi
    db=$((db + 1))
  done
  if ! python3.12 "$REDIS_STATE_TOOL" parse "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  mv "$tmp" "$output"
}

redis_state_equal() {
  python3.12 "$REDIS_STATE_TOOL" compare "$1" "$2" --tolerance-ms 2000
}

redis_state_format() {
  python3.12 "$REDIS_STATE_TOOL" format "$1"
}

expected_redis_databases() {
  python3.12 "$REDIS_STATE_TOOL" databases "$1"
}

# Usage: redis_stream_repair_manifest OUTPUT DATABASES redis-cli [options...]
# The caller owns the write pause that surrounds this capture and the v3
# fingerprint. DATABASES is explicit so a restored server cannot silently
# shrink the inspection range through a changed Redis configuration.
redis_stream_repair_manifest() (
  local output="$1" databases="$2"
  shift 2
  local -a client=("$@")
  local db result tmp
  [ "${#client[@]}" -gt 0 ] || return 1
  case "$databases" in ''|*[!0-9]*) return 1 ;; esac
  [ "$databases" -gt 0 ] && [ "$databases" -le 1024 ] || return 1

  umask 077
  tmp=$(mktemp "${output}.tmp.XXXXXX") || return 1
  chmod 600 "$tmp" || { rm -f "$tmp"; return 1; }
  {
    printf 'FORMAT redis-stream-repair-v1\n'
    printf 'DATABASES %s\n' "$databases"
  } > "$tmp" || { rm -f "$tmp"; return 1; }

  db=0
  while [ "$db" -lt "$databases" ]; do
    if ! redis_state_deadline_ok; then rm -f "$tmp"; return 1; fi
    result=$("${client[@]}" -n "$db" --raw EVAL_RO "$REDIS_STREAM_REPAIR_V1_LUA" 0 "$db" 2>/dev/null) || {
      rm -f "$tmp"
      return 1
    }
    if [ -n "$result" ]; then
      printf '%s\n' "$result" >> "$tmp" || { rm -f "$tmp"; return 1; }
    fi
    if ! redis_state_deadline_ok; then rm -f "$tmp"; return 1; fi
    db=$((db + 1))
  done
  if ! python3.12 "$REDIS_STATE_TOOL" stream-repair-parse "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  chmod 600 "$tmp" || { rm -f "$tmp"; return 1; }
  mv "$tmp" "$output"
)

# Usage: redis_stream_repair_apply MANIFEST redis-cli [options...]
# Apply is idempotent. It restores missing consumers and exact PEL ownership /
# delivery counts, then re-captures the sidecar and refuses success unless the
# repairable state is now byte-for-byte equivalent.
redis_stream_repair_apply() (
  local manifest="$1"
  shift
  local -a client=("$@")
  local databases observed
  [ "${#client[@]}" -gt 0 ] || return 1
  databases=$(python3.12 "$REDIS_STATE_TOOL" stream-repair-databases "$manifest") || return 1
  case "$databases" in ''|*[!0-9]*) return 1 ;; esac
  if ! python3.12 "$REDIS_STATE_TOOL" stream-repair-apply "$manifest" -- "${client[@]}"; then
    return 1
  fi
  umask 077
  # Keep the recapture beside the protected caller-owned manifest so an abrupt
  # process exit cannot strand reversible Redis identifiers in a shared temp
  # directory. Backup staging is mode 0700 and its EXIT cleanup removes it.
  observed=$(mktemp "${manifest}.observed.XXXXXX") || return 1
  if ! redis_stream_repair_manifest "$observed" "$databases" "${client[@]}"; then
    rm -f "$observed"
    return 1
  fi
  if ! python3.12 "$REDIS_STATE_TOOL" stream-repair-compare "$manifest" "$observed"; then
    python3.12 "$REDIS_STATE_TOOL" stream-repair-diff "$manifest" "$observed" >&2 || true
    rm -f "$observed"
    return 1
  fi
  rm -f "$observed"
)

# Offline, privacy-safe mismatch attribution. Output contains only database,
# value type, changed component, and SHA-256 of the raw stream key.
redis_stream_repair_diff() {
  python3.12 "$REDIS_STATE_TOOL" stream-repair-diff "$1" "$2"
}
