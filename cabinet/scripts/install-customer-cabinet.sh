#!/usr/bin/env bash
# cabinet/scripts/install-customer-cabinet.sh — FW-098 concierge install orchestrator
#
# Implements Spec 053 v4.1 Stage 4 "substrate execution" — the automation the Captain
# runs on the customer's Mac during the Day-0 concierge install. This is the COMMERCIAL
# CONCIERGE WRAPPER: it adds the commercial layer (install-token validation, customer
# secret injection, officer-mix spawn, first-boot validation) and DELEGATES generic
# new-cabinet stack provisioning to cabinet-bootstrap.sh (FW-082) — no duplication.
#
# USAGE:
#   install-customer-cabinet.sh <customer-slug> [--dry-run] [--confirm]
#     (no flag)  SAFE MODE — print the plan, mutate nothing. Exit 0.
#     --dry-run  explicit alias for safe mode.
#     --confirm  execute the install. Exit 0 on success, 1 on any failure (fail-closed).
#
# SECRETS (env inputs — pre-provisioned by Captain / FW-096 admin per runbook §0;
#          this script INJECTS them, it does NOT mint them. Values are NEVER echoed):
#   REFSLUND_INSTALL_TOKEN  (required) customer's signed JWT: customer_id + employee_count + tier
#   LLM_PROXY_KEY           (required) customer's LiteLLM virtual key (FW-096)
#   AUDIT_API_KEY           (required) audit-server key (FW-097 / Spec 052 CTO #5)
#   TELEGRAM_CEO_TOKEN      (required) single-CEO bot token (FW-084); written under the
#                                      per-customer key TELEGRAM_<UPPER_SLUG>_CEO_TOKEN
#   STRIPE_WEBHOOK_SECRET   (optional) Stripe webhook secret (FW-099 — may be unset Phase-1)
#
# CONFIG / TEST env (all overridable for hermetic testing):
#   CABINET_INSTALL_ROOT    where the framework lives (default: $HOME/cabinet)
#   CABINET_FRAMEWORK_REPO  clone source (default: https://github.com/nate-step/captains-cabinet.git)
#   CABINET_PRESET          preset for bootstrap (default: work)
#   INSTALL_SKIP_CLONE      if set, skip the git clone (idempotent / test)
#   INSTALL_SKIP_BOOTSTRAP  if set, skip the real cabinet-bootstrap.sh call (test)
#   INSTALL_SKIP_OFFICERS   if set, skip officer spawn (test / Phase-1 manual)
#
# PHASE-1 HONEST STUBS (documented, not over-promised — cf. FW-100 CTO #3 discipline):
#   - Install-token validation is LOCAL ONLY (structure + expiry + required claims). The
#     runbook's "validate against the LiteLLM proxy" needs a proxy token-validate endpoint
#     that FW-096 does not expose yet — TODO when it lands. NO cryptographic signature
#     verification Phase-1; the local decode is a sanity gate, not an auth boundary.
#   - Officer-mix spawn is best-effort; create-officer.sh may need interactive input, so
#     Phase-1 prints the hire commands when it cannot run them non-interactively.
#
# SECURITY (FW-100 lessons applied):
#   - customer-slug is validated as a strict slug BEFORE any interpolation into paths /
#     bootstrap args / .env writes (no injection surface).
#   - Secret VALUES are never echoed (stdout, dry-run, or logs) — only presence + length.
#   - The secrets .env is chmod 600. The git clone uses GIT_ASKPASS (PAT never in argv).
#   - first-boot validation FAILS the install if a raw ANTHROPIC_API_KEY is present in
#     cabinet/.env — that would bypass the proxy (and thus the $50/day cap + the audit log).

set -uo pipefail

CABINET_ROOT_SELF="${CABINET_ROOT:-/opt/founders-cabinet}"  # where THIS script's siblings live (for tests)
INSTALL_ROOT="${CABINET_INSTALL_ROOT:-$HOME/cabinet}"
FRAMEWORK_REPO="${CABINET_FRAMEWORK_REPO:-https://github.com/nate-step/captains-cabinet.git}"
PRESET="${CABINET_PRESET:-work}"

# ── Logging (secret-safe) ──────────────────────────────────────────────────────
log()  { echo "[install] $*"; }
info() { echo "[install] INFO:    $*"; }
warn() { echo "[install] WARNING: $*" >&2; }
die()  { echo "[install] ERROR:   $*" >&2; exit 1; }
step() { echo; echo "══════ $* ══════"; }
# secret_state <name> — report presence + length WITHOUT revealing the value.
secret_state() {
    local name="$1" val="${2:-}"
    if [ -n "$val" ]; then echo "set (${#val} chars)"; else echo "MISSING"; fi
}

