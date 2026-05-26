#!/bin/bash
# setup-mac.sh — One-command Mac Mini setup for Captain's Cabinet
#
# Prerequisites: macOS with Homebrew installed
# Usage: bash cabinet/scripts/setup-mac.sh [--check|--dry-run|--help]

set -euo pipefail

CHECK_ONLY=0
usage() {
  cat <<EOF
Usage: setup-mac.sh [--check|--dry-run|--help]

Modes:
  (no args)        Check prerequisites and install missing ones via Homebrew,
                   then start Redis, install Python deps, load preset, run tests.
  --check          Check prerequisites only. Exit 0 if all present, exit 1 if
                   any are missing. No installs, no side effects.
  --dry-run        Alias for --check.
  --help, -h       Print this help and exit.
EOF
}
if [ $# -gt 0 ]; then
  case "$1" in
    --check|--dry-run) CHECK_ONLY=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
fi

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
check_dep "Claude Code" claude || MISSING=1
# Convergence Phase 9: envsubst is needed by deploy-mac.sh to render plists.
# Ships in gettext on Homebrew; macOS does not include it by default.
check_dep "envsubst (gettext)" envsubst || MISSING=1
# gh CLI is needed by the github-issues task adapter (Phase 5) — Cabinet's
# default task system on a fresh deployment.
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
pip3 install --quiet pyyaml psycopg2-binary requests pytest 2>/dev/null
ok "Python deps installed"

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
import sys; sys.path.insert(0, '$CABINET_ROOT/cabinet/scripts/lib')
from policy_engine import load_policies
policies = load_policies('$CABINET_ROOT')
print(f'{len(policies)} policies loaded')
" 2>/dev/null; then
  ok "Policy engine works"
else
  warn "Policy engine failed to load (check Python path)"
fi

echo ""
echo "=== Step 7: Run framework tests ==="
if python3 -m pytest "$CABINET_ROOT/framework/" -q --rootdir="$CABINET_ROOT" 2>/dev/null | tail -1; then
  ok "Framework tests pass"
else
  warn "Some framework tests failed (run manually to investigate)"
fi

echo ""
echo "=== Step 8: Check configuration ==="
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  ok ".env file exists"
else
  warn "No .env file — copy cabinet/.env.example to cabinet/.env and fill in API keys"
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
echo "==========================================="
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Copy cabinet/.env.example → cabinet/.env (fill in API keys)"
echo "  2. Set your project in instance/config/active-project.txt"
echo "  3. Create instance/config/projects/<slug>.yml (see _template.yml)"
echo "  4. Declare outcomes in instance/config/outcomes.yml"
echo "  5. Start an officer: bash cabinet/scripts/start-officer.sh cos"
echo "==========================================="
