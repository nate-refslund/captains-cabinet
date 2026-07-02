#!/bin/bash
# due-followups.sh — READER for shared/interfaces/follow-ups.md.
#
# Prints the `## Active` follow-up entries that are DUE — i.e. whose
# `check_from` date is on or before today (UTC) AND whose `status` is `open`.
# This is the surface half of the dated follow-ups register: the briefing and
# the 30-min status-sweep call it to put due entries in front of the Chair, who
# then does GATHER-THEN-DECIDE per each entry's `nudge_if` (verify-resolved via
# brain/email BEFORE nudging — a resolved item stays silent). This script NEVER
# decides, nudges, or sends; it only selects which entries are ripe.
#
# Generic by design: any future dated follow-up is just one more line in the
# file — no change here. The format is the pipe-delimited contract documented in
# the file header:
#   id | deadline <date> | check_from <date> | subject | gather: … | nudge_if: … | status: <open|done>
#
# Robustness:
#   * Only the `## Active` section is scanned (entries under other headings —
#     e.g. a future `## Done` archive — are ignored).
#   * Field ORDER for date/status is not assumed: we locate `check_from` and
#     `status` by their key wherever they sit on the line, tolerating extra
#     whitespace and the `key: value` / `key value` prefixes.
#   * Date comparison is lexicographic on ISO YYYY-MM-DD (== chronological).
#   * A malformed line (no check_from, or no YYYY-MM-DD after it) is skipped,
#     never crashes the caller.
#
# Secrets: NONE. No network. Read-only on one local markdown file. Safe to run
# from any scheduled context.
#
# Usage:
#   due-followups.sh                 # human/markdown lines, one per due entry
#   due-followups.sh --json          # JSON array of due entries (objects)
#   due-followups.sh --count         # just the integer count of due entries
#   due-followups.sh --resolve <id> [--status <s>] [--note "<text>"]
#                                    # flip ONE entry's status (mark-done flow).
#                                    # <s> defaults to "done"; --note appends a
#                                    # "· note: <text>" annotation to the line.
#                                    # Used by the Chair AND the comms-officer's
#                                    # thread-watch (early-catch) to silence a
#                                    # follow-up the moment its thread resolves,
#                                    # so the date-trigger never fires a stale
#                                    # nudge. Rewrites only the matched entry,
#                                    # atomically. No-op (rc 0) if already that
#                                    # status; rc 4 if the id isn't found.
#   FOLLOWUPS_TODAY=2026-08-04 due-followups.sh   # override "today" (testing)
#   FOLLOWUPS_FILE=/path/to.md due-followups.sh   # override the file (testing)
#
# Exit status: 0 always when the file is readable (read modes: 0 due entries is
# not an error — it just prints nothing; resolve: 0 on success/no-op). Non-zero
# only if the register file is missing/unreadable (1), bad args (2), or
# --resolve id not found (4).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FOLLOWUPS_FILE="${FOLLOWUPS_FILE:-$ROOT/shared/interfaces/follow-ups.md}"

# Today in UTC (YYYY-MM-DD). Overridable via env for tests/verification.
TODAY="${FOLLOWUPS_TODAY:-$(date -u +%Y-%m-%d)}"

MODE="lines"
RESOLVE_ID=""
RESOLVE_STATUS="done"
RESOLVE_NOTE=""
case "${1:-}" in
  --json)  MODE="json" ;;
  --count) MODE="count" ;;
  --resolve)
    MODE="resolve"
    shift
    RESOLVE_ID="${1:-}"
    if [ -z "$RESOLVE_ID" ]; then
      echo "due-followups.sh: --resolve requires an <id>" >&2
      exit 2
    fi
    shift
    # Optional --status / --note flags, any order.
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --status) shift; RESOLVE_STATUS="${1:-done}"; shift ;;
        --note)   shift; RESOLVE_NOTE="${1:-}";       shift ;;
        *)
          echo "due-followups.sh: unknown --resolve flag '${1}' (expected --status | --note)" >&2
          exit 2
          ;;
      esac
    done
    ;;
  "")      MODE="lines" ;;
  *)
    echo "due-followups.sh: unknown arg '${1}' (expected --json | --count | --resolve | none)" >&2
    exit 2
    ;;
