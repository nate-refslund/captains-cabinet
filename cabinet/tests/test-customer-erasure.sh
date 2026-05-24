#!/usr/bin/env bash
# cabinet/tests/test-customer-erasure.sh — FW-100 / Spec 055 AC#6 regression harness.
#
# WHY THIS EXISTS: Spec 055 AC#6 (GDPR right-to-erasure substrate) requires
# hermetic validation of:
#   §A — sla-tracker.sh: create/complete/check/idempotency/breach
#   §B — customer-erasure.sh: 8-step Article-17 runbook end-to-end
#
# HERMETIC: at startup, all runtime dirs are set to a fresh mktemp -d.
#   LITELLM_AUDIT_LOG_ROOT, CABINET_GDPR_TICKET_DIR, CABINET_ERASURE_RECEIPT_DIR
#   all point into $TMP. CABINET_HOOK_TEST_MODE=1 suppresses real notifications.
#   CABINET_ERASURE_NO_CHATTR=1 suppresses chattr (runs fine without root).
#   No real network, no real Redis writes, no chattr calls.
#
# Usage: bash cabinet/tests/test-customer-erasure.sh
#   exit 0 = all assertions pass
#   exit 1 = one or more assertions failed (failures listed before summary)

set -u

# ── Locate repo root ──────────────────────────────────────────────────────────
_THIS_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
_SCRIPT_DIR="$(dirname "$_THIS_SCRIPT")"
# cabinet/tests → cabinet → repo root (two levels up)
CABINET_ROOT="$(cd "$_SCRIPT_DIR/../.." && pwd)"
AUDIT_SERVER="${CABINET_ROOT}/proxy/audit-server"
SCRIPTS="${CABINET_ROOT}/cabinet/scripts"

# ── Hermetic env setup ────────────────────────────────────────────────────────
TMP="$(mktemp -d)"
export LITELLM_AUDIT_LOG_ROOT="${TMP}/audit-root"
export CABINET_GDPR_TICKET_DIR="${TMP}/gdpr-tickets"
export CABINET_ERASURE_RECEIPT_DIR="${TMP}/erasure-receipts"
export CABINET_HOOK_TEST_MODE=1
export CABINET_ERASURE_NO_CHATTR=1
export CABINET_ROOT

mkdir -p "${LITELLM_AUDIT_LOG_ROOT}/audit" \
         "${CABINET_GDPR_TICKET_DIR}" \
         "${CABINET_ERASURE_RECEIPT_DIR}"

trap 'rm -rf "$TMP"' EXIT

# ── Test infrastructure ───────────────────────────────────────────────────────
PASS=0; FAIL=0; FAILURES=""

pass()    { PASS=$((PASS + 1)); }
fail()    { FAIL=$((FAIL + 1)); FAILURES="${FAILURES}  FAIL: $1\n"; printf '  FAIL: %s\n' "$1"; }
section() { printf '\n── %s\n' "$1"; }

assert_eq() {
    # assert_eq <label> <got> <want>
    if [ "$2" = "$3" ]; then pass; else fail "$1: got [$2] want [$3]"; fi
}
assert_contains() {
    # assert_contains <label> <haystack> <needle>
    if printf '%s' "$2" | grep -qF "$3"; then pass; else fail "$1: [$2] does not contain [$3]"; fi
}
assert_not_contains() {
    # assert_not_contains <label> <haystack> <needle>
    if ! printf '%s' "$2" | grep -qF "$3"; then pass; else fail "$1: [$2] should NOT contain [$3]"; fi
}
assert_exit0() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then pass; else fail "${label}: expected exit 0"; fi
}
assert_file_exists() {
    if [ -f "$2" ]; then pass; else fail "$1: file not found: $2"; fi
}

# Convenience: run python with our hermetic LITELLM_AUDIT_LOG_ROOT
py() {
    LITELLM_AUDIT_LOG_ROOT="${LITELLM_AUDIT_LOG_ROOT}" \
    PYTHONPATH="${AUDIT_SERVER}" \
    python3 "$@"
}