# ── Parse args ──────────────────────────────────────────────────────────────────
CUSTOMER_SLUG=""
DRY_RUN=0
CONFIRM=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --confirm) CONFIRM=1 ;;
        --*)       warn "unknown flag '$arg' ignored" ;;
        *)         CUSTOMER_SLUG="$arg" ;;
    esac
done

[ -n "$CUSTOMER_SLUG" ] || die "Usage: install-customer-cabinet.sh <customer-slug> [--dry-run] [--confirm]"

# SECURITY (FW-100 BUG-1 lesson): validate the slug BEFORE it touches paths / bootstrap
# args / .env writes. Matches the cabinet-bootstrap.sh slug contract (^[a-z0-9][a-z0-9-]*$, ≤32).
if ! [[ "$CUSTOMER_SLUG" =~ ^[a-z0-9][a-z0-9-]*$ ]] || [ "${#CUSTOMER_SLUG}" -gt 32 ]; then
    die "invalid customer-slug '$CUSTOMER_SLUG' — must match ^[a-z0-9][a-z0-9-]*\$ and be ≤32 chars (matches cabinet-bootstrap.sh)."
fi

[ "$DRY_RUN" -eq 1 ] && CONFIRM=0
MUTATE=0
[ "$CONFIRM" -eq 1 ] && [ "$DRY_RUN" -eq 0 ] && MUTATE=1

UPPER_SLUG="$(echo "$CUSTOMER_SLUG" | tr 'a-z-' 'A-Z_')"
ENV_FILE="${INSTALL_ROOT}/cabinet/.env"
BOOTSTRAP="${INSTALL_ROOT}/cabinet/scripts/cabinet-bootstrap.sh"

# ── Plan header ──────────────────────────────────────────────────────────────────
echo
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Concierge Install — Commercial Cabinet (Spec 053 / FW-098)  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "  Customer slug : ${CUSTOMER_SLUG}"
echo "  Install root  : ${INSTALL_ROOT}"
echo "  Preset        : ${PRESET}"
echo "  Mode          : $([ "$MUTATE" -eq 1 ] && echo 'EXECUTE (--confirm)' || echo 'SAFE/DRY-RUN (pass --confirm to execute)')"
echo "  Secrets       : INSTALL_TOKEN=$(secret_state token "${REFSLUND_INSTALL_TOKEN:-}")  LLM_PROXY_KEY=$(secret_state k "${LLM_PROXY_KEY:-}")  AUDIT_API_KEY=$(secret_state k "${AUDIT_API_KEY:-}")  TELEGRAM_CEO_TOKEN=$(secret_state k "${TELEGRAM_CEO_TOKEN:-}")  STRIPE_WEBHOOK_SECRET=$(secret_state k "${STRIPE_WEBHOOK_SECRET:-}")"
echo

# ── Step 1: install-token validation (Phase-1 local: structure + expiry + claims) ──
step "Step 1 — install-token validation (Phase-1 local)"
TOKEN="${REFSLUND_INSTALL_TOKEN:-}"
[ -n "$TOKEN" ] || die "REFSLUND_INSTALL_TOKEN env var is required (customer's signed install JWT)."

