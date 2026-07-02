#!/bin/bash
# run-draft-lane.sh — launchd entry for the cabinet's draft-reply lane (PROPOSE-half).
#
# Finds awaiting-reply threads, drafts each in Nate's voice (should-reply gate
# filtered), and PRESENTS the draft to the Chair's Telegram (@NateHQChairBot) with
# Send / Edit: / Skip:. PROPOSE-ONLY — nothing is sent to any recipient here; the
# approve→send (via the brain's queue_draft gate) is handled by the Chair in-session.
# Restores the daily draft loop that the screenpipe draft-reply pipe used to provide.
#
# Reversible: launchctl unload ~/Library/LaunchAgents/com.cabinet.draft-lane.plist
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/cabinet/.env"
[ -f "$ENV_FILE" ] || { echo "run-draft-lane: missing $ENV_FILE" >&2; exit 1; }

# Read only the two values needed for the Telegram present (never echo / never plist).
export TELEGRAM_COS_TOKEN="$(grep '^TELEGRAM_COS_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
export CAPTAIN_TELEGRAM_ID="$(grep '^CAPTAIN_TELEGRAM_ID=' "$ENV_FILE" | cut -d= -f2-)"
export CABINET_ENV=runtime
export REDIS_HOST="${REDIS_HOST:-localhost}"
# NEW drafts surfaced per run. The recency-aware dedup (open_proposal_blocks +
# already_handled) means this caps only GENUINELY-NEW threads — decided/awaiting
# ones are already filtered out — so a small batch clears a real backlog instead
# of starving fresh messages one-per-5min behind an arbitrary straggler (the
# Kristoffer Round-2 symptom). 4 is conservative-but-unblocking. Override: DRAFT_LANE_MAX.
export DRAFT_LANE_MAX="${DRAFT_LANE_MAX:-4}"

# launchd gives a minimal PATH; Homebrew holds redis-cli + python3.12.
export PATH="/opt/homebrew/bin:$PATH"

# The brain's drafting + retrieval (sa.gather / sa.draft_fn → draft_lib) needs the
# screenpipe shared keys (Voyage, LLM gateway, etc.). Source them so drafting works.
SP_ENV="${HOME:-/Users/nate}/.screenpipe/pipes/_shared/.env"
if [ -f "$SP_ENV" ]; then set -a; . "$SP_ENV"; set +a; fi

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1
exec "$PY" framework/acting/run_draft_lane.py
