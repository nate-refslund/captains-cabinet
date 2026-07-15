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
#   vercel.sh promote <project> <deployment-id>
#                                            Promote a READY deployment to
#                                            production (flips every prod alias,
#                                            e.g. polads.eu, to it), then polls
#                                            until the alias flip completes.
#                                            Idempotent: re-promoting the current
#                                            prod deployment is reported as a
#                                            no-op, not an error.
#   vercel.sh --help
#
# Options / env:
#   --team <id>     Override team (default: $VERCEL_TEAM_ID; there is no
#                   built-in default team — every deployment configures its
#                   own via VERCEL_TEAM_ID or --team).
#   VERCEL_TOKEN    API token; auto-loaded from cabinet/.env if unset
#                   (VERCEL_API_KEY also accepted as a fallback name).
#   VERCEL_TEAM_ID  Default team id.
#
# Examples:
#   vercel.sh deployments v0-politiske-annoncer
#   vercel.sh deployments v0-politiske-annoncer 5
#   vercel.sh deployment dpl_9Wuk7JFEMTP6EmyyTtvufwuc4EcS
#   vercel.sh promote v0-politiske-annoncer dpl_7hw2FBowFPhHRmHTagSWD4WRdetj
#   vercel.sh logdrains

set -euo pipefail

CABINET_DIR="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
# No built-in default team id (framework/cabinet code stays deployment-
# agnostic — see framework/probes/probe_vercel.py's identical env-only
# resolution). Every deployment must configure its own via VERCEL_TEAM_ID
# (env or cabinet/.env) or --team; absence is caught explicitly below.
DEFAULT_TEAM="${VERCEL_TEAM_ID:-}"
API_BASE="https://api.vercel.com"

