#!/bin/bash
# deploy-mac.sh — Orchestrate Mac native Cabinet deployment.
#
# Renders roster officers from the officer template and enabled services from
# cabinet/services.yml, writes them to ~/Library/LaunchAgents/, then reconciles
# launchd to that exact set.
#
# Usage:
#   bash cabinet/scripts/deploy-mac.sh --officer <officer>     # deploy one officer
#   bash cabinet/scripts/deploy-mac.sh --officer all           # deploy the roster fleet (instance/config/roster.yml)
#   bash cabinet/scripts/deploy-mac.sh --daemon <name>         # deploy one template-based non-officer service
#                                                              #   (any cabinet/launchd/com.cabinet.<name>.template.plist)
#   bash cabinet/scripts/deploy-mac.sh --officer X --daemon Y  # both in one invocation
#   bash cabinet/scripts/deploy-mac.sh --all                   # reconcile to EXACTLY roster officers + every
#                                                              #   enabled services.yml row; disabled/legacy agents
#                                                              #   are booted out and parked; the separately managed
#                                                              #   egress proxy is preserved
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
GENERATED_DIR="$TEMPLATES_DIR/generated"
LAUNCHCTL="${CABINET_LAUNCHCTL:-launchctl}"
BOOTOUT_DELAY_S="${CABINET_DEPLOY_BOOTOUT_DELAY_S:-0.2}"
DEPLOY_TMP=""
EXPECTED_LABELS_FILE=""
ALLOWED_LABELS_FILE=""

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

if ! $DRY_RUN && [ -z "$STOP" ]; then
  mkdir -p "$LAUNCHD_DIR" "$LOGS_DIR"
fi

cleanup() {
  [ -z "$DEPLOY_TMP" ] || rm -rf "$DEPLOY_TMP"
}
trap cleanup EXIT

# Populate .claude/agents/ from preset before LaunchAgent boots officers.
# start-officer-mac.sh probes for $REPO_ROOT/.claude/agents/$OFFICER.md to gate
# its --agent flag; without this, native_agent=false on every fresh deployment.
# load-preset.sh also does this inline, but at deploy time we may not have a Neon
# connection yet — sync-agents.sh is the agent-only step that runs unconditionally.
# Idempotent; safe to re-run. Skipped on --dry-run: a dry run must not mutate
# anything, including the generated .claude/agents/ directory.
sync_agents() {
  if $DRY_RUN; then
    echo "deploy-mac.sh: --dry-run — skipping sync-agents.sh (no writes)"
  elif ! bash "$REPO_ROOT/cabinet/scripts/sync-agents.sh" 2>&1; then
    echo "deploy-mac.sh: sync-agents.sh failed — refusing to boot a fleet with incomplete officer identities" >&2
    return 2
  fi
}

ensure_deploy_tmp() {
  if [ -z "$DEPLOY_TMP" ]; then
    DEPLOY_TMP="$(mktemp -d "${TMPDIR:-/tmp}/cabinet-deploy.XXXXXX")"
  fi
}

wait_for_unloaded() {
  local label="$1" attempt=0
  while "$LAUNCHCTL" print "gui/$(id -u)/$label" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 20 ] || return 1
    sleep "$BOOTOUT_DELAY_S"
  done
  return 0
}

# Replace and reload one plist with a per-service rollback. If the new job
# cannot bootstrap, restore the previous installed plist and (when it was
# loaded before) restore that previous job before returning failure.
install_plist_file() {
  local source="$1" final="$2" label="$3"
  local staged backup had_final=false was_loaded=false
  ensure_deploy_tmp
  backup="$DEPLOY_TMP/backup.$label.plist"
  staged="$final.tmp.$$"
  if [ -e "$final" ]; then
    cp "$final" "$backup"
    had_final=true
  fi
  if "$LAUNCHCTL" print "gui/$(id -u)/$label" >/dev/null 2>&1; then
    was_loaded=true
  fi

  cp "$source" "$staged"
  chmod 644 "$staged"
  mv -f "$staged" "$final"

  if [ "$was_loaded" = true ]; then
    "$LAUNCHCTL" bootout "gui/$(id -u)" "$final" 2>/dev/null || true
    if ! wait_for_unloaded "$label"; then
      echo "deploy-mac.sh: bootout failed for $label; installed plist restored" >&2
      [ "$had_final" != true ] || cp "$backup" "$final"
      return 2
    fi
  fi

  if "$LAUNCHCTL" bootstrap "gui/$(id -u)" "$final"; then
    echo "deployed: $label"
    return 0
  fi

  echo "deploy-mac.sh: bootstrap failed for $label — attempting per-service rollback" >&2
  if [ "$had_final" = true ]; then
    cp "$backup" "$final"
    if [ "$was_loaded" = true ]; then
      "$LAUNCHCTL" bootstrap "gui/$(id -u)" "$final" || {
        echo "deploy-mac.sh: ROLLBACK FAILED for $label; manual recovery required" >&2
        return 3
      }
    fi
  else
    /bin/rm -f "$final"
  fi
  return 2
}

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

  ensure_deploy_tmp
  local staged="$DEPLOY_TMP/rendered.$label.plist"
  echo "$rendered" > "$staged"
  chmod 644 "$staged"
  install_plist_file "$staged" "$final" "$label"
}

