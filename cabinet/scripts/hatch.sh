#!/bin/bash
# hatch.sh — ONE command to hatch a Captain's Cabinet (v0).
#
# THE THIN ORCHESTRATOR of the already-rehearsed chain. It runs the exact
# sequence of docs/runbooks/mini-hatch-tonight-2026-07-07.md and NEVER
# reimplements a step (design of record:
# docs/plans/world-onboarding-hatching-2026-07-09.md §7.3 — "hatch.sh
# ORCHESTRATES, never reimplements"). Every step is an existing, proven
# script; hatch.sh adds only ordering, flags, the flight recorder, and
# honest failure reporting.
#
# The chain (v0):
#   1. host bootstrap        setup-env.sh --defaults (with --defaults) +
#                            setup-mac.sh --fast   (clean-room: --check)
#   2. instance generation   generate-instance.py [--defaults]
#                            (inherited instance -> the rehearsed --adopt path)
#   3. activation            active-preset + bootstrap-roles.sh + load-preset.sh
#   4. proofs                roster-authz (every officer THIS hatch rostered is
#                            authorized by the germline pair) · P-a null-hatch.sh ·
#                            P-b clean-room pytest subset · P-c dry renders ·
#                            P-d kill-switch drill (--with-drill)
#   5. FIRST RECEIPT         first-briefing.sh --local (prints where it landed)
#      + DEMO receipt        emit-demo-receipt.sh — one LABELED demo receipt
#                            (real schema path + real renderer, NEVER
#                            journaled) so the Captain sees receipt anatomy
#                            in minute one
#   6. move-in               DEFERRED by default (--no-launchd is the v0 default;
#                            --with-launchd runs runbook section 6)
#
# GERMLINE steps (cabinet/mcp-scope.yml, cabinet/officer-capabilities.conf)
# are NEVER automated — they print as a numbered end-of-run CHECKLIST for the
# human (hatch-lib/errands.sh; "errand notes" in the code, plain words on screen),
# exactly like BotFather tokens and TCC clicks (design doc §3). And because
# they are never automated, the hatch must never DEPEND on them: since
# roster-authz (2026-07-26) generate-instance.py rosters a lane CEO only once
# those two files already authorize it, so the chain below — including
# [proof-a], whose lockstep gate fails any officer hired without those rows —
# completes Chair-only with zero human errands. Applying the rows and re-running
# the generator is how a lane CEO gets hired, always as a post-hatch act.
#
# CLEAN-ROOM CONTAINMENT (--clean-room; 2026-07-10 fix, PC-B verifier
# follow-up (a)): CABINET_RUNTIME_DIR is exported into the run's scratch
# area beside the flight log (<log dir>/cabinet-runtime) BEFORE any step
# runs, so a scratch hatch can never overwrite the live
# /tmp/cabinet-runtime/{constitution.md,safety-boundaries.md} that officers
# consume at boot (create-officer.sh / sync-agents.sh; load-preset.sh:27
# honors the override — step 6 is the chain's only runtime-dir writer). An
# explicit ambient CABINET_RUNTIME_DIR is respected (load-preset's own
# test-override contract) UNLESS it resolves to — or nests under — the
# live default (the containment must not self-defeat; adversarial fixes
# 2026-07-10): a routed runtime dir OR a flight-log dir landing on
# /tmp/cabinet-runtime in any spelling (the /private/tmp alias, slash
# runs, '.'/'..' segments and symlinks are normalized before the compare)
# is REFUSED, exit 64, before hatch writes anything at all — the
# flight-log parent is no longer pre-created; flight_init makes it only
# after the guards pass. So a --flight-log directly in /tmp (routes the
# runtime dir onto the live path), a --flight-log INSIDE
# /tmp/cabinet-runtime (flight.log + step-*.log would pollute the live
# governance dir), and an ambient override aimed at or under the live dir
# all refuse. The routed path prints in the clean-room banner and lands in
# the flight log. Seam 3 (hardening C11, 2026-07-11 — lesson
# `hatch-hatches-the-tree-it-runs-in`): a clean-room run inside a git work
# tree whose instance/config/platform.yml is tracked with a real deployment
# config (>50 lines) is REFUSED, exit 64 — a hatch there rewrites the
# checkout's tracked instance config in place; use a throwaway scratch
# EXPORT (`git archive HEAD | tar -x -C /tmp/hatch-scratch` — a plain clone
# of this repo tracks the same platform.yml and refuses identically), or
# HATCH_ALLOW_TRACKED_INSTANCE=1 to override (routine only on a throwaway
# clone). Fresh hatch targets are untouched by the guard (not a git tree /
# no tracked long platform.yml). KNOWN RESIDUAL SEAM (2026-07-11 verify
# pass): this guard is clean-room-scoped — a plain non-clean-room hatch
# run from such a checkout still rewrites the tracked platform.yml in
# place. In-scope containment per hardening Brief 1 is clean-room only.
#
# Flight recorder: per-step wall-clock timings + stamps (HATCH_START,
# HATCH_PROOFS_DONE, FIRST_RECEIPT_DONE) land in a flight log; the summary
# table, TTFR (proofs-done -> first-receipt) and total time print at the end.
#
# Failure honesty: any failed step prints the exact failed command + its log
# path and exits non-zero. Two documented warn-and-continues: a missing
# TELEGRAM_COS_TOKEN name in cabinet/.env (the Chair boots Telegram-dark —
# rehearsal-verified behavior), and the whole of step 6 (below).
#
# THE FRONT DOOR ALWAYS OPENS (2026-08-12). The operator-facing product is the
# dashboard + onboarding. Step 6 (move-in / launchd) is the advanced step and
# the one most likely to fail on an unfamiliar Mac — so it is NON-FATAL: a
# failure there is recorded, said plainly, and the run still starts the
# dashboard, hands over the password and opens the browser. Real gates —
# host setup, instance, activation, the proofs, the first receipt — still stop
# the run, because without them there is no product to open.
#
# Exit codes: 0 = chain green · 1 = a step failed · 64 = usage error ·
#   75 = hatched and the front door opened, but an OPTIONAL background helper
#        (step 6) did not start. Scripting that only cares "is there a working
#        cabinet" treats 0 and 75 alike; scripting that manages the fleet
#        treats 75 as "retry the move-in" (sysexits EX_TEMPFAIL).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"
# Children (load-preset.sh, deploy-mac.sh dry render) must resolve THIS tree,
# never a default install path — same convention as setup-mac.sh.
export CABINET_ROOT="$REPO_ROOT"
export REPO_ROOT

# shellcheck source=cabinet/scripts/hatch-lib/flight-recorder.sh
. "$SCRIPT_DIR/hatch-lib/flight-recorder.sh"
# shellcheck source=cabinet/scripts/hatch-lib/errands.sh
. "$SCRIPT_DIR/hatch-lib/errands.sh"

