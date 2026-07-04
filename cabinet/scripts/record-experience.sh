#!/bin/bash
# record-experience.sh — Write an experience record to Tier 3 + PostgreSQL,
# and emit an `experience_recorded` event (block 1c) so OVI's learning_rate
# counts it. Tier 3 (memory/tier3/experience-records/) is the CANONICAL
# experience store shared with framework/learning/experience.py — its
# list_records() parses the md files this script writes (2026-07-04
# unification), so these records feed skill induction directly.
# Called by Officers after completing any significant task.
#
# Usage: record-experience.sh <officer> <outcome> <task_summary> <what_happened> [lessons_learned] [tags]
#   outcome: success | failure | partial | escalated
#   tags: comma-separated, e.g. "git,deployment,migration"
#
# Optional (cross-cutting COUNTERFACTUAL-REPLAY, docs/meta-cognition-direction-2026-06-25.md):
#   COUNTERFACTUAL="<the one change that would have made this 10x better>" record-experience.sh ...
#   (or pass it as the 7th positional arg). Captured on the record and counted by a
#   normalized slug in Redis; escalation is REVERSIBILITY-TIERED (see block 1b):
#     - reversible self-adjustment (CF_REVERSIBLE=1 or a [reversible]/[self-adjust]
#       tag in the text) → escalates at the 1st occurrence (immediate, compounds);
#     - default / expensive / irreversible → gates on recurrence (CF_GATE_THRESHOLD,
#       default 3) — a real wall, not a one-off.
#   Passing neither signal preserves the prior >= 3 behavior exactly.
#
# Example:
#   record-experience.sh cto success "Fix migration drift" \
#     "Renumbered 3 colliding migration pairs, ran all migrations, verified 11 tables created" \
#     "Always check migration numbering before adding new migrations" \
#     "database,migrations,schema"

OFFICER="${1:?Usage: record-experience.sh <officer> <outcome> <task> <what_happened> [lessons] [tags]}"
OUTCOME="${2:?Outcome required: success|failure|partial|escalated}"
TASK_SUMMARY="${3:?Task summary required}"
WHAT_HAPPENED="${4:?Description of what happened required}"
LESSONS="${5:-}"
TAGS="${6:-}"
# Optional 7th field via env or positional (non-breaking — existing callers pass
# at most 6 args): "what ONE change would have made this 10x better?"
COUNTERFACTUAL="${COUNTERFACTUAL:-${7:-}}"

CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
DATE=$(date -u +%Y-%m-%d)
RECORD_ID=$(date +%s)-$$

# Validate outcome
case "$OUTCOME" in
  success|failure|partial|escalated) ;;
  *) echo "Invalid outcome: $OUTCOME (must be success|failure|partial|escalated)"; exit 1 ;;
esac

# ============================================================
# 1. Write markdown file to Tier 3 (filesystem)
# ============================================================
RECORD_DIR="$CABINET_ROOT/memory/tier3/experience-records"
mkdir -p "$RECORD_DIR"
RECORD_FILE="$RECORD_DIR/${DATE}-${OFFICER}-${RECORD_ID}.md"

cat > "$RECORD_FILE" << EOF
# Experience Record

- **Officer:** $OFFICER
- **Date:** $TIMESTAMP
- **Outcome:** $OUTCOME
- **Tags:** $TAGS

## Task
$TASK_SUMMARY

## What Happened
$WHAT_HAPPENED

## Lessons Learned
${LESSONS:-No specific lessons noted.}

## Counterfactual (one change → 10x)
${COUNTERFACTUAL:-(none noted)}
EOF

echo "Written to $RECORD_FILE"

