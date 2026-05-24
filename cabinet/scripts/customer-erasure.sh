#!/usr/bin/env bash
# cabinet/scripts/customer-erasure.sh — GDPR Article 17 right-to-erasure runbook
#
# Implements Spec 055 AC#6 — the 8-step erasure runbook for a customer cabinet.
# Framework: FW-100 (GDPR right-to-erasure substrate).
#
# USAGE:
#   customer-erasure.sh <cabinet_id> [--dry-run] [--confirm]
#
# BEHAVIOUR (convention):
#   - Without --confirm and without --dry-run: SAFE MODE — prints the plan,
#     does not mutate any data.  Exits 0.
#   - --dry-run: Same as safe mode — prints the plan and exits 0 without mutating.
#     Explicit alias so callers can document intent clearly.
#   - --confirm: Execute all mutating steps (pseudonymization, receipt write,
#     SLA ticket creation/completion, audit append).  Exits 0 on success, 1 on error.
#
# ENV (all overridable for hermetic testing):
#   LITELLM_AUDIT_LOG_ROOT     — SSOT audit log root (default: /opt/founders-cabinet/proxy/logs)
#   CABINET_ERASURE_RECEIPT_DIR — where receipts are written (default: /opt/founders-cabinet/proxy/logs/erasure)
#   CABINET_ERASURE_NO_CHATTR  — if set, SKIP all chattr calls (test / no-root env)
#   CABINET_HOOK_TEST_MODE     — if 1, suppress real notify/network; passed to sla-tracker
#
# DESIGN NOTES:
#   - Library Compliance Space filing (Step 1) is a MANUAL OFFICER STEP.
#     No bash→Library MCP path exists in Phase-1 (CTO #2 / Spec 055 §CTO-#2).
#   - Sub-processor cascade (Step 4) is an honest MANUAL/AUTOMATED split per CTO #3.
#     Automated only where API + key present; no-op-with-warning otherwise.
#   - Account profile / DB (Step 5) is an honest stub: wires to FW-099/FW-101 which
#     are not yet built. Documented and logged; does not fail the run.
#   - Erasure receipt (Step 7) is written unsigned (Phase-1); signing = Phase-2.
#
# IMPORTANT: message strings passed to notify-officer.sh / sla-tracker must use
# plain variable expansion only — NO backticks, NO $(...) — the trigger system
# shell-evaluates message text and backticks/command-subst corrupt it.

set -euo pipefail

CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
AUDIT_SERVER="${CABINET_ROOT}/proxy/audit-server"
AUDIT_LOG_ROOT="${LITELLM_AUDIT_LOG_ROOT:-${CABINET_ROOT}/proxy/logs}"
RECEIPT_DIR="${CABINET_ERASURE_RECEIPT_DIR:-${AUDIT_LOG_ROOT}/erasure}"
TEST_MODE="${CABINET_HOOK_TEST_MODE:-0}"
SLA_TRACKER="${CABINET_ROOT}/cabinet/scripts/sla-tracker.sh"
NOTIFY_SCRIPT="${CABINET_ROOT}/cabinet/scripts/notify-officer.sh"

# ── Parse args ────────────────────────────────────────────────────────────────

CABINET_ID=""
DRY_RUN=0
CONFIRM=0

for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=1 ;;
        --confirm)  CONFIRM=1 ;;
        --*)        echo "WARNING: unknown flag '$arg' ignored" >&2 ;;
        *)          CABINET_ID="$arg" ;;
    esac
done

if [ -z "$CABINET_ID" ]; then
    echo "Usage: customer-erasure.sh <cabinet_id> [--dry-run] [--confirm]" >&2
    exit 1
fi

# SECURITY (Opus review BUG-1/4/5): cabinet_id is interpolated into file paths,
# into three python3 -c invocations, and into notify-officer message text (which
# the trigger system later shell-evaluates). Validate it as a strict slug BEFORE
# any use — a charset-restricted slug cannot break out of a quoted python literal,
# carry shell metacharacters / command-substitution, or contain path-traversal.
# Same slug convention as triggers.sh / start-officer.sh. Reject anything else.
if ! [[ "$CABINET_ID" =~ ^[a-z0-9][a-z0-9-]{0,63}$ ]]; then
    echo "ERROR: invalid cabinet_id '$CABINET_ID' — must be a lowercase alphanumeric/hyphen slug (1-64 chars, matching ^[a-z0-9][a-z0-9-]{0,63})." >&2
    exit 1