# ────────────────────────────────────────────────────────────
# Help
# ────────────────────────────────────────────────────────────
usage() {
  sed -n '2,41p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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

if [ -z "${TEAM:-}" ]; then
  echo "ERROR: no Vercel team id configured." >&2
  echo "       Set VERCEL_TEAM_ID (env or cabinet/.env) or pass --team <id>." >&2
  exit 5
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

# ────────────────────────────────────────────────────────────
# vercel_post <path-with-leading-slash> [json-body] [extra-query-string]
# Authenticated POST that always carries teamId. Same token-safety contract as
# vercel_get: the bearer (Authorization header) is never surfaced — on failure
# we print guidance + the body's error message, neither of which carries it.
# Captures the HTTP status into the global VERCEL_POST_CODE so the caller can
# distinguish an idempotent 409 (already-promoted) from a real failure.
# Echoes the JSON body on 2xx; returns non-zero on any non-2xx.
# ────────────────────────────────────────────────────────────
VERCEL_POST_CODE=""
vercel_post() {
  local path="$1" data="${2:-{\}}" qs="${3:-}" url body code
  url="${API_BASE}${path}?teamId=${TEAM}"
  [ -n "$qs" ] && url="${url}&${qs}"

  body="$(mktemp)"
  code="$(curl -sS -o "$body" -w '%{http_code}' -X POST \
    -H "Authorization: Bearer ${VERCEL_TOKEN}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "$data" \
    "$url" || echo "000")"
  VERCEL_POST_CODE="$code"

  case "$code" in
    2??)
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
      echo "       Check the project id, deployment id, or --team id." >&2
      ;;
    000)
      echo "ERROR: could not reach api.vercel.com (network error)." >&2
      ;;
    *)
      echo "ERROR: Vercel returned HTTP $code for POST ${path}" >&2
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
# Subcommand: promote <project> <deployment-id>
# Flips the production alias(es) (polads.eu et al.) to a READY deployment.
#
# Vercel's promote API keys on the project's prj_ id (not the slug), so we
# resolve it first. We then refuse to promote anything that is not READY — a
# half-built deployment must never become production. The promote itself is
# POST /v10/projects/<prj>/promote/<dpl>; a 409 "already the current production
# deployment" is treated as success (idempotent), not failure. Finally we poll
# the promote-aliases status until every alias flip reports completed/succeeded.
# ────────────────────────────────────────────────────────────
cmd_promote() {
  local project="${1:?Usage: vercel.sh promote <project> <deployment-id>}"
  local dep="${2:?Usage: vercel.sh promote <project> <deployment-id>}"

  # 1) Resolve project slug -> prj_ id (the promote endpoint needs the id).
  local p_enc proj_json proj_id
  p_enc="$(jq -rn --arg p "$project" '$p|@uri')"
  proj_json="$(vercel_get "/v9/projects/${p_enc}")" || return 1
  proj_id="$(printf '%s' "$proj_json" | jq -r '.id // empty')"
  if [ -z "$proj_id" ]; then
    echo "ERROR: could not resolve a project id for '${project}'." >&2
    return 1
  fi

  # 2) Fetch the target deployment; verify it is READY before promoting.
  local dep_enc dep_json ready target sha ref msg
  dep_enc="$(jq -rn --arg i "$dep" '$i|@uri')"
  dep_json="$(vercel_get "/v13/deployments/${dep_enc}")" || return 1
  ready="$(printf '%s' "$dep_json" | jq -r '.readyState // .status // "UNKNOWN"')"
  target="$(printf '%s' "$dep_json" | jq -r '.target // "preview"')"
  sha="$(printf '%s' "$dep_json" | jq -r '(.meta.githubCommitSha // "—")[0:9]')"
  ref="$(printf '%s' "$dep_json" | jq -r '.meta.githubCommitRef // .gitSource.ref // "—"')"
  msg="$(printf '%s' "$dep_json" | jq -r '(.meta.githubCommitMessage // "" | split("\n")[0]) // "—"')"

  echo "Promote target — ${project}:"
  echo "  deployment: ${dep}"
  echo "  readyState: ${ready}    current target: ${target}"
  echo "  branch:     ${ref}    commit: ${sha}"
  echo "  msg:        ${msg}"
  echo

  if [ "$ready" != "READY" ]; then
    echo "ERROR: refusing to promote — deployment is '${ready}', not READY." >&2
    echo "       Only a fully-built READY deployment may become production." >&2
    return 1
  fi

  # 3) Promote. Treat 409 'already current production' as an idempotent success.
  # We swallow vercel_post's own stderr here: for a 409 it would read like a
  # failure, but cmd_promote owns the 409→no-op messaging. On a genuine failure
  # we re-run once WITHOUT suppression so the real error message reaches the CEO.
  echo "Promoting ${dep} to production on project ${proj_id}…"
  if vercel_post "/v10/projects/${proj_id}/promote/${dep_enc}" '{}' >/dev/null 2>&1; then
    echo "  → promote request accepted (HTTP ${VERCEL_POST_CODE}); alias flip in progress."
  elif [ "$VERCEL_POST_CODE" = "409" ]; then
    echo "  → already the current production deployment — nothing to flip (idempotent no-op)."
    echo
    echo "Production alias already points to ${dep}. Done."
    return 0
  else
    echo "ERROR: promote failed — Vercel returned HTTP ${VERCEL_POST_CODE}:" >&2
    # Re-issue once with stderr visible so the CEO sees Vercel's exact reason.
    vercel_post "/v10/projects/${proj_id}/promote/${dep_enc}" '{}' >/dev/null || true
    return 1
  fi

  # 4) Poll the alias-flip status until every alias completes (or we time out).
  echo
  echo "Waiting for production aliases to flip…"
  local i status_json pending
  for i in $(seq 1 20); do
    sleep 3
    status_json="$(vercel_get "/v1/projects/${proj_id}/promote/aliases")" || break
    # Count aliases not yet in a terminal-success state.
    pending="$(printf '%s' "$status_json" | jq '[.aliases[]? | select((.status // "") as $s | ($s != "completed" and $s != "succeeded"))] | length')"
    if [ "${pending:-1}" -eq 0 ]; then
      echo "  → all production aliases flipped:"
      printf '%s' "$status_json" | jq -r '.aliases[]? | "      \(.status)  \(.alias)"'
      echo
      echo "Promotion complete. Production now serves ${dep} (${ref} @ ${sha})."
      return 0
    fi
  done

  echo "  ⚠ alias flip still settling after the poll window — check the dashboard." >&2
  printf '%s' "${status_json:-}" | jq -r '.aliases[]? | "      \(.status)  \(.alias)"' 2>/dev/null || true
  return 0
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
  promote)     shift; cmd_promote     "$@" ;;
  logdrains)   shift; cmd_logdrains   "$@" ;;
  *)
    echo "ERROR: unknown subcommand '$SUBCMD'." >&2
    echo >&2
    usage >&2
    exit 2
    ;;
esac
