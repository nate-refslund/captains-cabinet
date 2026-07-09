#!/bin/bash
# setup-mac.sh — One-command Mac Mini setup for Captain's Cabinet
#
# Prerequisites: macOS with Homebrew installed
# Usage: bash cabinet/scripts/setup-mac.sh [flags]
#
# The DEFAULT run is the FAST boot (critical-path diet, 2026-07-09): host
# prereqs, Redis + AOF, Python deps, the LOCAL work store (PostgreSQL 16 +
# pgvector, provisioned only when no connection string is configured — no
# cloud account is boot-critical), dirs, preset + roles, policy engine, and
# the FAST proofs (the null-hatch gate + the clean-room pytest subset from
# docs/runbooks/mini-hatch-tonight-2026-07-07.md §5). Heavy lanes are
# opt-in flags; the end-of-run summary lists everything skipped and the
# flag that enables it.
#
# Flags (combinable):
#   --fast            Explicit alias of the default fast run.
#   --check           Check prerequisites only. Exit 0 if all present, exit 1
#                     if any are missing. No installs, no side effects.
#   --dry-run         Alias for --check.
#   --full-suite      Also run the FULL framework pytest suite (Step 7b).
#   --with-dashboard  Also build the dashboard (npm ci + build, Step 14).
#   --with-sensors    Also run Steps 9-11: screenpipe/cua/browser installs,
#                     the Cabinet Chrome profile, and macOS TCC permission
#                     grants. Default OFF — cabinet/scripts/null-hatch.sh is
#                     the CI-wired proof that core boots without them.
#   --all             Everything: --full-suite --with-dashboard --with-sensors.
#   --help, -h        Print this help and exit.

set -euo pipefail

CHECK_ONLY=0
WITH_SENSORS=0
WITH_DASHBOARD=0
FULL_SUITE=0
usage() {
  cat <<EOF
Usage: setup-mac.sh [--fast|--check|--dry-run|--full-suite|--with-dashboard|--with-sensors|--all|--help]

Modes (flags combinable):
  (no args) / --fast  FAST boot (the default): check/install prereqs via
                      Homebrew, start Redis + AOF, install Python deps,
                      provision the local work store (PostgreSQL 16 +
                      pgvector) when no connection string is configured,
                      create dirs, load preset + roles, verify the policy
                      engine, run the FAST proofs (null-hatch gate +
                      clean-room pytest subset). Skips sensors, dashboard
                      build, and the full test suite — see flags below.
  --check             Check prerequisites only. Exit 0 if all present, exit 1
                      if any are missing. No installs, no side effects.
  --dry-run           Alias for --check.
  --full-suite        Also run the full framework pytest suite.
  --with-dashboard    Also build the dashboard (npm ci + build).
  --with-sensors      Also install the sensor layer (Steps 9-11): screenpipe,
                      cua, browser MCPs, Cabinet Chrome profile, TCC grants.
  --all               --full-suite --with-dashboard --with-sensors.
  --help, -h          Print this help and exit.
EOF
}
while [ $# -gt 0 ]; do
  case "$1" in
    --check|--dry-run) CHECK_ONLY=1 ;;
    --fast) ;; # explicit alias of the default fast run
    --full-suite) FULL_SUITE=1 ;;
    --with-dashboard) WITH_DASHBOARD=1 ;;
    --with-sensors) WITH_SENSORS=1 ;;
    --all) FULL_SUITE=1; WITH_DASHBOARD=1; WITH_SENSORS=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

CABINET_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Export for child scripts (load-preset.sh reads CABINET_ROOT; matches the
# convention used by cabinet/scripts/start-officer-mac.sh which exports both
# CABINET_ROOT and REPO_ROOT for parity). Without this, load-preset.sh falls
# back to its hardcoded default and breaks Mac-native preset loading.
REPO_ROOT="$CABINET_ROOT"
export CABINET_ROOT REPO_ROOT
echo "Cabinet root: $CABINET_ROOT"
echo ""

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }

# End-of-run bookkeeping for the one-screen summary. Entries are
# "description|flag" (SKIPPED) or plain text (ISSUES). bash 3.2: length of a
# declared-empty array is safe under set -u; only expand when non-empty.
SKIPPED=()
ISSUES=()

