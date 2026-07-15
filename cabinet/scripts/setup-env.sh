#!/bin/bash
# setup-env.sh — interactive wizard for cabinet/.env
#
# Replaces the manual "edit cabinet/.env in a text editor" step. Walks the
# Captain through each key, opening signup URLs in the browser, validating
# where cheap to do so (Telegram tokens get a LIVE getMe check), and
# writing cabinet/.env with chmod 600.
#
# De-cloud doctrine (2026-07-09): NO key here is boot-critical. The Cabinet
# boots with zero cloud accounts — work store defaults to LOCAL PostgreSQL
# 16 + pgvector (provisioned by setup-mac.sh / provision-local-postgres.sh),
# the canonical task board is LOCAL, and Telegram is a post-boot errand
# ("connect after your first briefing" — boot warns-and-continues
# Telegram-dark). Every key is recommended or optional.
#
# Modes:
#   (no args)        Interactive wizard. Skips keys already filled.
#   --defaults       Non-interactive: write a minimal cabinet/.env with
#                    local defaults + auto-generated values only
#                    (DASHBOARD_PASSWORD, POSTGRES_PASSWORD,
#                    TELEGRAM_WEBHOOK_SECRET); leaves all
#                    optional keys unset. Exit 0. Used by setup-mac.sh when
#                    stdin is not a TTY (hatch engine / CI).
#   --check          Validate cabinet/.env: exit 1 only if the file is
#                    missing; otherwise report missing recommended keys as
#                    warnings and exit 0 (nothing cloud is boot-critical).
#   --force          Re-prompt for keys even if already filled.
#   --keychain       Mirror keys to macOS Keychain after writing .env.
#                    Future: officers can read from Keychain instead of .env.
#   --help, -h       Print this help.
#
# Captain UX per key:
#   - Read description + which officer uses it
#   - Press 'o' to open signup URL in browser
#   - Press 'p' to paste key (masked input; Telegram tokens live-validated)
#   - Press 's' to skip (the default — every key is skippable)
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
    --defaults) MODE="defaults"; shift ;;
    --force) FORCE=1; shift ;;
    --keychain) USE_KEYCHAIN=1; shift ;;
    # Self-maintaining help: print the leading comment block only (a numeric
    # sed range drifts when the header grows and leaks code lines).
    --help|-h)
      awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0" >&2
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
# DO NOT create the file — we want --check to report the absence honestly,
# not paper over it by initializing an empty template.
if [ ! -f "$ENV_FILE" ]; then
  if [ "$MODE" = "check" ]; then
    fail "$ENV_FILE does not exist"
    echo "  Run: bash cabinet/scripts/setup-env.sh   (or --defaults for local-only)"
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

# Live getMe validation for TELEGRAM_*_TOKEN pastes (errand E1). The token
# rides an env var NAME into the validator — never argv, never echoed.
# Return: 0 valid (validator prints the bot username), 1 rejected by
# Telegram, 2 network unreachable, 3 validator unavailable.
validate_telegram_token() {
  local value="$1"
  [ -f "$SCRIPT_DIR/telegram-validate-token.sh" ] || return 3
  local rc=0
  CABINET_TELEGRAM_TOKEN_CANDIDATE="$value" \
    bash "$SCRIPT_DIR/telegram-validate-token.sh" --env CABINET_TELEGRAM_TOKEN_CANDIDATE || rc=$?
  return "$rc"
}

# Prompt user for a key. Args: key, description, signup_url, tier, used_by
# Tiers: RECOMMENDED | OPTIONAL — nothing is critical; empty input = skip.
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
    echo -n "  (p)aste key / (o)pen signup URL / (s)kip [p/o/s, default=skip]: "
    read -r choice
    [ -z "$choice" ] && choice="s"
    case "$choice" in
      p|P)
        echo -n "  Paste $key (input hidden): "
        read -rs value
        echo ""
        if [ -z "$value" ]; then
          warn "Empty value; not saving"
          continue
        fi
        # Telegram bot tokens get a LIVE getMe check before saving (errand
        # E1): confirms the bot username to the Captain; the token itself is
        # never echoed anywhere.
        case "$key" in
          TELEGRAM_*_TOKEN)
            local vrc=0
            validate_telegram_token "$value" || vrc=$?
            if [ "$vrc" -eq 1 ]; then
              warn "Telegram rejected this token — NOT saved. Paste again, or skip."
              continue
            elif [ "$vrc" -eq 2 ]; then
              warn "Could not reach the Telegram API — saving UNVERIFIED (re-check later: bash cabinet/scripts/telegram-validate-token.sh --env $key)"
            elif [ "$vrc" -ge 3 ]; then
              warn "telegram-validate-token.sh not available — saving UNVERIFIED (validate later: bash cabinet/scripts/telegram-validate-token.sh --env $key)"
            fi
            ;;
        esac
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
      s|S)
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
# Tiers (de-cloud doctrine 2026-07-09): there is NO critical tier — the
# Cabinet boots with zero cloud accounts. Recommended = the connections a
# working deployment wants soon; everything else is optional.
# ---------------------------------------------------------------------------

