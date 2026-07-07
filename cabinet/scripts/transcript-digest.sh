#!/bin/bash
# transcript-digest.sh — launchd entry point for the ORG-SENSES-1
# transcript-digest organ (cabinet/scripts/transcript-digest.py).
# Fleet manifest row `transcript-digest` (cabinet/services.yml, daily 04:10
# local) + generated plist com.cabinet.transcript-digest.plist.
#
# WHAT IT RUNS: one nightly digest sweep — officer session JSONLs (+ the
# AUD-1 isolated config home's projects tree) and flight-recorder script(1)
# typescripts → redacted digests queued onto cabinet:memory:embed_queue via
# lib/memory.sh memory_queue_embed (the memory-worker drains + embeds;
# keyless stays fail-soft), + prompt-pattern lessons as experience records
# (propose-only skill_induction evidence).
#
# SELF-HEARTBEAT: a completed sweep appends one line to
# ~/.cabinet/logs/transcript-digest.log (dead-man semantics — stamped only
# after a completed sweep), the per-service log the outcome-watchdog derives
# freshness floors from once the manifest row exists.
#
# Secrets: NONE read here; the organ never prints env values and redacts
# secret-shaped transcript content (names-not-values). Read-only over its
# sources; writes = its own state/log + the Redis queue + experience JSONL.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# launchd hands a minimal PATH that excludes Homebrew (redis-cli, python3.12)
# — the exact PATH bug class that killed the 07:30 briefing on 2026-06-23.
export PATH="/opt/homebrew/bin:$PATH"

# Mac-native deployment runs Redis on localhost (queue lands via redis-cli).
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export CABINET_ROOT="${CABINET_ROOT:-$ROOT}"

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3

cd "$ROOT" || exit 1

exec "$PY" cabinet/scripts/transcript-digest.py "$@"
