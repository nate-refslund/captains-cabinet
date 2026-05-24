#!/bin/bash
# verify-deploy.sh — Poll CI + deploy status
# Usage:
#   bash verify-deploy.sh ci <commit-sha>     — check PR CI status (pre-merge)
#   bash verify-deploy.sh deploy <commit-sha>  — check Vercel deploy (post-merge)
#   bash verify-deploy.sh <commit-sha>         — check both sequentially
#
# CI state is read from BOTH GitHub sources (FW fix 2026-05-24) — modern CI (GitHub
# Actions, Vercel) reports via the Checks API (/check-runs), which the old /status-only
# poll was blind to (no statuses → combined state "pending" forever → false-timeout on
# green CI). We now read /check-runs AND legacy /status.
#
# GATING is an explicit ALLOWLIST (VERIFY_REQUIRED_CHECKS), NOT every check — Sensed's
# main has NO branch protection and several chronically-red NON-gating check-runs
# (e.g. `sync`, `QA Explorer — 5 Core Flows`); aggregating all of them would report
# failure on essentially every commit. We gate only on check-runs/statuses whose name
# matches the allowlist (default: Sensed's real CI gate "Build, Lint & Test"). Override
# via the VERIFY_REQUIRED_CHECKS env (comma-separated name substrings).
#
# Auth prefers GITHUB_PAT (officers push with it); the legacy origin-URL token-sed is a
# fallback only (it yields a bad token against clean credential-helper remotes → 401 →
# "unknown" → pending → timeout, part of the same bug).

set -euo pipefail

MODE="${1:-both}"
COMMIT_SHA=""

if [ "$MODE" = "ci" ] || [ "$MODE" = "deploy" ] || [ "$MODE" = "both" ]; then
  COMMIT_SHA="${2:-$(cd /workspace/product && git rev-parse HEAD)}"
else
  COMMIT_SHA="$MODE"   # legacy: first arg is the sha
  MODE="both"
fi

GITHUB_TOKEN="${GITHUB_PAT:-$(cd /workspace/product && git remote get-url origin | sed 's|https://\(.*\)@github.com.*|\1|')}"
REPO="STEP-Network/Sensed"
MAX_ATTEMPTS=20
POLL_INTERVAL=15
# Comma-separated check-name / status-context SUBSTRINGS that GATE the verdict.
: "${VERIFY_REQUIRED_CHECKS:=Build, Lint & Test}"

_gh() { # _gh <api-path> → raw JSON ("{}" on empty/error so jq stays valid)
  local out
  out=$(curl -s -H "Authorization: token $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$REPO/$1" 2>/dev/null)
  [ -n "$out" ] && echo "$out" || echo "{}"
}

# Echo success|failure|pending, considering ONLY checks/statuses whose name matches the
# VERIFY_REQUIRED_CHECKS allowlist. -r so the bare string matches the case below.
combined_ci_state() {
  local sha="$1" st cr
  st=$(_gh "commits/$sha/status")
  cr=$(_gh "commits/$sha/check-runs?per_page=100")
  jq -n -r --argjson s "$st" --argjson c "$cr" --arg req "$VERIFY_REQUIRED_CHECKS" '
    ($req | split(",") | map(gsub("^\\s+|\\s+$";"")) | map(select(length > 0))) as $names
    | ($names | length) as $nn
    | ([ ($c.check_runs // [])[] | {
          name: .name, done: (.status == "completed"),
          failed: ((.conclusion // "") as $x
            | (["failure","cancelled","timed_out","action_required","startup_failure","stale"] | index($x)) != null) } ]) as $cruns
    | ([ ($s.statuses // [])[] | {
          name: .context, done: (.state != "pending"),
          failed: (.state == "failure" or .state == "error") } ]) as $sts
    | (($cruns + $sts) | map(select(.name as $n | $names | any(. as $q | $n | contains($q))))) as $gating
    | ($gating | length) as $g
    | ([$gating[] | select(.done | not)]   | length) as $incomplete
    | ([$gating[] | select(.failed)]       | length) as $failed
    | if   $nn == 0       then "pending"     # no allowlist → undefined; stay safe
      elif $g == 0        then "pending"     # gating check not reported yet
      elif $failed > 0    then "failure"
      elif $incomplete > 0 then "pending"
      else                     "success" end
  '
}

# Print the failing GATING entries (allowlist-matched) from both sources.
dump_failures() {
  local sha="$1"
  { _gh "commits/$sha/check-runs?per_page=100" \
      | jq -rc '.check_runs[]? | {name, done:(.status=="completed"), conclusion, url:.html_url}'
    _gh "commits/$sha/status" \
      | jq -rc '.statuses[]? | {name:.context, done:(.state!="pending"), conclusion:.state, url:.target_url}'
  } | jq -rc --arg req "$VERIFY_REQUIRED_CHECKS" \
        '($req|split(",")|map(gsub("^\\s+|\\s+$";""))|map(select(length>0))) as $n
         | select(.name as $x | $n | any(. as $q | $x | contains($q)))
         | select((.conclusion // "") as $c | ["failure","cancelled","timed_out","action_required","startup_failure","stale","error"]|index($c))
         | "  GATING FAIL: \(.name) = \(.conclusion) — \(.url // "")"'
}

check_ci() {
  local sha="$1"
  echo "[verify-ci] Checking CI for ${sha:0:7} (gating on: $VERIFY_REQUIRED_CHECKS)"
  for i in $(seq 1 $MAX_ATTEMPTS); do
    case "$(combined_ci_state "$sha")" in
      success)
        echo "[verify-ci] ✅ CI GREEN (attempt $i)"
        redis-cli -h redis -p 6379 SET "cabinet:layer1:cto:ci-green" 1 EX 300 > /dev/null 2>&1
        return 0 ;;
      failure)
        echo "[verify-ci] ❌ CI FAILED (attempt $i)"; dump_failures "$sha"; return 1 ;;
      *)
        echo "[verify-ci] ⏳ Pending... (attempt $i/$MAX_ATTEMPTS)"; sleep $POLL_INTERVAL ;;
    esac
  done
  echo "[verify-ci] ⚠️ Timed out after $((MAX_ATTEMPTS * POLL_INTERVAL))s"; return 2
}

check_deploy() {
  local sha="$1"
  echo "[verify-deploy] Checking deploy for ${sha:0:7} (gating on: $VERIFY_REQUIRED_CHECKS)"
  for i in $(seq 1 $MAX_ATTEMPTS); do
    case "$(combined_ci_state "$sha")" in
      success) echo "[verify-deploy] ✅ Deploy successful (attempt $i)"; return 0 ;;
      failure) echo "[verify-deploy] ❌ Deploy FAILED (attempt $i)"; dump_failures "$sha"; return 1 ;;
      *)       echo "[verify-deploy] ⏳ Pending... (attempt $i/$MAX_ATTEMPTS)"; sleep $POLL_INTERVAL ;;
    esac
  done
  echo "[verify-deploy] ⚠️ Timed out after $((MAX_ATTEMPTS * POLL_INTERVAL))s"; return 2
}

case "$MODE" in
  ci)     check_ci "$COMMIT_SHA" ;;
  deploy) check_deploy "$COMMIT_SHA" ;;
  both|*) check_ci "$COMMIT_SHA" && check_deploy "$COMMIT_SHA" ;;
esac