# python interpreter for the proof/pytest steps — the runbook pins 3.12
# semantics; fall back to python3 where 3.12 isn't linked yet.
PYBIN="python3"
command -v python3.12 >/dev/null 2>&1 && PYBIN="python3.12"

echo "=== Step 0: API key wizard ==="
# Walks Captain through tiered API keys (recommended / optional), opens
# signup URLs, masks paste input, writes cabinet/.env at chmod 600.
# De-cloud doctrine (2026-07-09): NO key is boot-critical — the wizard is
# skippable and non-interactive runs write local defaults instead.
# Idempotent — skips already-filled keys. Skip-able via env var for CI.
if [ "$CHECK_ONLY" -eq 1 ]; then
  # --check promises zero side effects — never launch the wizard here.
  if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
    ok ".env exists (contents not validated in --check)"
  else
    warn "No cabinet/.env yet — a normal run writes it (wizard or --defaults)"
  fi
elif [ "${SKIP_ENV_WIZARD:-0}" = "1" ]; then
  warn "SKIP_ENV_WIZARD=1 — skipping interactive wizard. Run later: bash cabinet/scripts/setup-env.sh"
elif [ -f "$CABINET_ROOT/cabinet/.env" ] && bash "$CABINET_ROOT/cabinet/scripts/setup-env.sh" --check >/dev/null 2>&1; then
  ok ".env present (wizard skipped; connect accounts anytime: bash cabinet/scripts/setup-env.sh)"
elif [ -f "$CABINET_ROOT/cabinet/scripts/setup-env.sh" ]; then
  if [ -t 0 ]; then
    bash "$CABINET_ROOT/cabinet/scripts/setup-env.sh"
  else
    # Non-interactive session (hatch engine / CI): local defaults only.
    warn "stdin is not a TTY — writing local defaults (setup-env.sh --defaults); connect accounts later via setup-env.sh"
    bash "$CABINET_ROOT/cabinet/scripts/setup-env.sh" --defaults
  fi
else
  warn "setup-env.sh not found — fill cabinet/.env manually before continuing"
fi

echo ""
echo "=== Step 1: Check prerequisites ==="

check_dep() {
  local name="$1" cmd="$2"
  if command -v "$cmd" > /dev/null 2>&1; then
    ok "$name ($(command -v "$cmd"))"
    return 0
  else
    fail "$name not found"
    return 1
  fi
}

MISSING=0
check_dep "Homebrew" brew || MISSING=1
check_dep "tmux" tmux || MISSING=1
check_dep "jq" jq || MISSING=1
check_dep "Python 3" python3 || MISSING=1
check_dep "Redis CLI" redis-cli || MISSING=1
check_dep "Node.js" node || MISSING=1
check_dep "npm" npm || MISSING=1
check_dep "Claude Code" claude || MISSING=1
check_dep "Bun" bun || MISSING=1
# Convergence Phase 9: envsubst is needed by deploy-mac.sh to render plists.
# Ships in gettext on Homebrew; macOS does not include it by default.
check_dep "envsubst (gettext)" envsubst || MISSING=1
# gh CLI powers repo ops + the optional github-issues MIRROR adapter. The
# canonical work store is the LOCAL task board (officer_tasks) — no external
# PM tool or GitHub account is required for boot (README promise).
check_dep "gh CLI" gh || MISSING=1

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo ""
  if [ "$MISSING" -eq 1 ]; then
    echo "Missing prereqs — re-run without --check to install via Homebrew."
    exit 1
  fi
  echo "All prereqs present."
  exit 0
fi

if [ "$MISSING" -eq 1 ]; then
  echo ""
  echo "Installing missing dependencies via Homebrew..."
  command -v brew > /dev/null 2>&1 || { fail "Homebrew required. Install from https://brew.sh"; exit 1; }
  command -v tmux > /dev/null 2>&1 || brew install tmux
  command -v jq > /dev/null 2>&1 || brew install jq
  command -v python3 > /dev/null 2>&1 || brew install python3
  command -v redis-cli > /dev/null 2>&1 || brew install redis
  command -v node > /dev/null 2>&1 || brew install node
  command -v npm > /dev/null 2>&1 || brew install node
  command -v bun > /dev/null 2>&1 || brew install oven-sh/bun/bun
  command -v envsubst > /dev/null 2>&1 || brew install gettext
  command -v gh > /dev/null 2>&1 || brew install gh
  echo ""
