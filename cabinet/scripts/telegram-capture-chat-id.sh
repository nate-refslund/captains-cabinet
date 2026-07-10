#!/bin/bash
# telegram-capture-chat-id.sh — one-shot Captain chat-id capture (errand E1b).
#
# The return leg of the bot-token errand (design of record:
# docs/plans/world-onboarding-hatching-2026-07-09.md §3 E1b): after the bot
# token is set, the Captain sends the bot ANY word from their own Telegram;
# this helper polls getUpdates ONCE — a single read-only HTTP GET against the
# FIXED host api.telegram.org, with NO offset parameter, so no update is
# consumed (the Chair's poller still sees everything later) — and reports:
#   - latest PRIVATE message in the window -> CAPTAIN_TELEGRAM_ID candidate
#   - latest GROUP chat (id < 0) in window -> TELEGRAM_HQ_CHAT_ID candidate
# WINDOW SEMANTICS: Telegram serves the OLDEST pending updates first and no
# offset is ever sent, so the window is the oldest <=100 pending updates
# (limit=100 = the API max). "Latest" means latest WITHIN that window; a
# warn fires when the window comes back full (newer messages may lie
# beyond it).
# Chat ids are addresses, never secrets (design §2.3 row 3) — printing them
# is fine. The TOKEN is never printed, never argv, never logged.
#
# CAPTAIN_TELEGRAM_ID is the default-deny IDENTITY GATE officers apply to
# inbound DMs, so --write never seeds it unseen (design §3 E1b: the Captain
# CONFIRMS the id into the answers): on a TTY it shows the sender id + name
# and asks y/N; non-interactive runs write NOTHING unless --yes is given.
# Verify the printed id is YOURS — a stranger who DM'd the fresh bot first
# would otherwise become the Captain.
#
# RUN ONLY BEFORE THE CHAIR'S POLLER STARTS (the pre-deploy hatching window).
# If another poller or a webhook holds the token, Telegram answers 409
# Conflict — reported honestly, nothing stolen.
#
# Usage:
#   telegram-capture-chat-id.sh              report captured ids only
#   telegram-capture-chat-id.sh --write      also fill CAPTAIN_TELEGRAM_ID
#                                            (+ TELEGRAM_HQ_CHAT_ID when a group
#                                            message was seen) in cabinet/.env —
#                                            ONLY keys that are currently empty;
#                                            never overwrites (refuse-if-set);
#                                            confirms y/N on a TTY, refuses
#                                            non-interactively without --yes
#   telegram-capture-chat-id.sh --write --yes  skip the confirm prompt — only
#                                            after verifying the ids are yours
#   telegram-capture-chat-id.sh --env NAME   token env var NAME (default
#                                            TELEGRAM_COS_TOKEN; falls back to
#                                            cabinet/.env)
# Exit codes:
#   0  ids captured
#   1  Telegram rejected the token
#   2  could not reach api.telegram.org / unparseable response
#   3  no updates yet — send your bot any word, then re-run (honest empty)
#   4  409 Conflict — another poller/webhook holds this token
#   64 usage error / no token found
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Script lives at cabinet/scripts/, so repo root is TWO levels up (R4/R5 pattern).
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ENV_FILE="$CABINET_ROOT/cabinet/.env"

VAR_NAME="TELEGRAM_COS_TOKEN"
WRITE=0
YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --write) WRITE=1; shift ;;
    --yes) YES=1; shift ;;
    --env)
      [ $# -ge 2 ] || { echo "telegram-capture-chat-id: --env needs a variable NAME" >&2; exit 64; }
      VAR_NAME="$2"; shift 2 ;;
    # Self-maintaining help: print the leading comment block only (a numeric
    # sed range drifts when the header grows and leaks code lines).
    --help|-h) awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"; exit 0 ;;
    *) echo "telegram-capture-chat-id: unknown arg: $1" >&2; exit 64 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
info() { echo -e "  ${BLUE}[i]${NC} $1"; }

scrub() { sed -E 's|/bot[^/[:space:]"]+|/bot***REDACTED***|g'; }

if ! printf '%s' "$VAR_NAME" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]*$'; then
  echo "telegram-capture-chat-id: invalid variable name: $VAR_NAME" >&2
  exit 64
fi

# Read current value of KEY=... from .env. Empty string if unset.
current_value() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | sed "s/^${key}=//; s/^\"//; s/\"$//"
}