# Install a plist already rendered and linted by generate-plists.py. The
# installed copy is replaced atomically before launchd sees it.
deploy_generated_plist() {
  local source="$1" label final
  label="$(basename "$source" .plist)"
  final="$LAUNCHD_DIR/$label.plist"

  if $DRY_RUN; then
    echo "=== WOULD-WRITE $final (generated from enabled services.yml row) ==="
    cat "$source"
    echo "=== WOULD-BOOTSTRAP $label ==="
    return 0
  fi

  install_plist_file "$source" "$final" "$label"
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
# a live portfolio deployment (e.g. cos, acme-ceo, widgets-ceo, comms-officer) a
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
  local py
  py="$(python_for_generator)" || return 2
  # Shared abstraction: Cabinet Doctor and the recovery drill use these same
  # synthesized rows. Validate the label before returning a shell token.
  "$py" - "$REPO_ROOT" <<'PY'
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
        raise SystemExit(f"deploy-mac.sh: unsafe roster-derived officer label: {label!r}")
    print(match.group(1))
PY
}

python_for_generator() {
  local candidate="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
  if command -v "$candidate" >/dev/null 2>&1; then
    printf '%s\n' "$candidate"
  elif command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    echo "deploy-mac.sh: Python 3 is required to render services.yml" >&2
    return 1
  fi
}

# Validate and render the complete desired fleet before changing launchd.
# The expected-label file is also the reconciliation allowlist. The egress
# proxy is intentionally allowlisted, not installed: egress-guard.sh owns its
# lifecycle and a fleet deploy must never create a moment without enforcement.
prepare_exact_fleet() {
  local py render_dir duplicate
  ensure_deploy_tmp
  EXPECTED_LABELS_FILE="$DEPLOY_TMP/expected-labels"
  ALLOWED_LABELS_FILE="$DEPLOY_TMP/allowed-labels"
  : > "$EXPECTED_LABELS_FILE"

  py="$(python_for_generator)" || return 2
  OFFICERS_LIST="$(roster_officers)" || return 2
  [ -n "$OFFICERS_LIST" ] || {
    echo "deploy-mac.sh: roster.yml missing or parsed to an empty officer list — refusing." >&2
    return 2
  }
  local o
  for o in $OFFICERS_LIST; do
    guard_consultant "$o"
    printf 'com.cabinet.officer.%s\n' "$o" >> "$EXPECTED_LABELS_FILE"
  done

  if $DRY_RUN; then
    render_dir="$DEPLOY_TMP/generated"
  else
    render_dir="$GENERATED_DIR"
  fi
  "$py" "$REPO_ROOT/cabinet/scripts/generate-plists.py" \
    --output-dir "$render_dir"

  local p
  for p in "$render_dir"/com.cabinet.*.plist; do
    [ -e "$p" ] || continue
    basename "$p" .plist >> "$EXPECTED_LABELS_FILE"
  done

  duplicate="$(sort "$EXPECTED_LABELS_FILE" | uniq -d | head -n 1)"
  if [ -n "$duplicate" ]; then
    echo "deploy-mac.sh: duplicate desired launchd label: $duplicate — refusing before mutation" >&2
    return 2
  fi
  sort -o "$EXPECTED_LABELS_FILE" "$EXPECTED_LABELS_FILE"
  if grep -qxF "com.cabinet.egress-proxy" "$EXPECTED_LABELS_FILE"; then
    echo "deploy-mac.sh: services.yml/roster claims reserved label com.cabinet.egress-proxy — egress-guard.sh owns it" >&2
    return 2
  fi
  cp "$EXPECTED_LABELS_FILE" "$ALLOWED_LABELS_FILE"
  printf '%s\n' "com.cabinet.egress-proxy" >> "$ALLOWED_LABELS_FILE"
  sort -u -o "$ALLOWED_LABELS_FILE" "$ALLOWED_LABELS_FILE"
  EXACT_RENDER_DIR="$render_dir"
}

is_allowed_label() {
  grep -qxF "$1" "$ALLOWED_LABELS_FILE"
}