fi

echo ""
echo "=== Step 2: Start Redis ==="
if redis-cli ping > /dev/null 2>&1; then
  ok "Redis already running"
else
  echo "  Starting Redis via Homebrew services..."
  brew services start redis 2>/dev/null || redis-server --daemonize yes
  sleep 1
  if redis-cli ping > /dev/null 2>&1; then
    ok "Redis started"
  else
    fail "Redis failed to start"
    exit 1
  fi
fi

# Enable AOF durability for unattended Mac operation (cabinet needs ~1s
# data-loss tolerance for triggers / counters / heartbeats / memory queue).
# Idempotent; no-op if already enabled.
echo ""
echo "=== Step 2.5: Enable Redis AOF (durability) ==="
if bash "$CABINET_ROOT/cabinet/scripts/enable-redis-aof.sh" 2>&1 | tail -3; then
  ok "Redis AOF check complete"
else
  warn "Redis AOF enable failed — run manually: bash cabinet/scripts/enable-redis-aof.sh"
fi

echo ""
echo "=== Step 3: Install Python dependencies ==="
if pip3 install --quiet pyyaml psycopg2-binary requests pytest 2>/dev/null; then
  ok "Python deps installed"
else
  # PEP 668 externally-managed Homebrew pythons refuse bare pip3 installs.
  warn "pip3 install failed — ensure deps yourself: python3.12 -m pip install pyyaml pytest requests psycopg2-binary"
fi

echo ""
echo "=== Step 3.5: Local work store (PostgreSQL 16 + pgvector) ==="
# De-cloud doctrine (2026-07-09): NO cloud account is boot-critical. When no
# work-store connection string is configured, provision a LOCAL PostgreSQL 16
# + pgvector bound to localhost, credentialed with the auto-generated
# POSTGRES_PASSWORD, and write the connection string into the gitignored
# cabinet/.env. Neon stays the documented CLOUD ALTERNATIVE — paste your
# NEON_CONNECTION_STRING via setup-env.sh and this step no-ops. Runs BEFORE
# Step 5 so load-preset.sh applies schemas to the freshly-wired store.
EXISTING_CONN="$(grep -E '^NEON_CONNECTION_STRING=' "$CABINET_ROOT/cabinet/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
if [ -n "$EXISTING_CONN" ]; then
  ok "Work store already configured (NEON_CONNECTION_STRING set — value not shown)"
elif [ -f "$CABINET_ROOT/cabinet/scripts/provision-local-postgres.sh" ]; then
  if bash "$CABINET_ROOT/cabinet/scripts/provision-local-postgres.sh" 2>&1 | tail -8; then
    ok "Local work store ready"
  else
    warn "Local PostgreSQL provisioning failed — run manually: bash cabinet/scripts/provision-local-postgres.sh (or paste a Neon string via setup-env.sh)"
    ISSUES+=("work store not provisioned — bash cabinet/scripts/provision-local-postgres.sh")
  fi
else
  warn "provision-local-postgres.sh not found — configure a work store via setup-env.sh"
fi

echo ""
echo "=== Step 4: Create required directories ==="
mkdir -p "$CABINET_ROOT/instance/roles/active"
mkdir -p "$CABINET_ROOT/instance/roles/archive"
mkdir -p "$CABINET_ROOT/instance/roles/hats"
mkdir -p "$CABINET_ROOT/instance/memory/tier2"
mkdir -p "$CABINET_ROOT/memory/logs"
ok "Directories created"

echo ""
echo "=== Step 5: Load preset ==="
if [ -f "$CABINET_ROOT/cabinet/scripts/load-preset.sh" ]; then
  bash "$CABINET_ROOT/cabinet/scripts/load-preset.sh" 2>&1 | tail -1
  ok "Preset loaded"
