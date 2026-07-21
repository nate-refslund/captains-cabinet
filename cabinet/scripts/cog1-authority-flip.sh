#!/usr/bin/env bash
# cog1-authority-flip.sh — COG-1 cutover, rollback, and capture inverse, each
# ONE command (docs/plans/cognitive-core-phase-1-contract-2026-07-20.md
# §8.4 cutover, §8.5 rollback, §12.4 rehearsed inverses).
#
# Verbs:
#   outbox   CUTOVER: authority -> the outbox relay. my-tasks.sh emit_event
#            reads the pointer and SKIPS its legacy direct XADD; the cron wrapper
#            (cabinet/cron/outbox-relay.sh) resolves the pointer and passes the
#            LIVE stream target (cabinet:tasks:events) down to the relay (§8.4).
#            EXECUTABLE once the live-stream retarget seam is present: the
#            interlock below PROBES framework/outbox/relay.py for the seam's
#            landing marker (the token COG1_LIVE_STREAM_TARGET) and SELF-RELEASES
#            when it is found. If the seam is absent (or relay.py is missing) the
#            verb fails CLOSED (exit 64) so the live stream cannot be darkened.
#            Harness override (tokenless-relay rigs): COG1_FLIP_I_KNOW_NO_LIVE_TARGET=1.
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
  outbox)
    # INTERLOCK (§12.3 review F1): fail CLOSED unless the relay's live-stream
    # retarget seam is present. The seam's landing marker is the token
    # COG1_LIVE_STREAM_TARGET in relay.py; with the seam present this probe finds
    # it and the verb proceeds (the wrapper then routes cabinet:tasks:events).
    # Absent (or relay.py missing) -> flipping now would silence the legacy XADD
    # while the relay stayed on shadow, darkening cabinet:tasks:events -> refuse.
    if ! grep -q "COG1_LIVE_STREAM_TARGET" "$(dirname "$0")/../../framework/outbox/relay.py" 2>/dev/null; then
      if [ "${COG1_FLIP_I_KNOW_NO_LIVE_TARGET:-0}" != "1" ]; then
        echo "cog1-authority-flip: REFUSED — the relay live-stream retarget seam (§8.4) is not implemented; 'outbox' would darken cabinet:tasks:events. See the COG-1 review artifact deferral (pre-cutover blocker). Harness override: COG1_FLIP_I_KNOW_NO_LIVE_TARGET=1." >&2
        exit 64
      fi
    fi
    write_pointer outbox ;;
  legacy) write_pointer legacy ;;
  disarm) alter_trigger DISABLE ;;
  enable) alter_trigger ENABLE ;;
  *) usage ;;
esac
