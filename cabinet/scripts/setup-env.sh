#!/bin/bash
# setup-env.sh — interactive wizard for cabinet/.env
#
# Replaces the manual "edit cabinet/.env in a text editor" step. Walks the
# Captain through each required + optional API key, opening signup URLs
# in the browser, validating where cheap to do so, and writing
# cabinet/.env with chmod 600.
#
# Modes:
#   (no args)        Interactive wizard. Skips keys already filled.
#   --check          Validate cabinet/.env, exit 0 if all critical present,
#                    exit 1 if any critical key missing. No writes.
#   --force          Re-prompt for keys even if already filled.
#   --keychain       Mirror keys to macOS Keychain after writing .env.
#                    Future: officers can read from Keychain instead of .env.
#   --help, -h       Print this help.
#
# Captain UX per key:
#   - Read description + which officer uses it
#   - Press 'o' to open signup URL in browser
#   - Press 'p' to paste key (masked input)
#   - Press 's' to skip (with consequence note for critical keys)
#
# Idempotent: re-running picks up where you left off. Existing keys
# survive unless --force.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Script lives at cabinet/scripts/, so repo root is TWO levels up (R4/R5 pattern).
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ENV_FILE="$CABINET_ROOT/cabinet/.env"
ENV_EXAMPLE="$CABINET_ROOT/cabinet/.env.example"

MODE="interactive"
USE_KEYCHAIN=0
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check"; shift ;;
    --force) FORCE=1; shift ;;
    --keychain) USE_KEYCHAIN=1; shift ;;
    --help|-h)
      sed -n '1,30p' "$0" | sed 's/^# \{0,1\}//' >&2
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 64 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
info() { echo -e "  ${BLUE}[i]${NC} $1"; }

# Ensure .env exists (copy from .env.example if not). In --check mode,
# DO NOT create the file — we want --check to report missing-keys honestly,
# not paper over the absence by initializing an empty template.
if [ ! -f "$ENV_FILE" ]; then
  if [ "$MODE" = "check" ]; then
    fail "$ENV_FILE does not exist"
    echo "  Run: bash cabinet/scripts/setup-env.sh"
    exit 1
  fi
  if [ ! -f "$ENV_EXAMPLE" ]; then
    echo "setup-env: $ENV_EXAMPLE not found" >&2
    exit 1
  fi
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  info "Created $ENV_FILE from template"
fi

# chmod 600 always (in case re-run on a worktree where the file was looser)
chmod 600 "$ENV_FILE"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Read current value of KEY=... from .env. Empty string if unset.
current_value() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | sed "s/^${key}=//; s/^\"//; s/\"$//"
}

# Update KEY=value in .env. Adds line if KEY doesn't exist.
set_env_key() {
  local key="$1" value="$2"
  local tmp; tmp="$(mktemp)"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    # Use awk so we don't need GNU sed escapes for values with /
    awk -v k="$key" -v v="$value" \
      'BEGIN { FS="="; OFS="=" } $1 == k { print k "=" v; next } { print }' \
      "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"
    echo "${key}=${value}" >> "$tmp"
  fi
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"

  if [ "$USE_KEYCHAIN" = "1" ] && [ -n "$value" ]; then
    # Mirror to macOS Keychain (service=captains-cabinet, account=$KEY)
    security delete-generic-password -s "captains-cabinet" -a "$key" >/dev/null 2>&1 || true
    security add-generic-password -s "captains-cabinet" -a "$key" -w "$value" -U >/dev/null 2>&1 \
      && info "Mirrored $key → macOS Keychain"
  fi
}

# Prompt user for a key. Args: key, description, signup_url, tier, used_by
prompt_key() {
  local key="$1" desc="$2" url="$3" tier="$4" used_by="$5"
  local existing
  existing="$(current_value "$key")"

  # Skip if already set + not forcing
  if [ -n "$existing" ] && [ "$FORCE" = "0" ]; then
    ok "$key already set (skipping; use --force to re-prompt)"
    return 0
  fi

  echo ""
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BLUE}$key${NC}  [$tier]"
  echo "  $desc"
  echo "  Used by: $used_by"
  if [ -n "$url" ]; then
    echo "  Signup:  $url"
  fi
  echo ""

  while true; do
    if [ "$tier" = "CRITICAL" ]; then
      echo -n "  (p)aste key / (o)pen signup URL / (s)kip [p/o/s]: "
    else
      echo -n "  (p)aste key / (o)pen signup URL / (s)kip [p/o/s, default=skip]: "
    fi
    read -r choice
    [ -z "$choice" ] && [ "$tier" != "CRITICAL" ] && choice="s"
    case "$choice" in
      p|P)
        echo -n "  Paste $key (input hidden): "
        read -rs value
        echo ""
        if [ -z "$value" ]; then
          warn "Empty value; not saving"
          continue
        fi
        set_env_key "$key" "$value"
        ok "$key saved to $ENV_FILE"
        return 0
        ;;
      o|O)
        if [ -n "$url" ]; then
          open "$url" 2>/dev/null && info "Opened $url"
        else
          warn "No signup URL configured for $key"
        fi
        # Loop back to prompt
        ;;
      s|S|"")
        if [ "$tier" = "CRITICAL" ]; then
          warn "$key is CRITICAL — Cabinet may not function without it. Skip anyway? (y/N): "
          read -r confirm
          if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            continue
          fi
        fi
        warn "Skipped $key"
        return 0
        ;;
      *)
        warn "Unknown choice: $choice"
        ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# Mode: --check
