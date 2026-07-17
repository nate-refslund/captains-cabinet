#!/bin/bash
# model-fallback-pager.sh — AUD-2 loud-fallback page (Notification hook, audit #6/#33)
#
# The fleet pins claude-opus-4-8[1m] and start-officer-mac.sh appends
# --fallback-model 'claude-opus-4-8' to every officer launch line. The standing
# model rule (captain-decisions) requires non-primary-model operation to be
# LOUD — no silent fallback. This hook is the loud half: when the CLI emits a
# Notification whose text says model fallback engaged, it
#   1. stamps  cabinet:model-fallback:<officer>  in Redis (7d TTL, always), and
#   2. pages the Captain via the First Mate bot (TELEGRAM_COS_TOKEN +
#      CAPTAIN_TELEGRAM_ID — the cabinet Telegram plane, never the personal
#      bot), debounced (default 30 min per officer,
#      CABINET_FALLBACK_PAGE_DEBOUNCE_SECS overrides, 0 = page every time).
#
# LAYOUT NOTE: this script deliberately lives in cabinet/scripts/hooks-src/
# (NOT cabinet/scripts/hooks/ — that dir is schg-locked germline). Wiring
# lives in .claude/settings.local.json (the non-germline local settings
# layer, gitignored per Claude Code convention):
#   "Notification": [{"hooks":[{"type":"command","command":"bash","args":
#     ["${CLAUDE_PROJECT_DIR}/cabinet/scripts/hooks-src/model-fallback-pager.sh"],
#     "timeout":10}]}]
# The AUD-9 germline unlock window MAY consolidate the entry into
# .claude/settings.json (see the claude-code-audit addendum §AUD-2); until
# then the local wiring is load-bearing on the live box.
#
# KNOWN COVERAGE GAP (2026-07-07, CC 2.1.202): the documented Notification
# matcher types (permission_prompt, idle_prompt, auth_success, elicitation_*,
# agent_needs_input, agent_completed) do NOT include a model-fallback type,
# so whether the CLI emits a Notification event when fallback engages is
# UNVERIFIED until the first real engagement. If it proves silent, the next
# detection surface is statusline.sh (its stdin JSON carries model.id every
# render — compare against the pinned primary). Tracked on ledger row AUD-2.
#
# stdin: { session_id, transcript_path, cwd, hook_event_name, message, title? }
# Exit: ALWAYS 0 (a notification hook must never block the session).
# Security: token/chat-id values come from env or cabinet/.env and are never
# echoed; the notification excerpt is passed to curl as a data arg (no eval,
# no parse_mode) — message content is data, never interpreted.

HOOK_INPUT=$(cat 2>/dev/null || true)
# hooks-src/ sits at cabinet/scripts/hooks-src/ → repo root is three levels up
# (same resolution as the sibling germline hooks).
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-${CABINET_OFFICER:-unknown}}"

[ -n "$HOOK_INPUT" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

MSG=$(printf '%s' "$HOOK_INPUT" | jq -r '.message // empty' 2>/dev/null | head -c 300)
TITLE=$(printf '%s' "$HOOK_INPUT" | jq -r '.title // empty' 2>/dev/null | head -c 200)
TEXT_LC=$(printf '%s %s' "$TITLE" "$MSG" | tr '[:upper:]' '[:lower:]')

# Fallback-engagement match: require fallback in a model context so a stray
# "fallback" in an unrelated permission prompt does not page the Captain.
case "$TEXT_LC" in
  *model*fallback*|*fallback*model*|*"falling back"*|*fallback*claude-*)
    : ;; # engaged — fall through to stamp + page
  *)
    exit 0 ;;
esac

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
DEBOUNCE_SECS="${CABINET_FALLBACK_PAGE_DEBOUNCE_SECS:-1800}"

echo "model-fallback-pager: fallback engaged officer=$OFFICER at $TIMESTAMP (msg: $(printf '%s' "$MSG" | head -c 120))" >&2

# --- 1) Stamp (always, 7d TTL so a stale stamp self-expires) ---------------
if command -v redis-cli >/dev/null 2>&1; then
  STAMP=$(jq -cn --arg ts "$TIMESTAMP" --arg officer "$OFFICER" --arg msg "$MSG" \
    '{ts: $ts, officer: $officer, message: $msg}' 2>/dev/null)
  [ -n "$STAMP" ] || STAMP="{\"ts\":\"$TIMESTAMP\"}"
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
    SET "cabinet:model-fallback:$OFFICER" "$STAMP" EX 604800 >/dev/null 2>&1 || true

  # --- debounce gate (SET NX EX) — only gates the PAGE, never the stamp ----
  if [ "$DEBOUNCE_SECS" != "0" ]; then
    NX_RESULT=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
      SET "cabinet:model-fallback:page-debounce:$OFFICER" "$TIMESTAMP" NX EX "$DEBOUNCE_SECS" 2>/dev/null)
    if [ "$NX_RESULT" != "OK" ]; then
      echo "model-fallback-pager: page debounced (window ${DEBOUNCE_SECS}s) for $OFFICER" >&2
      exit 0
    fi
  fi
fi
# Redis absent/down: stamp+debounce unavailable — still page (loud beats quiet).

# --- 2) Page the First Mate (First Mate bot plane) -------------------------
TOKEN="${TELEGRAM_COS_TOKEN:-}"
CHAT_ID="${CAPTAIN_TELEGRAM_ID:-}"
ENV_FILE="$CABINET_ROOT/cabinet/.env"
if [ -z "$TOKEN" ] && [ -f "$ENV_FILE" ]; then
  TOKEN=$(grep '^TELEGRAM_COS_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2-)
fi
if [ -z "$CHAT_ID" ] && [ -f "$ENV_FILE" ]; then
  CHAT_ID=$(grep '^CAPTAIN_TELEGRAM_ID=' "$ENV_FILE" | head -1 | cut -d= -f2-)
fi

if [ -n "$TOKEN" ] && [ -n "$CHAT_ID" ] && command -v curl >/dev/null 2>&1; then
  PAGE_TEXT="🚨 Model fallback engaged — officer=$OFFICER at $TIMESTAMP
${MSG:-$TITLE}

Primary pin is claude-opus-4-8[1m]; the session degraded to the fallback model (AUD-2 loud-fallback rule: non-primary operation must be loud). Stamp: cabinet:model-fallback:$OFFICER"
  curl -s --max-time 5 -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -d chat_id="$CHAT_ID" \
    --data-urlencode text="$PAGE_TEXT" >/dev/null 2>&1 \
    && echo "model-fallback-pager: Captain paged for $OFFICER" >&2 \
    || echo "model-fallback-pager: page send failed for $OFFICER (non-blocking)" >&2
else
  echo "model-fallback-pager: no page transport (token/chat-id/curl missing) — stamp only" >&2
fi

exit 0
