#!/bin/bash
# cabinet-deploy.sh — `cabinet deploy`: promote a new pinned commit onto the
# runtime fleet, blue/green, with a health gate that makes rollback-by-
# construction (a bad slot is simply never promoted) — Captain-approved
# 2026-07-15 dev/runtime split (see docs/runbooks/dev-runtime-split-cutover.md
# for the one-time migration this is built for; NOT executed by this build,
# and this script never touches /Users/nate/captains-cabinet or the live
# fleet directly — only whatever --runtime-root points at).
#
# Composes cabinet/scripts/runtime-provision.sh's primitives (this script
# never re-implements provisioning/symlink-swap logic — see that file for
# the runtime layout and why instance/ is shared, not copied).
#
# FLOW (deploy, the default action):
#   fetch -> resolve <ref> (default: master, i.e. the mirror's tracked
#   origin/master) -> provision a new release slot at that commit -> HEALTH
#   GATE against the new (not-yet-live) slot -> if healthy: promote (atomic
#   current-symlink swap) -> gracefully restart officers -> if UNHEALTHY:
#   leave 'current' exactly where it was, exit non-zero. No separate
#   rollback branch is needed for a failed DEPLOY: a bad slot is simply
#   never promoted (rollback-by-construction).
#
# `rollback` is the separate, explicit escape hatch for a slot that only
# misbehaves once it is actually live (the pre-promotion gate cannot see
# everything — e.g. a boot crash only reachable under real officer load):
# swap 'current' back to 'previous' and restart.
#
# HEALTH GATE — reuses THE NEW SLOT'S OWN cabinet-doctor.sh unmodified
# (CABINET_ROOT pointed at the new slot; the doctor binary itself is also
# read from the new slot, not the currently-running one, so a commit that
# improves the doctor is validated against itself, not a stale copy). One
# documented, narrow exception: cabinet-doctor.sh's germline
# exists-without-schg watchdog (its check #10) WILL report DEAD for every
# germline path in ANY freshly `git worktree add`-ed slot — schg is an
# inode-level flag that only root can set (germline-lock.sh's own
# `need_root`), and officers carry no passwordless sudo, so a brand-new slot
# is legitimately unarmed until a Captain-available relock. That gap is
# inert (the slot isn't serving anything pre-promotion), so — and ONLY for a
# pre-promotion slot — a `DEAD   germline ...` line is downgraded to a loud
# WARN instead of failing the gate; every OTHER DEAD line still hard-fails
# it, unconditionally, no exceptions. The gate first best-effort tries
# `sudo -n .../germline-lock.sh lock` (silently succeeds if the Captain has
# cached sudo — the common case then needs no filtering at all) and, after
# promotion, ALWAYS prints the new current slot's germline-lock.sh status in
# the clear so an unarmed boundary is a visible, named handback — never a
# silent gap (same "attempt sudo -n, else a named handback" pattern used
# elsewhere for germline etiquette).
#
# RESTART — invoked via the STABLE <runtime_root>/current symlink STRING,
# never a resolved releases/<sha> path, and with CABINET_ROOT pinned to that
# same string. start-officer-mac.sh stamps CABINET_REPO_ROOT into each
# officer's tmux session and refuses a takeover across a DIFFERENT root on
# the next restart (its own multi-checkout guard) — invoking via the
# resolved path would flip that string on every single deploy and force
# CABINET_FORCE_TAKEOVER=1 needlessly; the symlink-string invocation keeps
# it constant across every future deploy, which is also exactly what lets
# launchd's plist ProgramArguments stay unchanged across deploys once the
# real cutover points them at .../current. Per officer (read from
# instance/config/roster.yml, same roster parser deploy-mac.sh already
# uses, adapted verbatim): if a real LaunchAgent is loaded, `launchctl
# kickstart -k` it (graceful, reuses the plist's own ProgramArguments —
# never rewrites a plist); otherwise (sandbox, or pre-cutover) invoke
# start-officer-mac.sh directly, honoring --dry-run.
#
# Usage:
#   cabinet-deploy.sh deploy   --runtime-root <path> [--ref <git-ref>] [--dry-run]
#   cabinet-deploy.sh rollback --runtime-root <path> [--dry-run]
#   cabinet-deploy.sh status   --runtime-root <path>
#   (action defaults to `deploy` if omitted)
#
# --dry-run: fetch/provision/health-gate/promote all still run for real (all
# confined to --runtime-root, never the live fleet) — a scratch-runtime-root
# promote is harmless; it is only ever dangerous for the LIVE runtime root,
# which this flag exists to let you rehearse against safely. Only the
# restart leg changes: it calls start-officer-mac.sh with --dry-run (its own
# documented zero-side-effect contract: prints the assembled command, no
# tmux/redis/boot) instead of `launchctl kickstart`.
#
# --runtime-root has NO hardcoded fallback to a real path: it is REQUIRED
# (flag or CABINET_DEPLOY_RUNTIME_ROOT env var) so this script can never
# silently default onto a live path. The documented eventual default once
# the cutover lands is ~/.cabinet/runtime (see the cutover runbook) — always
# pass it explicitly until then.
#
# Exit codes: 0 success · 1 health-gate/operational failure · 64 usage error.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVISION="$SCRIPT_DIR/runtime-provision.sh"
GERMLINE_LOCK_REL="cabinet/scripts/germline-lock.sh"   # relative to a slot root
DOCTOR_REL="cabinet/scripts/cabinet-doctor.sh"          # relative to a slot root