else
  warn "load-preset.sh not found, skipping"
fi

echo ""
echo "=== Step 5.5: Bootstrap durable roles ==="
# Seed the 5 active officers into org_roles + instance/roles/active/ so
# mission compilation can find role owners. Idempotent — no-op if already
# seeded. Without this, outcome → mission compilation fails with
# "unknown role for <product>: cos".
if [ -f "$CABINET_ROOT/cabinet/scripts/bootstrap-roles.sh" ]; then
  bash "$CABINET_ROOT/cabinet/scripts/bootstrap-roles.sh" 2>&1 | tail -10
  ok "Roles bootstrapped"
else
  warn "bootstrap-roles.sh not found, skipping (mission compilation will fail until you seed roles manually)"
fi

echo ""
echo "=== Step 6: Verify policy engine ==="
if python3 -c "
import sys; sys.path.insert(0, '$CABINET_ROOT')
from framework.authority.policy_engine import load_policies
policies = load_policies('$CABINET_ROOT')
print(f'{len(policies)} policies loaded')
" 2>/dev/null; then
  ok "Policy engine works"
else
  warn "Policy engine failed to load (check Python path)"
fi

echo ""
echo "=== Step 7: Fast proofs (null-hatch gate + clean-room subset) ==="
# The critical-path proofs from the mini-hatch runbook §5. P-a proves the
# COMMITTED tree boots with no captain data / no screenpipe / no source
# binding (hermetic sandbox); P-b proves the same clean-room ratchets on the
# WORKING tree. The FULL framework suite moved behind --full-suite.
if bash "$CABINET_ROOT/cabinet/scripts/null-hatch.sh" 2>&1 | tail -3; then
  ok "P-a null-hatch gate PASS"
else
  warn "P-a null-hatch gate FAILED — do not hatch on a red gate. Run manually: bash cabinet/scripts/null-hatch.sh"
  ISSUES+=("P-a null-hatch gate RED — bash cabinet/scripts/null-hatch.sh")
fi
if "$PYBIN" -m pytest \
    "$CABINET_ROOT/framework/tests/test_clean_room.py" \
    "$CABINET_ROOT/framework/tests/test_no_screenpipe_in_core.py" \
    "$CABINET_ROOT/framework/tests/test_no_launcher_hardcode.py" \
    -q --rootdir="$CABINET_ROOT" 2>/dev/null | tail -1; then
  ok "P-b clean-room subset PASS"
else
  warn "P-b clean-room subset FAILED — run manually to investigate"
  ISSUES+=("P-b clean-room pytest subset RED")
fi

echo ""
if [ "$FULL_SUITE" -eq 1 ]; then
  echo "=== Step 7b: Run FULL framework test suite (--full-suite) ==="
  if "$PYBIN" -m pytest "$CABINET_ROOT/framework/" -q --rootdir="$CABINET_ROOT" 2>/dev/null | tail -1; then
    ok "Framework tests pass"
  else
    warn "Some framework tests failed (run manually to investigate)"
    ISSUES+=("full framework suite RED — $PYBIN -m pytest framework/ -q")
  fi
else
  echo "=== Step 7b: Full framework suite (skipped — enable with --full-suite) ==="
  warn "Fast boot runs the proofs above only; the full suite is opt-in"
  SKIPPED+=("full framework pytest suite|--full-suite")
fi

echo ""
echo "=== Step 8: Check configuration ==="
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  ok ".env file exists"
else
  warn "No .env file — run: bash cabinet/scripts/setup-env.sh (or --defaults for local-only)"
fi

ACTIVE_PROJECT=$(cat "$CABINET_ROOT/instance/config/active-project.txt" 2>/dev/null | tr -d '[:space:]')
if [ -n "$ACTIVE_PROJECT" ] && [ "$ACTIVE_PROJECT" != "demo" ]; then
  ok "Active project: $ACTIVE_PROJECT"
else
  warn "Active project is 'demo' — set your project slug in instance/config/active-project.txt"
fi

if [ -f "$CABINET_ROOT/instance/config/outcomes.yml" ]; then
  ok "Outcomes file exists"
