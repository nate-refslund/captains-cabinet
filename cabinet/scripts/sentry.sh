#!/usr/bin/env bash
# sentry.sh — Sentry query helper for Cabinet officers (esp. a product CEO).
#
# Lets officers investigate production errors in Sentry directly, without a
# Sentry MCP. Officers are hook-blocked from reading cabinet/.env, but they
# CAN run this script, which sources the token internally (same pattern as
# advisor-crew.sh). The SENTRY_AUTH_TOKEN (a `sntryu_` user token) never
# appears in output — not in errors, usage, or curl traces.
#
# Usage:
#   sentry.sh issues <project> [query]   List unresolved issues.
#   sentry.sh event  <issue-id>          Latest event for an issue:
#                                        exception, failing/asset URL, release,
#                                        environment, tags.
#   sentry.sh --help
#
# Options / env:
#   --org <slug>        Override org (default: SENTRY_ORG from env or cabinet/.env).
#   SENTRY_AUTH_TOKEN   User token; auto-loaded from cabinet/.env if unset.
#   SENTRY_ORG          Default org slug.
#   SENTRY_STATS_PERIOD Stats window for `issues` (default: 14d).
#
# Examples:
#   sentry.sh issues sentry-step-acme
#   sentry.sh issues sentry-step-acme "Unexpected token"
#   sentry.sh event 11857079

set -euo pipefail

CABINET_DIR="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
# R110: org is instance data — env wins, then cabinet/.env (SENTRY_ORG or
# CABINET_SENTRY_ORG), no launcher default. Empty + no --org = clear error below.
DEFAULT_ORG="${SENTRY_ORG:-}"
if [ -z "$DEFAULT_ORG" ] && [ -f "$CABINET_DIR/cabinet/.env" ]; then
  DEFAULT_ORG="$(grep '^SENTRY_ORG=' "$CABINET_DIR/cabinet/.env" | cut -d= -f2-)"
  [ -n "$DEFAULT_ORG" ] || DEFAULT_ORG="$(grep '^CABINET_SENTRY_ORG=' "$CABINET_DIR/cabinet/.env" | cut -d= -f2-)"
fi
STATS_PERIOD="${SENTRY_STATS_PERIOD:-14d}"
API_BASE="https://sentry.io/api/0"

# ────────────────────────────────────────────────────────────
# Help
# ────────────────────────────────────────────────────────────
usage() {
  sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ────────────────────────────────────────────────────────────
# Parse --org (anywhere) out of the args, keep the rest positional
# ────────────────────────────────────────────────────────────
ORG="$DEFAULT_ORG"
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --org)   ORG="${2:?--org requires a slug}"; shift 2 ;;
    --org=*) ORG="${1#--org=}"; shift ;;
    -h|--help|help) usage; exit 0 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
set -- "${ARGS[@]:-}"

if [ -z "$ORG" ]; then
  echo "sentry.sh: no org configured — pass --org <slug> or set SENTRY_ORG (env or cabinet/.env)" >&2
  exit 1
fi

SUBCMD="${1:-}"
if [ -z "$SUBCMD" ]; then
  usage
  exit 2
fi

# ────────────────────────────────────────────────────────────
# Dependencies
# ────────────────────────────────────────────────────────────
for bin in curl jq; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: '$bin' is required but not installed." >&2
    exit 3
  fi
done

# ────────────────────────────────────────────────────────────
# Load token from cabinet/.env if not already in the environment.
# The token is NEVER echoed — only used as a curl header.
# ────────────────────────────────────────────────────────────
if [ -z "${SENTRY_AUTH_TOKEN:-}" ] && [ -f "$CABINET_DIR/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$CABINET_DIR/cabinet/.env"
  set +a
fi

if [ -z "${SENTRY_AUTH_TOKEN:-}" ]; then
  echo "ERROR: SENTRY_AUTH_TOKEN is not set and could not be loaded from" >&2
  echo "       $CABINET_DIR/cabinet/.env" >&2
  echo "       Add a 'sntryu_' user token there as SENTRY_AUTH_TOKEN=..." >&2
  exit 4
fi

# ────────────────────────────────────────────────────────────
# sentry_get <path-with-leading-slash> [query-string]
# Performs an authenticated GET, separating body from HTTP status.
# On auth/other failure, prints guidance WITHOUT leaking the token.
# Echoes the JSON body on success.
# ────────────────────────────────────────────────────────────
sentry_get() {
  local path="$1" qs="${2:-}" url body code
  url="${API_BASE}${path}"
  [ -n "$qs" ] && url="${url}?${qs}"

  body="$(mktemp)"
  # -sS quiet but show errors; capture status separately so the token in the
  # Authorization header is never surfaced via -v.
  code="$(curl -sS -o "$body" -w '%{http_code}' \
    -H "Authorization: Bearer ${SENTRY_AUTH_TOKEN}" \
    -H "Accept: application/json" \
    "$url" || echo "000")"

  case "$code" in
    200)
      cat "$body"
      rm -f "$body"
      return 0
      ;;
    401|403)
      echo "ERROR: Sentry returned HTTP $code (token expired or unauthorized)." >&2
      echo "       Refresh the SENTRY_AUTH_TOKEN ('sntryu_' user token) in cabinet/.env." >&2
      ;;
    404)
      echo "ERROR: Sentry returned HTTP 404 (not found): ${path}" >&2
      echo "       Check the org/project slug or issue id." >&2
      ;;
    000)
      echo "ERROR: could not reach sentry.io (network error)." >&2
      ;;
    *)
      echo "ERROR: Sentry returned HTTP $code for ${path}" >&2
      # Surface a short message from the body if present (no token in body).
      jq -r '.detail // .error // empty' "$body" 2>/dev/null | head -3 >&2 || true
      ;;
  esac
  rm -f "$body"
  return 1
}

