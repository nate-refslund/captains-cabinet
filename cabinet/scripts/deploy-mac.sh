#!/bin/bash
# deploy-mac.sh — Orchestrate Mac native Cabinet deployment.
#
# Substitutes envsubst variables against plist templates in cabinet/launchd/,
# writes them to ~/Library/LaunchAgents/, then bootstraps via launchctl.
#
# Usage:
#   bash cabinet/scripts/deploy-mac.sh --officer <officer>     # deploy one officer
#   bash cabinet/scripts/deploy-mac.sh --officer all           # deploy the roster fleet (instance/config/roster.yml)
#   bash cabinet/scripts/deploy-mac.sh --daemon <name>         # deploy one template-based non-officer service
#                                                              #   (any cabinet/launchd/com.cabinet.<name>.template.plist)
#   bash cabinet/scripts/deploy-mac.sh --officer X --daemon Y  # both in one invocation
#   bash cabinet/scripts/deploy-mac.sh --all                   # roster officers + the services.yml-backed
#                                                              #   template daemons (limit-reset-watchdog, dashboard);
#                                                              #   the rest of the fleet is manifest-owned — see
#                                                              #   cabinet/services.yml + generate-plists.py
#   bash cabinet/scripts/deploy-mac.sh --dry-run               # show what would be done, don't execute
#   bash cabinet/scripts/deploy-mac.sh --officer X --force     # override the consultant guard
#   bash cabinet/scripts/deploy-mac.sh --stop <name|all>       # bootout installed com.cabinet.* LaunchAgents
#                                                              #   (RUNTIME truth: enumerates ~/Library/LaunchAgents,
#                                                              #   never the manifest; idempotent; NEVER bootstraps;
#                                                              #   plist files stay on disk — redeploy to restart.
#                                                              #   Wave D / D2, DESIGN-companion-2026-07-10 §3)
#
# Consultant guard: --officer <name> refuses roles whose
# instance/roles/active/<name>.yml says officer_type: consultant —
# consultants are on-demand sessions (start-officer-mac.sh) and a KeepAlive
# LaunchAgent would pin them always-on. --force overrides.
#
# Per Spec 059 v1.1 Checkpoint 2.8 (envsubst + WorkingDirectory + SoftResourceLimits + KeepAlive ratifications).

set -euo pipefail

# Honor either CABINET_SOURCE_REPO (canonical Mac install path) or CABINET_ROOT
# (worktree / dev override). Fall back to script-relative if neither set.
REPO_ROOT="${CABINET_SOURCE_REPO:-${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}}"
# Re-export both so child scripts (sync-agents.sh, envsubst, etc.) see a
# consistent value regardless of which variable the operator set.
export CABINET_SOURCE_REPO="$REPO_ROOT"
export CABINET_ROOT="$REPO_ROOT"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
LOGS_DIR="$HOME/Library/Logs/cabinet"
TEMPLATES_DIR="$REPO_ROOT/cabinet/launchd"

OFFICER=""
DAEMON=""
STOP=""
ALL=false
DRY_RUN=false
FORCE=false

while [ $# -gt 0 ]; do
  case "$1" in
    --officer) OFFICER="${2:?--officer requires a name (or 'all')}"; shift 2 ;;
    --daemon)  DAEMON="${2:?--daemon requires a name}"; shift 2 ;;
    --stop)    STOP="${2:?--stop requires a name (or 'all')}"; shift 2 ;;
    --all)     ALL=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --force)   FORCE=true; shift ;;
    *) echo "deploy-mac.sh: unknown flag '$1'" >&2; exit 64 ;;
  esac
done

# --stop is teardown-only — combining it with deploy selectors would blur
# whether the invocation starts or stops things. Refuse loudly.
if [ -n "$STOP" ] && { [ "$ALL" = true ] || [ -n "$OFFICER" ] || [ -n "$DAEMON" ]; }; then
  echo "deploy-mac.sh: --stop cannot be combined with --all/--officer/--daemon" >&2
  exit 64
fi

mkdir -p "$LAUNCHD_DIR" "$LOGS_DIR"

# Populate .claude/agents/ from preset before LaunchAgent boots officers.
# start-officer-mac.sh probes for $REPO_ROOT/.claude/agents/$OFFICER.md to gate
# its --agent flag; without this, native_agent=false on every fresh deployment.
# load-preset.sh also does this inline, but at deploy time we may not have a Neon
# connection yet — sync-agents.sh is the agent-only step that runs unconditionally.
# Idempotent; safe to re-run. Skipped on --dry-run: a dry run must not mutate
# anything, including the generated .claude/agents/ directory.
if $DRY_RUN; then
  echo "deploy-mac.sh: --dry-run — skipping sync-agents.sh (no writes)"
