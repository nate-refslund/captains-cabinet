#!/usr/bin/env bash
# llm-routing.sh — Spec 051 v6 AC #11(a) model-name routing.
# Sourced by the officer session or calling script to select the per-request
# LLM model name (claude-sonnet-4-6 vs claude-opus-4-7) based on tool-call depth
# and per-officer config in .cabinet/agent-instructions.md → llm_routing.
#
# WHY MODEL-NAME (not headers): Claude Code's ANTHROPIC_CUSTOM_HEADERS is static
# per-session; it cannot vary per-request by runtime state. Model-name is the
# natively per-request routing key the proxy understands — verified against the
# claude-code-guide 2026-05-24 (Spec 051 v6 routing-mechanism correction).
#
# Config read from .cabinet/agent-instructions.md → llm_routing block (YAML-ish
# key:value, one per line). Supported keys:
#   mode: auto | opus-only | sonnet-only   (default: auto)
#   escalation_depth_threshold: <int>      (default: 3)
#   opus_model: <model-name>               (default: claude-opus-4-7)
#   sonnet_model: <model-name>             (default: claude-sonnet-4-6)
#
# Function:
#   llm_routing_select_model <officer> <tool_call_depth>  → prints model name
#
# Fail-safe: any parse/read error → print sonnet default, return 0.
# No hardcoded paths — agent-instructions path resolved via CABINET_ROOT.

: "${CABINET_ROOT:=/opt/founders-cabinet}"
: "${LLM_ROUTING_OPUS_DEFAULT:=claude-opus-4-7}"
: "${LLM_ROUTING_SONNET_DEFAULT:=claude-sonnet-4-6}"

# Internal: parse a key from the llm_routing block of agent-instructions.md.
# Prints the value for <key> or empty string if not found / file absent.
_llm_routing_parse_key() {
  local file="$1" key="$2" in_block=0 line k v
  [ -f "$file" ] || return 0
  while IFS= read -r line; do
    # Detect start of llm_routing block (YAML mapping key, possibly indented)
    case "$line" in
      *"llm_routing:"*) in_block=1; continue ;;
    esac
    [ "$in_block" = "0" ] && continue
    # Exit block on blank line or next top-level key (no leading spaces)
    case "$line" in
      ''|$'\r') in_block=0; continue ;;
      [a-zA-Z]*) in_block=0; continue ;;
    esac
    # Parse "  key: value" (leading spaces OK)
    line="${line#"${line%%[![:space:]]*}"}"   # ltrim
    k="${line%%:*}"
    k="${k%"${k##*[![:space:]]}"}"            # rtrim key
    v="${line#*:}"
    v="${v#"${v%%[![:space:]]*}"}"            # ltrim value
    v="${v%"${v##*[![:space:]]}"}"            # rtrim value
    if [ "$k" = "$key" ]; then
      printf '%s' "$v"
      return 0
    fi
  done < "$file"
  return 0
}

# Print the model name to use for the given officer + tool_call_depth.
# Usage: llm_routing_select_model <officer> <tool_call_depth>
llm_routing_select_model() {
  local officer="${1:-}" depth="${2:-0}"
  local instructions_file mode threshold opus sonnet

  # Resolve agent-instructions.md — officer-local path under cabinet root
  instructions_file="${CABINET_ROOT}/.cabinet/agent-instructions.md"

  # Framework defaults (Spec 051 v6 AC #11a)
  mode="auto"
  threshold=3
  opus="$LLM_ROUTING_OPUS_DEFAULT"
  sonnet="$LLM_ROUTING_SONNET_DEFAULT"

  # Override from agent-instructions.md if present
  if [ -f "$instructions_file" ]; then
    local _mode _threshold _opus _sonnet
    _mode="$(_llm_routing_parse_key "$instructions_file" "mode")"
    _threshold="$(_llm_routing_parse_key "$instructions_file" "escalation_depth_threshold")"
    _opus="$(_llm_routing_parse_key "$instructions_file" "opus_model")"
    _sonnet="$(_llm_routing_parse_key "$instructions_file" "sonnet_model")"
    [ -n "$_mode" ]      && mode="$_mode"
    [ -n "$_threshold" ] && threshold="$_threshold"
    [ -n "$_opus" ]      && opus="$_opus"
    [ -n "$_sonnet" ]    && sonnet="$_sonnet"
  fi

  # Sanitise threshold to a positive integer; fall back to 3 on garbage
  case "$threshold" in
    ''|*[!0-9]*) threshold=3 ;;
  esac

  # Sanitise depth to a non-negative integer
  case "$depth" in
    ''|*[!0-9]*) depth=0 ;;
  esac

  case "$mode" in
    opus-only)
      printf '%s\n' "$opus"
      ;;
    sonnet-only)
      printf '%s\n' "$sonnet"
      ;;
    auto|*)
      # auto: escalate to opus when depth >= threshold
      if [ "$depth" -ge "$threshold" ]; then
        printf '%s\n' "$opus"
      else
        printf '%s\n' "$sonnet"
      fi
      ;;
  esac
  return 0
}