# Run sla-tracker with hermetic env
sla() {
    CABINET_GDPR_TICKET_DIR="${CABINET_GDPR_TICKET_DIR}" \
    CABINET_HOOK_TEST_MODE=1 \
    bash "${SCRIPTS}/sla-tracker.sh" "$@"
}

# Run customer-erasure with hermetic env
erasure() {
    LITELLM_AUDIT_LOG_ROOT="${LITELLM_AUDIT_LOG_ROOT}" \
    CABINET_ERASURE_RECEIPT_DIR="${CABINET_ERASURE_RECEIPT_DIR}" \
    CABINET_GDPR_TICKET_DIR="${CABINET_GDPR_TICKET_DIR}" \
    CABINET_ERASURE_NO_CHATTR=1 \
    CABINET_HOOK_TEST_MODE=1 \
    CABINET_ROOT="${CABINET_ROOT}" \
    bash "${SCRIPTS}/customer-erasure.sh" "$@"
}

# Backdate a ticket's requested_at to N days ago (for SLA threshold testing)
backdate_ticket() {
    local ticket_file="$1"
    local days_ago="$2"
    local new_requested_at
    new_requested_at="$(date -u -d "${days_ago} days ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
                       || date -u -v"-${days_ago}d" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"
    local tmp_file
    tmp_file="$(mktemp "${ticket_file}.tmp.XXXXXX")"
    jq --arg ts "$new_requested_at" '.requested_at = $ts' "$ticket_file" > "$tmp_file" \
        && mv "$tmp_file" "$ticket_file"
}

# ════════════════════════════════════════════════════════════════════════════════
# §A — sla-tracker.sh
# ════════════════════════════════════════════════════════════════════════════════

section "§A.1 — sla-tracker create erasure"

SLA_OUT="$(sla create erasure test-cabinet-sla 2>/dev/null)"
TICKET_ID_A="$(echo "$SLA_OUT" | head -1)"
DUE_AT_A="$(echo "$SLA_OUT" | tail -1)"

TICKET_FILE_A="${CABINET_GDPR_TICKET_DIR}/${TICKET_ID_A}.json"

assert_file_exists "ticket JSON exists" "${TICKET_FILE_A}"
assert_eq "status is open"       "$(jq -r '.status'      "${TICKET_FILE_A}")" "open"
assert_eq "alerts_sent is empty" "$(jq -c '.alerts_sent' "${TICKET_FILE_A}")" "[]"
assert_eq "type is erasure"      "$(jq -r '.type'        "${TICKET_FILE_A}")" "erasure"
assert_eq "completed_at is null" "$(jq -r '.completed_at' "${TICKET_FILE_A}")" "null"

# Verify due_at is approximately requested_at + 30 days
REQUESTED_EPOCH="$(date -u -d "$(jq -r '.requested_at' "${TICKET_FILE_A}")" +%s 2>/dev/null || echo 0)"
DUE_EPOCH="$(date -u -d "${DUE_AT_A}" +%s 2>/dev/null || echo 0)"
DUE_DELTA=$(( DUE_EPOCH - REQUESTED_EPOCH ))
# Allow a 5-second window (due to date arithmetic rounding)
if [ "$DUE_DELTA" -ge 2591995 ] && [ "$DUE_DELTA" -le 2592005 ]; then
    pass
else
    fail "due_at delta: expected ~2592000s (30d), got ${DUE_DELTA}s"
fi

section "§A.2 — sla-tracker check at day-25 (approaching)"

backdate_ticket "${TICKET_FILE_A}" 25

CHECK_OUT_25="$(CABINET_SLA_NOW_OVERRIDE="" sla check 2>/dev/null)"
assert_contains "day-25 approaching notify" "$CHECK_OUT_25" "WOULD-NOTIFY cos: approaching ${TICKET_ID_A}"