fi

# Dry-run always wins over --confirm
if [ "$DRY_RUN" -eq 1 ]; then
    CONFIRM=0
fi

MUTATE=0
if [ "$CONFIRM" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
    MUTATE=1
fi

# Overall exit code — flipped to 1 by a failed/unverified erasure (Opus review BUG-2).
EXIT_CODE=0

SSOT="${AUDIT_LOG_ROOT}/audit/${CABINET_ID}.jsonl"
REQUESTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ── Logging helpers ───────────────────────────────────────────────────────────

log()  { echo "[erasure] $*"; }
info() { echo "[erasure] INFO:    $*"; }
warn() { echo "[erasure] WARNING: $*" >&2; }
step() { echo; echo "══════ Step $* ══════"; }

# BUG-3 (Opus review): re-apply the append-only flag on ANY exit so a
# mid-pseudonymization failure under `set -euo pipefail` cannot leave the audit
# log permanently mutable (the chattr -a / +a pair straddles the python call).
_restore_chattr() {
    if command -v chattr >/dev/null 2>&1 && [ -z "${CABINET_ERASURE_NO_CHATTR:-}" ] && [ -f "${SSOT}" ]; then
        chattr +a "${SSOT}" 2>/dev/null || true
    fi
}

# ── Plan header ───────────────────────────────────────────────────────────────

echo
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  GDPR Article 17 Erasure Runbook — Spec 055 AC#6 / FW-100  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "  Cabinet ID   : ${CABINET_ID}"
echo "  SSOT path    : ${SSOT}"
echo "  Receipt dir  : ${RECEIPT_DIR}"
echo "  Requested at : ${REQUESTED_AT}"
if [ "$MUTATE" -eq 1 ]; then
    echo "  Mode         : EXECUTE (--confirm)"
else
    echo "  Mode         : SAFE/DRY-RUN (no mutations — pass --confirm to execute)"
fi
echo

# ── Step 1: Library Compliance Space record ───────────────────────────────────

step "1 — Erasure record (Library Compliance Space)"
log "Create canonical erasure record payload:"
log "  cabinet_id    : ${CABINET_ID}"
log "  requested_at  : ${REQUESTED_AT}"
log "  request_type  : erasure"
log "  article       : GDPR Article 17"
echo
echo "  ┌─────────────────────────────────────────────────────────────────────┐"
echo "  │  MANUAL OFFICER STEP (CTO #2 / Spec 055 §CTO-#2):                  │"
echo "  │  File this erasure record to the Library Compliance Space using     │"
echo "  │  the MCP tool: library_create_record (space: Compliance).           │"
echo "  │  This is the canonical SSOT per A11 v5. Phase-1 has no bash→MCP    │"
echo "  │  Library path — filing must be performed by a Cabinet officer.      │"
echo "  └─────────────────────────────────────────────────────────────────────┘"

# ── Step 2: Identity validation ───────────────────────────────────────────────

step "2 — Identity validation"
log "Phase-1 trusts cabinet_id='${CABINET_ID}' (validated upstream by the"
log "refslund.ai/erasure web form + FW-101 backend authentication layer)."
log "No additional local identity check performed in this runbook."

# ── Step 3: SLA ticket creation ───────────────────────────────────────────────

step "3 — 30-day SLA ticket (GDPR Article 17 / Article 12(3))"

TICKET_ID=""
SLA_DUE_AT=""

if [ "$MUTATE" -eq 1 ]; then
    SLA_OUTPUT="$(CABINET_HOOK_TEST_MODE="${TEST_MODE}" bash "${SLA_TRACKER}" create erasure "${CABINET_ID}")"
    TICKET_ID="$(echo "${SLA_OUTPUT}" | head -1)"
    SLA_DUE_AT="$(echo "${SLA_OUTPUT}" | tail -1)"
    log "Created SLA ticket: ${TICKET_ID}"
    log "Due at: ${SLA_DUE_AT}"
else
    TICKET_ID="erasure-${CABINET_ID}-[DRY-RUN]"
    SLA_DUE_AT="[DRY-RUN: $(date -u -d "${REQUESTED_AT} +30 days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo 'requested_at+30d')]"
    log "(DRY-RUN) Would create SLA ticket via: sla-tracker.sh create erasure ${CABINET_ID}"
    log "  Projected ticket_id : ${TICKET_ID}"
    log "  Projected due_at    : ${SLA_DUE_AT}"
