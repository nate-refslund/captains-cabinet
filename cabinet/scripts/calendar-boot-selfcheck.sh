#!/usr/bin/env bash
# calendar-boot-selfcheck.sh — INFORMATIONAL officer boot check for the calendar
# TCC grant. Converts a SILENT officer-context calendar denial into ONE loud
# warroom line. It can NEVER enable, gate, or suppress a write — the double-book
# guard fails closed independently (calendar_read raises CalendarReadError →
# action_exec refuses the write). So this only tells; it never decides.
#
# It MUST run from the officer's boot TURN (claude → Bash → this script → helper),
# NOT from start-officer-mac.sh's own body: launchd → bash is a DIFFERENT
# responsible-process chain than the officer's claude → helper chain, so a probe
# there could pass while the real gather silently denies. It is wired as one step
# in start-officer-mac.sh's BOOT_PROMPT (see that file, right after the warroom
# self-announce).
#
# ALWAYS exits 0 — a probe failure must never block the officer from booting.
# Pure shell (no framework .py), so the clean-room ratchet does not apply.
set -uo pipefail

ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
HELPER="${CABINET_CAL_HELPER:-$ROOT/bin/cabinet-calread}"
RUNBOOK="docs/runbooks/calendar-officer-grant.md"

# Resolve exit code → (verdict, remedy). fullAccess=0 quiet; writeOnly=5 breaks
# undo; notDetermined=4 needs the GUI bootstrap; everything else = not granted.
verdict=""
remedy=""

probe_code=""
if [ -x "$HELPER" ]; then
  "$HELPER" probe >/dev/null 2>&1
  probe_code=$?
  # NOTE: `probe` reads authorizationStatus ONLY (no requestAccess) so it can
  # never block. Do NOT fall back to `read` on an old helper (exit 64) — `read`
  # calls requestFullAccessToEvents, which in a GUI-attached launchd/tmux session
  # with a notDetermined grant raises a TCC MODAL and blocks with NO timeout,
  # hanging the officer boot. An exit-64 (old helper) is itself the signal that a
  # rebuild is needed; treat it as such without spawning an access-requesting
  # subcommand.
  if [ "$probe_code" = "64" ]; then
    probe_code="oldhelper"
  fi
else
  probe_code="missing"
fi

case "$probe_code" in
  0)  verdict="ok" ;;
  5)  verdict="notok"; remedy="upgrade this helper's grant to Full Access (write-only silently breaks calendar undo)" ;;
  4)  verdict="notok"; remedy="run the one-time GUI bootstrap to grant Full calendar access" ;;
  oldhelper) verdict="notok"; remedy="calendar helper is an OLD build (no probe) — run cabinet/scripts/build-calendar-helper.sh then grant Full Access" ;;
  missing) verdict="notok"; remedy="calendar helper not built — run cabinet/scripts/build-calendar-helper.sh then grant Full Access" ;;
  *)  verdict="notok"; remedy="calendar Full Access is not granted for this officer context — re-grant" ;;
esac

if [ "$verdict" = "ok" ]; then
  exit 0   # granted → quiet
fi

LINE="⚠️ Calendar grant check: ${remedy}. Until fixed the double-book guard fails closed (calendar writes refused, never double-booked) and unattended calendar undo may be unavailable. Runbook: ${RUNBOOK}"

# Post ONE line to the warroom (launcher-agnostic; works for Telegram-dark lanes).
# The line is built HERE (deterministic), not by the LLM. Best-effort — a lost
# line never blocks boot, and the write path still fails closed regardless.
bash "$ROOT/cabinet/scripts/send-to-group.sh" "$LINE" >/dev/null 2>&1 || true

exit 0
