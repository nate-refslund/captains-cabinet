#!/bin/bash
# post-reply-audit.sh — Spec 052 Phase 5: emit a customer GDPR audit entry (officer-action:
# dm_sent) for outgoing Telegram replies. Triggered by the PostToolUse "reply" matcher.
#
# Commercial cabinets ONLY — audit-emit.sh self-gates on the emits_customer_audit_events
# capability, so non-commercial cabinets no-op. PII-MINIMIZED: emits ONLY the message LENGTH
# + attachment_count — NEVER the DM text (Spec 052 AC #3). Fail-safe + non-blocking (the lib
# backgrounds the POST); this hook never blocks the reply path.

HOOK_INPUT=$(cat)
export OFFICER_NAME="${OFFICER_NAME:-unknown}"
_AUDIT_LIB="${CABINET_ROOT:-/opt/founders-cabinet}/cabinet/scripts/lib/audit-emit.sh"
[ -f "$_AUDIT_LIB" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

# Reply text — used ONLY for its length; the text itself is never emitted.
REPLY_TEXT=$(printf '%s' "$HOOK_INPUT" | jq -r '
  .tool_input |
  if type=="string" then . elif .text then .text elif .content then .content
  elif .message then .message elif .body then .body else "" end' 2>/dev/null)
LEN=${#REPLY_TEXT}
ATTACH=$(printf '%s' "$HOOK_INPUT" | jq -r \
  '(.tool_input.attachments // .tool_input.files // []) | if type=="array" then length else 0 end' 2>/dev/null)
case "$ATTACH" in ''|*[!0-9]*) ATTACH=0 ;; esac

# shellcheck source=/dev/null
. "$_AUDIT_LIB" 2>/dev/null || exit 0
MD="$(jq -nc --argjson len "${LEN:-0}" --argjson att "$ATTACH" \
    '{length:$len, attachment_count:$att}' 2>/dev/null || echo '{}')"
audit_emit_event officer dm_sent telegram_dm "" "$MD" 2>/dev/null || true
exit 0
