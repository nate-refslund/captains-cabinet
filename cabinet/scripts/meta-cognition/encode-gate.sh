#!/bin/bash
# cabinet/scripts/meta-cognition/encode-gate.sh — LAYER 1 (PREVENT)
#
# The encode-time anti-accretion gate. Called at the encode chokepoint — when an
# officer (or the captain-rule-encoder hook) is about to write a NEW
# pattern/rule/skill. It answers, BEFORE row N+1 is written:
#
#   "Is this an instance of an existing principle? Should this be a principle,
#    not a case?"
#
# If YES it emits a proposal-only, per-item Captain-gated entry to the
# meta-cognition proposal ledger suggesting the collapse/generalization. It NEVER
# blocks the encode and NEVER applies anything — the new rule still gets written;
# the gate just flags "consider generalizing instead" for the Captain to decide.
#
# Concrete memories/facts are EXEMPT (mc_is_leave_as_is): a board id, model id,
# NATE_EMAILS, a secret, a URL, a date — those are facts, not generalizable
# behaviors, so the gate stays silent on them.
#
# Selectors (the design's "generator paired with a hard selector"):
#   1. mc_is_leave_as_is — facts exempt (no proposal).
#   2. Overlap floor (similarity.py) — only flags when the candidate meaningfully
#      overlaps an EXISTING principle (>= half the candidate's salient keywords
#      already live in one existing pattern). A genuinely-novel rule (no neighbor)
#      is NOT flagged — adding it is correct.
#
# Usage:
#   bash encode-gate.sh "<candidate rule/pattern text>"
#   echo "<candidate text>" | bash encode-gate.sh -
#   ENCODE_GATE_ENABLED=0 ...   # disable (no-op, exit 0)
#
# Exit: always 0 (warn-only). Prints the proposal id to stdout if it flagged, or
# nothing if exempt/novel. Never blocks the caller.
#
# Reversibility: rm this file; the encode paths fall back to plain append.

set -u

[ "${ENCODE_GATE_ENABLED:-1}" = "0" ] && exit 0

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
. "$SELF_DIR/lib.sh"

CANDIDATE="${1:-}"
if [ "$CANDIDATE" = "-" ] || [ -z "$CANDIDATE" ]; then
  CANDIDATE="$(cat 2>/dev/null)"
fi
[ -z "$CANDIDATE" ] && exit 0

# Selector 1 — concrete facts EXEMPT. A fact is not an accretion candidate.
if mc_is_leave_as_is "$CANDIDATE" >/dev/null 2>&1; then
  exit 0
fi

# LAYER 2 (HARVEST) accretion signal — this is a genuine rule/principle being
# encoded (not a fact), so the rule-base grew. Bump the accretion counter HERE,
# the single chokepoint every encode (auto hook + manual skill paths) flows
# through. The harvester fires once enough has accreted since the last harvest.
# Best-effort; a Redis miss degrades to "never auto-fires" (the retro is the
# floor). Disable independently with META_ACCRETION_ENABLED=0.
if [ "${META_ACCRETION_ENABLED:-1}" != "0" ]; then
  mc_accretion_incr 1 >/dev/null 2>&1 || true
fi

# Selector 2 — does an EXISTING principle/pattern already cover this? The scorer
# (similarity.py) returns "<best heading>\t<overlap>" when the candidate is
# substantially covered by one existing principle, or nothing when it is novel.
PATTERNS_FILE="${PATTERNS_FILE:-$MC_REPO_ROOT/shared/interfaces/captain-patterns.md}"
FLOOR="${ENCODE_GATE_OVERLAP_FLOOR:-0.50}"

MATCH="$(printf '%s' "$CANDIDATE" | python3 "$SELF_DIR/similarity.py" - "$PATTERNS_FILE" "$FLOOR" 2>/dev/null)"

# No meaningful neighbor → the rule is novel; adding it is correct. Stay silent.
[ -z "$MATCH" ] && exit 0

NEIGHBOR_TITLE="$(printf '%s' "$MATCH" | cut -f1)"
NEIGHBOR_SCORE="$(printf '%s' "$MATCH" | cut -f2)"
CAND_PREVIEW="$(printf '%s' "$CANDIDATE" | tr '\n' ' ' | cut -c1-400)"

# Build the proposal body with printf (avoids fragile heredoc-in-substitution).
BODY="$(printf '%s\n' \
  "A new rule is about to be encoded that looks like a SPECIFIC INSTANCE of an" \
  "existing principle — consider generalizing instead of adding another case" \
  "(anti-accretion, holistic-thinking L3)." \
  "" \
  "- About-to-encode (candidate): ${CAND_PREVIEW}" \
  "- Closest existing principle: ${NEIGHBOR_TITLE} (keyword overlap ${NEIGHBOR_SCORE})" \
  "" \
  "Options (Captain decides):" \
  "1. COLLAPSE — fold the candidate into ${NEIGHBOR_TITLE} (generalize the principle to cover both; do not add a new case)." \
  "2. KEEP-AS-CASE — the candidate is genuinely distinct; encode it as written." \
  "3. EDIT — restate as a higher-altitude principle that subsumes both." \
  "" \
  "The candidate was still written (the gate never blocks). This is a proposal to" \
  "reconsider it as a principle, not a case.")"

TITLE="Anti-accretion: candidate may be an instance of ${NEIGHBOR_TITLE}"
PID="$(mc_emit_proposal prevent "$TITLE" "$BODY" "fyi-digest")"
[ -n "$PID" ] && echo "$PID"
exit 0