elif [ -n "$STOP" ]; then
  : # --stop is teardown-only — agent sync belongs to the deploy legs
elif ! bash "$REPO_ROOT/cabinet/scripts/sync-agents.sh" 2>&1; then
  echo "deploy-mac.sh: sync-agents.sh failed — officers will boot without --agent flag" >&2
fi

render_template() {
  local template="$1"
  if command -v envsubst >/dev/null 2>&1; then
    OFFICER="$OFFICER_VAR" USER="$(id -un)" HOME="$HOME" REPO_ROOT="$REPO_ROOT" \
      envsubst '$OFFICER $USER $HOME $REPO_ROOT' < "$template"
  else
    OFFICER="$OFFICER_VAR" USER="$(id -un)" HOME="$HOME" REPO_ROOT="$REPO_ROOT" \
      python3 - "$template" <<'PY'
import os
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
for key in ("OFFICER", "USER", "HOME", "REPO_ROOT"):
    text = text.replace("${" + key + "}", os.environ.get(key, ""))
print(text, end="")
PY
  fi
}

# envsubst-render a template → final plist + bootstrap (or just print if --dry-run)
deploy_plist() {
  local template="$1" final="$2" label="$3"
  if [ ! -f "$template" ]; then
    echo "deploy-mac.sh: template not found: $template" >&2
    return 1
  fi

  # Build envsubst input — only substitute the variables we care about
  # (avoids accidentally consuming other env vars in the template)
  local rendered
  rendered=$(render_template "$template")

  if $DRY_RUN; then
    echo "=== WOULD-WRITE $final ==="
    echo "$rendered"
    echo "=== WOULD-BOOTSTRAP $label ==="
    return 0
  fi

  echo "$rendered" > "$final"
  chmod 644 "$final"

  # If already loaded, bootout first (idempotent)
  if launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)" "$final" 2>/dev/null || true
    sleep 1
  fi

  launchctl bootstrap "gui/$(id -u)" "$final" || {
    echo "deploy-mac.sh: bootstrap failed for $label" >&2
    return 2
  }
  echo "deployed: $label"
}

# Officer deployment
deploy_officer() {
  local officer="$1"
  OFFICER_VAR="$officer"
  deploy_plist \
    "$TEMPLATES_DIR/com.cabinet.officer.template.plist" \
    "$LAUNCHD_DIR/com.cabinet.officer.$officer.plist" \
    "com.cabinet.officer.$officer"
}

# Daemon deployment — renders any cabinet/launchd/com.cabinet.<name>.template.plist.
# (2026-07-04: comment de-staled with the --all prune — the old example list here
# named heartbeat-watchdog/cost-summary/worktree-listener, three of the very
# legacy daemons --all no longer auto-installs; see the daemon-leg note below.)
deploy_daemon() {
  local daemon="$1"
  OFFICER_VAR=""  # daemons don't use OFFICER
  deploy_plist \
    "$TEMPLATES_DIR/com.cabinet.$daemon.template.plist" \
    "$LAUNCHD_DIR/com.cabinet.$daemon.plist" \
    "com.cabinet.$daemon"
}

# Consultant guard — a persistent KeepAlive LaunchAgent contradicts the
# on-demand consultant lifecycle. Consultants are started per trigger via
# start-officer-mac.sh; deploying one needs an explicit --force.
guard_consultant() {
  local officer="$1"
  local role_yml="$REPO_ROOT/instance/roles/active/$officer.yml"
  [ -f "$role_yml" ] || return 0
  local otype
  otype=$(awk -F': *' '$1=="officer_type"{print $2; exit}' "$role_yml" | tr -d '[:space:]')
  if [ "$otype" = "consultant" ] && [ "$FORCE" != true ]; then
    cat >&2 <<EOF
deploy-mac.sh: refusing --officer $officer — instance/roles/active/$officer.yml
  says officer_type: consultant. Consultants are on-demand sessions, started
  per trigger via:  bash cabinet/scripts/start-officer-mac.sh $officer
  A persistent KeepAlive LaunchAgent would pin them always-on.
  Override deliberately with: deploy-mac.sh --officer $officer --force
EOF
    exit 2
  fi
}