usage() {
  cat <<'EOF'
Usage: cabinet-deploy.sh [deploy|rollback|status] --runtime-root <path> [--ref <git-ref>] [--dry-run]
  deploy (default)  fetch -> provision -> health-gate -> promote -> restart officers
  rollback          swap current back to previous -> restart officers
  status            print current/previous sha + germline status + last log lines
--runtime-root can also come from CABINET_DEPLOY_RUNTIME_ROOT. No default —
required, so this can never silently touch a real runtime path by accident.
EOF
}

# ---- args ------------------------------------------------------------------
ACTION="deploy"
RUNTIME_ROOT="${CABINET_DEPLOY_RUNTIME_ROOT:-}"
REF="master"
DRY_RUN=0

if [ $# -gt 0 ]; then
  case "$1" in
    deploy|rollback|status) ACTION="$1"; shift ;;
  esac
fi
while [ $# -gt 0 ]; do
  case "$1" in
    --runtime-root) RUNTIME_ROOT="${2:?--runtime-root requires a path}"; shift 2 ;;
    --ref)          REF="${2:?--ref requires a git ref}"; shift 2 ;;
    --dry-run)      DRY_RUN=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "cabinet-deploy.sh: unknown flag '$1'" >&2; usage >&2; exit 64 ;;
  esac
done
[ -n "$RUNTIME_ROOT" ] || { echo "cabinet-deploy.sh: --runtime-root is required (or CABINET_DEPLOY_RUNTIME_ROOT)" >&2; exit 64; }
RUNTIME_ROOT="$(cd "$RUNTIME_ROOT" 2>/dev/null && pwd)" || { echo "cabinet-deploy.sh: --runtime-root does not exist — run runtime-provision.sh init first" >&2; exit 64; }

LOG="$RUNTIME_ROOT/.cabinet-deploy.log"
log_line() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$LOG"; }

# ---- health gate -------------------------------------------------------------
# health_gate <slot_path> — runs THAT SLOT'S OWN cabinet-doctor.sh against
# itself (CABINET_ROOT=$slot). Returns 0/1. See the file header for the
# germline-DEAD filter rationale — it is the ONLY finding class ever
# downgraded; everything else hard-fails the gate exactly as doctor reports it.
health_gate() {
  local slot="$1"
  local doctor_bin="$slot/$DOCTOR_REL" lock_bin="$slot/$GERMLINE_LOCK_REL"

  if [ -f "$lock_bin" ]; then
    if sudo -n bash "$lock_bin" lock >/dev/null 2>&1; then
      echo "cabinet-deploy.sh: germline relocked on the new slot (cached sudo)"
    else
      echo "cabinet-deploy.sh: no cached sudo — new slot's germline boundary stays unarmed until a Captain relock (see below; this is expected pre-promotion, not a code defect)"
    fi
  fi

  [ -f "$doctor_bin" ] || { echo "cabinet-deploy.sh: HEALTH GATE FAILED — $doctor_bin missing on the new slot" >&2; return 1; }

  local out rc=0
  out="$(CABINET_ROOT="$slot" CABINET_SOURCE_REPO="$slot" bash "$doctor_bin" 2>&1)" || rc=$?
  printf '%s\n' "$out" | sed 's/^/  [doctor] /'

  [ "$rc" -eq 0 ] && return 0

  local all_dead non_germline_dead
  all_dead="$(printf '%s\n' "$out" | grep '^DEAD' || true)"
  non_germline_dead="$(printf '%s\n' "$all_dead" | grep -v '^DEAD   germline ' || true)"
  if [ -n "$non_germline_dead" ]; then
    echo "cabinet-deploy.sh: HEALTH GATE FAILED — non-germline DEAD finding(s) on the new slot:" >&2
    printf '%s\n' "$non_germline_dead" | sed 's/^/  /' >&2
    return 1
  fi
  # Every DEAD line was the known, inert pre-promotion germline gap.
  echo "cabinet-deploy.sh: WARN — new slot's germline boundary is unarmed (expected pre-promotion; see this script's header). Every OTHER cabinet-doctor.sh check is green." >&2
  return 0
}