# Remove every installed/loaded Cabinet job outside the manifest+roster set.
# Installed plists are parked beside the live file with a .disabled suffix so
# the rollback evidence remains available but launchd cannot rediscover it.
reconcile_unexpected_agents() {
  local candidates="$DEPLOY_TMP/candidate-labels" label plist target
  : > "$candidates"

  for plist in "$LAUNCHD_DIR"/com.cabinet.*.plist; do
    [ -e "$plist" ] || continue
    basename "$plist" .plist >> "$candidates"
  done
  if command -v "$LAUNCHCTL" >/dev/null 2>&1; then
    "$LAUNCHCTL" list 2>/dev/null | awk '$3 ~ /^com\.cabinet\./ {print $3}' >> "$candidates" || {
      if ! $DRY_RUN; then
        echo "deploy-mac.sh: launchctl list failed — cannot prove exact fleet" >&2
        return 2
      fi
    }
  elif ! $DRY_RUN; then
    echo "deploy-mac.sh: launchctl not found — cannot reconcile exact fleet" >&2
    return 2
  fi
  sort -u -o "$candidates" "$candidates"

  while IFS= read -r label; do
    [ -n "$label" ] || continue
    case "$label" in
      *[!a-z0-9.-]*)
        echo "deploy-mac.sh: unsafe launchd label from runtime inventory: $label" >&2
        return 2
        ;;
    esac
    is_allowed_label "$label" && continue
    plist="$LAUNCHD_DIR/$label.plist"
    target="$plist.disabled"
    if $DRY_RUN; then
      echo "=== WOULD-BOOTOUT unexpected $label ==="
      [ ! -e "$plist" ] || echo "=== WOULD-PARK $plist -> $target ==="
      continue
    fi

    if [ -e "$plist" ]; then
      "$LAUNCHCTL" bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
    else
      "$LAUNCHCTL" bootout "gui/$(id -u)/$label" 2>/dev/null || true
    fi
    if ! wait_for_unloaded "$label"; then
      echo "deploy-mac.sh: unexpected job $label remained loaded after bootout" >&2
      return 2
    fi
    if [ -e "$plist" ]; then
      mv -f "$plist" "$target"
      echo "parked unexpected plist: $target"
    else
      echo "booted out unexpected loaded job: $label"
    fi
  done < "$candidates"
}

verify_exact_fleet() {
  local label candidates="$DEPLOY_TMP/post-labels"
  while IFS= read -r label; do
    [ -n "$label" ] || continue
    if ! "$LAUNCHCTL" print "gui/$(id -u)/$label" >/dev/null 2>&1; then
      echo "deploy-mac.sh: post-reconcile verification missing expected job $label" >&2
      return 2
    fi
    if [ ! -f "$LAUNCHD_DIR/$label.plist" ]; then
      echo "deploy-mac.sh: post-reconcile verification missing expected plist $label.plist" >&2
      return 2
    fi
  done < "$EXPECTED_LABELS_FILE"

  : > "$candidates"
  "$LAUNCHCTL" list 2>/dev/null | awk '$3 ~ /^com\.cabinet\./ {print $3}' >> "$candidates" || return 2
  for label in "$LAUNCHD_DIR"/com.cabinet.*.plist; do
    [ -e "$label" ] || continue
    basename "$label" .plist >> "$candidates"
  done
  sort -u -o "$candidates" "$candidates"
  while IFS= read -r label; do
    [ -n "$label" ] || continue
    if ! is_allowed_label "$label"; then
      echo "deploy-mac.sh: post-reconcile verification found unexpected job/plist $label" >&2
      return 2
    fi
  done < "$candidates"
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
  # Fail-before-mutation: validate the roster, consultant policy, the whole
  # manifest and every generated plist before syncing agents or touching
  # launchd. Then park retired authority, install the deterministic services,
  # and boot officers only after their supporting fleet is present.
  prepare_exact_fleet
  sync_agents
  reconcile_unexpected_agents
  for p in "$EXACT_RENDER_DIR"/com.cabinet.*.plist; do
    [ -e "$p" ] || continue
    deploy_generated_plist "$p"
  done
  for o in $OFFICERS_LIST; do deploy_officer "$o"; done
  if ! $DRY_RUN; then verify_exact_fleet; fi
  if $DRY_RUN; then
    echo "deploy-mac.sh: dry-run plan complete ($(wc -l < "$EXPECTED_LABELS_FILE" | tr -d ' ') manifest+roster jobs); no runtime changes; egress untouched"
  else
    echo "deploy-mac.sh: exact fleet reconciled ($(wc -l < "$EXPECTED_LABELS_FILE" | tr -d ' ') manifest+roster jobs); egress proxy preserved"
  fi

  # dashboard-kiosk is intentionally outside services.yml, so exact --all
  # parks it. Installing it with --daemon is diagnostic-only and makes Doctor
  # red until it is removed or promoted into the manifest. The dashboard server
  # in services.yml binds
  # CABINET_DASHBOARD_HOST (default 127.0.0.1 — loopback-only since the
  # CC-LOOP ruling, 2026-07-12) so it is NOT reachable over the tailnet by
  # default. Remote reach: front it with `tailscale serve` (the blessed
  # path), or opt out with CABINET_DASHBOARD_HOST=0.0.0.0 in cabinet/.env —
  # a live box that needs plain http://<host>:3100 reach sets that BEFORE
  # this flip deploys; see cabinet/docs/mac-mini-deploy-runbook.md.
else
  sync_agents
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