ALERTS_AFTER_25="$(jq -c '.alerts_sent' "${TICKET_FILE_A}")"
assert_contains "approaching persisted in alerts_sent" "$ALERTS_AFTER_25" "approaching"

section "§A.3 — sla-tracker check idempotency (no duplicate approaching at day-25)"

CHECK_OUT_25_AGAIN="$(CABINET_SLA_NOW_OVERRIDE="" sla check 2>/dev/null)"
# Should NOT print another approaching notify (idempotent)
if printf '%s' "$CHECK_OUT_25_AGAIN" | grep -qF "approaching ${TICKET_ID_A}"; then
    fail "no duplicate approaching notify: second check printed another approaching"
else
    pass
fi

section "§A.4 — sla-tracker check at day-31 (BREACH)"

backdate_ticket "${TICKET_FILE_A}" 31

CHECK_OUT_31="$(CABINET_SLA_NOW_OVERRIDE="" sla check 2>/dev/null)"
assert_contains "day-31 BREACH notify" "$CHECK_OUT_31" "WOULD-NOTIFY cos: BREACH ${TICKET_ID_A}"

section "§A.5 — sla-tracker BREACH idempotency"

CHECK_OUT_31_AGAIN="$(CABINET_SLA_NOW_OVERRIDE="" sla check 2>/dev/null)"
if printf '%s' "$CHECK_OUT_31_AGAIN" | grep -qF "BREACH ${TICKET_ID_A}"; then
    fail "no duplicate BREACH notify: second check printed another BREACH"
else
    pass
fi

section "§A.6 — sla-tracker complete"

COMPLETE_OUT="$(sla complete "${TICKET_ID_A}" 2>/dev/null)"
assert_contains "complete confirmation" "$COMPLETE_OUT" "marked complete"
assert_eq "status is done"       "$(jq -r '.status'       "${TICKET_FILE_A}")" "done"
# completed_at should not be null
COMPLETED_AT_VAL="$(jq -r '.completed_at' "${TICKET_FILE_A}")"
if [ "$COMPLETED_AT_VAL" != "null" ] && [ -n "$COMPLETED_AT_VAL" ]; then
    pass
else
    fail "completed_at not set after complete (got: ${COMPLETED_AT_VAL})"
fi

section "§A.7 — sla-tracker check skips done tickets"

backdate_ticket "${TICKET_FILE_A}" 31  # still 31 days ago
CHECK_DONE="$(CABINET_SLA_NOW_OVERRIDE="" sla check 2>/dev/null)"
if printf '%s' "$CHECK_DONE" | grep -qF "${TICKET_ID_A}"; then
    fail "done ticket not re-notified: check still printed notify for done ticket"
else
    pass
fi

# ════════════════════════════════════════════════════════════════════════════════
# §B — customer-erasure.sh
# ════════════════════════════════════════════════════════════════════════════════

CABINET_ID_B="test-erasure-cabinet-b"
SSOT_B="${LITELLM_AUDIT_LOG_ROOT}/audit/${CABINET_ID_B}.jsonl"

section "§B.1 — seed 3 chained audit entries with PII"

py -c "
import hashchain, os
cabinet_id = '${CABINET_ID_B}'
for i in range(3):
    hashchain.append({
        'ts':         '2026-01-01T00:00:0{}Z'.format(i),
        'cabinet_id': cabinet_id,
        'entry_id':   'seed-{}'.format(i),
        'stream':     'cabinet',
        'event_type': 'signup',
        'actor':      {'officer': None, 'captain': True},
        'subject': {
            'type':   'cap_event',
            'target': 'signup',
            'metadata': {
                'customer_name': 'Alice Erasure-Test',
                'email':         'alice@erasure-test.example.com',
                'ip_address':    '192.0.2.1',
            }
        },
        'cost': {},
    })
" 2>/dev/null

assert_file_exists "SSOT seeded" "${SSOT_B}"

section "§B.2 — hashchain verify BEFORE erasure"