# ---------------------------------------------------------------------------

CRITICAL_KEYS=(
  TELEGRAM_HQ_CHAT_ID
  CAPTAIN_TELEGRAM_ID
  TELEGRAM_COS_TOKEN
  GITHUB_PAT
  NEON_CONNECTION_STRING
)

RECOMMENDED_KEYS=(
  ANTHROPIC_API_KEY
  VOYAGE_API_KEY
  NOTION_API_KEY
)

if [ "$MODE" = "check" ]; then
  missing_critical=()
  missing_recommended=()
  for k in "${CRITICAL_KEYS[@]}"; do
    v="$(current_value "$k")"
    [ -z "$v" ] && missing_critical+=("$k")
  done
  for k in "${RECOMMENDED_KEYS[@]}"; do
    v="$(current_value "$k")"
    [ -z "$v" ] && missing_recommended+=("$k")
  done

  echo "==========================================="
  echo "  cabinet/.env validation"
  echo "==========================================="
  if [ "${#missing_critical[@]}" -eq 0 ]; then
    ok "All ${#CRITICAL_KEYS[@]} critical keys present"
  else
    fail "Missing critical: ${missing_critical[*]}"
  fi
  if [ "${#missing_recommended[@]}" -eq 0 ]; then
    ok "All ${#RECOMMENDED_KEYS[@]} recommended keys present"
  else
    warn "Missing recommended: ${missing_recommended[*]}"
  fi
  echo ""
  if [ "${#missing_critical[@]}" -gt 0 ]; then
    echo "  Run: bash cabinet/scripts/setup-env.sh"
    exit 1
  fi
  exit 0
fi

# ---------------------------------------------------------------------------
# Mode: interactive wizard
# ---------------------------------------------------------------------------

echo "==========================================="
echo "  Cabinet — API key setup wizard"
echo "==========================================="
echo ""
echo "  Walks you through the API keys the Cabinet needs. For each:"
echo "    - You'll see what it's for + which officer uses it."
echo "    - Press 'o' to open the signup page in your browser."
echo "    - Press 'p' to paste the key (input is hidden)."
echo "    - Press 's' to skip (optional keys default to skip)."
echo ""
echo "  Keys already filled in cabinet/.env are skipped automatically."
echo "  Re-run with --force to re-prompt for every key."
if [ "$USE_KEYCHAIN" = "1" ]; then
  echo "  Mirror-to-Keychain enabled (--keychain). Keys also stored in"
  echo "  macOS Keychain under service 'captains-cabinet'."
fi
echo ""

# ──────────────────────────────────────────────────────────────────────────
# SECTION 1 — Critical (Cabinet won't boot without these)
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 1 — Critical (required for boot)"
echo "═══════════════════════════════════════════════════════"

prompt_key "CAPTAIN_TELEGRAM_ID" \
  "Your personal Telegram user ID (numeric). Officers verify it's you on incoming DMs." \
  "https://t.me/userinfobot" \
  "CRITICAL" \
  "all officers (default-deny on inbound DMs)"

prompt_key "TELEGRAM_HQ_CHAT_ID" \
  "The Cabinet's warroom group chat ID (negative number, e.g. -100xxxxxxxxxx). Officers broadcast updates here." \
  "https://t.me/userinfobot" \
  "CRITICAL" \
  "CoS for daily briefings + broadcast updates"

for officer_token in TELEGRAM_COS_TOKEN TELEGRAM_CTO_TOKEN TELEGRAM_CPO_TOKEN TELEGRAM_CRO_TOKEN TELEGRAM_COO_TOKEN; do
  officer_slug="$(echo "$officer_token" | sed 's/TELEGRAM_//; s/_TOKEN//' | tr '[:upper:]' '[:lower:]')"
  tier="CRITICAL"
  [ "$officer_slug" != "cos" ] && tier="RECOMMENDED"
  prompt_key "$officer_token" \
    "Telegram bot token for officer '$officer_slug' (one bot per officer for clean per-officer DM threading)." \
    "https://t.me/BotFather" \
    "$tier" \
    "$officer_slug"
