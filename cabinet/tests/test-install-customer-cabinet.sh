#!/usr/bin/env bash
# cabinet/tests/test-install-customer-cabinet.sh — FW-098 / Spec 053 v4.1 regression harness.
#
# Hermetic validation of cabinet/scripts/install-customer-cabinet.sh (concierge orchestrator):
#   §A slug-injection guard      §B install-token validation     §C secret handling + no-leak
#   §D dry-run no-mutation       §E --confirm injection path      §F ANTHROPIC-absent gate
#   §G idempotent re-run
#
# HERMETIC: CABINET_INSTALL_ROOT → mktemp; INSTALL_SKIP_{CLONE,BOOTSTRAP,OFFICERS}=1 so no real
# git clone, no real cabinet-bootstrap.sh, no officer spawn, no network. Secrets are the clearly
# fake values from the shared mock fixture (refslund-customer-mock.sh, CTO #5).
#
# Usage: bash cabinet/tests/test-install-customer-cabinet.sh   (exit 0 = all pass)

set -u

_THIS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="$(cd "$_THIS/../.." && pwd)"
SCRIPT="${CABINET_ROOT}/cabinet/scripts/install-customer-cabinet.sh"
# shellcheck source=/dev/null
source "${_THIS}/mocks/refslund-customer-mock.sh"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0; FAILURES=""
pass()    { PASS=$((PASS + 1)); }
fail()    { FAIL=$((FAIL + 1)); FAILURES="${FAILURES}  FAIL: $1\n"; printf '  FAIL: %s\n' "$1"; }
section() { printf '\n── %s\n' "$1"; }

# Run the install script with hermetic env. Arg 1 = install root; rest = script args.
# Secrets/token are read from the caller's exported env (forwarded by inheritance).
install_run() {
    local root="$1"; shift
    CABINET_INSTALL_ROOT="$root" \
    INSTALL_SKIP_CLONE=1 INSTALL_SKIP_BOOTSTRAP=1 INSTALL_SKIP_OFFICERS=1 \
    CABINET_HOOK_TEST_MODE=1 \
    bash "$SCRIPT" "$@"
}

# Default valid secrets + token for the happy-path tests.
export LLM_PROXY_KEY="$MOCK_LLM_PROXY_KEY"
export AUDIT_API_KEY="$MOCK_AUDIT_API_KEY"
export TELEGRAM_CEO_TOKEN="$MOCK_TELEGRAM_CEO_TOKEN"
export REFSLUND_INSTALL_TOKEN="$(mock_install_token)"

# ════════════════════════════════════════════════════════════════════════════════
section "§A — slug-injection guard (FW-100 lesson)"
SENTINEL="$TMP/PWNED"
for bad in 'evil; touch '"$SENTINEL" 'a$(touch '"$SENTINEL"')' 'UpperCase' '../etc' "$(printf 'a\nb')" 'way-too-long-slug-that-exceeds-the-thirty-two-character-cap-xxxxx'; do
    install_run "$TMP/slug-root" "$bad" --confirm >/dev/null 2>&1
    if [ "$?" -ne 0 ]; then pass; else fail "slug should be rejected: [$bad]"; fi
done
[ ! -f "$SENTINEL" ] && pass || fail "RCE: injection sentinel created"

# ════════════════════════════════════════════════════════════════════════════════
section "§B — install-token validation"
# valid
OUT="$(install_run "$TMP/tok-ok" "$MOCK_CUSTOMER_SLUG" --dry-run 2>&1)"
printf '%s' "$OUT" | grep -qF "Token OK" && pass || fail "valid token should pass"
# missing token
( unset REFSLUND_INSTALL_TOKEN; install_run "$TMP/tok-miss" "$MOCK_CUSTOMER_SLUG" --dry-run >/dev/null 2>&1 )
[ "$?" -ne 0 ] && pass || fail "missing token should die"
# not a JWT (no dots)
OUT="$(REFSLUND_INSTALL_TOKEN="notajwt" install_run "$TMP/tok-bad" "$MOCK_CUSTOMER_SLUG" --dry-run 2>&1)"
printf '%s' "$OUT" | grep -qiE "well-formed JWT" && pass || fail "non-JWT token should be rejected"
# expired
OUT="$(REFSLUND_INSTALL_TOKEN="$(mock_install_token 1000000000)" install_run "$TMP/tok-exp" "$MOCK_CUSTOMER_SLUG" --dry-run 2>&1)"
printf '%s' "$OUT" | grep -qiF "EXPIRED" && pass || fail "expired token should be rejected"
# missing required claim (no customer_id)
OUT="$(REFSLUND_INSTALL_TOKEN="$(mock_install_token_payload '{"tier":"base","exp":9999999999}')" install_run "$TMP/tok-claim" "$MOCK_CUSTOMER_SLUG" --dry-run 2>&1)"
printf '%s' "$OUT" | grep -qiF "missing required claim" && pass || fail "token missing customer_id should be rejected"