fi

# ── Step 4: Sub-processor cascade ────────────────────────────────────────────

step "4 — Sub-processor erasure cascade"

echo
echo "  MANUAL/AUTOMATED SPLIT (CTO #3 — do not over-promise):"
echo
echo "  [NO-OP]  Anthropic: Cabinet stores NO prompts or completions on the proxy"
echo "           side (proxy emits token counts + metadata only). Nothing to erase"
echo "           downstream with Anthropic. No action required."
echo
echo "  [MANUAL] Stripe: customer billing data is under legal hold (Bogføringsloven"
echo "           §10 5y / Skatteforvaltningsloven §47 10y). CANNOT delete."
echo "           Phase-1: FW-099 (Stripe) is NOT yet built. CoS officer must"
echo "           manually PII-anonymize the Stripe customer record per the DPA"
echo "           carve-out. Warn: no Stripe creds available in this runbook."
echo
echo "  [AUTOMATED/MANUAL] ElevenLabs: voice messages have a 30-day TTL already."
echo "           Force-delete attempted if ELEVENLABS_API_KEY is available."
echo

# ElevenLabs: attempt automated delete if key present
ELEVENLABS_STATUS="no-op (30-day TTL covers retention; API key not present)"
if [ -n "${ELEVENLABS_API_KEY:-}" ] && [ "$MUTATE" -eq 1 ]; then
    warn "ElevenLabs force-delete: API endpoint for customer voice data deletion"
    warn "is not yet wired in Phase-1. Manual delete required via ElevenLabs console."
    ELEVENLABS_STATUS="manual-required (API key present but ElevenLabs delete endpoint not wired Phase-1)"
elif [ -n "${ELEVENLABS_API_KEY:-}" ]; then
    log "(DRY-RUN) Would attempt ElevenLabs force-delete via API."
    ELEVENLABS_STATUS="dry-run: would attempt force-delete via API"
fi

echo "  [MANUAL] Cloudflare: edge cache flush + log purge required."
echo "           CoS officer: log into Cloudflare dashboard and purge cache"
echo "           for customer domain. Purge WAF logs if retained."
echo
echo "  [MANUAL] Hetzner: customer storage volume deletion required."
echo "           CoS officer: identify and delete the Hetzner storage volume"
echo "           associated with cabinet_id=${CABINET_ID}."
echo
echo "  ┌─────────────────────────────────────────────────────────────────────┐"
echo "  │  MANUAL-CASCADE CHECKLIST FOR CoS:                                  │"
echo "  │  [ ] Stripe: PII-anonymize customer record in Stripe dashboard       │"
echo "  │      (cannot delete — legal hold per Bogføringsloven §10)            │"
echo "  │  [ ] ElevenLabs: force-delete voice data in ElevenLabs console      │"
echo "  │      (cabinet_id: ${CABINET_ID})"
echo "  │  [ ] Cloudflare: purge edge cache + WAF logs for customer domain     │"
echo "  │  [ ] Hetzner: delete customer storage volume for this cabinet        │"
echo "  └─────────────────────────────────────────────────────────────────────┘"

# ── Step 5: Hot-storage purge ─────────────────────────────────────────────────

step "5 — Hot-storage purge"

PRE_WIPE_HASH="null"
ENTRIES_PROCESSED=0
ENTRIES_ERRORED=0
CHAIN_VERIFIED_POST="false"

