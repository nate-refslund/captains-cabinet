#!/bin/bash
# cabinet-deploy.sh — `cabinet deploy`: promote a new pinned commit onto the
# runtime fleet, blue/green, with a health gate that makes rollback-by-
# construction (a bad slot is simply never promoted) — Captain-approved
# 2026-07-15 dev/runtime split (see docs/runbooks/dev-runtime-split-cutover.md
# for the one-time migration this is built for; NOT executed by this build,
# and this script never touches $HOME/captains-cabinet or the live
# fleet directly — only whatever --runtime-root points at).
#
# Composes cabinet/scripts/runtime-provision.sh's primitives (this script
# never re-implements provisioning/symlink-swap logic — see that file for
# the runtime layout and why instance/ is shared, not copied).
#
# FLOW (deploy, the default action):
#   fetch -> resolve <ref> (default: master, i.e. the mirror's tracked
#   origin/master) -> provision a new release slot at that commit -> STATE-
#   PERSISTENCE PREFLIGHT (would this release discard durable state?) ->
#   HEALTH GATE against the new (not-yet-live) slot -> if healthy: promote (atomic
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
# real cutover points them at .../current. Per officer (derived from
# instance/config/roster.yml via the SAME lib_roster.officer_service_rows()
# abstraction deploy-mac.sh uses — label-validated; consultants are filtered
# out, on-demand not persistent): if a real LaunchAgent is loaded AND this is
# the canonical live runtime root, `launchctl kickstart -k` it (graceful,
# reuses the plist's own ProgramArguments — never rewrites a plist); on a
# non-canonical scratch/rehearsal root a colliding live agent is reported and
# SKIPPED (kickstart -k acts on the whole-host launchd, so a scratch deploy
# must never reach it — the same CANONICAL_RUNTIME_ROOT confinement the redis
# leg already uses); otherwise (sandbox, or pre-cutover) invoke
# start-officer-mac.sh directly, honoring --dry-run.
#
# REDIS CONFINEMENT (2026-07-15 sandbox-confinement review, finding #1): the
# doctor sub-process's own Redis calls (PING + heartbeat SET + world-
# chronicle GET) are pinned to an unreachable sandbox endpoint whenever
# --runtime-root is not the canonical live root (~/.cabinet/runtime) and no
# REDIS_HOST/REDIS_PORT was already set in this script's own environment —
# see health_gate()'s own comment for the exact resolution order. A
# scratch-root rehearsal therefore cannot reach, PING, or overwrite the live
# fleet's real Redis heartbeat.
#
# WHAT THE GATE STILL READS OUTSIDE --runtime-root — named here rather than
# implied away: the doctor's services.yml/launchd/tmux check (its section 1)
# asks the HOST's real launchctl/tmux whether an ALREADY-LOADED
# com.cabinet.officer.* LaunchAgent/session exists — read-only, never
# started/stopped/modified. Pre-cutover (or against any scratch root) that
# legitimately finds nothing to match and DEADs those rows, same as several
# other whole-fleet checks (MCP-env resolution, scope-grant registration,
# world-chronicle freshness) — a fresh/isolated checkout correctly reporting
# "nobody has deployed me yet" is not a doctor bug. See cabinet-doctor.sh's
# own header ("NOT DESIGNED TO GREEN IN ISOLATION") for the full list and
# rationale; a scratch-root health_gate rehearsal proves the deploy
# ORCHESTRATION (fetch/resolve/provision/gate-decision/promote/restart-
# dispatch/rollback), not a green whole-fleet claim.
#
# Usage:
#   cabinet-deploy.sh deploy   --runtime-root <path> [--ref <git-ref>] [--dry-run]
#   cabinet-deploy.sh rollback --runtime-root <path> [--dry-run]
#   cabinet-deploy.sh status   --runtime-root <path>
#   (action defaults to `deploy` if omitted)
#
# --dry-run: fetch/provision/health-gate/promote all still run for real,
# confined to --runtime-root's OWN filesystem tree — a scratch-runtime-root
# promote is harmless; it is only ever dangerous for the LIVE runtime root,
# which this flag exists to let you rehearse against safely. Two things the
# health gate touches OUTSIDE that tree are confined/documented, never left
# to an overclaim: the doctor's redis calls (PING + heartbeat SET +
# world-chronicle GET — see health_gate()'s own comment; pinned away from
# the live instance for any non-canonical --runtime-root) and its read-only
# launchd/tmux liveness check (see the HEALTH GATE section above). Only the
# restart leg changes with --dry-run: it calls start-officer-mac.sh with
# --dry-run (its own documented zero-side-effect contract: prints the
# assembled command, no tmux/redis/boot) instead of `launchctl kickstart` —
# restart_officer()'s own DRY_RUN guard additionally ensures --dry-run never
# kickstarts an ALREADY-LOADED live LaunchAgent either, for the same reason.
#
# --runtime-root has NO hardcoded fallback to a real path: it is REQUIRED
# (flag or CABINET_DEPLOY_RUNTIME_ROOT env var) so this script can never
# silently default onto a live path. The documented eventual default once
# the cutover lands is ~/.cabinet/runtime (see the cutover runbook) — always
# pass it explicitly until then.
#
# Exit codes: 0 success · 1 preflight/health-gate/operational failure · 64 usage
# error.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVISION="$SCRIPT_DIR/runtime-provision.sh"
GERMLINE_LOCK_REL="cabinet/scripts/germline-lock.sh"   # relative to a slot root
DOCTOR_REL="cabinet/scripts/cabinet-doctor.sh"          # relative to a slot root