esac

# Read modes need only read access; --resolve needs write access too.
if [ ! -r "$FOLLOWUPS_FILE" ]; then
  echo "due-followups.sh: cannot read $FOLLOWUPS_FILE" >&2
  exit 1
fi
if [ "$MODE" = "resolve" ] && [ ! -w "$FOLLOWUPS_FILE" ]; then
  echo "due-followups.sh: cannot write $FOLLOWUPS_FILE (needed for --resolve)" >&2
  exit 1
fi

# ── --resolve <id> : the mark-done flow ──────────────────────────────────────
# Flip ONE `## Active` entry's `status:` to RESOLVE_STATUS (default "done"),
# matched by the entry's id (the first pipe-delimited field). Optionally append
# a "· note: <text>" annotation. Rewrites only that entry; the rest of the file
# is byte-for-byte preserved. Atomic via a temp file + mv. This is the single
# safe way to mark a follow-up resolved — both the Chair (after a nudge+action)
# and the comms-officer thread-watch (on a new counterparty reply) call it,
# instead of hand-editing the markdown.
if [ "$MODE" = "resolve" ]; then
  TMP="$(mktemp "${TMPDIR:-/tmp}/due-followups.XXXXXX")" || {
    echo "due-followups.sh: mktemp failed" >&2; exit 1; }
  # awk does the surgical edit. We pass the id/status/note in via -v (note is
  # sanitized of pipes/newlines by the caller contract; we also strip any '|'
  # here so it can't break the field structure).
  awk -v want="$RESOLVE_ID" -v newst="$RESOLVE_STATUS" -v note="$RESOLVE_NOTE" '
    function trim(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
    BEGIN { in_active = 0; changed = 0; gsub(/\|/, "/", note) }   # | in note → / (never break fields)
    /^##[[:space:]]/ {
      hdr = trim(substr($0, 3))
      in_active = (tolower(hdr) == "active") ? 1 : 0
      print; next
    }
    in_active && /^[[:space:]]*-[[:space:]]/ {
      line = $0
      # id = first pipe field, after stripping the "- " bullet.
      body = line
      sub(/^[[:space:]]*-[[:space:]]*/, "", body)
      id = body
      sub(/[[:space:]]*\|.*$/, "", id)
      id = trim(id)
      if (id == want) {
        # Replace the status value wherever "status:" / "status " sits.
        if (match(line, /status[:[:space:]]+[A-Za-z]+/)) {
          pre  = substr(line, 1, RSTART - 1)
          post = substr(line, RSTART + RLENGTH)
          line = pre "status: " newst post
        } else {
          # No status field present — append one (keeps the contract intact).
          line = line " | status: " newst
        }
        if (note != "") line = line " · note: " note
        changed = 1
      }
      print line; next
    }
    { print }
    END { exit (changed ? 0 : 4) }
  ' "$FOLLOWUPS_FILE" > "$TMP"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    mv "$TMP" "$FOLLOWUPS_FILE"
    echo "due-followups.sh: resolved '$RESOLVE_ID' → status: $RESOLVE_STATUS" >&2
    exit 0
  else
    rm -f "$TMP"
    if [ "$rc" -eq 4 ]; then
      echo "due-followups.sh: --resolve id '$RESOLVE_ID' not found in ## Active" >&2
      exit 4
    fi
    echo "due-followups.sh: --resolve failed (awk rc=$rc)" >&2
    exit 1
  fi
fi

