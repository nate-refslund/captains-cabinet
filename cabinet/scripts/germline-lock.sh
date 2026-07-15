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
#        bash cabinet/scripts/germline-lock.sh --backend ro-mount <any>  # docker target: no-op + host-side ritual (AX-4)
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
  # --- officer clean-env / sandbox / observe / egress boundary ---
  "cabinet/scripts/start-officer-mac.sh"
  "cabinet/scripts/start-officer.sh"
  "cabinet/scripts/gen-officer-mcp-config.py"
  "cabinet/scripts/append-interface.sh"
  "cabinet/scripts/captain-law-broker.py"
  "cabinet/scripts/egress-guard.sh"
  "cabinet/scripts/egress-proxy.py"
  "cabinet/launchd/com.cabinet.egress-proxy.template.plist"
  "cabinet/scripts/observe-only.sh"
  "cabinet/scripts/lib/officer-env.py"
  "cabinet/scripts/lib/officer-env.sh"
  "cabinet/scripts/lib/officer-sandbox.sh"
  "framework/comms/channel_adapter.py"
  "framework/comms/tools.py"
  "framework/comms/mcp/server.py"
  "framework/comms/adapters/telegram.py"
  "instance/config/egress.yml"
  # --- judged authority code (grants authority / renders judgment) ---
  "framework/authority/classifier.py"
  "framework/authority/lane.py"
  "framework/authority/matrix.py"
  "framework/authority/veto.py"
  "framework/authority/deploy_classifier.py"
  "framework/fidelity/graduation.py"
  "framework/authority/policy_engine.py"
  "framework/frontdoor/action_exec.py"
  "framework/frontdoor/action_undo.py"
  "framework/frontdoor/actfirst_canary.py"
  "framework/frontdoor/veto_registry.py"
  "framework/frontdoor/tell_surface.py"
  "framework/frontdoor/calendar_template.py"
  "framework/acting/action_lane.py"
  "framework/acting/run_action_lane.py"
  "framework/frontdoor/channel.py"
  "framework/attention/situation.py"
  "framework/attention/feed.py"
  "framework/attention/acted_overlay.py"
  # --- war-room census + admission plane (command-center Stage 1) ---
  "framework/attention/situations.py"
  "framework/attention/queue.py"
  "framework/attention/hygiene.py"
  "framework/attention/queue_card.py"
  # --- judged config (NOT runtime-written) + rules ---
  "instance/config/act-first-surfaces.yml"
  "cabinet/mcp-scope.yml"
  "cabinet/officer-capabilities.conf"
  ".claude/rules/brain-bridge.md"
  ".claude/rules/courses-of-action.md"
  # --- sovereign-posture kernel (amendment 2026-07-05): code that resolves
  #     posture, mints/loads ceiling grants, files needs, or applies gate
  #     output. The two attestation configs are DEPLOYMENT-CREATED at apply
  #     time — lock skips absent paths, so listing them before they exist is
  #     safe and means the boundary arms the moment they land. ---
  "framework/authority/posture.py"
  "framework/authority/grants.py"
  "framework/authority/needs.py"
  "framework/learning/gate.py"
  "framework/learning/apply_watch.py"
  "cabinet/scripts/grant-apply.sh"
  "instance/config/posture.yml"
  "instance/config/standing-grants.yml"
  # --- ROOT-EXECUTED apply lane (D15, SOV-9a): the DARK germline code-apply
  #     script (sudo entrypoint + root daemon), its LaunchDaemon definition
  #     (ProgramArguments run as root on load), and the watch ledger whose
  #     rows cmd_watch executes as a root git apply -R — a forged row mints
  #     a root write, so the ledger is locked, never SKIP. Born at the first
  #     Captain-armed apply; lock skips absent paths. ---
  "cabinet/scripts/gate-apply.sh"
  "cabinet/launchd/com.cabinet.gate-apply.plist"
  "shared/interfaces/gate-apply-watch.jsonl"
  # --- cabinet-axes kernel (amendment 2026-07-05): the earn_up rung-ladder
  #     overlay (a forged rung map LIFTS verdicts), the axis-branching
  #     allowlist (framework/policies/ dir-cover already carries it — not
  #     re-listed here), the axes-contract rule, the extension gate pair
  #     (schema + validator), and the live Captain-locked rung-grant file
  #     (deployment-created at the first `grant rung`; lock skips absent —
  #     the .example stays unlocked). instance/config/posture-narrow is
  #     DELIBERATELY absent everywhere: it can only NARROW (fail-safe) and
  #     the Captain's binder verb writes it at runtime. ---
  "framework/learning/trust_ladder.py"
  ".claude/rules/axes-contract.md"
  "framework/schemas/extension-manifest.schema.json"
  "cabinet/scripts/validate-extension.sh"
  "instance/config/trust-ladder.yml"
  # --- evidence recorder v1 trusted integration seam ---
  "framework/onboarding/journey.py"
  "framework/schemas/evidence-event.schema.json"
  "cabinet/dashboard/src/lib/onboarding/bridge.ts"
  "cabinet/dashboard/src/lib/onboarding/telegram.ts"
  "cabinet/dashboard/src/app/api/telegram/provisioning-webhook/route.ts"
  "cabinet/dashboard/src/components/onboarding/journey-card.tsx"
  "cabinet/companion/main.swift"
  "cabinet/scripts/evidence-read.sh"
)
# whole directories locked -R (blocks edit AND new-file/rename/unlink inside —
# closes the `cp evil framework/policies/newfile` class at the FS layer)
DIRS=(
  "cabinet/scripts/hooks"      # the enforcer hooks (pre-tool-use.sh lives here)
  "framework/policies"         # typed policy rules
  "memory/golden-evals"        # the behavioral judges
  "instance/config/policies"   # D8: the instance policy layer — no officer may drop a widening policy file
  "instance/config/posture-presets"  # axes: shipped axis points — a forged preset seeds a widened ruling
  "framework/evidence"       # recorder + independent verifier + redaction/repair policy
  "cabinet/dashboard/src/app/api/onboarding"  # server-side onboarding/evidence seam
)
# DELIBERATELY NOT LOCKED — a sanctioned Python API appends to these at runtime
# (veto_registry.py / action_lessons.py / needs.py, same uid). Forging one only
# DEMOTES, records, or FILES A NEED (DoS / advisory) — it can never GRANT
# authority (grants live in the schg-locked standing-grants.yml, written only by
# grant-apply.sh in an unlock window), so the residual is fail-safe. schg here
# would break the learning + demotion + needs loops.
SKIP=(
  "shared/interfaces/captain-vetoes.yml"
  "shared/interfaces/action-lessons.yml"
  "shared/interfaces/needs-ledger.jsonl"
  "instance/evidence/v1/"
)