usage() {
  cat <<'EOF'
Usage: bash cabinet/scripts/hatch.sh [flags]

One command to hatch a Captain's Cabinet: host setup -> instance ->
activation -> proof gates -> first receipt (the genesis briefing) -> one
LABELED demo receipt (receipt anatomy, emit-demo-receipt.sh) -> your
Cabinet open in a browser, with a flight log timing every step. v0 stops
short of launchd by default, and the few steps only a human can do print
as a numbered checklist at the end.

Starting background helpers (--with-launchd) is never fatal: if it fails
the run says so plainly, opens the browser anyway, and exits 75.

Flags:
  --defaults           Non-interactive everywhere: setup-env.sh --defaults,
                       generate-instance.py --defaults, and auto-adopt when
                       the clone ships a previous deployment's instance/
                       (adoption archives aside, never deletes).
  --altitude RUNG      The operator's rung, recorded as mission.altitude in
                       the --defaults answers: contributor | project | team |
                       function | company. It is not a title — it is what you
                       can DECIDE, which bounds what a proposed outcome's
                       proof can be. It selects the preset (step 4) and
                       reshapes the genesis cards (step 13). Omit it and it
                       stays UNKNOWN, which reproduces the pre-altitude hatch
                       exactly. --defaults only; in the interview lane the
                       rung is recorded as mission.altitude in the answers.
  --clean-room         Throwaway-HOME tolerant. Skips installs (setup-mac.sh
                       --check must find deps present), never touches launchd
                       or the live Redis (load-preset's expected-active marks
                       are pointed at an unused port; skipped honestly), DB
                       schema apply stays best-effort (load-preset's own
                       honest skip), and CABINET_RUNTIME_DIR is routed into
                       the run's scratch area beside the flight log so the
                       live /tmp/cabinet-runtime is never written (an ambient
                       CABINET_RUNTIME_DIR is respected unless it resolves to
                       or inside that live dir — refused, exit 64, as is a
                       --flight-log directly in /tmp or anywhere inside
                       /tmp/cabinet-runtime; refusals fire before anything is
                       written). Refuses a checkout whose tracked
                       instance/config/platform.yml carries a real deployment
                       config — hatch from a scratch EXPORT (git archive |
                       tar -x; a plain clone refuses identically), or set
                       HATCH_ALLOW_TRACKED_INSTANCE=1 to override. Refuses
                       --with-launchd / --with-drill.
  --dry-run            Print the full numbered plan + the human-only
                       checklist, execute nothing, exit 0.
  --no-browser         Skip the browser handover at the very end: do not start
                       the dashboard, do not wait on it, do not touch the
                       clipboard, open nothing. The chain and every gate are
                       identical either way — this only removes the convenience
                       tail. HATCH_NO_BROWSER=1 does the same thing (what CI
                       sets); --clean-room already skips the tail entirely.
                       HATCH_NO_OPEN=1 is the narrower knob: still start the
                       dashboard and hand over the password, just don't open a
                       browser window.
  --with-launchd       Start the background helpers (runbook section 6):
                       deploy the Chair, render + lint + bootstrap the
                       measurement-plane plists, health-check. NEVER FATAL —
                       a failure is recorded, said plainly, and the browser
                       still opens (exit 75). Default is --no-launchd: it
                       becomes a checklist item instead.
  --with-drill         Include proof P-d, the kill-switch drill (activate ->
                       assert ACTIVE -> deactivate -> assert INACTIVE) against
                       REDIS_URL (default redis://localhost:6379). It HALTS a
                       live fleet by design — fresh boxes only.
  --flight-log <path>  Flight log file (default:
                       ~/hatch-logs/hatch-<UTCstamp>/flight.log; step logs
                       land beside it). Ignored by --dry-run (nothing runs,
                       nothing is logged). Relative paths resolve against
                       the repo root and are warned about.
  --help, -h           This help.

Spec of record: docs/runbooks/mini-hatch-tonight-2026-07-07.md
v0 runbook:     docs/runbooks/hatch-v0-2026-07-09.md
EOF
}

# ---- flags -------------------------------------------------------------------
DEFAULTS=0; CLEAN_ROOM=0; DRY_RUN=0; WITH_LAUNCHD=0; WITH_DRILL=0
FLIGHT_LOG_ARG=""; ALTITUDE_ARG=""
# The browser handover is opt-OUT: a hatch that ends in a terminal instruction
# was the thing this replaced. Env default so CI (and any headless caller that
# cannot pass a flag) can suppress it without touching the invocation.
NO_BROWSER="${HATCH_NO_BROWSER:-0}"
while [ $# -gt 0 ]; do
  case "$1" in
    --defaults)     DEFAULTS=1 ;;
    --clean-room)   CLEAN_ROOM=1 ;;
    --dry-run)      DRY_RUN=1 ;;
    --no-browser)   NO_BROWSER=1 ;;
    --with-launchd) WITH_LAUNCHD=1 ;;
    --no-launchd)   WITH_LAUNCHD=0 ;;   # the v0 default, accepted explicitly
    --with-drill)   WITH_DRILL=1 ;;
    --flight-log)   FLIGHT_LOG_ARG="${2:?--flight-log requires a path}"; shift ;;
    --altitude)     ALTITUDE_ARG="${2:?--altitude requires a rung}"; shift ;;
    --help|-h)      usage; exit 0 ;;
    *) echo "hatch.sh: unknown flag '$1'" >&2; usage >&2; exit 64 ;;
  esac
  shift
done

if [ "$CLEAN_ROOM" = "1" ] && [ "$WITH_LAUNCHD" = "1" ]; then
  echo "hatch.sh: --clean-room refuses --with-launchd (clean-room never touches launchd)" >&2
  exit 64
fi
if [ "$CLEAN_ROOM" = "1" ] && [ "$WITH_DRILL" = "1" ]; then
  echo "hatch.sh: --clean-room refuses --with-drill (the drill writes the Redis kill switch)" >&2
  exit 64
fi

PY="python3.12"
CLEANROOM_REDIS_PORT="${HATCH_CLEANROOM_REDIS_PORT:-6399}"  # deliberately-unused port

# The run's exit disposition, decided as the chain goes and honoured by the
# LAST line of this file. 0 = everything green. 75 = the cabinet hatched and
# the front door opened, but an OPTIONAL background helper did not start (see
# the move-in block); a real gate failure still exits 1 from step_fail, long
# before this matters.
HATCH_EXIT=0

# Telegram-dark check — NAME presence only; the value is never read, echoed,
# or logged (values-in-env, names-in-files). A function because the answer
# can change mid-run: the interactive setup-mac.sh wizard may write the name
# into cabinet/.env, so the final checklist recomputes it.
telegram_named() {
  if [ -f cabinet/.env ] && grep -q '^TELEGRAM_COS_TOKEN=..*' cabinet/.env 2>/dev/null; then
    echo 1
  else
    echo 0
  fi
}
TELEGRAM_NAMED="$(telegram_named)"

