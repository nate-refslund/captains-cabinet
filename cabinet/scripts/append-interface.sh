#!/bin/bash
# append-interface.sh — the ONLY sanctioned officer write path to the
# captain-law interface ledgers (the always-injected "Captain law" plane).
#
# Usage:
#   cabinet/scripts/append-interface.sh <captain-patterns|captain-intents|captain-decisions> <<'EOF'
#   ...entry text...
#   EOF
#
# Why this exists (audit 2026-07-07, severity CRITICAL): the captain-law
# plane (captain-patterns.md / captain-intents.md / captain-decisions.md +
# memory/skills/**) is injected into every officer session at start, but was
# officer-writable with NO guard — officer-authored text became standing law
# with no provenance (a self-persuasion / injection-persistence channel).
# pre-tool-use.sh §5/§5c now block direct Write/Edit and write-shaped Bash to
# those paths; THIS script is the carve-out: append-only, provenance-stamped,
# heading-safe.
#
# Contract (all enforced below):
#   - Target is one of THREE whitelisted ledgers — never a caller-supplied
#     path (no traversal; memory/skills/ has NO append lane: skills changes
#     go through the evolution loop as Captain-applied proposals).
#   - Content arrives on STDIN ONLY. Never eval'd, never interpolated into a
#     command — it flows through printf/cat straight into the file.
#   - APPEND-ONLY: the pre-append byte length + sha256 are captured under an
#     exclusive lock, the entry is written with >> only, and the ORIGINAL
#     PREFIX is re-hashed afterwards — if a single pre-existing byte changed,
#     the script reports corruption and exits non-zero.
#   - PROVENANCE: every entry lands under a "### officer-note — appended by
#     <officer> @ <UTC> [trust:officer]" heading. Captain-ratified entries in
#     these files use "## " headings (see the files' entry format), so
#     officer notes can NEVER collide with — or masquerade as — Captain law:
#     content containing a line that starts with "## " (or a top-level "# ")
#     is REJECTED unless the caller is the captain channel
#     (CABINET_CAPTAIN_CHANNEL=1, set only by Captain-side tooling such as
#     captain-rule-encoder.sh).
#
# Exit codes: 0 ok · 1 usage/validation refusal · 3 integrity check failed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

usage() {
  echo "Usage: append-interface.sh <captain-patterns|captain-intents|captain-decisions>  (entry text on stdin)" >&2
  echo "Appends an officer-note entry (append-only, provenance-stamped) to the captain-law ledger." >&2
  exit 1
}

[ $# -eq 1 ] || usage

# Fixed whitelist — the argument selects a slug, never a path.
case "$1" in
  captain-patterns)  TARGET="$CABINET_ROOT/shared/interfaces/captain-patterns.md" ;;
  captain-intents)   TARGET="$CABINET_ROOT/shared/interfaces/captain-intents.md" ;;
  captain-decisions) TARGET="$CABINET_ROOT/shared/interfaces/captain-decisions.md" ;;
  *)
    echo "REFUSED: unknown target '$1' — allowed: captain-patterns | captain-intents | captain-decisions" >&2
    exit 1
    ;;
esac

if [ ! -f "$TARGET" ]; then
  echo "REFUSED: target ledger does not exist: $TARGET (append-only interface never creates files)" >&2
  exit 1
fi

# Content: stdin only. Refuse an interactive tty (officers must pipe/heredoc)
# and refuse empty/whitespace-only bodies.
if [ -t 0 ]; then
  echo "REFUSED: entry text must arrive on stdin (pipe or heredoc) — no argv content." >&2
  exit 1
fi
CONTENT="$(cat)"
if [ -z "$(printf '%s' "$CONTENT" | tr -d '[:space:]')" ]; then
  echo "REFUSED: empty entry." >&2
  exit 1
fi

# Heading-collision gate: "## " is the Captain-entry heading format in all
# three ledgers ("# " is the file title). Officer appends live under
# "### officer-note" so retrieval/indexing can never read officer text as
# Captain-ratified law. Captain-side tooling may pass CABINET_CAPTAIN_CHANNEL=1.
if [ "${CABINET_CAPTAIN_CHANNEL:-0}" != "1" ]; then
  if printf '%s\n' "$CONTENT" | grep -qE '^##?[[:space:]]'; then
    echo "REFUSED: entry contains a '## ' (Captain-entry) or '# ' heading line. Officer appends are recorded under a '### officer-note' heading — use '###'-or-deeper headings (or plain text) inside your entry." >&2
    exit 1
  fi