if [ -f "${SSOT}" ]; then
    PRE_WIPE_HASH="$(sha256sum "${SSOT}" | awk '{print $1}')"
    log "Pre-wipe inventory hash (sha256): ${PRE_WIPE_HASH}"
else
    warn "SSOT file does not exist: ${SSOT}"
    log "No audit log found — nothing to pseudonymize. Pre-wipe hash: null"
fi

log
log "Audit log pseudonymization (FW-097 erasure.py — Spec 052 AC#8 two-hash schema):"

if [ "$MUTATE" -eq 1 ] && [ -f "${SSOT}" ]; then
    # Lift chattr +a append-only flag (deploy-gated; guarded by CABINET_ERASURE_NO_CHATTR).
    # Arm the EXIT trap FIRST (BUG-3) so +a is restored even if pseudonymize throws.
    if command -v chattr >/dev/null 2>&1 && [ -z "${CABINET_ERASURE_NO_CHATTR:-}" ]; then
        trap _restore_chattr EXIT
        chattr -a "${SSOT}" 2>/dev/null || true
    fi

    ERASURE_RESULT="$(PYTHONPATH="${AUDIT_SERVER}" python3 -c "
import erasure, pathlib, json
result = erasure.pseudonymize_cabinet('${CABINET_ID}', pathlib.Path('${SSOT}'))
print(result['processed'])
print(result['errors'])
")"
    ENTRIES_PROCESSED="$(echo "${ERASURE_RESULT}" | head -1)"
    ENTRIES_ERRORED="$(echo "${ERASURE_RESULT}" | tail -1)"

    # BUG-5 (Opus review): the python stdout MUST be two integers. Anything else
    # means a malformed result — never interpolate a non-integer into the Step-8
    # python / Step-7 jq (injection + half-done exit under set -e). Coerce to a
    # failure signal (errors=1 drives the BUG-2 success gate to fail-closed).
    if ! [[ "${ENTRIES_PROCESSED}" =~ ^[0-9]+$ ]]; then
        warn "Non-integer entries_processed='${ENTRIES_PROCESSED}' — treating as erasure failure."
        ENTRIES_PROCESSED=0
    fi
    if ! [[ "${ENTRIES_ERRORED}" =~ ^[0-9]+$ ]]; then
        warn "Non-integer entries_errored='${ENTRIES_ERRORED}' — treating as erasure failure."
        ENTRIES_ERRORED=1
    fi
    log "Pseudonymization result: processed=${ENTRIES_PROCESSED} errors=${ENTRIES_ERRORED}"

    # Re-apply chattr +a
    if command -v chattr >/dev/null 2>&1 && [ -z "${CABINET_ERASURE_NO_CHATTR:-}" ]; then
        chattr +a "${SSOT}" 2>/dev/null || true
    fi

    # Verify hash chain still validates post-erasure
    VERIFY_RESULT="$(PYTHONPATH="${AUDIT_SERVER}" python3 -c "
import hashchain
ok, bad_idx = hashchain.verify('${CABINET_ID}')
print(ok)
print(bad_idx)
" 2>/dev/null)"
    VERIFY_OK="$(echo "${VERIFY_RESULT}" | head -1)"
    VERIFY_BAD="$(echo "${VERIFY_RESULT}" | tail -1)"
    if [ "${VERIFY_OK}" = "True" ] && [ "${VERIFY_BAD}" = "None" ]; then
        CHAIN_VERIFIED_POST="true"
        log "Hash-chain verification post-erasure: PASS"
    else
        CHAIN_VERIFIED_POST="false"
        warn "Hash-chain verification post-erasure: FAIL at index ${VERIFY_BAD}"
    fi
elif [ "$MUTATE" -eq 1 ]; then
    log "SSOT does not exist — skipping pseudonymization gracefully."
    CHAIN_VERIFIED_POST="true"
else
    log "(DRY-RUN) Would pseudonymize via: erasure.pseudonymize_cabinet('${CABINET_ID}', Path('${SSOT}'))"
    log "(DRY-RUN) chattr -a / +a guarded by CABINET_ERASURE_NO_CHATTR env."
fi