RECOMMENDED_KEYS=(
  TELEGRAM_COS_TOKEN
  CAPTAIN_TELEGRAM_ID
  TELEGRAM_HQ_CHAT_ID
  GITHUB_PAT
  ANTHROPIC_API_KEY
  VOYAGE_API_KEY
  NOTION_API_KEY
)

# ---------------------------------------------------------------------------
# MCP env-var NAMES the Captain declared in the onboarding interview
# (instance/config/cabinet-init.answers.yml -> integrations.mcp_env_names).
# generate-instance.py validates these (UPPER_SNAKE, :345) but the wizard
# never read them, so a declared server's key silently went unasked. Here we
# fold them into the walk. READ-ONLY, NAMES ONLY (never values); any failure
# (no file / bad YAML / no python3.12) => empty, never crashes the wizard.
# Names already offered by an explicit prompt below are skipped; that skip set
# is derived from this script's own prompt_key call sites, so it cannot rot.
# ---------------------------------------------------------------------------
ANSWERS_FILE="$CABINET_ROOT/instance/config/cabinet-init.answers.yml"

_declared_mcp_env_names() {
  [ -f "$ANSWERS_FILE" ] || return 0
  command -v python3.12 >/dev/null 2>&1 || return 0
  python3.12 - "$ANSWERS_FILE" <<'PY' 2>/dev/null
import re, sys
try:
    import yaml
    d = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
except Exception:
    sys.exit(0)
if not isinstance(d, dict):
    sys.exit(0)
integ = d.get("integrations")
names = integ.get("mcp_env_names") if isinstance(integ, dict) else None
seen = set()
for n in names or []:
    # Same shape generate-instance.py enforces — guarantees shell-safe tokens.
    if isinstance(n, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", n) and n not in seen:
        seen.add(n)
        print(n)
PY
}

# Keys already offered by an explicit prompt_key "LITERAL" call in this script.
_statically_prompted() {
  grep -oE 'prompt_key "[A-Z][A-Z0-9_]*"' "${BASH_SOURCE[0]}" 2>/dev/null \
    | sed -E 's/.*"([^"]*)".*/\1/' | sort -u
}

# Populate once, before any mode branch needs it. Empty array is safe; every
# expansion below is length-guarded (macOS bash 3.2 + `set -u`).
MCP_ENV_NAMES=()
if [ -f "$ANSWERS_FILE" ]; then
  _static_set=" $(_statically_prompted | tr '\n' ' ') "
  while IFS= read -r _n; do
    [ -n "$_n" ] || continue
    case "$_static_set" in *" $_n "*) continue ;; esac
    MCP_ENV_NAMES+=("$_n")
  done < <(_declared_mcp_env_names)
fi