# ---- the plan (also the --dry-run output) -------------------------------------
emit_plan() {
  echo "==== HATCH PLAN v0 — orchestrates the rehearsed chain, reimplements nothing ===="
  echo "spec of record: docs/runbooks/mini-hatch-tonight-2026-07-07.md"
  echo "mode: defaults=$DEFAULTS clean-room=$CLEAN_ROOM with-launchd=$WITH_LAUNCHD with-drill=$WITH_DRILL no-browser=$NO_BROWSER"
  echo ""
  if [ "$DEFAULTS" = "1" ]; then
    echo " 1. [setup-env]     bash cabinet/scripts/setup-env.sh --defaults"
  else
    echo " 1. [setup-env]     (skipped — no --defaults; setup-mac.sh runs its own interactive wizard)"
  fi
  if [ "$CLEAN_ROOM" = "1" ]; then
    echo " 2. [setup-mac]     bash cabinet/scripts/setup-mac.sh --check"
    echo "                    (clean-room: deps must already be present; no installs,"
    echo "                    no service starts — honest failure if anything is missing)"
  else
    echo " 2. [setup-mac]     bash cabinet/scripts/setup-mac.sh --fast"
  fi
  if [ "$DEFAULTS" = "1" ]; then
    echo " 3. [gen]           $PY cabinet/scripts/generate-instance.py --defaults"
    echo "                    on inherited-instance refusal -> auto-adopt: re-run with --adopt"
    echo "                    (archives conflicts to instance/_pre-adopt-<stamp>/, deletes nothing)"
  else
    echo " 3. [gen]           $PY cabinet/scripts/generate-instance.py"
    echo "                    on inherited-instance refusal -> prints the exact --adopt command and stops"
  fi
  echo " 4. [preset]        write instance/config/active-preset from generate-instance.py --print-preset"
  echo "                    (cabinet.preset > mission.altitude > org_shape — the generator's ONE"
  echo "                    resolution; custom shapes = named handback, set the file yourself)"
  echo " 5. [roles]         bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml"
  echo "                    (no roster.yml -> plain bootstrap-roles.sh, the functional default seed)"
  if [ "$CLEAN_ROOM" = "1" ]; then
    echo " 6. [load-preset]   env REDIS_HOST=127.0.0.1 REDIS_PORT=$CLEANROOM_REDIS_PORT bash cabinet/scripts/load-preset.sh"
    echo "                    (clean-room: expected-active Redis marks pointed at an unused port —"
    echo "                    skipped honestly; DB schema apply is load-preset's own best-effort;"
    echo "                    CABINET_RUNTIME_DIR -> ${CABINET_RUNTIME_DIR:-<flight-log dir>/cabinet-runtime} —"
    echo "                    the live /tmp/cabinet-runtime is never written)"
  else
    echo " 6. [load-preset]   bash cabinet/scripts/load-preset.sh"
  fi
  echo " 7. [roster-authz]  $PY -m pytest framework/tests/test_roster_conf_lockstep.py -q"
  echo "                    (every officer THIS hatch rostered has its capability rows in"
  echo "                    cabinet/officer-capabilities.conf AND an agents: entry in"
  echo "                    cabinet/mcp-scope.yml — no silent capability/MCP-scope lockout."
  echo "                    Green by construction: generate-instance.py rosters only what"
  echo "                    those germline files already authorize)"
  echo " 8. [proof-a]       bash cabinet/scripts/null-hatch.sh"
  echo " 9. [proof-b]       $PY -m pytest framework/tests/test_clean_room.py \\"
  echo "                      framework/tests/test_no_screenpipe_in_core.py \\"
  echo "                      framework/tests/test_no_launcher_hardcode.py -q"
  echo "10. [proof-c1]      bash cabinet/scripts/start-officer-mac.sh cos --dry-run"
  echo "11. [proof-c2]      bash cabinet/scripts/deploy-mac.sh --officer cos --dry-run"
  if [ "$WITH_DRILL" = "1" ]; then
    echo "12. [proof-d]       kill-switch drill: activate -> assert ACTIVE -> deactivate -> assert INACTIVE"
    echo "                    (REDIS_URL=\${REDIS_URL:-redis://localhost:6379}; halts a live fleet by design)"
  else
    echo "12. [proof-d]       (skipped — enable with --with-drill; it writes the Redis kill switch)"
  fi
  echo "    -- stamp HATCH_PROOFS_DONE --"
  echo "13. [first-receipt] bash cabinet/scripts/first-briefing.sh --local"
  echo "                    then print where the briefing landed"
  echo "    -- stamp FIRST_RECEIPT_DONE; TTFR = proofs-done -> first-receipt --"
  echo "14. [demo-receipt]  bash cabinet/scripts/emit-demo-receipt.sh"
  echo "                    ONE labeled DEMO receipt (demo:true row built via the"
  echo "                    real schema path, rendered by the real receipt"
  echo "                    renderer — NEVER journaled: the live undo journal"
  echo "                    stays empty) -> instance/memory/demo-receipt.md"
  if [ "$WITH_LAUNCHD" = "1" ]; then
    echo "15. [move-in]       bash cabinet/scripts/deploy-mac.sh --officer cos"
    echo "                    $PY cabinet/scripts/generate-plists.py"
    echo "                    plutil -lint + launchctl bootout (idempotent re-run) + bootstrap"
    echo "                    gui/\$(id -u) for each generated plist"
    echo "                    bash cabinet/scripts/health-check.sh"
    echo "                    NEVER FATAL: the first failure here stops the rest of the"
    echo "                    move-in, is recorded, and the run continues to step 16 —"
    echo "                    the front door opens anyway (exit 75 instead of 0)"
  else
    echo "15. [move-in]       DEFERRED (v0 default --no-launchd) — printed in the checklist"
  fi
  echo "16. [open]          start your Cabinet (or reuse a running one / a successful move-in's),"
  echo "                    wait on /api/health, copy the password to the clipboard (never printed),"
  echo "                    save the .webloc shortcut, then open /onboarding in the browser"
  echo "                    (--no-browser or --clean-room skip the whole tail; it is never a gate)"
  echo ""
  echo "Flight recorder: per-step timings + stamps -> flight log; summary table,"
  echo "TTFR and total time print at the end."
}

if [ "$DRY_RUN" = "1" ]; then
  emit_plan
  print_errand_notes "$WITH_LAUNCHD" "$TELEGRAM_NAMED" ""
  echo ""
  echo "[dry-run] plan printed — nothing was executed."
  exit 0
fi

# ---- step machinery ------------------------------------------------------------
# Composite do_* steps are orchestration glue (shell functions), so their
# "exact command" is not paste-runnable by itself; map each to the underlying
# script invocation(s) a human would re-run by hand. Static strings only.
composite_cmd_hint() {
  case "$1" in
    do_set_preset)      echo 'echo "$(python3.12 cabinet/scripts/generate-instance.py --print-preset)" > instance/config/active-preset   # cabinet.preset > mission.altitude > org_shape' ;;
    do_bootstrap_roles) echo 'bash cabinet/scripts/bootstrap-roles.sh [--roster instance/config/roster.yml]' ;;
    do_drill)           echo 'bash cabinet/scripts/kill-switch.sh activate|status|deactivate   # REDIS_URL=${REDIS_URL:-redis://localhost:6379}' ;;
    do_first_receipt)   echo 'bash cabinet/scripts/first-briefing.sh --local' ;;
    do_movein_load)     echo 'for p in cabinet/launchd/generated/*.plist; do plutil -lint "$p"; launchctl bootout gui/$(id -u) "$p" 2>/dev/null || true; launchctl bootstrap gui/$(id -u) "$p"; done' ;;
    *) return 1 ;;
  esac
}

step_fail() {
  local id="$1" log="$2"; shift 2
  echo "" >&2
  echo "HATCH FAILED at step [$id]." >&2
  { printf '  exact command:'; printf ' %q' "$@"; printf '\n'; } >&2
  local hint
  if hint="$(composite_cmd_hint "${1:-}")"; then
    echo "  (composite step — the underlying, paste-runnable command:" >&2
    echo "   $hint )" >&2
  fi
  echo "  step log:      $log" >&2
  echo "  Root-cause it and re-run hatch.sh — the chain is re-runnable/idempotent" >&2
  echo "  by construction (runbook P3 discipline: no patch-arounds, no gate-skips)." >&2
  flight_line "HATCH_FAIL [$id]"
  flight_summary
  exit 1
}

# run_step_soft <id> <desc> <argv...>  — run + record; returns the step's rc
run_step_soft() {
  local id="$1" desc="$2"; shift 2
  local log="$HATCH_LOG_DIR/step-${id}.log" t0 t1 rc=0
  flight_step_begin "$id" "$desc"
  echo ""
  echo "==> [$id] $desc"
  printf '    $'; printf ' %q' "$@"; printf '\n'
  t0=$(date +%s)
  ( "$@" ) 2>&1 | tee -a "$log" || rc=$?
  t1=$(date +%s)
  if [ "$rc" -ne 0 ]; then
    flight_step_end "$id" fail "$((t1 - t0))"
    return "$rc"
  fi
  flight_step_end "$id" ok "$((t1 - t0))"
}

# run_step <id> <desc> <argv...>  — run_step_soft, but a failure ends the hatch
run_step() {
  local id="$1" desc="$2"; shift 2
  local rc=0
  run_step_soft "$id" "$desc" "$@" || rc=$?
  [ "$rc" -eq 0 ] || step_fail "$id" "$HATCH_LOG_DIR/step-${id}.log" "$@"
}

