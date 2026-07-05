#!/bin/bash
# run-probes.sh — launchd entry for the B2.3-B2.5 outcome probes
# (lane-supply 2026-07-05; wakes the probes the 2026-07-03 re-review found
# dead at runtime). Usage:
#
#   run-probes.sh github|vercel|sentry|all [--dry-run]
#
# Each probe is a READ-ONLY observer (writes nothing to GitHub/Vercel/Sentry):
# it joins external artifacts back to Cabinet proposals via the B2.1
# correlation-id and emits schema-valid outcome SUPERSEDES on the proposal's
# own ledger row — i.e. onto the same (actor, lane, action_type) graduation
# cell, where the hourly verifier (run-verifier.sh) then reconciles claims
# into verdict_judge rows. Products come from instance/config/probes.yml.
#
# FAIL-CLOSED: missing config/checkout/API key → probe skipped with a printed
# reason, NO verdict; a silent source while local git shows activity pages the
# healthchecks dead-man and emits NOTHING (lib.freshness_guard); any error →
# nonzero exit, no verdict. Live emits require CABINET_PROBES_ENABLED=1 (from
# the services.yml row / plist env — installing the plist IS the flip).
#
# SECRETS (env only, NEVER argv, never echoed):
#   - VERCEL_API_KEY — real value lives in ~/.screenpipe/pipes/_shared/.env
#     (product-ops pillar decision 2026-05-29); cabinet/.env carries
#     VERCEL_TOKEN, mapped below as a fallback when VERCEL_API_KEY is empty.
#   - SENTRY_AUTH_TOKEN — cabinet/.env.
#   - GitHub reads go through the `gh` CLI's own auth (keychain); GH_TOKEN is
#     mapped from GITHUB_PAT only when gh has no ambient auth of its own.
#
# 'all' runs the three sequentially with per-probe failure isolation: one
# probe crashing must not starve the others of their cycle; exit is nonzero
# if ANY probe failed (launchd log visibility).
#
# Reversible per probe:
#   launchctl bootout gui/$(id -u)/com.cabinet.probe-<src> \
#     && rm ~/Library/LaunchAgents/com.cabinet.probe-<src>.plist
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# launchd's minimal PATH excludes Homebrew (python3.12, gh) — the retro-trigger
# FATAL lesson (services.yml:118-122).
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Env order: cabinet/.env first, then _shared/.env so REAL keys win over
# cabinet/.env's empty placeholders (run-undo-sweep.sh:23-27 gotcha).
if [ -f "$ROOT/cabinet/.env" ]; then set -a; . "$ROOT/cabinet/.env"; set +a; fi
SP_ENV="${HOME:-/Users/nate}/.screenpipe/pipes/_shared/.env"
if [ -f "$SP_ENV" ]; then set -a; . "$SP_ENV"; set +a; fi

# Key mapping (values move env→env only; an empty value never claims a key).
if [ -z "${VERCEL_API_KEY:-}" ] && [ -n "${VERCEL_TOKEN:-}" ]; then
  export VERCEL_API_KEY="$VERCEL_TOKEN"
fi
if [ -z "${GH_TOKEN:-}" ] && [ -n "${GITHUB_PAT:-}" ]; then
  export GH_TOKEN="$GITHUB_PAT"
fi

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

SRC="${1:-all}"
shift 2>/dev/null || true

run_one() {  # $1 = probe module suffix; remaining args forwarded (--dry-run)
  local src="$1"
  shift   # WITHOUT this the suffix is forwarded again as a positional arg and
          # argparse rejects it (caught by the 2026-07-05 smoke test)
  "$PY" -m "framework.probes.probe_$src" "$@"
}

case "$SRC" in
  github|vercel|sentry)
    exec_rc=0
    run_one "$SRC" "$@" || exec_rc=$?
    exit "$exec_rc"
    ;;
  all)
    rc=0
    for src in github vercel sentry; do
      # Isolation: a crash in one probe must not starve the others' cycle.
      run_one "$src" "$@" || rc=1
    done
    exit "$rc"
    ;;
  *)
    echo "usage: run-probes.sh github|vercel|sentry|all [--dry-run]" >&2
    exit 2
    ;;
esac
