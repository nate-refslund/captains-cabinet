#!/bin/bash
# add-followup.sh — the ENFORCED FRONT DOOR for creating a dated follow-up.
#
# Captain directive (captain-patterns.md → follow-ups-carry-their-own-
# verification): you CANNOT create a follow-up without its built-in done-check.
# This helper REQUIRES and validates every field and REJECTS an incomplete entry
# (naming the missing field), so a bare "remind me on date X" — the stale-nudge
# failure mode — is impossible. On valid input it appends ONE well-formed entry
# to shared/interfaces/follow-ups.md under `## Active`, in the exact pipe format
# the reader (due-followups.sh) parses and the briefing/sweep consume.
#
# Field names are consistent across this helper, the file header, and the
# reader: VERIFY→`gather:`, NUDGE→`nudge_if:`, RESOLVED_IF→`resolved_if:`,
# WATCH_SIGNAL→`thread_id:`. The reader keys off id (first pipe field),
# check_from, and status; the rest is carried inline to the Chair.
#
# Secrets: NONE. No network. Writes one local markdown file. Read-only on
# everything else.
#
# Usage (flags, any order):
#   add-followup.sh \
#     --id <slug> \
#     --subject "<one line>" \
#     --deadline <YYYY-MM-DD> \
#     --check-from <YYYY-MM-DD> \
#     --verify "<concrete how-to-check: thread-id / Monday board+status / brain query>" \
#     --resolved-if "<what counts as done → stay silent>" \
#     --nudge "<what to tell Nate if still open at check time>" \
#     [--watch-signal "<thread/source to watch for early-catch>"] \
#     [--status open]            # default open
#
#   FOLLOWUPS_FILE=/path/to.md add-followup.sh ...   # override file (testing)
#   ADD_FOLLOWUP_DRYRUN=1 add-followup.sh ...        # print the entry, don't write
#
# Exit status:
#   0  entry valid + appended (or printed under DRYRUN)
#   2  a required field missing / invalid / vague (message names the field)
#   3  id already exists in ## Active (duplicate)
#   1  file missing/unwritable, or no `## Active` section to append under
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FOLLOWUPS_FILE="${FOLLOWUPS_FILE:-$ROOT/shared/interfaces/follow-ups.md}"

ID=""; SUBJECT=""; DEADLINE=""; CHECK_FROM=""
VERIFY=""; RESOLVED_IF=""; NUDGE=""; WATCH_SIGNAL=""; STATUS="open"

die() { echo "add-followup.sh: $1" >&2; exit "${2:-2}"; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --id)            shift; ID="${1:-}" ;;
    --subject)       shift; SUBJECT="${1:-}" ;;
    --deadline)      shift; DEADLINE="${1:-}" ;;
    --check-from)    shift; CHECK_FROM="${1:-}" ;;
    --verify)        shift; VERIFY="${1:-}" ;;
    --resolved-if)   shift; RESOLVED_IF="${1:-}" ;;
    --nudge)         shift; NUDGE="${1:-}" ;;
    --watch-signal)  shift; WATCH_SIGNAL="${1:-}" ;;
    --status)        shift; STATUS="${1:-open}" ;;
    -h|--help)
      sed -n '1,45p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) die "unknown flag '$1'" 2 ;;
  esac
  shift
done

# ── Required-field enforcement: name the FIRST missing/invalid field ─────────
is_iso_date() { printf '%s' "$1" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; }

# A VERIFY that's just a vague gesture ("see if done", "check if resolved",
# "look into it") defeats the whole point — reject it. The check must point at a
# CONCRETE signal: a thread/email, a Monday board/id/status, or a brain/Outlook
# query. We reject when the text is too short OR matches a vague phrase AND
# carries no concrete anchor (a quote, an @, a board/id/url/status keyword).
verify_is_vague() {
  local v; v="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  # too short to be a real instruction
  [ "${#1}" -lt 12 ] && return 0
  # obvious vague stock phrases
  case "$v" in
    *"see if done"*|*"see if it"*|*"check if done"*|*"check if it"*\
    |*"check if resolved"*|*"look into it"*|*"follow up"*|*"figure out"*\
    |*"find out if"*|*"tbd"*|*"todo"*|*"somehow"*)
      # allow even a vague-sounding phrase IF it carries a concrete anchor
      case "$v" in
        *@*|*http*|*monday*|*board*|*thread*|*msg*|*query*|*search*\
        |*outlook*|*teams*|*status*|*"polads.eu"*|*neon*|*"\""*) return 1 ;;
        *) return 0 ;;
      esac
      ;;
  esac
  return 1
}

[ -n "$ID" ]          || die "missing required field: --id" 2
printf '%s' "$ID" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]*$' \
  || die "invalid --id '$ID' (use a kebab/snake slug: letters, digits, . _ -)" 2
