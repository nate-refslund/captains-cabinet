#!/bin/bash
# check-cost-ledger-health.sh — is the spend ledger actually being written?
#
# WHY THIS EXISTS
#   cabinet:cost:tokens:daily:<date> is the ONLY input to the daily spending
#   caps in pre-tool-use.sh (FW-002). Its only live writer is the Stop hook,
#   cabinet/scripts/hooks/session-stop.sh. If that writer stops, the caps do
#   not tighten — they DISAPPEAR: the hook reads an empty ledger as "$0 spent
#   today" and every call stays under cap, forever, silently.
#
#   That is not hypothetical. The two tests that existed to catch exactly this
#   (golden EVAL-008 and memory/golden-evals/framework/fw-a14-stop-guard.sh)
#   were both pointed at cabinet/scripts/hooks/stop-hook.sh — a near-identical
#   twin wired to NO hook event. The tested writer was dead and the live writer
#   had no test at all, so both evals could stay green while the real ledger
#   stayed empty.
#
#   Unit tests cannot close this on their own: they prove the writer works when
#   invoked, not that anything is invoking it. This check asserts the outcome
#   in the live system — the ledger is non-empty when sessions have run.
#
# CHECKS
#   1. Redis reachable                      (else UNMEASURABLE, fail closed)
#   2. Stop hook still wired to the live writer in .claude/settings.json
#   3. That wired file still contains a cabinet:cost:tokens:daily writer
#   4. Ledger non-empty when officers have been active (the outcome check)
#   5. Every *_cost_micro field is numeric   (a corrupt ledger is untrustworthy)
#
#   Activity is judged from cabinet:heartbeat:activity:* / :liveness:*, which
#   are written by post-tool-use.sh and session-start.sh — DIFFERENT files from
#   the ledger writer. An activity signal that shared the writer would die with
#   it and this check would go quiet exactly when it should shout.
#
# GRACE
#   The daily key legitimately does not exist between 00:00 UTC and the day's
#   first Stop event. Check 4 therefore only fires once
#   CABINET_LEDGER_GRACE_MIN (default 60) minutes have elapsed since UTC
#   midnight; before that an empty ledger reports green with a note.
#
# Exit 0 = healthy. Exit 1 = a real problem (page). Read-only: this script
# never writes a Redis key and never touches a file.
#
# Usage: bash cabinet/scripts/check-cost-ledger-health.sh [--verbose]

set -uo pipefail

VERBOSE=0
[ "${1:-}" = "--verbose" ] && VERBOSE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# Redis resolution mirrors pre-tool-use.sh (B4 — Mac portability): explicit
# REDIS_HOST/REDIS_PORT win; REDIS_URL is a fallback; default is loopback.
if [ -n "${REDIS_HOST:-}" ] || [ -n "${REDIS_PORT:-}" ]; then
  REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
  REDIS_PORT="${REDIS_PORT:-6379}"
elif [ -n "${REDIS_URL:-}" ]; then
  REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
  REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)
  REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
  REDIS_PORT="${REDIS_PORT:-6379}"
else
  REDIS_HOST="127.0.0.1"
  REDIS_PORT="6379"
fi

GRACE_MIN="${CABINET_LEDGER_GRACE_MIN:-60}"
SETTINGS="$CABINET_ROOT/.claude/settings.json"
LIVE_WRITER_REL="cabinet/scripts/hooks/session-stop.sh"
LIVE_WRITER="$CABINET_ROOT/$LIVE_WRITER_REL"
LEDGER_PREFIX="cabinet:cost:tokens:daily:"

PROBLEMS=0
note()  { [ "$VERBOSE" = "1" ] && echo "       $*"; return 0; }
ok()    { echo "  [ OK ] $*"; }
bad()   { echo "  [FAIL] $*" >&2; PROBLEMS=$((PROBLEMS + 1)); }

echo "=== cost-ledger health ==="

# ---- 1. Redis reachable -------------------------------------------------
if ! command -v redis-cli > /dev/null 2>&1; then
  bad "redis-cli not on PATH — ledger health is UNMEASURABLE from here (launchd hands a minimal PATH; Homebrew's /opt/homebrew/bin is not on it)"
  echo ""
  echo "RESULT: UNMEASURABLE ($PROBLEMS problem(s))"
  exit 1
fi
PING=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PING 2>/dev/null)
if [ "$PING" != "PONG" ]; then
  bad "Redis unreachable at $REDIS_HOST:$REDIS_PORT — ledger health is UNMEASURABLE, and the spending caps have no data to read"
  echo ""
  echo "RESULT: UNMEASURABLE ($PROBLEMS problem(s))"
  exit 1
fi
ok "Redis reachable at $REDIS_HOST:$REDIS_PORT"

# ---- 2. Stop hook still wired to the live writer ------------------------
# This is the dead-twin check. If Stop stops routing to the file that writes
# the ledger, the ledger dies and every cap silently reads $0.
if [ ! -f "$SETTINGS" ]; then
  note "no .claude/settings.json at $SETTINGS — skipping wiring check (not a runtime tree)"
  ok "Stop wiring check skipped (no settings.json in this tree)"