log
log "Account profile / cabinet config (Phase-1 STUB):"
log "  Per CTO #3, no per-customer DB is local in Phase-1."
log "  This step wires to FW-099 (Stripe) + FW-101 (backend) when built."
log "  Action: log erasure_request=true against cabinet_id in customer DB."
log "  Phase-1: no-op with this log line. Profile deletion is MANUAL in Hetzner/DB."

# ── Erasure success gate (Opus review BUG-2) ─────────────────────────────────
# A failed pseudonymization (errors>0) or a broken post-erasure hash-chain must
# NOT be recorded as a completed erasure. Steps 7-8 branch on this: on failure the
# receipt is marked failed, the SLA ticket is left OPEN for retry, CoS is alerted,
# and the run exits 1. No-SSOT (nothing to erase) is trivially OK.
ERASURE_OK=1
if [ "$MUTATE" -eq 1 ] && [ -f "${SSOT}" ]; then
    [ "${ENTRIES_ERRORED}" -eq 0 ]        || ERASURE_OK=0
    [ "${CHAIN_VERIFIED_POST}" = "true" ] || ERASURE_OK=0
fi

# ── Step 6: Cold-storage handling ─────────────────────────────────────────────

step "6 — Cold-storage handling"
log "The pseudonymized audit log IS the compliance-retained form."
log "Legal basis for retention despite erasure request:"
log "  • Article 6(1)(c) — processing necessary for compliance with legal obligation"
log "  • Article 17(3)(b) — retention necessary for legal claims defence"
log "  • Bogføringsloven §10 — 5 years for general accounting records"
log "  • Skatteforvaltningsloven §47 — 10 years for tax-relevant records"
log "No further deletion of the log file. PII is pseudonymized (blanked)."
log "Cold-storage retention: 5y general / 10y tax-relevant (anonymized)."

# ── Step 7: Deletion receipt ──────────────────────────────────────────────────

step "7 — Deletion receipt"

COMPLETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ "$MUTATE" -eq 1 ]; then
    mkdir -p "${RECEIPT_DIR}"
    RECEIPT_FILE="${RECEIPT_DIR}/${TICKET_ID}-receipt.json"

    if [ "$ERASURE_OK" -eq 1 ]; then ERASURE_STATUS="completed"; else ERASURE_STATUS="failed"; fi

    jq -n \
        --arg status            "${ERASURE_STATUS}" \
        --arg ticket_id         "${TICKET_ID}" \
        --arg cabinet_id        "${CABINET_ID}" \
        --arg requested_at      "${REQUESTED_AT}" \
        --arg completed_at      "${COMPLETED_AT}" \
        --arg sla_due_at        "${SLA_DUE_AT}" \
        --arg pre_wipe_hash     "${PRE_WIPE_HASH}" \
        --argjson entries_proc  "${ENTRIES_PROCESSED}" \
        --argjson entries_err   "${ENTRIES_ERRORED}" \
        --arg chain_verified    "${CHAIN_VERIFIED_POST}" \
        --arg el_status         "${ELEVENLABS_STATUS}" \
        '{
            status:                 $status,
            erasure_verified:       ($status == "completed"),
            ticket_id:              $ticket_id,
            cabinet_id:             $cabinet_id,
            request_type:           "erasure",
            requested_at:           $requested_at,
            completed_at:           $completed_at,
            sla_due_at:             $sla_due_at,
            pre_wipe_inventory_hash: $pre_wipe_hash,
            audit_log_disposition:  {
                action:             "pseudonymized",
                entries_processed:  $entries_proc,
                entries_errored:    $entries_err,
                chain_verified_post: ($chain_verified == "true")
            },
            per_data_type: [
                {type: "audit-log",        disposition: "pseudonymized",              legal_basis: "Article17(3)(b)+Article6(1)(c)"},
                {type: "account-profile",  disposition: "deleted-or-stub",            note: "Phase-1 stub: wires to FW-099/FW-101; manual delete in DB/Hetzner"},
                {type: "voice-messages",   disposition: "30d-TTL-or-force-deleted",   status: $el_status},
                {type: "uploaded-files",   disposition: "customer-local-not-server",  note: "Files live on customer MacMini; not server-side; no Cabinet deletion required"},
                {type: "billing",          disposition: "Stripe-legal-hold-anonymized", note: "Cannot delete; Bogføringsloven §10 legal hold; PII-anonymize in Stripe"}
            ],
            subprocessor_cascade: [
                {name: "Anthropic",    method: "no-op",    status: "complete", note: "No Cabinet-side prompt/completion retention; nothing to erase"},
                {name: "Stripe",       method: "manual",   status: "pending",  note: "Legal hold (Bogføringsloven); PII-anonymize in Stripe dashboard — CoS action required"},
                {name: "ElevenLabs",   method: "automated", status: $el_status, note: "30-day TTL; force-delete if API key present"},
                {name: "Cloudflare",   method: "manual",   status: "pending",  note: "Edge cache flush + WAF log purge — CoS action required"},
                {name: "Hetzner",      method: "manual",   status: "pending",  note: "Customer storage volume deletion — CoS action required"}
            ],
            legal_basis: [
                "GDPR Article 17 — right to erasure",
                "GDPR Article 6(1)(c) — processing necessary for legal obligation",
                "GDPR Article 17(3)(b) — retention for legal claims defence",
                "Bogføringsloven §10 — 5-year general accounting retention",
                "Skatteforvaltningsloven §47 — 10-year tax-relevant retention"
            ],
            signed: false,
            signed_note: "Phase-1 unsigned; signing = Phase-2 when key custody infrastructure exists",
            library_compliance_filing: "REQUIRED — file to Library Compliance Space; not auto-filed in Phase-1 (no bash→Library MCP path)"
        }' > "${RECEIPT_FILE}"

    log "Receipt written: ${RECEIPT_FILE}"
    echo
    echo "  ── Receipt summary ──────────────────────────────────────────────────"
    echo "  ticket_id              : ${TICKET_ID}"
    echo "  completed_at           : ${COMPLETED_AT}"
    echo "  pre_wipe_inventory_hash: ${PRE_WIPE_HASH}"
    echo "  entries_processed      : ${ENTRIES_PROCESSED}"
    echo "  entries_errored        : ${ENTRIES_ERRORED}"
    echo "  chain_verified_post    : ${CHAIN_VERIFIED_POST}"
    echo "  erasure status         : ${ERASURE_STATUS}"
    echo "  receipt_file           : ${RECEIPT_FILE}"
    echo "  signed                 : false (Phase-1)"
    echo "  ─────────────────────────────────────────────────────────────────────"
else
    RECEIPT_FILE="${RECEIPT_DIR}/[DRY-RUN]-receipt.json"
    log "(DRY-RUN) Would write receipt to: ${RECEIPT_DIR}/${TICKET_ID}-receipt.json"
fi

# ── Step 8: Audit-log erasure event + SLA completion ─────────────────────────

step "8 — Tamper-evident erasure audit event + SLA completion"

if [ "$MUTATE" -eq 1 ]; then
    # Convert bash "true"/"false" to a Python bool literal for the metadata.
    PY_CHAIN_VERIFIED="True"
    [ "${CHAIN_VERIFIED_POST}" = "true" ] || PY_CHAIN_VERIFIED="False"

    # BUG-2: record an ACCURATE event — completed only when the erasure verified,
    # otherwise a failure event. The SLA ticket is NEVER marked done on failure.
    if [ "$ERASURE_OK" -eq 1 ]; then
        ERASURE_EVENT="gdpr_erasure_completed"
    else
        ERASURE_EVENT="gdpr_erasure_failed"
    fi

    # Append the erasure event AFTER pseudonymization so it is tamper-evidently
    # logged. chattr toggle is deploy-gated; guard it (the EXIT trap restores +a).
    if command -v chattr >/dev/null 2>&1 && [ -z "${CABINET_ERASURE_NO_CHATTR:-}" ]; then
        trap _restore_chattr EXIT
        chattr -a "${SSOT}" 2>/dev/null || true
    fi

    PYTHONPATH="${AUDIT_SERVER}" python3 -c "
