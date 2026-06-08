#!/bin/bash
# install-extensions.sh — install Claude Code extensions (plugins + MCP
# servers) declared in instance/config/extensions.yml.
#
# The Captain's Cabinet is a UNIVERSAL product — it installs NO third-party
# extensions unless YOU declare them. This script reads your
# instance/config/extensions.yml and applies it idempotently, so a fresh
# clone or a new Mac mini re-installs exactly the extensions you chose.
#
# Same surface as Claude Desktop / Claude Code, just declarative:
#   plugins:  `claude plugin marketplace add <source>` + `claude plugin install`
#   mcps:     merged into instance/config/extra-mcps.json, which
#             start-officer-mac.sh deep-merges into every officer's .mcp.json
#   skills:   file-drop (.claude/skills/<name>/SKILL.md) or plugin-bundled —
#             nothing for this script to do; documented in extensions.yml.
#
# Idempotent. Re-running skips already-installed plugins and re-renders the
# extra-mcps.json from the declared set.
#
# Usage:
#   bash cabinet/scripts/install-extensions.sh
#   CABINET_EXTENSIONS_FILE=/path/to/extensions.yml bash ...

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
EXT_FILE="${CABINET_EXTENSIONS_FILE:-$CABINET_ROOT/instance/config/extensions.yml}"
EXTRA_MCPS_FILE="$CABINET_ROOT/instance/config/extra-mcps.json"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
info() { echo -e "  ${BLUE}[i]${NC} $1"; }

if [ ! -f "$EXT_FILE" ]; then
  info "No $EXT_FILE — Cabinet installs no third-party extensions by default."
  info "To add plugins / MCPs, copy the template and edit it:"
  info "  cp instance/config/extensions.yml.example instance/config/extensions.yml"
  exit 0
fi

# Normalize the whole YAML to JSON once (pyyaml is pip-installed by setup-mac
# Step 3; fall back to a minimal plugins-only hand-parse if it's missing).
PARSED_JSON="$(python3 - "$EXT_FILE" <<'PY'
import sys, json
from pathlib import Path
text = Path(sys.argv[1]).read_text()
try:
    import yaml
    data = yaml.safe_load(text) or {}
except Exception:
    data = {"plugins": [], "mcps": [], "skills": []}
out = {
    "plugins": data.get("plugins") or [],
    "mcps": data.get("mcps") or [],
    "skills": data.get("skills") or [],
}
print(json.dumps(out))
PY
)"

if [ -z "$PARSED_JSON" ]; then
  fail "Could not parse $EXT_FILE"
  exit 1
fi

echo "==========================================="
echo "  Cabinet — extension installer"
echo "==========================================="

N_PLUGINS=$(printf '%s' "$PARSED_JSON" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['plugins']))")
N_MCPS=$(printf '%s' "$PARSED_JSON" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['mcps']))")
echo "  declared: $N_PLUGINS plugin(s), $N_MCPS extra MCP server(s)"

# ──────────────────────────────────────────────────────────────────────────
# Plugins
# ──────────────────────────────────────────────────────────────────────────
if [ "$N_PLUGINS" -gt 0 ]; then
  if ! command -v claude >/dev/null 2>&1; then
    fail "claude CLI not found — can't install plugins"
    exit 1
  fi
  INSTALLED="$(claude plugin list 2>/dev/null || echo "")"

  i=0
  while [ "$i" -lt "$N_PLUGINS" ]; do
    get() { printf '%s' "$PARSED_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin)['plugins'][$i]; v=d.get('$1',''); print(v if not isinstance(v,list) else ','.join(map(str,v)))"; }
    name="$(get name)"; marketplace="$(get marketplace)"; source="$(get source)"
    optional="$(get optional)"; required_env="$(get required_env)"
    i=$((i + 1))
    [ -z "$name" ] && continue

    echo ""
    echo -e "${BLUE}plugin [$i/$N_PLUGINS] $name${NC}  (source: $source)"

    # required_env check (warn only; cabinet/.env is loaded at officer boot)
    if [ -n "$required_env" ]; then
      IFS=',' read -ra envs <<< "$required_env"
      for var in "${envs[@]}"; do
        var="$(echo "$var" | tr -d '[:space:]')"; [ -z "$var" ] && continue
        if [ -z "${!var:-}" ] && ! grep -qE "^${var}=" "$CABINET_ROOT/cabinet/.env" 2>/dev/null; then
          warn "$var not set (not in env or cabinet/.env) — plugin may fail at runtime"
        fi
      done
    fi

    if echo "$INSTALLED" | grep -qE "^${name}\b"; then
      ok "$name already installed (skip)"; continue
    fi

    if [ -n "$source" ]; then
      info "marketplace add $source"
      if ! claude plugin marketplace add "$source" 2>&1 | tail -3; then
        if [ "$optional" = "true" ] || [ "$optional" = "True" ]; then
          warn "marketplace add failed (optional) — continuing"; continue
        else
          fail "marketplace add failed — aborting"; exit 1
        fi
      fi
    fi

    install_spec="$name"; [ -n "$marketplace" ] && install_spec="$name@$marketplace"
    info "plugin install $install_spec"
    if ! claude plugin install "$install_spec" 2>&1 | tail -5; then
      if [ "$optional" = "true" ] || [ "$optional" = "True" ]; then
        warn "install failed (optional) — continuing"
      else
        fail "install failed — aborting"; exit 1
      fi
    else
      ok "$name installed"
    fi
  done
fi

# ──────────────────────────────────────────────────────────────────────────
# Extra MCP servers → instance/config/extra-mcps.json
# ──────────────────────────────────────────────────────────────────────────
# Render the declared mcps into a {"mcpServers": {...}} doc. start-officer-mac.sh
# deep-merges this over .mcp.json.mac-native for every officer at boot.
if [ "$N_MCPS" -gt 0 ]; then
  echo ""
  echo -e "${BLUE}Rendering $N_MCPS extra MCP server(s) → instance/config/extra-mcps.json${NC}"
  printf '%s' "$PARSED_JSON" | python3 -c "
import json, sys
data = json.load(sys.stdin)
servers = {}
for m in data['mcps']:
    name = m.get('name')
    if not name:
        continue
    entry = {}
    if m.get('command'): entry['command'] = m['command']
    if m.get('args'): entry['args'] = m['args']
    if m.get('transport'): entry['transport'] = m['transport']
    if m.get('url'): entry['url'] = m['url']
    if m.get('env'): entry['env'] = m['env']
    servers[name] = entry
out = {'mcpServers': servers}
import os
with open('$EXTRA_MCPS_FILE', 'w') as f:
    json.dump(out, f, indent=2)
print('  wrote ' + str(len(servers)) + ' server(s) to $EXTRA_MCPS_FILE')
"
  ok "extra-mcps.json rendered (merged into officer .mcp.json at boot)"
else
  # No extra MCPs declared — remove a stale extra-mcps.json so it doesn't
  # inject servers the captain removed from extensions.yml.
  if [ -f "$EXTRA_MCPS_FILE" ]; then
    rm -f "$EXTRA_MCPS_FILE"
    info "no extra MCPs declared — removed stale extra-mcps.json"
  fi
fi

echo ""
echo "==========================================="
echo "  Extension install pass complete."
echo ""
echo "  To grant an officer access to a newly-installed plugin/MCP tool,"
echo "  drop an overlay at instance/agents/<officer>.md with an extended"
echo "  'tools:' list (sync-agents.sh merges it over the preset)."
echo ""
echo "  Plugins needing per-project config (e.g. dev-tasks) also want a"
echo "  .claude/project-config.json — see the plugin's own docs."
echo "==========================================="
