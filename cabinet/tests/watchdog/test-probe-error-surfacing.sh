#!/bin/bash
# test-probe-error-surfacing.sh — F0.10 debt (b): the pipe-watchdog must surface
# transport failures as PROBE ERRORS (an alarm), never swallow them as ''.
#
# Reproduces the original incident shape: redis-cli unavailable/broken. We
# PATH-shadow redis-cli with a stub exiting 127 and run check.py in a SANDBOX
# HOME (no plists, no state, no live kickstarts possible — every WATCH pipe
# resolves "no cadence/plist — skip"), then assert the report line carries
# "PROBE ERRORS" and names redis-cli.
#
# STANDALONE (not wired into cabinet-ci.yml): check.py lives in the screenpipe
# estate (~/.screenpipe), which does not exist on CI runners. Run locally:
#   bash cabinet/tests/watchdog/test-probe-error-surfacing.sh
set -uo pipefail

CHECK="${SCREENPIPE_WATCHDOG:-$HOME/.screenpipe/pipes/pipe-watchdog/check.py}"
if [ ! -f "$CHECK" ]; then
  echo "SKIP: $CHECK not present (screenpipe estate absent — flavor-A-only test)"
  exit 0
fi

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
mkdir -p "$SANDBOX/Library/LaunchAgents" "$SANDBOX/.screenpipe/state" "$SANDBOX/bin"

# Broken redis-cli stub — exits 127 like a missing binary
cat > "$SANDBOX/bin/redis-cli" <<'EOF'
#!/bin/bash
exit 127
EOF
chmod +x "$SANDBOX/bin/redis-cli"

OUT=$(HOME="$SANDBOX" PATH="$SANDBOX/bin:/usr/bin:/bin" HEALTHCHECKS_PING_KEY= \
  /opt/homebrew/bin/python3.12 "$CHECK" 2>&1)

FAIL=0
if ! grep -q "PROBE ERRORS" <<<"$OUT"; then
  echo "FAIL: report does not surface 'PROBE ERRORS' when redis-cli is broken"
  FAIL=1
fi
if ! grep -qi "redis-cli" <<<"$OUT"; then
  echo "FAIL: probe error does not name the failing transport (redis-cli)"
  FAIL=1
fi
if grep -q "HEALED\|kickstart_ok" <<<"$OUT"; then
  echo "FAIL: sandbox run attempted a kickstart — sandbox not inert"
  FAIL=1
fi

if [ "$FAIL" -eq 0 ]; then
  echo "PASS: probe errors surfaced loudly (rc-127 transport -> 'PROBE ERRORS' in report)"
  exit 0
fi
echo "--- captured report ---"
echo "$OUT" | tail -5
exit 1