need_root() { [ "$(id -u)" = "0" ] || { echo "ERROR: '$1' needs root (schg is system-immutable). Re-run: sudo bash cabinet/scripts/germline-lock.sh $1" >&2; exit 2; }; }

# --backend ro-mount (docker deployment target, axes spec 2026-07-05 §3):
# schg does not exist in a Linux container — there the boundary is the HOST's
# read-only bind mounts (compose :ro over the germline dirs + posture.yml +
# standing-grants.yml), which the container cannot remount at any privilege.
# Every command is a deliberate NO-OP under this backend; the lock/unlock
# ritual happens host-side. Runbook: cabinet/deploy/docker/README.md
if [ "${1:-}" = "--backend" ]; then
  case "${2:-}" in
    ro-mount|ro_mount)
      echo "germline-lock: backend ro-mount — nothing to chflags in a container."
      echo "The boundary is the host's read-only bind mounts. To edit germline:"
      echo "  1. on the HOST, edit the mounted files (unlock schg there first if the host arms it)"
      echo "  2. docker compose restart cabinet"
      echo "Runbook: cabinet/deploy/docker/README.md"
      exit 0 ;;
    schg) shift 2 ;;   # the explicit default — fall through to normal behavior
    *) echo "usage: germline-lock.sh [--backend schg|ro-mount] lock|unlock [path]|status|verify" >&2; exit 1 ;;
  esac
fi

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
    if [ -e /.dockerenv ]; then
      echo "NOTE: container detected — schg is meaningless here; the boundary is the host-side ro mounts."
      echo "      Run: bash cabinet/scripts/germline-lock.sh --backend ro-mount status (runbook: cabinet/deploy/docker/README.md)"
    fi
    locked=0; unlocked=0
    for f in "${FILES[@]}"; do
      [ -e "$f" ] || continue
      # macOS immutable flags are exposed only by ls -O.
      # shellcheck disable=SC2010
      if ls -lO "$f" 2>/dev/null | grep -q schg; then locked=$((locked+1)); else unlocked=$((unlocked+1)); echo "UNLOCKED  $f"; fi
    done
    for d in "${DIRS[@]}"; do
      [ -d "$d" ] || continue
      # macOS immutable flags are exposed only by ls -O.
      # shellcheck disable=SC2010
      if ls -ldO "$d" 2>/dev/null | grep -q schg; then locked=$((locked+1)); else unlocked=$((unlocked+1)); echo "UNLOCKED  $d/"; fi
    done
    echo "--- $locked locked, $unlocked unlocked (of ${#FILES[@]} files + ${#DIRS[@]} dirs) ---"
    [ "$unlocked" = 0 ] && echo "BOUNDARY ARMED" || echo "BOUNDARY NOT FULLY ARMED"
    ;;
  verify)
    # non-root proof the lock holds: try to write a locked file, expect failure
    probe="framework/authority/classifier.py"
    # macOS immutable flags are exposed only by ls -O.
    # shellcheck disable=SC2010
    if ! ls -lO "$probe" 2>/dev/null | grep -q schg; then echo "verify: $probe is NOT locked — run lock first"; exit 1; fi
    if printf '' >> "$probe" 2>/dev/null; then echo "VERIFY FAILED — wrote to locked $probe (boundary NOT holding)"; exit 1
    else echo "VERIFY OK — write to schg-locked $probe was refused (Operation not permitted)"; fi
    ;;
  *) echo "usage: germline-lock.sh [--backend schg|ro-mount] lock|unlock [path]|status|verify" >&2; exit 1 ;;
esac
