#!/usr/bin/env bash
# spec049-ceiling.sh — Spec 049 Phase 2a per-task step+token ceiling tracking +
# cap-event-chain. SOURCED by post-tool-use.sh (counter update per tool call) and
# by /self-review + /ship-pr (cap-gate check). Bulk logic lives here so the hook
# wiring is a one-line source+call (minimizes the shared-hook diff).
#
# Sources (Spec 049 v3.1 C1, units corrected d61e729):
#   agentSteps       = (GET cabinet:toolcalls:$OFFICER)            − agentStepBaseline
#   agentTokensTotal = (HSET <date> <role>_input + <role>_output)  − agentTokenBaseline   (TOKENS, not _cost_micro)
#   visualUatCost    = written separately by stagehand-runner (Gate-4 USD)
# Caps + baselines live in <project>/.claude/active-task.json (v2 schema, 15 fields).
#
# Cap-event-chain (Spec 049 §"Per-task token+step ceiling", lines 181-183):
#   ≥80% of ANY cap  → ONE CAP_APPROACH event, payload lists ALL triggered caps + pct
#   100% of ANY cap  → ONE CAP_HIT event; block priority cost > token > step
#                      (cost is irreversible spend; tokens/steps recover on restart)
#
# FAIL-SAFE: no active-task / no baselines (pre-snapshot) / redis down / jq missing
# → silent no-op, return 0. NEVER break an officer's tool flow or gate on infra.

# --- config (match post-tool-use.sh conventions) ---
: "${REDIS_HOST:=redis}"
: "${REDIS_PORT:=6379}"
: "${CABINET_CEILING_EVENT_LOG:=${CABINET_ROOT:-/opt/founders-cabinet}/cabinet/logs/spec049-cap-events.jsonl}"

# Resolve the active-task.json for the current project. Arg 1 wins; else
# <cwd>/.claude/active-task.json (per-project per Spec 049 lifecycle).
_s49_state_path() {
  if [ -n "${1:-}" ]; then echo "$1"; else echo "./.claude/active-task.json"; fi
}

_s49_redis() { redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@" 2>/dev/null; }

# Recompute agentSteps + agentTokensTotal as deltas from the snapshotted baselines
# and write them back. No-op (0) if state/baselines/redis/jq unavailable.
# Usage: spec049_update_counters [active-task-path] [officer]
spec049_update_counters() {
  local state officer date toolcalls inp out cur_steps cur_tokens base_step base_tok tmp
  state="$(_s49_state_path "${1:-}")"
  officer="${2:-${OFFICER_NAME:-${OFFICER:-}}}"
  command -v jq >/dev/null 2>&1 || return 0
  [ -f "$state" ] || return 0
  jq -e . "$state" >/dev/null 2>&1 || return 0
  base_step="$(jq -r '.agentStepBaseline // empty' "$state" 2>/dev/null)"
  base_tok="$(jq -r '.agentTokenBaseline // empty' "$state" 2>/dev/null)"
  # Baselines null/absent ⇒ /pickup-task hasn't snapshotted yet ⇒ nothing to delta.
  [ -n "$base_step" ] && [ -n "$base_tok" ] || return 0
  [ -n "$officer" ] || return 0

  date="$(date -u +%Y-%m-%d)"
  toolcalls="$(_s49_redis GET "cabinet:toolcalls:$officer")"; toolcalls="${toolcalls:-$base_step}"
  inp="$(_s49_redis HGET "cabinet:cost:tokens:daily:$date" "${officer}_input")"; inp="${inp:-0}"
  out="$(_s49_redis HGET "cabinet:cost:tokens:daily:$date" "${officer}_output")"; out="${out:-0}"

  # Integer-guard (redis returns strings; non-numeric ⇒ bail safe).
  case "$toolcalls$inp$out$base_step$base_tok" in *[!0-9]*) return 0;; esac

  cur_steps=$(( toolcalls - base_step )); [ "$cur_steps" -lt 0 ] && cur_steps=0
  cur_tokens=$(( inp + out - base_tok )); [ "$cur_tokens" -lt 0 ] && cur_tokens=0

  tmp="$(mktemp "${state}.s49.XXXXXX")" || return 0
  if jq --argjson s "$cur_steps" --argjson t "$cur_tokens" \
       '.agentSteps=$s | .agentTokensTotal=$t' "$state" > "$tmp" 2>/dev/null; then
    mv "$tmp" "$state"
  else
    rm -f "$tmp"
  fi
  return 0
}

# Evaluate caps against current counters + visualUatCost. Emits at most ONE event
# (CAP_APPROACH at ≥80%, CAP_HIT at 100%) with all triggered caps in the payload.
# Returns: 0 = clear/approach (advisory only); 2 = CAP_HIT (caller blocks).
# Usage: spec049_check_caps [active-task-path]
spec049_check_caps() {
  local state caps hit approach
  state="$(_s49_state_path "${1:-}")"
  command -v jq >/dev/null 2>&1 || return 0
  [ -f "$state" ] || return 0
  jq -e . "$state" >/dev/null 2>&1 || return 0

  # Build the triggered-caps array, ordered cost > token > step (priority, spec
  # line 183). Each cap with a positive ceiling contributes {name,pct}.
  # COST ARM IS DORMANT IN PHASE 2a: visualUatCostCap is set by Phase 3 (Gate-4 /
  # stagehand-runner owns the $5 visual cost cap per AC #10). Until then it's
  # absent → cap 0 → select(.cap>0) drops it, so Phase 2a enforces token+step and
  # the cost arm auto-activates when Phase 3 writes the cap field. Forward-compat
  # by construction (keeps the unified cost>token>step ordering ready, not a bug).
  caps="$(jq -c '
    [ {name:"cost",  cur:(.visualUatCost//0),    cap:(.visualUatCostCap//0)},
      {name:"token", cur:(.agentTokensTotal//0), cap:(.agentTokenCap//0)},
      {name:"step",  cur:(.agentSteps//0),       cap:(.agentStepCap//0)} ]
    | map(select(.cap>0) | . + {pct: ((.cur*100/.cap)|floor)})
  ' "$state" 2>/dev/null)" || return 0
  [ -n "$caps" ] && [ "$caps" != "null" ] || return 0

  hit="$(jq -c '[.[]|select(.pct>=100)]' <<<"$caps")"
  approach="$(jq -c '[.[]|select(.pct>=80)]' <<<"$caps")"

  if [ "$(jq 'length' <<<"$hit")" -gt 0 ]; then
    _s49_emit "CAP_HIT" "$hit"
    return 2
  fi
  if [ "$(jq 'length' <<<"$approach")" -gt 0 ]; then
    _s49_emit "CAP_APPROACH" "$approach"
  fi
  return 0
}

# Emit one structured event to stderr (officer-visible) + append to the jsonl
# audit log. Priority of the FIRST-listed cap drives the block (caps already
# ordered cost>token>step).
_s49_emit() {
  local kind payload ts line
  kind="$1"; payload="$2"
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  line="$(jq -nc --arg k "$kind" --arg ts "$ts" --argjson caps "$payload" \
    '{ts:$ts, event:$k, caps:$caps}' 2>/dev/null)" || return 0
  echo "[$kind] $payload" >&2
  mkdir -p "$(dirname "$CABINET_CEILING_EVENT_LOG")" 2>/dev/null || true
  echo "$line" >> "$CABINET_CEILING_EVENT_LOG" 2>/dev/null || true
}
