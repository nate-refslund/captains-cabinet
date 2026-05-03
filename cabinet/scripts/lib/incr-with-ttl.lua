-- Atomic INCR + EXPIRE — fixes the race where two-command (INCR then EXPIRE)
-- patterns can drop the TTL between calls, causing unbounded counter growth.
--
-- Pattern documented in production-failure literature (April 2026): non-atomic
-- INCR followed by EXPIRE in two separate commands has a TTL gap on rollover —
-- if the key expires between calls, the new key created by INCR has no TTL.
--
-- Usage from bash:
--   redis-cli -h redis -p 6379 \
--     EVAL "$(cat cabinet/scripts/lib/incr-with-ttl.lua)" 1 \
--     <key> <ttl_seconds> [<incr_amount>]
--
-- Returns: the new counter value after INCR.
--
-- Behavior:
--   - INCRBY by <incr_amount> (default 1) on KEYS[1]
--   - If TTL is unset (-1) or expired (-2), SET TTL to ARGV[1]
--   - If TTL is already set (>0), leave it alone (preserves natural expiry rolling)
--
-- Idempotent: safe to call concurrently; INCRBY + EXPIRE-if-needed are
-- atomic within the script.

local key = KEYS[1]
local ttl_sec = tonumber(ARGV[1])
local incr_amount = tonumber(ARGV[2]) or 1

if not ttl_sec or ttl_sec <= 0 then
  return redis.error_reply("ttl_seconds must be a positive integer")
end

local new_val = redis.call("INCRBY", key, incr_amount)

local current_ttl = redis.call("TTL", key)
if current_ttl == -1 or current_ttl == -2 then
  redis.call("EXPIRE", key, ttl_sec)
end

return new_val
