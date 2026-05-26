#!/bin/bash
# enable-redis-aof.sh — enable Append-Only File durability on Homebrew Redis.
#
# Why: mac-preflight.sh flags `redis-aof: appendonly=no` as a blocker for
# unattended Mac operation. Default Homebrew Redis ships with AOF off (only
# RDB snapshots every few minutes). On crash, anything since the last RDB
# is gone — for Cabinet that means lost triggers, lost cost counters,
# lost heartbeats, lost memory-queue work.
#
# AOF appendfsync=everysec gives ~1s data-loss tolerance with minimal
# performance impact. That's the right posture for an always-on Mac mini
# Cabinet.
#
# What this does:
#   1. Reads the Homebrew Redis config path (`brew --prefix`/etc/redis.conf).
#   2. If `appendonly no` → flips to `appendonly yes` + sets `appendfsync everysec`
#      and `auto-aof-rewrite-percentage 100`, `auto-aof-rewrite-min-size 64mb`.
#   3. If already on → no-op.
#   4. Restarts `brew services redis` so the change takes effect.
#
# Idempotent. Safe to re-run.
#
# Captain-physical step? Mostly no — runs unattended via setup-mac.sh. The
# only Captain-physical edge is when Homebrew's redis.conf has been
# manually edited; this script preserves unrelated lines.

set -euo pipefail

if ! command -v redis-cli >/dev/null 2>&1; then
  echo "[enable-redis-aof] redis-cli not found — install Redis via Homebrew first: brew install redis" >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "[enable-redis-aof] Homebrew not found — this script only handles Homebrew Redis." >&2
  echo "[enable-redis-aof] For non-Homebrew installs, edit your redis.conf manually:" >&2
  echo "                     appendonly yes" >&2
  echo "                     appendfsync everysec" >&2
  exit 1
fi

CONF="$(brew --prefix)/etc/redis.conf"
if [ ! -f "$CONF" ]; then
  echo "[enable-redis-aof] Redis config not found at $CONF — is Homebrew Redis installed?" >&2
  exit 1
fi

# Current state via CONFIG GET (live Redis) — most reliable signal.
CURRENT="$(redis-cli CONFIG GET appendonly 2>/dev/null | tail -1 || echo unknown)"
if [ "$CURRENT" = "yes" ]; then
  echo "[enable-redis-aof] AOF already enabled. No-op."
  exit 0
fi

echo "[enable-redis-aof] Current appendonly = $CURRENT — enabling..."

# Live config change first (takes effect immediately, no restart needed for
# enabling AOF — Redis will start writing the AOF file).
redis-cli CONFIG SET appendonly yes
redis-cli CONFIG SET appendfsync everysec
redis-cli CONFIG REWRITE 2>/dev/null || {
  # CONFIG REWRITE fails if the original config file lacked an `appendonly`
  # directive (Redis can't infer where to write). Append our settings to
  # the config file ourselves so the change survives restart.
  echo "" >> "$CONF"
  echo "# enabled by cabinet/scripts/enable-redis-aof.sh ($(date -u +%Y-%m-%dT%H:%M:%SZ))" >> "$CONF"
  echo "appendonly yes" >> "$CONF"
  echo "appendfsync everysec" >> "$CONF"
  echo "auto-aof-rewrite-percentage 100" >> "$CONF"
  echo "auto-aof-rewrite-min-size 64mb" >> "$CONF"
  echo "[enable-redis-aof] CONFIG REWRITE not available; appended directives to $CONF"
}

# Restart via brew services so the change is loaded with full config.
# `brew services restart redis` is idempotent and survives reboots.
echo "[enable-redis-aof] Restarting brew services redis..."
brew services restart redis >/dev/null 2>&1 || {
  echo "[enable-redis-aof] brew services restart failed — try manually:" >&2
  echo "                     brew services restart redis" >&2
  exit 1
}

# Verify
sleep 2
NEW="$(redis-cli CONFIG GET appendonly 2>/dev/null | tail -1 || echo unknown)"
if [ "$NEW" = "yes" ]; then
  echo "[enable-redis-aof] AOF enabled successfully (appendonly=$NEW, appendfsync=everysec)."
  exit 0
else
  echo "[enable-redis-aof] WARN: AOF reported $NEW after restart — verify manually with 'redis-cli CONFIG GET appendonly'" >&2
  exit 1
fi
