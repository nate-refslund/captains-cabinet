#!/bin/bash
# install-mac-tools.sh — install the Captain-layer tool stack on a Mac mini.
#
# Idempotent. Safe to re-run. Called by setup-mac.sh Step 9 — ONLY when the
# Captain opts in with --with-sensors (critical-path diet, 2026-07-09): the
# fast default boot skips the whole sensor layer, and
# cabinet/scripts/null-hatch.sh is the CI-wired proof that core boots
# without it. Run standalone anytime to add the layer later.
#
# What it installs (framework-required tools; run on every --with-sensors
# opt-in regardless of which OPTIONAL personal-source adapter, if any, you
# also use — see instance/flavor-a/README.md's own "Mac install +
# permissions" section for that adapter's separate install step, R168
# 2026-07-16):
#   1. chrome-devtools-mcp (npm)    — authenticated browser automation
#   2. @playwright/mcp (npm)        — deterministic E2E browser testing
#   3. @browserbasehq/stagehand     — AI-native semantic browser actions
#   4. trycua/cua-driver            — native macOS GUI control (MCP)
#
# After install, the operator still needs to:
#   - Grant macOS Screen Recording / Accessibility permissions
#     (use cabinet/scripts/grant-mac-permissions.sh)
#   - Launch the dedicated Cabinet Chrome profile
#     (use cabinet/scripts/start-cabinet-chrome.sh)
#   - Log into Linear/Monday/Notion/Gmail in that Chrome profile ONCE
#
# Doesn't fail the entire setup-mac.sh run if a single tool fails to install;
# warns + continues so the Captain can fix individual gaps without restarting.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }

echo "==========================================="
echo "  Captain-layer tools installer"
echo "==========================================="
echo ""

# 1) chrome-devtools-mcp — authenticated browser via CDP
echo "[1/4] chrome-devtools-mcp"
if npm list -g chrome-devtools-mcp >/dev/null 2>&1; then
  ok "chrome-devtools-mcp already installed globally"
else
  # The MCP is npx-able without global install (.mcp.json.mac-native uses npx -y).
  # Warm the cache so first officer session doesn't hit npm cold-start.
  if npx -y chrome-devtools-mcp@latest --help >/dev/null 2>&1; then
    ok "chrome-devtools-mcp cache warmed (npx will run on first use)"
  else
    warn "chrome-devtools-mcp warm failed — first officer session may be slow on cold npx"
  fi
fi
echo ""

# 2) Playwright MCP — deterministic browser testing
echo "[2/4] @playwright/mcp"
if npx -y @playwright/mcp@latest --help >/dev/null 2>&1; then
  ok "@playwright/mcp cache warmed"
else
  warn "@playwright/mcp warm failed"
fi
# Also install Playwright's Chromium binary so MCP can drive a sandbox browser
if command -v npx >/dev/null 2>&1; then
  if npx -y playwright install chromium >/dev/null 2>&1; then
    ok "Playwright Chromium installed"
  else
    warn "Playwright Chromium install failed — run manually: npx playwright install chromium"
  fi
fi
echo ""

# 3) Stagehand v3 — AI-native semantic actions on top of CDP
# NOT an MCP. Officers invoke from Node code when they need act/extract.
echo "[3/4] @browserbasehq/stagehand (lib, not MCP)"
if command -v npm >/dev/null 2>&1; then
  if npm install -g @browserbasehq/stagehand >/dev/null 2>&1; then
    ok "Stagehand v3 installed globally"
  else
    warn "Stagehand v3 install failed — install per-officer in node deps if needed"
  fi
fi
echo ""

# 4) trycua/cua-driver — native macOS GUI control via MCP
echo "[4/4] cua-driver"
if command -v cua-driver >/dev/null 2>&1; then
  ok "cua-driver already installed ($(command -v cua-driver))"
else
  # Try npm first (most common); fall back to brew tap if available.
  if command -v npm >/dev/null 2>&1 && npm install -g @trycua/cua-driver >/dev/null 2>&1; then
    ok "cua-driver installed via npm"
  elif command -v brew >/dev/null 2>&1 && brew install trycua/tap/cua-driver >/dev/null 2>&1; then
    ok "cua-driver installed via brew"
  else
    warn "cua-driver auto-install failed. Manual install: see https://github.com/trycua/cua"
    warn "  Common path: npm install -g @trycua/cua-driver"
    warn "  Or:          pip install trycua-cua"
  fi
fi

# Verify cua-driver permissions if installed (cua-driver has its own checker)
if command -v cua-driver >/dev/null 2>&1; then
  echo ""
  if cua-driver check_permissions 2>&1 | tail -5; then
    ok "cua-driver permissions verified"
  else
    warn "cua-driver permissions not yet granted — run grant-mac-permissions.sh"
  fi
fi
echo ""

echo "==========================================="
echo "  Captain-layer install complete."
echo ""
echo "  Next: bash cabinet/scripts/grant-mac-permissions.sh"
echo "         (opens System Settings; Captain clicks Allow)"
echo ""
echo "  Then: bash cabinet/scripts/start-cabinet-chrome.sh"
echo "         (launches dedicated Chrome profile; log into web apps ONCE)"
echo ""
echo "  Using the optional personal-source adapter? Its install step is"
echo "  separate — see instance/flavor-a/README.md."
echo "==========================================="