# Auto-generate runtime secrets that need no account anywhere. Shared by
# the interactive wizard tail and --defaults.
apply_runtime_defaults() {
  local existing GEN_PWD

  # Dashboard password
  existing="$(current_value "DASHBOARD_PASSWORD")"
  if [ -z "$existing" ] || [ "$existing" = "changeme" ] || [ "$existing" = "changeme_secure_password" ]; then
    GEN_PWD="$(openssl rand -base64 24 2>/dev/null | tr -d '/+=' | head -c 24)"
    if [ -n "$GEN_PWD" ]; then
      set_env_key "DASHBOARD_PASSWORD" "$GEN_PWD"
      ok "DASHBOARD_PASSWORD auto-generated (24 chars, base64)"
      info "To sign in, copy it securely: bash cabinet/scripts/dashboard-password.sh --copy"
    fi
  else
    ok "DASHBOARD_PASSWORD already set"
    info "To sign in, copy it securely: bash cabinet/scripts/dashboard-password.sh --copy"
  fi

  # Local postgres password (used by provision-local-postgres.sh for the
  # default LOCAL work store; harmless if you later paste a Neon string).
  existing="$(current_value "POSTGRES_PASSWORD")"
  if [ -z "$existing" ]; then
    GEN_PWD="$(openssl rand -base64 32 2>/dev/null | tr -d '/+=' | head -c 32)"
    if [ -n "$GEN_PWD" ]; then
      set_env_key "POSTGRES_PASSWORD" "$GEN_PWD"
      ok "POSTGRES_PASSWORD auto-generated (32 chars, base64) — used by the local PostgreSQL work store"
    fi
  else
    ok "POSTGRES_PASSWORD already set"
  fi

  # Telegram authenticates every webhook delivery with this local transport
  # secret. It is not a BotFather/account credential and is safe to generate
  # before Telegram is connected. The value is stored only in cabinet/.env
  # (chmod 600) and is never printed.
  existing="$(current_value "TELEGRAM_WEBHOOK_SECRET")"
  if [ -z "$existing" ]; then
    GEN_PWD="$(openssl rand -hex 32 2>/dev/null | head -c 64)"
    if [ -n "$GEN_PWD" ]; then
      set_env_key "TELEGRAM_WEBHOOK_SECRET" "$GEN_PWD"
      ok "Telegram webhook authentication secret generated (value not shown)"
    fi
  else
    ok "Telegram webhook authentication secret already set (value not shown)"
  fi
}

# ---------------------------------------------------------------------------
# Mode: --check
# ---------------------------------------------------------------------------

if [ "$MODE" = "check" ]; then
  missing_recommended=()
  for k in "${RECOMMENDED_KEYS[@]}"; do
    v="$(current_value "$k")"
    [ -z "$v" ] && missing_recommended+=("$k")
  done

  echo "==========================================="
  echo "  cabinet/.env validation"
  echo "==========================================="
  ok "cabinet/.env exists (nothing cloud is boot-critical — de-cloud doctrine)"
  if [ "${#missing_recommended[@]}" -eq 0 ]; then
    ok "All ${#RECOMMENDED_KEYS[@]} recommended keys present"
  else
    warn "Missing recommended (connect after your first briefing): ${missing_recommended[*]}"
  fi
  # MCP keys the Captain declared in the interview but hasn't filled yet.
  if [ "${#MCP_ENV_NAMES[@]}" -gt 0 ]; then
    mcp_missing=()
    for k in "${MCP_ENV_NAMES[@]}"; do
      v="$(current_value "$k")"
      [ -z "$v" ] && mcp_missing+=("$k")
    done
    if [ "${#mcp_missing[@]}" -eq 0 ]; then
      ok "All ${#MCP_ENV_NAMES[@]} declared MCP keys present"
    else
      warn "Declared MCP keys not yet set (from your interview): ${mcp_missing[*]}"
    fi
  fi
  if [ -z "$(current_value "NEON_CONNECTION_STRING")" ]; then
    info "Work store: local PostgreSQL default (provisioned by setup-mac.sh Step 3.5 / provision-local-postgres.sh)"
  else
    ok "Work store connection string set (value not shown)"
  fi
  echo ""
  exit 0
fi

# ---------------------------------------------------------------------------
# Mode: --defaults (non-interactive — local boot, zero cloud accounts)
# ---------------------------------------------------------------------------

if [ "$MODE" = "defaults" ]; then
  echo "==========================================="
  echo "  cabinet/.env — local defaults (non-interactive)"
  echo "==========================================="
  apply_runtime_defaults
  chmod 600 "$ENV_FILE"
  ok "$ENV_FILE permissions: 600 (Captain only)"
  info "All account keys left unset — the Cabinet boots without them:"
  info "  work store  → local PostgreSQL 16 + pgvector (setup-mac.sh Step 3.5)"
  info "  task board  → local (no external PM tool required)"
  info "  Telegram    → connect after your first briefing:"
  info "                bash cabinet/scripts/setup-env.sh          (paste bot token, live-validated)"
  info "                bash cabinet/scripts/telegram-capture-chat-id.sh --write  (capture your chat id)"
  echo ""
  exit 0
fi

# ---------------------------------------------------------------------------
# Mode: interactive wizard
# ---------------------------------------------------------------------------

