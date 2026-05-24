#!/usr/bin/env bash
# model-pricing.sh — Spec 049 AC #18 accessors over model-pricing.json.
# Sourced by the Gate-4 stagehand-runner (shell side) + cabinet/tests/test-spec-049.sh.
# The single source of truth is model-pricing.json (committed, dated, version-pinned);
# this lib is the read/compute interface. No live pricing lookup (M4) — drift is caught
# only by model_pricing_staleness_check (the AC #18 staleness assertion).
#
# Path override via MODEL_PRICING_JSON; default resolves through CABINET_ROOT (no
# hardcoded framework path — ports to Mac-native, per the Spec 049 build-wide principle).
#
# Functions:
#   model_pricing_staleness_check          → 0 fresh; 1 stale (+ WARN to stderr)
#   model_pricing_rate  <model> <input|output>                       → USD per Mtoken
#   model_pricing_cost  <model> <in> <out> [cache_w] [cache_r] [5m|1h] → USD for one call

: "${MODEL_PRICING_JSON:=${CABINET_ROOT:-/opt/founders-cabinet}/cabinet/scripts/lib/model-pricing.json}"

# YYYY-MM-DD → epoch seconds. GNU date first, then BSD/macOS form (Mac-native arc).
_mp_epoch() {
  date -u -d "$1" +%s 2>/dev/null || date -u -j -f "%Y-%m-%d" "$1" +%s 2>/dev/null
}

# Resolve a model string to a table key: exact match, else the LONGEST prefix match
# (so a dated id like claude-opus-4-7-20260101 maps to the claude-opus-4-7 entry).
_mp_key() {
  local model="$1" keys k best=""
  command -v jq >/dev/null 2>&1 || return 1
  [ -f "$MODEL_PRICING_JSON" ] || return 1
  if jq -e --arg m "$model" '.models[$m]' "$MODEL_PRICING_JSON" >/dev/null 2>&1; then
    echo "$model"; return 0
  fi
  keys="$(jq -r '.models | keys[]' "$MODEL_PRICING_JSON" 2>/dev/null)" || return 1
  for k in $keys; do
    case "$model" in
      "$k"*) [ "${#k}" -gt "${#best}" ] && best="$k" ;;
    esac
  done
  [ -n "$best" ] && { echo "$best"; return 0; }
  return 1
}

# WARN (return 1) if the pricing table is older than staleness_warn_days. Fail-open
# (return 0) if jq/file/date unavailable — staleness is advisory, never a hard gate.
model_pricing_staleness_check() {
  local as_of warn_days then now age
  command -v jq >/dev/null 2>&1 || return 0
  [ -f "$MODEL_PRICING_JSON" ] || return 0
  as_of="$(jq -r '.pricing_as_of // empty' "$MODEL_PRICING_JSON" 2>/dev/null)"
  warn_days="$(jq -r '.staleness_warn_days // 30' "$MODEL_PRICING_JSON" 2>/dev/null)"
  [ -n "$as_of" ] || return 0
  then="$(_mp_epoch "$as_of")" || return 0
  [ -n "$then" ] || return 0
  now="$(date -u +%s)"
  age=$(( (now - then) / 86400 ))
  if [ "$age" -gt "$warn_days" ]; then
    echo "WARN: model-pricing.json pricing_as_of=$as_of is ${age}d old (>${warn_days}d) — refresh rates against console.anthropic.com billing + bump pricing_as_of (Spec 049 AC #18)." >&2
    return 1
  fi
  return 0
}

# Print the USD-per-Mtoken rate for a model's input|output field.
model_pricing_rate() {
  local key; key="$(_mp_key "$1")" || return 1
  jq -er --arg k "$key" --arg f "$2" '.models[$k][$f]' "$MODEL_PRICING_JSON" 2>/dev/null
}

# Print the USD cost of ONE call's usage. Args: model in_tok out_tok [cache_write_tok]
# [cache_read_tok] [5m|1h]. cache_* default 0, tier default 5m. jq does the float math.
model_pricing_cost() {
  local key in_tok out_tok cw_tok cr_tok tier
  key="$(_mp_key "$1")" || return 1
  in_tok="${2:-0}"; out_tok="${3:-0}"; cw_tok="${4:-0}"; cr_tok="${5:-0}"; tier="${6:-5m}"
  jq -er --arg k "$key" --argjson in "$in_tok" --argjson out "$out_tok" \
         --argjson cw "$cw_tok" --argjson cr "$cr_tok" --arg tier "$tier" '
    .models[$k] as $m
    | (if $tier == "1h" then .cache_multipliers.write_1h else .cache_multipliers.write_5m end) as $cwm
    | .cache_multipliers.read as $crm
    | ( ($in * $m.input) + ($out * $m.output) + ($cw * $m.input * $cwm) + ($cr * $m.input * $crm) ) / 1000000
  ' "$MODEL_PRICING_JSON" 2>/dev/null
}