VERIFY_BEFORE="$(py -c "
import hashchain
ok, bad = hashchain.verify('${CABINET_ID_B}')
print('ok' if ok else 'bad')
" 2>/dev/null)"
assert_eq "chain valid before erasure" "$VERIFY_BEFORE" "ok"

# Capture pre-erasure sha256
PRE_HASH="$(sha256sum "${SSOT_B}" | awk '{print $1}')"

section "§B.3 — capture pre-erasure entry_hash values"

PRE_ENTRY_HASHES="$(py -c "
import json, pathlib
lines = pathlib.Path('${SSOT_B}').read_text().strip().splitlines()
for line in lines:
    e = json.loads(line)
    print(e.get('integrity', {}).get('entry_hash', 'MISSING'))
" 2>/dev/null)"

section "§B.4 — run customer-erasure.sh --confirm"

ERASURE_OUT="$(erasure "${CABINET_ID_B}" --confirm 2>/dev/null)"
ERASURE_RC="$?"
assert_eq "erasure exits 0" "$ERASURE_RC" "0"

# Verify PII is blanked
SSOT_CONTENT="$(cat "${SSOT_B}")"
assert_contains "PII blanked: REDACTED present" "$SSOT_CONTENT" "REDACTED-"
assert_not_contains "PII gone: no original name" "$SSOT_CONTENT" "Alice Erasure-Test"
assert_not_contains "PII gone: no original email" "$SSOT_CONTENT" "alice@erasure-test.example.com"
assert_contains "pseudonym_marker_hash added" "$SSOT_CONTENT" "pseudonym_marker_hash"

section "§B.5 — entry_hash values PRESERVED post-erasure"

POST_ENTRY_HASHES="$(py -c "
import json, pathlib
lines = pathlib.Path('${SSOT_B}').read_text().strip().splitlines()
hashes = []
for line in lines:
    e = json.loads(line)
    h = e.get('integrity', {}).get('entry_hash', 'MISSING')
    # Only check first 3 (original entries, not the appended erasure event)
    hashes.append(h)
print('\n'.join(hashes[:3]))
" 2>/dev/null)"

# Compare first 3 hashes to pre-erasure
PRE_LINES="$(echo "$PRE_ENTRY_HASHES" | head -3)"
POST_LINES="$(echo "$POST_ENTRY_HASHES" | head -3)"
assert_eq "entry_hash values unchanged post-erasure" "$PRE_LINES" "$POST_LINES"

section "§B.6 — hashchain verify AFTER erasure"

VERIFY_AFTER="$(py -c "
import hashchain
ok, bad = hashchain.verify('${CABINET_ID_B}')
print('ok' if ok else 'bad-at-{}'.format(bad))
" 2>/dev/null)"
assert_eq "chain valid after erasure" "$VERIFY_AFTER" "ok"

section "§B.7 — receipt exists with correct fields"

# Find receipt file for this cabinet
RECEIPT_FILE="$(find "${CABINET_ERASURE_RECEIPT_DIR}" -name "*${CABINET_ID_B}*-receipt.json" 2>/dev/null | head -1)"
if [ -z "$RECEIPT_FILE" ]; then
    RECEIPT_FILE="$(find "${CABINET_ERASURE_RECEIPT_DIR}" -name "*-receipt.json" 2>/dev/null | head -1)"
fi

assert_file_exists "receipt file exists" "${RECEIPT_FILE}"

RECEIPT_CONTENT="$(cat "${RECEIPT_FILE}")"

# pre_wipe_inventory_hash matches the sha256 we captured before erasure
RECEIPT_PRE_HASH="$(jq -r '.pre_wipe_inventory_hash' "${RECEIPT_FILE}")"
assert_eq "pre_wipe_inventory_hash matches" "$RECEIPT_PRE_HASH" "$PRE_HASH"

# chain_verified_post == true
CHAIN_VERIFIED="$(jq -r '.audit_log_disposition.chain_verified_post' "${RECEIPT_FILE}")"
assert_eq "chain_verified_post is true" "$CHAIN_VERIFIED" "true"