# Update KEY=value in .env (adds the line if KEY absent) — same awk pattern
# as setup-env.sh.
set_env_key() {
  local key="$1" value="$2"
  local tmp; tmp="$(mktemp)"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    awk -v k="$key" -v v="$value" \
      'BEGIN { FS="="; OFS="=" } $1 == k { print k "=" v; next } { print }' \
      "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"
    echo "${key}=${value}" >> "$tmp"
  fi
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

# Fill a key only when currently empty — the .env write plane never
# overwrites (matches the hatching write doctrine, refuse-if-set).
fill_if_empty() {
  local key="$1" value="$2"
  local cur; cur="$(current_value "$key")"
  if [ -n "$cur" ]; then
    warn "$key already set in cabinet/.env — NOT overwriting (change via: setup-env.sh --force)"
    return 0
  fi
  set_env_key "$key" "$value"
  ok "$key=$value written to cabinet/.env"
}

TOKEN="${!VAR_NAME:-}"
if [ -z "$TOKEN" ] && [ -f "$ENV_FILE" ]; then
  TOKEN="$(grep -E "^${VAR_NAME}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  TOKEN="${TOKEN%\"}"; TOKEN="${TOKEN#\"}"
fi
if [ -z "$TOKEN" ]; then
  fail "no token in \$$VAR_NAME or cabinet/.env — set the bot token first (setup-env.sh)"
  exit 64
fi

if [ "$WRITE" -eq 1 ] && [ ! -f "$ENV_FILE" ]; then
  fail "--write needs cabinet/.env — run: bash cabinet/scripts/setup-env.sh --defaults"
  exit 64
fi

if ! command -v curl >/dev/null 2>&1; then
  fail "curl not found — cannot reach api.telegram.org"
  exit 2
fi

info "one-shot getUpdates poll (read-only: no offset sent, no update consumed)"

BODY="$(mktemp)"; ERRF="$(mktemp)"
cleanup() { rm -f "$BODY" "$ERRF"; }
trap cleanup EXIT

# limit=100 is the API max — anything smaller SHRINKS the pending window
# (Telegram serves oldest first, so a narrow window can hide the newest DM).
currc=0
HTTP_CODE="$(printf 'url = "https://api.telegram.org/bot%s/getUpdates?timeout=0&limit=100"\n' "$TOKEN" \
  | curl -sS --max-time 10 -K - -o "$BODY" -w '%{http_code}' 2>"$ERRF")" || currc=$?

if [ "$currc" -ne 0 ] || [ -z "$HTTP_CODE" ] || [ "$HTTP_CODE" = "000" ]; then
  fail "could not reach api.telegram.org (curl exit $currc)"
  scrub < "$ERRF" | sed 's/^/    /' >&2
  exit 2
fi

if [ "$HTTP_CODE" = "409" ]; then
  fail "409 Conflict — another poller (or a webhook) holds this token. Run this ONLY before the Chair's poller starts."
  exit 4
fi

PARSED="$(python3 - "$BODY" 2>/dev/null <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        d = json.load(fh)
except Exception:
    print("PARSE_ERROR")
    raise SystemExit(0)
if d.get("ok") is not True:
    print("REJECTED|" + str(d.get("description", "no description")))
    raise SystemExit(0)
updates = d.get("result", [])
captain_id = ""
private_chat = ""
group_id = ""
label = ""
for u in updates:
    m = u.get("message") or u.get("edited_message") or {}
    chat = m.get("chat") or {}
    frm = m.get("from") or {}
    cid = chat.get("id")
    if not isinstance(cid, int):
        continue
    if cid > 0 and isinstance(frm.get("id"), int):
        captain_id = str(frm["id"])   # latest private msg IN THE WINDOW wins
        private_chat = str(cid)
        u_name = frm.get("username")
        f_name = frm.get("first_name")
        raw = "@" + u_name if isinstance(u_name, str) and u_name else (
            f_name if isinstance(f_name, str) else "")
        # sanitized for the single-line pipe protocol + terminal output
        label = "".join(
            c if c.isprintable() and c != "|" else " " for c in raw
        )[:64].strip()
    elif cid < 0:
        group_id = str(cid)           # latest group msg IN THE WINDOW wins
if not captain_id and not group_id:
    print("EMPTY")
else:
    print("FOUND|%s|%s|%s|%d|%s"
          % (captain_id, private_chat, group_id, len(updates), label))
PY
)" || PARSED="PARSE_ERROR"

