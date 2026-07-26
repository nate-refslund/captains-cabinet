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
# are NEVER automated — they print as numbered ERRAND NOTES for the human,
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
# path and exits non-zero. The only documented warn-and-continue: a missing
# TELEGRAM_COS_TOKEN name in cabinet/.env (the Chair boots Telegram-dark —
# rehearsal-verified behavior).
#
# Exit codes: 0 = chain green · 1 = a step failed · 64 = usage error.
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
LABELED demo receipt (receipt anatomy, emit-demo-receipt.sh), with a
flight log timing every step. v0 stops short of launchd by default and
prints numbered ERRAND NOTES for every human-only step.

Flags:
  --defaults           Non-interactive everywhere: setup-env.sh --defaults,
                       generate-instance.py --defaults, and auto-adopt when
                       the clone ships a previous deployment's instance/
                       (adoption archives aside, never deletes).
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
  --dry-run            Print the full numbered plan + errand notes, execute
                       nothing, exit 0.
  --with-launchd       Run the move-in (runbook section 6): deploy the Chair,
                       render + lint + bootstrap the measurement-plane plists,
                       health-check. Default is --no-launchd: move-in prints
                       as an errand note instead.
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
FLIGHT_LOG_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --defaults)     DEFAULTS=1 ;;
    --clean-room)   CLEAN_ROOM=1 ;;
    --dry-run)      DRY_RUN=1 ;;
    --with-launchd) WITH_LAUNCHD=1 ;;
    --no-launchd)   WITH_LAUNCHD=0 ;;   # the v0 default, accepted explicitly
    --with-drill)   WITH_DRILL=1 ;;
    --flight-log)   FLIGHT_LOG_ARG="${2:?--flight-log requires a path}"; shift ;;
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

# Telegram-dark check — NAME presence only; the value is never read, echoed,
# or logged (values-in-env, names-in-files). A function because the answer
# can change mid-run: the interactive setup-mac.sh wizard may write the name
# into cabinet/.env, so the final errand notes recompute it.
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
  echo "mode: defaults=$DEFAULTS clean-room=$CLEAN_ROOM with-launchd=$WITH_LAUNCHD with-drill=$WITH_DRILL"
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
  echo " 4. [preset]        write instance/config/active-preset from the answers' org_shape"
  echo "                    (portfolio -> portfolio, functional -> work — the generator's own mapping;"
  echo "                    custom shapes = named handback, set the file yourself)"
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
  else
    echo "15. [move-in]       DEFERRED (v0 default --no-launchd) — printed as an errand note"
  fi
  echo "16. [app-feel]      dashboard URL + Add-to-Dock hints; --with-launchd: probe + open + .webloc"
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
    do_set_preset)      echo 'echo <portfolio|work> > instance/config/active-preset   # from answers org_shape: portfolio->portfolio, functional->work' ;;
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
  # Mirrors the generator's OWN printed mapping (generate-instance.py next
  # steps: portfolio -> portfolio, functional -> work). Derivation reads the
  # answers file as data — no interview logic is reimplemented here.
  local answers="instance/config/cabinet-init.answers.yml" shape="" preset=""
  if [ ! -f "$answers" ]; then
    if [ -s instance/config/active-preset ]; then
      echo "answers file absent; keeping existing active-preset ($(tr -d '[:space:]' < instance/config/active-preset))"
      return 0
    fi
    echo "cannot derive the preset: $answers is missing and instance/config/active-preset is unset." >&2
    echo "Named handback — set it yourself, e.g.: echo portfolio > instance/config/active-preset" >&2
    return 1
  fi
  shape="$("$PY" -c '
import sys, yaml
a = yaml.safe_load(open(sys.argv[1])) or {}
print(str(((a.get("cabinet") or {}).get("org_shape")) or ""))' "$answers")"
  case "$shape" in
    portfolio)  preset="portfolio" ;;
    functional) preset="work" ;;
    *)
      echo "org_shape '$shape' has no preset mapping (custom shape)." >&2
      echo "Named handback — set instance/config/active-preset yourself, then re-run." >&2
      return 1 ;;
  esac
  printf '%s\n' "$preset" > instance/config/active-preset
  echo "active-preset = $preset (from answers org_shape: $shape)"
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
echo "==== HATCH v0 — recording to $LOG_DIR (flight-recorder rule) ===="
if [ "$CLEAN_ROOM" = "1" ]; then
  echo "==== CLEAN-ROOM — CABINET_RUNTIME_DIR -> $CABINET_RUNTIME_DIR ===="
  echo "     (scratch-routed runtime dir: the live /tmp/cabinet-runtime is never written)"
  flight_line "CLEAN_ROOM_RUNTIME_DIR $CABINET_RUNTIME_DIR"