usage() {
  cat <<'EOF'
Usage: cabinet-deploy.sh [deploy|rollback|status] --runtime-root <path> [--ref <git-ref>] [--dry-run]
  deploy (default)  fetch -> provision -> state-persistence preflight -> health-gate
                    -> promote -> restart officers
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

# CANONICAL_RUNTIME_ROOT — the one --runtime-root value this script treats
# as "the real, eventually-live fleet path" (~/.cabinet/runtime, the
# documented eventual default in the --runtime-root usage note above).
# Resolved the same way RUNTIME_ROOT itself is (cd+pwd) so a symlinked
# $HOME or a trailing slash can't produce a false mismatch; best-effort — if
# that directory doesn't exist yet on this box (the common case
# pre-cutover), it simply can never equal RUNTIME_ROOT, which is the
# conservative (sandbox-confining) direction to fail in. Used by
# health_gate() below to decide whether the doctor sub-process may touch
# the real local Redis, or must be pinned away from it.
CANONICAL_RUNTIME_ROOT="$(cd "$HOME/.cabinet/runtime" 2>/dev/null && pwd || true)"

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

  # ---- redis sandbox-confinement (2026-07-15 review finding #1) -----------
  # The doctor sub-process defaults REDIS_HOST/REDIS_PORT to 127.0.0.1:6379
  # (cabinet-doctor.sh's own fallback) whenever neither is set — the REAL
  # local Redis the live fleet's heartbeats/trigger-bus/kill-switch already
  # use. Left alone, EVERY health_gate call (including a scratch-root
  # rehearsal that never intends to touch anything live) would PING that
  # instance and unconditionally SET cabinet:doctor:heartbeat there
  # (cabinet-doctor.sh's own final step) — a real, if narrow, live-fleet
  # side effect this script's header promises never happens. Resolution
  # order:
  #   1. an explicit REDIS_HOST/REDIS_PORT already in THIS script's own
  #      environment always wins, unchanged — lets a rehearsal deliberately
  #      point the doctor at its own throwaway Redis (e.g.
  #      `redis-server --port 6399`) and observe real PONG/heartbeat
  #      behaviour without touching the live instance.
  #   2. otherwise, when --runtime-root IS the canonical live root
  #      ($CANONICAL_RUNTIME_ROOT, ~/.cabinet/runtime), leave both unset so
  #      the doctor's own production default (127.0.0.1:6379) applies —
  #      correct once this root is actually the live one (post-cutover).
  #   3. otherwise (any other --runtime-root — a scratch/rehearsal path)
  #      pin both to a loopback port nothing binds (127.0.0.1:1 — a
  #      privileged, unassigned TCP port; connections fail closed with
  #      ECONNREFUSED, not a hang) so the doctor's PING/heartbeat-SET/
  #      world-chronicle-GET all report DEAD/absent instead of silently
  #      succeeding against whatever happens to be listening on the
  #      default.
  local hg_redis_host="${REDIS_HOST:-}" hg_redis_port="${REDIS_PORT:-}"
  if [ -z "$hg_redis_host" ] && [ -z "$hg_redis_port" ] \
     && { [ -z "$CANONICAL_RUNTIME_ROOT" ] || [ "$RUNTIME_ROOT" != "$CANONICAL_RUNTIME_ROOT" ]; }; then
    hg_redis_host=127.0.0.1
    hg_redis_port=1
    echo "cabinet-deploy.sh: --runtime-root is not the canonical live root (${CANONICAL_RUNTIME_ROOT:-~/.cabinet/runtime}) — pinning the doctor's redis calls to an unreachable sandbox endpoint (127.0.0.1:1) so this rehearsal cannot touch the live fleet's redis/heartbeat"
  fi

  local out rc=0
  out="$(CABINET_ROOT="$slot" CABINET_SOURCE_REPO="$slot" REDIS_HOST="$hg_redis_host" REDIS_PORT="$hg_redis_port" bash "$doctor_bin" 2>&1)" || rc=$?
  printf '%s\n' "$out" | sed 's/^/  [doctor] /'

  [ "$rc" -eq 0 ] && return 0

  local all_dead non_germline_dead
  all_dead="$(printf '%s\n' "$out" | grep '^DEAD' || true)"
  non_germline_dead="$(printf '%s\n' "$all_dead" | grep -v '^DEAD   germline ' || true)"
  if [ -n "$non_germline_dead" ]; then
    echo "cabinet-deploy.sh: HEALTH GATE FAILED — non-germline DEAD finding(s) on the new slot:" >&2
    printf '%s\n' "$non_germline_dead" | sed 's/^/  /' >&2
    echo "cabinet-deploy.sh: (a scratch/rehearsal --runtime-root pre-cutover is EXPECTED to DEAD out several whole-fleet checks here — not this script's bug; see cabinet-doctor.sh's own header, \"NOT DESIGNED TO GREEN IN ISOLATION\")" >&2
    return 1
  fi
  # Every DEAD line was the known, inert pre-promotion germline gap.
  echo "cabinet-deploy.sh: WARN — new slot's germline boundary is unarmed (expected pre-promotion; see this script's header). Every OTHER cabinet-doctor.sh check is green." >&2
  return 0
}