# ============================================================
# 1b. Counterfactual-replay recurrence → escalation (REVERSIBILITY-TIERED)
# ============================================================
# Cross-cutting selector (docs/meta-cognition-direction-2026-06-25.md), now tiered
# by reversibility instead of a blunt count-for-everything (matches the
# individual-reflection skill guidance — adapt immediately when reversible, gate
# when not). We normalize the counterfactual to a slug + INCR a Redis counter;
# the threshold that triggers a proposal depends on the tier:
#
#   * REVERSIBLE tier — the counterfactual is an officer SELF-ADJUSTMENT that is
#     cheap to make and self-corrects next cycle if wrong (signalled by
#     CF_REVERSIBLE=1|true|yes OR a [reversible]/[self-adjust] tag in the text):
#     escalate at the FIRST occurrence. An immediate, reversible self-adjustment
#     that compounds — no waiting, no Captain spam (the proposal frames it as a
#     reversible self-adjustment, not a build-this capability gap).
#   * DEFAULT / IRREVERSIBLE tier — a capability gap that spends Captain attention
#     or a hard-to-reverse change: keep gating on "reversible + evidenced", i.e.
#     the recurrence threshold (CF_GATE_THRESHOLD, default 3). RECURRENCE OF THE
#     SAME wall is the evidence.
#
# DEFAULT-PRESERVING: a caller that passes NEITHER a reversibility signal NOR a
# CF_GATE_THRESHOLD override gets EXACTLY the prior behavior (escalate at >= 3).
# The live fleet's escalation cadence is therefore UNCHANGED until a caller opts
# in (marks a counterfactual reversible) or the default threshold is retuned.
#
# Host note: uses the same REDIS resolution as the counter reset below
# (${REDIS_HOST:-localhost}) — the legacy `-h redis` default silently failed on
# Mac-native (the Docker service name does not resolve), so the counter never
# incremented and NOTHING ever escalated. localhost resolves on Mac AND Docker
# exports REDIS_HOST=redis-<slug>, so both are correct.
if [ -n "$COUNTERFACTUAL" ]; then
  CF_LIB="$CABINET_ROOT/cabinet/scripts/meta-cognition/lib.sh"
  CF_REDIS_HOST="${REDIS_HOST:-localhost}"
  CF_REDIS_PORT="${REDIS_PORT:-6379}"

  # Reversibility tier: explicit env wins; else an inline [reversible]/[self-adjust] tag.
  CF_TIER="default"
  case "$(printf '%s' "${CF_REVERSIBLE:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|reversible) CF_TIER="reversible" ;;
  esac
  if [ "$CF_TIER" = "default" ]; then
    case "$(printf '%s' "$COUNTERFACTUAL" | tr '[:upper:]' '[:lower:]')" in
      *'[reversible]'*|*'[self-adjust]'*|*'[self adjust]'*) CF_TIER="reversible" ;;
    esac
  fi

  # Threshold: reversible → fire at 1; default/irreversible → CF_GATE_THRESHOLD (default 3).
  if [ "$CF_TIER" = "reversible" ]; then
    CF_THRESHOLD=1
  else
    CF_THRESHOLD="${CF_GATE_THRESHOLD:-3}"
  fi

  # Normalized slug: lowercase, alnum-and-space, first 8 salient words.
  CF_SLUG="$(printf '%s' "$COUNTERFACTUAL" \
    | tr '[:upper:]' '[:lower:]' \
    | tr -cs 'a-z0-9 ' ' ' \
    | tr -s ' ' \
    | awk '{ for(i=1;i<=NF && i<=8;i++) printf "%s%s", (i>1?"-":""), $i }')"
  if [ -n "$CF_SLUG" ] && command -v redis-cli >/dev/null 2>&1; then
    CF_KEY="cabinet:meta:counterfactual:$CF_SLUG"
    CF_COUNT="$(redis-cli -h "$CF_REDIS_HOST" -p "$CF_REDIS_PORT" INCR "$CF_KEY" 2>/dev/null)"
    [ "$CF_COUNT" = "1" ] && redis-cli -h "$CF_REDIS_HOST" -p "$CF_REDIS_PORT" EXPIRE "$CF_KEY" 2592000 >/dev/null 2>&1
    if [ -n "$CF_COUNT" ] && [ "$CF_COUNT" -ge "$CF_THRESHOLD" ] 2>/dev/null && [ -f "$CF_LIB" ]; then
      if [ "$CF_TIER" = "reversible" ]; then
        CF_TITLE="Reversible self-adjustment (counterfactual): ${CF_SLUG}"
        CF_BODY="$(printf '%s\n' \
          "An officer flagged a CHEAP, REVERSIBLE 'one change would 10x this' — escalated immediately (1st occurrence) because a reversible self-adjustment compounds and self-corrects next cycle if wrong; no need to wait for recurrence." \
          "Phrasing: ${COUNTERFACTUAL}" \
          "Proposed: let the officer apply this self-adjustment now and observe next cycle. Captain may APPROVE | EDIT | SKIP — but the bar is low because it is reversible.")"
      else
        CF_TITLE="Recurring counterfactual (${CF_COUNT}x) -> capability gap: ${CF_SLUG}"
        CF_BODY="$(printf '%s\n' \
          "The same 'one change would 10x this' counterfactual has recurred ${CF_COUNT} times (gate=${CF_THRESHOLD}) across experience records — that is a wall, not a one-off, and the change is expensive / not trivially reversible." \
          "Latest phrasing: ${COUNTERFACTUAL}" \
          "Proposed: open a capability-gap (the capability-gap skill, .claude/skills/capability-gap) to build the missing tool/skill/process. Captain decides: APPROVE the gap | EDIT scope | SKIP.")"
      fi
      ( . "$CF_LIB" \
        && mc_emit_proposal counterfactual "$CF_TITLE" "$CF_BODY" "batch-into-next-briefing" >/dev/null 2>&1 || true ) &
      disown 2>/dev/null || true
    fi
  fi
