#!/bin/bash
# captain-exceptions harness — the Captain's "not that" list, proven END TO END
# through the REAL pre-tool-use.sh, both directions.
#
# CAPTAIN-RULING 2026-07-27: "cabinet should decide what action is allowed. if
# captain wants some specific actions not allowed, captain can just say so and
# cabinet should be able to adjust, e.g. guardrails through hooks."
#
# instance/config/authority-exceptions.yml is that surface. The unit tests
# (cabinet/scripts/lib/tests/test_captain_exceptions.py) prove the evaluator;
# THIS proves the WIRE — that a row the Captain adds actually reaches exit 2 at
# the hook, and that removing it actually restores the allow. An exception
# surface nobody proves is honoured is the same failure as an eval pointed at a
# dead twin.
#
# WHY A TEMP ROOT, NOT THE CHECKOUT. Every probe drives the hook with
# CABINET_ROOT pointed at a throwaway skeleton (framework/ + presets/ +
# policy-shadow.py symlinked in; instance/config/ real and writable). The
# harness therefore NEVER writes a live control surface — not
# authority-exceptions.yml, not authority-enforcing, not observe-only. A test
# that mutates a live safety switch destroys attribution even when it restores.
#
# The skeleton carries its OWN instance/config/authority-enforcing so the typed
# plane is armed for the probes regardless of the host checkout's state — the
# harness must not depend on, or change, whether enforcement is on for real.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HOOK="$REPO_ROOT/cabinet/scripts/hooks/pre-tool-use.sh"
PASS=0; FAIL=0

TMPROOT="$(mktemp -d)"
cleanup() { rm -rf "$TMPROOT"; }
trap cleanup EXIT

ln -s "$REPO_ROOT/framework" "$TMPROOT/framework"
ln -s "$REPO_ROOT/presets"   "$TMPROOT/presets"
mkdir -p "$TMPROOT/cabinet/scripts" "$TMPROOT/instance/config"
ln -s "$REPO_ROOT/cabinet/scripts/lib"             "$TMPROOT/cabinet/scripts/lib"
ln -s "$REPO_ROOT/cabinet/scripts/policy-shadow.py" "$TMPROOT/cabinet/scripts/policy-shadow.py"
: > "$TMPROOT/instance/config/authority-enforcing"

EXC="$TMPROOT/instance/config/authority-exceptions.yml"

# write_exceptions <<'YAML' ... YAML
write_exceptions() { cat > "$EXC"; }