else
  warn "No outcomes.yml — declare Captain outcomes in instance/config/outcomes.yml"
fi

echo ""
if [ "$WITH_SENSORS" -eq 1 ]; then
  echo "=== Step 9: Install Captain-layer tools (screenpipe, cua, browsers) ==="
  # Installs: screenpipe (brew), chrome-devtools-mcp + @playwright/mcp + Stagehand
  # (npm), cua-driver (npm/brew). Idempotent. Warns but doesn't fail on
  # individual install errors so Captain can fix gaps without restarting.
  if [ -f "$CABINET_ROOT/cabinet/scripts/install-mac-tools.sh" ]; then
    bash "$CABINET_ROOT/cabinet/scripts/install-mac-tools.sh" 2>&1 | tail -25
    ok "Captain-layer tools install complete"
  else
    warn "install-mac-tools.sh not found, skipping (officers won't have screenpipe/cua/browsers)"
  fi

  echo ""
  echo "=== Step 10: Bootstrap dedicated Cabinet Chrome profile ==="
  # Creates ~/.cabinet-chrome-profile and launches Chrome with --remote-debugging
  # bound to 127.0.0.1:9222 ONLY (Corridor security invariant). Captain will need
  # to log into Linear/Monday/Notion/Gmail ONCE in this Chrome window — those
  # sessions then persist forever for all officer chrome-devtools MCP usage.
  if [ -f "$CABINET_ROOT/cabinet/scripts/start-cabinet-chrome.sh" ]; then
    bash "$CABINET_ROOT/cabinet/scripts/start-cabinet-chrome.sh" 2>&1 | tail -15
    ok "Cabinet Chrome profile started (sign into product platforms in the new window)"
  else
    warn "start-cabinet-chrome.sh not found, skipping"
  fi

  echo ""
  echo "=== Step 11: Grant macOS Privacy permissions (interactive) ==="
  # macOS TCC requires user clicks; this opens System Settings panes + tells
  # Captain which apps need Allow. Skip-able via env var for unattended re-runs.
  if [ "${SKIP_MAC_PERMISSIONS:-0}" = "1" ]; then
    warn "SKIP_MAC_PERMISSIONS=1 — skipping interactive grant. Run later: bash cabinet/scripts/grant-mac-permissions.sh"
  elif [ -f "$CABINET_ROOT/cabinet/scripts/grant-mac-permissions.sh" ]; then
    bash "$CABINET_ROOT/cabinet/scripts/grant-mac-permissions.sh" 2>&1
    ok "Permission grants complete (verify with: cua-driver check_permissions)"
  else
    warn "grant-mac-permissions.sh not found, skipping"
  fi
else
  echo "=== Steps 9-11: Sensor layer (skipped — enable with --with-sensors) ==="
  # The base hatch needs NONE of these (mini-hatch runbook §0: screenpipe /
  # TCC grants are deliberately NOT prerequisites; null-hatch.sh is the
  # CI-wired proof core boots without them). Connect the sensor layer when a
  # capability actually needs it.
  warn "screenpipe/cua/browser installs, Cabinet Chrome profile, TCC grants deferred (fast boot)"
  SKIPPED+=("sensor layer: screenpipe/cua/browsers + Chrome profile + TCC grants|--with-sensors")
fi

