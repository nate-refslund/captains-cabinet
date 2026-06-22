#!/bin/bash
# chair-preflight.sh — verify the Chair (CoS front-door brain) is launch-ready.
#
# READ-ONLY: no mutations, no sends, NO launch. It prints READY + the launch
# command for Nate to run under supervision. Secrets are read into local vars and
# NEVER echoed (only the resolved bot username is shown).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/cabinet/.env"
PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
ok=0; bad=0
pass() { echo "  ✅ $1"; ok=$((ok + 1)); }
fail() { echo "  ❌ $1"; bad=$((bad + 1)); }

echo "── Chair preflight ─────────────────────────────"

# 1 + 2: env present + token valid (getMe; token never printed)
if [ -f "$ENV_FILE" ]; then
  TOK="$(grep '^TELEGRAM_COS_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
  CID="$(grep '^CAPTAIN_TELEGRAM_ID=' "$ENV_FILE" | cut -d= -f2-)"
  [ -n "$TOK" ] && pass "cabinet/.env has TELEGRAM_COS_TOKEN" || fail "TELEGRAM_COS_TOKEN missing"
  [ -n "$CID" ] && pass "cabinet/.env has CAPTAIN_TELEGRAM_ID" || fail "CAPTAIN_TELEGRAM_ID missing"
  if [ -n "$TOK" ]; then
    BOT="$(curl -s --max-time 15 "https://api.telegram.org/bot${TOK}/getMe" \
      | "$PY" -c 'import sys,json;d=json.load(sys.stdin);r=d.get("result") or {};print(r.get("username","") if d.get("ok") else "")' 2>/dev/null)"
    [ -n "$BOT" ] && pass "bot token valid → @$BOT" || fail "bot token invalid (getMe failed)"
  fi
else
  fail "cabinet/.env missing"
fi

# 3: Redis reachable (durable intake)
if redis-cli -h "${REDIS_HOST:-localhost}" ping >/dev/null 2>&1; then
  pass "Redis reachable (intake)"
else
  fail "Redis not reachable at ${REDIS_HOST:-localhost}"
fi

# 4: brain MCP rendered
if grep -q '"brain"' "$ROOT/instance/config/extra-mcps.json" 2>/dev/null; then
  pass "brain MCP rendered (extra-mcps.json)"
else
  fail "brain MCP not in extra-mcps.json"
fi

# 5: operating-loop skill
if [ -f "$ROOT/memory/skills/evolved/chair-front-door-loop.md" ]; then
  pass "operating-loop skill present"
else
  fail "chair-front-door-loop skill missing"
fi

# 6: front-door imports
if (cd "$ROOT" && "$PY" -c "import framework.frontdoor.intake, framework.frontdoor.composer, framework.frontdoor.channel, framework.frontdoor.reply_binder, framework.frontdoor.run_briefing" >/dev/null 2>&1); then
  pass "framework.frontdoor imports"
else
  fail "framework.frontdoor import error"
fi

# 7: screenpipe silenced (one channel)
if grep -q '^CABINET_OWNS_TELEGRAM=1' "$HOME/.screenpipe/pipes/_shared/.env" 2>/dev/null; then
  pass "screenpipe DMs silenced (one channel)"
else
  fail "screenpipe NOT silenced (CABINET_OWNS_TELEGRAM != 1)"
fi

# 8: recurring briefing scheduled
if launchctl list 2>/dev/null | grep -q frontdoor-briefing; then
  pass "briefing LaunchAgent loaded"
else
  fail "briefing LaunchAgent not loaded"
fi

# 9: officer launcher present
LAUNCHER="$ROOT/cabinet/scripts/start-officer-mac.sh"
[ -f "$LAUNCHER" ] && pass "officer launcher present" || fail "start-officer-mac.sh missing"

echo "────────────────────────────────────────────────"
if [ "$bad" -eq 0 ]; then
  echo "READY ($ok checks passed). Launch the Chair UNDER SUPERVISION:"
  echo ""
  echo "    CABINET_ENV=runtime REDIS_HOST=localhost bash $LAUNCHER cos"
  echo ""
  echo "It reads memory/skills/evolved/chair-front-door-loop.md as its operating loop."
  echo "Watch the first interactive cycle (a real Telegram reply → orchestration)"
  echo "before leaving it running. Verify the launcher's flags first."
else
  echo "NOT READY — $bad failed, $ok passed. Resolve the ❌ items above first."
fi
exit 0
