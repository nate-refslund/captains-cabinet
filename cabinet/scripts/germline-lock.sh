#!/bin/bash
# germline-lock.sh — the REAL germline boundary: macOS system-immutable (schg)
# on the enforcer + judge plane, so the officer uid (same user as the Captain,
# no passwordless sudo) physically cannot write them — no string hook required.
#
# WHY schg AND NOT uchg (empirically verified 2026-07-04):
#   uchg (user-immutable)   — the FILE OWNER can `chflags nouchg` then write it
#                             WITHOUT sudo. Officers run as the owner => they
#                             could unlock-then-forge. INSUFFICIENT.
#   schg (system-immutable) — only root may SET or CLEAR it. Officers have no
#                             passwordless sudo (`sudo -n true` fails), so they
#                             can neither forge the file NOR clear the flag.
#                             A germline change becomes a DELIBERATE Captain
#                             unlock. This IS the complete boundary a
#                             Turing-complete shell can never give a string hook.
#
# The string hook (cabinet/scripts/hooks/pre-tool-use.sh §5/§5b) remains as
# defense-in-depth — but it is INSIDE this locked set, so it too can no longer
# be forged (the sharpest hole: an officer overwriting the enforcer itself).
#
# USAGE (schg needs root — run under sudo):
#   sudo bash cabinet/scripts/germline-lock.sh lock     # arm the boundary
#   sudo bash cabinet/scripts/germline-lock.sh unlock   # Captain edit window
#   sudo bash cabinet/scripts/germline-lock.sh unlock <path>   # one file
#        bash cabinet/scripts/germline-lock.sh status   # who is locked (no sudo)
#        bash cabinet/scripts/germline-lock.sh verify    # prove a locked file rejects a write (no sudo)
#
# OPERATIONAL PATTERN: unlock -> edit/commit germline -> lock. Because schg
# blocks git rename/checkout on these paths, do all commits while UNLOCKED and
# re-lock when returning to autonomous running.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || { echo "cannot cd $REPO" >&2; exit 1; }

# ---- THE LOCKED SET — keep in lockstep with pre-tool-use.sh §5 case list +
#      §5b GERM_PATH_RE. Two additions beyond the hook's judged set: the
#      ENFORCER TRIAD (settings.json + the hooks dir + policy-shadow.py) whose
#      forge disables the perimeter itself, and this script. --------------------
FILES=(
  # --- enforcer: forging any of these disables/subverts the perimeter ---
  ".claude/settings.json"
  "cabinet/scripts/policy-shadow.py"
  "cabinet/scripts/kill-switch.sh"
  "cabinet/scripts/germline-lock.sh"
  # --- judged authority code (grants authority / renders judgment) ---
  "framework/authority/classifier.py"
  "framework/authority/lane.py"
  "framework/authority/matrix.py"
  "framework/authority/veto.py"
  "framework/authority/deploy_classifier.py"
  "framework/fidelity/graduation.py"
  "cabinet/scripts/lib/policy_engine.py"
  "framework/frontdoor/action_exec.py"
  "framework/frontdoor/action_undo.py"
  "framework/frontdoor/actfirst_canary.py"
  "framework/frontdoor/veto_registry.py"
  "framework/frontdoor/tell_surface.py"
  "framework/frontdoor/calendar_template.py"
  "framework/acting/action_lane.py"
  "framework/acting/run_action_lane.py"
  # --- judged config (NOT runtime-written) + rules ---
  "instance/config/act-first-surfaces.yml"
  "cabinet/mcp-scope.yml"
  "cabinet/officer-capabilities.conf"
  ".claude/rules/brain-bridge.md"
  ".claude/rules/courses-of-action.md"
)
# whole directories locked -R (blocks edit AND new-file/rename/unlink inside —
# closes the `cp evil framework/policies/newfile` class at the FS layer)
DIRS=(
  "cabinet/scripts/hooks"      # the enforcer hooks (pre-tool-use.sh lives here)
  "framework/policies"         # typed policy rules
  "memory/golden-evals"        # the behavioral judges
)
# DELIBERATELY NOT LOCKED — a sanctioned Python API appends to these at runtime
# (veto_registry.py / action_lessons.py, same uid). Forging one only DEMOTES or
# records (DoS / advisory) — it can never GRANT authority, so the residual is
# fail-safe. schg here would break the learning + demotion loops.
SKIP=(
  "shared/interfaces/captain-vetoes.yml"
  "shared/interfaces/action-lessons.yml"
)

