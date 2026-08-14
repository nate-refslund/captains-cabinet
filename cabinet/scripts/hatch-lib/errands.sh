# shellcheck shell=bash
# hatch-lib/errands.sh — the end-of-run CHECKLIST printer for hatch.sh
# (sourced, not run).
#
# External-by-nature and germline steps are NEVER automated by hatch.sh —
# they are printed as a clearly-numbered checklist for the human, exactly
# the way docs/plans/world-onboarding-hatching-2026-07-09.md §3 treats
# BotFather and TCC, and the way the mini-hatch runbook keeps the germline
# copy-paste edits in the Captain's hands. Each item says WHERE it happens
# (plainly, off-hatch), WHY it cannot be automated, and WHAT to do.
#
# WORDING (2026-08-12, never-strand pass): these lines are read by whoever
# double-clicked the app, so they are written for a person and not for this
# codebase. Technical names survive only where the person has to TYPE them
# (a filename, a command, an env-var NAME). The reasoning stays — it is what
# makes the checklist trustworthy rather than bossy.
#
# Sources of record: docs/runbooks/mini-hatch-tonight-2026-07-07.md
# (steps 4.2 + 6, "Mini-manual steps") and the design doc §3 errand table.
# No secret values, chat ids, or real hostnames ever appear here.

ERRAND_N=0