# probe <label> <officer> <tool> <json-tool-input-body> <BLOCK|ALLOW> [expected-substring]
probe() {
  local label="$1" officer="$2" tool="$3" body="$4" expected="$5" want="${6:-}"
  local out exit_code
  out=$(printf '{"tool_name":"%s","tool_input":%s}' "$tool" "$body" \
        | CABINET_ROOT="$TMPROOT" CABINET_HOOK_TEST_MODE=1 OFFICER_NAME="$officer" \
          bash "$HOOK" 2>&1)
  exit_code=$?
  local verdict="FAIL"
  if [ "$expected" = "BLOCK" ]; then
    if [ "$exit_code" = "2" ]; then
      if [ -z "$want" ] || printf '%s' "$out" | grep -qF -- "$want"; then
        verdict="PASS"
      fi
    fi
  else
    [ "$exit_code" = "0" ] && verdict="PASS"
  fi
  if [ "$verdict" = "PASS" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi
  printf "%-6s | %-56s | exit=%s\n" "$verdict" "$label" "$exit_code"
}

echo "=== captain-exceptions: the default posture is EMPTY ==="
write_exceptions <<'YAML'
version: 1
denylist: []
YAML
probe "E1 empty denylist allows benign bash"  cos Bash '{"command":"echo hello"}'          ALLOW
probe "E2 empty denylist allows a read"       cro Read '{"file_path":"/tmp/notes.md"}'     ALLOW

echo ""
echo "=== the file ABSENT is the same as empty (a fresh hatch) ==="
rm -f "$EXC"
probe "E3 absent file allows benign bash"     cos Bash '{"command":"echo hello"}'          ALLOW

echo ""
echo "=== a Captain row REFUSES — and names itself and the why ==="
write_exceptions <<'YAML'
version: 1
denylist:
  - id: no-echo-hello
    why: "synthetic harness row"
    command_contains: "echo hello"
YAML
probe "E4 matching row blocks"                cos Bash '{"command":"echo hello"}'          BLOCK "captain_exception:no-echo-hello"
probe "E5 refusal carries the why"            cos Bash '{"command":"echo hello"}'          BLOCK "synthetic harness row"
probe "E6 non-matching command still allowed" cos Bash '{"command":"echo goodbye"}'        ALLOW
probe "E7 other tools unaffected"             cos Read '{"file_path":"/tmp/notes.md"}'     ALLOW

echo ""
echo "=== REMOVING the row restores the allow (the other direction) ==="
write_exceptions <<'YAML'
version: 1
denylist: []
YAML
probe "E8 row removed -> allowed again"       cos Bash '{"command":"echo hello"}'          ALLOW

echo ""
echo "=== predicates scope: officer / tool / path ==="
write_exceptions <<'YAML'
version: 1
denylist:
  - id: cro-no-bash
    why: "CRO works through the API"
    officer: cro
    tool: Bash
YAML
probe "E9 scoped officer blocked"             cro Bash '{"command":"ls"}'                  BLOCK "captain_exception:cro-no-bash"
probe "E10 other officer NOT blocked"         cos Bash '{"command":"ls"}'                  ALLOW
probe "E11 other tool NOT blocked"            cro Read '{"file_path":"/tmp/notes.md"}'     ALLOW

write_exceptions <<'YAML'
version: 1
denylist:
  - id: billing-frozen
    why: "frozen until the audit closes"
    path_contains: "/billing/"
YAML
probe "E12 path predicate blocks"             cto Edit '{"file_path":"/srv/app/billing/rates.py"}' BLOCK "captain_exception:billing-frozen"
probe "E13 sibling path allowed"              cto Edit '{"file_path":"/srv/app/docs/rates.md"}'    ALLOW

echo ""
echo "=== FAIL CLOSED: an unreadable exclusion list is never ignored ==="
printf 'version: 1\ndenylist: [ broken: yaml: here\n' > "$EXC"
probe "E14 unparseable file refuses"          cos Bash '{"command":"echo hello"}'          BLOCK "captain_exceptions"
# Erasure must be LOUD. `ln -sf /dev/null <path>` would otherwise read as
# ABSENT — i.e. as an empty denylist — silently dropping every exclusion.
rm -f "$EXC"; ln -s /dev/null "$EXC"
probe "E14b symlink refuses (erasure is loud)" cos Bash '{"command":"echo hello"}'         BLOCK "symlink"
rm -f "$EXC"; mkdir -p "$EXC"
probe "E14c directory refuses"                cos Bash '{"command":"echo hello"}'          BLOCK "regular file"
rmdir "$EXC"
write_exceptions <<'YAML'
version: 1
denylist:
  - id: oops
    why: "predicate forgotten"
YAML
probe "E15 predicate-less row is an ERROR"    cos Bash '{"command":"echo hello"}'          BLOCK "captain_exceptions_malformed"

echo ""
echo "=== E-STOP: removing authority-enforcing disarms the plane entirely ==="
write_exceptions <<'YAML'
version: 1
denylist:
  - id: no-echo-hello
    why: "synthetic harness row"
    command_contains: "echo hello"
YAML
probe "E16 armed -> blocked"                  cos Bash '{"command":"echo hello"}'          BLOCK "captain_exception:no-echo-hello"
rm -f "$TMPROOT/instance/config/authority-enforcing"
probe "E17 disarmed -> allowed (E-stop works)" cos Bash '{"command":"echo hello"}'         ALLOW
: > "$TMPROOT/instance/config/authority-enforcing"

echo ""
echo "captain-exceptions: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
