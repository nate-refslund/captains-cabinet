#!/usr/bin/env bash
# Publish a skill-update event so other concurrently-running officer sessions
# in this cabinet pick up the change at next tool call.
#
# Wraps the within-cabinet skill propagation pattern from the 2026-04-28
# skill-propagation-pattern-decision: PUBLISH on cabinet:skills:evolved:updated
# + INCR on cabinet:skills:evolved:version.
#
# Officers compare the version counter at session start + on each tool call
# (via post-tool-use hook) to know whether the skill index is stale. The
# version-counter pattern is crash-safe: if a session misses a PUBLISH event
# (mid-tool-call when fired), the next tool call's counter compare catches it.
#
# Usage:
#   publish-skill-update.sh <skill-name> [<event-type>]
#
#   publish-skill-update.sh "context-routing"
#   publish-skill-update.sh "context-routing" "promoted"   # evolved → foundation
#   publish-skill-update.sh "context-routing" "deprecated" # marked stale
#
# Event types: created (default), updated, promoted, deprecated, archived.

set -euo pipefail

SKILL_NAME="${1:?Usage: publish-skill-update.sh <skill-name> [<event-type>]}"
EVENT_TYPE="${2:-updated}"

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

case "$EVENT_TYPE" in
  created|updated|promoted|deprecated|archived) ;;
  *)
    echo "ERROR: invalid event-type '$EVENT_TYPE'. Valid: created, updated, promoted, deprecated, archived." >&2
    exit 2
    ;;
esac

NEW_VERSION=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  INCR cabinet:skills:evolved:version)

PAYLOAD=$(printf '{"skill":"%s","event":"%s","version":%s,"ts":"%s"}' \
  "$SKILL_NAME" "$EVENT_TYPE" "$NEW_VERSION" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")

SUBSCRIBERS=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  PUBLISH cabinet:skills:evolved:updated "$PAYLOAD")

echo "Published version=$NEW_VERSION ($EVENT_TYPE/$SKILL_NAME) to $SUBSCRIBERS subscribers"
