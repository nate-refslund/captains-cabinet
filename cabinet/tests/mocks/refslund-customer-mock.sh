#!/usr/bin/env bash
# cabinet/tests/mocks/refslund-customer-mock.sh — shared mock commercial customer (Spec 053 CTO #5).
#
# SOURCE this file (do not execute). It provides a single mock refslund.ai customer
# (slug + install token + fake secrets) so the Spec 051/052/053/055 test harnesses do
# not each re-invent one. ~80 lines avoiding 5x duplication.
#
# Provides (overridable before sourcing):
#   MOCK_CUSTOMER_SLUG MOCK_CUSTOMER_ID MOCK_TIER MOCK_EMPLOYEE_COUNT
#   MOCK_LLM_PROXY_KEY MOCK_AUDIT_API_KEY MOCK_TELEGRAM_CEO_TOKEN MOCK_STRIPE_WEBHOOK_SECRET
#   mock_install_token [exp_epoch]   -> echoes a JWT-structured install token (default far-future exp)
#   mock_install_token_payload <json> -> echoes a JWT with a caller-supplied payload JSON (edge cases)
#
# All secret values are CLEARLY FAKE. They are safe to appear in test fixtures; a harness
# that asserts "no secret leaked to stdout" greps for these exact values in script output.

MOCK_CUSTOMER_SLUG="${MOCK_CUSTOMER_SLUG:-mock-refslund-co}"
MOCK_CUSTOMER_ID="${MOCK_CUSTOMER_ID:-cust_mock_0001}"
MOCK_TIER="${MOCK_TIER:-base}"
MOCK_EMPLOYEE_COUNT="${MOCK_EMPLOYEE_COUNT:-3}"

MOCK_LLM_PROXY_KEY="${MOCK_LLM_PROXY_KEY:-sk-mock-proxy-deadbeef0001}"
MOCK_AUDIT_API_KEY="${MOCK_AUDIT_API_KEY:-mock-audit-key-cafef00d0002}"
MOCK_TELEGRAM_CEO_TOKEN="${MOCK_TELEGRAM_CEO_TOKEN:-1234567:MOCK-ceo-bot-token-0003}"
MOCK_STRIPE_WEBHOOK_SECRET="${MOCK_STRIPE_WEBHOOK_SECRET:-whsec_mock_stripe_0004}"

# base64url encode (portable: strip GNU line-wrap + '=' padding, map +/ -> -_)
_mock_b64url() { printf '%s' "$1" | base64 | tr -d '\n=' | tr '+/' '-_'; }

# mock_install_token_payload <payload-json> — JWT-structured header.payload.sig.
# Phase-1 install validation only does a LOCAL decode (no signature verification), so the
# signature is a fixed placeholder; harnesses exercise structure/claims/expiry only.
mock_install_token_payload() {
    local payload_json="$1" header payload
    header="$(_mock_b64url '{"alg":"HS256","typ":"JWT"}')"
    payload="$(_mock_b64url "$payload_json")"
    printf '%s.%s.%s' "$header" "$payload" "mocksig"
}

# mock_install_token [exp_epoch] — a valid mock install token (default exp far future).
mock_install_token() {
    local exp="${1:-9999999999}"
    mock_install_token_payload "{\"customer_id\":\"${MOCK_CUSTOMER_ID}\",\"tier\":\"${MOCK_TIER}\",\"employee_count\":${MOCK_EMPLOYEE_COUNT},\"exp\":${exp}}"
}
