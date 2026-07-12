#!/bin/bash
# chair-release-thread.sh — the Chair RELEASES a thread it had claimed, so the
# draft-lane resumes normal handling of it.
#
# The counterpart to chair-claim-thread.sh (FIX 1 of the wrong-Milo draft
# race). The Chair calls this when it has finished hand-crafting (and queued /
# sent) its reply on a thread. It DELs the redis key
# cabinet:chair:active-thread:<slug>; once gone, screenpipe_adapter.chair_holds_thread()
# returns False and find_threads() considers the thread again. (The lock also
# auto-frees on its own TTL, so a missed release is self-healing — this just
# frees it immediately.)
#
# Key derivation MUST match screenpipe_adapter._active_thread_key and
# chair-claim-thread.sh: sanitize the slug by replacing every char outside
# [A-Za-z0-9._-] with '_'. Same redis host as the lane (REDIS_HOST, default
# localhost).
#
# Secrets: NONE. Deletes one redis key. Read-only on everything else. Idempotent:
# releasing an already-free thread is a harmless no-op.
#
# Usage:
#   chair-release-thread.sh <slug>
#   chair-release-thread.sh Milo-Archer
set -uo pipefail

SLUG="${1:-}"
if [ -z "$SLUG" ]; then
  echo "usage: chair-release-thread.sh <slug>" >&2
  exit 2
fi

SAFE="$(printf '%s' "$SLUG" | LC_ALL=C sed 's/[^A-Za-z0-9._-]/_/g')"
KEY="cabinet:chair:active-thread:${SAFE}"
HOST="${REDIS_HOST:-localhost}"

OUT="$(redis-cli -h "$HOST" DEL "$KEY" 2>/dev/null)"
if [ $? -ne 0 ]; then
  echo "ERROR: could not reach redis at $HOST to delete $KEY" >&2
  exit 1
fi
if [ "$OUT" = "1" ]; then
  echo "released: $SLUG (key=$KEY) — draft-lane will handle this thread again"
else
  echo "released: $SLUG (no active lock found — already free, no-op)"
fi
