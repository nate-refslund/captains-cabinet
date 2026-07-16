#!/bin/bash
# cabinet/scripts/meta-cognition/lib.sh — shared selectors + the ONE gated sink
# for the self-improving meta-cognition system (framework/docs/meta-cognition-direction-2026-06-25.md).
#
# This is sourced (not executed) by every layer of the system:
#   Layer 1 (PREVENT)  — encode-time anti-accretion gate
#   Layer 2 (HARVEST)  — principle-harvester evolved skill
#   Layer 2 (DETECT)   — anomaly-seeking in the 48h retro
#   Layer 3 (BACKSTOP) — retro accretion-counter check
#   cross-cutting      — counterfactual-replay escalation
#
# Two responsibilities, both load-bearing per the design's cross-cutting rule
# ("every generator is paired with a hard selector"):
#
#   1. mc_is_leave_as_is <text>
#      The hard SELECTOR for "concrete memories/facts EXEMPT". Returns 0 (true,
#      LEAVE AS IS — do NOT generalize/collapse) when the candidate text matches
#      the LEAVE-AS-IS allow-list: safety-boundaries, authority-matrix,
#      CAPTAIN_EMAILS, board/model IDs, SECRET_PATTERNS, and concrete identifiers
#      (URLs, tokens, IDs, dates, paths). Returns 1 (false) for genuine
#      behavioral/governance/execution rules that ARE candidates for
#      collapse-to-principle.
#
#   2. mc_emit_proposal <layer> <title> <body>
#      The ONE sink. Appends a proposal-only, per-item Captain-gated entry to
#      shared/interfaces/meta-cognition-proposals.md. NOTHING here applies a
#      change — every entry is a PROPOSAL the CoS surfaces into the next briefing
#      decision-queue (the "stale proposals auto-expire into the briefing"
#      pattern, same as courses-of-action). The ledger is gitignored runtime
#      state (shared/interfaces/**/*.md).
#
# Secrets: NONE. No network. Reads/writes local files + (optionally) a Redis
# counter via redis-cli. Safe to source from any scheduled context.
#
# Reversibility: rm this file + the two consumers stop emitting. No DB, no
# schema, no migration.

# Resolve REPO_ROOT for both Docker (/opt/founders-cabinet) and Mac-native.
if [ -z "${MC_REPO_ROOT:-}" ]; then
  if [ -n "${REPO_ROOT:-}" ]; then
    MC_REPO_ROOT="$REPO_ROOT"
  elif [ -d "/opt/founders-cabinet" ]; then
    MC_REPO_ROOT="/opt/founders-cabinet"
  else
    MC_REPO_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." 2>/dev/null && pwd)}"
  fi
fi

MC_PROPOSALS_FILE="${MC_PROPOSALS_FILE:-$MC_REPO_ROOT/shared/interfaces/meta-cognition-proposals.md}"
MC_REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
MC_REDIS_PORT="${REDIS_PORT:-6379}"