# ════════════════════════════════════════════════════════════════════════════════
section "§C — secret handling: presence + NO value leak to output"
# missing a required secret
OUT="$( unset LLM_PROXY_KEY; install_run "$TMP/sec-miss" "$MOCK_CUSTOMER_SLUG" --dry-run 2>&1 )"
printf '%s' "$OUT" | grep -qiF "missing required secret" && pass || fail "missing LLM_PROXY_KEY should die"
# NO LEAK: secret VALUES must never appear in stdout/stderr (only presence + length)
OUT="$(install_run "$TMP/sec-leak" "$MOCK_CUSTOMER_SLUG" --confirm 2>&1)"
LEAK=0
for v in "$MOCK_LLM_PROXY_KEY" "$MOCK_AUDIT_API_KEY" "$MOCK_TELEGRAM_CEO_TOKEN"; do
    printf '%s' "$OUT" | grep -qF "$v" && LEAK=1
done
[ "$LEAK" -eq 0 ] && pass || fail "secret VALUE leaked to script output (redaction failed)"

# ════════════════════════════════════════════════════════════════════════════════
section "§D — dry-run mutates nothing"
DROOT="$TMP/dry-root"
install_run "$DROOT" "$MOCK_CUSTOMER_SLUG" --dry-run >/dev/null 2>&1
[ ! -f "$DROOT/cabinet/.env" ] && pass || fail "dry-run must NOT write cabinet/.env"

# ════════════════════════════════════════════════════════════════════════════════
section "§E — --confirm injects secrets into cabinet/.env (chmod 600)"
CROOT="$TMP/confirm-root"
install_run "$CROOT" "$MOCK_CUSTOMER_SLUG" --confirm >/dev/null 2>&1
RC=$?
ENVF="$CROOT/cabinet/.env"
[ "$RC" -eq 0 ] && pass || fail "--confirm happy path should exit 0 (got $RC)"
[ -f "$ENVF" ] && pass || fail "cabinet/.env should be created"
grep -q "^LLM_PROXY_KEY=" "$ENVF" 2>/dev/null && pass || fail "LLM_PROXY_KEY not injected"
grep -q "^AUDIT_API_KEY=" "$ENVF" 2>/dev/null && pass || fail "AUDIT_API_KEY not injected"
grep -q "^TELEGRAM_MOCK_REFSLUND_CO_CEO_TOKEN=" "$ENVF" 2>/dev/null && pass || fail "per-customer TELEGRAM key not injected"
grep -q "^REFSLUND_INSTALL_TOKEN=" "$ENVF" 2>/dev/null && pass || fail "install token not persisted"
MODE="$(stat -c '%a' "$ENVF" 2>/dev/null || stat -f '%Lp' "$ENVF" 2>/dev/null)"
[ "$MODE" = "600" ] && pass || fail "cabinet/.env mode should be 600 (got $MODE)"
# the injected secret VALUE is in the FILE (correct) — sanity that injection actually wrote it
grep -qF "$MOCK_LLM_PROXY_KEY" "$ENVF" 2>/dev/null && pass || fail "LLM_PROXY_KEY value not written to .env"

# ════════════════════════════════════════════════════════════════════════════════
section "§F — first-boot gate FAILS on raw ANTHROPIC_API_KEY (proxy/cap/audit bypass)"
AROOT="$TMP/anthropic-root"; mkdir -p "$AROOT/cabinet"
printf 'ANTHROPIC_API_KEY=sk-raw-bypass\n' > "$AROOT/cabinet/.env"
OUT="$(install_run "$AROOT" "$MOCK_CUSTOMER_SLUG" --confirm 2>&1)"
RC=$?
[ "$RC" -ne 0 ] && pass || fail "raw ANTHROPIC_API_KEY must FAIL the install (got exit 0)"
printf '%s' "$OUT" | grep -qiF "VALIDATION FAIL" && pass || fail "ANTHROPIC-absent gate should print VALIDATION FAIL"

# ════════════════════════════════════════════════════════════════════════════════
section "§G — idempotent re-run (no duplicate keys)"
IROOT="$TMP/idem-root"
install_run "$IROOT" "$MOCK_CUSTOMER_SLUG" --confirm >/dev/null 2>&1
install_run "$IROOT" "$MOCK_CUSTOMER_SLUG" --confirm >/dev/null 2>&1
CNT="$(grep -c "^LLM_PROXY_KEY=" "$IROOT/cabinet/.env" 2>/dev/null || echo 99)"
[ "$CNT" -eq 1 ] && pass || fail "re-run duplicated LLM_PROXY_KEY (count=$CNT, expect 1)"

# ── Summary ───────────────────────────────────────────────────────────────────
printf '\n════════════════════════════════════════════════════════════════════\n'
printf '  FW-098 / Spec 053 v4.1 — install-customer-cabinet harness\n'
printf '  PASS: %d   FAIL: %d   TOTAL: %d\n' "$PASS" "$FAIL" "$((PASS + FAIL))"
[ "$FAIL" -gt 0 ] && printf '\nFailed:\n%b\n' "$FAILURES"
printf '════════════════════════════════════════════════════════════════════\n'
[ "$FAIL" -eq 0 ]
