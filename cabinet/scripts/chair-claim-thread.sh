#!/bin/bash
# chair-claim-thread.sh — the Chair CLAIMS a thread it is hand-crafting a reply
# for, so the draft-lane never ALSO drafts (or surfaces) that same thread.
#
# This is FIX 1 of the draft-lane race that produced the wrong-Morten draft: the
# autonomous lane drafted a thread the Chair was concurrently handling. The Chair
# calls this the moment it takes ownership of a thread (and chair-release-thread.sh
# when it finishes). It SETs a redis key cabinet:chair:active-thread:<slug> with a
# TTL, which framework.acting.screenpipe_adapter.chair_holds_thread() reads in
# find_threads() to DROP the locked thread BEFORE the gate/drafter — neither
# drafting it nor pinging Nate about it.
#
# The TTL means a crashed/forgetful Chair auto-frees the thread (default 12h);
# re-running this command refreshes the lock (call it again to extend). It is the
# RUNTIME-OWNERSHIP counterpart to the standing skip-list — a thread can be
# claimed, hand-replied, released, and then resume normal lane flow.
#
# Key derivation MUST match screenpipe_adapter._active_thread_key: the slug is
# sanitized by replacing every char outside [A-Za-z0-9._-] with '_', so the
# helper and the reader compute the identical key for a given slug. Same redis
# host as the lane (REDIS_HOST, default localhost).
#
# Secrets: NONE. Writes one redis key. Read-only on everything else.
#
# Usage:
#   chair-claim-thread.sh <slug> [ttl_seconds]
#   chair-claim-thread.sh Morten-Stagaard            # default 12h TTL
#   chair-claim-thread.sh Morten-Stagaard 7200       # custom 2h TTL
set -uo pipefail

SLUG="${1:-}"
TTL="${2:-43200}"   # 12h default
if [ -z "$SLUG" ]; then
  echo "usage: chair-claim-thread.sh <slug> [ttl_seconds]" >&2
  exit 2
fi

# Sanitize the slug EXACTLY like screenpipe_adapter._active_thread_key so the
# lock the lane reads is the lock the Chair set (flat key, no spaces/colons).
SAFE="$(printf '%s' "$SLUG" | LC_ALL=C sed 's/[^A-Za-z0-9._-]/_/g')"
KEY="cabinet:chair:active-thread:${SAFE}"
HOST="${REDIS_HOST:-localhost}"

if redis-cli -h "$HOST" SET "$KEY" "1" EX "$TTL" >/dev/null 2>&1; then
  echo "claimed: $SLUG (key=$KEY ttl=${TTL}s) — draft-lane will skip this thread"
  echo "release with: chair-release-thread.sh $SLUG"
else
  echo "ERROR: could not reach redis at $HOST to set $KEY" >&2
  exit 1
fi
