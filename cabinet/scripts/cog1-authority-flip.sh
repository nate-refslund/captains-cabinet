#!/usr/bin/env bash
# cog1-authority-flip.sh — COG-1 cutover, rollback, and capture inverse, each
# ONE command (docs/plans/cognitive-core-phase-1-contract-2026-07-20.md
# §8.4 cutover, §8.5 rollback, §12.4 rehearsed inverses).
#
# Verbs:
#   outbox   CUTOVER: authority -> the outbox relay. my-tasks.sh emit_event
#            reads the pointer and SKIPS its legacy direct XADD; the relay owns
#            the durable tasks exhaust. (§8.4)
#   legacy   ROLLBACK: authority -> the legacy direct emit; the relay returns to
#            shadow-only. The one-command inverse of `outbox`. (§8.5)
#   disarm   CAPTURE EMERGENCY inverse: DISABLE the officer_tasks capture
#            trigger — for a defective-trigger incident the authority flip
#            cannot reach (a dark drain makes the RELAY inert, never the
#            trigger). No data surgery; reversible via `enable`. (§12.4)
#   enable   Re-ENABLE the capture trigger (the inverse of `disarm`).
#
# The authority pointer is ONE well-known host-global default path:
#   ~/.cabinet/state/cog1-authority
# Officer shells, launchd jobs, and the cron wrapper (cabinet/cron/outbox-relay.sh)
# all read THIS file with ZERO env dependency — no per-context, per-worktree, or
# split-authority window. CABINET_COG1_AUTHORITY overrides for tests/scratch
# ONLY. The path literal lives only in cabinet/scripts + cabinet/cron (layer-legal
# there); the framework relay never reads it. Absent/unreadable pointer => the
# consumers fail safe to `legacy` (§8.4). Self-ratified per the 2026-07-07
# full-autonomy grant.
set -euo pipefail

# Load-bearing: the exact capture trigger 047 names (§5.2) and the target of the
# `disarm` inverse (§12.4). Renaming it in 047 requires renaming it here.
TRIGGER="trg_officer_tasks_outbox_capture"

usage() {
  echo "usage: $(basename "$0") {outbox|legacy|disarm|enable}" >&2
  exit 2
}

# Atomic pointer write: mktemp in the SAME dir + rename(2) — an officer/launchd
# reader never sees a half-written pointer, and there is no partial-authority
# window during the flip.
write_pointer() {
  local val="$1" pointer dir tmp
  # Resolved lazily: disarm/enable never touch the pointer, so those verbs must
  # not require $HOME (set -u would otherwise crash a bare-env operator run).
  pointer="${CABINET_COG1_AUTHORITY:-$HOME/.cabinet/state/cog1-authority}"
  dir="$(dirname "$pointer")"
  mkdir -p "$dir"
  tmp="$(mktemp "$dir/.cog1-authority.XXXXXX")"
  printf '%s\n' "$val" >"$tmp"
  mv -f "$tmp" "$pointer"
  echo "cog1-authority-flip: authority -> ${val}  (${pointer})"
}

# DISABLE/ENABLE the capture trigger against the work store. Fail LOUD when no
# connection is configured (a silent no-op that leaves capture live is exactly
# the incident this inverse answers). ON_ERROR_STOP=1 makes a wrong trigger name
# or a permission failure a non-zero exit, never a quiet pass.
alter_trigger() {
  local action="$1"
  if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
    echo "cog1-authority-flip: ERROR \$NEON_CONNECTION_STRING not set — cannot ${action} the capture trigger" >&2
    exit 1
  fi
  psql "$NEON_CONNECTION_STRING" -v ON_ERROR_STOP=1 -q \
    -c "ALTER TABLE officer_tasks ${action} TRIGGER ${TRIGGER};"
  echo "cog1-authority-flip: officer_tasks capture trigger ${action}D  (${TRIGGER})"
}

[ "$#" -eq 1 ] || usage
case "$1" in
  outbox) write_pointer outbox ;;
  legacy) write_pointer legacy ;;
  disarm) alter_trigger DISABLE ;;
  enable) alter_trigger ENABLE ;;
  *) usage ;;
esac
