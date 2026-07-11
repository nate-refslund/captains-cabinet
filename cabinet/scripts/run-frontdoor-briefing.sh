#!/bin/bash
# run-frontdoor-briefing.sh — the launchd entry point for the cabinet's recurring
# unified briefing on the one channel (@NateHQChairBot).
#
# Pulls real signals into the front-door intake and runs ONE send-path pass:
#   morning_synthesis.enqueue_synthesis  →  run_frontdoor.run_send_path
#
# TI-5: run_briefing also enqueues the act-then-tell digest (tell_digest.
# enqueue_digest — ACTED with stable `undo <n>` handles / AWAITING / WATCHING /
# SELF) into this same briefing on BOTH the AM and PM runs, persisting the
# cabinet:digest:<date> index manifest FIRST so undo-by-index replies bind the
# moment the text lands. Best-effort (a digest failure never blocks the
# briefing); disable with CABINET_TELL_DIGEST=0.
#
# Secrets: the bot token lives ONLY in cabinet/.env (chmod 600). We read the two
# values we need into the process env here — never echoed, never written to the
# plist. Everything else (allow_sends gate, captain-only recipient) is enforced
# downstream in channel.send. Reversible: `launchctl unload` the plist.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/cabinet/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "run-frontdoor-briefing: missing $ENV_FILE" >&2
  exit 1
fi

# Read ONLY the two values needed for the send; do not source the whole file
# (avoids exporting empty optional keys that could shadow the shared env's keys).
export TELEGRAM_COS_TOKEN="$(grep '^TELEGRAM_COS_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
export CAPTAIN_TELEGRAM_ID="$(grep '^CAPTAIN_TELEGRAM_ID=' "$ENV_FILE" | cut -d= -f2-)"

# Runtime so channel.send's allow_sends() gate opens; localhost Redis for intake.
export CABINET_ENV=runtime
export REDIS_HOST="${REDIS_HOST:-localhost}"

# Captain timezone for the gate's quiet-hours/briefing-slot math. Without it
# the attention gate falls back to UTC and reads 07:30 LOCAL as 05:30 "local"
# — inside the 21:00–07:00 quiet window — so the briefing CARD (which rides
# the gate, unlike the old raw-channel wall) would be quiet-routed back into
# the very intake it summarizes (found live 2026-07-11 arming briefing-as-
# card). Same one-line resolution the outcome-watchdog wrapper uses.
CAPTAIN_TZ_LINE="$(grep '^captain_timezone:' "$ROOT/instance/config/platform.yml" 2>/dev/null | awk '{print $2}')"
export CABINET_CAPTAIN_TZ="${CABINET_CAPTAIN_TZ:-${CAPTAIN_TZ_LINE:-Europe/Berlin}}"

# Run mode: the evening (PM) run additionally builds the comprehensive daily
# recap (writes today's Monday Reflections item + the vault daily note, folds the
# recap into this briefing). The morning (AM) run stays signals-only. We key off
# the local hour: hour >= 17 → PM, else AM. Honor a caller-supplied override so a
# manual `CABINET_RUN_MODE=PM bash run-frontdoor-briefing.sh` forces the recap.
if [ -z "${CABINET_RUN_MODE:-}" ]; then
  HOUR="$(date +%H)"
  # Strip any leading zero so 09 doesn't trip base-8 arithmetic.
  if [ "$((10#$HOUR))" -ge 17 ]; then
    CABINET_RUN_MODE=PM
  else
    CABINET_RUN_MODE=AM
  fi
fi
export CABINET_RUN_MODE

# Deploy-health source: a read-only Vercel API key + the monitored app list.
# The key lives in the PersonalSource shared env (instance platform.yml
# shared_env_path, resolved via lib/personal-env.sh — R070 indirection; NOT
# cabinet/.env); read ONLY that one key (never source the whole file).
# CABINET_DEPLOY_HEALTH_APPS holds the instance's product app names so the
# framework module stays product-agnostic. Both optional — unset (e.g. a
# clean-room deployment with no shared env) → deploy-health simply stays silent.
. "$ROOT/cabinet/scripts/lib/personal-env.sh"
SHARED_ENV_FILE="$(personal_env_file)"
[ -n "$SHARED_ENV_FILE" ] && [ -f "$SHARED_ENV_FILE" ] && export VERCEL_API_KEY="$(grep '^VERCEL_API_KEY=' "$SHARED_ENV_FILE" | cut -d= -f2-)"
# R110: instance values live in cabinet/.env (env wins, then cabinet/.env,
# then empty = the signal stays silent) — no launcher org/app defaults here.
_env_key() { grep "^$1=" "$ENV_FILE" | cut -d= -f2-; }
export CABINET_DEPLOY_HEALTH_APPS="${CABINET_DEPLOY_HEALTH_APPS:-$(_env_key CABINET_DEPLOY_HEALTH_APPS)}"

# Sentry error-health source: a read-scoped token from the cabinet's OWN store
# (cabinet/.env, read here like the bot token) + the instance's org/project (kept
# out of the framework module, same as the Vercel app list). Optional — unset →
# sentry-health stays silent.
export SENTRY_AUTH_TOKEN="$(_env_key SENTRY_AUTH_TOKEN)"
export CABINET_SENTRY_ORG="${CABINET_SENTRY_ORG:-$(_env_key CABINET_SENTRY_ORG)}"
export CABINET_SENTRY_PROJECT="${CABINET_SENTRY_PROJECT:-$(_env_key CABINET_SENTRY_PROJECT)}"

# launchd hands us a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin) that EXCLUDES
# Homebrew. The intake module's stdlib backend shells out to `redis-cli`, which
# lives in /opt/homebrew/bin — without this the briefing crashes at enqueue with
# `FileNotFoundError: redis-cli` and NO briefing reaches Nate (observed
# 2026-06-23 07:30). Prepend Homebrew bin so redis-cli (and the brew python)
# resolve. Matches this script's existing /opt/homebrew/bin/python3.12 default.
export PATH="/opt/homebrew/bin:$PATH"

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1

# Wake-race guard (observed 2026-06-30 + 07-01): launchd fires this briefing when
# the Mac WAKES from overnight sleep, before the network stack is ready — so
# channel.send fails "telegram transport error: URLError" and NO briefing reaches
# Nate until a manual re-run. Wait until Telegram's API is actually reachable (up
# to ~3 min) before composing/sending, so the cron self-heals the wake race.
# Transient blips DURING the send are still caught by channel.send's transport
# retry; anything still missed stays pending and is recovered by the next run's
# recover_pending (loss-safe). Best-effort: proceed after the cap regardless.
for _i in $(seq 1 36); do
  if "$PY" -c 'import socket; socket.create_connection(("api.telegram.org", 443), timeout=4).close()' 2>/dev/null; then
    break
  fi
  sleep 5
done

# Run the briefing and stamp the delivered-marker ONLY on a confirmed send, so the
# outcome-watchdog can tell a delivered briefing from a failed one (it treats
# cabinet:schedule:last-run:cos:briefing as the satisfied-by-any-means signal;
# run_briefing itself does not stamp it, so a delivered auto-briefing previously
# looked identical to a failed one).
BRIEF_OUT="$("$PY" -m framework.frontdoor.run_briefing 2>&1)"
printf '%s\n' "$BRIEF_OUT"
if printf '%s' "$BRIEF_OUT" | grep -q '"sent": *true'; then
  redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" \
    SET cabinet:schedule:last-run:cos:briefing "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >/dev/null 2>&1 || true
fi