# ---- composite steps (orchestration glue only — no reimplementation) -----------
do_generate_instance() {
  local gen_argv=("$PY" "cabinet/scripts/generate-instance.py")
  [ "$DEFAULTS" = "1" ] && gen_argv+=("--defaults")
  # --altitude is a --defaults-only knob (the generator refuses it otherwise):
  # in the interview lane the rung is recorded as mission.altitude instead.
  [ -n "$ALTITUDE_ARG" ] && gen_argv+=("--altitude" "$ALTITUDE_ARG")
  local log="$HATCH_LOG_DIR/step-gen.log" rc=0
  run_step_soft gen "generate the instance (init fast-lane)" "${gen_argv[@]}" || rc=$?
  [ "$rc" -eq 0 ] && return 0
  # The generator's own refusal string for an inherited instance/ — the
  # rehearsed cue for --adopt (mini-hatch runbook step 3).
  if grep -q "REFUSING to overwrite" "$log" 2>/dev/null; then
    if [ "$DEFAULTS" = "1" ]; then
      echo ""
      echo "    Inherited instance detected -> auto-adopt (--defaults): every"
      echo "    conflicting file is archived to instance/_pre-adopt-<stamp>/ —"
      echo "    nothing is deleted (generate-instance.py --adopt semantics)."
      run_step gen-adopt "generate the instance (--adopt: settle the previous homestead)" \
        "${gen_argv[@]}" --adopt
      return 0
    fi
    echo "" >&2
    echo "This clone ships a previous deployment's instance/ (the standard case" >&2
    echo "per the mini-hatch runbook). The rehearsed path is adoption:" >&2
    echo "    $PY cabinet/scripts/generate-instance.py --adopt" >&2
    echo "or re-run hatch.sh with --defaults to auto-adopt." >&2
    step_fail gen "$log" "${gen_argv[@]}"
  fi
  step_fail gen "$log" "${gen_argv[@]}"
}

do_set_preset() {
  # ASKS THE GENERATOR, never re-derives. This used to mirror the generator's
  # printed mapping by hand (portfolio -> portfolio, functional -> work) and
  # had already drifted: it wrote `portfolio` even when the answers declared
  # `cabinet.preset: developer`, and it could not see mission.altitude at all.
  # `--print-preset` is the ONE resolution (generate-instance.resolve_preset),
  # so altitude reaches the file that is actually written here.
  local answers="instance/config/cabinet-init.answers.yml" preset="" rc=0
  if [ ! -f "$answers" ]; then
    if [ -s instance/config/active-preset ]; then
      echo "answers file absent; keeping existing active-preset ($(tr -d '[:space:]' < instance/config/active-preset))"
      return 0
    fi
    echo "cannot derive the preset: $answers is missing and instance/config/active-preset is unset." >&2
    echo "Named handback — set it yourself, e.g.: echo portfolio > instance/config/active-preset" >&2
    return 1
  fi
  preset="$("$PY" cabinet/scripts/generate-instance.py --print-preset --answers "$answers")" || rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$preset" ]; then
    echo "the generator could not resolve a preset for $answers (rc=$rc)." >&2
    echo "Named handback — set instance/config/active-preset yourself, then re-run." >&2
    return 1
  fi
  # EXISTENCE GUARD (from the personal-preset landing, 2026-07-27): the resolved
  # slug becomes a path segment, and an unpopulated preset fails later and less
  # clearly. Kept on the single-resolution path rather than beside a second copy
  # of the mapping — the drift this guard was written next to is what
  # --print-preset removes.
  if [ ! -f "presets/$preset/preset.yml" ]; then
    echo "resolved preset '$preset' has no presets/$preset/preset.yml." >&2
    echo "Named handback — populate that preset or fix the answers file, then re-run." >&2
    return 1
  fi
  printf '%s\n' "$preset" > instance/config/active-preset
  echo "active-preset = $preset (resolved by generate-instance.py --print-preset)"
}

do_bootstrap_roles() {
  if [ -f instance/config/roster.yml ]; then
    bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml
  else
    # No roster (functional shape) — the generator's printed default seed.
    bash cabinet/scripts/bootstrap-roles.sh
  fi
}

do_drill() {
  # P-d, v0 scope: prove the switch flips and reads back, fail-closed store
  # reachable. HONEST LIMIT: the full revocation proof — a BOOTED officer
  # refusing its next tool call while ACTIVE — needs a live officer (runbook
  # steps 5-6); run that at move-in.
  export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
  bash cabinet/scripts/kill-switch.sh activate
  bash cabinet/scripts/kill-switch.sh status | grep -q "Kill switch: ACTIVE" \
    || { echo "drill: switch did not read back ACTIVE"; return 1; }
  bash cabinet/scripts/kill-switch.sh deactivate
  bash cabinet/scripts/kill-switch.sh status | grep -q "Kill switch: INACTIVE" \
    || { echo "drill: switch did not read back INACTIVE"; return 1; }
  echo "drill: kill switch flips + reads back (full booted-officer refusal proof = move-in)"
}

do_first_receipt() {
  if [ ! -f cabinet/scripts/first-briefing.sh ]; then
    echo "cabinet/scripts/first-briefing.sh not found — the genesis first-receipt" >&2
    echo "contract is not on this tree; cannot mint the first receipt." >&2
    return 1
  fi
  bash cabinet/scripts/first-briefing.sh --local
}

# ---- clean-room containment path helpers ----------------------------------------
# lex_norm_path <path> — PURELY LEXICAL normalization, never touches the
# filesystem: collapses '//' runs and '.' segments, pops '..' normpath-style,
# strips the trailing '/'. Used for the containment compares (and for a
# not-yet-existing flight-log parent) where realpath has nothing to resolve,
# so spelled variants like /tmp//cabinet-runtime, /tmp/./cabinet-runtime or
# /tmp/gone/../cabinet-runtime normalize to one compare form. Lexical '..'
# popping can differ from physical resolution only through an existing
# symlinked prefix — for a REFUSAL compare, over-normalizing can only
# over-refuse, which is fail-safe. Subshell body keeps `set -f` (no
# glob-expansion of split segments) contained. Bash 3.2-safe.
lex_norm_path() (
  set -f
  local IFS='/' seg out="" abs=0 n
  local parts=()
  case "$1" in /*) abs=1 ;; esac
  for seg in $1; do
    case "$seg" in
      ''|'.') ;;
      '..')
        n=${#parts[@]}
        if [ "$n" -gt 0 ] && [ "${parts[$((n - 1))]}" != ".." ]; then
          unset "parts[$((n - 1))]"
        elif [ "$abs" = "0" ]; then
          parts+=("..")
        fi
        ;;
      *) parts+=("$seg") ;;
    esac
  done
  for seg in ${parts[@]+"${parts[@]}"}; do out="$out/$seg"; done
  if [ "$abs" = "1" ]; then
    printf '%s' "${out:-/}"
  else
    printf '%s' "${out#/}"
  fi
)

# resolve_for_compare <path> — the strongest honest resolution for the
# containment refusals below: lexical normalization, then PHYSICAL
# resolution of the deepest EXISTING ancestor (realpath) with the
# not-yet-existing remainder re-appended — so /tmp vs /private/tmp (one
# directory on macOS) and symlinked spellings compare equal even when the
# leaf does not exist yet. Relative paths return lexically normalized only
# (they resolve under the repo root and can never spell the live
# /tmp/cabinet-runtime); a box without realpath falls back to the lexical
# form (the refusal case patterns carry both literal spellings for exactly
# that fallback).
resolve_for_compare() {
  local p head tail=""
  p="$(lex_norm_path "$1")"
  case "$p" in
    /*) ;;
    *) printf '%s' "$p"; return 0 ;;
  esac
  if ! command -v realpath >/dev/null 2>&1; then
    printf '%s' "$p"
    return 0
  fi
  head="$p"
  while [ "$head" != "/" ]; do
    if [ -e "$head" ]; then
      head="$(realpath "$head" 2>/dev/null || printf '%s' "$head")"
      if [ "$head" = "/" ]; then head=""; fi
      printf '%s%s' "$head" "$tail"
      return 0
    fi
    tail="/${head##*/}$tail"
    head="${head%/*}"
    if [ -z "$head" ]; then head="/"; fi
  done
  printf '%s' "$p"
}