# ── The hard LEAVE-AS-IS allow-list ──────────────────────────────────────────
# A candidate rule/pattern/fact is EXEMPT from collapse-to-principle (return 0 =
# "leave as is") when it is a concrete fact, identifier, or a safety/authority
# germline reference — never a generalizable behavior. This is the selector that
# stops the harvester from collapsing genuine facts (board IDs, model IDs,
# CAPTAIN_EMAILS, secrets) into a lossy "principle". Case-insensitive substring +
# regex match. Conservative by design: when in doubt, LEAVE AS IS.
#
# Usage: mc_is_leave_as_is "<candidate text>"  → exit 0 (leave as is) / 1 (eligible)
mc_is_leave_as_is() {
  local text="$1"
  [ -z "$text" ] && return 0   # empty → nothing to generalize; leave as is

  python3 - "$text" <<'PYEOF'
import sys, re

text = sys.argv[1]
low = text.lower()

# 1) Named germline / facts surfaces that must NEVER be collapsed.
#    These are the design's explicit LEAVE-AS-IS allow-list.
NAMED = [
    "safety-boundaries", "safety_boundaries", "safety boundaries",
    "authority-matrix", "authority_matrix", "authority matrix",
    "captain_emails", "captain emails",
    "secret_patterns", "secret pattern",
    "killswitch", "kill switch",
    ".claude/rules", "framework/policies", "framework/authority",
    "germline",
]
for n in NAMED:
    if n in low:
        print("leave")
        sys.exit(0)

# 2) Concrete identifiers — a rule that hinges on a specific ID/URL/token/date/
#    path/email/secret is a FACT, not a behavior. Collapsing it loses the fact.
PATTERNS = [
    r"\b\d{8,}\b",                       # long numeric IDs (Monday board/pulse ids)
    r"\bboard\s*[#:]?\s*\d+",            # "board 12345"
    r"\bpulse[s]?\s*[#:/]?\s*\d+",       # monday pulse ids
    r"claude-[a-z0-9.\-\[\]]+",          # model ids (claude-opus-4-8[1m], claude-fable-5)
    r"\b(opus|sonnet|haiku|fable|mythos)[ \-]?\d",  # model lineage tokens
    r"https?://",                        # any URL
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",  # email address
    r"\b[A-Za-z0-9_\-]*(?:token|secret|api[_\-]?key|password|bearer)[A-Za-z0-9_\-]*\b",  # secret-ish
    r"\b\d{4}-\d{2}-\d{2}\b",            # a hard date (concrete event, not a rule)
    r"\b(sk|pk|ghp|gho|xox[bp])[_\-][A-Za-z0-9]{8,}\b",  # secret token shapes
    r"/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-/]+",  # an absolute-ish path
    r"\bproject\s+[\"']?[a-z]+-[a-z]+-\d+",  # neon project ids (restless-king-62586913)
    r"\bbr-[a-z]+-[a-z]+-[a-z0-9]+",     # neon branch ids
    r"\bID[s]?\b\s*[:=]?\s*\d",          # "ID: 12345"
]
for pat in PATTERNS:
    if re.search(pat, text, re.IGNORECASE):
        print("leave")
        sys.exit(0)

# Otherwise: a genuine behavioral/governance/execution rule → ELIGIBLE for
# collapse-to-principle. The generator still proposes (never applies); the
# Captain still gates per-item.
print("eligible")
sys.exit(1)
PYEOF
}

# ── The ONE gated sink ───────────────────────────────────────────────────────
# Append a proposal-only, per-item Captain-gated entry to the meta-cognition
# proposal ledger. The CoS retro surfaces ledger entries into the next briefing
# decision-queue. NOTHING is applied here.
#
# Usage: mc_emit_proposal <layer> <title> <body> [urgency_tier]
#   layer        one of: prevent | harvest | detect | backstop | counterfactual
#   title        one-line proposal title
#   body         the proposal detail (multi-line OK; pass as a single arg)
#   urgency_tier batch-into-next-briefing (default) | ping-now | fyi-digest
mc_emit_proposal() {
  local layer="$1" title="$2" body="$3" tier="${4:-batch-into-next-briefing}"
  [ -z "$layer" ] && { echo "mc_emit_proposal: layer required" >&2; return 2; }
  [ -z "$title" ] && { echo "mc_emit_proposal: title required" >&2; return 2; }

  local now_iso
  now_iso="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  local pid
  pid="MC-$(printf '%s' "$layer|$title" | shasum 2>/dev/null | awk '{print substr($1,1,8)}')"
  [ -z "$pid" ] && pid="MC-$(date +%s)"

  mkdir -p "$(dirname "$MC_PROPOSALS_FILE")" 2>/dev/null

  # Idempotency: if an OPEN entry with this id already exists, do not duplicate.
  if [ -f "$MC_PROPOSALS_FILE" ] && grep -q "id: $pid .*status: open" "$MC_PROPOSALS_FILE" 2>/dev/null; then
    echo "$pid (already open — not duplicated)"
    return 0
  fi

  {
    printf '\n---\n\n'
    printf '### %s\n\n' "$title"
    printf -- '- id: %s | layer: %s | added: %s | urgency: %s | status: open\n' \
      "$pid" "$layer" "$now_iso" "$tier"
    printf -- '- **Proposal (per-item Captain-gated — apply | edit | skip):**\n\n'
    printf '%s\n' "$body" | sed 's/^/  /'
    printf '\n'
  } >> "$MC_PROPOSALS_FILE" 2>/dev/null

  echo "$pid"
  return 0
}