# ────────────────────────────────────────────────────────────
# Subcommand: issues <project> [query]
# ────────────────────────────────────────────────────────────
cmd_issues() {
  local project="${1:?Usage: sentry.sh issues <project> [query]}"
  local query="${2:-}"

  # Default to unresolved; append the user's free-text query if given.
  local search="is:unresolved"
  [ -n "$query" ] && search="is:unresolved ${query}"

  # URL-encode the query and statsPeriod.
  local q_enc period_enc
  q_enc="$(jq -rn --arg q "$search" '$q|@uri')"
  period_enc="$(jq -rn --arg p "$STATS_PERIOD" '$p|@uri')"

  local json
  json="$(sentry_get "/projects/${ORG}/${project}/issues/" \
    "query=${q_enc}&statsPeriod=${period_enc}&limit=25")" || return 1

  local n
  n="$(printf '%s' "$json" | jq 'length')"
  if [ "$n" -eq 0 ]; then
    echo "No unresolved issues for ${ORG}/${project}${query:+ matching \"$query\"} (last ${STATS_PERIOD})."
    return 0
  fi

  echo "Unresolved issues — ${ORG}/${project}${query:+ · query: \"$query\"} (last ${STATS_PERIOD}):"
  echo
  printf '%s' "$json" | jq -r '
    .[] |
    "● [\(.shortId // "—")]  id=\(.id)\n" +
    "    \(.title // .metadata.value // "(no title)")\n" +
    "    events=\(.count // "?")  users=\(.userCount // 0)  lastSeen=\(.lastSeen // "?")\n" +
    "    culprit: \(.culprit // "—")\n"
  '
}

# ────────────────────────────────────────────────────────────
# Subcommand: event <issue-id>
# ────────────────────────────────────────────────────────────
cmd_event() {
  local issue="${1:?Usage: sentry.sh event <issue-id>}"

  # Org-scoped issue path — the bare /issues/<id>/ path 404s for org tokens.
  local json
  json="$(sentry_get "/organizations/${ORG}/issues/${issue}/events/latest/")" || return 1

  printf '%s' "$json" | jq -r '
    "Latest event — issue \(.groupID // "'"$issue"'")  event \(.eventID // .id // "?")\n" +
    "title:       \(.title // .message // "—")\n" +
    "datetime:    \(.dateReceived // .dateCreated // "—")\n" +
    "release:     \((.release.version // .release // (.tags[]? | select(.key=="release") | .value)) // "—")\n" +
    "environment: \(((.tags[]? | select(.key=="environment") | .value)) // "—")\n"
  '

  # Exception type + value (entries[type==exception]).
  echo
  echo "exception:"
  printf '%s' "$json" | jq -r '
    [.entries[]? | select(.type=="exception") | .data.values[]?] as $ex
    | if ($ex | length) > 0
      then ($ex[] | "  \(.type // "Error"): \(.value // "")")
      else "  (none reported)"
      end
  '

  # Failing / asset URL — request URL + stack-frame paths (this is where the
  # CSS-served-as-script SyntaxError surfaces the offending asset URL).
  # Prefer the request entry; fall back to the `url` tag only if absent.
  echo
  echo "request URL:"
  printf '%s' "$json" | jq -r '
    ((.entries[]? | select(.type=="request") | .data.url)
       // (.tags[]? | select(.key=="url") | .value)
       // "") as $u
    | if $u == "" then "  —" else "  \($u)" end
  ' | head -1

  echo
  echo "stack frames (asset/source paths, innermost last):"
  printf '%s' "$json" | jq -r '
    [.entries[]? | select(.type=="exception") | .data.values[]? | .stacktrace?.frames[]?]
    | if length == 0 then "  (no stack frames)"
      else (.[] | "  \(.filename // .absPath // .module // "?")" +
                  (if .lineNo then ":\(.lineNo)" else "" end) +
                  (if .function and .function != "" then "  — \(.function)" else "" end))
      end
  '

  # Key tags for quick triage.
  echo
  echo "tags:"
  printf '%s' "$json" | jq -r '
    if (.tags? | length // 0) > 0
    then (.tags[] | "  \(.key)=\(.value)")
    else "  (none)"
    end
  '
}

# ────────────────────────────────────────────────────────────
# Dispatch
# ────────────────────────────────────────────────────────────
case "$SUBCMD" in
  issues) shift; cmd_issues "$@" ;;
  event)  shift; cmd_event  "$@" ;;
  *)
    echo "ERROR: unknown subcommand '$SUBCMD'." >&2
    echo >&2
    usage >&2
    exit 2
    ;;
esac