# F0.2 (2026-07-02): the officer fleet is DERIVED from the deployment's roster
# (instance/config/roster.yml — the authoritative, deployment-local seed source
# that bootstrap-roles.sh consumes), never hardcoded. The previous hardcoded
# `cos cto cpo cro coo` deployed the retired 5-officer work-preset fleet — on
# the live portfolio deployment (cos, polads-ceo, stephie-ceo, comms-officer) a
# redeploy would have replaced the WORKING org with a dead one (blueprint §2.3-D,
# red-team amendment RT#13). No roster file ⇒ refuse loudly; never fall back to
# a preset default.
roster_officers() {
  local roster="$REPO_ROOT/instance/config/roster.yml"
  if [ ! -f "$roster" ]; then
    cat >&2 <<EOF
deploy-mac.sh: instance/config/roster.yml not found — cannot derive the officer
  fleet. Seed it first (cabinet-init interview or bootstrap-roles.sh --roster),
  or deploy a single officer explicitly with --officer <name>.
  Refusing to guess: deploying a preset default fleet onto a live deployment is
  exactly the wrong-fleet-redeploy failure this guard exists to prevent.
EOF
    exit 2
  fi
  # Parser contract (mirrors bootstrap-roles.sh): top-level `roster:` opens the
  # section; role slugs are 2-space-indented keys (hyphens allowed); 4-space
  # lines are per-role fields and are skipped.
  awk '
    /^roster:[[:space:]]*$/ { in_roster=1; next }
    in_roster && /^[^[:space:]#]/ { exit }
    in_roster && /^  [a-z0-9-]+:[[:space:]]*$/ {
      slug=$1; sub(/:$/,"",slug); print slug
    }
  ' "$roster"
}

# --stop leg (Wave D / D2 — DESIGN-companion-2026-07-10 §3). Acts on RUNTIME
# truth: the plists actually installed in ~/Library/LaunchAgents — never
# services.yml or the roster, so it is immune to manifest drift (companion
# spec OC-6). Reuses the deploy leg's idempotent bootout primitive; NEVER
# bootstraps; never deletes plist files (redeploy restarts a stopped agent).
stop_one() {
  local plist="$1" label
  label="$(basename "$plist" .plist)"
  if $DRY_RUN; then
    echo "=== WOULD-BOOTOUT $label ==="
    return 0
  fi
  # Idempotent like the deploy leg's own pre-flight bootout: an already-stopped
  # agent is success, not an error (the post-state is "not running" either way).
  # (Comment wording matters here: test_deploy_mac_stop.py source-pins this
  # slice to contain no b-o-o-t-s-t-r-a-p reference at all — the stop leg only
  # ever boots agents OUT.)
  launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
  echo "stopped: $label"
}

stop_agents() {
  local target="$1"
  if [ "$target" = "all" ]; then
    local p matched=false
    for p in "$LAUNCHD_DIR"/com.cabinet.*.plist; do
      [ -e "$p" ] || continue   # unmatched glob → literal pattern; skip
      matched=true
      stop_one "$p"
    done
    if [ "$matched" = false ]; then
      echo "deploy-mac.sh: no com.cabinet.*.plist installed in $LAUNCHD_DIR — nothing to stop"
    fi
    return 0
  fi
  # Single name: accept both spellings the deploy legs write —
  # com.cabinet.<name>.plist (daemons) and com.cabinet.officer.<name>.plist.
  local c plist=""
  for c in "$LAUNCHD_DIR/com.cabinet.$target.plist" \
           "$LAUNCHD_DIR/com.cabinet.officer.$target.plist"; do
    if [ -f "$c" ]; then plist="$c"; break; fi
  done
  if [ -z "$plist" ]; then
    cat >&2 <<EOF
deploy-mac.sh: --stop $target — neither com.cabinet.$target.plist nor
  com.cabinet.officer.$target.plist is installed in $LAUNCHD_DIR.
  --stop acts on runtime truth (installed LaunchAgents); nothing was changed.
EOF
    exit 2
  fi
  stop_one "$plist"
}

# Execute
if [ -n "$STOP" ]; then
  stop_agents "$STOP"
  exit 0
fi
if [ "$ALL" = true ]; then
  OFFICERS_LIST=$(roster_officers)
  [ -n "$OFFICERS_LIST" ] || { echo "deploy-mac.sh: roster.yml parsed to an empty officer list — refusing." >&2; exit 2; }
  for o in $OFFICERS_LIST; do guard_consultant "$o"; deploy_officer "$o"; done
  # Daemon leg (corrected 2026-07-04, lane/config-0705). cabinet/services.yml
  # is THE fleet manifest (F0.4): daemon/watchdog plists are rendered from it
  # by cabinet/scripts/generate-plists.py (render-only by security contract —
  # it never calls launchctl). The previous hardcoded 12-daemon list here
  # installed TEN services absent from both services.yml AND the live fleet
  # (heartbeat-watchdog, cost-summary, worktree-listener, mission-supervisor,
  # task-sync, role-evals-weekly, outbox-relay, ovi-weekly,
  # self-improvement-loop, chrome-profile) — the same wrong-fleet-redeploy
  # hazard F0.2 fixed for officers, and mission-supervisor in particular would
  # resurrect 5-min push routing against the Captain's pull-only ruling (see
  # .claude/skills/cabinet-route-tasks/). --all now installs only the
  # manifest-backed template daemons; the retired templates stay on disk and
  # remain individually deployable via an explicit `--daemon <name>` (a
  # deliberate operator act, not a default).
  #
  # TODO(F0.4 follow-up — full reconcile): teach deploy-mac.sh to bootstrap
  # cabinet/launchd/generated/*.plist (run generate-plists.py, then
  # launchctl bootstrap each non-officer service) so --all installs the FULL
  # manifest fleet — including replacing the invalid-XML limit-reset-watchdog
  # template render, which services.yml notes should be superseded by its
  # generated plist at next deploy. Deferred here: new launchctl machinery on
  # the LIVE fleet needs its own tested change, not a docs/CI lane rider.
  for d in \
    limit-reset-watchdog \
    dashboard; do
    deploy_daemon "$d"
  done
  cat >&2 <<'EOF'
deploy-mac.sh: NOTE — --all installs officers (roster-derived) plus the two
  manifest-backed template daemons (limit-reset-watchdog, dashboard). The rest
  of the daemon/watchdog fleet is owned by cabinet/services.yml: render with
  `python3.12 cabinet/scripts/generate-plists.py` and bootstrap the generated
  plists deliberately (per-plist header comments carry the install commands).
  Legacy templates (heartbeat-watchdog, cost-summary, worktree-listener,
  mission-supervisor, task-sync, role-evals-weekly, outbox-relay, ovi-weekly,
  self-improvement-loop, chrome-profile) are NOT in the manifest and are no
  longer auto-installed; use --daemon <name> only if you mean it.
EOF
  # dashboard-kiosk is OPT-IN (needs a physical monitor on the Mac mini).
  # Office-display deployments add it explicitly:
  #   bash cabinet/scripts/deploy-mac.sh --daemon dashboard-kiosk
  # Headless servers skip it; the dashboard server above binds
  # CABINET_DASHBOARD_HOST (default 0.0.0.0 — unchanged) and so stays
  # reachable over Tailscale at http://<host>:3100 regardless. Loopback-only
  # opt-in: CABINET_DASHBOARD_HOST=127.0.0.1 in cabinet/.env; flipping the
  # DEFAULT is captain-gated (CC-LOOP) — see cabinet/docs/mac-mini-deploy-runbook.md.
else
  # --officer and --daemon are independent selectors and may be combined in
  # one invocation (previously the elif chain silently dropped --daemon
  # whenever --officer was present).
  DEPLOYED_ANY=false
  if [ "$OFFICER" = "all" ]; then
    OFFICERS_LIST=$(roster_officers)
    [ -n "$OFFICERS_LIST" ] || { echo "deploy-mac.sh: roster.yml parsed to an empty officer list — refusing." >&2; exit 2; }
    for o in $OFFICERS_LIST; do guard_consultant "$o"; deploy_officer "$o"; done
    DEPLOYED_ANY=true
  elif [ -n "$OFFICER" ]; then
    guard_consultant "$OFFICER"
    deploy_officer "$OFFICER"
    DEPLOYED_ANY=true
  fi
  if [ -n "$DAEMON" ]; then
    deploy_daemon "$DAEMON"
    DEPLOYED_ANY=true
  fi
  if [ "$DEPLOYED_ANY" = false ]; then
    echo "Usage: deploy-mac.sh [--officer <name>|all] [--daemon <name>] [--all] [--stop <name>|all] [--dry-run] [--force]" >&2
    exit 64
  fi
fi

exit 0