import hashchain
hashchain.append({
    'ts':         '${COMPLETED_AT}',
    'cabinet_id': '${CABINET_ID}',
    'entry_id':   'gdpr-erasure-${TICKET_ID}',
    'stream':     'cabinet',
    'event_type': '${ERASURE_EVENT}',
    'actor': {
        'officer': 'cto-erasure-runbook',
        'captain': False
    },
    'subject': {
        'type':   'cabinet',
        'target': '${CABINET_ID}',
        'metadata': {
            'ticket_id':       '${TICKET_ID}',
            'request_type':    'erasure',
            'entries_processed': ${ENTRIES_PROCESSED},
            'entries_errored':   ${ENTRIES_ERRORED},
            'chain_verified':  ${PY_CHAIN_VERIFIED}
        }
    },
    'cost': {}
})
" || warn "Could not append ${ERASURE_EVENT} audit event."
    log "Appended ${ERASURE_EVENT} event to audit log."

    if command -v chattr >/dev/null 2>&1 && [ -z "${CABINET_ERASURE_NO_CHATTR:-}" ]; then
        chattr +a "${SSOT}" 2>/dev/null || true
    fi

    if [ "$ERASURE_OK" -eq 1 ]; then
        # Success: complete the SLA ticket.
        CABINET_HOOK_TEST_MODE="${TEST_MODE}" bash "${SLA_TRACKER}" complete "${TICKET_ID}"
    else
        # Failure: leave the SLA ticket OPEN (stays on the board for retry), alert
        # CoS, and fail the run. No false-complete (Opus review BUG-2).
        EXIT_CODE=1
        warn "Erasure FAILED for cabinet ${CABINET_ID}: errors=${ENTRIES_ERRORED} chain_verified=${CHAIN_VERIFIED_POST}."
        warn "SLA ticket ${TICKET_ID} left OPEN for retry; receipt marked failed."
        if [ "${TEST_MODE}" = "1" ]; then
            echo "WOULD-NOTIFY cos: erasure-FAILED ${TICKET_ID}"
        else
            bash "${NOTIFY_SCRIPT}" cos "GDPR erasure FAILED: ticket ${TICKET_ID} cabinet ${CABINET_ID} — errors ${ENTRIES_ERRORED}, chain_verified ${CHAIN_VERIFIED_POST}. SLA ticket left open; manual intervention required." 2>/dev/null || true
        fi
    fi
else
    log "(DRY-RUN) Would append gdpr_erasure_completed event to: ${SSOT}"
    log "(DRY-RUN) Would complete SLA ticket: ${TICKET_ID}"
fi

# ── Final summary ─────────────────────────────────────────────────────────────

echo
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║  Erasure runbook complete                                            ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo "  Cabinet ID : ${CABINET_ID}"
if [ "$MUTATE" -eq 1 ]; then
    echo "  Mode       : $([ "$EXIT_CODE" -eq 0 ] && echo 'EXECUTED (erasure verified)' || echo 'FAILED (erasure NOT verified — see warnings above)')"
else
    echo "  Mode       : DRY-RUN (no mutations performed)"
fi
if [ "$MUTATE" -eq 1 ]; then
    echo "  Receipt    : ${RECEIPT_FILE}"
fi
echo
echo "  ┌─────────────────────────────────────────────────────────────────────┐"
echo "  │  REQUIRED MANUAL STEPS FOR CoS OFFICER:                             │"
echo "  │  1. File erasure record to Library Compliance Space (MCP tool)       │"
echo "  │  2. Stripe: PII-anonymize customer record (legal hold — cannot del.) │"
echo "  │  3. ElevenLabs: confirm voice data deletion in console               │"
echo "  │  4. Cloudflare: purge edge cache + WAF logs                          │"
echo "  │  5. Hetzner: delete customer storage volume                          │"
echo "  │  6. Send erasure completion notification to customer with receipt     │"
echo "  └─────────────────────────────────────────────────────────────────────┘"
echo
if [ "$MUTATE" -eq 0 ]; then
    echo "  Run with --confirm to execute the erasure."
fi

exit ${EXIT_CODE}
