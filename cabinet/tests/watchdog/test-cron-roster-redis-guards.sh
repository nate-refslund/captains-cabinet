#!/bin/bash
# test-cron-roster-redis-guards.sh — regression net for the 2026-07-14
# foundation bughunt findings on the cron/watchdog services:
#
#   runtime-services-3  empty roster + bash 3.2 + set -u must NO-OP, not crash
#                       ("${ARR[@]}" on an empty array is an unbound-variable
#                       fatal under /bin/bash 3.2) — limit-reset-watchdog,
#                       heartbeat-watchdog, cost-summary.
#   officer-fleet-6     heartbeat-watchdog primary roster path must skip a
#                       roster-seeded slug with NO installed LaunchAgent on
#                       this host (never kickstart/alert a phantom).
#   runtime-services-4  briefing/retrospective/health-check must NOT clobber a
#                       caller-set REDIS_HOST with the docker-era `redis`
#                       hostname (conditional derive, caller wins).
#   runtime-services-5  retrospective must FATAL (non-zero, no false success
#                       line) when the triggers lib is missing, and must
#                       source it via CABINET_ROOT, not /opt/founders-cabinet.
#
# Fully sandboxed: PATH-shadowed redis-cli/launchctl/curl stubs, throwaway
# HOME + repo trees — no network, no live launchctl, no real Redis. Uses
# /bin/bash explicitly (macOS 3.2) so the set -u array semantics under test
# are the real ones. Run locally:
#   bash cabinet/tests/watchdog/test-cron-roster-redis-guards.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

mkdir -p "$SANDBOX/bin"
export LAUNCHCTL_LOG="$SANDBOX/launchctl.log"
export REDIS_CLI_LOG="$SANDBOX/redis-cli.log"

# redis-cli stub — records every invocation, answers the handful of shapes the
# scripts use. Keyword scan (not positional) keeps it robust to -h/-p/-t.
cat > "$SANDBOX/bin/redis-cli" <<'EOF'
#!/bin/bash
echo "$@" >> "${REDIS_CLI_LOG:-/dev/null}"
args=" $* "
case "$args" in
  *" PING "*)          echo PONG ;;
  *" EXISTS "*)        echo 0 ;;
  *" INCR "*)          echo 1 ;;
  *" SET "*)           echo OK ;;
  *" EXPIRE "*|*" DEL "*) echo 1 ;;
  *" KEYS "*)          : ;;
  *)                   echo "" ;;
esac
exit 0
EOF
# launchctl stub — records kickstart targets, always "succeeds".
cat > "$SANDBOX/bin/launchctl" <<'EOF'
#!/bin/bash
echo "$@" >> "${LAUNCHCTL_LOG:-/dev/null}"
exit 0
EOF
# curl stub — health-check's send_alert must never reach the network.
cat > "$SANDBOX/bin/curl" <<'EOF'
#!/bin/bash
exit 0
EOF
chmod +x "$SANDBOX/bin/redis-cli" "$SANDBOX/bin/launchctl" "$SANDBOX/bin/curl"
# NOTE: no tmux stub on purpose — limit-reset-watchdog's `command -v tmux`
# guard makes the DETECT branch a clean skip in the sandbox.
SBPATH="$SANDBOX/bin:/usr/bin:/bin"

fails=0
ok()   { echo "  ok   | $1"; }
fail() { echo "  FAIL | $1"; fails=$((fails+1)); }

# --------------------------------------------------------------------------
# 1) runtime-services-3 — empty roster must no-op cleanly under bash 3.2+set -u
# --------------------------------------------------------------------------
EMPTY_REPO="$SANDBOX/repo-empty"
mkdir -p "$EMPTY_REPO" "$SANDBOX/home1"

OUT=$(HOME="$SANDBOX/home1" PATH="$SBPATH" CABINET_SOURCE_REPO="$EMPTY_REPO" \
  /bin/bash "$REPO_ROOT/cabinet/cron/limit-reset-watchdog.sh" 2>&1); rc=$?
if [ "$rc" -eq 0 ] && grep -q "tick complete (0 officer pane(s) scanned)" <<<"$OUT"; then
  ok "limit-reset-watchdog: empty roster → rc=0 + tick heartbeat"
else
  fail "limit-reset-watchdog: empty roster rc=$rc out: $(tail -2 <<<"$OUT")"
fi

OUT=$(HOME="$SANDBOX/home1" PATH="$SBPATH" CABINET_SOURCE_REPO="$EMPTY_REPO" \
  /bin/bash "$REPO_ROOT/cabinet/cron/heartbeat-watchdog.sh" 2>&1); rc=$?
if [ "$rc" -eq 0 ] && grep -q "nothing to watch this tick" <<<"$OUT"; then
  ok "heartbeat-watchdog: empty roster → rc=0 + nothing-to-watch log"
else
  fail "heartbeat-watchdog: empty roster rc=$rc out: $(tail -2 <<<"$OUT")"
fi

OUT=$(HOME="$SANDBOX/home1" PATH="$SBPATH" CABINET_SOURCE_REPO="$EMPTY_REPO" \
  /bin/bash "$REPO_ROOT/cabinet/cron/cost-summary.sh" 2>&1); rc=$?
if [ "$rc" -eq 0 ] && grep -q "totals-only digest" <<<"$OUT"; then
  ok "cost-summary: empty roster → rc=0 + totals-only digest"
else
  fail "cost-summary: empty roster rc=$rc out: $(tail -2 <<<"$OUT")"
fi