# per_data_type array present and non-empty
PER_DATA_TYPE_LEN="$(jq '.per_data_type | length' "${RECEIPT_FILE}" 2>/dev/null)"
if [ "$PER_DATA_TYPE_LEN" -gt 0 ] 2>/dev/null; then pass; else fail "per_data_type array empty or missing (len=${PER_DATA_TYPE_LEN})"; fi

# subprocessor_cascade array present and non-empty
SUBPROCESS_LEN="$(jq '.subprocessor_cascade | length' "${RECEIPT_FILE}" 2>/dev/null)"
if [ "$SUBPROCESS_LEN" -gt 0 ] 2>/dev/null; then pass; else fail "subprocessor_cascade array empty or missing (len=${SUBPROCESS_LEN})"; fi

# legal_basis array present and non-empty
LEGAL_LEN="$(jq '.legal_basis | length' "${RECEIPT_FILE}" 2>/dev/null)"
if [ "$LEGAL_LEN" -gt 0 ] 2>/dev/null; then pass; else fail "legal_basis array empty or missing (len=${LEGAL_LEN})"; fi

# signed == false
RECEIPT_SIGNED="$(jq -r '.signed' "${RECEIPT_FILE}")"
assert_eq "signed is false (Phase-1)" "$RECEIPT_SIGNED" "false"

# library_compliance_filing present
LIBRARY_FIELD="$(jq -r '.library_compliance_filing' "${RECEIPT_FILE}")"
if [ -n "$LIBRARY_FIELD" ] && [ "$LIBRARY_FIELD" != "null" ]; then pass; else fail "library_compliance_filing field missing or null"; fi

section "§B.8 — gdpr_erasure_completed event appended to SSOT"

ERASURE_EVENT="$(py -c "
import json, pathlib
lines = pathlib.Path('${SSOT_B}').read_text().strip().splitlines()
for line in lines:
    e = json.loads(line)
    if e.get('event_type') == 'gdpr_erasure_completed':
        print('found')
        break
" 2>/dev/null)"
assert_eq "gdpr_erasure_completed event in SSOT" "$ERASURE_EVENT" "found"

section "§B.9 — SLA ticket created by run is marked done"

# The receipt has the ticket_id
SLA_TICKET_ID="$(jq -r '.ticket_id' "${RECEIPT_FILE}" 2>/dev/null)"
SLA_TICKET_FILE="${CABINET_GDPR_TICKET_DIR}/${SLA_TICKET_ID}.json"
assert_file_exists "SLA ticket file exists" "${SLA_TICKET_FILE}"
assert_eq "SLA ticket status is done" "$(jq -r '.status' "${SLA_TICKET_FILE}")" "done"

section "§B.10 — --dry-run does NOT mutate a second cabinet"

CABINET_ID_DRY="test-erasure-dryrun-cabinet"
SSOT_DRY="${LITELLM_AUDIT_LOG_ROOT}/audit/${CABINET_ID_DRY}.jsonl"

# Seed it
py -c "
import hashchain
hashchain.append({
    'ts':         '2026-06-01T00:00:00Z',
    'cabinet_id': '${CABINET_ID_DRY}',
    'entry_id':   'dry-seed-1',
    'stream':     'cabinet',
    'event_type': 'signup',
    'actor':      {'officer': None, 'captain': True},
    'subject':    {'type': 'cap_event', 'target': 'signup', 'metadata': {'customer_name': 'Dry Run User', 'email': 'dry@example.com'}},
    'cost':       {},
})
" 2>/dev/null

# Capture content before dry-run
CONTENT_BEFORE="$(cat "${SSOT_DRY}")"

# Run dry-run
erasure "${CABINET_ID_DRY}" --dry-run >/dev/null 2>&1

# Content must be identical after dry-run
CONTENT_AFTER="$(cat "${SSOT_DRY}")"
assert_eq "dry-run: SSOT unchanged" "$CONTENT_BEFORE" "$CONTENT_AFTER"