# tracked_instance_guard <repo root> — returns 1 (refuse) ONLY when the tree
# hatch would write into is a git work tree whose instance/config/platform.yml
# is git-tracked AND real-deployment-sized (>50 lines). The paid lesson
# `hatch-hatches-the-tree-it-runs-in` (2026-07-11): a clean-room hatch run
# from a git worktree rewrote that checkout's TRACKED platform.yml in place
# (337->14 lines) + sources.yml and littered 8 untracked instance/ paths —
# the Wave-C containment covered /tmp runtime dirs, not the checkout's own
# instance/. Real hatch targets are a no-op here (a fresh box is not a git
# tree, or carries no tracked long platform.yml — its instance/ is generated,
# not versioned). HATCH_ALLOW_TRACKED_INSTANCE=1 bypasses deliberately.
# Fail-open on probe anomalies: the prime contract is zero effect on targets.
# REMEDIATION SHAPE (verify pass 2026-07-11): every clone of THIS repo also
# tracks platform.yml >50 lines, so a bare `git clone` is refusal-shaped too
# — the refusal below therefore prescribes a `git archive | tar -x` export
# (not a git tree -> silent pass) and names the bypass as clone-only advice.
tracked_instance_guard() {
  local n
  [ "${HATCH_ALLOW_TRACKED_INSTANCE:-0}" = "1" ] && return 0
  git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
  git -C "$1" ls-files --error-unmatch instance/config/platform.yml >/dev/null 2>&1 || return 0
  n="$(wc -l < "$1/instance/config/platform.yml" 2>/dev/null || echo 0)"
  [ "$n" -gt 50 ] 2>/dev/null || return 0
  return 1
}