fi

# ============================================================
# 1c. Emit experience_recorded event (OVI learning_rate feed)
# ============================================================
# UNIFICATION (2026-07-04, lane/learn-0705): OVI's learning_rate component is
# count(experience_recorded events in window) (framework/ovi/compute.py +
# framework/ovi/components.yml) — but only the Python writer
# (framework/learning/experience.py record()) ever emitted that event, and
# the fleet records experience through THIS script. Result: learning_rate
# sat at 0 while real records accumulated on disk. Emit the same event here
# so both write paths feed the ledger.
#
# Safety/robustness:
#   * Values cross into Python via ENVIRONMENT VARIABLES, never interpolated
#     into the source — task summaries are arbitrary text; interpolation
#     would be a code-injection vector (Corridor-reviewed pattern).
#   * Best-effort end to end (`|| true`, output discarded): recording an
#     experience must NEVER fail because the event ledger hiccuped. The md
#     file above is the durable record either way — list_records() reads it.
#   * lesson_type mirrors the md→structured mapping in
#     framework/learning/experience.py (_OUTCOME_TO_LESSON_TYPE): keep the
#     two in sync if either changes.
#   * ATTRIBUTION (deliberate, reviewed cp1 #2): the event actor is the
#     positional $1 officer — the officer the RECORD belongs to — matching
#     the md file and the PG row. The Redis signal keys further down use the
#     SESSION officer (OFFICER_NAME env wins there) because they feed
#     per-session idle/reflection detection. Two different semantics; do not
#     "unify" them.
if [ -f "$CABINET_ROOT/framework/events/emitter.py" ] && command -v python3 >/dev/null 2>&1; then
  case "$OUTCOME" in
    success) EV_LESSON_TYPE="pattern" ;;
    failure) EV_LESSON_TYPE="anti_pattern" ;;
    *)       EV_LESSON_TYPE="blocker" ;;   # partial | escalated
  esac
  CABINET_ROOT="$CABINET_ROOT" \
  EV_RECORD_FILE="$RECORD_FILE" \
  EV_OFFICER="$OFFICER" \
  EV_LESSON_TYPE="$EV_LESSON_TYPE" \
  EV_TRIGGER="$TASK_SUMMARY" \
  python3 - <<'PYEOF' >/dev/null 2>&1 || true
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ["CABINET_ROOT"])
from framework.events.emitter import emit

