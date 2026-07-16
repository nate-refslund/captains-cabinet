#!/bin/bash
# remind-captain.sh — file a Captain reminder that fires to the Captain's
# one-tap card surface at a chosen time (the create half of the Captain-arm).
#
# The Chair (or any officer, e.g. after "remind me tomorrow to …") runs this;
# it inserts ONE officer_tasks row OWNED BY THE CAPTAIN
# (officer_slug = framework.env.captain_slug(), type = 'reminder',
# status = 'queue') with a due_at. cabinet/scripts/due-at-reminder-tick.sh then
# files a needs-ledger one-tap card when the row comes due — which renders into
# the frontdoor briefing digest + attention drain to the Captain's Telegram.
#
# Usage:
#   remind-captain.sh <when> <text...>            [--context SLUG]
#
#   <when>  one of (see docs/runbooks/captain-reminders.md for the full grammar):
#     2026-07-20T09:00          ISO 8601, Captain-local wall clock
#     2026-07-20T09:00:00Z      ISO 8601, tz-aware (used as-is)
#     "today 09:00"             today at 09:00 local   (quote OR two tokens)
#     "tomorrow 09:00"          tomorrow at 09:00 local
#     "monday 09:00"            the NEXT monday (mon..sun) at 09:00 local
#     +3d  /  +6h  /  +90m      N days / hours / minutes from now
#   Ambiguous input or a past time is REFUSED loudly — this never guesses.
#
#   <text...> the reminder body (all remaining args). UNTRUSTED — bound to the
#   INSERT via `psql -v`, NEVER interpolated into SQL program text.
#
# Officers self-filing reminders for THEMSELVES do not need this script: any
# officer_tasks row with a due_at already fires a task_reminder to the owning
# officer's Redis stream (Spec 041). This script is the Captain-surface sugar.
#
# Connection string: CONN > NEON_CONNECTION_STRING > DATABASE_URL (same
# resolution as due-at-reminder-tick.sh) — read from env, NEVER echoed/logged.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARM="$HERE/captain-reminder-arm.py"
PY="${PYTHON:-python3.12}"

usage() {
  grep '^# ' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

[ $# -lt 1 ] && usage

# --- parse <when> (single quoted arg OR the two-token 'day HH:MM' form) -------
DAY_WORDS=" today tomorrow monday tuesday wednesday thursday friday saturday sunday mon tue tues wed thu thur thurs fri sat sun "
WHEN=""
first="$1"
first_lc="$(printf '%s' "$first" | tr '[:upper:]' '[:lower:]')"
if [[ "$DAY_WORDS" == *" $first_lc "* ]] && [ $# -ge 2 ] \
   && [[ "$2" =~ ^([01]?[0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  WHEN="$1 $2"; shift 2
else
  WHEN="$1"; shift
fi

# --- remaining args: text, with an optional --context flag anywhere ----------
CONTEXT_SLUG=""
TEXT_PARTS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --context) CONTEXT_SLUG="${2:-}"; shift 2 ;;
    --context=*) CONTEXT_SLUG="${1#--context=}"; shift ;;
    *) TEXT_PARTS+=("$1"); shift ;;
  esac
done
TEXT="${TEXT_PARTS[*]:-}"

if [ -z "${WHEN// }" ]; then echo "ERROR: <when> required" >&2; usage; fi
if [ -z "${TEXT// }" ]; then echo "ERROR: reminder <text> required" >&2; usage; fi

# --- connection string (env only; never echoed) ------------------------------
CONN="${CONN:-${NEON_CONNECTION_STRING:-${DATABASE_URL:-}}}"
if [ -z "$CONN" ]; then
  echo "ERROR: no DB connection string (CONN | NEON_CONNECTION_STRING | DATABASE_URL)" >&2
  exit 1
fi

# --- resolve owner slug + fire time via the arm (framework.env-backed) --------
OWNER="$("$PY" "$ARM" owner-slug 2>/dev/null)"
if [ -z "$OWNER" ]; then
  echo "ERROR: could not resolve the Captain owner slug" >&2
  exit 1
fi

# parse-when prints a UTC ISO instant on success, or exits non-zero with a
# REFUSED line on stderr (past / ambiguous). Surface that verbatim and abort —
# never guess a time.
DUE_UTC="$("$PY" "$ARM" parse-when "$WHEN")"
PW_RC=$?
if [ $PW_RC -ne 0 ] || [ -z "$DUE_UTC" ]; then
  echo "ERROR: could not parse <when>='$WHEN' (see the refusal above)." >&2
  exit "$PW_RC"
fi

# --- resolve context_slug (mirror my-tasks.sh: flag / env / active-project) ---
CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
if [ -z "$CONTEXT_SLUG" ] && [ -n "${CABINET_CONTEXT:-}" ]; then
  CONTEXT_SLUG="$CABINET_CONTEXT"
fi
if [ -z "$CONTEXT_SLUG" ] && [ -f "$CABINET_ROOT/instance/config/active-project.txt" ]; then
  CONTEXT_SLUG="$(tr -d '[:space:]' < "$CABINET_ROOT/instance/config/active-project.txt")"
fi
if [ -z "$CONTEXT_SLUG" ]; then
  echo "ERROR: context_slug required. Pass --context <slug>, set \$CABINET_CONTEXT, or write instance/config/active-project.txt." >&2
  exit 1
fi
if [ ! -f "$CABINET_ROOT/instance/config/contexts/$CONTEXT_SLUG.yml" ]; then
  echo "ERROR: context '$CONTEXT_SLUG' has no YAML at instance/config/contexts/$CONTEXT_SLUG.yml." >&2
  exit 1
fi

# --- INSERT (fully parameterized; untrusted text bound via -v, never inlined) -
# type='reminder' requires migration 042 (officer_tasks_type_check widened).
# The `{ …; } 2>&1` wrapper mirrors my-tasks.sh's `start` so a CHECK/constraint
# error is captured for the readable message below.
OUTPUT=$({ psql "$CONN" -v ON_ERROR_STOP=1 -A -t -q \
  -v slug="$OWNER" -v title="$TEXT" -v ctx="$CONTEXT_SLUG" -v due="$DUE_UTC" <<'SQL'
BEGIN;
SELECT set_config('app.cabinet_officer', :'slug', true);
INSERT INTO officer_tasks (officer_slug, title, status, type, due_at, context_slug)
VALUES (:'slug', :'title', 'queue', 'reminder', :'due'::timestamptz, :'ctx')
RETURNING id, due_at;
COMMIT;
SQL
} 2>&1)
RC=$?
if [ $RC -ne 0 ] || ! printf '%s' "$OUTPUT" | grep -qE '^[0-9]+\|'; then
  echo "ERROR: reminder INSERT failed: $OUTPUT" >&2
  exit 1
fi

ROW_ID=$(printf '%s\n' "$OUTPUT" | grep -E '^[0-9]+\|' | head -1 | cut -d'|' -f1)
echo "REMINDER id=$ROW_ID owner=$OWNER fire_at=$DUE_UTC context=$CONTEXT_SLUG"