# No receipt for dry-run cabinet
DRY_RECEIPT="$(find "${CABINET_ERASURE_RECEIPT_DIR}" -name "*${CABINET_ID_DRY}*" 2>/dev/null | head -1)"
if [ -z "$DRY_RECEIPT" ]; then pass; else fail "dry-run: receipt should not be written, found: ${DRY_RECEIPT}"; fi

section "§B.11 — sub-processor cascade with no creds: exits 0 + prints MANUAL checklist"

CABINET_ID_NOKEY="test-erasure-nokey"
# Seed a minimal SSOT for it
py -c "
import hashchain
hashchain.append({
    'ts': '2026-06-01T00:00:00Z', 'cabinet_id': '${CABINET_ID_NOKEY}',
    'entry_id': 'nk-1', 'stream': 'cabinet', 'event_type': 'signup',
    'actor': {'officer': None, 'captain': True},
    'subject': {'type': 'cap_event', 'target': 'signup', 'metadata': {'customer_name': 'No Key User'}},
    'cost': {},
})
" 2>/dev/null

NOKEY_OUT="$(ELEVENLABS_API_KEY="" erasure "${CABINET_ID_NOKEY}" --confirm 2>/dev/null)"
NOKEY_RC=$?
assert_eq "exits 0 with no creds" "$NOKEY_RC" "0"
assert_contains "Anthropic no-op line present" "$NOKEY_OUT" "Anthropic"
assert_contains "Cloudflare manual checklist present" "$NOKEY_OUT" "Cloudflare"
assert_contains "Hetzner manual checklist present" "$NOKEY_OUT" "Hetzner"

section "§B.12 — chattr guard: CABINET_ERASURE_NO_CHATTR=1 honoured (no chattr error)"

# If CABINET_ERASURE_NO_CHATTR=1 is honoured, the run above produced no chattr errors.
# Re-run the nokey cabinet in safe mode and confirm no chattr-related error output.
CHATTR_OUT="$(CABINET_ERASURE_NO_CHATTR=1 erasure "${CABINET_ID_DRY}" --dry-run 2>&1)"
assert_not_contains "no chattr error in output" "$CHATTR_OUT" "chattr:"

# ════════════════════════════════════════════════════════════════════════════════
# §C — security + failure-injection (Opus review SG-1: the happy-path harness was
#      blind to BUG-1 cabinet_id injection + BUG-2 false-complete-on-failure)
# ════════════════════════════════════════════════════════════════════════════════

section "§C.1 — cabinet_id injection is rejected at entry (Opus BUG-1/RCE)"

SENTINEL="${TMP}/PWNED_SENTINEL"

# (a) python-literal break-out + os.system — the exact RCE class the reviewer proved.
rm -f "$SENTINEL"
INJECT_PY="x'); import os; os.system('touch ${SENTINEL}'); ('"
erasure "$INJECT_PY" --confirm >/dev/null 2>&1
INJ_RC=$?
if [ "$INJ_RC" -ne 0 ]; then pass; else fail "python-injection cabinet_id must be rejected (got exit 0)"; fi
if [ ! -f "$SENTINEL" ]; then pass; else fail "RCE: python-injection sentinel was created — cabinet_id NOT validated!"; fi

# (b) shell-metacharacter break-out.
rm -f "$SENTINEL"
erasure "evil; touch ${SENTINEL}" --confirm >/dev/null 2>&1
SH_RC=$?
if [ "$SH_RC" -ne 0 ]; then pass; else fail "shell-metachar cabinet_id must be rejected (got exit 0)"; fi
if [ ! -f "$SENTINEL" ]; then pass; else fail "RCE: shell-metachar sentinel was created!"; fi

# (c) path-traversal (cross-tenant / outside-root read).
erasure "../../etc/passwd" --confirm >/dev/null 2>&1
if [ "$?" -ne 0 ]; then pass; else fail "path-traversal cabinet_id must be rejected"; fi