need_root() { [ "$(id -u)" = "0" ] || { echo "ERROR: '$1' needs root (schg is system-immutable). Re-run: sudo bash cabinet/scripts/germline-lock.sh $1" >&2; exit 2; }; }

cmd="${1:-status}"
case "$cmd" in
  lock)
    need_root lock
    n=0
    for f in "${FILES[@]}"; do
      if [ -e "$f" ]; then chflags schg "$f" && n=$((n+1)) || echo "WARN could not lock $f" >&2
      else echo "skip (absent): $f"; fi
    done
    for d in "${DIRS[@]}"; do
      if [ -d "$d" ]; then chflags -R schg "$d" && n=$((n+1)) || echo "WARN could not lock $d" >&2
      else echo "skip (absent dir): $d"; fi
    done
    echo "LOCKED $n germline targets (schg). Runtime-written fail-safe files left writable: ${SKIP[*]}"
    echo "To edit germline: sudo bash cabinet/scripts/germline-lock.sh unlock"
    ;;
  unlock)
    need_root unlock
    tgt="${2:-}"
    if [ -n "$tgt" ]; then
      chflags noschg "$tgt" 2>/dev/null || chflags -R noschg "$tgt"
      echo "UNLOCKED $tgt — re-lock with: sudo bash cabinet/scripts/germline-lock.sh lock"
      exit 0
    fi
    for f in "${FILES[@]}"; do [ -e "$f" ] && chflags noschg "$f"; done
    for d in "${DIRS[@]}"; do [ -d "$d" ] && chflags -R noschg "$d"; done
    echo "UNLOCKED all germline targets. RE-LOCK when done: sudo bash cabinet/scripts/germline-lock.sh lock"
    ;;
  status)
    locked=0; unlocked=0
    for f in "${FILES[@]}"; do
      [ -e "$f" ] || continue
      if ls -lO "$f" 2>/dev/null | grep -q schg; then locked=$((locked+1)); else unlocked=$((unlocked+1)); echo "UNLOCKED  $f"; fi
    done
    for d in "${DIRS[@]}"; do
      [ -d "$d" ] || continue
      if ls -ldO "$d" 2>/dev/null | grep -q schg; then locked=$((locked+1)); else unlocked=$((unlocked+1)); echo "UNLOCKED  $d/"; fi
    done
    echo "--- $locked locked, $unlocked unlocked (of ${#FILES[@]} files + ${#DIRS[@]} dirs) ---"
    [ "$unlocked" = 0 ] && echo "BOUNDARY ARMED" || echo "BOUNDARY NOT FULLY ARMED"
    ;;
  verify)
    # non-root proof the lock holds: try to write a locked file, expect failure
    probe="framework/authority/classifier.py"
    if ! ls -lO "$probe" 2>/dev/null | grep -q schg; then echo "verify: $probe is NOT locked — run lock first"; exit 1; fi
    if printf '' >> "$probe" 2>/dev/null; then echo "VERIFY FAILED — wrote to locked $probe (boundary NOT holding)"; exit 1
    else echo "VERIFY OK — write to schg-locked $probe was refused (Operation not permitted)"; fi
    ;;
  *) echo "usage: germline-lock.sh lock|unlock [path]|status|verify" >&2; exit 1 ;;
esac