fi
emit_plan

if [ "$TELEGRAM_NAMED" = "0" ]; then
  echo ""
  echo "WARN: TELEGRAM_COS_TOKEN is not named in cabinet/.env — the Chair will"
  echo "      boot Telegram-dark (documented warn-and-continue; errand note below)."
  flight_line "WARN telegram-dark (TELEGRAM_COS_TOKEN name absent)"
fi

# 1. host bootstrap
if [ "$DEFAULTS" = "1" ]; then
  run_step setup-env "seed cabinet/.env non-interactively (boot-path contract)" \
    bash cabinet/scripts/setup-env.sh --defaults
fi
if [ "$CLEAN_ROOM" = "1" ]; then
  run_step setup-mac "host preflight (clean-room: check only, no installs)" \
    bash cabinet/scripts/setup-mac.sh --check
  echo "    clean-room: install/service phases skipped (deps verified present);"
  echo "    launchd, the live Redis, and the live /tmp/cabinet-runtime are never"
  echo "    touched in this mode (runtime dir scratch-routed — see banner above)."
else
  run_step setup-mac "host bootstrap (boot-path fast lane)" \
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
run_step preset "select the active preset (runbook 4.1)" do_set_preset
echo ""
echo "NOTE: germline activation edits (runbook 4.2) are NOT automated — see the"
echo "      numbered errand notes at the end (mcp-scope.yml + officer-capabilities.conf)."
echo "      They are OPTIONAL: the roster hires only officers those two files"
echo "      already authorize, so this chain completes without them."
run_step roles "seed the durable roster (runbook 4.4)" do_bootstrap_roles
if [ "$CLEAN_ROOM" = "1" ]; then
  run_step load-preset "assemble the runtime (clean-room: Redis marks -> unused port $CLEANROOM_REDIS_PORT)" \
    env REDIS_HOST=127.0.0.1 REDIS_PORT="$CLEANROOM_REDIS_PORT" bash cabinet/scripts/load-preset.sh
else
  run_step load-preset "assemble the runtime (runbook 4.5)" \
    bash cabinet/scripts/load-preset.sh
fi

# 4. proofs (runbook step 5) — do not proceed past a red gate
# roster-authz (2026-07-26) runs FIRST and against the LIVE tree this hatch just
# wrote — it is a claim about THIS deployment's roster, not about the shipped
# egg, so it cannot live inside null-hatch (whose sandbox deliberately carries
# no deployment-local state). It fires the lockstep module's live arm, which
# skips on a bare checkout and asserts here because roster.yml now exists.
run_step roster-authz "roster authorization: every hired officer has capability + MCP-scope rows" \
  "$PY" -m pytest framework/tests/test_roster_conf_lockstep.py -q
run_step proof-a "P-a null-hatch gate (egg boots with NO captain data)" \
  bash cabinet/scripts/null-hatch.sh
run_step proof-b "P-b clean-room ratchets (pytest subset)" \
  "$PY" -m pytest framework/tests/test_clean_room.py \
    framework/tests/test_no_screenpipe_in_core.py \
    framework/tests/test_no_launcher_hardcode.py -q
run_step proof-c1 "P-c dry render: officer boot command assembly (zero side effects)" \
  bash cabinet/scripts/start-officer-mac.sh cos --dry-run
run_step proof-c2 "P-c dry render: plist render plan (zero side effects)" \
  bash cabinet/scripts/deploy-mac.sh --officer cos --dry-run
if [ "$WITH_DRILL" = "1" ]; then
  run_step proof-d "P-d kill-switch drill (fail-closed store)" do_drill
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
run_step first-receipt "FIRST RECEIPT: the genesis briefing (first-briefing.sh --local)" \
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
run_step demo-receipt "DEMO receipt: seed one labeled receipt-anatomy example (emit-demo-receipt.sh)" \
  bash cabinet/scripts/emit-demo-receipt.sh
DEMO_LOG="$HATCH_LOG_DIR/step-demo-receipt.log"
DEMO_LANDING="$(sed -n 's/^DEMO_RECEIPT=//p' "$DEMO_LOG" 2>/dev/null | tail -1 || true)"