# ---- the run -------------------------------------------------------------------
STAMP="$(date -u +%Y%m%d-%H%M%S)"
if [ -n "$FLIGHT_LOG_ARG" ]; then
  case "$FLIGHT_LOG_ARG" in
    /*) ;;
    *)
      echo "hatch.sh: WARN — relative --flight-log resolves against the repo root" >&2
      echo "          ($REPO_ROOT); step logs will land inside the working tree." >&2
      echo "          An absolute path is recommended." >&2 ;;
  esac
  # Resolve the log dir WITHOUT creating anything: the clean-room guard below
  # must judge (and possibly refuse) this run before its first write — a
  # refused run writes nothing, not even the flight-log parent (fix-pass
  # 2026-07-10; the old pre-guard mkdir -p is gone — flight_init mkdir-s the
  # dir once the run is allowed to proceed). An existing parent resolves via
  # cd; a not-yet-existing one lexically, to the same absolute form mkdir -p
  # will create.
  _flight_parent="$(dirname "$FLIGHT_LOG_ARG")"
  case "$_flight_parent" in
    /*) ;;
    *) _flight_parent="$REPO_ROOT/$_flight_parent" ;;
  esac
  if ! LOG_DIR="$(cd "$_flight_parent" 2>/dev/null && pwd)"; then
    LOG_DIR="$(lex_norm_path "$_flight_parent")"
  fi
  unset _flight_parent
  FLIGHT_LOG="$LOG_DIR/$(basename "$FLIGHT_LOG_ARG")"
else
  LOG_DIR="$HOME/hatch-logs/hatch-$STAMP"
  FLIGHT_LOG="$LOG_DIR/flight.log"
fi

# Clean-room containment (2026-07-10, PC Wave-C hatch-hardening; PC-B verifier
# follow-up (a)): load-preset.sh (step 6) assembles constitution.md +
# safety-boundaries.md into ${CABINET_RUNTIME_DIR:-/tmp/cabinet-runtime} — the
# LIVE files officers read at boot. Route the runtime dir into this run's
# scratch area BEFORE any step runs (same throwaway discipline as the
# clean-room HOME); an explicit ambient CABINET_RUNTIME_DIR is respected
# (load-preset.sh's own test-override contract) UNLESS it resolves to — or
# nests under — the live default, which is refused below.
if [ "$CLEAN_ROOM" = "1" ]; then
  export CABINET_RUNTIME_DIR="${CABINET_RUNTIME_DIR:-$LOG_DIR/cabinet-runtime}"
  # The containment must not self-defeat (adversarial fixes, 2026-07-10): a
  # flight log directly in /tmp makes LOG_DIR=/tmp, so the default above
  # resolves to /tmp/cabinet-runtime — the exact live path this routing
  # exists to protect; an ambient CABINET_RUNTIME_DIR aimed there (or UNDER
  # it — scratch twins inside the live governance dir are pollution too)
  # has the same effect. Refuse, never work around (the
  # --with-launchd/--with-drill posture). resolve_for_compare normalizes
  # spellings (//, /./, .., trailing /) and resolves the deepest existing
  # ancestor physically — /tmp and /private/tmp alias one directory on
  # macOS — with both literal spellings kept in the patterns for
  # realpath-less boxes. The refusals fire before flight_init AND before
  # the flight-log parent exists — a refused run writes nothing at all.
  # Seam 1 (fix-pass 2026-07-10), checked FIRST so the refusal names the
  # flag the user actually got wrong: a --flight-log INSIDE the live dir
  # (e.g. /tmp/cabinet-runtime/flight.log) routes the runtime dir to a
  # NESTED scratch path — the runtime-dir compare below would catch it, but
  # blame the derived CABINET_RUNTIME_DIR — while flight_init + run_step
  # would write flight.log and step-*.log INTO the live governance dir
  # under the very banner claiming it is never written. Refuse a log dir
  # that resolves to (or under) the live dir.
  _routed_logdir="$(resolve_for_compare "$LOG_DIR")"
  case "$_routed_logdir" in
    /tmp/cabinet-runtime|/tmp/cabinet-runtime/*|/private/tmp/cabinet-runtime|/private/tmp/cabinet-runtime/*)
      echo "hatch.sh: --clean-room refuses a flight-log dir of $LOG_DIR —" >&2
      echo "          that is the live runtime dir (or inside it): flight.log +" >&2
      echo "          step-*.log would pollute the governance files officers read at" >&2
      echo "          boot. Put the flight log in its own directory, e.g." >&2
      echo "          --flight-log /tmp/hatch-scratch/flight.log" >&2
      exit 64
      ;;
  esac
  # Seam 2 (the original adversarial fix): the routed runtime dir itself.
  _routed_runtime="$(resolve_for_compare "$CABINET_RUNTIME_DIR")"
  case "$_routed_runtime" in
    /tmp/cabinet-runtime|/tmp/cabinet-runtime/*|/private/tmp/cabinet-runtime|/private/tmp/cabinet-runtime/*)
      echo "hatch.sh: --clean-room refuses CABINET_RUNTIME_DIR=$CABINET_RUNTIME_DIR —" >&2
      echo "          that IS (or sits inside) the live runtime dir the clean-room" >&2
      echo "          containment exists to protect (a --flight-log directly in /tmp" >&2
      echo "          routes here; so does an ambient CABINET_RUNTIME_DIR override)." >&2
      echo "          Put the flight log in its own directory, or point" >&2
      echo "          CABINET_RUNTIME_DIR at a scratch path." >&2
      exit 64
      ;;
  esac
  unset _routed_runtime _routed_logdir
  # Seam 3 (hardening C11, 2026-07-11 — lesson `hatch-hatches-the-tree-it-runs-
  # in`): the checkout's OWN instance/. Seams 1+2 protect the live /tmp runtime
  # dir; nothing protected the tracked instance config of the git tree the run
  # sits in. Refuse — verification hatches belong in throwaway scratch clones.
  if ! tracked_instance_guard "$REPO_ROOT"; then
    echo "hatch.sh: --clean-room refuses to run in this checkout ($REPO_ROOT) —" >&2
    echo "          instance/config/platform.yml is git-tracked here with a real" >&2
    echo "          deployment config; the hatch chain would rewrite it (and" >&2
    echo "          sources.yml) in place and litter untracked instance/ paths." >&2
    echo "          Run from a throwaway scratch EXPORT instead (a plain git" >&2
    echo "          clone tracks the same platform.yml and refuses identically):" >&2
    echo "            mkdir -p /tmp/hatch-scratch" >&2
    echo "            git -C \"$REPO_ROOT\" archive HEAD | tar -x -C /tmp/hatch-scratch" >&2
    # The scratch export is gitless, so null-hatch.sh re-derives shipped-vs-local
    # from .gitignore alone and would delete FORCE-TRACKED content (dashboard
    # officers pages, memory/tier3, deployment-status.md) that git archive just
    # shipped. egg-export.sh writes this list for the real egg; a hand-cut
    # scratch has to write its own or the clean-room proof runs on a tree the
    # export does not have.
    echo "            git -C \"$REPO_ROOT\" ls-files -c -i --exclude-standard \\" >&2
    echo "              > /tmp/hatch-scratch/cabinet/scripts/shipped-ignored-paths.txt" >&2
    echo "            cd /tmp/hatch-scratch" >&2
    echo "          (a scratch clone works too, but needs" >&2
    echo "          HATCH_ALLOW_TRACKED_INSTANCE=1 — safe there: it is throwaway)." >&2
    echo "          If this tree really is the hatch target," >&2
    echo "          set HATCH_ALLOW_TRACKED_INSTANCE=1 to override." >&2
    exit 64
  fi
fi

flight_init "$LOG_DIR" "$FLIGHT_LOG"
flight_stamp HATCH_START
# The first thing a person sees. Plain, and it answers the two questions
# somebody watching a wall of scrolling text actually has: how long, and do I
# have to do anything?
echo "==== SETTING UP YOUR CABINET ===="
echo "This takes a few minutes. You don't need to do anything — leave this window"
echo "open and it will open in your browser when it's ready."
echo "A record of everything it does is being kept in: $LOG_DIR"
echo ""
if [ "$CLEAN_ROOM" = "1" ]; then
  echo "==== CLEAN-ROOM — CABINET_RUNTIME_DIR -> $CABINET_RUNTIME_DIR ===="
  echo "     (scratch-routed runtime dir: the live /tmp/cabinet-runtime is never written)"
  flight_line "CLEAN_ROOM_RUNTIME_DIR $CABINET_RUNTIME_DIR"
fi
echo "The technical plan, for the record — nothing here needs your attention:"
emit_plan

if [ "$TELEGRAM_NAMED" = "0" ]; then
  echo ""
  echo "Heads up: there's no Telegram bot token yet, so your Cabinet won't be able"
  echo "      to message you on Telegram. Everything else works, and you can add"
  echo "      one later — it's in the checklist at the end (TELEGRAM_COS_TOKEN)."
  flight_line "WARN telegram-dark (TELEGRAM_COS_TOKEN name absent)"
fi

# 1. host bootstrap
if [ "$DEFAULTS" = "1" ]; then
  run_step setup-env "getting your settings file ready" \
    bash cabinet/scripts/setup-env.sh --defaults
fi
if [ "$CLEAN_ROOM" = "1" ]; then
  run_step setup-mac "checking this Mac has what it needs (checking only, installing nothing)" \
    bash cabinet/scripts/setup-mac.sh --check
  echo "    clean-room: install/service phases skipped (deps verified present);"
  echo "    launchd, the live Redis, and the live /tmp/cabinet-runtime are never"
  echo "    touched in this mode (runtime dir scratch-routed — see banner above)."
else
  run_step setup-mac "checking this Mac has what it needs, and installing anything missing" \
    bash cabinet/scripts/setup-mac.sh --fast
fi

# setup-mac is the bootstrap owner for Python 3.12.  Checking before it ran
# made the advertised one-command hatch fail on the exact fresh Mac it exists
# to prepare.  Re-check after the step so clean-room stays install-free while a
# normal hatch can install the pinned interpreter before any Python consumer.
command -v "$PY" >/dev/null 2>&1 || {
  echo "hatch.sh: setup-mac completed without $PY; run 'brew install python@3.12' and retry" >&2
  exit 1
}

# 2. instance generation (init fast-lane; rehearsed adoption on refusal)
do_generate_instance

# 3. activation (runbook step 4)
run_step preset "choosing the layout that matches your answers" do_set_preset
echo ""
echo "Note: two settings files are only ever edited by hand, on purpose — they"
echo "      are in the checklist at the end. They are OPTIONAL and nothing here"
echo "      is waiting on them."
run_step roles "creating the roles your Cabinet will use" do_bootstrap_roles
if [ "$CLEAN_ROOM" = "1" ]; then
  run_step load-preset "putting it all together (clean-room: Redis marks -> unused port $CLEANROOM_REDIS_PORT)" \
    env REDIS_HOST=127.0.0.1 REDIS_PORT="$CLEANROOM_REDIS_PORT" bash cabinet/scripts/load-preset.sh
else
  run_step load-preset "putting it all together" \
    bash cabinet/scripts/load-preset.sh
fi

# 4. proofs (runbook step 5) — do not proceed past a red gate
# roster-authz (2026-07-26) runs FIRST and against the LIVE tree this hatch just
# wrote — it is a claim about THIS deployment's roster, not about the shipped
# egg, so it cannot live inside null-hatch (whose sandbox deliberately carries
# no deployment-local state). It fires the lockstep module's live arm, which
# skips on a bare checkout and asserts here because roster.yml now exists.
run_step roster-authz "safety check: every role is properly authorised" \
  "$PY" -m pytest framework/tests/test_roster_conf_lockstep.py -q
run_step proof-a "safety check: a brand-new Cabinet starts with none of your data in it" \
  bash cabinet/scripts/null-hatch.sh
run_step proof-b "safety check: nothing personal leaked into the shared parts" \
  "$PY" -m pytest framework/tests/test_clean_room.py \
    framework/tests/test_no_screenpipe_in_core.py \
    framework/tests/test_no_launcher_hardcode.py -q
run_step proof-c1 "safety check: rehearsing the start-up, without starting anything" \
  bash cabinet/scripts/start-officer-mac.sh cos --dry-run
run_step proof-c2 "safety check: rehearsing the background schedule, without installing it" \
  bash cabinet/scripts/deploy-mac.sh --officer cos --dry-run
if [ "$WITH_DRILL" = "1" ]; then
  run_step proof-d "safety check: the emergency stop switch really stops things" do_drill
else
  echo ""
  echo "==> [proof-d] SKIPPED (enable with --with-drill; it writes the Redis kill"
  echo "    switch and halts a live fleet by design — fresh boxes only)"
  # keep the flight-log grammar paired (STEP_BEGIN ... STEP_END), skips included
  flight_step_begin proof-d "P-d kill-switch drill (skipped — no --with-drill)"
  flight_step_end proof-d skip 0
fi
flight_stamp HATCH_PROOFS_DONE

# 5. FIRST RECEIPT — the genesis briefing
run_step first-receipt "writing your first briefing" \
  do_first_receipt
flight_stamp FIRST_RECEIPT_DONE
RECEIPT_LOG="$HATCH_LOG_DIR/step-first-receipt.log"
# first-briefing.sh's own machine-readable receipt line is the contract
# (genesis area, 2026-07-09); fall back to a path grep, then the raw tail.
RECEIPT_LANDING="$(sed -n 's/^FIRST_BRIEFING_RECEIPT=//p' "$RECEIPT_LOG" 2>/dev/null | tail -1 || true)"
[ -n "$RECEIPT_LANDING" ] || \
  RECEIPT_LANDING="$(grep -Eio '[^ "]*/[^ "]*brief[^ "]*' "$RECEIPT_LOG" 2>/dev/null | tail -1 || true)"