# Mark a proposal resolved (the Captain decided, or the CoS folded it into a
# briefing). Never hand-edit the status field. Usage: mc_resolve_proposal <id> [status]
mc_resolve_proposal() {
  local pid="$1" new_status="${2:-decided}"
  [ -z "$pid" ] && { echo "mc_resolve_proposal: id required" >&2; return 2; }
  [ -f "$MC_PROPOSALS_FILE" ] || return 0
  local tmp
  tmp="$(mktemp "${TMPDIR:-/tmp}/mc-proposals.XXXXXX")" || return 1
  sed "s/\(id: $pid .*status:\) open/\1 $new_status/" "$MC_PROPOSALS_FILE" > "$tmp" && mv "$tmp" "$MC_PROPOSALS_FILE"
  return 0
}

# ── Accretion counter (the content trigger for Layer 2 HARVEST) ──────────────
# A Redis counter incremented whenever the patterns ledger / CLAUDE.md / rules
# set grows. The harvester fires when (counter - last_harvest_mark) >= threshold.
# Best-effort: a Redis failure degrades to "never auto-fires", and the retro
# (Layer 3) is the floor that catches it.
MC_ACCRETION_KEY="${MC_ACCRETION_KEY:-cabinet:meta:accretion-count}"
MC_ACCRETION_MARK_KEY="${MC_ACCRETION_MARK_KEY:-cabinet:meta:accretion-mark-at-last-harvest}"
MC_ACCRETION_THRESHOLD="${MC_ACCRETION_THRESHOLD:-5}"

# Increment the accretion counter by N (default 1). Echoes the new value.
mc_accretion_incr() {
  local by="${1:-1}"
  command -v redis-cli >/dev/null 2>&1 || { echo 0; return 0; }
  redis-cli -h "$MC_REDIS_HOST" -p "$MC_REDIS_PORT" INCRBY "$MC_ACCRETION_KEY" "$by" 2>/dev/null || echo 0
}

# Echo how much accretion has happened since the last harvest mark (>= 0).
mc_accretion_since_harvest() {
  command -v redis-cli >/dev/null 2>&1 || { echo 0; return 0; }
  local cur mark
  cur="$(redis-cli -h "$MC_REDIS_HOST" -p "$MC_REDIS_PORT" GET "$MC_ACCRETION_KEY" 2>/dev/null)"
  mark="$(redis-cli -h "$MC_REDIS_HOST" -p "$MC_REDIS_PORT" GET "$MC_ACCRETION_MARK_KEY" 2>/dev/null)"
  cur="${cur:-0}"; mark="${mark:-0}"
  echo $(( cur - mark ))
}

# Echo 1 if the harvest threshold has been crossed since the last harvest, else 0.
mc_accretion_threshold_crossed() {
  local since
  since="$(mc_accretion_since_harvest)"
  if [ "${since:-0}" -ge "${MC_ACCRETION_THRESHOLD}" ] 2>/dev/null; then echo 1; else echo 0; fi
}

# Stamp "last harvest happened now" — sets the mark to the current counter so the
# next harvest fires only on NEW accretion. Call this after a harvest pass.
mc_accretion_mark_harvest() {
  command -v redis-cli >/dev/null 2>&1 || return 0
  local cur
  cur="$(redis-cli -h "$MC_REDIS_HOST" -p "$MC_REDIS_PORT" GET "$MC_ACCRETION_KEY" 2>/dev/null)"
  redis-cli -h "$MC_REDIS_HOST" -p "$MC_REDIS_PORT" SET "$MC_ACCRETION_MARK_KEY" "${cur:-0}" >/dev/null 2>&1 || true
}
