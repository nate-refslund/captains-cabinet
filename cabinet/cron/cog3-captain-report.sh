#!/bin/bash
# cog3-captain-report.sh — the wake vehicle for the two COG-3 captain-facing
# report CLIs (scheduled 2026-07-26 per the Captain's arm-the-cabinet ruling).
#
#   cog3-captain-report.sh verdict-inbox     -> cog3-verdict-inbox.py    (daily)
#   cog3-captain-report.sh shadow-dividend   -> cog3-shadow-dividend.py  (weekly)
#
# WHY A WRAPPER AT ALL (and why these are not organ-runner organs): both CLIs
# take a DECLARED canonical `--now` and never read a clock (the cog3-staleness
# A-m8 purity idiom — same inputs always produce byte-identical output). An
# organ manifest's `entrypoints.run` is a fixed tracked string with nowhere to
# inject a timestamp, so the composed runner cannot host them. This wrapper is
# the smallest thing that can: it stamps --now, maps "graph never built" to an
# honest SKIP, and — for the weekly report — appends the Captain's window on
# the armed self-improvement loop.
#
# EXIT CONTRACT (what the no-silent-cron floor sees):
#   0  report written, or an honest SKIP (no objectives graph on this cabinet)
#   2  the CLI REFUSED (tampered / counterfactual / mixed-epoch store) — this
#      SHOULD page: a refusing instrument means the substrate is not trustworthy
#   3  wrapper misuse (unknown report name)
# A refusal writes NOTHING and leaves the last-report state byte-untouched;
# stale captain-facing advice is never emitted.
#
# Shell hardening: -uo pipefail, deliberately NOT -e — the failure paths below
# read $? after a command substitution, and errexit would abort ON the
# assignment, deleting the diagnostic the watchdog's JOB_ERROR_MARKERS scan
# pages on while the exit code still says 1 (failure that reads as silence).
# Same reasoning + same flags as cabinet/cron/research-sweep.sh.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
cd "$CABINET_ROOT" || exit 1

# Interpreter pin (the apoptosis-sweep.sh / self-improvement-loop.sh idiom):
# bare python3 under launchd is the 3.9 system Python; the framework is 3.12.
PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
[ -x "$PY" ] || PY="python3.12"

NOW="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
CACHE="${CABINET_OBJECTIVES_CACHE:-$CABINET_ROOT/cabinet/cache/objectives}"
REPORT="${1:-}"

# Validate the report name FIRST — before the cache pre-check below, so a typo
# in a services.yml row surfaces as the loud usage error it is instead of being
# masked by an honest "no graph yet" skip.
case "$REPORT" in
  verdict-inbox|shadow-dividend) : ;;
  *)
    echo "cog3-captain-report: unknown report '${REPORT}' (want: verdict-inbox|shadow-dividend)" >&2
    exit 3
    ;;
esac

# The built-graph sentinel (framework/objectives/query.py:166 serves
# <cache>/graph.jsonl). Absent = this cabinet never built the shadow objectives
# graph. The verdict-inbox CLI reports that as exit 2 — indistinguishable from a
# genuine REFUSE — so the wrapper pre-checks and skips instead, the same
# credless-skip idiom retrieval-eval-nightly.sh uses on a keyless box. A daily
# page for "a substrate you never turned on" is exactly the cries-wolf class
# that got half this fleet parked.
if [ ! -f "$CACHE/graph.jsonl" ]; then
  echo "cog3-captain-report[$REPORT]: SKIP — no objectives graph at $CACHE (run cabinet/scripts/cog3-rebuild.py to build one)"
  exit 0
fi

case "$REPORT" in
  verdict-inbox)
    "$PY" cabinet/scripts/cog3-verdict-inbox.py --cache "$CACHE" --now "$NOW" --json
    rc=$?
    echo "cog3-captain-report[verdict-inbox]: rc=$rc now=$NOW"
    exit "$rc"
    ;;
  shadow-dividend)
    "$PY" cabinet/scripts/cog3-shadow-dividend.py --cache "$CACHE" --now "$NOW"
    rc=$?
    if [ "$rc" -ne 0 ]; then
      echo "cog3-captain-report[shadow-dividend]: rc=$rc now=$NOW (no report written)"
      exit "$rc"
    fi
    # SAFEGUARD (b) of the 2026-07-26 arming ruling: the Captain accepted a
    # risk window when he armed the self-improvement loop's auto-apply, so the
    # window gets INSPECTED weekly rather than assumed. The section is rendered
    # from the application journal and appended to the report the CLI just
    # wrote (the CLI itself stays byte-pure: serve-surface only, no clock, no
    # env, no shelling out — appending afterwards keeps that property intact).
    REPORT_FILE="$CABINET_ROOT/shared/interfaces/cognitive/shadow-dividend-${NOW%%T*}.md"
    SECTION="$("$PY" cabinet/scripts/self-improvement-journal.py --weekly-section --now "$NOW" 2>&1)"
    sec_rc=$?
    if [ "$sec_rc" -ne 0 ]; then
      # Never lose the window: if the renderer fails, the section still lands in
      # this job's log, and the failure is visible without killing the report.
      echo "cog3-captain-report[shadow-dividend]: WARN self-improvement section rc=$sec_rc — ${SECTION}" >&2
      # ...but stderr alone is NOT the Captain's surface, and WARN is not in the
      # watchdog's JOB_ERROR_MARKERS (framework/watchdog/registry.py:753), so a
      # renderer failure would silently delete safeguard (b) of the arming
      # ruling: the report still arrives, just without the one window onto what
      # the armed loop applied to itself, and nothing pages. Say so IN the
      # report, where he actually reads. Still exit 0 — a cosmetic renderer
      # fault must not page, and must not lie either.
      if [ -f "$REPORT_FILE" ]; then
        printf '\n## Self-improvement — applied to itself\n\n**Unavailable this week.** The renderer failed (rc=%s), so what the armed learning loop applied to itself in this window is NOT shown below. Read it directly with `python3.12 cabinet/scripts/self-improvement-journal.py --list --since-days 7`; the job log carries the error.\n' "$sec_rc" >>"$REPORT_FILE"
      fi
    elif [ -f "$REPORT_FILE" ]; then
      printf '\n%s\n' "$SECTION" >>"$REPORT_FILE"
    else
      echo "cog3-captain-report[shadow-dividend]: WARN report file missing at $REPORT_FILE — section below went to the log only" >&2
      printf '%s\n' "$SECTION"
    fi
    echo "cog3-captain-report[shadow-dividend]: rc=0 now=$NOW report=$REPORT_FILE"
    exit 0
    ;;
esac