done

prompt_key "GITHUB_PAT" \
  "GitHub Personal Access Token. Used by the github-issues task adapter (cabinet default backlog) + gh CLI for repo ops." \
  "https://github.com/settings/tokens/new?scopes=repo,workflow,read:org&description=captains-cabinet" \
  "CRITICAL" \
  "CTO (repo ops), CPO (issue triage)"

prompt_key "NEON_CONNECTION_STRING" \
  "Postgres connection string. Drives org_events ledger, cabinet_memory (pgvector), mission/role state." \
  "https://console.neon.tech/" \
  "CRITICAL" \
  "all officers (durable state); CoS most"

# ──────────────────────────────────────────────────────────────────────────
# SECTION 2 — Strongly recommended (cabinet works without but degraded)
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 2 — Strongly recommended"
echo "═══════════════════════════════════════════════════════"

prompt_key "ANTHROPIC_API_KEY" \
  "Anthropic API key. Drives the cua MCP server (native Mac GUI control) when CUA_MODEL_BACKEND=anthropic. Skip if using Max OAuth + you don't need native Mac apps." \
  "https://console.anthropic.com/settings/keys" \
  "RECOMMENDED" \
  "cua (native Mac control); officer fallback when Max OAuth misroutes"

prompt_key "VOYAGE_API_KEY" \
  "Voyage AI key for cabinet_memory embeddings (voyage-4-large, 1024d). Without this, the semantic recall layer doesn't work — keyword retrieval still does." \
  "https://dash.voyageai.com/" \
  "RECOMMENDED" \
  "CoS (Captain DM recall), CRO (research embeddings)"

prompt_key "NOTION_API_KEY" \
  "Notion internal integration token. Cabinet reads strategy/brand/vision docs + writes research briefs + officer specs here." \
  "https://www.notion.so/my-integrations" \
  "RECOMMENDED" \
  "CoS (briefings), CRO (research), CPO (specs)"

# ──────────────────────────────────────────────────────────────────────────
# SECTION 3 — Task system (pick ONE)
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 3 — Task system (pick the one you actually use)"
echo "═══════════════════════════════════════════════════════"
echo ""
info "Cabinet syncs mission work-graph nodes to your existing task system."
info "Pick ONE — skip the others. Linear is the default if unsure."

prompt_key "LINEAR_API_KEY" \
  "Linear API key. Default Cabinet task system." \
  "https://linear.app/settings/api" \
  "RECOMMENDED" \
  "CPO (backlog), CTO (issue ops), CoS (cross-officer)"

prompt_key "MONDAY_API_KEY" \
  "Monday.com API key. Use if your team is on monday.com instead of Linear." \
  "https://developer.monday.com/api-reference/docs/authentication" \
  "OPTIONAL" \
  "CPO (if monday board is your backlog)"

prompt_key "JIRA_API_KEY" \
  "Jira API key. Use if your team is on Jira." \
  "https://id.atlassian.com/manage-profile/security/api-tokens" \
  "OPTIONAL" \
  "CPO"

prompt_key "ASANA_API_KEY" \
  "Asana API key." \
  "https://app.asana.com/0/my-apps" \
  "OPTIONAL" \
  "CPO"

# ──────────────────────────────────────────────────────────────────────────
# SECTION 4 — Research APIs (CRO — connect when first research outcome ratified)
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 4 — Research APIs (defer unless CRO is active)"
echo "═══════════════════════════════════════════════════════"
echo ""
info "These power the CRO research sweep. Skip on first setup; connect"
info "when a research outcome is ratified."

prompt_key "PERPLEXITY_API_KEY" \
  "Perplexity API. Best general-purpose web research." \
  "https://www.perplexity.ai/settings/api" \
  "OPTIONAL" \
  "CRO research sweep"

prompt_key "EXA_API_KEY" \
  "Exa (formerly Metaphor). Semantic search across the web." \
  "https://dashboard.exa.ai/" \
  "OPTIONAL" \
  "CRO competitive intel"

prompt_key "BRAVE_SEARCH_API_KEY" \
  "Brave Search API. Privacy-respecting backup search." \
  "https://api.search.brave.com/" \
  "OPTIONAL" \
  "CRO (search fallback)"

prompt_key "GOOGLE_API_KEY" \
  "Google AI Studio key. Drives Gemini text/vision API + Nano Banana (Gemini 2.5 Flash Image generation). Single key for both. Cheapest image gen on the market." \
  "https://aistudio.google.com/apikey" \
  "OPTIONAL" \
  "CRO (Gemini search/vision), any officer (Nano Banana image gen)"

