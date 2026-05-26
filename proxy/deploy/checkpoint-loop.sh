#!/usr/bin/env bash
# proxy/deploy/checkpoint-loop.sh — Spec 052 CTO#4: daily WORM off-box checkpoint emitter sidecar.
#
# Sleeps until the next 00:05 UTC, runs checkpoint.py (emit the OPAQUE-keyed served snapshot +
# commit the local git mirror, AC #13), then PUSHES the public mirror to the `origin` remote IF
# provision.sh wired one (the public refslund-cabinet-checkpoints repo + a deploy token). Phase-1
# commits are UNSIGNED (CTO#7; Phase-2 adds offline Captain PGP).
#
# WHY a sidecar loop, not a host /etc/cron.d entry: the job runs IN-container (it needs Python +
# the FW-097 modules + git + the bind-mounted dirs), so a sidecar is self-contained + reboot-
# resilient via the compose stack (systemd refslund-backend.service) with no host->container exec
# coupling. Daily cadence; the ~24h sleep is negligible. Runs as the non-root `audit` user.
#
# The push uses the `origin` remote configured by provision.sh (token lives in .git/config, mode
# 0750 dir, NEVER in this script's args / process table); git output is token-redacted defensively.
set -u

cd /app/audit-server || { echo "[checkpoint-loop] FATAL: /app/audit-server missing" >&2; exit 1; }
GITDIR="${AUDIT_CHECKPOINT_GIT_DIR:-/data/checkpoints-git}"
echo "[checkpoint-loop] start; daily 00:05 UTC; root=${LITELLM_AUDIT_LOG_ROOT:-<default>} mirror=${GITDIR}"

while true; do
  now="$(date -u +%s)"
  target="$(date -u -d '00:05 today' +%s)"
  [ "$target" -le "$now" ] && target="$(date -u -d '00:05 tomorrow' +%s)"
  sleep_s=$(( target - now ))
  echo "[checkpoint-loop] sleeping ${sleep_s}s until the next 00:05 UTC checkpoint"
  sleep "$sleep_s"

  python checkpoint.py || echo "[checkpoint-loop] emit error (continuing — next cycle retries)" >&2

  # Push the public mirror (Phase-1 UNSIGNED) when provision.sh wired the `origin` remote + the repo
  # is initialized; otherwise local-commit only (the off-box anchor is inert until the push is wired).
  if [ -d "${GITDIR}/.git" ] && git -C "${GITDIR}" remote get-url origin >/dev/null 2>&1; then
    git -C "${GITDIR}" push origin HEAD 2>&1 \
      | sed -E 's#(https://)[^@]*@#\1REDACTED@#g' \
      || echo "[checkpoint-loop] push error (continuing — local commit is intact)" >&2
  else
    echo "[checkpoint-loop] no 'origin' remote — local commit only (deploy wires the public push)"
  fi
done