echo "==========================================="
echo "  Cabinet — API key setup wizard"
echo "==========================================="
echo ""
echo "  Walks you through the keys the Cabinet can use. NOTHING here is"
echo "  required for boot — skip everything and the Cabinet still hatches"
echo "  (local work store, local task board, Telegram-dark). For each key:"
echo "    - You'll see what it's for + which officer uses it."
echo "    - Press 'o' to open the signup page in your browser."
echo "    - Press 'p' to paste the key (input is hidden)."
echo "    - Press 's' (or just Enter) to skip."
echo ""
echo "  Keys already filled in cabinet/.env are skipped automatically."
echo "  Re-run with --force to re-prompt for every key."
if [ "$USE_KEYCHAIN" = "1" ]; then
  echo "  Mirror-to-Keychain enabled (--keychain). Keys also stored in"
  echo "  macOS Keychain under service 'captains-cabinet'."
fi
echo ""

# ──────────────────────────────────────────────────────────────────────────
# SECTION 1 — Recommended connections (none block boot)
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 1 — Recommended (none of these block boot)"
echo "═══════════════════════════════════════════════════════"
echo ""
info "Telegram is the Captain's voice channel, but the Cabinet boots"
info "Telegram-dark and continues — you can connect after your first briefing."

for officer_token in TELEGRAM_COS_TOKEN TELEGRAM_CTO_TOKEN TELEGRAM_CPO_TOKEN TELEGRAM_CRO_TOKEN TELEGRAM_COO_TOKEN; do
  officer_slug="$(echo "$officer_token" | sed 's/TELEGRAM_//; s/_TOKEN//' | tr '[:upper:]' '[:lower:]')"
  tier="OPTIONAL"
  [ "$officer_slug" = "cos" ] && tier="RECOMMENDED"
  prompt_key "$officer_token" \
    "Telegram bot token for officer '$officer_slug' (one bot per officer for clean per-officer DM threading). Connect after your first briefing — boot continues Telegram-dark without it. Pasted tokens are LIVE-validated (getMe) and the bot username confirmed back; the token is never echoed." \
    "https://t.me/BotFather" \
    "$tier" \
    "$officer_slug"
done

prompt_key "CAPTAIN_TELEGRAM_ID" \
  "Your personal Telegram user ID (numeric). Officers verify it's you on incoming DMs. Easiest capture: set the bot token, message your bot once, then run: bash cabinet/scripts/telegram-capture-chat-id.sh --write" \
  "https://t.me/userinfobot" \
  "RECOMMENDED" \
  "all officers (default-deny on inbound DMs)"

prompt_key "TELEGRAM_HQ_CHAT_ID" \
  "The Cabinet's warroom group chat ID (negative number, e.g. -100xxxxxxxxxx). Officers broadcast updates here. telegram-capture-chat-id.sh --write fills this too when it sees a group message." \
  "https://t.me/userinfobot" \
  "RECOMMENDED" \
  "CoS for daily briefings + broadcast updates"

prompt_key "GITHUB_PAT" \
  "GitHub Personal Access Token for repo ops (gh CLI) + the github-issues MIRROR adapter. The cabinet's canonical work store is the LOCAL task board — no external PM tool or GitHub account is required for boot." \
  "https://github.com/settings/tokens/new?scopes=repo,workflow,read:org&description=captains-cabinet" \
  "RECOMMENDED" \
  "CTO (repo ops), CPO (issue mirroring)"

prompt_key "ANTHROPIC_API_KEY" \
  "Anthropic API key. Drives the cua MCP server (native Mac GUI control) when CUA_MODEL_BACKEND=anthropic. Skip if using Max OAuth + you don't need native Mac apps." \
  "https://console.anthropic.com/settings/keys" \
  "RECOMMENDED" \
  "cua (native Mac control); officer fallback when Max OAuth misroutes"

prompt_key "VOYAGE_API_KEY" \
  "Voyage AI key for cabinet_memory embeddings (voyage-4-large, 1024d). Without this, semantic recall fail-softs to keyword-only retrieval (verified keyless degrade) — recommended, never blocking." \
  "https://dash.voyageai.com/" \
  "RECOMMENDED" \
  "CoS (Captain DM recall), CRO (research embeddings)"

prompt_key "NOTION_API_KEY" \
  "Notion internal integration token. Cabinet reads strategy/brand/vision docs + writes research briefs + officer specs here." \
  "https://www.notion.so/my-integrations" \
  "RECOMMENDED" \
  "CoS (briefings), CRO (research), CPO (specs)"