# base64url-decode a JWT segment (pad to a multiple of 4; map -_ to +/).
_b64url_decode() {
    local seg="$1"
    local rem=$(( ${#seg} % 4 ))
    [ "$rem" -eq 2 ] && seg="${seg}=="
    [ "$rem" -eq 3 ] && seg="${seg}="
    local std; std="$(echo "$seg" | tr '_-' '/+')"
    # base64 decode flag differs by platform: GNU = -d, BSD/macOS = -D. This script
    # runs on the customer's Mac, so try both.
    printf '%s' "$std" | base64 -d 2>/dev/null || printf '%s' "$std" | base64 -D 2>/dev/null
}
# JWT = header.payload.signature — exactly 2 dots.
if [ "$(echo "$TOKEN" | tr -cd '.' | wc -c)" -ne 2 ]; then
    die "install token is not a well-formed JWT (expected header.payload.signature)."
fi
TOKEN_PAYLOAD="$(echo "$TOKEN" | cut -d. -f2)"
TOKEN_JSON="$(_b64url_decode "$TOKEN_PAYLOAD")"
[ -n "$TOKEN_JSON" ] || die "install token payload could not be base64url-decoded."
echo "$TOKEN_JSON" | jq -e . >/dev/null 2>&1 || die "install token payload is not valid JSON."

TOK_CUSTOMER_ID="$(echo "$TOKEN_JSON" | jq -r '.customer_id // empty')"
TOK_TIER="$(echo "$TOKEN_JSON" | jq -r '.tier // empty')"
TOK_EMPLOYEES="$(echo "$TOKEN_JSON" | jq -r '.employee_count // empty')"
TOK_EXP="$(echo "$TOKEN_JSON" | jq -r '.exp // empty')"
[ -n "$TOK_CUSTOMER_ID" ] || die "install token missing required claim: customer_id."
[ -n "$TOK_TIER" ]        || die "install token missing required claim: tier."
if [ -n "$TOK_EXP" ] && [[ "$TOK_EXP" =~ ^[0-9]+$ ]]; then
    if [ "$TOK_EXP" -lt "$(date -u +%s)" ]; then
        die "install token is EXPIRED (exp=${TOK_EXP}). Captain must re-issue from refslund.ai admin."
    fi
fi
log "Token OK (local check): customer_id=${TOK_CUSTOMER_ID} tier=${TOK_TIER} employee_count=${TOK_EMPLOYEES:-unset}"
warn "Phase-1: token signature NOT cryptographically verified (proxy token-validate endpoint is a FW-096 TODO). Local structure/expiry/claims gate only."

# ── Step 2: require secret inputs (presence only — never echo values) ──────────────
step "Step 2 — required secrets present"
MISSING=""
[ -n "${LLM_PROXY_KEY:-}" ]      || MISSING="${MISSING} LLM_PROXY_KEY"
[ -n "${AUDIT_API_KEY:-}" ]      || MISSING="${MISSING} AUDIT_API_KEY"
[ -n "${TELEGRAM_CEO_TOKEN:-}" ] || MISSING="${MISSING} TELEGRAM_CEO_TOKEN"
[ -z "$MISSING" ] || die "missing required secret env var(s):${MISSING}. Provision them (FW-096 virtual key, FW-097 audit key, BotFather token) before install."
[ -n "${STRIPE_WEBHOOK_SECRET:-}" ] || warn "STRIPE_WEBHOOK_SECRET not set — Stripe webhook wiring deferred (FW-099 not live Phase-1)."
log "All required secrets present (values redacted)."

if [ "$MUTATE" -eq 0 ]; then
    step "Plan only (no --confirm)"
    log "Would: clone framework to ${INSTALL_ROOT} (if absent), inject secrets into ${ENV_FILE} (chmod 600),"
    log "       run cabinet-bootstrap.sh ${CUSTOMER_SLUG} --preset ${PRESET}, spawn officer-mix, validate first-boot."
    log "Run with --confirm to execute."
    exit 0
fi

# ── Step 3: clone framework (idempotent; GIT_ASKPASS so PAT never hits argv/logs) ──
step "Step 3 — framework present at ${INSTALL_ROOT}"
if [ -n "${INSTALL_SKIP_CLONE:-}" ]; then
    log "INSTALL_SKIP_CLONE set — skipping clone (assuming framework already present)."
elif [ -d "${INSTALL_ROOT}/.git" ]; then
    log "Framework already cloned at ${INSTALL_ROOT} — skipping (idempotent)."
else
    log "Cloning framework → ${INSTALL_ROOT}"
    if [ -n "${GITHUB_PAT:-}" ]; then
        # Credential helper reads the PAT from env (never in argv / logs / reflog).
        GIT_TERMINAL_PROMPT=0 git -c credential.helper='!f() { echo username=x-access-token; echo "password=$GITHUB_PAT"; }; f' \
            clone --depth 1 "$FRAMEWORK_REPO" "$INSTALL_ROOT" >/dev/null 2>&1 || die "git clone failed."
    else
        git clone --depth 1 "$FRAMEWORK_REPO" "$INSTALL_ROOT" >/dev/null 2>&1 || die "git clone failed (no GITHUB_PAT; public clone also failed)."
    fi
    log "Clone complete."
fi

# ── Step 4: inject secrets into cabinet/.env (values never echoed; chmod 600) ──────
step "Step 4 — inject secrets into ${ENV_FILE}"
mkdir -p "$(dirname "$ENV_FILE")" || die "could not create $(dirname "$ENV_FILE")."
touch "$ENV_FILE" || die "could not create ${ENV_FILE}."
chmod 600 "$ENV_FILE" || die "could not chmod 600 ${ENV_FILE}."
# env_upsert <KEY> <VALUE> — replace the KEY= line if present else append; writes the
# value straight to the file (never to stdout). Atomic via temp + mv.
env_upsert() {
    local key="$1" value="$2" tmp
    # BUG-1 (Opus review): refuse a newline/CR in any injected value — it would plant an
    # arbitrary extra cabinet/.env line (e.g. a raw ANTHROPIC_API_KEY that bypasses the
    # first-boot gate) and break idempotency. Also guards the install-token write (line below).
    case "$value" in
        *$'\n'*|*$'\r'*) die "refusing to inject ${key}: value contains a newline/CR (would corrupt cabinet/.env)." ;;
    esac
    tmp="$(mktemp)"
    grep -v "^${key}=" "$ENV_FILE" > "$tmp" 2>/dev/null || true
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
    mv "$tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    log "  injected ${key} (redacted)"
}
env_upsert "LLM_PROXY_KEY"               "${LLM_PROXY_KEY}"
env_upsert "AUDIT_API_KEY"               "${AUDIT_API_KEY}"
env_upsert "TELEGRAM_${UPPER_SLUG}_CEO_TOKEN" "${TELEGRAM_CEO_TOKEN}"
env_upsert "REFSLUND_INSTALL_TOKEN"      "${TOKEN}"
[ -n "${STRIPE_WEBHOOK_SECRET:-}" ] && env_upsert "STRIPE_WEBHOOK_SECRET" "${STRIPE_WEBHOOK_SECRET}"
log "Secrets injected; ${ENV_FILE} mode is $(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%Lp' "$ENV_FILE" 2>/dev/null)."

# ── Step 5: delegate stack provisioning to cabinet-bootstrap.sh (FW-082) ──────────
step "Step 5 — stack provisioning (delegate to cabinet-bootstrap.sh)"
if [ -n "${INSTALL_SKIP_BOOTSTRAP:-}" ]; then
    log "INSTALL_SKIP_BOOTSTRAP set — skipping real bootstrap call."
elif [ -x "$BOOTSTRAP" ]; then
    log "Running: cabinet-bootstrap.sh ${CUSTOMER_SLUG} --preset ${PRESET}"
    bash "$BOOTSTRAP" "$CUSTOMER_SLUG" --preset "$PRESET" || die "cabinet-bootstrap.sh failed for ${CUSTOMER_SLUG}. Secrets remain in ${ENV_FILE} (mode 600) — rerun the install or remove the file."
    log "Stack provisioned."
else
    die "cabinet-bootstrap.sh not found/executable at ${BOOTSTRAP}."
fi

# ── Step 6: spawn officer-mix (best-effort; print hire commands if non-interactive fails) ──
step "Step 6 — officer-mix spawn"
if [ -n "${INSTALL_SKIP_OFFICERS:-}" ]; then
    log "INSTALL_SKIP_OFFICERS set — skipping officer spawn."
else
    log "Phase-1: hire the CEO officer (single-CEO bot model, FW-084) + the customer's chosen roster."
    log "  Run on the customer Mac: bash ${INSTALL_ROOT}/cabinet/scripts/start-officer.sh <role>  (per chosen mix)"
    log "  (employee_count from token: ${TOK_EMPLOYEES:-unset}; officer-mix wizard is FW-103/Phase-2)"
fi

# ── Step 7: first-boot validation ────────────────────────────────────────────────
step "Step 7 — first-boot validation"
EXIT_CODE=0
# SECURITY: a raw ANTHROPIC_API_KEY in cabinet/.env would bypass the proxy (→ no $50/day
# cap, no audit log). All LLM traffic MUST flow through the proxy via LLM_PROXY_KEY.
# Scope: cabinet/.env ONLY (Spec 053 053-04 — customer's own ~/.env is out of scope).
# BUG-2 (Opus review): tolerate leading whitespace, an `export ` prefix, and case — a dotenv
# loader honors all of these, so a narrow ^ANTHROPIC_API_KEY= anchor is a weak gate.
if grep -qiE '^[[:space:]]*(export[[:space:]]+)?ANTHROPIC_API_KEY[[:space:]]*=' "$ENV_FILE"; then
    warn "VALIDATION FAIL: raw ANTHROPIC_API_KEY present in ${ENV_FILE} — this bypasses the proxy cap + audit. Remove it; officers must use LLM_PROXY_KEY only."
    EXIT_CODE=1
else
    log "OK: no raw ANTHROPIC_API_KEY in cabinet/.env (LLM traffic routes through the proxy)."
fi
# Sanity: the injected keys are present.
for k in LLM_PROXY_KEY AUDIT_API_KEY "TELEGRAM_${UPPER_SLUG}_CEO_TOKEN"; do
    grep -q "^${k}=" "$ENV_FILE" || { warn "VALIDATION FAIL: ${k} missing from ${ENV_FILE} after injection."; EXIT_CODE=1; }
done

# ── Summary ──────────────────────────────────────────────────────────────────────
echo
if [ "$EXIT_CODE" -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Install substrate complete — ${CUSTOMER_SLUG}"
    echo "╚══════════════════════════════════════════════════════════════╝"
    log "Next (runbook §1.5-1.7): customer pastes BotFather token, start officers, confirm Telegram round-trip, dashboard + GDPR walkthrough."
else
    warn "Install completed WITH VALIDATION FAILURES (see above) — do NOT hand off until resolved."
fi
exit "$EXIT_CODE"