# ---- roster parsing — derives the fleet via the shared
# lib_roster.officer_service_rows() abstraction (label-validated), same as
# deploy-mac.sh; consultants are filtered separately in restart_fleet. -------
python_for_generator() {
  local candidate="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
  if command -v "$candidate" >/dev/null 2>&1; then
    printf '%s\n' "$candidate"
  elif command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    echo "cabinet-deploy.sh: Python 3 is required to derive the officer fleet" >&2
    return 1
  fi
}

roster_officers() {
  local root="$1"
  local roster="$root/instance/config/roster.yml"
  [ -f "$roster" ] || { echo "cabinet-deploy.sh: $roster not found — cannot derive the officer fleet" >&2; return 1; }
  local py
  py="$(python_for_generator)" || return 1
  # Shared abstraction: deploy-mac.sh, Cabinet Doctor, and the recovery drill
  # all consume these same synthesized rows. Validate the label before
  # returning a shell token (byte-mirror of deploy-mac.sh's own
  # roster_officers() — the re.fullmatch allowlist gate Corridor flagged).
  # lib_roster is imported from THIS slot's own cabinet/scripts (same "read
  # the new slot, not the running one" discipline as the health gate).
  "$py" - "$root" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "cabinet" / "scripts"))
import lib_roster

for row in lib_roster.officer_service_rows(root):
    label = str(row["label"])
    match = re.fullmatch(r"com\.cabinet\.officer\.([a-z0-9-]+)", label)
    if not match:
        raise SystemExit(f"cabinet-deploy.sh: unsafe roster-derived officer label: {label!r}")
    print(match.group(1))
PY
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
    elif [ -z "$CANONICAL_RUNTIME_ROOT" ] || [ "$RUNTIME_ROOT" != "$CANONICAL_RUNTIME_ROOT" ]; then
      # A non-canonical scratch/rehearsal --runtime-root must never
      # SIGKILL+relaunch a LIVE LaunchAgent whose slug happens to collide:
      # `kickstart -k` targets the HOST's launchd (gui/<uid>/<label> — a
      # whole-host namespace), not anything confined to this scratch slot. Only
      # the canonical/live runtime root (~/.cabinet/runtime) may touch live
      # agents — the same CANONICAL_RUNTIME_ROOT confinement the health gate's
      # redis leg already applies. Report + skip (same shape as --dry-run).
      echo "cabinet-deploy.sh: [non-canonical runtime root] would kickstart live LaunchAgent $label (skipped)"
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