fi

WHO="${CLAUDE_OFFICER:-${OFFICER:-${OFFICER_NAME:-unknown}}}"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Exclusive lock on the ledger while we hash + append + re-verify, so a
# concurrent appender cannot interleave (prefix-hash race). flock(1) when
# available (repo-standard, cf. cabinet-spawn.sh); mkdir-spinlock fallback
# for hosts without it (macOS ships no flock — homebrew provides one).
LOCKDIR=""
if command -v flock >/dev/null 2>&1; then
  exec 9>>"$TARGET"
  if ! flock -w 15 9; then
    echo "REFUSED: could not acquire lock on $TARGET within 15s." >&2
    exit 1
  fi
else
  LOCKDIR="${TMPDIR:-/tmp}/append-interface.$(basename "$TARGET").lock"
  _tries=0
  until mkdir "$LOCKDIR" 2>/dev/null; do
    _tries=$((_tries + 1))
    if [ "$_tries" -ge 150 ]; then
      echo "REFUSED: could not acquire lock ($LOCKDIR) within 15s." >&2
      exit 1
    fi
    sleep 0.1
  done
  trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT
fi

ORIG_LEN=$(wc -c < "$TARGET" | tr -d '[:space:]')
ORIG_SHA=$(shasum -a 256 "$TARGET" | awk '{print $1}')

# Append the provenance-stamped entry. >> is the only write; the body is
# emitted with printf '%s' (never eval, never command-substituted).
{
  printf '\n### officer-note — appended by %s @ %s [trust:officer]\n\n' "$WHO" "$STAMP"
  printf '%s\n' "$CONTENT"
} >> "$TARGET"

# Integrity tripwire: the original prefix must be byte-identical.
NEW_PREFIX_SHA=$(head -c "$ORIG_LEN" "$TARGET" | shasum -a 256 | awk '{print $1}')
if [ "$NEW_PREFIX_SHA" != "$ORIG_SHA" ]; then
  echo "INTEGRITY FAILURE: pre-existing bytes of $TARGET changed during append (prefix sha256 mismatch: $ORIG_SHA -> $NEW_PREFIX_SHA). File may be corrupted — alert the Captain; restore from git." >&2
  exit 3
fi

NEW_LEN=$(wc -c < "$TARGET" | tr -d '[:space:]')
echo "APPENDED: $(basename "$TARGET") +$((NEW_LEN - ORIG_LEN)) bytes by $WHO @ $STAMP (prefix sha256 verified unchanged: $ORIG_SHA)"

# Best-effort Cabinet Memory ingestion (2026-07-07 review fix): this append
# is a plain bash write, so the PostToolUse Write/Edit hook
# (post-file-write-memory.sh) never fires for it, direct officer Write/Edit
# to the ledgers is pre-tool-use §5 blocked, and memory-reconcile.sh
# deliberately excepts captain-decisions.md — without this block the
# sanctioned append lane was the ONE ledger write path that never reached
# cabinet_memory. Re-queue the ledger through the hook's own shared parsing
# library (captain-decisions → per-H2-entry upsert; patterns/intents →
# whole-file embed). Backgrounded + fully best-effort: a missing .env /
# lib / redis silently no-ops and NEVER changes the appender's exit code.
# fd 9 (flock) is closed inside so the subshell cannot hold the ledger lock.
(
  set -a
  source "$CABINET_ROOT/cabinet/.env" 2>/dev/null
  set +a
  source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh" 2>/dev/null
  POST_FILE_WRITE_MEMORY_LIB=1 source "$CABINET_ROOT/cabinet/scripts/hooks/post-file-write-memory.sh" 2>/dev/null
  declare -f memory_queue_embed > /dev/null 2>&1 || exit 0
  declare -f pfwm_queue_watched_file > /dev/null 2>&1 || exit 0
  pfwm_queue_watched_file "$TARGET" "$WHO" || true
) > /dev/null 2>&1 9>&- &

exit 0
