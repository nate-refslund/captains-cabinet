#!/bin/bash
# install-plugins.sh — install Claude Code plugins declared in
# instance/config/required-plugins.yml.
#
# Idempotent. Re-running is a no-op for already-installed plugins.
#
# The Cabinet's plugin install model:
#   - Plugins are installed at user level (~/.claude/plugins/) — one install
#     covers all 5 officers (cos/cto/cpo/cro/coo).
#   - Per-project config lives in .claude/project-config.json (when the
#     plugin requires it, like dev-tasks for STEP-Network).
#   - The list of plugins to install lives in instance/config/required-plugins.yml
#     (instance-specific — different cabinets may want different plugins).
#
# Format of required-plugins.yml:
#   plugins:
#     - name: dev-tasks
#       marketplace: dev-tasks-marketplace
#       source: STEP-Network/dev-tasks
#       description: Monday.com workflow for STEP-Network products
#       required_env: [MONDAY_API_TOKEN]
#       optional: false   # if true, log + continue on failure
#
# Pre-requisites for the dev-tasks specific case:
#   - gh auth status shows STEP-Network membership (private repo)
#   - MONDAY_API_TOKEN exported in shell launching claude
#
# Captain still has to: cp .claude/project-config.json.template
#                       .claude/project-config.json + fill product fields,
# then run `/dev-tasks:doctor` in their first session to verify.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
PLUGINS_FILE="${CABINET_PLUGINS_FILE:-$CABINET_ROOT/instance/config/required-plugins.yml}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
info() { echo -e "  ${BLUE}[i]${NC} $1"; }

if ! command -v claude >/dev/null 2>&1; then
  fail "claude CLI not found — install Claude Code first"
  exit 1
fi

if [ ! -f "$PLUGINS_FILE" ]; then
  info "No $PLUGINS_FILE — nothing to install."
  info "To enable plugins, copy the example:"
  info "  cp $CABINET_ROOT/instance/config/required-plugins.yml.example \\"
  info "     $CABINET_ROOT/instance/config/required-plugins.yml"
  exit 0
fi

# Parse required-plugins.yml without external deps (cabinet stays minimal).
# This is a deliberately simple parser; if the file gets complex, swap to yq.
python3 - "$PLUGINS_FILE" <<'PY' > /tmp/cabinet-plugins.json
import sys
import json
from pathlib import Path

text = Path(sys.argv[1]).read_text()
try:
    import yaml
    data = yaml.safe_load(text) or {}
except Exception:
    # Minimal hand-parse for the simple shape above
    data = {"plugins": []}
    current = None
    for line in text.splitlines():
        s = line.rstrip()
        if s.startswith("- name:"):
            if current is not None:
                data["plugins"].append(current)
            current = {"name": s.split(":", 1)[1].strip()}
        elif current is not None and ":" in s and s.startswith("  "):
            k, v = s.strip().split(":", 1)
            current[k.strip()] = v.strip()
    if current is not None:
        data["plugins"].append(current)

print(json.dumps(data.get("plugins", [])))
PY

if [ ! -s /tmp/cabinet-plugins.json ]; then
  warn "Could not parse $PLUGINS_FILE"
  exit 1
fi

echo "==========================================="
echo "  Cabinet — Claude plugin installer"
echo "==========================================="
echo ""

# Already-installed list (once)
INSTALLED="$(claude plugin list 2>/dev/null || echo "")"

# Iterate plugins
n_plugins=$(python3 -c "import json; print(len(json.load(open('/tmp/cabinet-plugins.json'))))")
i=0
while [ "$i" -lt "$n_plugins" ]; do
  name=$(python3 -c "import json; print(json.load(open('/tmp/cabinet-plugins.json'))[$i].get('name',''))")
  marketplace=$(python3 -c "import json; print(json.load(open('/tmp/cabinet-plugins.json'))[$i].get('marketplace',''))")
  source=$(python3 -c "import json; print(json.load(open('/tmp/cabinet-plugins.json'))[$i].get('source',''))")
  optional=$(python3 -c "import json; print(json.load(open('/tmp/cabinet-plugins.json'))[$i].get('optional','false'))")
  required_env=$(python3 -c "import json; d=json.load(open('/tmp/cabinet-plugins.json'))[$i]; v=d.get('required_env',''); print(v if isinstance(v,str) else ','.join(v))")
  i=$((i + 1))

  if [ -z "$name" ]; then continue; fi

  echo ""
  echo -e "${BLUE}[$i/$n_plugins] $name${NC}"
  echo "  source: $source"
  echo "  marketplace: $marketplace"

  # Check required env (warn-only — plugin install may still proceed)
  if [ -n "$required_env" ]; then
    IFS=',' read -ra envs <<< "$required_env"
    for var in "${envs[@]}"; do
      var="$(echo "$var" | tr -d '[:space:]')"
      [ -z "$var" ] && continue
      if [ -z "${!var:-}" ]; then
        if grep -qE "^${var}=" "$CABINET_ROOT/cabinet/.env" 2>/dev/null; then
          info "$var not exported, but present in cabinet/.env (will be loaded at officer boot)"
        else
          warn "$var not set — plugin may fail when officers use it"
        fi
      fi
    done
  fi

  # Idempotency: skip if already installed
  if echo "$INSTALLED" | grep -qE "^${name}\b"; then
    ok "$name already installed (skip)"
    continue
  fi

  # Add marketplace
  if [ -n "$source" ]; then
    info "Adding marketplace: $source"
    if claude plugin marketplace add "$source" 2>&1 | tail -3; then
      ok "marketplace $source added"
    else
      if [ "$optional" = "true" ]; then
        warn "marketplace add failed for $source (optional) — continuing"
        continue
      else
        fail "marketplace add failed for $source — aborting"
        exit 1
      fi
    fi
  fi

  # Install
  install_spec="$name"
  [ -n "$marketplace" ] && install_spec="$name@$marketplace"
  info "Installing $install_spec"
  if claude plugin install "$install_spec" 2>&1 | tail -5; then
    ok "$name installed"
  else
    if [ "$optional" = "true" ]; then
      warn "install failed for $name (optional) — continuing"
    else
      fail "install failed for $name — aborting"
      exit 1
    fi
  fi
done

echo ""
echo "==========================================="
echo "  Plugin install pass complete."
echo ""
echo "  Next steps for any plugin with per-project config (e.g. dev-tasks):"
echo "    1. cp .claude/project-config.json.template .claude/project-config.json"
echo "    2. \$EDITOR .claude/project-config.json  # fill in product fields"
echo "    3. In a fresh CC session: /dev-tasks:doctor (or plugin's verify cmd)"
echo "==========================================="

rm -f /tmp/cabinet-plugins.json