echo ""
echo "=== Step 12: Verify Captain-layer MCP wiring ==="
if [ -f "$CABINET_ROOT/.mcp.json.mac-native" ]; then
  CAPTAIN_MCPS=$(python3 -c "
import json
with open('$CABINET_ROOT/.mcp.json.mac-native') as f:
    d = json.load(f)
servers = d.get('mcpServers', {})
captain_layer = ['screenpipe', 'chrome_devtools', 'playwright', 'cua']
present = [s for s in captain_layer if s in servers]
missing = [s for s in captain_layer if s not in servers]
print('present=' + ','.join(present))
print('missing=' + ','.join(missing) if missing else 'missing=none')
" 2>/dev/null)
  echo "  $CAPTAIN_MCPS" | head -5
  if echo "$CAPTAIN_MCPS" | grep -q "missing=none"; then
    ok "All 4 Captain-layer MCPs declared in .mcp.json.mac-native"
  else
    warn "Some Captain-layer MCPs missing from .mcp.json.mac-native"
  fi
else
  warn ".mcp.json.mac-native not found"
fi

echo ""
echo "=== Step 13: Install declared Claude extensions (plugins + MCPs) ==="
# Installs Claude Code extensions declared in instance/config/extensions.yml
# (if present). The Cabinet ships UNIVERSAL — no third-party extensions are
# installed unless you declare them. Plugins install user-level (one install
# covers all 5 officers); extra MCP servers render to extra-mcps.json which
# start-officer-mac.sh merges into each officer's .mcp.json at boot.
# Idempotent; warns + continues on individual install failures.
if [ -f "$CABINET_ROOT/cabinet/scripts/install-extensions.sh" ]; then
  bash "$CABINET_ROOT/cabinet/scripts/install-extensions.sh" 2>&1 | tail -20
  ok "Extension install pass complete"
else
  warn "install-extensions.sh not found, skipping (no extensions installed)"
fi

echo ""
if [ "$WITH_DASHBOARD" -eq 1 ]; then
  echo "=== Step 14: Build the dashboard (office wall-display + control panel) ==="
  # Pre-build so the com.cabinet.dashboard LaunchAgent starts instantly instead
  # of building on first boot. Best-effort: a build failure here doesn't block
  # setup (start-dashboard.sh will retry the build at launch).
  DASH_DIR="$CABINET_ROOT/cabinet/dashboard"
  if [ -d "$DASH_DIR" ] && command -v npm >/dev/null 2>&1; then
    echo "  Building Next.js dashboard (npm ci + build, ~1-2 min)..."
    ( cd "$DASH_DIR" \
      && { [ -d node_modules ] || npm ci >/dev/null 2>&1; } \
      && npm run build >/dev/null 2>&1 ) \
      && ok "Dashboard built (serve: cabinet/scripts/start-dashboard.sh → :3100/display)" \
      || warn "Dashboard build failed — start-dashboard.sh will retry at launch"
  else
    warn "Dashboard dir or npm missing — skipping build"
  fi
else
  echo "=== Step 14: Dashboard build (skipped — enable with --with-dashboard) ==="
  warn "npm ci + build deferred (start-dashboard.sh builds on first launch anyway)"
  SKIPPED+=("dashboard build: npm ci + npm run build|--with-dashboard")
fi

echo ""
echo "==========================================="
# Banner wording is driven by the SKIPPED list itself so it can never
# contradict the summary below (an --all run is a full run, not "fast boot").
if [ "${#SKIPPED[@]}" -gt 0 ]; then
  echo "  Setup complete (fast boot)."
  echo ""
  echo "  Skipped on this run — each is one flag away:"
  for item in "${SKIPPED[@]}"; do
    desc="${item%%|*}"; flag="${item##*|}"
    printf '    - %-58s %s\n' "$desc" "$flag"
  done
  echo "  Run everything: bash cabinet/scripts/setup-mac.sh --all"
else
  echo "  Setup complete (full run)."
  echo ""
  echo "  Nothing skipped (this was a full run)."
fi
if [ "${#ISSUES[@]}" -gt 0 ]; then
  echo ""
  echo "  ATTENTION — fix before hatching (do not proceed past a red gate):"
  for item in "${ISSUES[@]}"; do
    echo "    - $item"
  done
fi
echo ""
echo "  Next steps for Captain:"
echo "  1. Connect accounts when ready: bash cabinet/scripts/setup-env.sh"
echo "     (Telegram can wait — connect after your first briefing; capture"
echo "     your chat id with: bash cabinet/scripts/telegram-capture-chat-id.sh --write)"
echo "  2. Set your project in instance/config/active-project.txt"
echo "  3. Create instance/config/projects/<slug>.yml (see _template.yml)"
echo "  4. Declare outcomes in instance/config/outcomes.yml"
echo "  5. Deploy LaunchAgents: CABINET_ROOT=\"\$(pwd)\" bash cabinet/scripts/deploy-mac.sh --all"
echo "==========================================="
