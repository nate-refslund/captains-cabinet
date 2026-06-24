#!/usr/bin/env bash
# vercel.sh — Vercel query helper for Cabinet officers (esp. the PolAds CEO).
#
# Lets officers verify deployments and diagnose log-drains directly, without a
# Vercel MCP (the per-officer MCP token can go stale / 403). Officers are
# hook-blocked from reading cabinet/.env, but they CAN run this script, which
# sources the token internally (same pattern as sentry.sh / advisor-crew.sh).
# The VERCEL_TOKEN never appears in output — not in errors, usage, or traces.
#
# Usage:
#   vercel.sh deployments <project> [limit]  Recent deployments for a project:
#                                            state, url, target (prod/preview),
#                                            createdAt, branch + commit.
#   vercel.sh deployment  <id>               One deployment's readyState, url,
#                                            target, and any build error.
#   vercel.sh logdrains                      Configured log-drains (status,
#                                            destination URL, sources, envs) —
#                                            diagnose the failing PolAds drain.
#   vercel.sh --help
#
# Options / env:
#   --team <id>     Override team (default: VERCEL_TEAM_ID or the step-network
#                   team team_FEdAEOgfT3WhQ9c1moxCpO2s).
#   VERCEL_TOKEN    API token; auto-loaded from cabinet/.env if unset
#                   (VERCEL_API_KEY also accepted as a fallback name).
#   VERCEL_TEAM_ID  Default team id.
#
# Examples:
#   vercel.sh deployments v0-politiske-annoncer
#   vercel.sh deployments v0-politiske-annoncer 5
#   vercel.sh deployment dpl_9Wuk7JFEMTP6EmyyTtvufwuc4EcS
#   vercel.sh logdrains

set -euo pipefail

CABINET_DIR="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DEFAULT_TEAM="${VERCEL_TEAM_ID:-team_FEdAEOgfT3WhQ9c1moxCpO2s}"
API_BASE="https://api.vercel.com"

# ────────────────────────────────────────────────────────────
# Help
# ────────────────────────────────────────────────────────────
usage() {
  sed -n '2,27p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ────────────────────────────────────────────────────────────
# Parse --team (anywhere) out of the args, keep the rest positional
# ────────────────────────────────────────────────────────────
TEAM="$DEFAULT_TEAM"
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --team)   TEAM="${2:?--team requires an id}"; shift 2 ;;
    --team=*) TEAM="${1#--team=}"; shift ;;
    -h|--help|help) usage; exit 0 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
set -- "${ARGS[@]:-}"

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
# Accept VERCEL_TOKEN, fall back to VERCEL_API_KEY. The token is NEVER
# echoed — only used as a curl Authorization header.
# ────────────────────────────────────────────────────────────
if [ -z "${VERCEL_TOKEN:-}" ] && [ -f "$CABINET_DIR/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$CABINET_DIR/cabinet/.env"
  set +a
fi
# Allow VERCEL_API_KEY as an alternate name for the same token.
VERCEL_TOKEN="${VERCEL_TOKEN:-${VERCEL_API_KEY:-}}"

if [ -z "${VERCEL_TOKEN:-}" ]; then
  echo "ERROR: VERCEL_TOKEN is not set and could not be loaded from" >&2
  echo "       $CABINET_DIR/cabinet/.env" >&2
  echo "       Add a Vercel API token there as VERCEL_TOKEN=... (or VERCEL_API_KEY=...)." >&2
  exit 4
fi

# ────────────────────────────────────────────────────────────
# vercel_get <path-with-leading-slash> [extra-query-string]
# Authenticated GET that always carries teamId. Separates body from HTTP
# status so the bearer token (in the Authorization header) is never surfaced.
# On auth/other failure, prints guidance WITHOUT leaking the token.
# Echoes the JSON body on success.
# ────────────────────────────────────────────────────────────
vercel_get() {
  local path="$1" qs="${2:-}" url body code
  url="${API_BASE}${path}"
  # Always scope to the team; append any caller query after it.
  url="${url}?teamId=${TEAM}"
  [ -n "$qs" ] && url="${url}&${qs}"

  body="$(mktemp)"
  code="$(curl -sS -o "$body" -w '%{http_code}' \
    -H "Authorization: Bearer ${VERCEL_TOKEN}" \
    -H "Accept: application/json" \
    "$url" || echo "000")"

  case "$code" in
    200)
      cat "$body"
      rm -f "$body"
      return 0
      ;;
    401|403)
      echo "ERROR: Vercel returned HTTP $code (token expired or unauthorized) — the token may need refreshing." >&2
      echo "       Refresh the VERCEL_TOKEN in cabinet/.env (a working token authenticates as the step-network team)." >&2
      ;;
    404)
      echo "ERROR: Vercel returned HTTP 404 (not found): ${path}" >&2
      echo "       Check the project name, deployment id, or --team id." >&2
      ;;
    000)
      echo "ERROR: could not reach api.vercel.com (network error)." >&2
      ;;
    *)
      echo "ERROR: Vercel returned HTTP $code for ${path}" >&2
      # Surface a short message from the body if present (Vercel errors carry
      # no token; .error.message is the standard envelope field).
      jq -r '.error.message // .message // .error // empty' "$body" 2>/dev/null | head -3 >&2 || true
      ;;
  esac
  rm -f "$body"
  return 1
}

