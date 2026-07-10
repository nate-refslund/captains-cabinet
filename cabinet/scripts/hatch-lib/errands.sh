# shellcheck shell=bash
# hatch-lib/errands.sh — the ERRAND NOTES printer for hatch.sh (sourced, not run).
#
# External-by-nature and germline steps are NEVER automated by hatch.sh —
# they are printed as clearly-numbered errand notes for the human, exactly
# the way docs/plans/world-onboarding-hatching-2026-07-09.md §3 treats
# BotFather and TCC, and the way the mini-hatch runbook keeps the germline
# copy-paste edits in the Captain's hands. Each note says WHERE the errand
# happens (plainly, off-hatch), WHY it cannot be automated, and WHAT to do.
#
# Sources of record: docs/runbooks/mini-hatch-tonight-2026-07-07.md
# (steps 4.2 + 6, "Mini-manual steps") and the design doc §3 errand table.
# No secret values, chat ids, or real hostnames ever appear here.

ERRAND_N=0

# errand <title> — begin a numbered errand note
errand() {
  ERRAND_N=$((ERRAND_N + 1))
  echo ""
  echo "  ERRAND $ERRAND_N — $1"
}
errand_line() { echo "    $1"; }

# print_errand_notes <with_launchd:0|1> <telegram_named:0|1|unknown> <gen_log_hint>
#   with_launchd    1 = move-in ran (skip the move-in errand)
#   telegram_named  1 = TELEGRAM_COS_TOKEN name present in cabinet/.env
#   gen_log_hint    path to the generate-instance step log ("" in dry-run)
print_errand_notes() {
  local with_launchd="$1" telegram_named="$2" gen_log="$3"
  ERRAND_N=0
  echo ""
  echo "==== ERRAND NOTES (human-only steps — hatch.sh never automates these) ===="

  errand "Germline scope lines (lane-CEO entries) — Captain's hands only"
  errand_line "WHERE: your editor, at this clone:"
  errand_line "       cabinet/mcp-scope.yml            (agents: block)"
  errand_line "       cabinet/officer-capabilities.conf (capability rows)"
  errand_line "WHY:   germline discipline — hatch.sh NEVER writes germline files."
  errand_line "       On a FRESH clone they are not schg-locked; plain edits work"
  errand_line "       (runbook step 4.2). Chair-only hatch proceeds without this;"
  errand_line "       lane-CEO seeding waits until the lines are in."
  if [ -n "$gen_log" ]; then
    errand_line "WHAT:  copy-paste the exact entries generate-instance.py printed —"
    errand_line "       see: $gen_log"
  else
    errand_line "WHAT:  copy-paste the exact entries generate-instance.py prints in"
    errand_line "       its 'Next steps' block (captured in the gen step log)."
  fi

  errand "Chair bot token — BotFather -> cabinet/.env"
  errand_line "WHERE: Telegram -> @BotFather -> /newbot (a human conversation)."
  errand_line "WHY:   tokens never ship in the repo (values-in-env, names-in-files)."
  errand_line "WHAT:  put the token in cabinet/.env as TELEGRAM_COS_TOKEN=<token>"
  errand_line "       (chmod 600). Optional but recommended: VOYAGE_API_KEY=<key>"
  errand_line "       alongside it — without it org-memory search degrades honestly"
  errand_line "       to keyword-only (keyless fail-soft, verified 2026-07-07)."
  if [ "$telegram_named" = "1" ]; then
    errand_line "STATE: TELEGRAM_COS_TOKEN is named in cabinet/.env — done."
  else
    errand_line "STATE: not yet named in cabinet/.env — the Chair boots"
    errand_line "       Telegram-dark until this lands (documented warn-and-continue)."
  fi

  errand "TCC grants — ONLY if calendar/computer-use is wanted (skip for base hatch)"
  errand_line "WHERE: System Settings -> Privacy & Security, walked by:"
  errand_line "       bash cabinet/scripts/grant-mac-permissions.sh"
  errand_line "WHY:   macOS requires human clicks; grants are responsible-process-"
  errand_line "       scoped. NOT in the base hatch path (runbook Mini-manual 2)."

  if [ "$with_launchd" != "1" ]; then
    errand "MOVE-IN — raise the fleet (deferred: hatch.sh v0 defaults to --no-launchd)"
    errand_line "WHERE: this terminal, when you are ready to trust the org"
    errand_line "       (or re-run: bash cabinet/scripts/hatch.sh --with-launchd)."
    errand_line "WHY:   loading launchd agents starts a live org; v0 leaves that a"
    errand_line "       deliberate human step (runbook section 6)."
    errand_line "WHAT (in order):"
    errand_line "  bash cabinet/scripts/deploy-mac.sh --officer cos"
    errand_line "  python3.12 cabinet/scripts/generate-plists.py"
    errand_line "  for p in cabinet/launchd/generated/*.plist; do plutil -lint \"\$p\"; done"
    errand_line "  # bootout-first = idempotent on re-runs (no-op on a fresh box):"
    errand_line "  for p in cabinet/launchd/generated/*.plist; do launchctl bootout gui/\$(id -u) \"\$p\" 2>/dev/null || true; launchctl bootstrap gui/\$(id -u) \"\$p\"; done"
    errand_line "  bash cabinet/scripts/health-check.sh"
    errand_line "  bash cabinet/scripts/cabinet-doctor.sh   # the FINAL acceptance gate"
  fi

  errand "Healthchecks.io dead-man registration"
  errand_line "WHERE: your healthchecks.io account."
  errand_line "WHY:   needs the account owner; API-created checks ship with EMPTY"
  errand_line "       alert-channel lists (2026-07-02 drill) — assign channels."
  errand_line "WHAT:  create checks per cabinet/services.yml expected-floors (at"
  errand_line "       minimum verifier + drill-failed), ASSIGN ALERT CHANNELS, put"
  errand_line "       ping/API keys in cabinet/.env (names-not-values everywhere else)."

  errand "Germline lock — post-hatch Captain act (fresh clones start unlocked)"
  errand_line "WHERE: this terminal, with sudo:"
  errand_line "       sudo bash cabinet/scripts/germline-lock.sh lock"
  errand_line "WHY:   unlock/lock is Captain sudo by doctrine; never part of the"
  errand_line "       automated hatch. Posture upgrades ride the same ritual"
  errand_line "       (cabinet/docs/mac-mini-setup.md section 2.6)."

  echo ""
  echo "==== END ERRAND NOTES ===="
}