# 6. move-in (runbook section 6) — deferred by default
if [ "$WITH_LAUNCHD" = "1" ]; then
  run_step movein-chair "move-in: deploy the Chair (launchd)" \
    bash cabinet/scripts/deploy-mac.sh --officer cos
  run_step movein-plists "move-in: render measurement-plane plists" \
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
  run_step movein-load "move-in: lint + bootstrap measurement-plane plists (bootout-first, idempotent)" \
    do_movein_load
  run_step movein-health "move-in: health check" \
    bash cabinet/scripts/health-check.sh
  echo ""
  echo "Move-in done. FINAL acceptance gate (run when the Chair is up):"
  echo "    bash cabinet/scripts/cabinet-doctor.sh   # exit 0 required"
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
echo "==== WHERE THINGS LIVE (minute one) ===="
echo "First briefing:        ${RECEIPT_LANDING:-see $RECEIPT_LOG}"
echo "DEMO receipt:          ${DEMO_LANDING:-see $DEMO_LOG}"
echo "                       (labeled demo — receipt anatomy; reply-to-undo works on real receipts only)"
echo "How it's governed:     docs/how-your-cabinet-is-governed.md  (one page, plain language)"
echo "Menu-bar companion:    bash cabinet/scripts/build-companion.sh && open \"bin/Cabinet Companion.app\""
echo "Dashboard:             ${DASH_URL} (wall display: ${DASH_URL}display)"
echo "App feel:              Safari File>Add to Dock, or Chrome menu > Cast, save and share > Install page as app"
echo ""
echo "==== HATCH VERDICT: GREEN (v0 chain complete) ===="
if [ "$WITH_LAUNCHD" = "1" ]; then
  echo "Host + instance + activation + proofs + first receipt + move-in: all green."
  echo "Final acceptance stays cabinet-doctor.sh GREEN (see above)."
else
  echo "Host + instance + activation + proofs + first receipt: all green."
  echo "The org is NOT live yet — v0 defaults to --no-launchd. Move in via the"
  echo "errand note above, or re-run: bash cabinet/scripts/hatch.sh --with-launchd"
fi

# ---- app-feel (Wave D) — bookmark + auto-open; convenience tail, NEVER a gate ----
# EOF is reached only on the GREEN path (step_fail exits 1 earlier). This tail
# must preserve exit 0: every branch returns 0; invocation carries || fallback.
app_feel() {
  local webloc ok
  if [ "$CLEAN_ROOM" = "1" ]; then
    echo "[app-feel] clean-room: skipped (no browser, no ~/Applications writes)"; return 0
  fi
  if [ "$WITH_LAUNCHD" != "1" ]; then
    echo "[app-feel] dashboard not started (--no-launchd default). Start: bash cabinet/scripts/start-dashboard.sh"
    echo "           then open $DASH_URL — no bookmark dropped for a server that isn't running."
    return 0
  fi
  webloc="$HOME/Applications/Captain's Cabinet.webloc"
  if mkdir -p "$HOME/Applications" \
     && printf '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n\t<key>URL</key>\n\t<string>%s</string>\n</dict>\n</plist>\n' "$DASH_URL" > "$webloc.tmp" \
     && plutil -lint "$webloc.tmp" >/dev/null \
     && mv "$webloc.tmp" "$webloc"; then
    echo "[app-feel] bookmark: $webloc (opens in your default browser)"
  else
    rm -f "$webloc.tmp" || true
    echo "[app-feel] bookmark skipped: could not write/validate $webloc (non-fatal)"
  fi
  ok=0
  for _ in $(seq 1 60); do
    curl -fsS --max-time 2 "${DASH_URL}api/health" >/dev/null 2>&1 && { ok=1; break; } || true
    sleep 2
  done
  if [ "$ok" = "1" ] && [ -z "${SSH_CONNECTION:-}" ] && [ "${HATCH_NO_OPEN:-0}" != "1" ]; then
    open "$DASH_URL" || echo "[app-feel] auto-open failed — open $DASH_URL manually"
  elif [ "$ok" = "1" ]; then
    echo "[app-feel] dashboard is UP — open $DASH_URL (auto-open skipped: SSH/HATCH_NO_OPEN)"
  else
    echo "[app-feel] AMBER: dashboard not reachable yet at ${DASH_URL}api/health (first build ~1-2 min)."
    echo "           Check: launchctl print gui/\$(id -u)/com.cabinet.dashboard — then open $DASH_URL"
  fi
  return 0
}
app_feel || echo "[app-feel] non-fatal: app-feel step hit an unexpected error; the hatch verdict above stands"