record_id = Path(os.environ["EV_RECORD_FILE"]).stem
emit("experience_recorded", actor=os.environ.get("EV_OFFICER", "unknown"), payload={
    # experience_id keys the Store aggregate (emitter _AGGREGATE_MAP);
    # it equals the md file stem so the event links back to the record.
    "experience_id": record_id,
    "record_id": record_id,
    "lesson_type": os.environ.get("EV_LESSON_TYPE", "pattern"),
    "trigger_signal": os.environ.get("EV_TRIGGER", "")[:160],
    "applicability_scope": "this_role",
    "has_evidence": True,
    "source": "record-experience.sh",
})
PYEOF
fi

# ============================================================
# 2. Insert into PostgreSQL (if available)
# ============================================================
DATABASE_URL="${DATABASE_URL:-}"
if [ -n "$DATABASE_URL" ]; then
  # Parameterized query via psql -v + heredoc (injection-safe).
  # :'var' substitution only works with stdin/heredoc, NOT with -c flag.
  # Tags pass as comma-separated text and split server-side via string_to_array().
  # Phase 1 CP9: stamp cabinet_id so logs remain queryable when Phase 2 adds
  # a second Cabinet. Defaults to 'main' in Phase 1 (single-Cabinet deployments).
  CABINET_ID="${CABINET_ID:-main}"
  if psql "$DATABASE_URL" -q \
    -v officer="$OFFICER" \
    -v task_summary="$TASK_SUMMARY" \
    -v outcome="$OUTCOME" \
    -v what_happened="$WHAT_HAPPENED" \
    -v lessons="$LESSONS" \
    -v tags="$TAGS" \
    -v cabinet_id="$CABINET_ID" <<'SQLEOF' > /dev/null 2>&1
INSERT INTO experience_records (officer, task_summary, outcome, what_happened, lessons_learned, tags, cabinet_id)
VALUES (
  :'officer',
  :'task_summary',
  :'outcome',
  :'what_happened',
  :'lessons',
  CASE
    WHEN :'tags' = '' THEN ARRAY[]::TEXT[]
    ELSE string_to_array(:'tags', ',')
  END,
  :'cabinet_id'
);
SQLEOF
  then
    echo "Inserted into PostgreSQL experience_records"
  else
    echo "Warning: PostgreSQL insert failed (record saved to file)" >&2
  fi
else
  echo "No DATABASE_URL — saved to file only"
fi

# Reset experience record counters after recording.
# Host: localhost resolves on Mac-native AND Docker exports REDIS_HOST=redis-<slug>;
# the legacy `-h redis` default silently failed on Mac (Docker service name does not
# resolve), so last-experience never updated and the proactive-work / reflection-gate
# signals that read it were starved.
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
# Attribution fix (2026-07-04): this line used to be `${OFFICER_NAME:-unknown}`,
# which CLOBBERED the positional $1 officer whenever the OFFICER_NAME env was
# absent (manual/cron invocations) — so cabinet:last-experience:<officer> and
# cabinet:toolcalls:<officer> landed on "unknown" and the reflection-gate /
# proactive-work signals that read them per-officer (post-tool-use.sh) were
# starved. Env still wins (officer sessions export OFFICER_NAME); the
# positional arg is now the fallback instead of "unknown".
OFFICER="${OFFICER_NAME:-$OFFICER}"
if command -v redis-cli &>/dev/null; then
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "cabinet:last-experience:$OFFICER" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" EX 7200 > /dev/null 2>&1
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "cabinet:toolcalls:$OFFICER" 0 > /dev/null 2>&1
fi
