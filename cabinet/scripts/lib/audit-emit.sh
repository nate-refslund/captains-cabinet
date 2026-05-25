#!/usr/bin/env bash
# cabinet/scripts/lib/audit-emit.sh — Spec 052 Phase 5 officer-side audit-event emitter.
#
# SOURCE this (do not execute). Provides audit_emit_event — emits an officer-action /
# cabinet-event audit entry to the FW-097 audit-server (POST /proxy/audit/log), so the
# customer GDPR audit trail captures officer actions (streams 2+3), not just LLM requests.
#
# DESIGN — every gate is FAIL-SAFE and the emit is NON-BLOCKING: this is sourced by
# post-tool-use.sh which runs on EVERY tool call, so it must NEVER break or slow the hook.
#   Gate 1 (capability): no-op unless this officer has emits_customer_audit_events
#                        (non-commercial cabinets have no grant -> silent). Mirrors post-tool-use.sh.
#   Gate 2 (config):     no-op unless AUDIT_LOG_ENDPOINT + AUDIT_API_KEY + cabinet slug are set
#                        (absent -> mock-now / live-at-deploy; no emission until the VPS exists).
#   Gate 3 (capture):    if AUDIT_EMIT_CAPTURE is set, append the payload to that file instead of
#                        POSTing (lets the harness assert payload shape + PII without a live server).
#   PII-minimize:        client-side mirror of proxy/audit-server/validator.py — strip forbidden
#                        Telegram-DM full-text keys + attachment-content keys, cap metadata at 4096B.
#                        The server validator is the backstop; this keeps us from ever sending PII.
#   POST:                fire-and-forget background curl with a short timeout, output discarded,
#                        disowned (FW-077 redirect+disown) -> never blocks the hot path, never fails it.
#
# Wire contract (proxy/audit-server/app.py AuditEntryRequest): the server synthesizes
# entry_id + integrity (hash-chain) + ts; the client sends cabinet_id/stream/event_type/actor/subject.
#
# NOTE: a sourced lib must not `set -e`/`set -u` on the caller; all vars are ${x:-} guarded.

# Forbidden metadata keys (mirror validator.py): DM full-text + attachment content. NEVER emitted.
_AUDIT_FORBIDDEN_KEYS='text,content,body,message,full_text,data,attachment_data,file_content'
_AUDIT_MAX_METADATA_BYTES=4096

# audit_emit_event <stream> <event_type> <subject_type> <target> <metadata_json>
#   stream:        "officer" | "cabinet"
#   event_type:    e.g. "tool_call" | "dm_sent" | "dm_received" | "key_rotation" | "breach_notification"
#   subject_type:  e.g. "tool_call" | "telegram_dm" | "cabinet_event"
#   target:        short subject target (tool name / event name); "" to omit. NO argv content / NO PII.
#   metadata_json: a JSON object string, already minimized by the caller; "" -> {}.
# Always returns 0 (fail-safe). Emits in the background.
audit_emit_event() {
    local stream="${1:-}" event_type="${2:-}" subject_type="${3:-}" target="${4:-}" metadata="${5:-}"
    [ -n "$stream" ] && [ -n "$event_type" ] || return 0
    command -v jq >/dev/null 2>&1 || return 0   # no jq -> cannot build safe JSON -> no-op

    local officer="${OFFICER_NAME:-${OFFICER:-unknown}}"
    local conf="${AUDIT_CAPABILITIES_FILE:-${CABINET_ROOT:-/opt/founders-cabinet}/cabinet/officer-capabilities.conf}"

    # ── Gate 1: capability (non-commercial / ungranted officer -> silent no-op) ──
    grep -q "^${officer}:emits_customer_audit_events$" "$conf" 2>/dev/null || return 0

    local capture="${AUDIT_EMIT_CAPTURE:-}"
    local endpoint="${AUDIT_LOG_ENDPOINT:-}" key="${AUDIT_API_KEY:-}"
    local cabinet="${CABINET_SLUG:-${CABINET_ID:-}}"

    # ── Gate 2: config (absent -> no-op; capture-mode tolerates missing endpoint/key/slug) ──
    if [ -n "$capture" ]; then
        [ -n "$cabinet" ] || cabinet="test-cabinet"
    else
        [ -n "$endpoint" ] && [ -n "$key" ] && [ -n "$cabinet" ] || return 0
    fi

    # ── PII-minimize the metadata (defense-in-depth; validator.py is the server backstop) ──
    # NOTE: default in a SEPARATE statement — do NOT use ${metadata:-{}} (bash closes ${...} at the
    # first }, leaking a literal trailing } -> invalid JSON -> jq fails -> the || clobbers md to {}).
    [ -n "$metadata" ] || metadata='{}'
    local md
    md="$(printf '%s' "$metadata" | jq -c '.' 2>/dev/null)" || md='{}'
    [ -n "$md" ] || md='{}'
    # strip forbidden keys (DM full-text + attachment content) regardless of caller — explicit del()
    # (a dynamic delpaths was buggy: it wiped ALL keys; explicit del leaves non-forbidden keys intact).
    md="$(printf '%s' "$md" | jq -c \
            'del(.text, .content, .body, .message, .full_text, .data, .attachment_data, .file_content)' \
            2>/dev/null)" || md='{}'
    # cap size -> replace with a marker rather than emit an oversized (server-rejected) payload
    if [ "$(printf '%s' "$md" | wc -c)" -gt "$_AUDIT_MAX_METADATA_BYTES" ]; then
        md='{"_truncated":true}'
    fi

    # ── Build the AuditEntryRequest payload (server synthesizes entry_id/integrity/ts) ──
    local payload
    payload="$(jq -nc \
        --arg cab "$cabinet" --arg st "$stream" --arg et "$event_type" \
        --arg off "$officer" --arg sty "$subject_type" --arg tgt "$target" \
        --argjson md "$md" \
        '{cabinet_id:$cab, stream:$st, event_type:$et,
          actor:{officer:$off, captain:false},
          subject:({type:$sty, metadata:$md} + (if $tgt=="" then {} else {target:$tgt} end))}' \
        2>/dev/null)" || return 0
    [ -n "$payload" ] || return 0

    # ── Gate 3: capture-mode (harness) — write payload, no POST ──
    if [ -n "$capture" ]; then
        printf '%s\n' "$payload" >> "$capture" 2>/dev/null || true
        return 0
    fi

    # ── Fail-safe NON-BLOCKING POST (background + timeout + disowned; never blocks/breaks the hook) ──
    ( curl -sS --max-time "${AUDIT_EMIT_TIMEOUT:-2}" -o /dev/null \
        -X POST "$endpoint" \
        -H "Authorization: Bearer ${key}" \
        -H "Content-Type: application/json" \
        -d "$payload" >/dev/null 2>&1 ) >/dev/null 2>&1 &
    disown 2>/dev/null || true
    return 0
}