case "$PARSED" in
  REJECTED\|*)
    fail "Telegram rejected the token: $(printf '%s' "${PARSED#REJECTED|}" | scrub)"
    exit 1
    ;;
  EMPTY)
    warn "no messages seen yet — open Telegram, send your bot ANY word, then re-run this script"
    exit 3
    ;;
  FOUND\|*)
    rest="${PARSED#FOUND|}"
    CAPTAIN_ID="${rest%%|*}"; rest="${rest#*|}"
    PRIVATE_CHAT="${rest%%|*}"; rest="${rest#*|}"
    GROUP_ID="${rest%%|*}"; rest="${rest#*|}"
    UPDATE_COUNT="${rest%%|*}"
    FROM_LABEL="${rest#*|}"   # sanitized by the parser; '|'-free
    ;;
  *)
    fail "unexpected response from api.telegram.org (HTTP $HTTP_CODE, unparseable body)"
    exit 2
    ;;
esac

if [ -n "$CAPTAIN_ID" ]; then
  ok "Captain Telegram id candidate (latest private sender in the window): $CAPTAIN_ID${FROM_LABEL:+ — $FROM_LABEL}"
  [ -n "$PRIVATE_CHAT" ] && [ "$PRIVATE_CHAT" != "$CAPTAIN_ID" ] && info "private chat id: $PRIVATE_CHAT"
  info "VERIFY this id is YOURS — it becomes the default-deny identity gate on inbound DMs"
else
  warn "no PRIVATE message seen — DM the bot directly to capture CAPTAIN_TELEGRAM_ID"
fi
if [ -n "$GROUP_ID" ]; then
  ok "group chat id (warroom candidate): $GROUP_ID"
fi
if [ "${UPDATE_COUNT:-0}" -ge 100 ] 2>/dev/null; then
  warn "pending-update window came back FULL ($UPDATE_COUNT updates) — newer messages may lie beyond it (Telegram serves oldest first; no offset is ever sent, so re-runs see the same window)."
  warn "  If the ids look wrong: quiet the bot's group chats, wait for update expiry (~24h), or start the poller and read the ids from its log."
fi

if [ "$WRITE" -eq 1 ]; then
  echo ""
  # CAPTAIN_TELEGRAM_ID is the default-deny identity gate on inbound DMs —
  # never seed it from "whoever DM'd the bot" without a human eye (design
  # §3 E1b: the Captain CONFIRMS the id). Interactive: y/N prompt.
  # Non-interactive: refuse unless --yes.
  will_write=0
  [ -n "$CAPTAIN_ID" ] && [ -z "$(current_value "CAPTAIN_TELEGRAM_ID")" ] && will_write=1
  [ -n "$GROUP_ID" ] && [ -z "$(current_value "TELEGRAM_HQ_CHAT_ID")" ] && will_write=1
  confirmed=0
  if [ "$will_write" -eq 0 ]; then
    confirmed=1   # nothing new would be written; fill_if_empty only reports
  elif [ "$YES" -eq 1 ]; then
    confirmed=1
    warn "--yes given — skipping the confirm prompt; you attest the ids above are YOURS"
  elif [ -t 0 ]; then
    echo -n "  Write the captured id(s) to cabinet/.env? CAPTAIN_TELEGRAM_ID becomes the inbound-DM identity gate. [y/N]: "
    read -r reply || reply=""
    case "$reply" in
      y|Y|yes|YES) confirmed=1 ;;
      *) warn "declined — nothing written (re-run --write once you've verified the ids)" ;;
    esac
  else
    warn "stdin is not a TTY and --yes was not given — NOT writing the identity gate."
    info "verify the ids above are yours, then re-run: telegram-capture-chat-id.sh --write --yes"
  fi
  if [ "$confirmed" -eq 1 ]; then
    if [ -n "$CAPTAIN_ID" ]; then
      fill_if_empty "CAPTAIN_TELEGRAM_ID" "$CAPTAIN_ID"
    fi
    if [ -n "$GROUP_ID" ]; then
      fill_if_empty "TELEGRAM_HQ_CHAT_ID" "$GROUP_ID"
    fi
  fi
else
  echo ""
  info "re-run with --write to fill CAPTAIN_TELEGRAM_ID / TELEGRAM_HQ_CHAT_ID in cabinet/.env (empty keys only; confirms on a TTY, --yes for non-interactive)"
fi
exit 0