# ──────────────────────────────────────────────────────────────────────────
# SECTION 5 — Product integrations (defer until outcome demands)
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 5 — Product integrations (connect when needed)"
echo "═══════════════════════════════════════════════════════"
echo ""
info "Skip these on first setup. Connect only when an outcome demands them."

prompt_key "VERCEL_TOKEN" \
  "Vercel API token. Cabinet uses it to verify deploys + read build logs." \
  "https://vercel.com/account/tokens" \
  "OPTIONAL" \
  "CTO (deploy), COO (validate)"

prompt_key "SENTRY_DSN" \
  "Sentry DSN (project-level)." \
  "https://docs.sentry.io/concepts/key-terms/dsn-explainer/" \
  "OPTIONAL" \
  "COO error triage"

prompt_key "SENTRY_AUTH_TOKEN" \
  "Sentry auth token (for API queries). Same project as DSN above." \
  "https://docs.sentry.io/api/auth/" \
  "OPTIONAL" \
  "COO error triage"

prompt_key "POSTHOG_API_KEY" \
  "PostHog API key. Use when the product has real users to analyze." \
  "https://app.posthog.com/settings/project-details#variables" \
  "OPTIONAL" \
  "CRO (product analytics), CPO (feature usage)"

prompt_key "MAPBOX_TOKEN" \
  "Mapbox token. Only needed if the product uses maps." \
  "https://account.mapbox.com/access-tokens/" \
  "OPTIONAL" \
  "(product-specific)"

# ──────────────────────────────────────────────────────────────────────────
# SECTION 6 — Optional alt-providers + media
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 6 — Optional alternates"
echo "═══════════════════════════════════════════════════════"

prompt_key "OPENAI_API_KEY" \
  "OpenAI API. Optional alternate for cua backend (CUA_MODEL_BACKEND=openai) or Stagehand model. Skip if fully on Anthropic." \
  "https://platform.openai.com/api-keys" \
  "OPTIONAL" \
  "cua (alt backend)"

prompt_key "ELEVENLABS_API_KEY" \
  "ElevenLabs voice generation. Powers the post-reply-voice.sh hook which sends voice messages on Telegram. Skip if Captain prefers text-only." \
  "https://elevenlabs.io/app/settings/api-keys" \
  "OPTIONAL" \
  "all officers (Captain DM replies)"

# ──────────────────────────────────────────────────────────────────────────
# SECTION 7 — Cabinet runtime (auto-generate sensible defaults)
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 7 — Cabinet runtime defaults"
echo "═══════════════════════════════════════════════════════"

# Auto-generate dashboard password if empty
existing="$(current_value "DASHBOARD_PASSWORD")"
if [ -z "$existing" ] || [ "$existing" = "changeme" ] || [ "$existing" = "changeme_secure_password" ]; then
  GEN_PWD="$(openssl rand -base64 24 2>/dev/null | tr -d '/+=' | head -c 24)"
  if [ -n "$GEN_PWD" ]; then
    set_env_key "DASHBOARD_PASSWORD" "$GEN_PWD"
    ok "DASHBOARD_PASSWORD auto-generated (24 chars, base64)"
  fi
else
  ok "DASHBOARD_PASSWORD already set"
fi

# Auto-generate postgres password if empty (cabinet sidecar PG, not Neon)
existing="$(current_value "POSTGRES_PASSWORD")"
if [ -z "$existing" ]; then
  GEN_PWD="$(openssl rand -base64 32 2>/dev/null | tr -d '/+=' | head -c 32)"
  if [ -n "$GEN_PWD" ]; then
    set_env_key "POSTGRES_PASSWORD" "$GEN_PWD"
    ok "POSTGRES_PASSWORD auto-generated (32 chars, base64) — only used if running cabinet PG sidecar"
  fi
fi

# ──────────────────────────────────────────────────────────────────────────
# Final summary
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "==========================================="
echo "  cabinet/.env wizard complete."
echo "==========================================="
echo ""
chmod 600 "$ENV_FILE"
ok "$ENV_FILE permissions: 600 (Captain only)"

# Re-check critical keys
missing_critical=()
for k in "${CRITICAL_KEYS[@]}"; do
  v="$(current_value "$k")"
  [ -z "$v" ] && missing_critical+=("$k")
done
if [ "${#missing_critical[@]}" -eq 0 ]; then
  ok "All ${#CRITICAL_KEYS[@]} critical keys filled — Cabinet can boot"
else
  warn "Still missing critical: ${missing_critical[*]}"
  warn "Cabinet may not boot. Re-run: bash cabinet/scripts/setup-env.sh"
fi

if [ "$USE_KEYCHAIN" = "1" ]; then
  ok "All set keys mirrored to macOS Keychain (service=captains-cabinet)"
fi

echo ""
echo "  Next: bash cabinet/scripts/setup-mac.sh   (full Mac mini setup)"
echo "==========================================="