# Render an epoch-millis timestamp as a readable UTC string (— if absent/0).
# Pure jq helper string, reused inside the projections below.
read -r -d '' TS_FMT <<'JQ' || true
def ts(ms): if (ms // 0) > 0 then ((ms/1000) | strftime("%Y-%m-%dT%H:%M:%SZ")) else "—" end;
JQ

# ────────────────────────────────────────────────────────────
# Subcommand: deployments <project> [limit]
# ────────────────────────────────────────────────────────────
cmd_deployments() {
  local project="${1:?Usage: vercel.sh deployments <project> [limit]}"
  local limit="${2:-10}"

  # Validate limit is a positive integer (Vercel rejects non-numerics).
  case "$limit" in
    ''|*[!0-9]*) echo "ERROR: limit must be a positive integer (got '$limit')." >&2; exit 2 ;;
  esac

  local p_enc json
  p_enc="$(jq -rn --arg p "$project" '$p|@uri')"
  json="$(vercel_get "/v6/deployments" "app=${p_enc}&limit=${limit}")" || return 1

  local n
  n="$(printf '%s' "$json" | jq '.deployments | length')"
  if [ "$n" -eq 0 ]; then
    echo "No deployments found for project '${project}' on team ${TEAM}."
    echo "(Check the project name — list via the dashboard or another helper.)"
    return 0
  fi

  echo "Recent deployments — ${project} (team ${TEAM}, latest ${n}):"
  echo
  printf '%s' "$json" | jq -r "
    ${TS_FMT}
    .deployments[] |
    \"● \(.readyState // .state // \"?\")  \(.url // \"—\")\n\" +
    \"    target: \((.target // \"preview\"))   created: \(ts(.createdAt // .created))\n\" +
    \"    id: \(.uid // .id // \"?\")\n\" +
    \"    branch: \((.meta.githubCommitRef // .meta.branch // \"—\"))   commit: \((.meta.githubCommitSha // \"—\")[0:9])\n\" +
    \"    msg: \(((.meta.githubCommitMessage // \"\") | split(\"\n\")[0] // \"—\"))\n\"
  "
}

# ────────────────────────────────────────────────────────────
# Subcommand: deployment <id>
# ────────────────────────────────────────────────────────────
cmd_deployment() {
  local id="${1:?Usage: vercel.sh deployment <id>}"

  local id_enc json
  id_enc="$(jq -rn --arg i "$id" '$i|@uri')"
  json="$(vercel_get "/v13/deployments/${id_enc}")" || return 1

  printf '%s' "$json" | jq -r "
    ${TS_FMT}
    \"Deployment \(.id // .uid // \"${id}\")\n\" +
    \"readyState:  \(.readyState // .status // \"—\")\n\" +
    \"state:       \(.state // \"—\")\n\" +
    \"url:         \(.url // \"—\")\n\" +
    \"target:      \((.target // \"preview\"))\n\" +
    \"created:     \(ts(.createdAt // .created))\n\" +
    \"branch:      \((.gitSource.ref // .meta.githubCommitRef // .meta.branch // \"—\"))\n\" +
    \"commit:      \((.meta.githubCommitSha // \"—\")[0:9])\n\" +
    \"inspector:   \(.inspectorUrl // \"—\")\n\"
  "

  # Surface any build / deploy error explicitly (this is the deploy-verify
  # payoff: a FAILED/ERROR deployment carries errorCode + errorMessage).
  echo
  echo "error:"
  printf '%s' "$json" | jq -r '
    if (.errorCode // .errorMessage // .aliasError) != null
    then "  code:    \(.errorCode // (.aliasError.code) // "—")\n" +
         "  message: \(.errorMessage // (.aliasError.message) // "—")"
    else "  (none — deployment reports no error)"
    end
  '
}

# ────────────────────────────────────────────────────────────
# Subcommand: logdrains
# Lists configured log-drains so the CEO can see/diagnose the failing PolAds
# drain. NEVER prints the drain's secret headers (x-sentry-auth etc.).
# ────────────────────────────────────────────────────────────
cmd_logdrains() {
  # v1 carries the per-drain `status` field (enabled/disabled/errored) that the
  # integration (v2) listing omits — that status is the whole point of a
  # diagnosis, so v1 is primary.
  local json
  json="$(vercel_get "/v1/log-drains")" || return 1

  local n
  n="$(printf '%s' "$json" | jq 'if type=="array" then length else 0 end')"
  if [ "$n" -eq 0 ]; then
    echo "No log-drains configured on team ${TEAM}."
    return 0
  fi

  echo "Log-drains — team ${TEAM} (${n}):"
  echo
  # Whitelist only safe fields; the secret `headers` map is deliberately
  # never emitted.
  printf '%s' "$json" | jq -r "
    ${TS_FMT}
    .[] |
    \"● \(.name // \"(unnamed)\")  id=\(.id // \"—\")\n\" +
    \"    status:   \(.status // \"—\")\n\" +
    \"    url:      \(.url // \"—\")\n\" +
    \"    format:   \(.deliveryFormat // \"—\")\n\" +
    \"    sources:  \(((.sources // []) | join(\", \")) // \"—\")\n\" +
    \"    envs:     \(((.environments // []) | join(\", \")) // \"all\")\n\" +
    \"    projects: \(((.projectIds // []) | length)) project(s)\n\" +
    \"    created:  \(ts(.createdAt))   from: \(.createdFrom // \"—\")\n\"
  "
}

# ────────────────────────────────────────────────────────────
# Dispatch
# ────────────────────────────────────────────────────────────
case "$SUBCMD" in
  deployments) shift; cmd_deployments "$@" ;;
  deployment)  shift; cmd_deployment  "$@" ;;
  logdrains)   shift; cmd_logdrains   "$@" ;;
  *)
    echo "ERROR: unknown subcommand '$SUBCMD'." >&2
    echo >&2
    usage >&2
    exit 2
    ;;
esac