elif grep -q "hooks/session-stop.sh" "$SETTINGS"; then
  ok "Stop hook wired to $LIVE_WRITER_REL"
else
  bad "Stop hook is NOT wired to $LIVE_WRITER_REL in .claude/settings.json — the cost ledger has no writer, so every spending cap will read \$0 spent"
fi

# ---- 3. The wired file still writes the ledger --------------------------
if [ ! -f "$LIVE_WRITER" ]; then
  bad "live writer missing: $LIVE_WRITER"
elif grep -q "$LEDGER_PREFIX" "$LIVE_WRITER"; then
  ok "live writer still contains a ${LEDGER_PREFIX}* writer"
else
  bad "$LIVE_WRITER_REL no longer writes ${LEDGER_PREFIX}* — the caps' only data source is gone"
fi

# ---- 4. Ledger non-empty when officers have been active -----------------
TODAY=$(date -u +%Y-%m-%d)
LEDGER_KEY="${LEDGER_PREFIX}${TODAY}"

# The activity signal must have the SAME officer domain as the writer, or this
# check false-positives forever. post-tool-use.sh writes
# cabinet:heartbeat:activity:$OFFICER with NO officer!=unknown gate, while
# session-stop.sh:30 gates the ledger write on exactly that. So any non-officer
# Claude Code session in this repo — the Captain's own, a reviewer's, a
# subagent's — produces `...:unknown` heartbeats and no ledger write, which
# would page LEDGER DEAD on a perfectly healthy cabinet. Exclude `unknown`:
# those sessions are genuinely not expected to write cost rows.
ACTIVE_COUNT=0
for pat in "cabinet:heartbeat:activity:*" "cabinet:heartbeat:liveness:*"; do
  n=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --scan --pattern "$pat" 2>/dev/null \
        | grep -v ':unknown$' | grep -c . )
  ACTIVE_COUNT=$((ACTIVE_COUNT + n))
done

FIELD_COUNT=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HLEN "$LEDGER_KEY" 2>/dev/null)
case "$FIELD_COUNT" in *[!0-9]*|'') FIELD_COUNT=0 ;; esac

MINUTES_INTO_DAY=$(( 10#$(date -u +%H) * 60 + 10#$(date -u +%M) ))

note "ledger key   : $LEDGER_KEY"
note "ledger fields: $FIELD_COUNT"
note "activity keys: $ACTIVE_COUNT"
note "minutes into UTC day: $MINUTES_INTO_DAY (grace $GRACE_MIN)"

if [ "$FIELD_COUNT" -gt 0 ]; then
  ok "ledger $LEDGER_KEY has $FIELD_COUNT field(s)"
elif [ "$ACTIVE_COUNT" -eq 0 ]; then
  ok "ledger empty, but no officer activity detected — nothing to record yet"
elif [ "$MINUTES_INTO_DAY" -lt "$GRACE_MIN" ]; then
  ok "ledger empty within the ${GRACE_MIN}min start-of-day grace ($MINUTES_INTO_DAY min into the UTC day)"
else
  bad "LEDGER DEAD: $ACTIVE_COUNT active officer heartbeat(s) but $LEDGER_KEY is empty, $MINUTES_INTO_DAY min into the UTC day. The Stop hook is not recording spend, so pre-tool-use.sh reads \$0 today and NO daily cap can fire. Check that Stop runs $LIVE_WRITER_REL and that its redis-cli/jq/date dependencies resolve under the launchd PATH."
fi

# ---- 5. Ledger values are numeric ---------------------------------------
# A non-numeric field means the caps cannot compute realized spend. The hook
# now refuses on this rather than coercing it to 0; surface it here too so it
# is caught before it blocks an officer.
if [ "$FIELD_COUNT" -gt 0 ]; then
  BAD_FIELDS=""
  while IFS= read -r fld; do
    [ -z "$fld" ] && continue
    case "$fld" in
      *_cost_micro) ;;
      *) continue ;;
    esac
    v=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "$LEDGER_KEY" "$fld" 2>/dev/null)
    [ -z "$v" ] && continue
    case "$v" in
      *[!0-9]*) BAD_FIELDS="${BAD_FIELDS:+$BAD_FIELDS }$fld=$v" ;;
    esac
  done < <(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HKEYS "$LEDGER_KEY" 2>/dev/null)
  if [ -n "$BAD_FIELDS" ]; then
    bad "ledger holds non-numeric cost value(s): $BAD_FIELDS — pre-tool-use.sh will refuse tool calls until this is repaired (inspect: redis-cli HGETALL $LEDGER_KEY)"
  else
    ok "all *_cost_micro values are numeric"
  fi
fi

echo ""
if [ "$PROBLEMS" -eq 0 ]; then
  echo "RESULT: HEALTHY"
  exit 0
fi
echo "RESULT: UNHEALTHY ($PROBLEMS problem(s))"
exit 1