echo ""
echo "==== FIRST RECEIPT ===="
if [ -n "$RECEIPT_LANDING" ]; then
  echo "The briefing landed at: $RECEIPT_LANDING"
else
  echo "first-briefing.sh did not print a recognizable path — its full output:"
  echo "  $RECEIPT_LOG  (tail below)"
  tail -n 8 "$RECEIPT_LOG" 2>/dev/null | sed 's/^/  | /' || true
fi

# 5b. DEMO receipt — one labeled receipt-anatomy example beside the briefing
# (Wave B day-1 legibility). Same wiring discipline as the first receipt: the
# script's own machine-readable DEMO_RECEIPT= line is the contract.
run_step demo-receipt "adding one clearly-labelled example receipt, so you can see what they look like" \
  bash cabinet/scripts/emit-demo-receipt.sh
DEMO_LOG="$HATCH_LOG_DIR/step-demo-receipt.log"
DEMO_LANDING="$(sed -n 's/^DEMO_RECEIPT=//p' "$DEMO_LOG" 2>/dev/null | tail -1 || true)"

# 6. background helpers (runbook section 6, "move-in") — deferred by default,
#    and NEVER fatal.
#
# 2026-08-12, never-strand fix. A real operator double-clicked the app on his
# own Mac. Everything above succeeded; `deploy-mac.sh --officer cos` then died
# with launchd's "Bootstrap failed: 5: Input/output error". Because each
# move-in step was a hard `run_step`, hatch.sh exited 1 right there — BEFORE
# the verdict and before the browser handover — so no dashboard started, no
# password reached the clipboard, nothing opened, and the Terminal window said
# "Process completed". He was stranded with a working cabinet he could not see.
#
# The rule that follows from it: the operator-facing PRODUCT is the dashboard
# and onboarding; starting background helpers is the advanced step and the one
# most likely to fail on an unfamiliar machine. A helper that will not start is
# a note, not a dead end. So these steps run soft: the first failure stops the
# REST of the sequence (each step depends on the one before it), is recorded in
# the flight log with its exact command and step log, and the chain carries on
# to the front door. HATCH_EXIT becomes 75 so scripting can still tell this
# apart from a clean run — see the exit-code block at the end of the file.
MOVEIN_OK=1
MOVEIN_FAILED_LOG=""
if [ "$WITH_LAUNCHD" = "1" ]; then
  # movein_step <id> <desc> <argv...> — run_step_soft that records the first
  # failure, skips every later move-in step, and ALWAYS returns 0. Nothing in
  # this block may end the run: that is the whole point of the fix.
  movein_step() {
    local id="$1" desc="$2"; shift 2
    local rc=0
    [ "$MOVEIN_OK" = "1" ] || return 0
    run_step_soft "$id" "$desc" "$@" || rc=$?
    [ "$rc" -eq 0 ] && return 0
    MOVEIN_OK=0
    MOVEIN_FAILED_LOG="$HATCH_LOG_DIR/step-${id}.log"
    flight_line "MOVEIN_FAILED [$id] rc=$rc (not fatal — the front door still opens)"
    echo ""
    echo "    That step didn't work on this Mac. It is optional, so setup keeps"
    echo "    going: your Cabinet still opens in your browser in a moment."
    return 0
  }
  movein_step movein-chair "start the helper that runs your Cabinet in the background" \
    bash cabinet/scripts/deploy-mac.sh --officer cos
  movein_step movein-plists "write the background schedule" \
    "$PY" cabinet/scripts/generate-plists.py
  do_movein_load() {
    local p found=0
    for p in cabinet/launchd/generated/*.plist; do
      [ -e "$p" ] || continue
      found=1
      plutil -lint "$p"
      # Bootout-first = idempotent re-run (deploy-mac.sh's own proven idiom):
      # a raw bootstrap hard-fails "Bootstrap failed: 5" (EEXIST) when the
      # plist is already loaded — e.g. on the advised re-run after a
      # movein-health failure. Bootout errors harmlessly when not loaded.
      launchctl bootout "gui/$(id -u)" "$p" 2>/dev/null || true
      launchctl bootstrap "gui/$(id -u)" "$p"
    done
    [ "$found" = "1" ] || { echo "no plists under cabinet/launchd/generated/"; return 1; }
  }
  movein_step movein-load "put the background schedule in place" \
    do_movein_load
  movein_step movein-health "check the background helpers answered" \
    bash cabinet/scripts/health-check.sh
  if [ "$MOVEIN_OK" = "1" ]; then
    echo ""
    echo "Your Cabinet's background helpers are running."
    echo "You can check on them any time with:"
    echo "    bash cabinet/scripts/cabinet-doctor.sh"
  else
    HATCH_EXIT=75
  fi
fi

# ---- verdict --------------------------------------------------------------------
GEN_LOG_HINT="$HATCH_LOG_DIR/step-gen.log"
[ -f "$HATCH_LOG_DIR/step-gen-adopt.log" ] && GEN_LOG_HINT="$HATCH_LOG_DIR/step-gen-adopt.log"
# Recompute — the interactive wizard may have named the token mid-run, and
# the STATE line must reflect post-chain reality (same read-only
# name-presence grep; the value is still never read).
TELEGRAM_NAMED="$(telegram_named)"
print_errand_notes "$WITH_LAUNCHD" "$TELEGRAM_NAMED" "$GEN_LOG_HINT"
flight_summary
echo ""
# app-feel: dashboard port — explicit env wins; else cabinet/.env; else 3100.
# (A port is config, not a secret — values-in-env doctrine concerns tokens.)
DASH_PORT="${CABINET_DASHBOARD_PORT:-}"
if [ -z "$DASH_PORT" ] && [ -f cabinet/.env ]; then
  DASH_PORT="$(sed -n 's/^CABINET_DASHBOARD_PORT=//p' cabinet/.env | tail -1)" || DASH_PORT=""
fi
DASH_PORT="${DASH_PORT:-3100}"; DASH_URL="http://127.0.0.1:${DASH_PORT}/"
echo "==== WHERE THINGS ARE ===="
echo "Your first briefing:   ${RECEIPT_LANDING:-see $RECEIPT_LOG}"
echo "                       (easier to read in your browser: ${DASH_URL}briefing)"
echo "An example receipt:    ${DEMO_LANDING:-see $DEMO_LOG}"
echo "                       (clearly labelled as an example, so you can see what a receipt looks like)"
echo "How it's governed:     docs/how-your-cabinet-is-governed.md  (one page, plain language)"
echo "Small menu-bar app:    bash cabinet/scripts/build-companion.sh && open \"bin/Cabinet Companion.app\""
echo "Your Cabinet:          ${DASH_URL} (big-screen view: ${DASH_URL}display)"
echo "Keep it in your Dock:  Safari File > Add to Dock, or Chrome menu > Cast, save and share > Install page as app"
echo ""
echo "==== YOUR CABINET IS READY ===="
if [ "$WITH_LAUNCHD" = "1" ] && [ "$MOVEIN_OK" = "1" ]; then
  echo "Everything is set up, and the background helpers are running."
  echo "It's about to open in your browser."
elif [ "$WITH_LAUNCHD" = "1" ]; then
  # The never-strand case. Plain, calm, in context — and NOT the raw launchd
  # error, which is already in the step log for whoever needs it.
  echo "Everything you need is set up, and it's about to open in your browser."
  echo ""
  echo "One thing to know: a background helper didn't start on this Mac. That's"
  echo "fine — it only lets your Cabinet keep working while you're away, and"
  echo "nothing you do in the browser needs it. To try it again later, run:"
  echo "    bash cabinet/scripts/hatch.sh --with-launchd"
  echo "If you'd like the details (or want to show someone), they're in:"
  echo "    ${MOVEIN_FAILED_LOG:-$HATCH_LOG_DIR}"
else
  echo "Everything is set up, and it's about to open in your browser."
  echo ""
  echo "Your Cabinet isn't working in the background yet — that's the deliberate"
  echo "default. When you want it to, run:"
  echo "    bash cabinet/scripts/hatch.sh --with-launchd"
fi

# ---- app-feel (Wave D) — bookmark + auto-open; convenience tail, NEVER a gate ----
# EOF is reached only on the GREEN path (step_fail exits 1 earlier). This tail
# must preserve exit 0: every branch returns 0; invocation carries || fallback.
#
# 2026-08-02 (hatch-to-browser). The DEFAULT --no-launchd path used to stop at
# "dashboard not started" — a hatch whose last act was telling a person to go
# back to a terminal. It now starts the dashboard itself, waits on its health
# endpoint, hands the password over via the clipboard (dashboard-password.sh
# writes only to pbcopy; the password stays unprinted, unlogged, out of argv)
# and lands the operator on /onboarding. Three ways out, all honest:
#   * --clean-room  = CI = headless: skips the ENTIRE tail, unchanged from
#     before — no server started, no clipboard touched, nothing opened;
#   * --no-browser / HATCH_NO_BROWSER=1: same skip on a normal run, for a
#     caller that wants the chain without a server;
#   * HATCH_NO_OPEN=1 / SSH: the narrow one — still start, still wait, still
#     hand over the password, just don't raise a browser window.
# The started dashboard OUTLIVES this script (that is the point), so the line
# that reports it also says where its log is and how to stop it.
#
# 2026-08-12 (never-strand). Two changes here, both from one real operator's
# run: (1) a FAILED launchd move-in means nothing started the dashboard, so
# this step starts it itself — the front door opens on every path where the
# cabinet actually hatched; (2) every line a person reads here is plain now.
# The technical detail did not go anywhere: it is in the flight log and the
# per-step logs, which is where a diagnosis belongs.
DASH_LANDING="${DASH_URL}onboarding"
DASH_LOG="${HATCH_LOG_DIR:-${TMPDIR:-/tmp}}/step-dashboard.log"
DASH_SCRIPTS="${SCRIPT_DIR:-$PWD/cabinet/scripts}"
app_feel() {
  local webloc ok tries waited dash_pid self_start
  if [ "$CLEAN_ROOM" = "1" ]; then
    echo "[opening] clean-room: skipped (no browser, no ~/Applications writes)"; return 0
  fi
  if [ "$NO_BROWSER" = "1" ]; then
    echo "[opening] --no-browser: your Cabinet was not started and nothing was opened."
    echo "          To start it yourself: bash cabinet/scripts/start-dashboard.sh"
    echo "          Then go to: $DASH_LANDING"
    return 0
  fi
  # Who starts it? A SUCCESSFUL background move-in already did. Every other
  # path — the default, or a move-in that failed on this machine — starts it
  # right here. MOVEIN_OK defaults to 1 so this stays correct when the tail is
  # driven on its own. Either way the health probe below decides it is really up.
  self_start=1
  if [ "$WITH_LAUNCHD" = "1" ] && [ "${MOVEIN_OK:-1}" = "1" ]; then
    self_start=0
  fi
  tries=60
  if [ "$self_start" = "1" ]; then
    if curl -fsS --max-time 2 "${DASH_URL}api/health" >/dev/null 2>&1; then
      echo "[opening] your Cabinet is already running at $DASH_URL — using that one"
    else
      : > "$DASH_LOG" 2>/dev/null || true
      nohup bash "$DASH_SCRIPTS/start-dashboard.sh" >>"$DASH_LOG" 2>&1 &
      dash_pid=$!
      echo "[opening] starting your Cabinet (id $dash_pid). It keeps running after this window closes."
      echo "          Notes for later, if anything looks wrong: $DASH_LOG"
      echo "          To stop it: kill \$(lsof -ti tcp:$DASH_PORT)"
      # A first run does npm ci + next build before it serves anything: minutes,
      # not seconds. 150 x (2s curl cap + 2s sleep) bounds the wait at ~10 min.
      tries=150
    fi
  fi
  webloc="$HOME/Applications/Captain's Cabinet.webloc"
  if mkdir -p "$HOME/Applications" \
     && printf '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n\t<key>URL</key>\n\t<string>%s</string>\n</dict>\n</plist>\n' "$DASH_URL" > "$webloc.tmp" \
     && plutil -lint "$webloc.tmp" >/dev/null \
     && mv "$webloc.tmp" "$webloc"; then
    echo "[opening] shortcut saved: $webloc (double-click it any time)"
  else
    rm -f "$webloc.tmp" || true
    echo "[opening] shortcut skipped: could not save $webloc. Nothing else is affected."
  fi
  ok=0
  waited=0
  echo "[opening] waiting for your Cabinet to answer. You don't need to do anything."
  for _ in $(seq 1 "$tries"); do
    curl -fsS --max-time 2 "${DASH_URL}api/health" >/dev/null 2>&1 && { ok=1; break; } || true
    sleep 2
    waited=$((waited + 2))
    # Say what is being waited on, and how to not wait next time. A silent
    # multi-minute pause at the end of a hatch reads as a hang.
    if [ "$((waited % 60))" = "0" ]; then
      echo "[opening] still starting (${waited}s so far — the first time, it builds itself). This is normal."
      echo "          Skip this next time: bash cabinet/scripts/hatch.sh --no-browser"
    fi
  done
  # Password handover. dashboard-password.sh NEVER prints the password — it
  # copies to the clipboard and says only that it did. That stays true here.
  if [ "$ok" = "1" ]; then
    bash "$DASH_SCRIPTS/dashboard-password.sh" --copy \
      || echo "[opening] password not copied — get it with: bash cabinet/scripts/dashboard-password.sh --copy"
  fi
  if [ "$ok" = "1" ] && [ -z "${SSH_CONNECTION:-}" ] && [ "${HATCH_NO_OPEN:-0}" != "1" ] \
     && command -v open >/dev/null 2>&1; then
    echo "[opening] Your Cabinet is open in your browser. Sign in with the password we"
    echo "          just copied for you — paste it in."
    open "$DASH_LANDING" || echo "[opening] couldn't open your browser — go to $DASH_LANDING yourself"
  elif [ "$ok" = "1" ]; then
    echo "[opening] your Cabinet is ready — go to $DASH_LANDING (we didn't open a window for you)"
  else
    echo "[opening] your Cabinet is taking longer than expected to answer."
    echo "          Nothing is broken and nothing is lost — give it a minute, then go to:"
    echo "          $DASH_LANDING"
    if [ "$self_start" = "1" ]; then
      echo "          If it still doesn't load, the notes are in: $DASH_LOG"
    else
      echo "          If it still doesn't load, run: bash cabinet/scripts/start-dashboard.sh"
    fi
  fi
  return 0
}
app_feel || echo "[opening] something unexpected happened while opening your browser; your Cabinet is still set up"
# The run's exit code, and the ONLY thing that may follow the tail: 0 = all
# green · 75 = hatched and the front door opened, but an optional background
# helper did not start. A real gate failure exited 1 from step_fail long ago.
exit "$HATCH_EXIT"