# (d) uppercase rejected (strict lowercase slug).
erasure "UpperCaseCabinet" --confirm >/dev/null 2>&1
if [ "$?" -ne 0 ]; then pass; else fail "uppercase cabinet_id must be rejected"; fi

# (e) the rejection is explicit.
REJECT_MSG="$(erasure "bad;id" --confirm 2>&1 || true)"
assert_contains "rejection names invalid cabinet_id" "$REJECT_MSG" "invalid cabinet_id"

# (f) regression guard — a legitimate slug is NOT over-rejected.
VALID_MSG="$(erasure "valid-cabinet-123" --dry-run 2>&1 || true)"
assert_not_contains "valid slug not over-rejected" "$VALID_MSG" "invalid cabinet_id"

section "§C.2 — corrupt-log erasure fails CLOSED, never false-completes (Opus BUG-2)"

CABINET_ID_FAIL="test-erasure-failcabinet"
SSOT_FAIL="${LITELLM_AUDIT_LOG_ROOT}/audit/${CABINET_ID_FAIL}.jsonl"

# Seed one valid PII entry, then append a CORRUPT (non-JSON) line so pseudonymize
# reports errors>0 AND the post-erasure chain verify fails.
py -c "
import hashchain
hashchain.append({
    'ts': '2026-02-01T00:00:00Z', 'cabinet_id': '${CABINET_ID_FAIL}',
    'entry_id': 'fail-1', 'stream': 'cabinet', 'event_type': 'signup',
    'actor': {'officer': None, 'captain': True},
    'subject': {'type': 'cap_event', 'target': 'signup', 'metadata': {'customer_name': 'Fail User', 'email': 'fail@example.com'}},
    'cost': {},
})
" 2>/dev/null
printf 'THIS IS NOT VALID JSON {{{ broken\n' >> "${SSOT_FAIL}"

FAIL_OUT="$(erasure "${CABINET_ID_FAIL}" --confirm 2>&1)"
FAIL_RC=$?

# (a) fail-closed: must exit non-zero (no false-complete).
if [ "$FAIL_RC" -ne 0 ]; then pass; else fail "corrupt-log erasure must exit non-zero (got 0 — false-complete!)"; fi
# (b) CoS is alerted to the failure.
assert_contains "failure alerts CoS" "$FAIL_OUT" "erasure-FAILED"
# (c) receipt is marked failed, not pseudonymized-success.
FAIL_RECEIPT="$(find "${CABINET_ERASURE_RECEIPT_DIR}" -name "*${CABINET_ID_FAIL}*-receipt.json" 2>/dev/null | head -1)"
assert_file_exists "failure receipt exists" "${FAIL_RECEIPT}"
assert_eq "receipt status is failed"        "$(jq -r '.status'           "${FAIL_RECEIPT}" 2>/dev/null)" "failed"
assert_eq "receipt erasure_verified false"  "$(jq -r '.erasure_verified' "${FAIL_RECEIPT}" 2>/dev/null)" "false"
# (d) SLA ticket is LEFT OPEN for retry (never marked done on failure).
FAIL_TICKET_ID="$(jq -r '.ticket_id' "${FAIL_RECEIPT}" 2>/dev/null)"
assert_eq "SLA ticket left OPEN on failure" "$(jq -r '.status' "${CABINET_GDPR_TICKET_DIR}/${FAIL_TICKET_ID}.json" 2>/dev/null)" "open"

# ── Summary ───────────────────────────────────────────────────────────────────

printf '\n════════════════════════════════════════════════════════════════════\n'
printf '  FW-100 / Spec 055 AC#6 — customer-erasure harness\n'
printf '  PASS: %d   FAIL: %d   TOTAL: %d\n' "$PASS" "$FAIL" "$((PASS + FAIL))"
if [ "$FAIL" -gt 0 ]; then
    printf '\nFailed assertions:\n'
    printf '%b' "$FAILURES"
    printf '\n'
fi
printf '════════════════════════════════════════════════════════════════════\n'

[ "$FAIL" -eq 0 ]