# is_consultant <slug> — true (0) when the current slot's role file marks
# this officer officer_type: consultant. Consultants are on-demand sessions
# (start-officer-mac.sh per trigger), so a persistent restart on every deploy
# contradicts their lifecycle — restart_fleet SKIPS them. This is the
# deploy-side mirror of deploy-mac.sh's guard_consultant refusal, using the
# same `awk -F': *'` extraction. officer_service_rows() does NOT expose the
# `type` field, so the role file is the authority here — exactly how
# deploy-mac.sh splits label-derivation (lib_roster) from the consultant
# check (role yaml).
is_consultant() {
  local slug="$1"
  local role_yml="$RUNTIME_ROOT/current/instance/roles/active/$slug.yml"
  [ -f "$role_yml" ] || return 1
  local otype
  otype="$(awk -F': *' '$1=="officer_type"{print $2; exit}' "$role_yml" | tr -d '[:space:]')"
  [ "$otype" = "consultant" ]
}

restart_fleet() {
  local officers officer rc=0
  officers="$(roster_officers "$RUNTIME_ROOT/current")" || return 1
  [ -n "$officers" ] || { echo "cabinet-deploy.sh: roster parsed to an empty officer list — nothing to restart" >&2; return 0; }
  while IFS= read -r officer; do
    [ -n "$officer" ] || continue
    if is_consultant "$officer"; then
      echo "cabinet-deploy.sh: skipping $officer — officer_type: consultant (on-demand session, not a persistent restart)"
      continue
    fi
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

  # ---- state-persistence preflight (BLOCKING) --------------------------------
  # Runs AFTER provision (so the slot's symlinks are in place) and BEFORE the
  # health gate and promote, so a release that would discard durable state
  # never becomes `current`.
  #
  # Why this gate exists: a release is a FRESH `git worktree`, which contains
  # tracked files and nothing else. Every gitignored path — which is precisely
  # the cabinet's accumulated state — survives only if runtime-provision.sh's
  # lists symlink it into shared/. Those hand-maintained lists drifted from
  # .gitignore and silently discarded ratified Captain rules, the tier-3
  # decision log, the tool-call log and the append-only foundry archive. The
  # health gate passed and nothing errored: the old release kept the only copy
  # and `prune --keep 5` later rm -rf'd it. Absence of an error was never
  # evidence the state carried.
  #
  # The checker is run from THIS SLOT's own tree (the same "read the new slot,
  # not the running one" discipline as health_gate/roster_officers), and in
  # --slot mode it asserts against the real provisioned release rather than
  # trusting the lists to describe what actually happened.
  local preflight="$slot/cabinet/scripts/state-persistence-preflight.py" py_pf
  if [ -f "$preflight" ]; then
    py_pf="$(python_for_generator)" || exit 1
    echo "cabinet-deploy.sh: state-persistence preflight against $slot..."
    if ! "$py_pf" "$preflight" --repo "$slot" --slot "$slot" --shared "$RUNTIME_ROOT/shared"; then
      log_line "deploy FAILED sha=$sha slot=$slot reason=state-persistence-preflight current=unchanged"
      echo "cabinet-deploy.sh: DEPLOY ABORTED — this release would DISCARD durable state." >&2
      echo "cabinet-deploy.sh: 'current' left untouched. Fix the persistence lists in" >&2
      echo "cabinet-deploy.sh: cabinet/scripts/runtime-provision.sh (or declare the path" >&2
      echo "cabinet-deploy.sh: disposable, with a reason, in cabinet/config/state-persistence-policy.yml)." >&2
      exit 1
    fi
  else
    # Fail closed: a release old enough to predate the checker cannot prove it
    # preserves state, and this gate must never be skippable by deleting it.
    log_line "deploy FAILED sha=$sha slot=$slot reason=state-persistence-preflight-missing current=unchanged"
    echo "cabinet-deploy.sh: DEPLOY ABORTED — $preflight is missing, so this release" >&2
    echo "cabinet-deploy.sh: cannot prove it preserves durable state. 'current' left untouched." >&2
    exit 1
  fi

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