# ---- roster parsing (mirrors deploy-mac.sh's roster_officers(), verbatim) ----
roster_officers() {
  local roster="$1/instance/config/roster.yml"
  [ -f "$roster" ] || { echo "cabinet-deploy.sh: $roster not found — cannot derive the officer fleet" >&2; return 1; }
  awk '
    /^roster:[[:space:]]*$/ { in_roster=1; next }
    in_roster && /^[^[:space:]#]/ { exit }
    in_roster && /^  [a-z0-9-]+:[[:space:]]*$/ {
      slug=$1; sub(/:$/,"",slug); print slug
    }
  ' "$roster"
}

restart_officer() {
  local officer="$1"
  local label="com.cabinet.officer.$officer"
  if launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then
    if [ "$DRY_RUN" = "1" ]; then
      # --dry-run must NEVER restart a live agent. A rehearsal that happens to
      # share an officer slug with an already-loaded LaunchAgent would otherwise
      # `kickstart -k` (SIGKILL + relaunch) the real one — the header's whole
      # point is that --dry-run "calls start-officer-mac.sh with --dry-run
      # instead of launchctl kickstart", which was only true when no live agent
      # of that label existed. Report, don't execute.
      echo "cabinet-deploy.sh: [dry-run] would kickstart live LaunchAgent $label (skipped)"
    else
      launchctl kickstart -k "gui/$(id -u)/$label"
      echo "cabinet-deploy.sh: kickstarted live LaunchAgent $label"
    fi
  else
    local extra=()
    [ "$DRY_RUN" = "1" ] && extra+=(--dry-run)
    CABINET_ROOT="$RUNTIME_ROOT/current" CABINET_SOURCE_REPO="$RUNTIME_ROOT/current" \
      bash "$RUNTIME_ROOT/current/cabinet/scripts/start-officer-mac.sh" "$officer" ${extra[@]+"${extra[@]}"}
  fi
}

restart_fleet() {
  local officers officer rc=0
  officers="$(roster_officers "$RUNTIME_ROOT/current")" || return 1
  [ -n "$officers" ] || { echo "cabinet-deploy.sh: roster parsed to an empty officer list — nothing to restart" >&2; return 0; }
  while IFS= read -r officer; do
    [ -n "$officer" ] || continue
    restart_officer "$officer" || rc=1
  done <<< "$officers"
  return "$rc"
}

print_germline_status() {
  echo ""
  echo "==== germline status (current slot) ===="
  bash "$RUNTIME_ROOT/current/$GERMLINE_LOCK_REL" status || true
  echo "(unarmed here is a NAMED handback, not a silent gap — Captain-available:"
  echo " sudo bash \"$RUNTIME_ROOT/current/$GERMLINE_LOCK_REL\" lock)"
}

# ---- actions -----------------------------------------------------------------
do_deploy() {
  bash "$PROVISION" fetch "$RUNTIME_ROOT"
  local sha slot prov_out
  sha="$(bash "$PROVISION" resolve "$RUNTIME_ROOT" "$REF")"
  echo "cabinet-deploy.sh: target ref '$REF' -> $sha"

  prov_out="$(bash "$PROVISION" provision "$RUNTIME_ROOT" "$sha")"
  printf '%s\n' "$prov_out"
  slot="$(printf '%s\n' "$prov_out" | sed -n 's/^PROVISIONED_SLOT=//p')"
  [ -n "$slot" ] || { echo "cabinet-deploy.sh: provision did not report a slot path — aborting" >&2; exit 1; }

  echo "cabinet-deploy.sh: running the health gate against $slot (not yet live)..."
  if ! health_gate "$slot"; then
    log_line "deploy FAILED sha=$sha slot=$slot reason=health-gate current=unchanged"
    echo "cabinet-deploy.sh: DEPLOY ABORTED — 'current' left untouched. Bad slot never promoted." >&2
    exit 1
  fi

  bash "$PROVISION" promote "$RUNTIME_ROOT" "$sha"
  echo "cabinet-deploy.sh: promoted $sha — restarting officers..."
  local restart_rc=0
  restart_fleet || restart_rc=$?
  log_line "deploy OK sha=$sha slot=$slot restart_rc=$restart_rc"

  print_germline_status

  if [ "$restart_rc" -ne 0 ]; then
    echo "cabinet-deploy.sh: promoted but one or more officer restarts reported non-zero — inspect above." >&2
    exit 1
  fi
  echo "cabinet-deploy.sh: DEPLOY OK — current=$sha"
}

do_rollback() {
  bash "$PROVISION" rollback "$RUNTIME_ROOT"
  echo "cabinet-deploy.sh: rolled back — restarting officers..."
  local restart_rc=0
  restart_fleet || restart_rc=$?
  log_line "rollback restart_rc=$restart_rc"
  [ "$restart_rc" -eq 0 ] || { echo "cabinet-deploy.sh: rolled back but a restart reported non-zero — inspect above." >&2; exit 1; }
  echo "cabinet-deploy.sh: ROLLBACK OK"
}

do_status() {
  local cur prev
  cur="$(bash "$PROVISION" current "$RUNTIME_ROOT")"
  echo "current:  $cur"
  if [ -L "$RUNTIME_ROOT/previous" ]; then
    prev="$(basename "$(readlink "$RUNTIME_ROOT/previous")")"
    echo "previous: $prev"
  else
    echo "previous: NONE"
  fi
  [ -L "$RUNTIME_ROOT/current" ] && print_germline_status
  if [ -f "$LOG" ]; then
    echo ""
    echo "==== last 5 deploy-log lines ===="
    tail -5 "$LOG"
  fi
}

case "$ACTION" in
  deploy)   do_deploy ;;
  rollback) do_rollback ;;
  status)   do_status ;;
esac