# ──────────────────────────────────────────────────────────────────────────
# SECTION 1b — MCP keys you named in your onboarding interview
# (rendered only when integrations.mcp_env_names is non-empty; the env-var
#  NAMES your declared MCP servers need, minus any already prompted above)
# ──────────────────────────────────────────────────────────────────────────
if [ "${#MCP_ENV_NAMES[@]}" -gt 0 ]; then
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "  SECTION 1b — MCP keys you declared when you hatched"
  echo "═══════════════════════════════════════════════════════"
  echo ""
  info "You listed these under integrations.mcp_env_names in your interview —"
  info "the env-var NAMES your officers' MCP servers need. Paste each value or"
  info "skip and connect later; boot never blocks on them."
  for _mcp_key in "${MCP_ENV_NAMES[@]}"; do
    prompt_key "$_mcp_key" \
      "MCP integration key you named in the onboarding interview (integrations.mcp_env_names) — a server your officers use needs it. Paste the value or skip." \
      "" \
      "RECOMMENDED" \
      "officers with this MCP server in scope"
  done
fi

# ──────────────────────────────────────────────────────────────────────────
# SECTION 2 — Work store (local by default; Neon = cloud alternative)
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 2 — Work store (local PostgreSQL by default)"
echo "═══════════════════════════════════════════════════════"
echo ""
info "SKIP this and setup-mac.sh provisions a LOCAL PostgreSQL 16 + pgvector"
info "(bound to localhost, auto-generated password, connection string written"
info "here automatically). Paste a string only for the managed cloud alternative."

prompt_key "NEON_CONNECTION_STRING" \
  "Postgres connection string for the work store (org_events ledger, cabinet_memory pgvector, mission/role state, local task board). DEFAULT = skip: a local PostgreSQL 16 + pgvector is provisioned by setup-mac.sh / cabinet/scripts/provision-local-postgres.sh — no cloud account needed. Neon is the documented cloud alternative." \
  "https://console.neon.tech/" \
  "OPTIONAL" \
  "all officers (durable state); CoS most"

# ──────────────────────────────────────────────────────────────────────────
# SECTION 3 — Task system mirrors (the local board is canonical)
# ──────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SECTION 3 — Task system mirrors (all optional)"
echo "═══════════════════════════════════════════════════════"
echo ""
info "The canonical work store is the cabinet's LOCAL task board — no external"
info "PM tool is required. These attach as optional MIRROR adapters; pick the"
info "one your team already uses, skip the rest."

prompt_key "LINEAR_API_KEY" \
  "Linear API key. Optional mirror adapter." \
  "https://linear.app/settings/api" \
  "OPTIONAL" \
  "CPO (backlog), CTO (issue ops), CoS (cross-officer)"

prompt_key "MONDAY_API_TOKEN" \
  "Monday.com personal API token. Drives the STEP-Network/dev-tasks Claude plugin (44 MCP tools + 15 workflow skills). Replaces the cabinet's own Monday adapter (which was removed in favor of the plugin)." \
  "https://developer.monday.com/api-reference/docs/authentication" \
  "OPTIONAL" \
  "dev-tasks plugin → CPO (backlog), CTO (issues), CoS (cross-officer)"

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

apply_runtime_defaults

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

# Recommended-key recap (informational — nothing blocks boot)
missing_recommended=()
for k in "${RECOMMENDED_KEYS[@]}"; do
  v="$(current_value "$k")"
  [ -z "$v" ] && missing_recommended+=("$k")
done
if [ "${#missing_recommended[@]}" -eq 0 ]; then
  ok "All ${#RECOMMENDED_KEYS[@]} recommended keys filled"
else
  info "Not yet connected (fine — connect after your first briefing): ${missing_recommended[*]}"
fi
if [ "${#MCP_ENV_NAMES[@]}" -gt 0 ]; then
  mcp_missing=()
  for k in "${MCP_ENV_NAMES[@]}"; do
    [ -z "$(current_value "$k")" ] && mcp_missing+=("$k")
  done
  if [ "${#mcp_missing[@]}" -gt 0 ]; then
    info "Declared MCP keys still unset: ${mcp_missing[*]}"
  fi
fi
if [ -z "$(current_value "NEON_CONNECTION_STRING")" ]; then
  info "Work store: local PostgreSQL 16 + pgvector will be provisioned by setup-mac.sh"
fi
ok "The Cabinet boots with zero cloud accounts — local work store, local task board, Telegram-dark until connected"

if [ "$USE_KEYCHAIN" = "1" ]; then
  ok "All set keys mirrored to macOS Keychain (service=captains-cabinet)"
fi

echo ""
echo "  Next: bash cabinet/scripts/setup-mac.sh   (fast Mac setup; --all for everything)"
echo "==========================================="
