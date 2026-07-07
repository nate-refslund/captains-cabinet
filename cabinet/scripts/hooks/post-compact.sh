#!/bin/bash
# post-compact.sh — Fires after context compaction (auto or manual)
# Outputs essential skill refresh instructions as a system message.
# The output is injected directly into the officer's context.

OFFICER="${OFFICER_NAME:-unknown}"

CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

cat <<REFRESH
⚠️ CONTEXT COMPACTED — ESSENTIAL SKILL REFRESH REQUIRED

Your context was just compressed. Behavioral rules loaded earlier in this session may be lost. Re-read your essential skills NOW before continuing any work.

ALL OFFICERS — read these immediately:
1. memory/skills/evolved/telegram-communication.md — reactions (react to EVERY Captain message before replying), threading (always use reply_to), formatting rules, SEND FILES when referencing paths (Captain cannot access the server filesystem — attach files with reply(files=[...]))
2. memory/skills/individual-reflection.md — event-triggered reflection + value maximization step
3. The three Captain ledgers — re-read ALL THREE (SessionStart loads them at boot but does not necessarily re-fire on every compaction, so this is your post-compaction refresh):
   - shared/interfaces/captain-patterns.md (ratified standing behaviors — 4th loop)
   - shared/interfaces/captain-intents.md (inferred latent intents — 5th loop)
   - shared/interfaces/captain-decisions.md (decision trail — check before any design/UI work)
4. Your role definition in .claude/agents/${OFFICER}.md — re-read your full role
5. instance/memory/tier2/${OFFICER}/corrections.md — Captain corrections (mistakes to never repeat)

OFFICER-SPECIFIC — also read:
REFRESH

# Load officer-specific skill refresh from per-officer file (officer-agnostic)
SKILLS_FILE="$CABINET_ROOT/cabinet/officer-skills/${OFFICER}.txt"
if [ -f "$SKILLS_FILE" ]; then
  cat "$SKILLS_FILE"
else
  echo "- No officer-specific skills file found at ${SKILLS_FILE}."
  echo "- Re-read your role definition at .claude/agents/${OFFICER}.md for your specific responsibilities."
fi

echo ""

# ============================================================
# SESSION STATE RECOVERY — inject pre-compaction operational state
# ============================================================
STATE_FILE="$CABINET_ROOT/instance/memory/tier2/${OFFICER}/.session-state.json"
if [ -f "$STATE_FILE" ] && PARSED=$(jq '.' "$STATE_FILE" 2>/dev/null); then
  CAPTURED=$(echo "$PARSED" | jq -r '.captured_at // "unknown"')
  TOOL_CT=$(echo "$PARSED" | jq -r '.tool_calls // 0')
  TRIGGERS=$(echo "$PARSED" | jq -r '.pending_triggers // 0')

  # Check staleness — warn if state file is older than 2 hours.
  # Audit #11 (germline window 2, 2026-07-07): GNU-only `date -d` fails on
  # macOS -> CAPTURE_EPOCH=0 -> "state is ~494,000h old" on EVERY macOS
  # compaction, training officers to ignore the one real staleness signal.
  # BSD `date -j -f` fallback ported from post-tool-use.sh (2026-07-02 fix);
  # parse failure (0) now SKIPS the warning — unparseable is not stale.
  CAPTURE_EPOCH=$(date -d "$CAPTURED" +%s 2>/dev/null \
    || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "${CAPTURED%%.*}Z" +%s 2>/dev/null \
    || echo "0")
  NOW_EPOCH=$(date -u +%s)
  CAPTURE_AGE=$(( NOW_EPOCH - CAPTURE_EPOCH ))

  echo "SESSION STATE (captured at $CAPTURED, before compaction):"
  if [ "$CAPTURE_EPOCH" != "0" ] && [ "$CAPTURE_AGE" -gt 7200 ] 2>/dev/null; then
    echo "⚠️ WARNING: State is $((CAPTURE_AGE / 3600))h old — may not reflect current session."
  fi
  echo "- Tool calls this session: $TOOL_CT"
  echo "- Pending triggers at compaction: $TRIGGERS"

  # Print schedule timestamps
  SCHED=$(echo "$PARSED" | jq -r '.schedules // {} | to_entries[] | "  - \(.key): \(.value)"')
  if [ -n "$SCHED" ]; then
    echo "- Schedule last-run timestamps:"
    echo "$SCHED"
  fi

  # Re-surface the narrative excerpt captured at PreCompact — the officer's
  # own working notes + .remember buffer. This is a deterministic floor under
  # Claude Code's native compaction summary: even if the summary drops the
  # in-flight thread, these curated notes carry it back into context.
  NARR=$(echo "$PARSED" | jq -r '.narrative_excerpt // ""')
  if [ -n "$NARR" ] && [ "$NARR" != "null" ]; then
    echo ""
    echo "WORKING-MEMORY EXCERPT (your own notes at compaction — verify against current reality before acting):"
    echo "----------------------------------------"
    echo "$NARR"
    echo "----------------------------------------"
  fi

  echo ""
  echo "Read your working notes for full context: instance/memory/tier2/${OFFICER}/working-notes.md"
  echo ""
elif [ -f "$STATE_FILE" ]; then
  echo "⚠️ Pre-compaction state file exists but is corrupt. Read instance/memory/tier2/${OFFICER}/working-notes.md for context."
  echo ""
else
  echo "No pre-compaction state file found. Read instance/memory/tier2/${OFFICER}/working-notes.md for context."
  echo ""
fi

echo "Read the files above now before doing anything else. Do not skip this step."
echo ""
echo "MANDATORY REFLECTION (compaction = significant work happened):"
echo "Write a 3-level reflection to instance/memory/tier2/${OFFICER}/reflections/\$(date -u +%Y-%m-%d-%H%M).md:"
echo "  L1 WORK: What did I accomplish in this session? What worked, what failed?"
echo "  L2 WORKFLOW: What about my process could be better?"
echo "  L3 META: What pattern would improve the cabinet's improvement process itself?"
echo "Read memory/skills/holistic-thinking.md for the lens."
echo "Surface L2/L3 ideas to CoS via notify-officer.sh."
echo "After writing it, stamp the reflection via the shared host-correct sink (writes last-run + INCRs the retro counter — do NOT hand-write 'redis-cli -h redis', it silently fails on Mac):"
echo "  . ${CABINET_ROOT}/cabinet/scripts/lib/reflection.sh && reflection_stamp ${OFFICER}"
echo ""
echo "THEN:"
echo "1. Check for pending triggers (hook auto-delivers, but manual: source ${CABINET_ROOT}/cabinet/scripts/lib/triggers.sh && trigger_read ${OFFICER})"
echo "2. Re-create your /loop (safety net — will skip if already running):"

# Read the officer's loop prompt from file
LOOP_FILE="$CABINET_ROOT/cabinet/loop-prompts/${OFFICER}.txt"
if [ -f "$LOOP_FILE" ]; then
  LOOP_PROMPT=$(cat "$LOOP_FILE" | tr '\n' ' ' | head -c 200)
  echo "   /loop 5m ${LOOP_PROMPT}..."
else
  echo "   /loop 5m Check triggers and do proactive work per your role definition."
fi

exit 0