# --------------------------------------------------------------------------
# 2) officer-fleet-6 — primary roster path skips slugs with no installed plist
# --------------------------------------------------------------------------
FLEET_REPO="$SANDBOX/repo-fleet"
FLEET_HOME="$SANDBOX/home2"
mkdir -p "$FLEET_REPO/instance/roles/active" "$FLEET_HOME/Library/LaunchAgents" \
         "$FLEET_HOME/Library/Caches/cabinet"
printf 'officer_type: fulltime\n' > "$FLEET_REPO/instance/roles/active/alpha.yml"
printf 'officer_type: fulltime\n' > "$FLEET_REPO/instance/roles/active/beta.yml"
touch "$FLEET_HOME/Library/LaunchAgents/com.cabinet.officer.alpha.plist"
: > "$LAUNCHCTL_LOG"

OUT=$(HOME="$FLEET_HOME" PATH="$SBPATH" CABINET_SOURCE_REPO="$FLEET_REPO" \
  /bin/bash "$REPO_ROOT/cabinet/cron/heartbeat-watchdog.sh" 2>&1); rc=$?
if [ "$rc" -eq 0 ] && grep -q "com.cabinet.officer.alpha" "$LAUNCHCTL_LOG" 2>/dev/null; then
  ok "heartbeat-watchdog: deployed alpha (stale) was kickstarted"
else
  fail "heartbeat-watchdog: deployed alpha not kickstarted (rc=$rc) log: $(cat "$LAUNCHCTL_LOG" 2>/dev/null)"
fi
if grep -q "com.cabinet.officer.beta" "$LAUNCHCTL_LOG" 2>/dev/null; then
  fail "heartbeat-watchdog: UNDEPLOYED beta was kickstarted (phantom restart)"
else
  ok "heartbeat-watchdog: undeployed beta never kickstarted"
fi
if grep -q "skipping beta" <<<"$OUT"; then
  ok "heartbeat-watchdog: undeployed beta skip is logged"
else
  fail "heartbeat-watchdog: no skip log for undeployed beta"
fi

# --------------------------------------------------------------------------
# 3) runtime-services-4 — caller REDIS_HOST survives (no docker-era clobber)
# --------------------------------------------------------------------------
TRIG_REPO="$SANDBOX/repo-trig"
TRIG_LOG="$SANDBOX/trigger.log"
mkdir -p "$TRIG_REPO/cabinet/scripts/lib"
cat > "$TRIG_REPO/cabinet/scripts/lib/triggers.sh" <<EOF
trigger_send() { echo "HOST=\${REDIS_HOST:-unset} PORT=\${REDIS_PORT:-unset} target=\$1" >> "$TRIG_LOG"; return 0; }
EOF

for script in cabinet/cron/briefing.sh cabinet/cron/retrospective.sh; do
  name=$(basename "$script")
  : > "$TRIG_LOG"
  OUT=$(PATH="$SBPATH" CABINET_ROOT="$TRIG_REPO" REDIS_HOST=custom-host.test REDIS_PORT=7777 \
    /bin/bash "$REPO_ROOT/$script" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && grep -q "HOST=custom-host.test PORT=7777" "$TRIG_LOG" 2>/dev/null; then
    ok "$name: caller REDIS_HOST/PORT win (no docker-era clobber)"
  else
    fail "$name: rc=$rc trigger-env: $(cat "$TRIG_LOG" 2>/dev/null) out: $(tail -1 <<<"$OUT")"
  fi
  : > "$TRIG_LOG"
  OUT=$(env -u REDIS_HOST -u REDIS_PORT -u REDIS_URL PATH="$SBPATH" CABINET_ROOT="$TRIG_REPO" \
    /bin/bash "$REPO_ROOT/$script" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && grep -q "HOST=localhost" "$TRIG_LOG" 2>/dev/null; then
    ok "$name: bare run derives localhost (not \`redis\`)"
  else
    fail "$name: bare run rc=$rc trigger-env: $(cat "$TRIG_LOG" 2>/dev/null)"
  fi
done

: > "$REDIS_CLI_LOG"
OUT=$(PATH="$SBPATH" REDIS_HOST=custom-host.test REDIS_PORT=7777 \
  TELEGRAM_COS_TOKEN=dummy CAPTAIN_TELEGRAM_ID=1 \
  /bin/bash "$REPO_ROOT/cabinet/scripts/health-check.sh" 2>&1); rc=$?
if [ "$rc" -eq 0 ] && grep -q -- "-h custom-host.test" "$REDIS_CLI_LOG" 2>/dev/null \
   && ! grep -q -- "-h redis " "$REDIS_CLI_LOG" 2>/dev/null; then
  ok "health-check: caller REDIS_HOST wins (redis-cli probed custom-host.test)"
else
  fail "health-check: rc=$rc redis-cli calls: $(head -1 "$REDIS_CLI_LOG" 2>/dev/null)"
fi

# --------------------------------------------------------------------------
# 4) runtime-services-5 — retrospective FATALs when triggers lib is absent
# --------------------------------------------------------------------------
OUT=$(PATH="$SBPATH" CABINET_ROOT="$EMPTY_REPO" \
  /bin/bash "$REPO_ROOT/cabinet/cron/retrospective.sh" 2>&1); rc=$?
if [ "$rc" -ne 0 ] && grep -q "FATAL" <<<"$OUT" && ! grep -q "Retrospective trigger pushed" <<<"$OUT"; then
  ok "retrospective: missing triggers lib → rc=$rc FATAL, no false success"
else
  fail "retrospective: missing lib rc=$rc out: $(tail -2 <<<"$OUT")"
fi

echo "---"
if [ "$fails" -eq 0 ]; then echo "ALL PASS"; exit 0; else echo "$fails FAIL(S)"; exit 1; fi
