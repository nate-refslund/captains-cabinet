#!/bin/bash
# session-start.sh — SessionStart hook (gap report G10)
#
# Fires once per Claude Code session, before any UserPromptSubmit. Loads the
# officer's boot ritual context — captain triplet + tier 2 working notes
# excerpt — into the session via `hookSpecificOutput.additionalContext`.
#
# This automates Tier 1 required reading items 7, 10, 11 from CLAUDE.md so
# officers can stop the manual `Read shared/interfaces/captain-*.md` step.
#
# Side-effect-only on failure: any read error degrades gracefully to a
# shorter context block; the hook never blocks session start.
#
# Disable via: SESSION_START_HOOK_ENABLED=0

set -u

if [ "${SESSION_START_HOOK_ENABLED:-1}" = "0" ]; then
  exit 0
fi

# Hook lives at cabinet/scripts/hooks/, so repo root is three levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." 2>/dev/null && pwd)}"
OFFICER="${OFFICER_NAME:-${CABINET_OFFICER:-unknown}}"

TRIPLET_DIR="$CABINET_ROOT/shared/interfaces"
TIER2_DIR="$CABINET_ROOT/instance/memory/tier2/$OFFICER"

# Build the context block. Skip files that don't exist so a freshly-cloned
# repo with no Captain triplet yet doesn't emit empty sections.
context=""

add_section() {
  local title="$1"
  local body="$2"
  if [ -n "$body" ]; then
    context="${context}## ${title}\n\n${body}\n\n"
  fi
}

if [ -f "$TRIPLET_DIR/captain-patterns.md" ]; then
  # Patterns are append-only and grow over time; cap at 100 lines for the
  # session boot blast.
  body="$(head -100 "$TRIPLET_DIR/captain-patterns.md" 2>/dev/null)"
  add_section "Captain Patterns (4th-loop ledger — head 100)" "$body"
fi

if [ -f "$TRIPLET_DIR/captain-intents.md" ]; then
  body="$(head -100 "$TRIPLET_DIR/captain-intents.md" 2>/dev/null)"
  add_section "Captain Intents (5th-loop ledger — head 100)" "$body"
fi

if [ -f "$TRIPLET_DIR/captain-decisions.md" ]; then
  # Decisions are most useful from the tail (most recent decisions matter).
  body="$(tail -40 "$TRIPLET_DIR/captain-decisions.md" 2>/dev/null)"
  add_section "Captain Decisions (last 40 lines)" "$body"
fi

if [ -d "$TIER2_DIR" ]; then
  notes="$(ls -1 "$TIER2_DIR" 2>/dev/null | head -20)"
  if [ -n "$notes" ]; then
    add_section "Tier 2 Working Notes ($OFFICER)" "Files in instance/memory/tier2/$OFFICER:\n\`\`\`\n$notes\n\`\`\`"
  fi
fi

# Nothing to inject — exit silently.
if [ -z "$context" ]; then
  exit 0
fi

# Emit hookSpecificOutput per Sprint A G4 standardization.
header="# Session-Start Boot Context ($OFFICER)\n\nAutomatically loaded by cabinet/scripts/hooks/session-start.sh — Tier 1 reading items 7/10/11 from CLAUDE.md. Skim before composing the first reply.\n\n"
full_context="$(printf '%b%b' "$header" "$context")"

# jq -Rs reads stdin as raw string, then we wrap in the hookSpecificOutput
# envelope. Quote-safe via --arg.
printf '%s' "$full_context" | jq -Rs --slurpfile _ /dev/null '
  {
    "hookSpecificOutput": {
      "additionalContext": .
    }
  }
' 2>/dev/null || true

exit 0