# errand <title> — begin a numbered checklist item
errand() {
  ERRAND_N=$((ERRAND_N + 1))
  echo ""
  echo "  $ERRAND_N. $1"
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
  echo "==== YOUR CHECKLIST — the few things only you can do ===="
  echo "None of them are needed to start using your Cabinet today."

  errand "Add a second team lead — only if you want one. OPTIONAL."
  errand_line "Where: two settings files, in your text editor, in this folder:"
  errand_line "       cabinet/mcp-scope.yml"
  errand_line "       cabinet/officer-capabilities.conf"
  errand_line "Why:   these two decide what your Cabinet is allowed to do, so"
  errand_line "       nothing edits them automatically — not even the setup you"
  errand_line "       just ran. They are yours."
  errand_line "Now:   nothing is waiting on this. Your Cabinet is set up and works"
  errand_line "       with the one lead it already has."
  if [ -n "$gen_log" ]; then
    errand_line "To do it: copy the exact lines the setup printed for you —"
    errand_line "       they are saved in: $gen_log"
    errand_line "       — then run these two, in order:"
    errand_line "         python3.12 cabinet/scripts/generate-instance.py"
    errand_line "         bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml"
  else
    errand_line "To do it: copy the exact lines the setup prints under 'Next steps'"
    errand_line "       (they are saved in the setup log), then run the generator"
    errand_line "       and bootstrap-roles.sh --roster instance/config/roster.yml."
  fi

  errand "Let your Cabinet message you on Telegram"
  errand_line "Where: your browser. Open your Cabinet and go to Integrations >"
  errand_line "       Telegram, or click 'Connect Telegram' on the front page."
  errand_line "Why:   only you can create a bot — Telegram will not hand one to a"
  errand_line "       program — and keys are never shipped inside this software."
  errand_line "To do it: the four steps on that page walk you through it. It sends"
  errand_line "       you a message at the end so you can see it worked. No"
  errand_line "       terminal, no files to edit, nothing to copy into this window."
  errand_line "       While you are in Integrations, a Voyage key is worth adding:"
  errand_line "       without it, searching your Cabinet's memory still works but"
  errand_line "       matches words rather than meaning."
  if [ "$telegram_named" = "1" ]; then
    errand_line "Now:   done — a token is already saved."
  else
    errand_line "Now:   not set up yet, so your Cabinet won't message you on"
    errand_line "       Telegram. Everything else works without it."
  fi

  errand "Mac permissions — only if you want calendar or screen access. OPTIONAL."
  errand_line "Where: System Settings > Privacy & Security. This walks you through it:"
  errand_line "       bash cabinet/scripts/grant-mac-permissions.sh"
  errand_line "Why:   macOS only accepts these from a person clicking, by design."
  errand_line "Now:   not needed for anything you have set up so far."

  if [ "$with_launchd" != "1" ]; then
    errand "Let your Cabinet keep working while you're away"
    errand_line "Where: this window, whenever you're ready. The one-line way is to"
    errand_line "       run: bash cabinet/scripts/hatch.sh --with-launchd"
    errand_line "Why:   this is what makes your Cabinet run in the background instead"
    errand_line "       of only while you're watching, so it waits for you to say go."
    errand_line "Now:   not on. Everything in your browser works without it."
    errand_line "The long way, if you prefer to run the steps yourself:"
    errand_line "  bash cabinet/scripts/deploy-mac.sh --officer cos"
    errand_line "  python3.12 cabinet/scripts/generate-plists.py"
    errand_line "  for p in cabinet/launchd/generated/*.plist; do plutil -lint \"\$p\"; done"
    errand_line "  # bootout-first = idempotent on re-runs (no-op on a fresh box):"
    errand_line "  for p in cabinet/launchd/generated/*.plist; do launchctl bootout gui/\$(id -u) \"\$p\" 2>/dev/null || true; launchctl bootstrap gui/\$(id -u) \"\$p\"; done"
    errand_line "  bash cabinet/scripts/health-check.sh"
    errand_line "  bash cabinet/scripts/cabinet-doctor.sh   # the final all-clear check"
  fi

  errand "Get told if your Cabinet ever goes quiet (healthchecks.io)"
  errand_line "Where: your own healthchecks.io account (free)."
  errand_line "Why:   only the account owner can set this up, and a check created"
  errand_line "       through the API arrives with NOBODY on its alert list — so it"
  errand_line "       watches silently and tells no one. Set the alerts yourself."
  errand_line "To do it: create one check per expected-floor row in"
  errand_line "       cabinet/services.yml (at minimum verifier + drill-failed),"
  errand_line "       ADD YOURSELF TO EACH ALERT LIST, and put the keys in"
  errand_line "       cabinet/.env."
  errand_line "       Also create these three and paste their slugs into"
  errand_line "       instance/config/liveness.yml (see the next item):"
  errand_line "         fleet_alive       period ~1h,  grace ~30m"
  errand_line "         captain_outbound  period ~1.5d, grace ~6h"
  errand_line "         captain_inbound   period ~7d,   grace ~1d"
  errand_line "       Give each cabinet its OWN slugs: if two share one, a cabinet"
  errand_line "       that has died looks just like one that is merely quiet."

  errand "Turn that warning on — until you do, silence looks exactly like healthy"
  errand_line "Where: this window and your text editor, in this folder."
  errand_line "Why:   every warning your Cabinet can raise about itself runs inside"
  errand_line "       your Cabinet — so if the whole thing stops, the warning stops"
  errand_line "       with it. That really happened here once, and nothing was heard"
  errand_line "       for five days. The two files below are the part that keeps"
  errand_line "       watching from outside. Leaving this off is not the safe choice:"
  errand_line "       it is the silent one, and silence looks exactly like fine."
  errand_line "To do it, in order:"
  errand_line "  cp instance/config/fleetwatch.yml.example instance/config/fleetwatch.yml"
  errand_line "  cp instance/config/liveness.yml.example  instance/config/liveness.yml"
  errand_line "  \$EDITOR instance/config/liveness.yml    # instance_id, base_url, slugs"
  errand_line "  \$EDITOR instance/config/fleetwatch.yml  # keep only sources you run"
  errand_line "  python3.12 cabinet/scripts/fleet-deadman.py --status   # expect local+external"
  errand_line "  python3.12 cabinet/scripts/fleet-deadman.py --dry-run  # expect a verdict"
  errand_line "  python3.12 cabinet/scripts/fleet-deadman-install.py --install"
  errand_line "  # then run the two launchctl lines it prints (it never runs them)"
  errand_line "Then test it: don't trust a green. Switch one thing off, wait, and"
  errand_line "       confirm you actually get told. A warning you have never seen"
  errand_line "       fire is a hope, not a warning."

  errand "Lock the files that decide what your Cabinet may do"
  errand_line "Where: this window. It asks for your Mac password:"
  errand_line "       sudo bash cabinet/scripts/germline-lock.sh lock"
  errand_line "Why:   after this, those files can only be changed by you, deliberately"
  errand_line "       — nothing your Cabinet runs can rewrite its own rules. Setup"
  errand_line "       never does this for you, because it needs your password."
  errand_line "       Details: cabinet/docs/mac-mini-setup.md section 2.6."

  echo ""
  echo "==== END OF CHECKLIST ===="
}
