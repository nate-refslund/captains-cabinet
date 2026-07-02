#!/bin/bash
# cabinet/scripts/lib/reflection.sh — the ONE host-correct sink for per-officer
# reflection cadence. Source this; never re-implement the stamp by hand.
#
# WHY THIS EXISTS (root-cause fix, 2026-06-25):
#   The individual-reflection skill + post-compact hook hardcoded
#   `redis-cli -h redis -p 6379` to stamp `cabinet:schedule:last-run:<o>:reflection`
#   and INCR `cabinet:reflections:count`. On the Mac-native deployment the Docker
#   service name `redis` does NOT resolve, so the SET silently failed (exit 1,
#   swallowed by `2>/dev/null`) while a later GET via a working host returned
#   nothing — "the stamp didn't persist." Reflection therefore never registered
#   for ANY officer, and the meta-cognition anomaly-scan (which reads those two
#   keys) + the cross-officer-retro trigger (fires at reflections:count>=5) were
#   both starved. Centralizing the stamp here, behind the same proven
#   REDIS_HOST resolution the post-tool-use hook uses (B4 — Mac portability),
#   makes the stamp correct-by-construction on BOTH Mac-native and Docker and
#   kills the `-h redis` class of bug for reflection for good.
#
# Two responsibilities:
#   1. reflection_due <officer> [min_gap_minutes]
#      Echoes 1 when a reflection is WARRANTED, else 0. Event-gated, never a
#      clock: warranted == the officer did NEW work since its last reflection
#      (an experience record landed after the last reflection stamp) AND at
#      least min_gap_minutes have elapsed since that last stamp (default 90,
#      mirrors the screenpipe self-knowledge MIN_GAP guard against re-asking).
#      Idle (no new work) → 0, so the loops stay quiet exactly as designed.
#
#   2. reflection_stamp <officer>
#      The single stamp. SET cabinet:schedule:last-run:<officer>:reflection = now
#      AND INCR cabinet:reflections:count. Host-correct. Call this as the LAST
#      step of an individual-reflection pass (skill step 7). Echoes the new
#      reflections:count on success, nothing on redis-unavailable.
#
# Secrets: NONE. No network beyond local Redis. Read-mostly (two writes in
# reflection_stamp). Safe to source from any officer session or scheduled hook.
#
# Reversibility: rm this file + revert the 2 skill copies / post-compact / loop
# prompts to their prior text and the reflection cadence reverts. No DB, no
# schema, no migration.

# ── REDIS resolution (verbatim mirror of post-tool-use.sh "B4 — Mac portability")
# Honors REDIS_HOST + REDIS_PORT first; REDIS_URL only if neither is set; else a
# local default that always resolves on Mac-native (127.0.0.1). This is the
# whole point of the helper — every caller gets the working host.
_refl_resolve_redis() {
  if [ -n "${REDIS_HOST:-}" ] || [ -n "${REDIS_PORT:-}" ]; then
    REFL_REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
    REFL_REDIS_PORT="${REDIS_PORT:-6379}"
  elif [ -n "${REDIS_URL:-}" ]; then
    REFL_REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
    REFL_REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)
    REFL_REDIS_HOST="${REFL_REDIS_HOST:-127.0.0.1}"
    REFL_REDIS_PORT="${REFL_REDIS_PORT:-6379}"
  else
    REFL_REDIS_HOST="127.0.0.1"
    REFL_REDIS_PORT="6379"
  fi
}

_refl_redis() {
  # Thin wrapper: resolve host once per call, run redis-cli, swallow nothing the
  # caller didn't ask to swallow. Returns redis-cli's exit code.
  command -v redis-cli >/dev/null 2>&1 || return 127
  _refl_resolve_redis
  redis-cli -h "$REFL_REDIS_HOST" -p "$REFL_REDIS_PORT" "$@"
}

# Slug guard — same contract as the rest of the cabinet (lowercase, digits, dash).
_refl_valid_officer() {
  case "$1" in
    "" ) return 1 ;;
    *[!a-z0-9-]* ) return 1 ;;
    * ) [ "${#1}" -le 32 ] ;;
  esac
}

# Parse an ISO-8601 UTC timestamp (…Z) to epoch seconds. Echoes epoch or empty.
_refl_iso_to_epoch() {
  local iso="${1%Z}"
  [ -z "$iso" ] && return 0
  # GNU date first, BSD/macOS date second.
  date -u -d "$iso" +%s 2>/dev/null \
    || date -u -j -f "%Y-%m-%dT%H:%M:%S" "$iso" +%s 2>/dev/null \
    || true
}

# reflection_due <officer> [min_gap_minutes]  → echoes "1" (do reflect) | "0"
reflection_due() {
  local officer="$1" min_gap_min="${2:-90}"
  _refl_valid_officer "$officer" || { echo 0; return 0; }
  command -v redis-cli >/dev/null 2>&1 || { echo 0; return 0; }

  local last_refl last_work now_epoch refl_epoch work_epoch
  last_refl="$(_refl_redis GET "cabinet:schedule:last-run:${officer}:reflection" 2>/dev/null)"
  last_work="$(_refl_redis GET "cabinet:last-experience:${officer}" 2>/dev/null)"
  now_epoch="$(date -u +%s)"

  # No work signal at all since the last experience-record TTL window → idle →
  # nothing to reflect on. (last-experience is set by record-experience.sh with
  # a 2h TTL; its presence is a positive "recent work happened" signal.)
  if [ -z "$last_work" ] || [ "$last_work" = "(nil)" ]; then
    echo 0; return 0
  fi
  work_epoch="$(_refl_iso_to_epoch "$last_work")"
  [ -z "$work_epoch" ] && { echo 0; return 0; }

  # First-ever reflection: work exists, never reflected → due.
  if [ -z "$last_refl" ] || [ "$last_refl" = "(nil)" ]; then
    echo 1; return 0
  fi
  refl_epoch="$(_refl_iso_to_epoch "$last_refl")"
  [ -z "$refl_epoch" ] && { echo 1; return 0; }  # unparseable stamp → reflect + restamp clean

  # Min-gap guard: don't reflect more than once per min_gap_minutes.
  if [ "$(( now_epoch - refl_epoch ))" -lt "$(( min_gap_min * 60 ))" ]; then
    echo 0; return 0
  fi

  # New work since last reflection? (work signal newer than the last stamp.)
  if [ "$work_epoch" -gt "$refl_epoch" ]; then
    echo 1; return 0
  fi
  echo 0; return 0
}

# reflection_stamp <officer>  → SET last-run + INCR count, host-correct.
# Echoes the new reflections:count on success.
reflection_stamp() {
  local officer="$1"
  _refl_valid_officer "$officer" || { echo "reflection_stamp: invalid officer '$officer'" >&2; return 2; }
  command -v redis-cli >/dev/null 2>&1 || { echo "reflection_stamp: redis-cli unavailable — stamp skipped" >&2; return 127; }

  local now_iso count
  now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if ! _refl_redis SET "cabinet:schedule:last-run:${officer}:reflection" "$now_iso" >/dev/null 2>&1; then
    echo "reflection_stamp: redis SET failed (host unreachable) — stamp NOT recorded" >&2
    return 1
  fi
  count="$(_refl_redis INCR cabinet:reflections:count 2>/dev/null)"
  echo "${count:-?}"
  return 0
}