# Single awk pass: track whether we're inside the `## Active` section, and for
# each entry line ("- ..." with pipe fields) emit it iff check_from<=today and
# status==open. We emit the RAW entry line (minus the leading "- ") for the
# default/lines mode, and a TAB-separated (raw, id, check_from) tuple that the
# json builder below re-parses. Keeping the heavy lifting in one awk keeps the
# parse identical across modes.
DUE_TSV="$(
  awk -v today="$TODAY" '
    function trim(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
    # Section tracking: a line beginning with "## " starts a new section.
    /^##[[:space:]]/ {
      hdr = trim(substr($0, 3))
      in_active = (tolower(hdr) == "active") ? 1 : 0
      next
    }
    # Only consider list-item entry lines while inside ## Active.
    in_active && /^[[:space:]]*-[[:space:]]/ {
      raw = $0
      # Strip the leading "- " bullet for the emitted entry text.
      entry = raw
      sub(/^[[:space:]]*-[[:space:]]*/, "", entry)
      entry = trim(entry)

      # Pull check_from date: first YYYY-MM-DD appearing AFTER the literal
      # "check_from" token anywhere on the line.
      cf = ""
      if (match(entry, /check_from[: ]+[0-9]{4}-[0-9]{2}-[0-9]{2}/)) {
        seg = substr(entry, RSTART, RLENGTH)
        if (match(seg, /[0-9]{4}-[0-9]{2}-[0-9]{2}/))
          cf = substr(seg, RSTART, RLENGTH)
      }
      if (cf == "") next            # no parseable check_from → skip

      # Pull status value (token right after "status"). Default missing→open
      # would be unsafe (could re-nudge a done item), so a missing status is
      # treated as NOT open (skip) — the contract requires an explicit status.
      st = ""
      if (match(entry, /status[: ]+[A-Za-z]+/)) {
        seg = substr(entry, RSTART, RLENGTH)
        sub(/^status[: ]+/, "", seg)
        st = tolower(trim(seg))
      }
      if (st != "open") next        # only open entries are due

      # Pull id: the first pipe-delimited field (before the first "|").
      id = entry
      sub(/[[:space:]]*\|.*$/, "", id)
      id = trim(id)

      # Due iff check_from <= today (ISO lexicographic == chronological).
      if (cf <= today) {
        # TAB-separated: raw-entry \t id \t check_from
        printf "%s\t%s\t%s\n", entry, id, cf
      }
    }
  ' "$FOLLOWUPS_FILE"
)"

# Count of due entries (empty DUE_TSV → 0).
if [ -z "$DUE_TSV" ]; then
  DUE_N=0
else
  DUE_N="$(printf '%s\n' "$DUE_TSV" | grep -c .)"
fi

case "$MODE" in
  count)
    echo "$DUE_N"
    ;;
  lines)
    # One markdown bullet per due entry (the raw entry text), so the output
    # drops straight into a "📌 Follow-ups due" briefing section.
    [ "$DUE_N" -eq 0 ] && exit 0
    printf '%s\n' "$DUE_TSV" | while IFS=$'\t' read -r entry _id _cf; do
      [ -n "$entry" ] && printf -- '- %s\n' "$entry"
    done
    ;;
  json)
    # JSON array of objects {id, check_from, entry}. We build it with a tiny
    # python (already on PATH for the cabinet) so quoting is correct; fall back
    # to a hand-rolled escape if python is unavailable.
    if command -v python3 >/dev/null 2>&1; then
      printf '%s' "$DUE_TSV" | python3 -c '
import sys, json
out = []
for line in sys.stdin.read().splitlines():
    if not line.strip():
        continue
    parts = line.split("\t")
    entry = parts[0] if len(parts) > 0 else ""
    _id = parts[1] if len(parts) > 1 else ""
    cf = parts[2] if len(parts) > 2 else ""
    out.append({"id": _id, "check_from": cf, "entry": entry})
print(json.dumps(out, ensure_ascii=False))
'
    else
      # Minimal fallback (no python): emit a best-effort array. Escapes the
      # two JSON-significant chars in the entry text.
      printf '['
      first=1
      printf '%s\n' "$DUE_TSV" | while IFS=$'\t' read -r entry _id _cf; do
        [ -z "$entry" ] && continue
        esc="${entry//\\/\\\\}"; esc="${esc//\"/\\\"}"
        idesc="${_id//\\/\\\\}"; idesc="${idesc//\"/\\\"}"
        [ "$first" -eq 1 ] || printf ','
        first=0
        printf '{"id":"%s","check_from":"%s","entry":"%s"}' "$idesc" "$_cf" "$esc"
      done
      printf ']\n'
    fi
    ;;
esac
