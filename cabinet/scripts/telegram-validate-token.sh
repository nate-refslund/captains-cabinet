#!/bin/bash
# telegram-validate-token.sh — live getMe validation for a Telegram bot token.
#
# Errand E1 validator (docs/plans/world-onboarding-hatching-2026-07-09.md §3):
# confirms a pasted bot token actually works by calling the FIXED host
# https://api.telegram.org (the only egress) and reporting the bot USERNAME —
# never the token. Called by setup-env.sh after a TELEGRAM_*_TOKEN paste;
# safe to run standalone.
#
# Token handling (values-in-env doctrine):
#   telegram-validate-token.sh [--env VAR_NAME]
#     Reads the token from the environment variable VAR_NAME (default
#     TELEGRAM_COS_TOKEN), falling back to that key's value in the
#     gitignored cabinet/.env. The token is NEVER accepted as a positional
#     argument (argv leaks via ps), never echoed, never logged; as a belt,
#     all curl/output text is scrubbed of /bot<token> path segments before
#     re-emission.
#
# Exit codes:
#   0  token valid — prints "bot username: @..."
#   1  Telegram rejected the token (getMe ok:false)
#   2  could not reach api.telegram.org (network down / curl missing /
#      unparseable response)
#   64 usage error / no token found
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Script lives at cabinet/scripts/, so repo root is TWO levels up (R4/R5 pattern).
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ENV_FILE="$CABINET_ROOT/cabinet/.env"

VAR_NAME="TELEGRAM_COS_TOKEN"
while [ $# -gt 0 ]; do
  case "$1" in
    --env)
      [ $# -ge 2 ] || { echo "telegram-validate-token: --env needs a variable NAME" >&2; exit 64; }
      VAR_NAME="$2"; shift 2 ;;
    # Self-maintaining help: print the leading comment block only (a numeric
    # sed range drifts when the header grows and leaks code lines).
    --help|-h) awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"; exit 0 ;;
    *) echo "telegram-validate-token: unknown arg: $1 (tokens are never argv — use --env VAR_NAME)" >&2; exit 64 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }

# Belt: strip /bot<anything> path segments from any text we re-emit.
scrub() { sed -E 's|/bot[^/[:space:]"]+|/bot***REDACTED***|g'; }

# Variable NAME must be a sane env identifier before indirect expansion.
if ! printf '%s' "$VAR_NAME" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]*$'; then
  echo "telegram-validate-token: invalid variable name: $VAR_NAME" >&2
  exit 64
fi

TOKEN="${!VAR_NAME:-}"
if [ -z "$TOKEN" ] && [ -f "$ENV_FILE" ]; then
  TOKEN="$(grep -E "^${VAR_NAME}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  # strip optional surrounding quotes
  TOKEN="${TOKEN%\"}"; TOKEN="${TOKEN#\"}"
fi
if [ -z "$TOKEN" ]; then
  fail "no token in \$$VAR_NAME or cabinet/.env ($VAR_NAME=) — nothing to validate"
  exit 64
fi

if ! command -v curl >/dev/null 2>&1; then
  fail "curl not found — cannot reach api.telegram.org"
  exit 2
fi

BODY="$(mktemp)"; ERRF="$(mktemp)"
cleanup() { rm -f "$BODY" "$ERRF"; }
trap cleanup EXIT

# The URL rides a curl config on STDIN so the token never appears in argv.
# Fixed host api.telegram.org — the only egress this script can make.
currc=0
HTTP_CODE="$(printf 'url = "https://api.telegram.org/bot%s/getMe"\n' "$TOKEN" \
  | curl -sS --max-time 10 -K - -o "$BODY" -w '%{http_code}' 2>"$ERRF")" || currc=$?

if [ "$currc" -ne 0 ] || [ -z "$HTTP_CODE" ] || [ "$HTTP_CODE" = "000" ]; then
  fail "could not reach api.telegram.org (curl exit $currc)"
  scrub < "$ERRF" | sed 's/^/    /' >&2
  exit 2
fi

# Telegram answers JSON on success AND on auth failure ({"ok":false,...}).
# Parse with fixed argv (the only argument is the mktemp body path — never
# the token); the response body never contains the token.
PARSED="$(python3 - "$BODY" 2>/dev/null <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        d = json.load(fh)
except Exception:
    print("PARSE_ERROR")
    raise SystemExit(0)
if d.get("ok") is True and isinstance(d.get("result"), dict):
    print("VALID\t" + str(d["result"].get("username", "")))
else:
    print("REJECTED\t" + str(d.get("description", "no description")))
PY
)" || PARSED="PARSE_ERROR"

TAB="$(printf '\t')"
STATUS="${PARSED%%${TAB}*}"
DETAIL="${PARSED#*${TAB}}"
case "$STATUS" in
  VALID)
    if [ -n "$DETAIL" ]; then
      ok "token valid — bot username: @$DETAIL"
    else
      ok "token valid (Telegram returned no username)"
    fi
    exit 0
    ;;
  REJECTED)
    fail "Telegram rejected the token (HTTP $HTTP_CODE): $(printf '%s' "$DETAIL" | scrub)"
    exit 1
    ;;
  *)
    fail "unexpected response from api.telegram.org (HTTP $HTTP_CODE, unparseable body)"
    exit 2
    ;;
esac