[ -n "$SUBJECT" ]     || die "missing required field: --subject" 2
[ -n "$DEADLINE" ]    || die "missing required field: --deadline" 2
is_iso_date "$DEADLINE"   || die "invalid --deadline '$DEADLINE' (want YYYY-MM-DD)" 2
[ -n "$CHECK_FROM" ]  || die "missing required field: --check-from" 2
is_iso_date "$CHECK_FROM" || die "invalid --check-from '$CHECK_FROM' (want YYYY-MM-DD)" 2
# check_from must be on/before the deadline (ISO lexicographic == chronological)
[ "$CHECK_FROM" \> "$DEADLINE" ] && die "--check-from ($CHECK_FROM) is AFTER --deadline ($DEADLINE)" 2
[ -n "$VERIFY" ]      || die "missing required field: --verify (the CONCRETE how-to-check)" 2
verify_is_vague "$VERIFY" && die "--verify is too vague ('$VERIFY') — name a concrete signal: a thread-id, a Monday board+status, or a brain/Outlook query" 2
[ -n "$RESOLVED_IF" ] || die "missing required field: --resolved-if (what counts as done → stay silent)" 2
[ -n "$NUDGE" ]       || die "missing required field: --nudge (what to tell Nate if still open)" 2

case "$STATUS" in open|done|replied|snoozed) : ;; *) die "invalid --status '$STATUS' (open|done|replied|snoozed)" 2 ;; esac

# ── Sanitize free-text: strip pipes + newlines so fields can't break format ──
clean() { printf '%s' "$1" | tr '\n|' ' /' | sed 's/  */ /g; s/^ //; s/ $//'; }
SUBJECT="$(clean "$SUBJECT")"
VERIFY="$(clean "$VERIFY")"
RESOLVED_IF="$(clean "$RESOLVED_IF")"
NUDGE="$(clean "$NUDGE")"
WATCH_SIGNAL="$(clean "$WATCH_SIGNAL")"

# ── File + duplicate-id checks ───────────────────────────────────────────────
[ -f "$FOLLOWUPS_FILE" ] || die "register file not found: $FOLLOWUPS_FILE" 1
if [ -z "${ADD_FOLLOWUP_DRYRUN:-}" ] && [ ! -w "$FOLLOWUPS_FILE" ]; then
  die "register file not writable: $FOLLOWUPS_FILE" 1
fi
grep -q '^##[[:space:]]\+Active[[:space:]]*$' "$FOLLOWUPS_FILE" \
  || die "no '## Active' section in $FOLLOWUPS_FILE to append under" 1

# Duplicate id: any existing ## Active entry whose first pipe field == ID.
DUP="$(
  awk -v want="$ID" '
    function trim(s){gsub(/^[[:space:]]+|[[:space:]]+$/,"",s);return s}
    /^##[[:space:]]/ { ina=(tolower(trim(substr($0,3)))=="active")?1:0; next }
    ina && /^[[:space:]]*-[[:space:]]/ {
      b=$0; sub(/^[[:space:]]*-[[:space:]]*/,"",b); id=b; sub(/[[:space:]]*\|.*$/,"",id)
      if (trim(id)==want) { print "dup"; exit }
    }
  ' "$FOLLOWUPS_FILE"
)"
[ "$DUP" = "dup" ] && die "id '$ID' already exists in ## Active (pick a unique id)" 3

# ── Build the entry line (reader-parseable; optional fields only if present) ──
ENTRY="- ${ID} | deadline ${DEADLINE} | check_from ${CHECK_FROM} | ${SUBJECT}"
ENTRY="${ENTRY} | gather: ${VERIFY} | nudge_if: ${NUDGE} | resolved_if: ${RESOLVED_IF}"
[ -n "$WATCH_SIGNAL" ] && ENTRY="${ENTRY} | thread_id: ${WATCH_SIGNAL}"
ENTRY="${ENTRY} | status: ${STATUS}"

if [ -n "${ADD_FOLLOWUP_DRYRUN:-}" ]; then
  echo "$ENTRY"
  exit 0
fi

# ── Append under the LAST line of the ## Active section, atomically ──────────
# We append the new entry as the final line of the file IF ## Active is the last
# section (the register's shape today). To be robust to a future trailing
# section, we insert it right before the next "## " heading after ## Active, or
# at EOF if none. awk builds the new file to a temp, then mv.
TMP="$(mktemp "${TMPDIR:-/tmp}/add-followup.XXXXXX")" || die "mktemp failed" 1
awk -v entry="$ENTRY" '
  BEGIN { in_active=0; inserted=0 }
  /^##[[:space:]]/ {
    # Leaving ## Active for a new section → flush the entry just before it.
    if (in_active && !inserted) { print entry; inserted=1 }
    in_active = (tolower($0) ~ /^##[[:space:]]+active[[:space:]]*$/) ? 1 : 0
    print; next
  }
  { print }
  END { if (in_active && !inserted) print entry }
' "$FOLLOWUPS_FILE" > "$TMP" || { rm -f "$TMP"; die "awk append failed" 1; }

mv "$TMP" "$FOLLOWUPS_FILE"
echo "add-followup.sh: added '$ID' under ## Active (check_from $CHECK_FROM, deadline $DEADLINE)" >&2
exit 0
