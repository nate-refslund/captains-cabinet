#!/bin/bash
# cabinet/scripts/hooks/capture-captain-dm.sh — Capture inbound Captain DMs to cabinet_memory
#
# Wired as a UserPromptSubmit hook in .claude/settings.json. Fires after
# pre-captain-dm.sh (so the pre-hook can detect/transcribe voice first) and
# before captain-rule-encoder.sh (so the encoder runs on a fully resolved DM).
#
# Flow:
#   1. Read JSON stdin (.prompt is the user-prompt body).
#   2. Bail unless the prompt carries a <channel source="telegram" ...> tag.
#   3. Gate to the configured Captain chat_id (mirrors pre-captain-dm.sh).
#      Default-deny: missing config → silent exit (no embed).
#   4. Extract DM body. If the channel block is a voice message and the
#      shared transcript cache from pre-captain-dm.sh has a hit, use the
#      transcript instead of the "(voice message)" placeholder.
#   5. Push the DM body to the cabinet:memory:embed_queue Redis Stream
#      (source_type=telegram_dm, sender=captain). Worker processes it.
#
# Best-effort: ANY error → exit 0. Never blocks the officer reply.
#
# Reversibility: rm this file + drop the UserPromptSubmit entry in
# .claude/settings.json → inbound Captain DMs simply stop being captured.

set -u

# Allow operator disable without touching settings.json.
if [ "${CAPTURE_CAPTAIN_DM_ENABLED:-1}" = "0" ]; then
  exit 0
fi

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-${REPO_ROOT:-$(cd "$SELF_DIR/../../.." && pwd)}}"
export CABINET_ROOT

OFFICER="${OFFICER_NAME:-${CABINET_OFFICER:-unknown}}"

# Read JSON stdin.
INPUT="$(cat 2>/dev/null)"
[ -z "$INPUT" ] && exit 0

PROMPT="$(printf '%s' "$INPUT" | jq -r '.prompt // ""' 2>/dev/null)"
[ -z "$PROMPT" ] && exit 0

# Only inbound Telegram channel messages.
if ! printf '%s' "$PROMPT" | grep -q '<channel source="telegram"' 2>/dev/null; then
  exit 0
fi

# Captain chat_id gate — default-deny if missing (mirrors pre-captain-dm.sh).
CAPTAIN_CHAT_ID="$(grep -E '^[[:space:]]*captain_telegram_chat_id:' \
  "$CABINET_ROOT/instance/config/product.yml" \
  "$CABINET_ROOT/instance/config/platform.yml" 2>/dev/null \
  | head -1 | awk -F: '{print $NF}' | tr -d '"' | tr -d ' ')"
if [ -z "$CAPTAIN_CHAT_ID" ]; then
  # No way to tell Captain DMs from group @-mentions; refuse to capture.
  exit 0
fi
if ! printf '%s' "$PROMPT" | grep -qE "<channel source=\"telegram\"[^>]*chat_id=\"$CAPTAIN_CHAT_ID\"" 2>/dev/null; then
  exit 0
fi

# Pull chat_id + message_id from the channel attrs for source_id.
META="$(printf '%s' "$PROMPT" | python3 -c '
import sys, re, json
text = sys.stdin.read()
m = re.search(r"<channel source=\"telegram\"([^>]*)>", text)
if not m:
    sys.exit(0)
attrs = m.group(1)
def find_attr(name):
    am = re.search(name + r"=\"([^\"]*)\"", attrs)
    return am.group(1) if am else ""
out = {
    "chat_id": find_attr("chat_id"),
    "message_id": find_attr("message_id"),
    "username": find_attr("username"),
    "attachment_kind": find_attr("attachment_kind"),
    "attachment_mime": find_attr("attachment_mime"),
    "attachment_file_id": find_attr("attachment_file_id"),
}
sys.stdout.write(json.dumps(out))
' 2>/dev/null)"
[ -z "$META" ] && exit 0

CHAT_ID="$(printf '%s' "$META" | jq -r '.chat_id // empty' 2>/dev/null)"
MSG_ID="$(printf '%s' "$META" | jq -r '.message_id // empty' 2>/dev/null)"

# Extract the DM body between <channel ...> and </channel>.
DM_BODY="$(printf '%s' "$PROMPT" | python3 -c '
import sys, re
text = sys.stdin.read()
m = re.search(r"<channel source=\"telegram\"[^>]*>(.*?)</channel>", text, re.DOTALL)
sys.stdout.write(m.group(1).strip() if m else "")
' 2>/dev/null)"

[ -z "$DM_BODY" ] && exit 0

# Voice cache hand-off: pre-captain-dm.sh writes the transcript to
# cabinet/cache/voice-transcripts/<MSG_ID>.txt. If the DM body is the
# literal "(voice message)" placeholder and a cached transcript exists,
# substitute the transcript so semantic recall has the real words.
if [ -n "$MSG_ID" ]; then
  CACHE_FILE="$CABINET_ROOT/cabinet/cache/voice-transcripts/$MSG_ID.txt"
  if [ -f "$CACHE_FILE" ]; then
    # GNU FIRST, deliberately: on GNU coreutils `stat -f` is "file system" and
    # SUCCEEDS, printing a mount point, so a BSD-first `||` chain never falls
    # through and feeds that string into arithmetic. `stat -c` simply fails on
    # BSD, so this order is the only one that is right on both.
    cache_age=$(( $(date +%s) - $(stat -c %Y "$CACHE_FILE" 2>/dev/null || stat -f %m "$CACHE_FILE" 2>/dev/null || echo 0) ))
    if [ "$cache_age" -lt 86400 ]; then
      TRANSCRIPT="$(cat "$CACHE_FILE" 2>/dev/null)"
      if [ -n "$TRANSCRIPT" ]; then
        DM_BODY="$TRANSCRIPT"
      fi
    fi
  fi
fi

# Build source_id — globally unique per (chat_id, message_id).
# Falls back to a per-officer timestamp ref if message_id absent (rare).
if [ -n "$CHAT_ID" ] && [ -n "$MSG_ID" ]; then
  SOURCE_ID="tg-${CHAT_ID}-${MSG_ID}"
else
  SOURCE_ID="tg-in-$(date -u +%Y%m%dT%H%M%S)-${OFFICER}"
fi

NOW_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Source memory library to use memory_queue_embed (matches worker payload shape).
LIB="$CABINET_ROOT/cabinet/scripts/lib/memory.sh"
if [ ! -f "$LIB" ]; then
  exit 0
fi

# Background fire-and-forget so the hook never delays prompt delivery.
(
  set -a
  source "$CABINET_ROOT/cabinet/.env" 2>/dev/null
  set +a
  # shellcheck disable=SC1090
  source "$LIB" 2>/dev/null || exit 0

  if ! declare -f memory_queue_embed > /dev/null; then
    exit 0
  fi

  METADATA="$(jq -nc \
    --arg chat_id "$CHAT_ID" \
    --arg message_id "$MSG_ID" \
    --arg direction "incoming" \
    --argjson attach "$(printf '%s' "$META" | jq '{kind: .attachment_kind, mime: .attachment_mime, file_id: .attachment_file_id}' 2>/dev/null || echo '{}')" \
    '{chat_id: $chat_id, message_id: $message_id, direction: $direction, attachment: $attach}' 2>/dev/null)"
  [ -z "$METADATA" ] && METADATA='{}'

  memory_queue_embed "telegram_dm" "$SOURCE_ID" "$OFFICER" "captain" \
    "$DM_BODY" "$METADATA" "$NOW_TS" 2>/dev/null || true
) > /dev/null 2>&1 &

exit 0
